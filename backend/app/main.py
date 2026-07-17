import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import crud
from .database import SessionLocal
from .mcp import mcp_registry
from .routers import ai, auth, documents, mcp as mcp_router, settings, tasks
from .services.auth import get_password_hash
from .services.config import migrate_legacy_ai_settings
from .services.dependencies import require_auth
from .services.task_executor import (
    cleanup_stale_ai_task_jobs,
    reset_stuck_ai_tasks,
    run_task_scheduler,
)


__all__ = ["app", "require_auth"]

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        migrated_ai_settings = migrate_legacy_ai_settings(db)
        interrupted_count = crud.fail_interrupted_uploaded_documents(db)
    for legacy_key, current_key in migrated_ai_settings:
        logger.info("[config] Migrated setting key %s -> %s", legacy_key, current_key)
    if interrupted_count:
        logger.warning(
            "[upload] Recovered interrupted tasks count=%s action=marked_failed",
            interrupted_count,
        )

    # 首次启动初始化默认管理员
    with SessionLocal() as db:
        user_count = crud.count_users(db)
        if user_count == 0:
            default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
            default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
            default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@agentchat.local")

            crud.create_user(
                db,
                username=default_username,
                password_hash=get_password_hash(default_password),
                email=default_email,
                role="admin",
            )

            logger.warning("[auth] ============================================")
            logger.warning("[auth] Default admin created:")
            logger.warning("[auth]   Username: %s", default_username)
            logger.warning("[auth]   Password: %s", default_password)
            logger.warning("[auth] Please login and change the password!")
            logger.warning("[auth] ============================================")

    _app.state.mcp_registry = mcp_registry
    await mcp_registry.refresh()
    try:
        recovered_tasks = reset_stuck_ai_tasks()
        if recovered_tasks:
            logger.warning(
                "[task_executor] Recovered stuck AI tasks on startup count=%s",
                recovered_tasks,
            )
    except Exception:
        logger.exception("[task_executor] Failed to recover stuck AI tasks on startup")
    try:
        await cleanup_stale_ai_task_jobs()
    except Exception:
        logger.exception("[task_executor] Failed to clean stale AI task jobs on startup")

    task_scheduler_stop = asyncio.Event()
    task_scheduler_task = asyncio.create_task(
        run_task_scheduler(stop_event=task_scheduler_stop)
    )
    mcp_sync_stop = asyncio.Event()
    mcp_sync_task = asyncio.create_task(
        mcp_registry.watch_config_changes(stop_event=mcp_sync_stop)
    )
    try:
        yield
    finally:
        mcp_sync_stop.set()
        mcp_sync_task.cancel()
        try:
            await mcp_sync_task
        except asyncio.CancelledError:
            pass
        task_scheduler_stop.set()
        task_scheduler_task.cancel()
        try:
            await task_scheduler_task
        except asyncio.CancelledError:
            pass
        await mcp_registry.close()


app = FastAPI(lifespan=lifespan)

# 允许本地前端开发服务器访问 API。
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://frp-six.com:46189",
    "https://frp-six.com:46189",
    "https://noproblem.icu:46189",
    "https://www.r853982.nyat.app:46189",
]

# 添加跨域中间件，使前端能携带凭据调用后端接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# 将各业务路由注册到主应用。
app.include_router(ai.router)
app.include_router(tasks.router)
app.include_router(settings.router)
app.include_router(auth.router)
app.include_router(mcp_router.router)
app.include_router(documents.router)


@app.get("/")
def read_root():
    """提供最小的服务存活检查接口。"""

    return {"Hello": "World"}
