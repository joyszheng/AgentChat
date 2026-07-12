"""Helpers for classifying and logging upstream AI service failures."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import openai
from fastapi import HTTPException, status


@dataclass(frozen=True)
class AIErrorInfo:
    code: str
    status_code: int
    level: int
    include_traceback: bool = False


UNKNOWN_AI_ERROR = AIErrorInfo(
    code="ai_service_unavailable",
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    level=logging.ERROR,
    include_traceback=True,
)


# 判定为"瞬时"的错误码，值得退避后重试；鉴权/未知错误不重试。
RETRYABLE_AI_ERROR_CODES = frozenset(
    {
        "ai_timeout",
        "ai_connection_failed",
        "ai_rate_limited",
        "ai_upstream_error",
    }
)


def is_retryable_ai_exception(exc: BaseException) -> bool:
    """AI/任务执行失败是否值得退避重试。"""

    return classify_ai_exception(exc).code in RETRYABLE_AI_ERROR_CODES


def classify_ai_exception(exc: BaseException) -> AIErrorInfo:
    """Map common upstream AI failures to concise, operationally useful errors."""

    for item in _exception_chain(exc):
        if isinstance(item, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)):
            return AIErrorInfo(
                code="ai_timeout",
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                level=logging.WARNING,
            )

        if isinstance(item, (openai.APIConnectionError, httpx.NetworkError)):
            return AIErrorInfo(
                code="ai_connection_failed",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                level=logging.WARNING,
            )

        if isinstance(item, openai.RateLimitError):
            return AIErrorInfo(
                code="ai_rate_limited",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                level=logging.WARNING,
            )

        if isinstance(item, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return AIErrorInfo(
                code="ai_auth_failed",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                level=logging.ERROR,
            )

        if isinstance(item, openai.APIStatusError):
            return AIErrorInfo(
                code="ai_upstream_error",
                status_code=status.HTTP_502_BAD_GATEWAY,
                level=logging.WARNING,
            )

    return UNKNOWN_AI_ERROR


def raise_ai_http_exception(
    *,
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    detail: str,
) -> None:
    info = classify_ai_exception(exc)
    log_ai_exception(logger=logger, operation=operation, exc=exc, info=info)
    raise HTTPException(
        status_code=info.status_code,
        detail=detail,
        headers={"X-AgentChat-AI-Error": info.code},
    ) from exc


def ai_sse_error_payload(
    *,
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    default_code: str,
    message: str,
) -> dict[str, str]:
    info = classify_ai_exception(exc)
    log_ai_exception(logger=logger, operation=operation, exc=exc, info=info)
    return {
        "code": info.code if info is not UNKNOWN_AI_ERROR else default_code,
        "message": message,
    }


def log_ai_exception(
    *,
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    info: AIErrorInfo | None = None,
) -> None:
    resolved = info or classify_ai_exception(exc)
    logger.log(
        resolved.level,
        "[ai] %s failed code=%s error_type=%s error=%s",
        operation,
        resolved.code,
        exc.__class__.__name__,
        _exception_summary(exc),
        exc_info=resolved.include_traceback,
    )


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _exception_summary(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__
