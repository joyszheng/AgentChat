from langchain.tools import tool

from .. import crud, schemas
from ..database import SessionLocal

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
        
        lines = [
            f"ID: {task.id}, 标题：{task.title}, 描述：{task.description or '无'}"
            for task in tasks
        ]

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
            completed=False
        )

        task = crud.create_task(db=db, task = task_data)

        return(
            f"任务创建成功"
            f"ID:{task.id}, 标题：{task.title},"
            f"描述：{task.description or '无'}"
        )
    finally:
        db.close()