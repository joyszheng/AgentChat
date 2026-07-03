"""配置管理服务，支持从数据库或环境变量读取配置。"""

import logging
import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from .. import crud
from .encryption import decrypt_value


logger = logging.getLogger("uvicorn.error")


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
