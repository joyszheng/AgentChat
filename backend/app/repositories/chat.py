from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .. import models


def create_chat_session(db: Session, *, title: str | None = None, mode: str = "chat"):
    """创建一个多轮对话会话。"""

    session = models.ChatSession(title=title, mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_chat_session(db: Session, session_id: int, *, include_deleted: bool = False):
    """按 ID 查询会话，默认排除已软删除的记录。"""

    query = db.query(models.ChatSession).filter(models.ChatSession.id == session_id)
    if not include_deleted:
        query = query.filter(models.ChatSession.deleted_at.is_(None))
    return query.first()


def delete_chat_session(db: Session, session_id: int) -> bool:
    """软删除会话并保留关联消息；会话不存在时返回 False。"""

    session = get_chat_session(db, session_id)
    if session is None:
        return False

    session.deleted_at = func.now()
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
        .filter(models.ChatSession.deleted_at.is_(None))
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
