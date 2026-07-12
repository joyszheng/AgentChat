from datetime import datetime

from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


TaskStatus = Literal["todo", "in_progress", "blocked", "done", "canceled"]
TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskSource = Literal["manual", "ai"]
TaskExecutionMode = Literal["manual", "ai_auto"]
TaskRecurrenceRule = Literal["none", "daily"]
TaskRunStatus = Literal["idle", "pending", "queued", "running", "success", "failed"]


class TaskCreate(BaseModel):
    """创建或完整替换任务时使用的请求数据。"""

    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    completed: bool = False
    status: TaskStatus | None = None
    priority: TaskPriority = "normal"
    due_at: datetime | None = None
    source: TaskSource = "manual"
    execution_mode: TaskExecutionMode = "manual"
    schedule_at: datetime | None = None
    recurrence_rule: TaskRecurrenceRule = "none"
    ai_prompt: str | None = Field(default=None, max_length=4000)
    notify_email: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def normalize_status(self):
        if self.status is None:
            self.status = "done" if self.completed else "todo"
        else:
            self.completed = self.status == "done"
        if self.execution_mode == "ai_auto":
            if self.schedule_at is None:
                raise ValueError("AI 自动任务需要设置执行时间")
            if not self.ai_prompt or not self.ai_prompt.strip():
                raise ValueError("AI 自动任务需要填写执行说明")
        return self


class TaskUpdate(BaseModel):
    """部分更新任务时使用的请求数据；未提供的字段保持不变。"""

    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    completed: bool | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    execution_mode: TaskExecutionMode | None = None
    schedule_at: datetime | None = None
    recurrence_rule: TaskRecurrenceRule | None = None
    ai_prompt: str | None = Field(default=None, max_length=4000)
    notify_email: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def normalize_status(self):
        if self.status is not None:
            self.completed = self.status == "done"
        elif self.completed is not None:
            self.status = "done" if self.completed else "todo"
        return self


class TaskResponse(TaskCreate):
    """任务接口返回的数据结构。"""

    id: int
    user_id: int | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_status: str
    run_error: str | None
    run_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        # 允许直接从 SQLAlchemy ORM 对象生成响应模型。
        "from_attributes": True
    }


class TaskRunResponse(BaseModel):
    """AI 自动任务单次执行记录。"""

    id: int
    task_id: int
    user_id: int | None
    status: str
    input_snapshot: dict
    output: str | None
    error_message: str | None
    tools_used: list[str]
    email_sent: bool
    started_at: datetime
    finished_at: datetime | None

    model_config = {
        "from_attributes": True
    }


class UploadedDocumentResponse(BaseModel):
    """上传文档记录接口返回的数据结构。"""

    id: int
    original_filename: str
    stored_filename: str
    content_type: str | None
    file_ext: str
    size_bytes: int
    saved_to: str
    status: str
    document_count: int
    chunk_count: int
    file_sha256: str | None
    warnings: list[str]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class UploadedDocumentDeleteResponse(BaseModel):
    """删除上传文档后返回的资源清理结果。"""

    document_id: int
    deleted: bool
    file_deleted: bool
    vector_chunks_deleted: int


class ChatSessionCreate(BaseModel):
    """创建会话时使用的数据。"""

    title: str | None = Field(default=None, max_length=200)
    mode: str = Field(default="chat", max_length=50)


class ChatSessionResponse(BaseModel):
    """会话列表和详情返回的数据结构。"""

    id: int
    title: str | None
    mode: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None
    deleted_at: datetime | None

    model_config = {
        "from_attributes": True
    }


class ChatMessageResponse(BaseModel):
    """会话消息返回的数据结构。"""

    id: int
    session_id: int
    role: str
    content: str
    message_metadata: dict
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ChatRequest(BaseModel):
    """普通聊天请求，session_id 为空时自动创建新会话。"""

    message: str = Field(min_length=1, max_length=2000, description="user message")
    session_id: int | None = None


class ChatResponse(BaseModel):
    """普通聊天响应。"""

    answer: str = Field(description="AI response")
    session_id: int
    user_message_id: int
    assistant_message_id: int


class MCPAssistantResponse(ChatResponse):
    """Response from the assistant that may invoke registered MCP tools."""

    tools_used: list[str] = Field(default_factory=list)


class AssistantResponse(ChatResponse):
    """Response from the unified assistant across chat, RAG, tasks, and MCP."""

    route: str = Field(description="Selected execution route")
    sources: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class SystemSettingBase(BaseModel):
    """系统配置基础模型。"""

    key: str = Field(min_length=1, max_length=100)
    value: str
    category: str = Field(min_length=1, max_length=50)
    is_encrypted: bool = False
    description: str | None = Field(default=None, max_length=500)


class SystemSettingCreate(SystemSettingBase):
    """创建或更新系统配置时使用的请求数据。"""
    pass


class SystemSettingResponse(BaseModel):
    """系统配置接口返回的数据结构。"""

    id: int
    key: str
    value: str  # 敏感配置会自动脱敏
    category: str
    is_encrypted: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class SystemSettingBatchUpdate(BaseModel):
    """批量更新系统配置。"""

    settings: list[SystemSettingCreate]


class ModelOptionsRequest(BaseModel):
    """Request available model IDs from an OpenAI-compatible provider."""

    kind: Literal["llm", "embedding"]
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)


class ModelOption(BaseModel):
    """One model returned by an OpenAI-compatible /models endpoint."""

    id: str
    owned_by: str | None = None


class ModelOptionsResponse(BaseModel):
    """Available models for a provider configuration."""

    models: list[ModelOption]
    count: int


class MCPServerBase(BaseModel):
    """Common configuration for a remote MCP server."""

    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    description: str | None = Field(default=None, max_length=500)
    transport: Literal["streamable_http"] = "streamable_http"
    url: AnyHttpUrl
    enabled: bool = False
    require_admin: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    call_timeout_seconds: int = Field(default=20, ge=1, le=300)
    max_result_chars: int = Field(default=20000, ge=1000, le=200000)

    @field_validator("allowed_tools")
    @classmethod
    def normalize_allowed_tools(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for tool_name in value:
            name = tool_name.strip()
            if name and name not in normalized:
                normalized.append(name)
        return normalized


class MCPServerCreate(MCPServerBase):
    """Register a new MCP server. Headers are encrypted before storage."""

    headers: dict[str, str] = Field(default_factory=dict)


class MCPServerUpdate(BaseModel):
    """Partially update an MCP server. Omitted headers preserve current credentials."""

    description: str | None = Field(default=None, max_length=500)
    url: AnyHttpUrl | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None
    require_admin: bool | None = None
    allowed_tools: list[str] | None = None
    call_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    max_result_chars: int | None = Field(default=None, ge=1000, le=200000)

    @field_validator("allowed_tools")
    @classmethod
    def normalize_optional_allowed_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for tool_name in value:
            name = tool_name.strip()
            if name and name not in normalized:
                normalized.append(name)
        return normalized


class MCPServerResponse(BaseModel):
    """MCP server configuration without secret header values."""

    id: int
    name: str
    description: str | None
    transport: str
    url: str
    enabled: bool
    require_admin: bool
    allowed_tools: list[str]
    discovered_tools: list[str]
    header_names: list[str]
    call_timeout_seconds: int
    max_result_chars: int
    last_health_status: str
    last_error: str | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MCPToolInfo(BaseModel):
    """A tool discovered from an MCP server."""

    server_id: int
    server_name: str
    name: str
    qualified_name: str
    description: str
    enabled: bool
    require_admin: bool


class MCPToolInvokeRequest(BaseModel):
    """Arguments for an administrator-initiated MCP tool call."""

    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolInvokeResponse(BaseModel):
    """Result of an administrator-initiated MCP tool call."""

    qualified_name: str
    result: Any
    duration_ms: int


class UserLogin(BaseModel):
    """用户登录请求。"""

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    """用户信息响应。"""

    id: int
    username: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class TokenResponse(BaseModel):
    """登录成功返回的令牌。"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
