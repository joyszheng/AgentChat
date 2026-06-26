from sqlalchemy.orm import Session

from . import models, schemas


def create_task(db: Session, task: schemas.TaskCreate):
    """创建任务并返回包含数据库生成 ID 的记录。"""
    db_task = models.Task(
        title=task.title,
        description=task.description,
        completed=task.completed
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def list_tasks(
    db: Session,
    completed: bool | None = None,
    skip: int = 0,
    limit: int = 10
):
    """按完成状态筛选任务，并支持分页查询。"""
    query = db.query(models.Task)

    if completed is not None:
        query = query.filter(models.Task.completed == completed)

    return query.offset(skip).limit(limit).all()


def get_task(db: Session, task_id: int):
    """按 ID 查询单个任务；不存在时返回 None。"""
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def update_task(db: Session, task_id: int, task_update: schemas.TaskCreate):
    """用完整请求体替换任务内容。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    task.title = task_update.title
    task.description = task_update.description
    task.completed = task_update.completed

    db.commit()
    db.refresh(task)
    return task


def partial_update_task(db: Session, task_id: int, task_update: schemas.TaskUpdate):
    """仅更新请求中显式提供的字段。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    # 排除未传入的字段，避免 PATCH 请求意外覆盖已有数据。
    update_data = task_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int):
    """删除指定任务；不存在时返回 None。"""
    task = get_task(db, task_id)

    if task is None:
        return None

    db.delete(task)
    db.commit()
    return task
