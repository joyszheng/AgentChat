"""系统配置路由，提供配置的增删改查接口。"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..services.encryption import decrypt_value, encrypt_value, mask_sensitive_value
from ..services.dependencies import require_admin


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/settings", tags=["settings"])


def _value_for_storage(db: Session, setting_data: schemas.SystemSettingCreate) -> str:
    """Encrypt a new secret, or keep the ciphertext when the client sends its mask."""
    if not setting_data.is_encrypted or not setting_data.value:
        return setting_data.value

    existing = crud.get_system_setting(db, setting_data.key)
    if existing is not None and existing.is_encrypted:
        if setting_data.value == "******":
            return existing.value

        try:
            current_value = decrypt_value(existing.value)
            current_mask = mask_sensitive_value(
                current_value,
                show_first=3,
                show_last=3,
            )
            if setting_data.value == current_mask:
                return existing.value
        except Exception:
            logger.exception(
                "[settings] Failed to compare masked setting key=%s",
                setting_data.key,
            )

    return encrypt_value(setting_data.value)


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
