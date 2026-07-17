"""Adapters from AgentChat transport config to langchain-mcp connections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MCPTransportAdapter(ABC):
    """Build one langchain-mcp connection from canonical AgentChat config."""

    transport: str

    @abstractmethod
    def build_connection(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Return the connection dictionary consumed by MultiServerMCPClient."""

    def _http_connection(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        connection: dict[str, Any] = {
            "transport": self.transport,
            "url": config["url"],
            "timeout": float(config["request_timeout_seconds"]),
        }
        if headers:
            connection["headers"] = headers
        return connection


class StreamableHTTPTransportAdapter(MCPTransportAdapter):
    transport = "streamable_http"

    def build_connection(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return self._http_connection(config, headers=headers)


class SSETransportAdapter(MCPTransportAdapter):
    transport = "sse"

    def build_connection(
        self,
        config: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        connection = self._http_connection(config, headers=headers)
        connection["sse_read_timeout"] = float(config["sse_read_timeout_seconds"])
        return connection


_TRANSPORT_ADAPTERS: dict[str, MCPTransportAdapter] = {
    adapter.transport: adapter
    for adapter in (StreamableHTTPTransportAdapter(), SSETransportAdapter())
}


def get_transport_adapter(transport: str) -> MCPTransportAdapter:
    """Return the registered adapter for a canonical transport name."""

    try:
        return _TRANSPORT_ADAPTERS[transport]
    except KeyError as exc:
        raise ValueError(f"暂不支持的 MCP transport：{transport}") from exc


def build_mcp_connection(
    config: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a MultiServerMCPClient connection using the selected adapter."""

    adapter = get_transport_adapter(str(config.get("transport", "")))
    return adapter.build_connection(config, headers=headers or {})
