import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..services import task_executor
from ..services.dependencies import require_auth


logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)


def _queued_next_run(task) -> datetime | None:
    if task.execution_mode != "ai_auto":
        return None
    if task.status in ("done", "canceled"):
        return None
    return task.next_run_at


def _is_before_now(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc) < datetime.now(timezone.utc)


def _reject_past_schedule(schedule_at: datetime | None) -> None:
    if schedule_at is not None and _is_before_now(schedule_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI 执行时间不能早于当前时间",
        )


async def _sync_task_queue(
    *,
    task_id: int,
    previous_next_run_at: datetime | None,
    current_next_run_at: datetime | None,
) -> None:
    try:
        await task_executor.reschedule_ai_task_job(
            task_id=task_id,
            previous_next_run_at=previous_next_run_at,
            current_next_run_at=current_next_run_at,
        )
    except Exception:
        logger.exception("[tasks] Failed to synchronize AI task queue task_id=%s", task_id)


@router.post("", response_model=schemas.TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: schemas.TaskCreate,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """创建一条任务。"""
    if task.execution_mode == "ai_auto":
        _reject_past_schedule(task.schedule_at)
    created_task = crud.create_task(db, task, user_id=user.id)
    await _sync_task_queue(
        task_id=created_task.id,
        previous_next_run_at=None,
        current_next_run_at=_queued_next_run(created_task),
    )
    return created_task


@router.get("", response_model=list[schemas.TaskResponse])
def list_tasks(
    completed: bool | None = None,
    status_filter: Annotated[schemas.TaskStatus | None, Query(alias="status")] = None,
    priority: schemas.TaskPriority | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """查询任务列表，可按完成状态筛选并分页。"""
    return crud.list_tasks(
        db,
        completed=completed,
        status=status_filter,
        priority=priority,
        search=search,
        user_id=user.id,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=schemas.TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """返回指定 ID 的任务。"""
    task = crud.get_task(db, task_id, user_id=user.id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task


@router.get("/{task_id}/runs", response_model=list[schemas.TaskRunResponse])
def list_task_runs(
    task_id: int,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """查询当前用户指定 AI 自动任务的执行记录。"""
    task = crud.get_task(db, task_id, user_id=user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return crud.list_task_runs(
        db,
        task_id=task_id,
        user_id=user.id,
        skip=skip,
        limit=limit,
    )


@router.put("/{task_id}", response_model=schemas.TaskResponse)
async def update_task(
    task_id: int,
    task_update: schemas.TaskCreate,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """使用完整数据替换指定任务。"""
    if task_update.execution_mode == "ai_auto":
        _reject_past_schedule(task_update.schedule_at)
    existing_task = crud.get_task(db, task_id, user_id=user.id)
    if existing_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    previous_next_run_at = _queued_next_run(existing_task)
    task = crud.update_task(db, task_id, task_update, user_id=user.id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    await _sync_task_queue(
        task_id=task.id,
        previous_next_run_at=previous_next_run_at,
        current_next_run_at=_queued_next_run(task),
    )
    return task


@router.patch("/{task_id}", response_model=schemas.TaskResponse)
async def partial_update_task(
    task_id: int,
    task_update: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """更新指定任务中请求体提供的字段。"""
    _reject_past_schedule(task_update.schedule_at)
    existing_task = crud.get_task(db, task_id, user_id=user.id)
    if existing_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    previous_next_run_at = _queued_next_run(existing_task)
    task = crud.partial_update_task(db, task_id, task_update, user_id=user.id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    await _sync_task_queue(
        task_id=task.id,
        previous_next_run_at=previous_next_run_at,
        current_next_run_at=_queued_next_run(task),
    )
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """删除指定任务。"""
    existing_task = crud.get_task(db, task_id, user_id=user.id)
    if existing_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    previous_next_run_at = _queued_next_run(existing_task)
    task = crud.delete_task(db, task_id, user_id=user.id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    await _sync_task_queue(
        task_id=task_id,
        previous_next_run_at=previous_next_run_at,
        current_next_run_at=None,
    )
    return None
