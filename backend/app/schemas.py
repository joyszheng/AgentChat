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
