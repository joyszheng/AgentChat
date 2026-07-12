import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv()

# 优先使用 .env 中的 PostgreSQL 连接；未配置时回退到项目目录下的 SQLite 文件。
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite（默认回退 / 测试）：允许跨线程复用连接。
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL（生产）：pool_pre_ping 处理长驻 worker 的陈旧连接，
    # pool_recycle 主动回收，避免数据库/中间件断开后拿到坏连接。
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
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
