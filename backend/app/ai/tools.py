from langchain.tools import tool
from langchain_core.tools import BaseTool, StructuredTool

from .. import crud, schemas
from ..database import SessionLocal


def _format_task(task) -> str:
    due_text = task.due_at.isoformat() if task.due_at else "无"
    return (
        f"ID: {task.id}, 标题：{task.title}, 状态：{task.status}, "
        f"优先级：{task.priority}, 截止时间：{due_text}, "
        f"描述：{task.description or '无'}"
    )


def create_task_tools(user_id: int | None = None) -> list[BaseTool]:
    """Create request-scoped task tools, optionally limited to one user."""

    def list_my_tasks(
        limit: int = 10,
        status: schemas.TaskStatus | None = None,
        priority: schemas.TaskPriority | None = None,
    ) -> str:
        """查询当前用户的任务列表，可按状态和优先级筛选。"""

        if user_id is None:
            return "请先登录后再查询任务。"

        db = SessionLocal()
        try:
            tasks = crud.list_tasks(
                db=db,
                completed=False if status is None else None,
                status=status,
                priority=priority,
                user_id=user_id,
                limit=limit,
            )

            if not tasks:
                return "当前没有匹配的任务。"

            return "\n".join(_format_task(task) for task in tasks)
        finally:
            db.close()

    def create_my_task(
        title: str,
        description: str | None = None,
        priority: schemas.TaskPriority = "normal",
        due_at: str | None = None,
    ) -> str:
        """创建一条新的待办任务。due_at 使用 ISO 日期时间字符串。"""

        if user_id is None:
            return "请先登录后再创建任务。"

        db = SessionLocal()
        try:
            task_data = schemas.TaskCreate(
                title=title,
                description=description,
                priority=priority,
                due_at=due_at,
                source="ai",
            )
            task = crud.create_task(db=db, task=task_data, user_id=user_id)

            return f"任务创建成功。{_format_task(task)}"
        finally:
            db.close()

    return [
        StructuredTool.from_function(
            func=list_my_tasks,
            name="list_uncompleted_tasks",
            description="查询当前用户未完成或指定状态/优先级的任务。",
        ),
        StructuredTool.from_function(
            func=create_my_task,
            name="create_task_by_ai",
            description="为当前用户创建一条新的待办任务。仅在用户明确要求创建任务时使用。",
        ),
    ]

@tool
def list_uncompleted_tasks(limit: int = 10) -> str:
    """查询数据库中的未完成任务
    
    Args:
        limit = 最多返回多少条任务，默认返回10条。
    """

    db = SessionLocal()

    try:
        tasks = crud.list_tasks(
            db = db,
            completed=False,
            limit = limit
        )

        if not tasks:
            return "当前 没有未完成任务。"
        
        lines = [_format_task(task) for task in tasks]

        return "\n".join(lines)
    finally:
        db.close()


@tool
def create_task_by_ai(
    title: str,
    description: str | None = None
) -> str:
    """创建一条新的待办任务
    
    Args:
        title: 任务标题，不能为空。
        description: 任务的详细描述，可以不填写。
    """

    db = SessionLocal()

    try:
        task_data = schemas.TaskCreate(
            title = title,
            description = description,
            completed=False,
            source="ai",
        )

        task = crud.create_task(db=db, task = task_data)

        return(
            f"任务创建成功。{_format_task(task)}"
        )
    finally:
        db.close()
