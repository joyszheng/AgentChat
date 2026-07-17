import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, StreamingResponse

from .. import crud, schemas
from ..ai.document_processing import DocumentProcessingError, validate_document_extension
from ..ai.rag import delete_document_from_index
from ..database import SessionLocal, get_db
from ..services.dependencies import require_auth
from ..services.document_ingestion import (
    ACTIVE_DOCUMENT_STATUSES,
    DOCUMENT_PROGRESS,
    TERMINAL_DOCUMENT_STATUSES,
    process_uploaded_document,
)
from ..services.upload_policy import (
    content_length_is_definitely_too_large,
    get_upload_chunk_read_bytes,
    limit_message,
    upload_limit_for_suffix,
    upload_policy,
)


logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["documents"])

DOCUMENT_PROGRESS_POLL_INTERVAL = 0.5
DOCUMENT_PROGRESS_UPDATE_INTERVAL = 3.0
DOCUMENT_PROGRESS_STREAM_LIFETIME = 10.0

# 统一保存上传文件，并在首次启动时自动创建目录。
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post(
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
    request: Request,
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

    max_upload_bytes = upload_limit_for_suffix(suffix)
    if content_length_is_definitely_too_large(
        request.headers.get("content-length"),
        max_upload_bytes,
    ):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "upload_too_large",
                "message": limit_message(original_filename, max_upload_bytes),
                "max_bytes": max_upload_bytes,
            },
        )

    new_filename = f"{uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / new_filename
    temp_path = UPLOAD_DIR / f".{new_filename}.tmp"

    read_started_at = time.perf_counter()
    size_bytes = 0
    digest = hashlib.sha256()
    chunk_size = get_upload_chunk_read_bytes()
    try:
        with temp_path.open("wb") as output_file:
            while chunk := await file.read(chunk_size):
                size_bytes += len(chunk)
                if size_bytes > max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail={
                            "code": "upload_too_large",
                            "message": limit_message(
                                original_filename,
                                max_upload_bytes,
                                size_bytes,
                            ),
                            "max_bytes": max_upload_bytes,
                            "actual_bytes": size_bytes,
                        },
                    )
                digest.update(chunk)
                output_file.write(chunk)
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        logger.exception("[upload] File save failed file=%r error=%s", original_filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File save failed",
        ) from exc
    logger.info(
        "[upload] File read completed file=%r type=%s size=%s bytes elapsed=%.3fs",
        original_filename,
        suffix,
        size_bytes,
        time.perf_counter() - read_started_at,
    )

    file_sha256 = digest.hexdigest()
    duplicate_document = crud.get_uploaded_document_by_name_hash(
        db,
        original_filename=original_filename,
        file_sha256=file_sha256,
    )
    if duplicate_document is not None:
        temp_path.unlink(missing_ok=True)
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

    temp_path.replace(file_path)

    try:
        upload_record = crud.create_uploaded_document(
            db,
            original_filename=original_filename,
            stored_filename=new_filename,
            content_type=file.content_type,
            file_ext=suffix,
            size_bytes=size_bytes,
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
        size_bytes,
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
        "size": size_bytes,
        "saved_to": str(file_path),
        "indexed": False,
        "status": upload_record.status,
        "document_count": 0,
        "chunk_count": 0,
        "warnings": [],
        "message": "文件上传成功，正在后台解析并加入 RAG 索引",
    }


@router.get("/documents/upload-policy")
def get_document_upload_policy():
    return upload_policy()


@router.get("/documents", response_model=list[schemas.UploadedDocumentResponse])
def list_documents(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    """查询上传文档记录。"""

    return crud.list_uploaded_documents(db, skip=skip, limit=limit)


@router.get("/documents/{document_id}/download")
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


@router.delete(
    "/documents/{document_id}",
    response_model=schemas.UploadedDocumentDeleteResponse,
)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
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


@router.get("/documents/{document_id}/progress")
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
