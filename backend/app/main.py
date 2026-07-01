import logging
import time
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from pathlib import Path
from uuid import uuid4

from . import crud, models, schemas
from .ai.document_processing import DocumentProcessingError
from .ai.rag import ingest_upload
from .database import SessionLocal, engine, get_db
from .routers import tasks, ai


# 开发阶段启动时自动建表；生产环境建议改用数据库迁移工具。
models.Base.metadata.create_all(bind=engine)

app = FastAPI()
# Reuse Uvicorn's configured logger so INFO progress is visible in the server terminal.
logger = logging.getLogger("uvicorn.error")

# 允许本地前端开发服务器访问 API。
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 添加跨域中间件，使前端能携带凭据调用后端接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 将任务相关路由注册到主应用。
app.include_router(ai.router)
app.include_router(tasks.router)


@app.get("/")
def read_root():
    """提供最小的服务存活检查接口。"""

    return {"Hello": "World"}

# 统一保存上传文件，并在首次启动时自动创建目录。
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

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
    try:
        processed, chunk_count = ingest_upload(
            file_path,
            original_filename=original_filename,
            content_type=content_type,
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
    except DocumentProcessingError as exc:
        db.rollback()
        crud.mark_uploaded_document_failed(db, document_id, error_message=str(exc))
        logger.exception(
            "[upload:%s] Background processing failed stage=parse elapsed=%.2fs error=%s",
            document_id,
            time.perf_counter() - started_at,
            exc,
        )
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
    finally:
        db.close()


@app.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """保存上传文件，并在后台解析文本、写入 RAG 检索索引。"""

    content = await file.read()

    original_filename = file.filename or "uploaded-file"
    suffix = Path(original_filename).suffix.lower()
    new_filename = f"{uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / new_filename

    file_path.write_bytes(content)

    upload_record = crud.create_uploaded_document(
        db,
        original_filename=original_filename,
        stored_filename=new_filename,
        content_type=file.content_type,
        file_ext=suffix,
        size_bytes=len(content),
        saved_to=str(file_path),
    )
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
