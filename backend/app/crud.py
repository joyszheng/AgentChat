from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from . import models, schemas


INTERRUPTED_DOCUMENT_STATUSES = ("uploaded", "processing", "parsing", "chunking", "indexing")


def create_task(db: Session, task: schemas.TaskCreate):
    """创建任务并返回包含数据库生成 ID 的记录。"""
    db_task = models.Task(
        title=task.title,
        description=task.description,
        completed=task.completed
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def list_tasks(
    db: Session,
    completed: bool | None = None,
    skip: int = 0,
    limit: int = 10
):
    """按完成状态筛选任务，并支持分页查询。"""
    query = db.query(models.Task)

    if completed is not None:
        query = query.filter(models.Task.completed == completed)

    return query.offset(skip).limit(limit).all()


def get_task(db: Session, task_id: int):
    """按 ID 查询单个任务；不存在时返回 None。"""
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def update_task(db: Session, task_id: int, task_update: schemas.TaskCreate):
    """用完整请求体替换任务内容。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    task.title = task_update.title
    task.description = task_update.description
    task.completed = task_update.completed

    db.commit()
    db.refresh(task)
    return task


def partial_update_task(db: Session, task_id: int, task_update: schemas.TaskUpdate):
    """仅更新请求中显式提供的字段。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    # 排除未传入的字段，避免 PATCH 请求意外覆盖已有数据。
    update_data = task_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int):
    """删除指定任务；不存在时返回 None。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    db.delete(task)
    db.commit()
    return task


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


def create_chat_session(db: Session, *, title: str | None = None, mode: str = "chat"):
    """创建一个多轮对话会话。"""

    session = models.ChatSession(title=title, mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_chat_session(db: Session, session_id: int):
    """按 ID 查询会话。"""

    return db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()


def delete_chat_session(db: Session, session_id: int) -> bool:
    """删除会话及其关联消息；会话不存在时返回 False。"""

    session = get_chat_session(db, session_id)
    if session is None:
        return False

    db.delete(session)
    db.commit()
    return True


def get_or_create_chat_session(
    db: Session,
    *,
    session_id: int | None = None,
    title: str | None = None,
    mode: str = "chat",
):
    """传入 session_id 时复用会话；未传入时创建新会话。"""

    if session_id is not None:
        return get_chat_session(db, session_id)

    return create_chat_session(db, title=title, mode=mode)


def list_chat_sessions(db: Session, skip: int = 0, limit: int = 20):
    """按最近消息时间倒序查询会话列表。"""

    return (
        db.query(models.ChatSession)
        .order_by(
            models.ChatSession.last_message_at.desc().nullslast(),
            models.ChatSession.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_chat_message(
    db: Session,
    *,
    session_id: int,
    role: str,
    content: str,
    message_metadata: dict | None = None,
):
    """保存一条会话消息，并刷新会话最近消息时间。"""

    message = models.ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        message_metadata=message_metadata or {},
    )
    db.add(message)

    session = get_chat_session(db, session_id)
    if session is not None:
        session.last_message_at = func.now()

    db.commit()
    db.refresh(message)

    return message


def list_chat_messages(db: Session, session_id: int, skip: int = 0, limit: int = 50):
    """按时间正序查询会话消息。"""

    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc(), models.ChatMessage.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_recent_chat_messages(db: Session, session_id: int, limit: int = 10):
    """获取最近 N 条消息，并按时间正序返回。"""

    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(messages))
