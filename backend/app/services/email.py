"""邮件发送服务模块，支持 SMTP 异步发送。"""

import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger("uvicorn.error")


class EmailSettings(BaseSettings):
    """邮件配置，从环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "AgentChat通知系统"
    smtp_enabled: bool = True


email_settings = EmailSettings()


async def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    *,
    html: bool = False,
    config_override: dict | None = None,
) -> bool:
    """异步发送邮件。

    Args:
        to: 收件人邮箱地址，可以是单个字符串或列表
        subject: 邮件主题
        body: 邮件正文
        html: 是否为 HTML 格式，默认为纯文本
        config_override: 配置覆盖，用于从数据库读取的配置

    Returns:
        bool: 发送成功返回 True，否则返回 False
    """
    # 使用覆盖配置或默认配置
    config = config_override or {}
    smtp_enabled = config.get("smtp_enabled", email_settings.smtp_enabled)
    smtp_host = config.get("smtp_host", email_settings.smtp_host)
    smtp_port = config.get("smtp_port", email_settings.smtp_port)
    smtp_user = config.get("smtp_user", email_settings.smtp_user)
    smtp_password = config.get("smtp_password", email_settings.smtp_password)
    smtp_from_email = config.get("smtp_from_email", email_settings.smtp_from_email)
    smtp_from_name = config.get("smtp_from_name", email_settings.smtp_from_name)

    if not smtp_enabled:
        logger.info("[email] Email disabled, skipping send to=%s subject=%r", to, subject)
        return False

    if not smtp_user or not smtp_password:
        logger.warning("[email] SMTP credentials not configured, skipping send")
        return False

    try:
        message = EmailMessage()
        message["From"] = f"{smtp_from_name} <{smtp_from_email}>"
        message["To"] = to if isinstance(to, str) else ", ".join(to)
        message["Subject"] = subject

        if html:
            message.set_content(body, subtype="html")
        else:
            message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            use_tls=True,
        )

        logger.info("[email] Email sent successfully to=%s subject=%r", to, subject)
        return True

    except Exception as exc:
        logger.exception("[email] Failed to send email to=%s subject=%r error=%s", to, subject, exc)
        return False


def format_document_notification_email(
    *,
    original_filename: str,
    size_bytes: int,
    status: str,
    created_at: str,
    document_count: int = 0,
    chunk_count: int = 0,
    warnings: list[str] | None = None,
    error_message: str | None = None,
) -> tuple[str, str]:
    """格式化文档处理通知邮件的主题和正文。

    Returns:
        tuple[str, str]: (subject, body)
    """
    status_text = {
        "indexed": "✅ 处理成功",
        "failed": "❌ 处理失败",
    }.get(status, f"状态：{status}")

    subject = f"【AgentChat】文档处理完成 - {original_filename}"

    size_mb = size_bytes / (1024 * 1024)
    body_lines = [
        f"文档处理已完成，详情如下：\n",
        f"文件名：{original_filename}",
        f"文件大小：{size_mb:.2f} MB ({size_bytes:,} 字节)",
        f"上传时间：{created_at}",
        f"处理状态：{status_text}",
    ]

    if status == "indexed":
        body_lines.extend([
            f"\n处理结果：",
            f"- 文档数量：{document_count}",
            f"- 文本分片数：{chunk_count}",
        ])
        if warnings:
            body_lines.append(f"\n⚠️  警告信息：")
            for warning in warnings:
                body_lines.append(f"  - {warning}")
    elif status == "failed" and error_message:
        body_lines.append(f"\n错误信息：{error_message}")

    body_lines.extend([
        f"\n---",
        f"此邮件由 AgentChat 系统自动发送，请勿回复。",
    ])

    body = "\n".join(body_lines)
    return subject, body


def get_email_config_from_db(db) -> dict:
    """从数据库读取邮件配置。

    Args:
        db: 数据库会话

    Returns:
        dict: 邮件配置字典
    """
    from .config import get_config_service

    config_service = get_config_service(db)

    return {
        "smtp_enabled": config_service.get_bool("smtp_enabled", True),
        "smtp_host": config_service.get("smtp_host", "smtp.qq.com"),
        "smtp_port": config_service.get_int("smtp_port", 465),
        "smtp_user": config_service.get("smtp_user", ""),
        "smtp_password": config_service.get("smtp_password", ""),
        "smtp_from_email": config_service.get("smtp_from_email", ""),
        "smtp_from_name": config_service.get("smtp_from_name", "AgentChat通知系统"),
    }
