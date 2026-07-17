import asyncio
import logging
import time
from pathlib import Path

from .. import crud
from ..ai.config import get_embeddings_from_config
from ..ai.document_processing import DocumentProcessingError
from ..ai.rag import ingest_upload
from ..database import SessionLocal
from .document_notifications import send_document_notification_email


logger = logging.getLogger("uvicorn.error")

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

        try:
            asyncio.run(
                send_document_notification_email(
                    document_id=document_id,
                    original_filename=original_filename,
                    size_bytes=file_path.stat().st_size,
                    status="indexed",
                    document_count=len(processed.documents),
                    chunk_count=chunk_count,
                    warnings=processed.warnings,
                )
            )
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

        try:
            asyncio.run(
                send_document_notification_email(
                    document_id=document_id,
                    original_filename=original_filename,
                    size_bytes=file_path.stat().st_size,
                    status="failed",
                    error_message=str(exc),
                )
            )
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

        try:
            asyncio.run(
                send_document_notification_email(
                    document_id=document_id,
                    original_filename=original_filename,
                    size_bytes=file_path.stat().st_size,
                    status="failed",
                    error_message=error_message,
                )
            )
        except Exception:
            logger.exception("Failed to send document notification email")

    finally:
        db.close()
