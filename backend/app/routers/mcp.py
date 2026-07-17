"""Administrative API for registering and operating remote MCP servers."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..mcp import mcp_registry
from ..mcp.config import build_transport_config, normalize_server_namespace
from ..services.dependencies import require_admin
from ..services.encryption import decrypt_value, encrypt_value


logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/mcp", tags=["mcp"])


def _encrypted_headers(headers: dict[str, str]) -> str | None:
    if not headers:
        return None
    return encrypt_value(json.dumps(headers, ensure_ascii=False, sort_keys=True))


def _header_names(server: models.MCPServer) -> list[str]:
    if not server.headers_encrypted:
        return []
    try:
        value = json.loads(decrypt_value(server.headers_encrypted))
        if isinstance(value, dict):
            return sorted(str(key) for key in value)
    except Exception:
        logger.exception("[mcp] Failed to read encrypted header names server=%s", server.name)
    return []


def _next_config_revision(db: Session) -> int:
    state = db.get(models.MCPConfigState, 1)
    if state is None:
        state = models.MCPConfigState(id=1, revision=1)
        db.add(state)
        return 1
    state.revision += 1
    db.add(state)
    return state.revision


def _transport_config(server: models.MCPServer) -> dict:
    if server.transport_config:
        return dict(server.transport_config)
    return build_transport_config(
        transport=server.transport,
        url=server.url,
        request_timeout_seconds=server.call_timeout_seconds,
    )


def _server_response(server: models.MCPServer) -> schemas.MCPServerResponse:
    return schemas.MCPServerResponse(
        id=server.id,
        name=server.name,
        namespace=server.namespace or normalize_server_namespace(server.name),
        description=server.description,
        transport=server.transport,
        url=server.url,
        transport_config=_transport_config(server),
        auth_profile_id=server.auth_profile_id,
        config_revision=server.config_revision,
        active_revision=server.active_revision,
        enabled=server.enabled,
        require_admin=server.require_admin,
        allowed_tools=list(server.allowed_tools or []),
        discovered_tools=list(server.discovered_tools or []),
        header_names=_header_names(server),
        call_timeout_seconds=server.call_timeout_seconds,
        max_result_chars=server.max_result_chars,
        last_health_status=server.last_health_status,
        last_error=server.last_error,
        last_checked_at=server.last_checked_at,
        protocol_version=server.protocol_version,
        server_info=dict(server.server_info or {}),
        capabilities=dict(server.capabilities or {}),
        catalog_status=server.catalog_status,
        catalog_updated_at=server.catalog_updated_at,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.get("/servers", response_model=list[schemas.MCPServerResponse])
def list_mcp_servers(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    servers = db.query(models.MCPServer).order_by(models.MCPServer.name).all()
    return [_server_response(server) for server in servers]


@router.post(
    "/servers",
    response_model=schemas.MCPServerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_server(
    request: schemas.MCPServerCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    assert request.url is not None
    transport_config = (
        request.transport_config.model_dump(mode="json")
        if request.transport_config is not None
        else build_transport_config(
            transport=request.transport,
            url=str(request.url),
            request_timeout_seconds=request.call_timeout_seconds,
        )
    )
    revision = _next_config_revision(db)
    server = models.MCPServer(
        name=request.name,
        namespace=normalize_server_namespace(request.name),
        description=request.description,
        transport=request.transport,
        url=str(request.url),
        transport_config=transport_config,
        config_revision=revision,
        headers_encrypted=_encrypted_headers(request.headers),
        enabled=request.enabled,
        require_admin=request.require_admin,
        allowed_tools=request.allowed_tools,
        call_timeout_seconds=request.call_timeout_seconds,
        max_result_chars=request.max_result_chars,
    )
    db.add(server)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MCP Server 名称或 namespace 已存在",
        ) from exc
    db.refresh(server)
    await mcp_registry.reload_server(server.id)
    db.refresh(server)
    return _server_response(server)


@router.get("/servers/{server_id}", response_model=schemas.MCPServerResponse)
def get_mcp_server(
    server_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    server = db.get(models.MCPServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    return _server_response(server)


@router.put("/servers/{server_id}", response_model=schemas.MCPServerResponse)
async def update_mcp_server(
    server_id: int,
    request: schemas.MCPServerUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    server = db.get(models.MCPServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    changes = request.model_dump(exclude_unset=True)
    requested_transport_config = changes.pop("transport_config", None)
    if requested_transport_config is not None:
        assert request.transport_config is not None
        server.transport_config = request.transport_config.model_dump(mode="json")
        server.transport = request.transport_config.transport
        server.url = str(request.transport_config.url)
        changes.pop("url", None)
        changes.pop("transport", None)
    else:
        requested_transport = changes.pop("transport", None)
        requested_url = changes.pop("url", None)
        requested_timeout = changes.get("call_timeout_seconds")
        if requested_transport is not None and requested_transport != server.transport:
            server.transport = requested_transport
            server.url = str(requested_url or server.url)
            server.transport_config = build_transport_config(
                transport=server.transport,
                url=server.url,
                request_timeout_seconds=requested_timeout or server.call_timeout_seconds,
            )
        elif requested_url is not None or requested_timeout is not None:
            config = _transport_config(server)
            if requested_url is not None:
                server.url = str(requested_url)
                config["url"] = server.url
            if requested_timeout is not None:
                config["request_timeout_seconds"] = requested_timeout
            server.transport_config = config
    if "headers" in changes:
        server.headers_encrypted = _encrypted_headers(changes.pop("headers"))
    for key, value in changes.items():
        setattr(server, key, value)
    server.config_revision = _next_config_revision(db)
    db.add(server)
    db.commit()
    await mcp_registry.reload_server(server.id)
    db.refresh(server)
    return _server_response(server)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    server = db.get(models.MCPServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    _next_config_revision(db)
    db.delete(server)
    db.commit()
    await mcp_registry.remove_server(server_id)
    return None


@router.post("/servers/{server_id}/test", response_model=list[schemas.MCPToolInfo])
async def test_mcp_server(
    server_id: int,
    _user=Depends(require_admin),
):
    try:
        return await mcp_registry.test_server(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="MCP Server 不存在") from exc
    except Exception as exc:
        logger.exception("[mcp] Server test failed id=%s error=%s", server_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP Server 连接失败：{exc}",
        ) from exc


@router.post("/reload", response_model=list[schemas.MCPToolInfo])
async def reload_mcp_registry(_user=Depends(require_admin)):
    await mcp_registry.refresh()
    return mcp_registry.list_tools(is_admin=True, include_disabled=True)


@router.get("/tools", response_model=list[schemas.MCPToolInfo])
def list_mcp_tools(
    include_disabled: bool = Query(default=True),
    _user=Depends(require_admin),
):
    return mcp_registry.list_tools(
        is_admin=True,
        include_disabled=include_disabled,
    )


@router.post(
    "/tools/{qualified_name}/invoke",
    response_model=schemas.MCPToolInvokeResponse,
)
async def invoke_mcp_tool(
    qualified_name: str,
    request: schemas.MCPToolInvokeRequest,
    user=Depends(require_admin),
):
    try:
        result, duration_ms = await mcp_registry.invoke(
            qualified_name,
            request.arguments,
            is_admin=user.role == "admin",
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="MCP 工具不存在、未启用或当前用户无权限",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="MCP 工具调用超时") from exc
    except Exception as exc:
        logger.exception("[mcp] Tool call failed tool=%s error=%s", qualified_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP 工具调用失败：{exc}",
        ) from exc

    return schemas.MCPToolInvokeResponse(
        qualified_name=qualified_name,
        result=jsonable_encoder(result),
        duration_ms=duration_ms,
    )
