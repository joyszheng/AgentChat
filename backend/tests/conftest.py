import os
from pathlib import Path


# RAG 的 Embedding 模型已下载到本地缓存。测试时禁止 Hugging Face
# 再次检查远程元数据，避免网络波动导致 pytest 在收集阶段失败。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Set this before test modules import app.database. Tests must never use the
# DATABASE_URL from backend/.env, otherwise chat integration tests pollute the
# application's real conversation history.
_TEST_DATABASE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".pytest-agentchat.db"
)
for suffix in ("", "-shm", "-wal"):
    Path(f"{_TEST_DATABASE_PATH}{suffix}").unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE_PATH.as_posix()}"

# Production builds its schema with Alembic migrations (`alembic upgrade head`).
# Tests use a throwaway SQLite file, so create the tables straight from the ORM
# models here — this replaces the import-time create_all that used to live in
# app.main. Must run after DATABASE_URL is set above.
from app.database import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401

Base.metadata.create_all(bind=engine)
