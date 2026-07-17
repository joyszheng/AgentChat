"""Typed MCP connection configuration and compatibility helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any


_NAMESPACE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_MAX_NAMESPACE_LENGTH = 48
SUPPORTED_REMOTE_TRANSPORTS = frozenset({"streamable_http", "sse"})


def normalize_server_namespace(name: str) -> str:
    """Return a provider-safe, stable namespace derived from a display name."""

    normalized = _NAMESPACE_PATTERN.sub("_", name).strip("_").lower() or "mcp"
    if len(normalized) <= _MAX_NAMESPACE_LENGTH:
        return normalized
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    prefix_length = _MAX_NAMESPACE_LENGTH - len(suffix) - 1
    return f"{normalized[:prefix_length]}_{suffix}"


def build_streamable_http_config(
    *,
    url: str,
    request_timeout_seconds: int,
    connect_timeout_seconds: int = 10,
    tls_verify: bool = True,
    network_policy: str = "private_allowlist",
) -> dict[str, Any]:
    """Build the canonical non-secret configuration for an HTTP MCP server."""

    return build_transport_config(
        transport="streamable_http",
        url=url,
        request_timeout_seconds=request_timeout_seconds,
        connect_timeout_seconds=connect_timeout_seconds,
        tls_verify=tls_verify,
        network_policy=network_policy,
    )


def build_sse_config(
    *,
    url: str,
    request_timeout_seconds: int,
    connect_timeout_seconds: int = 10,
    sse_read_timeout_seconds: int = 300,
    tls_verify: bool = True,
    network_policy: str = "private_allowlist",
) -> dict[str, Any]:
    """Build the canonical non-secret configuration for an SSE MCP server."""

    return build_transport_config(
        transport="sse",
        url=url,
        request_timeout_seconds=request_timeout_seconds,
        connect_timeout_seconds=connect_timeout_seconds,
        sse_read_timeout_seconds=sse_read_timeout_seconds,
        tls_verify=tls_verify,
        network_policy=network_policy,
    )


def build_transport_config(
    *,
    transport: str,
    url: str,
    request_timeout_seconds: int,
    connect_timeout_seconds: int = 10,
    sse_read_timeout_seconds: int = 300,
    tls_verify: bool = True,
    network_policy: str = "private_allowlist",
) -> dict[str, Any]:
    """Build canonical non-secret configuration for a supported remote transport."""

    if transport not in SUPPORTED_REMOTE_TRANSPORTS:
        raise ValueError(f"暂不支持的 MCP transport：{transport}")
    config: dict[str, Any] = {
        "transport": transport,
        "url": url,
        "connect_timeout_seconds": connect_timeout_seconds,
        "request_timeout_seconds": request_timeout_seconds,
        "tls_verify": tls_verify,
        "network_policy": network_policy,
    }
    if transport == "sse":
        config["sse_read_timeout_seconds"] = sse_read_timeout_seconds
    return config


def resolve_transport_config(
    *,
    transport_config: dict[str, Any] | None,
    legacy_transport: str,
    legacy_url: str,
    legacy_timeout_seconds: int,
) -> dict[str, Any]:
    """Resolve canonical config for any supported remote MCP transport."""

    config = dict(transport_config or {})
    transport = config.get("transport") or legacy_transport
    if transport not in SUPPORTED_REMOTE_TRANSPORTS:
        raise ValueError(f"暂不支持的 MCP transport：{transport}")
    url = config.get("url") or legacy_url
    if not isinstance(url, str) or not url:
        raise ValueError(f"{transport} MCP 配置缺少 URL")
    config["transport"] = transport
    config["url"] = url
    config.setdefault("connect_timeout_seconds", 10)
    config.setdefault("request_timeout_seconds", legacy_timeout_seconds)
    config.setdefault("tls_verify", True)
    config.setdefault("network_policy", "private_allowlist")
    if transport == "sse":
        config.setdefault("sse_read_timeout_seconds", 300)
    else:
        config.pop("sse_read_timeout_seconds", None)
    return config


def resolve_streamable_http_config(
    *,
    transport_config: dict[str, Any] | None,
    legacy_transport: str,
    legacy_url: str,
    legacy_timeout_seconds: int,
) -> dict[str, Any]:
    """Compatibility wrapper for callers that require Streamable HTTP."""

    config = resolve_transport_config(
        transport_config=transport_config,
        legacy_transport=legacy_transport,
        legacy_url=legacy_url,
        legacy_timeout_seconds=legacy_timeout_seconds,
    )
    if config["transport"] != "streamable_http":
        raise ValueError(f"暂不支持的 MCP transport：{config['transport']}")
    return config
