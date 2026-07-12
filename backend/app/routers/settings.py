"""系统配置路由，提供配置的增删改查接口。"""

import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..ai.models import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    LLM_API_KEY,
    LLM_BASE_URL,
)
from ..database import get_db
from ..services.encryption import decrypt_value, encrypt_value, mask_sensitive_value
from ..services.config import get_config_service
from ..services.dependencies import require_admin


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/settings", tags=["settings"])


def _value_for_storage(db: Session, setting_data: schemas.SystemSettingCreate) -> str:
    """Encrypt a new secret; never persist a display mask the client echoed back."""
    if not setting_data.is_encrypted or not setting_data.value:
        return setting_data.value

    # 客户端把脱敏掩码原样回传（未改动该字段）：保留已有密文，绝不把掩码加密成新密钥。
    # 这样即便前后端掩码格式不完全一致，也不会再把 "abc******xyz" 存成真实密钥。
    if _looks_like_masked_secret(setting_data.value):
        existing = crud.get_system_setting(db, setting_data.key)
        if existing is not None and existing.is_encrypted:
            return existing.value
        return ""

    return encrypt_value(setting_data.value)


def _looks_like_masked_secret(value: str | None) -> bool:
    """Return True when the settings UI sent a displayed mask instead of a real key."""
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or stripped == "******" or "***" in stripped


def _models_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("模型接口地址不能为空")
    if normalized.endswith("/models"):
        return normalized
    return f"{normalized}/models"


def _parse_model_options(payload: Any) -> list[schemas.ModelOption]:
    if not isinstance(payload, dict):
        raise ValueError("模型服务返回格式不是 JSON 对象")

    items = payload.get("data")
    if items is None:
        items = payload.get("models")
    if not isinstance(items, list):
        raise ValueError("模型服务返回中缺少模型列表")

    models: list[schemas.ModelOption] = []
    seen: set[str] = set()
    for item in items:
        model_id: str | None = None
        owned_by: str | None = None
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            raw_id = item.get("id") or item.get("name") or item.get("model")
            if raw_id is not None:
                model_id = str(raw_id)
            raw_owner = item.get("owned_by") or item.get("owner")
            if raw_owner is not None:
                owned_by = str(raw_owner)

        if model_id and model_id not in seen:
            seen.add(model_id)
            models.append(schemas.ModelOption(id=model_id, owned_by=owned_by))

    return models


def _fetch_model_options(base_url: str, api_key: str) -> list[schemas.ModelOption]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = httpx.get(_models_url(base_url), headers=headers, timeout=10)
    response.raise_for_status()
    return _parse_model_options(response.json())


def _resolve_model_options_config(
    db: Session,
    request: schemas.ModelOptionsRequest,
) -> tuple[str, str]:
    config_service = get_config_service(db)
    llm_base_url = config_service.get(
        "llm_base_url",
        config_service.get("ai_base_url", LLM_BASE_URL),
    )
    llm_api_key = config_service.get("llm_api_key", LLM_API_KEY)

    submitted_base_url = (request.base_url or "").strip()
    submitted_api_key = (request.api_key or "").strip()

    if request.kind == "llm":
        base_url = submitted_base_url or llm_base_url
        api_key = (
            submitted_api_key
            if not _looks_like_masked_secret(submitted_api_key)
            else llm_api_key
        )
        return base_url, api_key

    embedding_base_url = config_service.get("embedding_base_url", "") or llm_base_url or EMBEDDING_BASE_URL
    embedding_api_key = config_service.get("embedding_api_key", "") or llm_api_key or EMBEDDING_API_KEY
    base_url = submitted_base_url or embedding_base_url
    api_key = (
        submitted_api_key
        if not _looks_like_masked_secret(submitted_api_key)
        else embedding_api_key
    )
    return base_url, api_key


@router.get("", response_model=list[schemas.SystemSettingResponse])
def list_settings(
    category: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
    _user = Depends(require_admin),
):
    """查询系统配置列表，可按分类筛选。敏感配置会自动脱敏。需要管理员权限。"""
    settings = crud.list_system_settings(db, category=category)

    # 对敏感配置进行脱敏
    result = []
    for setting in settings:
        setting_dict = {
            "id": setting.id,
            "key": setting.key,
            "value": setting.value,
            "category": setting.category,
            "is_encrypted": setting.is_encrypted,
            "description": setting.description,
            "created_at": setting.created_at,
            "updated_at": setting.updated_at,
        }

        # 如果是加密配置，先解密再脱敏
        if setting.is_encrypted:
            try:
                decrypted = decrypt_value(setting.value)
                setting_dict["value"] = mask_sensitive_value(decrypted, show_first=3, show_last=3)
            except Exception as exc:
                logger.exception("[settings] Failed to decrypt setting key=%s error=%s", setting.key, exc)
                setting_dict["value"] = "******"

        result.append(schemas.SystemSettingResponse(**setting_dict))

    return result


@router.post("/model-options", response_model=schemas.ModelOptionsResponse)
def list_model_options(
    request: schemas.ModelOptionsRequest,
    db: Session = Depends(get_db),
    _user = Depends(require_admin),
):
    """Fetch available model IDs from the configured OpenAI-compatible provider."""
    base_url, api_key = _resolve_model_options_config(db, request)

    try:
        models = _fetch_model_options(base_url, api_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="获取模型列表超时，请检查模型服务地址",
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"模型服务返回错误：HTTP {status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="无法连接模型服务，请检查接口地址和网络",
        ) from exc

    return schemas.ModelOptionsResponse(models=models, count=len(models))


@router.get("/{key}", response_model=schemas.SystemSettingResponse)
def get_setting(key: str, db: Session = Depends(get_db), _user = Depends(require_admin)):
    """查询单个系统配置。敏感配置会自动脱敏。需要管理员权限。"""
    setting = crud.get_system_setting(db, key)

    if setting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    setting_dict = {
        "id": setting.id,
        "key": setting.key,
        "value": setting.value,
        "category": setting.category,
        "is_encrypted": setting.is_encrypted,
        "description": setting.description,
        "created_at": setting.created_at,
        "updated_at": setting.updated_at,
    }

    # 如果是加密配置，先解密再脱敏
    if setting.is_encrypted:
        try:
            decrypted = decrypt_value(setting.value)
            setting_dict["value"] = mask_sensitive_value(decrypted, show_first=3, show_last=3)
        except Exception as exc:
            logger.exception("[settings] Failed to decrypt setting key=%s error=%s", setting.key, exc)
            setting_dict["value"] = "******"

    return schemas.SystemSettingResponse(**setting_dict)


@router.put("/{key}", response_model=schemas.SystemSettingResponse)
def upsert_setting(
    key: str,
    setting_data: schemas.SystemSettingCreate,
    db: Session = Depends(get_db),
    _user = Depends(require_admin),
):
    """创建或更新系统配置。如果标记为加密，会自动加密存储。需要管理员权限。"""

    # 确保 key 一致
    if key != setting_data.key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL 中的 key 与请求体中的 key 不一致",
        )

    try:
        value_to_store = _value_for_storage(db, setting_data)
    except Exception as exc:
        logger.exception("[settings] Encryption failed key=%s error=%s", key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="配置加密失败",
        ) from exc

    setting = crud.upsert_system_setting(
        db,
        key=key,
        value=value_to_store,
        category=setting_data.category,
        is_encrypted=setting_data.is_encrypted,
        description=setting_data.description,
    )

    logger.info(
        "[settings] Setting upserted key=%s category=%s encrypted=%s",
        key,
        setting_data.category,
        setting_data.is_encrypted,
    )

    # 返回时脱敏
    setting_dict = {
        "id": setting.id,
        "key": setting.key,
        "value": setting.value,
        "category": setting.category,
        "is_encrypted": setting.is_encrypted,
        "description": setting.description,
        "created_at": setting.created_at,
        "updated_at": setting.updated_at,
    }

    if setting.is_encrypted:
        try:
            decrypted = decrypt_value(setting.value)
            setting_dict["value"] = mask_sensitive_value(decrypted, show_first=3, show_last=3)
        except Exception:
            setting_dict["value"] = "******"

    return schemas.SystemSettingResponse(**setting_dict)


@router.post("/batch", response_model=list[schemas.SystemSettingResponse])
def batch_upsert_settings(
    batch_data: schemas.SystemSettingBatchUpdate,
    db: Session = Depends(get_db),
    _user = Depends(require_admin),
):
    """批量创建或更新系统配置。需要管理员权限。"""
    result = []

    for setting_data in batch_data.settings:
        try:
            value_to_store = _value_for_storage(db, setting_data)
            setting = crud.upsert_system_setting(
                db,
                key=setting_data.key,
                value=value_to_store,
                category=setting_data.category,
                is_encrypted=setting_data.is_encrypted,
                description=setting_data.description,
            )

            # 返回时脱敏
            setting_dict = {
                "id": setting.id,
                "key": setting.key,
                "value": setting.value,
                "category": setting.category,
                "is_encrypted": setting.is_encrypted,
                "description": setting.description,
                "created_at": setting.created_at,
                "updated_at": setting.updated_at,
            }

            if setting.is_encrypted:
                try:
                    decrypted = decrypt_value(setting.value)
                    setting_dict["value"] = mask_sensitive_value(decrypted, show_first=3, show_last=3)
                except Exception:
                    setting_dict["value"] = "******"

            result.append(schemas.SystemSettingResponse(**setting_dict))

        except Exception as exc:
            logger.exception(
                "[settings] Batch upsert failed key=%s error=%s",
                setting_data.key,
                exc,
            )

    logger.info("[settings] Batch upsert completed count=%s", len(result))
    return result


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting(key: str, db: Session = Depends(get_db), _user = Depends(require_admin)):
    """删除系统配置。需要管理员权限。"""
    deleted = crud.delete_system_setting(db, key)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    logger.info("[settings] Setting deleted key=%s", key)
    return None
