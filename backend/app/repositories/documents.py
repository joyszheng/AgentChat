from sqlalchemy.orm import Session

from .. import models


INTERRUPTED_DOCUMENT_STATUSES = ("uploaded", "processing", "parsing", "chunking", "indexing")


def create_uploaded_document(
    db: Session,
    *,
    original_filename: str,
    stored_filename: str,
    content_type: str | None,
    file_ext: str,
    size_bytes: int,
    saved_to: str,
    file_sha256: str | None = None,
):
    """创建上传文件记录，初始状态为 uploaded。"""

    document = models.UploadedDocument(
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_ext=file_ext,
        size_bytes=size_bytes,
        saved_to=saved_to,
        file_sha256=file_sha256,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_processing(db: Session, document_id: int):
    """Mark an uploaded document as being processed by the background worker."""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "processing"
    document.error_message = None

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_stage(
    db: Session,
    document_id: int,
    *,
    stage: str,
    chunk_count: int | None = None,
):
    """更新文档处理阶段，供列表查询和 SSE 进度订阅使用。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = stage
    document.error_message = None
    if chunk_count is not None:
        document.chunk_count = chunk_count

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_indexed(
    db: Session,
    document_id: int,
    *,
    document_count: int,
    chunk_count: int,
    file_sha256: str | None,
    warnings: list[str],
):
    """标记上传文件已成功解析并加入 RAG 索引。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "indexed"
    document.document_count = document_count
    document.chunk_count = chunk_count
    if file_sha256 is not None:
        document.file_sha256 = file_sha256
    document.warnings = warnings
    document.error_message = None

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_failed(db: Session, document_id: int, *, error_message: str):
    """标记上传文件解析或入库失败，并保存失败原因。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "failed"
    document.error_message = error_message

    db.commit()
    db.refresh(document)

    return document


def fail_interrupted_uploaded_documents(db: Session) -> int:
    """服务重启后，将无法继续执行的后台上传任务标记为失败。"""

    interrupted_count = (
        db.query(models.UploadedDocument)
        .filter(models.UploadedDocument.status.in_(INTERRUPTED_DOCUMENT_STATUSES))
        .update(
            {
                models.UploadedDocument.status: "failed",
                models.UploadedDocument.error_message: (
                    "服务重启导致后台处理任务中断，请删除后重新上传"
                ),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return interrupted_count


def get_uploaded_document(db: Session, document_id: int):
    """按 ID 查询上传文件记录。"""

    return db.query(models.UploadedDocument).filter(models.UploadedDocument.id == document_id).first()


def get_uploaded_document_by_name_hash(
    db: Session,
    *,
    original_filename: str,
    file_sha256: str,
):
    """查询是否已存在同名且内容完全相同的上传文件。"""

    return (
        db.query(models.UploadedDocument)
        .filter(models.UploadedDocument.original_filename == original_filename)
        .filter(models.UploadedDocument.file_sha256 == file_sha256)
        .first()
    )


def list_uploaded_documents(db: Session, skip: int = 0, limit: int = 20):
    """按创建时间倒序查询上传文件记录。"""

    return (
        db.query(models.UploadedDocument)
        .order_by(models.UploadedDocument.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_uploaded_document(db: Session, document_id: int) -> bool:
    """删除上传文档记录；记录不存在时返回 False。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return False

    db.delete(document)
    db.commit()
    return True
