from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# 开发环境使用项目目录下的 SQLite 文件；生产环境应改为独立配置。
DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    DATABASE_URL,
    # SQLite 默认不允许跨线程访问连接，FastAPI 开发服务器需要显式放开。
    connect_args={"check_same_thread": False}
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
