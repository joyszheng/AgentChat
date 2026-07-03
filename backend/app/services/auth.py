"""认证工具：密码加密和 JWT 令牌管理。"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger("uvicorn.error")


class AuthSettings(BaseSettings):
    """认证配置，从环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 43200  # 30 天


auth_settings = AuthSettings()

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_or_generate_jwt_secret() -> str:
    """获取或生成 JWT 密钥。"""
    if auth_settings.jwt_secret_key:
        return auth_settings.jwt_secret_key

    # 生成随机密钥
    import secrets
    secret = secrets.token_urlsafe(32)
    logger.warning(
        "[auth] JWT_SECRET_KEY not configured in .env, using temporary key. "
        "Add this to .env to persist: JWT_SECRET_KEY=%s",
        secret,
    )
    return secret


JWT_SECRET_KEY = _get_or_generate_jwt_secret()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配。

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        bool: 密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """对密码进行哈希加密。

    Args:
        password: 明文密码

    Returns:
        str: 哈希后的密码
    """
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建 JWT 访问令牌。

    Args:
        data: 要编码的数据（如 {"sub": "username"}）
        expires_delta: 过期时间增量，不传则使用默认配置

    Returns:
        str: JWT 令牌
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=auth_settings.jwt_access_token_expire_minutes
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=auth_settings.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """解码 JWT 访问令牌。

    Args:
        token: JWT 令牌

    Returns:
        dict | None: 解码后的数据，失败返回 None
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[auth_settings.jwt_algorithm])
        return payload
    except JWTError as exc:
        logger.debug("[auth] JWT decode failed: %s", exc)
        return None
