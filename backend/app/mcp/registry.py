"""Runtime registry for remote MCP servers and their exposed tools."""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal
from ..services.encryption import decrypt_value


logger = logging.getLogger("uvicorn.error")
_TOOL_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_MAX_TOOL_NAME_LENGTH = 64
_TRUNCATED_RESULT_MARKER = "\n[结果过长，已截断]"


@dataclass(frozen=True)
class RegisteredMCPTool:
    """A discovered MCP tool plus AgentChat's local policy metadata."""

    server_id: int
    server_name: str
    source_name: str
    qualified_name: str
    description: str
    enabled: bool
    require_admin: bool
    tool: BaseTool

    def to_info(self) -> schemas.MCPToolInfo:
        return schemas.MCPToolInfo(
            server_id=self.server_id,
            server_name=self.server_name,
            name=self.source_name,
            qualified_name=self.qualified_name,
            description=self.description,
            enabled=self.enabled,
            require_admin=self.require_admin,
        )


class MCPRegistry:
    """Load remote MCP tools once and provide role-filtered views per request."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tools: dict[str, RegisteredMCPTool] = {}
        self._clients: dict[int, MultiServerMCPClient] = {}

    async def refresh(self) -> None:
        """Reload every enabled server without making MCP availability block startup."""

        async with self._lock:
            with SessionLocal() as db:
                server_ids = [
                    server.id
                    for server in db.query(models.MCPServer).order_by(models.MCPServer.id).all()
                ]

            new_tools: dict[str, RegisteredMCPTool] = {}
            new_clients: dict[int, MultiServerMCPClient] = {}

            for server_id in server_ids:
                server_name = str(server_id)
                try:
                    with SessionLocal() as db:
                        server = db.get(models.MCPServer, server_id)
                        if server is None:
                            continue
                        server_name = server.name
                        if not server.enabled:
                            self._set_status(
                                db,
                                server,
                                status="disabled",
                                error=None,
                            )
                            continue

                        config = self._server_config(server)
                        policy = self._server_policy(server)

                    client, source_tools = await self._load_source_tools(config)
                    registered = self._register_tools(policy, source_tools)
                    new_clients[server_id] = client
                    for item in registered:
                        if item.qualified_name in new_tools:
                            raise RuntimeError(
                                f"MCP 工具名称冲突：{item.qualified_name}"
                            )
                        new_tools[item.qualified_name] = item

                    with SessionLocal() as db:
                        current = db.get(models.MCPServer, server_id)
                        if current is not None:
                            current.discovered_tools = sorted(
                                {item.source_name for item in registered}
                            )
                            self._set_status(db, current, status="healthy", error=None)
                    logger.info(
                        "[mcp] Server loaded name=%s tools=%s exposed=%s",
                        policy["name"],
                        len(registered),
                        sum(item.enabled for item in registered),
                    )
                except Exception as exc:
                    logger.exception(
                        "[mcp] Server load failed id=%s name=%s error=%s",
                        server_id,
                        server_name,
                        exc,
                    )
                    with SessionLocal() as db:
                        current = db.get(models.MCPServer, server_id)
                        if current is not None:
                            self._set_status(
                                db,
                                current,
                                status="unhealthy",
                                error=str(exc),
                            )

            self._tools = new_tools
            self._clients = new_clients

    async def test_server(self, server_id: int) -> list[schemas.MCPToolInfo]:
        """Connect to one server and discover tools without exposing them globally."""

        with SessionLocal() as db:
            server = db.get(models.MCPServer, server_id)
            if server is None:
                raise KeyError(server_id)
            config = self._server_config(server)
            policy = self._server_policy(server)

        try:
            _client, source_tools = await self._load_source_tools(config)
            registered = self._register_tools(policy, source_tools)
        except Exception as exc:
            with SessionLocal() as db:
                current = db.get(models.MCPServer, server_id)
                if current is not None:
                    self._set_status(
                        db,
                        current,
                        status="unhealthy",
                        error=str(exc),
                    )
            raise

        with SessionLocal() as db:
            current = db.get(models.MCPServer, server_id)
            if current is not None:
                current.discovered_tools = sorted({item.source_name for item in registered})
                self._set_status(db, current, status="healthy", error=None)

        return [item.to_info() for item in registered]

    def list_tools(
        self,
        *,
        is_admin: bool,
        include_disabled: bool = False,
    ) -> list[schemas.MCPToolInfo]:
        """List tools visible to a role, optionally including non-whitelisted tools."""

        result = []
        for item in self._tools.values():
            if item.require_admin and not is_admin:
                continue
            if not include_disabled and not item.enabled:
                continue
            result.append(item.to_info())
        return sorted(result, key=lambda item: item.qualified_name)

    def get_tools(self, *, is_admin: bool) -> list[BaseTool]:
        """Return enabled LangChain tools that may be exposed to the current model."""

        return [
            item.tool
            for item in self._tools.values()
            if item.enabled and (is_admin or not item.require_admin)
        ]

    def get_tool(self, qualified_name: str, *, is_admin: bool) -> BaseTool | None:
        item = self._tools.get(qualified_name)
        if item is None or not item.enabled:
            return None
        if item.require_admin and not is_admin:
            return None
        return item.tool

    async def invoke(
        self,
        qualified_name: str,
        arguments: dict[str, Any],
        *,
        is_admin: bool,
    ) -> tuple[Any, int]:
        """Invoke one enabled tool and return its result plus elapsed milliseconds."""

        tool = self.get_tool(qualified_name, is_admin=is_admin)
        if tool is None:
            raise KeyError(qualified_name)
        started_at = time.perf_counter()
        result = await tool.ainvoke(arguments)
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        return result, duration_ms

    async def close(self) -> None:
        """Drop runtime references; adapter clients use short-lived sessions by default."""

        async with self._lock:
            self._tools = {}
            self._clients = {}

    async def _load_source_tools(
        self,
        config: dict[str, Any],
    ) -> tuple[MultiServerMCPClient, list[BaseTool]]:
        client = MultiServerMCPClient({config["name"]: config["connection"]})
        tools = await client.get_tools()
        return client, tools

    def _register_tools(
        self,
        policy: dict[str, Any],
        source_tools: list[BaseTool],
    ) -> list[RegisteredMCPTool]:
        allowed_tools = set(policy["allowed_tools"])
        allow_all = "*" in allowed_tools
        registered: list[RegisteredMCPTool] = []

        for source_tool in source_tools:
            qualified_name = _qualified_tool_name(policy["name"], source_tool.name)
            enabled = allow_all or source_tool.name in allowed_tools
            wrapped = _wrap_tool(
                source_tool,
                qualified_name=qualified_name,
                server_name=policy["name"],
                timeout_seconds=policy["call_timeout_seconds"],
                max_result_chars=policy["max_result_chars"],
            )
            registered.append(
                RegisteredMCPTool(
                    server_id=policy["id"],
                    server_name=policy["name"],
                    source_name=source_tool.name,
                    qualified_name=qualified_name,
                    description=source_tool.description or "",
                    enabled=enabled,
                    require_admin=policy["require_admin"],
                    tool=wrapped,
                )
            )
        return registered

    @staticmethod
    def _server_config(server: models.MCPServer) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if server.headers_encrypted:
            decrypted = decrypt_value(server.headers_encrypted)
            loaded = json.loads(decrypted)
            if not isinstance(loaded, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in loaded.items()
            ):
                raise ValueError("MCP 认证 Headers 格式无效")
            headers = loaded

        connection: dict[str, Any] = {
            "transport": "streamable_http",
            "url": server.url,
            "timeout": float(server.call_timeout_seconds),
        }
        if headers:
            connection["headers"] = headers
        return {"name": server.name, "connection": connection}

    @staticmethod
    def _server_policy(server: models.MCPServer) -> dict[str, Any]:
        return {
            "id": server.id,
            "name": server.name,
            "require_admin": server.require_admin,
            "allowed_tools": list(server.allowed_tools or []),
            "call_timeout_seconds": server.call_timeout_seconds,
            "max_result_chars": server.max_result_chars,
        }

    @staticmethod
    def _set_status(
        db: Session,
        server: models.MCPServer,
        *,
        status: str,
        error: str | None,
    ) -> None:
        from sqlalchemy import func

        server.last_health_status = status
        server.last_error = error[:4000] if error else None
        server.last_checked_at = func.now()
        db.add(server)
        db.commit()


def _qualified_tool_name(server_name: str, source_name: str) -> str:
    raw_name = f"{server_name}__{source_name}"
    normalized = _TOOL_NAME_PATTERN.sub("_", raw_name).strip("_") or "mcp_tool"
    if len(normalized) <= _MAX_TOOL_NAME_LENGTH:
        return normalized
    suffix = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:8]
    prefix_length = _MAX_TOOL_NAME_LENGTH - len(suffix) - 1
    return f"{normalized[:prefix_length]}_{suffix}"


def _wrap_tool(
    source_tool: BaseTool,
    *,
    qualified_name: str,
    server_name: str,
    timeout_seconds: int,
    max_result_chars: int,
) -> BaseTool:
    async def call_mcp_tool(**kwargs):
        result = await asyncio.wait_for(
            source_tool.ainvoke(kwargs),
            timeout=timeout_seconds,
        )
        return _limit_tool_result(result, max_result_chars)

    return StructuredTool(
        name=qualified_name,
        description=(
            f"MCP server '{server_name}' tool '{source_tool.name}'. "
            f"{source_tool.description or ''}"
        ).strip(),
        args_schema=source_tool.args_schema,
        coroutine=call_mcp_tool,
        metadata={
            "mcp_server": server_name,
            "mcp_source_tool": source_tool.name,
        },
    )


def _limit_tool_result(result: Any, max_result_chars: int) -> Any:
    """Limit textual MCP results while preserving common content-block structures."""

    remaining = max_result_chars

    def limit(value: Any) -> Any:
        nonlocal remaining

        if isinstance(value, str):
            if remaining <= 0:
                return _TRUNCATED_RESULT_MARKER
            if len(value) <= remaining:
                remaining -= len(value)
                return value

            truncated = value[:remaining] + _TRUNCATED_RESULT_MARKER
            remaining = 0
            return truncated

        if isinstance(value, list):
            limited_items: list[Any] = []
            for item in value:
                if remaining <= 0:
                    limited_items.append(
                        {
                            "type": "text",
                            "text": _TRUNCATED_RESULT_MARKER.strip(),
                        }
                    )
                    break
                limited_items.append(limit(item))
            return limited_items

        if isinstance(value, dict) and isinstance(value.get("text"), str):
            return {
                key: limit(item) if key == "text" else item
                for key, item in value.items()
            }

        if isinstance(value, dict):
            return {key: limit(item) for key, item in value.items()}

        return value

    return limit(result)


mcp_registry = MCPRegistry()
