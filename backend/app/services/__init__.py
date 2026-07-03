"""服务模块，包含邮件发送等业务逻辑。"""

from .email import send_email, format_document_notification_email

__all__ = ["send_email", "format_document_notification_email"]
