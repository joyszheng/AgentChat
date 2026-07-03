"""配置加密服务，使用 Fernet (AES 128) 对称加密。"""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger("uvicorn.error")


class EncryptionSettings(BaseSettings):
    """加密配置，从环境变量加载加密密钥。"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    encryption_key: str = ""


_encryption_settings = EncryptionSettings()


def _get_or_generate_key() -> bytes:
    """获取或生成加密密钥。"""
    if _encryption_settings.encryption_key:
        return _encryption_settings.encryption_key.encode()

    # 如果环境变量未配置，生成一个新密钥并警告
    key = Fernet.generate_key()
    logger.warning(
        "[encryption] ENCRYPTION_KEY not configured in .env, using temporary key. "
        "Add this to .env to persist encryption: ENCRYPTION_KEY=%s",
        key.decode(),
    )
    return key


_fernet = Fernet(_get_or_generate_key())


def encrypt_value(plaintext: str) -> str:
    """加密明文字符串，返回 base64 编码的密文。

    Args:
        plaintext: 需要加密的明文字符串

    Returns:
        str: base64 编码的密文
    """
    if not plaintext:
        return ""

    try:
        encrypted_bytes = _fernet.encrypt(plaintext.encode())
        return encrypted_bytes.decode()
    except Exception as exc:
        logger.exception("[encryption] Encryption failed: %s", exc)
        raise


def decrypt_value(ciphertext: str) -> str:
    """解密密文字符串，返回明文。

    Args:
        ciphertext: base64 编码的密文

    Returns:
        str: 解密后的明文字符串
    """
    if not ciphertext:
        return ""

    try:
        decrypted_bytes = _fernet.decrypt(ciphertext.encode())
        return decrypted_bytes.decode()
    except Exception as exc:
        logger.exception("[encryption] Decryption failed: %s", exc)
        raise


def mask_sensitive_value(value: str, *, show_first: int = 0, show_last: int = 0) -> str:
    """对敏感信息进行脱敏显示。

    Args:
        value: 原始值
        show_first: 显示开头多少个字符
        show_last: 显示末尾多少个字符

    Returns:
        str: 脱敏后的字符串，如 "sk-***xyz"
    """
    if not value:
        return ""

    if len(value) <= show_first + show_last:
        return "*" * len(value)

    first_part = value[:show_first] if show_first > 0 else ""
    last_part = value[-show_last:] if show_last > 0 else ""

    return f"{first_part}{'*' * 6}{last_part}"
