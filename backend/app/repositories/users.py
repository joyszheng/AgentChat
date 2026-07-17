from sqlalchemy.orm import Session

from .. import models


def get_user_by_username(db: Session, username: str):
    """按用户名查询用户。"""
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str):
    """按邮箱查询用户。"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: int):
    """按 ID 查询用户。"""
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    email: str | None = None,
    role: str = "user",
):
    """创建用户。"""
    user = models.User(
        username=username,
        password_hash=password_hash,
        email=email,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def count_users(db: Session) -> int:
    """统计用户数量。"""
    return db.query(models.User).count()
