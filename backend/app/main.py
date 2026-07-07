import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import DateTime, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, StreamingResponse

from pathlib import Path
from uuid import uuid4

from . import crud, models, schemas
from .ai.document_processing import DocumentProcessingError, validate_document_extension
from .ai.config import get_embeddings_from_config
from .ai.rag import delete_document_from_index, ingest_upload
from .database import SessionLocal, engine, get_db
from .routers import tasks, ai, settings, auth, mcp as mcp_router
from .mcp import mcp_registry
from .services.email import send_email, format_document_notification_email
from .services.dependencies import require_auth
from .services.config import migrate_legacy_ai_settings


logger = logging.getLogger("uvicorn.error")


def _ensure_chat_session_soft_delete_schema() -> bool:
    """Add deleted_at and its index for installations created before soft deletion."""
    inspector = inspect(engine)
    if not inspector.has_table("chat_sessions"):
        return False

    schema_changed = False
    column_names = {
        column["name"]
        for column in inspector.get_columns("chat_sessions")
    }
    if "deleted_at" not in column_names:
        column_type = DateTime(timezone=True).compile(dialect=engine.dialect)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE chat_sessions "
                    f"ADD COLUMN deleted_at {column_type} NULL"
                )
            )
        schema_changed = True

    index_names = {
        index["name"]
        for index in inspect(engine).get_indexes("chat_sessions")
    }
    if "ix_chat_sessions_deleted_at" not in index_names:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_sessions_deleted_at "
                    "ON chat_sessions (deleted_at)"
                )
            )
        schema_changed = True

    return schema_changed


def _ensure_uploaded_document_unique_schema() -> bool:
    """为旧安装补齐上传文档的重复保护索引。"""

    inspector = inspect(engine)
    if not inspector.has_table("uploaded_documents"):
        return False

    index_names = {
        index["name"]
        for index in inspector.get_indexes("uploaded_documents")
    }
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("uploaded_documents")
    }
    if (
        "uq_uploaded_document_name_hash" in index_names
        or "uq_uploaded_document_name_hash" in unique_constraints
    ):
        return False

    with engine.begin() as connection:
        duplicate = connection.execute(
            text(
                "SELECT original_filename, file_sha256, COUNT(*) AS duplicate_count "
                "FROM uploaded_documents "
                "WHERE file_sha256 IS NOT NULL "
                "GROUP BY original_filename, file_sha256 "
                "HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        ).mappings().first()
    if duplicate is not None:
        logger.warning(
            "[database] Uploaded document duplicate guard not created; "
            "duplicate rows exist filename=%r sha256=%s count=%s",
            duplicate["original_filename"],
            str(duplicate["file_sha256"])[:12],
            duplicate["duplicate_count"],
        )
        return False

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_uploaded_document_name_hash "
                    "ON uploaded_documents (original_filename, file_sha256)"
                )
            )
    except SQLAlchemyError:
        logger.warning(
            "[database] Could not add uploaded_documents duplicate guard; "
            "existing duplicate rows may need manual cleanup"
        )
        return False

    return True


# 开发阶段启动时自动建表；生产环境建议改用数据库迁移工具。
models.Base.metadata.create_all(bind=engine)
soft_delete_schema_added = _ensure_chat_session_soft_delete_schema()
upload_unique_schema_added = _ensure_uploaded_document_unique_schema()

if soft_delete_schema_added:
    logger.info("[database] Ensured chat_sessions soft-delete schema")
if upload_unique_schema_added:
    logger.info("[database] Ensured uploaded_documents duplicate guard schema")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        migrated_ai_settings = migrate_legacy_ai_settings(db)
        interrupted_count = crud.fail_interrupted_uploaded_documents(db)
    for legacy_key, current_key in migrated_ai_settings:
        logger.info("[config] Migrated setting key %s -> %s", legacy_key, current_key)
    if interrupted_count:
        logger.warning(
            "[upload] Recovered interrupted tasks count=%s action=marked_failed",
            interrupted_count,
        )

    # 首次启动初始化默认管理员
    from .services.auth import get_password_hash
    import os

    with SessionLocal() as db:
        user_count = crud.count_users(db)
        if user_count == 0:
            default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
            default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
            default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@agentchat.local")

            crud.create_user(
                db,
                username=default_username,
                password_hash=get_password_hash(default_password),
                email=default_email,
                role="admin",
            )

            logger.warning(
                "[auth] ============================================"
            )
            logger.warning(
                "[auth] Default admin created:"
            )
            logger.warning(
                "[auth]   Username: %s", default_username
            )
            logger.warning(
                "[auth]   Password: %s", default_password
            )
            logger.warning(
                "[auth] Please login and change the password!"
            )
            logger.warning(
                "[auth] ============================================"
            )

    _app.state.mcp_registry = mcp_registry
    await mcp_registry.refresh()
    try:
        yield
    finally:
        await mcp_registry.close()


app = FastAPI(lifespan=lifespan)

DOCUMENT_PROGRESS = {
    "uploaded": (5, "文件已上传"),
    "processing": (10, "等待开始处理"),
    "parsing": (25, "正在解析文档内容"),
    "chunking": (55, "正在清洗并切分文本"),
    "indexing": (75, "正在生成向量并写入索引"),
    "indexed": (100, "文档处理完成"),
    "failed": (100, "文档处理失败"),
}
TERMINAL_DOCUMENT_STATUSES = {"indexed", "failed"}
ACTIVE_DOCUMENT_STATUSES = {"uploaded", "processing", "parsing", "chunking", "indexing"}
DOCUMENT_PROGRESS_POLL_INTERVAL = 0.5
DOCUMENT_PROGRESS_UPDATE_INTERVAL = 3.0
DOCUMENT_PROGRESS_STREAM_LIFETIME = 10.0

# 允许本地前端开发服务器访问 API。
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://frp-six.com:46189",
    "https://frp-six.com:46189",
    "https://noproblem.icu:46189",
    "https://www.r853982.nyat.app:46189"
]

# 添加跨域中间件，使前端能携带凭据调用后端接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# 将任务相关路由注册到主应用。
app.include_router(ai.router)
app.include_router(tasks.router)
app.include_router(settings.router)
app.include_router(auth.router)
app.include_router(mcp_router.router)


@app.get("/")
def read_root():
    """提供最小的服务存活检查接口。"""

    return {"Hello": "World"}

# 统一保存上传文件，并在首次启动时自动创建目录。
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 文档处理完成后的邮件通知接收地址
DOCUMENT_NOTIFICATION_EMAIL = "2810363752@qq.com"


async def _send_document_notification_email(
    *,
    document_id: int,
    original_filename: str,
    size_bytes: int,
    status: str,
    document_count: int = 0,
    chunk_count: int = 0,
    warnings: list[str] | None = None,
    error_message: str | None = None,
) -> None:
    """发送文档处理完成通知邮件。"""
    try:
        with SessionLocal() as db:
            document = crud.get_uploaded_document(db, document_id)
            if document is None:
                logger.warning("[email] Document not found, skipping notification document_id=%s", document_id)
                return

            created_at = document.created_at.strftime("%Y-%m-%d %H:%M:%S")

            # 从数据库读取邮件配置
            from .services.email import get_email_config_from_db
            email_config = get_email_config_from_db(db)

            # 获取通知接收邮箱（优先从数据库读取）
            from .services.config import get_config_service
            config_service = get_config_service(db)
            notification_email = config_service.get(
                "document_notification_email",
                DOCUMENT_NOTIFICATION_EMAIL,
            )

        subject, body = format_document_notification_email(
            original_filename=original_filename,
            size_bytes=size_bytes,
            status=status,
            created_at=created_at,
            document_count=document_count,
            chunk_count=chunk_count,
            warnings=warnings or [],
            error_message=error_message,
        )

        success = await send_email(
            to=notification_email,
            subject=subject,
            body=body,
            config_override=email_config,
        )

        if success:
            logger.info(
                "[upload:%s] Email notification sent to=%s status=%s",
                document_id,
                notification_email,
                status,
            )
        else:
            logger.warning(
                "[upload:%s] Email notification failed to=%s status=%s",
                document_id,
                notification_email,
                status,
            )

    except Exception as exc:
        logger.exception(
            "[upload:%s] Email notification error document_id=%s error=%s",
            document_id,
            document_id,
            exc,
        )


def process_uploaded_document(
    document_id: int,
    file_path: Path,
    *,
    original_filename: str,
    content_type: str | None,
) -> None:
    """Parse and index an uploaded document outside the request lifecycle."""

    started_at = time.perf_counter()
    logger.info(
        "[upload:%s] Background processing started file=%r stored=%s",
        document_id,
        original_filename,
        file_path.name,
    )
    db = SessionLocal()

    def update_stage(stage: str, *, chunk_count: int | None = None) -> None:
        document = crud.mark_uploaded_document_stage(
            db,
            document_id,
            stage=stage,
            chunk_count=chunk_count,
        )
        if document is None:
            raise RuntimeError(f"上传文档记录不存在：{document_id}")

        progress, message = DOCUMENT_PROGRESS[stage]
        logger.info(
            "[upload:%s] Progress updated stage=%s progress=%s message=%s",
            document_id,
            stage,
            progress,
            message,
        )

    try:
        processed, chunk_count = ingest_upload(
            file_path,
            original_filename=original_filename,
            content_type=content_type,
            document_id=document_id,
            progress_callback=update_stage,
            embedding_function=get_embeddings_from_config(db),
        )

        file_sha256 = None
        if processed.documents:
            file_sha256 = processed.documents[0].metadata.get("file_sha256")

        crud.mark_uploaded_document_indexed(
            db,
            document_id,
            document_count=len(processed.documents),
            chunk_count=chunk_count,
            file_sha256=file_sha256,
            warnings=processed.warnings,
        )
        logger.info(
            "[upload:%s] Background processing completed status=indexed documents=%s "
            "chunks=%s elapsed=%.2fs",
            document_id,
            len(processed.documents),
            chunk_count,
            time.perf_counter() - started_at,
        )

        # 发送邮件通知文档处理成功
        try:
            asyncio.run(_send_document_notification_email(
                document_id=document_id,
                original_filename=original_filename,
                size_bytes=file_path.stat().st_size,
                status="indexed",
                document_count=len(processed.documents),
                chunk_count=chunk_count,
                warnings=processed.warnings,
            ))
        except Exception:
            logger.exception("Failed to send document notification email")

    except DocumentProcessingError as exc:
        db.rollback()
        crud.mark_uploaded_document_failed(db, document_id, error_message=str(exc))
        logger.exception(
            "[upload:%s] Background processing failed stage=parse elapsed=%.2fs error=%s",
            document_id,
            time.perf_counter() - started_at,
            exc,
        )

        # 发送邮件通知文档处理失败
        try:
            asyncio.run(_send_document_notification_email(
                document_id=document_id,
                original_filename=original_filename,
                size_bytes=file_path.stat().st_size,
                status="failed",
                error_message=str(exc),
            ))
        except Exception:
            logger.exception("Failed to send document notification email")

    except Exception as exc:
        db.rollback()
        error_message = f"文档入库失败：{exc}"
        crud.mark_uploaded_document_failed(db, document_id, error_message=error_message)
        logger.exception(
            "[upload:%s] Background processing failed stage=index elapsed=%.2fs error=%s",
            document_id,
            time.perf_counter() - started_at,
            exc,
        )

        # 发送邮件通知文档处理失败
        try:
            asyncio.run(_send_document_notification_email(
                document_id=document_id,
                original_filename=original_filename,
                size_bytes=file_path.stat().st_size,
                status="failed",
                error_message=error_message,
            ))
        except Exception:
            logger.exception("Failed to send document notification email")

    finally:
        db.close()


@app.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "description": "文件格式不受支持",
        },
    },
)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """保存上传文件，并在后台解析文本、写入 RAG 检索索引。"""

    original_filename = file.filename or "uploaded-file"
    logger.info(
        "[upload] Request received file=%r content_type=%s",
        original_filename,
        file.content_type or "unknown",
    )
    try:
        suffix = validate_document_extension(original_filename)
    except DocumentProcessingError as exc:
        logger.warning(
            "[upload] Request rejected file=%r content_type=%s reason=%s",
            original_filename,
            file.content_type or "unknown",
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    read_started_at = time.perf_counter()
    content = await file.read()
    logger.info(
        "[upload] File read completed file=%r type=%s size=%s bytes elapsed=%.3fs",
        original_filename,
        suffix,
        len(content),
        time.perf_counter() - read_started_at,
    )

    file_sha256 = hashlib.sha256(content).hexdigest()
    duplicate_document = crud.get_uploaded_document_by_name_hash(
        db,
        original_filename=original_filename,
        file_sha256=file_sha256,
    )
    if duplicate_document is not None:
        logger.info(
            "[upload] Duplicate rejected file=%r sha256=%s existing_document_id=%s",
            original_filename,
            file_sha256[:12],
            duplicate_document.id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同名且内容相同的文档已存在，请勿重复上传",
        )

    new_filename = f"{uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / new_filename

    file_path.write_bytes(content)

    try:
        upload_record = crud.create_uploaded_document(
            db,
            original_filename=original_filename,
            stored_filename=new_filename,
            content_type=file.content_type,
            file_ext=suffix,
            size_bytes=len(content),
            saved_to=str(file_path),
            file_sha256=file_sha256,
        )
    except IntegrityError as exc:
        db.rollback()
        file_path.unlink(missing_ok=True)
        logger.info(
            "[upload] Duplicate rejected by database file=%r sha256=%s",
            original_filename,
            file_sha256[:12],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同名且内容相同的文档已存在，请勿重复上传",
        ) from exc
    upload_record = crud.mark_uploaded_document_processing(db, upload_record.id)

    logger.info(
        "[upload:%s] File saved and queued file=%r stored=%s size=%s bytes",
        upload_record.id,
        original_filename,
        new_filename,
        len(content),
    )

    background_tasks.add_task(
        process_uploaded_document,
        upload_record.id,
        file_path,
        original_filename=original_filename,
        content_type=file.content_type,
    )

    return {
        "document_id": upload_record.id,
        "filename": new_filename,
        "original_filename": original_filename,
        "content_type": file.content_type,
        "size": len(content),
        "saved_to": str(file_path),
        "indexed": False,
        "status": upload_record.status,
        "document_count": 0,
        "chunk_count": 0,
        "warnings": [],
        "message": "文件上传成功，正在后台解析并加入 RAG 索引",
    }


@app.get("/documents", response_model=list[schemas.UploadedDocumentResponse])
def list_documents(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    """查询上传文档记录。"""

    return crud.list_uploaded_documents(db, skip=skip, limit=limit)


@app.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    """下载上传时保存的原始文档。"""

    document = crud.get_uploaded_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    stored_path = _resolve_upload_path(document.saved_to, document_id=document_id)
    if not stored_path.is_file():
        logger.warning(
            "[upload:%s] Download failed reason=file_missing path=%s",
            document_id,
            stored_path,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="文档原文件已不存在",
        )

    logger.info(
        "[upload:%s] Original file download file=%r stored=%s size=%s bytes",
        document_id,
        document.original_filename,
        stored_path.name,
        stored_path.stat().st_size,
    )
    return FileResponse(
        path=stored_path,
        media_type=document.content_type or "application/octet-stream",
        filename=document.original_filename,
    )


@app.delete(
    "/documents/{document_id}",
    response_model=schemas.UploadedDocumentDeleteResponse,
)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user = Depends(require_auth),
) -> schemas.UploadedDocumentDeleteResponse:
    """删除文档记录、本地文件，并在已生成分片时清理向量索引。需要登录。"""

    document = crud.get_uploaded_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    if document.status in ACTIVE_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="文档正在处理中，请等待处理完成或失败后再删除",
        )

    stored_path = _resolve_upload_path(document.saved_to, document_id=document_id)

    vector_chunks_deleted = 0
    if document.status == "indexed" or document.chunk_count > 0:
        try:
            vector_chunks_deleted = delete_document_from_index(
                document_id=document_id,
                file_sha256=document.file_sha256,
                source=document.saved_to,
            )
        except Exception as exc:
            logger.exception(
                "[upload:%s] Delete failed stage=vector_cleanup error=%s",
                document_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="向量索引清理失败，文档尚未删除，请稍后重试",
            ) from exc

    try:
        file_deleted = stored_path.exists()
        if file_deleted:
            stored_path.unlink()
    except OSError as exc:
        logger.exception(
            "[upload:%s] Delete failed stage=file_cleanup path=%s error=%s",
            document_id,
            stored_path,
            exc,
        )
        raise HTTPException(status_code=500, detail="本地文件删除失败，请稍后重试") from exc

    crud.delete_uploaded_document(db, document_id)
    logger.info(
        "[upload:%s] Document deleted file_deleted=%s vector_chunks_deleted=%s",
        document_id,
        file_deleted,
        vector_chunks_deleted,
    )
    return schemas.UploadedDocumentDeleteResponse(
        document_id=document_id,
        deleted=True,
        file_deleted=file_deleted,
        vector_chunks_deleted=vector_chunks_deleted,
    )


@app.get("/documents/{document_id}/progress")
async def stream_document_progress(document_id: int, request: Request) -> StreamingResponse:
    """通过 SSE 推送文档解析和索引进度，直到成功或失败。"""

    with SessionLocal() as db:
        document = crud.get_uploaded_document(db, document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    async def event_stream():
        last_payload: dict | None = None
        stream_started_at = time.monotonic()
        stage_started_at = stream_started_at
        last_progress_event_at = stream_started_at

        while not await request.is_disconnected():
            with SessionLocal() as stream_db:
                current_document = crud.get_uploaded_document(stream_db, document_id)
                payload = (
                    _document_progress_payload(current_document)
                    if current_document is not None
                    else None
                )

            if payload is None:
                yield _sse_event(
                    "failed",
                    {
                        "document_id": document_id,
                        "code": "document_deleted",
                        "message": "文档记录已被删除",
                    },
                )
                return

            if payload != last_payload:
                event = "progress"
                if payload["status"] == "indexed":
                    event = "complete"
                elif payload["status"] == "failed":
                    event = "failed"

                yield _sse_event(event, payload)
                last_payload = payload
                stage_started_at = time.monotonic()
                last_progress_event_at = stage_started_at

                if payload["status"] in TERMINAL_DOCUMENT_STATUSES:
                    return

            now = time.monotonic()
            if (
                last_payload is not None
                and last_payload["status"] in ACTIVE_DOCUMENT_STATUSES
                and now - last_progress_event_at >= DOCUMENT_PROGRESS_UPDATE_INTERVAL
            ):
                elapsed_seconds = int(now - stage_started_at)
                progress_payload = {
                    **last_payload,
                    "stage_elapsed_seconds": elapsed_seconds,
                    "detail": f"{last_payload['message']}，已持续 {elapsed_seconds} 秒",
                }
                yield _sse_event("progress", progress_payload)
                last_progress_event_at = now

            if now - stream_started_at >= DOCUMENT_PROGRESS_STREAM_LIFETIME:
                yield _sse_event(
                    "reconnect",
                    {
                        "document_id": document_id,
                        "message": "进度流连接周期结束，客户端将自动重连",
                    },
                )
                return

            await asyncio.sleep(DOCUMENT_PROGRESS_POLL_INTERVAL)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _document_progress_payload(document) -> dict:
    progress, message = DOCUMENT_PROGRESS.get(
        document.status,
        (0, "等待处理状态更新"),
    )
    return {
        "document_id": document.id,
        "filename": document.original_filename,
        "status": document.status,
        "progress": progress,
        "message": message,
        "document_count": document.document_count,
        "chunk_count": document.chunk_count,
        "warnings": document.warnings,
        "error_message": document.error_message,
        "updated_at": document.updated_at.isoformat(),
    }


def _resolve_upload_path(saved_to: str, *, document_id: int) -> Path:
    stored_path = Path(saved_to).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if not stored_path.is_relative_to(upload_root):
        logger.error(
            "[upload:%s] File access rejected reason=unsafe_path path=%s upload_root=%s",
            document_id,
            stored_path,
            upload_root,
        )
        raise HTTPException(status_code=500, detail="文档存储路径异常，已拒绝访问")

    return stored_path


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
