import logging

import httpx
import openai
from fastapi import HTTPException

from app.ai.errors import classify_ai_exception, log_ai_exception, raise_ai_http_exception


def test_classifies_openai_timeout_as_gateway_timeout():
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    exc = openai.APITimeoutError(request=request)

    info = classify_ai_exception(exc)

    assert info.code == "ai_timeout"
    assert info.status_code == 504
    assert info.include_traceback is False


def test_known_ai_error_logs_without_traceback(caplog):
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    exc = openai.APITimeoutError(request=request)
    logger = logging.getLogger("tests.ai.errors")

    with caplog.at_level(logging.WARNING, logger="tests.ai.errors"):
        log_ai_exception(logger=logger, operation="assistant", exc=exc)

    assert "code=ai_timeout" in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text


def test_http_exception_uses_classified_status_and_error_header():
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    exc = openai.APITimeoutError(request=request)
    logger = logging.getLogger("tests.ai.errors")

    try:
        raise_ai_http_exception(
            logger=logger,
            operation="assistant",
            exc=exc,
            detail="AI service unavailable",
        )
    except HTTPException as http_exc:
        assert http_exc.status_code == 504
        assert http_exc.detail == "AI service unavailable"
        assert http_exc.headers == {"X-AgentChat-AI-Error": "ai_timeout"}
    else:
        raise AssertionError("Expected HTTPException")
