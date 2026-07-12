from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Task(Base):
    """任务表对应的 ORM 模型。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="todo", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    execution_mode: Mapped[str] = mapped_column(
        String(30), default="manual", nullable=False, index=True
    )
    schedule_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    recurrence_rule: Mapped[str] = mapped_column(
        String(30), default="none", nullable=False, index=True
    )
    ai_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    notify_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # 置为 running 时写入，供 reaper 判定执行是否超时（租约起点）。
    run_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run_status: Mapped[str] = mapped_column(
        String(30), default="idle", nullable=False, index=True
    )
    run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 当前这次到期执行的连续失败次数；成功或推进到下一次执行时清零。
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TaskRun(Base):
    """AI 自动任务的单次执行记录。"""

    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False, index=True)
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadedDocument(Base):
    """上传文档表，记录文件保存、解析和入库状态。"""

    __tablename__ = "uploaded_documents"
    __table_args__ = (
        UniqueConstraint(
            "original_filename",
            "file_sha256",
            name="uq_uploaded_document_name_hash",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_ext: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_to: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False, index=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatSession(Base):
    """多轮对话会话，保存长期摘要记忆和会话元信息。"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode: Mapped[str] = mapped_column(String(50), default="chat", nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    """多轮对话消息记录。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class SystemSetting(Base):
    """系统配置表，存储加密后的配置项。"""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MCPServer(Base):
    """Registered remote MCP server and its local exposure policy."""

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transport: Mapped[str] = mapped_column(
        String(30), default="streamable_http", nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    headers_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    require_admin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    discovered_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    call_timeout_seconds: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    max_result_chars: Mapped[int] = mapped_column(Integer, default=20000, nullable=False)
    last_health_status: Mapped[str] = mapped_column(
        String(30), default="unknown", nullable=False, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base):
    """用户表，存储用户认证信息。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
