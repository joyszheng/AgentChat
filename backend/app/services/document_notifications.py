import logging

from .. import crud
from ..database import SessionLocal
from .config import get_config_service
from .email import format_document_notification_email, get_email_config_from_db, send_email


logger = logging.getLogger("uvicorn.error")

# 文档处理完成后的邮件通知接收地址
DOCUMENT_NOTIFICATION_EMAIL = "2810363752@qq.com"


async def send_document_notification_email(
    *,
    document_id: int,
    original_filename: str,
    size_bytes: int,
    status: str,
    document_count: int = 0,
    chunk_count: int = 0,
    warnings: list[str] | None = None,
    error_message: str | None = None,
) -> None:
    """发送文档处理完成通知邮件。"""
    try:
        with SessionLocal() as db:
            document = crud.get_uploaded_document(db, document_id)
            if document is None:
                logger.warning(
                    "[email] Document not found, skipping notification document_id=%s",
                    document_id,
                )
                return

            created_at = document.created_at.strftime("%Y-%m-%d %H:%M:%S")
            email_config = get_email_config_from_db(db)
            config_service = get_config_service(db)
            notification_email = config_service.get(
                "document_notification_email",
                DOCUMENT_NOTIFICATION_EMAIL,
            )

        subject, body = format_document_notification_email(
            original_filename=original_filename,
            size_bytes=size_bytes,
            status=status,
            created_at=created_at,
            document_count=document_count,
            chunk_count=chunk_count,
            warnings=warnings or [],
            error_message=error_message,
        )

        success = await send_email(
            to=notification_email,
            subject=subject,
            body=body,
            config_override=email_config,
        )

        if success:
            logger.info(
                "[upload:%s] Email notification sent to=%s status=%s",
                document_id,
                notification_email,
                status,
            )
        else:
            logger.warning(
                "[upload:%s] Email notification failed to=%s status=%s",
                document_id,
                notification_email,
                status,
            )

    except Exception as exc:
        logger.exception(
            "[upload:%s] Email notification error document_id=%s error=%s",
            document_id,
            document_id,
            exc,
        )
