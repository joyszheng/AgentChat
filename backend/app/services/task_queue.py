"""Redis queue helpers for AI task execution."""

import inspect
import os
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from dotenv import load_dotenv


load_dotenv()

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
TASK_QUEUE_JOB_NAME = "execute_ai_task_job"


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def get_redis_settings(redis_url: str | None = None) -> RedisSettings:
    parsed = urlparse(redis_url or get_redis_url())
    scheme = parsed.scheme or "redis"
    if scheme not in {"redis", "rediss"}:
        raise ValueError(f"Unsupported Redis URL scheme: {scheme}")

    database = int(parsed.path.lstrip("/") or "0")
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=database,
        password=parsed.password,
        ssl=scheme == "rediss",
    )


async def create_task_queue_pool() -> ArqRedis:
    return await create_pool(get_redis_settings())


async def close_task_queue_pool(redis: ArqRedis | None) -> None:
    if redis is None:
        return

    close = getattr(redis, "aclose", None) or getattr(redis, "close", None)
    if close is None:
        return

    result = close()
    if inspect.isawaitable(result):
        await result
