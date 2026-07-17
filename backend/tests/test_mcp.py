import asyncio
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app import models
from app.database import SessionLocal
from app.main import app
from app import schemas
from app.mcp import registry as registry_module
from app.mcp.config import (
    build_sse_config,
    build_streamable_http_config,
    normalize_server_namespace,
    resolve_transport_config,
    resolve_streamable_http_config,
)
from app.mcp.registry import MCPRegistry, RegisteredMCPTool, _qualified_tool_name, _wrap_tool
from app.mcp.transports import build_mcp_connection
from app.routers import ai as ai_router
from app.routers import mcp as mcp_router
from app.services.encryption import decrypt_value


async def _echo(value: str) -> str:
    return f"echo:{value}"


def _source_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_echo,
        name="echo",
        description="Echo a value",
    )


def _create_enabled_mcp_server(name: str) -> int:
    with SessionLocal() as db:
        existing = db.query(models.MCPServer).filter_by(name=name).one_or_none()
        if existing is not None:
            db.delete(existing)
            db.commit()
        server = models.MCPServer(
            name=name,
            namespace=normalize_server_namespace(name),
            transport="streamable_http",
            url="http://127.0.0.1:9999/mcp",
            transport_config=build_streamable_http_config(
                url="http://127.0.0.1:9999/mcp",
                request_timeout_seconds=2,
            ),
            enabled=True,
            allowed_tools=["*"],
            call_timeout_seconds=2,
        )
        db.add(server)
        db.commit()
        return server.id


def _delete_mcp_server(server_id: int) -> None:
    with SessionLocal() as db:
        server = db.get(models.MCPServer, server_id)
        if server is not None:
            db.delete(server)
            db.commit()


def _login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_qualified_tool_name_is_provider_safe_and_stable():
    assert _qualified_tool_name("demo", "echo") == "demo__echo"
    long_name = _qualified_tool_name("server", "工具" * 100)
    assert len(long_name) <= 64
    assert long_name == _qualified_tool_name("server", "工具" * 100)


def test_server_namespace_and_transport_config_are_stable_and_compatible():
    assert normalize_server_namespace("Demo_Server") == "demo_server"
    assert normalize_server_namespace("工具" * 100) == normalize_server_namespace("工具" * 100)

    config = resolve_streamable_http_config(
        transport_config={
            "transport": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "request_timeout_seconds": 45,
        },
        legacy_transport="streamable_http",
        legacy_url="https://legacy.example.com/mcp",
        legacy_timeout_seconds=20,
    )
    assert config["url"] == "https://mcp.example.com/mcp"
    assert config["request_timeout_seconds"] == 45
    assert config["connect_timeout_seconds"] == 10


def test_mcp_create_schema_accepts_discriminated_transport_config_without_legacy_url():
    request = schemas.MCPServerCreate(
        name="typed-config",
        transport_config={
            "transport": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "request_timeout_seconds": 30,
        },
    )
    assert str(request.url) == "https://mcp.example.com/mcp"
    assert request.transport_config is not None
    assert request.transport_config.request_timeout_seconds == 30


def test_sse_config_schema_and_adapter_connection():
    request = schemas.MCPServerCreate(
        name="sse-config",
        transport_config={
            "transport": "sse",
            "url": "https://mcp.example.com/sse",
            "request_timeout_seconds": 15,
            "sse_read_timeout_seconds": 180,
        },
    )
    assert request.transport == "sse"
    assert request.transport_config is not None

    config = resolve_transport_config(
        transport_config=request.transport_config.model_dump(mode="json"),
        legacy_transport="streamable_http",
        legacy_url="https://legacy.example.com/mcp",
        legacy_timeout_seconds=20,
    )
    connection = build_mcp_connection(
        config,
        headers={"Authorization": "Bearer secret"},
    )

    assert config == build_sse_config(
        url="https://mcp.example.com/sse",
        request_timeout_seconds=15,
        sse_read_timeout_seconds=180,
    )
    assert connection == {
        "transport": "sse",
        "url": "https://mcp.example.com/sse",
        "timeout": 15.0,
        "sse_read_timeout": 180.0,
        "headers": {"Authorization": "Bearer secret"},
    }


def test_wrapped_tool_enforces_namespace_and_result_limit():
    source = StructuredTool.from_function(
        coroutine=_echo,
        name="echo",
        description="Echo a value",
    )
    wrapped = _wrap_tool(
        source,
        qualified_name="demo__echo",
        server_name="demo",
        timeout_seconds=2,
        max_result_chars=1000,
    )

    assert wrapped.name == "demo__echo"
    assert asyncio.run(wrapped.ainvoke({"value": "hello"})) == "echo:hello"


def test_wrapped_tool_limits_mcp_content_blocks():
    async def _long_content(value: str) -> list[dict[str, str]]:
        return [{"type": "text", "text": value}]

    source = StructuredTool.from_function(
        coroutine=_long_content,
        name="long_content",
        description="Return MCP-style content blocks",
    )
    wrapped = _wrap_tool(
        source,
        qualified_name="demo__long_content",
        server_name="demo",
        timeout_seconds=2,
        max_result_chars=5,
    )

    result = asyncio.run(wrapped.ainvoke({"value": "0123456789"}))

    assert result == [{"type": "text", "text": "01234\n[结果过长，已截断]"}]


def test_registry_filters_tools_by_allowlist_and_role():
    registry = MCPRegistry()
    registered = registry._register_tools(
        {
            "id": 7,
            "name": "demo",
            "require_admin": True,
            "allowed_tools": ["echo"],
            "call_timeout_seconds": 2,
            "max_result_chars": 1000,
        },
        [_source_tool()],
    )
    registry._tools = {item.qualified_name: item for item in registered}

    assert [tool.name for tool in registry.get_tools(is_admin=True)] == ["demo__echo"]
    assert registry.get_tools(is_admin=False) == []


def test_registry_builds_streamable_http_client(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, connections):
            captured.update(connections)

        async def get_tools(self):
            return [_source_tool()]

    monkeypatch.setattr(registry_module, "MultiServerMCPClient", FakeClient)
    registry = MCPRegistry()
    client, tools = asyncio.run(
        registry._load_source_tools(
            {
                "name": "demo",
                "connection": {
                    "transport": "streamable_http",
                    "url": "http://127.0.0.1:9999/mcp",
                    "headers": {"Authorization": "Bearer secret"},
                },
            }
        )
    )

    assert isinstance(client, FakeClient)
    assert [tool.name for tool in tools] == ["echo"]
    assert captured["demo"]["transport"] == "streamable_http"


def test_registry_refresh_marks_bad_server_config_unhealthy(monkeypatch):
    server_name = "bad_config_mcp"
    with SessionLocal() as db:
        existing = db.query(models.MCPServer).filter_by(name=server_name).one_or_none()
        if existing is not None:
            db.delete(existing)
            db.commit()
        server = models.MCPServer(
            name=server_name,
            url="http://127.0.0.1:9999/mcp",
            enabled=True,
            allowed_tools=["*"],
        )
        db.add(server)
        db.commit()
        server_id = server.id

    registry = MCPRegistry()
    monkeypatch.setattr(
        registry,
        "_server_config",
        lambda _server: (_ for _ in ()).throw(ValueError("bad mcp config")),
    )

    try:
        asyncio.run(registry.refresh())

        with SessionLocal() as db:
            current = db.get(models.MCPServer, server_id)
            assert current is not None
            assert current.last_health_status == "unhealthy"
            assert current.last_error == "bad mcp config"
        assert registry.list_tools(is_admin=True, include_disabled=True) == []
    finally:
        with SessionLocal() as db:
            current = db.get(models.MCPServer, server_id)
            if current is not None:
                db.delete(current)
                db.commit()


def test_reload_server_keeps_last_known_good_snapshot_when_refresh_fails(monkeypatch):
    server_id = _create_enabled_mcp_server("last_known_good_mcp")
    registry = MCPRegistry()
    should_fail = False

    async def fake_load_source_tools(_config):
        if should_fail:
            raise RuntimeError("temporary outage")
        return SimpleNamespace(), [_source_tool()]

    monkeypatch.setattr(registry, "_load_source_tools", fake_load_source_tools)

    try:
        assert asyncio.run(registry.reload_server(server_id)) is True
        assert [tool.name for tool in registry.get_tools(is_admin=True)] == [
            "last_known_good_mcp__echo"
        ]

        with SessionLocal() as db:
            server = db.get(models.MCPServer, server_id)
            assert server is not None
            server.config_revision += 1
            db.add(server)
            db.commit()

        should_fail = True
        assert asyncio.run(registry.reload_server(server_id)) is False
        assert [tool.name for tool in registry.get_tools(is_admin=True)] == [
            "last_known_good_mcp__echo"
        ]
        with SessionLocal() as db:
            server = db.get(models.MCPServer, server_id)
            assert server is not None
            assert server.catalog_status == "stale"
            assert server.active_revision < server.config_revision

        registry._stale_ttl_seconds = 0
        asyncio.run(registry._expire_stale_snapshots())
        assert registry.get_tools(is_admin=True) == []
        with SessionLocal() as db:
            server = db.get(models.MCPServer, server_id)
            assert server is not None
            assert server.catalog_status == "unhealthy"
    finally:
        _delete_mcp_server(server_id)


def test_sync_if_changed_reloads_only_changed_server(monkeypatch):
    first_id = _create_enabled_mcp_server("revision_first_mcp")
    second_id = _create_enabled_mcp_server("revision_second_mcp")
    registry = MCPRegistry()
    loaded_ids: list[str] = []

    async def fake_load_source_tools(config):
        loaded_ids.append(config["name"])
        return SimpleNamespace(), [_source_tool()]

    monkeypatch.setattr(registry, "_load_source_tools", fake_load_source_tools)

    try:
        asyncio.run(registry.refresh())
        loaded_ids.clear()
        with SessionLocal() as db:
            first = db.get(models.MCPServer, first_id)
            assert first is not None
            first.config_revision += 1
            state = db.get(models.MCPConfigState, 1)
            if state is None:
                state = models.MCPConfigState(id=1, revision=1)
            else:
                state.revision += 1
            db.add_all([first, state])
            db.commit()

        assert asyncio.run(registry.sync_if_changed()) is True
        assert loaded_ids == ["revision_first_mcp"]
    finally:
        _delete_mcp_server(first_id)
        _delete_mcp_server(second_id)


def test_mcp_adapter_end_to_end_with_streamable_http_asgi():
    server = FastMCP(
        "AgentChat test MCP",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=["127.0.0.1"]),
    )

    @server.tool()
    async def add(a: int, b: int) -> int:
        """Add two integers."""

        return a + b

    asgi_app = server.streamable_http_app()

    def http_client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=asgi_app),
            base_url="http://127.0.0.1",
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    async def exercise_adapter():
        async with asgi_app.router.lifespan_context(asgi_app):
            client = MultiServerMCPClient(
                {
                    "local": {
                        "transport": "streamable_http",
                        "url": "http://127.0.0.1/mcp",
                        "httpx_client_factory": http_client_factory,
                    }
                }
            )
            tools = await client.get_tools()
            result = await tools[0].ainvoke({"a": 2, "b": 5})
            return tools, result

    tools, result = asyncio.run(exercise_adapter())
    assert [tool.name for tool in tools] == ["add"]
    assert result[0]["type"] == "text"
    assert result[0]["text"] == "7"


def test_mcp_server_crud_encrypts_headers_and_requires_admin():
    with TestClient(app) as client:
        unauthorized = client.get("/mcp/servers")
        assert unauthorized.status_code == 401

        auth_headers = _login_admin(client)
        response = client.post(
            "/mcp/servers",
            headers=auth_headers,
            json={
                "name": "test_mcp_server",
                "description": "test",
                "transport": "streamable_http",
                "url": "http://127.0.0.1:9999/mcp",
                "headers": {"Authorization": "Bearer top-secret"},
                "enabled": False,
                "allowed_tools": ["echo"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["namespace"] == "test_mcp_server"
        assert data["transport_config"]["transport"] == "streamable_http"
        assert data["transport_config"]["url"] == "http://127.0.0.1:9999/mcp"
        assert data["config_revision"] >= 1
        assert data["header_names"] == ["Authorization"]
        assert "top-secret" not in response.text

        update_response = client.put(
            f"/mcp/servers/{data['id']}",
            headers=auth_headers,
            json={
                "transport": "sse",
                "url": "http://127.0.0.1:9999/sse",
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["transport"] == "sse"
        assert updated["transport_config"]["transport"] == "sse"
        assert updated["transport_config"]["sse_read_timeout_seconds"] == 300

        with SessionLocal() as db:
            stored = db.get(models.MCPServer, data["id"])
            assert stored is not None
            assert stored.transport == "sse"
            assert "top-secret" not in stored.headers_encrypted
            assert json.loads(decrypt_value(stored.headers_encrypted)) == {
                "Authorization": "Bearer top-secret"
            }

        delete_response = client.delete(
            f"/mcp/servers/{data['id']}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204


def test_mcp_tool_invoke_endpoint_uses_registered_tool(monkeypatch):
    source = _source_tool()
    wrapped = _wrap_tool(
        source,
        qualified_name="demo__echo",
        server_name="demo",
        timeout_seconds=2,
        max_result_chars=1000,
    )
    item = RegisteredMCPTool(
        server_id=1,
        server_name="demo",
        source_name="echo",
        qualified_name="demo__echo",
        description="Echo a value",
        enabled=True,
        require_admin=True,
        tool=wrapped,
    )

    with TestClient(app) as client:
        auth_headers = _login_admin(client)
        monkeypatch.setattr(mcp_router.mcp_registry, "_tools", {item.qualified_name: item})
        response = client.post(
            "/mcp/tools/demo__echo/invoke",
            headers=auth_headers,
            json={"arguments": {"value": "hello"}},
        )

    assert response.status_code == 200
    assert response.json()["result"] == "echo:hello"


def test_mcp_assistant_uses_role_filtered_tools(monkeypatch):
    fake_agent = SimpleNamespace(
        ainvoke=lambda _input: None,
    )

    async def fake_ainvoke(_input):
        return {
            "messages": [
                SimpleNamespace(
                    type="ai",
                    content="我调用工具完成了查询",
                    tool_calls=[{"name": "demo__echo", "args": {}, "id": "call-1"}],
                )
            ]
        }

    fake_agent.ainvoke = fake_ainvoke
    fake_tool = _source_tool()
    monkeypatch.setattr(ai_router.mcp_registry, "get_tools", lambda **_kwargs: [fake_tool])
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "create_mcp_agent", lambda _llm, _tools: fake_agent)

    with TestClient(app) as client:
        auth_headers = _login_admin(client)
        response = client.post(
            "/ai/mcp-assistant",
            headers=auth_headers,
            json={"message": "使用工具查询"},
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "我调用工具完成了查询"
    assert response.json()["tools_used"] == ["demo__echo"]
