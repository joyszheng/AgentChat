"""ARQ worker entrypoint for AI task jobs."""

import asyncio
import logging
import os

from ..mcp import mcp_registry
from .task_executor import execute_ai_task
from .task_queue import get_redis_settings


logger = logging.getLogger("arq.worker")


async def execute_ai_task_job(ctx, task_id: int) -> str:
    await execute_ai_task(task_id)
    return f"ai-task:{task_id}:finished"


async def startup(ctx) -> None:
    """Load MCP tools once so scheduled tasks can use them (e.g. Amap weather)."""

    try:
        await mcp_registry.refresh()
        stop_event = asyncio.Event()
        ctx["mcp_sync_stop"] = stop_event
        ctx["mcp_sync_task"] = asyncio.create_task(
            mcp_registry.watch_config_changes(stop_event=stop_event)
        )
        logger.info("[task_worker] MCP registry refreshed on startup")
    except Exception:
        logger.exception("[task_worker] Failed to refresh MCP registry on startup")


async def shutdown(ctx) -> None:
    stop_event = ctx.get("mcp_sync_stop")
    sync_task = ctx.get("mcp_sync_task")
    if stop_event is not None:
        stop_event.set()
    if sync_task is not None:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
    try:
        await mcp_registry.close()
    except Exception:
        logger.exception("[task_worker] Failed to close MCP registry on shutdown")


class WorkerSettings:
    functions = [execute_ai_task_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = int(os.getenv("TASK_WORKER_MAX_JOBS", "2"))
    job_timeout = int(os.getenv("TASK_WORKER_JOB_TIMEOUT_SECONDS", "600"))
    keep_result = int(os.getenv("TASK_WORKER_KEEP_RESULT_SECONDS", "3600"))
    health_check_interval = int(os.getenv("TASK_WORKER_HEALTH_CHECK_SECONDS", "30"))
