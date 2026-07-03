from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    """创建或完整替换任务时使用的请求数据。"""

    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    completed: bool = False


class TaskUpdate(BaseModel):
    """部分更新任务时使用的请求数据；未提供的字段保持不变。"""

    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    completed: bool | None = None


class TaskResponse(TaskCreate):
    """任务接口返回的数据结构。"""

    id: int

    model_config = {
        # 允许直接从 SQLAlchemy ORM 对象生成响应模型。
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
