"""配置管理服务，支持从数据库或环境变量读取配置。"""

import logging
import os
from functools import lru_cache

from sqlalchemy.orm import Session

from .. import crud
from .encryption import decrypt_value


logger = logging.getLogger("uvicorn.error")

LEGACY_LLM_API_KEY = "glm_api_key"
LLM_API_KEY = "llm_api_key"
LEGACY_LLM_BASE_URL = "ai_base_url"
LLM_BASE_URL = "llm_base_url"
LEGACY_LLM_MODEL = "ai_model"
LLM_MODEL = "llm_model"


def _migrate_setting_key(db: Session, legacy_key: str, current_key: str) -> bool:
    """Rename one database setting while preserving encrypted values as-is."""
    legacy_setting = crud.get_system_setting(db, legacy_key)
    if legacy_setting is None:
        return False

    current_setting = crud.get_system_setting(db, current_key)
    if current_setting is None:
        crud.upsert_system_setting(
            db,
            key=current_key,
            value=legacy_setting.value,
            category=legacy_setting.category,
            is_encrypted=legacy_setting.is_encrypted,
            description=legacy_setting.description,
        )

    crud.delete_system_setting(db, legacy_key)
    return True


def migrate_legacy_llm_api_key(db: Session) -> bool:
    """Rename the legacy database setting without exposing or re-encrypting it."""
    return _migrate_setting_key(db, LEGACY_LLM_API_KEY, LLM_API_KEY)


def migrate_legacy_ai_settings(db: Session) -> list[tuple[str, str]]:
    """Move legacy shared AI keys into the LLM-specific namespace."""
    migrations = (
        (LEGACY_LLM_API_KEY, LLM_API_KEY),
        (LEGACY_LLM_BASE_URL, LLM_BASE_URL),
        (LEGACY_LLM_MODEL, LLM_MODEL),
    )
    migrated: list[tuple[str, str]] = []
    for legacy_key, current_key in migrations:
        if _migrate_setting_key(db, legacy_key, current_key):
            migrated.append((legacy_key, current_key))
    return migrated


class ConfigService:
    """配置服务，优先从数据库读取，回退到环境变量。"""

    def __init__(self, db: Session):
        self.db = db

    @lru_cache(maxsize=128)
    def get(self, key: str, default: str = "") -> str:
        """获取配置值，优先从数据库读取，回退到环境变量。

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            str: 配置值
        """
        # 先从数据库读取
        setting = crud.get_system_setting(self.db, key)
        if setting is not None:
            value = setting.value
            # 如果是加密配置，解密
            if setting.is_encrypted:
                try:
                    value = decrypt_value(value)
                except Exception as exc:
                    logger.exception(
                        "[config] Failed to decrypt setting key=%s error=%s",
                        key,
                        exc,
                    )
                    # 解密失败，回退到环境变量
                    return os.getenv(key.upper(), default)
            return value

        # 回退到环境变量
        return os.getenv(key.upper(), default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型配置。"""
        value = self.get(key, str(default))
        return value.lower() in ("true", "1", "yes", "on")

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数类型配置。"""
        value = self.get(key, str(default))
        try:
            return int(value)
        except ValueError:
            logger.warning(
                "[config] Invalid int value for key=%s value=%r, using default=%s",
                key,
                value,
                default,
            )
            return default

    def clear_cache(self):
        """清除配置缓存。"""
        self.get.cache_clear()


def get_config_service(db: Session) -> ConfigService:
    """获取配置服务实例。"""
    return ConfigService(db)
