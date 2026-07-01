import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv()

# 优先使用 .env 中的 PostgreSQL 连接；未配置时回退到项目目录下的 SQLite 文件。
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的基类。"""

    pass


def get_db():
    """为每个请求创建数据库会话，并在请求结束后确保关闭。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
