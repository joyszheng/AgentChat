import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas


# 生成失败的退避重试策略（可被环境变量覆盖）。
TASK_MAX_RETRIES = int(os.getenv("TASK_MAX_RETRIES", "3"))
_RETRY_BACKOFF_SECONDS = (60, 300, 900)


def _sync_task_execution_schedule(task: models.Task, *, force_reschedule: bool = False) -> None:
    if task.execution_mode != "ai_auto" or task.status in ("done", "canceled"):
        task.next_run_at = None
        if task.run_status != "running":
            task.run_status = "idle"
        task.run_error = None
        return

    if task.schedule_at is None:
        task.next_run_at = None
        task.run_status = "idle"
        return

    if force_reschedule or task.next_run_at is None or task.last_run_at is None:
        task.next_run_at = task.schedule_at

    if task.run_status != "running":
        task.run_status = "pending"
        task.run_error = None


def create_task(db: Session, task: schemas.TaskCreate, *, user_id: int | None = None):
    """创建任务并返回包含数据库生成 ID 的记录。"""
    db_task = models.Task(
        title=task.title,
        description=task.description,
        completed=task.completed,
        status=task.status or ("done" if task.completed else "todo"),
        priority=task.priority,
        due_at=task.due_at,
        source=task.source,
        user_id=user_id,
        execution_mode=task.execution_mode,
        schedule_at=task.schedule_at,
        recurrence_rule=task.recurrence_rule,
        ai_prompt=task.ai_prompt,
        notify_email=task.notify_email,
    )
    _sync_task_execution_schedule(db_task, force_reschedule=True)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def list_tasks(
    db: Session,
    completed: bool | None = None,
    status: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    user_id: int | None = None,
    skip: int = 0,
    limit: int = 10,
):
    """按完成状态筛选任务，并支持分页查询。"""
    query = db.query(models.Task)

    if user_id is not None:
        query = query.filter(models.Task.user_id == user_id)
    if completed is not None:
        query = query.filter(models.Task.completed == completed)
    if status is not None:
        query = query.filter(models.Task.status == status)
    if priority is not None:
        query = query.filter(models.Task.priority == priority)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.Task.title.ilike(pattern),
                models.Task.description.ilike(pattern),
            )
        )

    return (
        query.order_by(
            models.Task.completed.asc(),
            models.Task.due_at.asc().nullslast(),
            models.Task.updated_at.desc(),
            models.Task.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_task(db: Session, task_id: int, *, user_id: int | None = None):
    """按 ID 查询单个任务；不存在时返回 None。"""
    query = db.query(models.Task).filter(models.Task.id == task_id)
    if user_id is not None:
        query = query.filter(models.Task.user_id == user_id)
    return query.first()


def update_task(
    db: Session,
    task_id: int,
    task_update: schemas.TaskCreate,
    *,
    user_id: int | None = None,
):
    """用完整请求体替换任务内容。"""
    task = get_task(db, task_id, user_id=user_id)

    if task is None:
        return None

    task.title = task_update.title
    task.description = task_update.description
    task.completed = task_update.completed
    task.status = task_update.status or ("done" if task_update.completed else "todo")
    task.priority = task_update.priority
    task.due_at = task_update.due_at
    task.source = task_update.source
    task.execution_mode = task_update.execution_mode
    task.schedule_at = task_update.schedule_at
    task.recurrence_rule = task_update.recurrence_rule
    task.ai_prompt = task_update.ai_prompt
    task.notify_email = task_update.notify_email
    _sync_task_execution_schedule(task, force_reschedule=True)

    db.commit()
    db.refresh(task)
    return task


def partial_update_task(
    db: Session,
    task_id: int,
    task_update: schemas.TaskUpdate,
    *,
    user_id: int | None = None,
):
    """仅更新请求中显式提供的字段。"""
    task = get_task(db, task_id, user_id=user_id)

    if task is None:
        return None

    # 排除未传入的字段，避免 PATCH 请求意外覆盖已有数据。
    update_data = task_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(task, key, value)

    should_sync_schedule = any(
        key in update_data
        for key in ("execution_mode", "schedule_at", "recurrence_rule", "status", "completed")
    )
    if should_sync_schedule:
        _sync_task_execution_schedule(
            task,
            force_reschedule=any(
                key in update_data for key in ("execution_mode", "schedule_at", "recurrence_rule")
            ),
        )

    db.commit()
    db.refresh(task)
    return task


def list_due_ai_tasks(db: Session, *, now: datetime, limit: int = 5):
    """Return AI tasks ready to run and mark them as queued."""

    tasks = (
        db.query(models.Task)
        .filter(models.Task.execution_mode == "ai_auto")
        .filter(models.Task.next_run_at.is_not(None))
        .filter(models.Task.next_run_at <= now)
        .filter(models.Task.run_status.notin_(("queued", "running")))
        .filter(models.Task.status.notin_(("done", "canceled")))
        .order_by(models.Task.next_run_at.asc(), models.Task.id.asc())
        .limit(limit)
        .all()
    )

    for task in tasks:
        task.run_status = "queued"
        task.run_error = None

    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks


def mark_ai_task_pending(db: Session, task_id: int):
    task = get_task(db, task_id)
    if task is None:
        return None
    if task.execution_mode == "ai_auto" and task.next_run_at is not None:
        task.run_status = "pending"
    db.commit()
    db.refresh(task)
    return task


def reset_stuck_ai_tasks(
    db: Session,
    *,
    now: datetime,
    running_timeout: timedelta,
    queued_timeout: timedelta,
) -> int:
    """恢复因崩溃/丢 job 而卡死的 AI 任务，返回恢复数量。"""
    running_cutoff = now - running_timeout
    queued_cutoff = now - queued_timeout
    recovered = 0

    stuck_running = (
        db.query(models.Task)
        .filter(models.Task.execution_mode == "ai_auto")
        .filter(models.Task.run_status == "running")
        .filter(
            or_(
                models.Task.run_started_at.is_(None),
                models.Task.run_started_at < running_cutoff,
            )
        )
        .all()
    )
    for task in stuck_running:
        dangling_run = (
            db.query(models.TaskRun)
            .filter(models.TaskRun.task_id == task.id)
            .filter(models.TaskRun.status == "running")
            .order_by(models.TaskRun.id.desc())
            .first()
        )
        if dangling_run is not None:
            dangling_run.status = "failed"
            dangling_run.error_message = "执行被中断（进程退出或超时），已自动恢复"
            dangling_run.finished_at = now
        task.run_status = "pending"
        task.run_started_at = None
        task.run_error = "上次执行被中断，已自动恢复重试"
        recovered += 1

    stuck_queued = (
        db.query(models.Task)
        .filter(models.Task.execution_mode == "ai_auto")
        .filter(models.Task.run_status == "queued")
        .filter(models.Task.updated_at < queued_cutoff)
        .all()
    )
    for task in stuck_queued:
        task.run_status = "pending"
        recovered += 1

    if recovered:
        db.commit()
    return recovered


def start_ai_task_execution(db: Session, task_id: int, *, now: datetime):
    task = get_task(db, task_id)
    if task is None:
        return None
    if task.execution_mode != "ai_auto":
        return None
    if task.status == "canceled":
        return None
    if task.next_run_at is None:
        return None
    next_run_at = task.next_run_at
    if next_run_at.tzinfo is None and now.tzinfo is not None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)
    if next_run_at > now:
        return None
    if task.run_status == "running":
        return None

    task.run_status = "running"
    task.run_started_at = now
    task.run_error = None
    db.commit()
    db.refresh(task)
    return task


def create_task_run(
    db: Session,
    *,
    task: models.Task,
    input_snapshot: dict,
):
    run = models.TaskRun(
        task_id=task.id,
        user_id=task.user_id,
        status="running",
        input_snapshot=input_snapshot,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _as_aware_utc(value: datetime) -> datetime:
    """把 DB 读回的 datetime 统一成 aware-UTC（SQLite 会丢时区，PG 保留）。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _next_daily_run(next_run_at: datetime, now: datetime) -> datetime:
    candidate = _as_aware_utc(next_run_at) + timedelta(days=1)
    now = _as_aware_utc(now)
    while candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


def _retry_backoff(attempt: int) -> timedelta:
    index = min(max(attempt, 1), len(_RETRY_BACKOFF_SECONDS)) - 1
    return timedelta(seconds=_RETRY_BACKOFF_SECONDS[index])


def _advance_after_success(task: models.Task, now: datetime) -> None:
    if task.recurrence_rule == "daily" and task.next_run_at is not None:
        task.next_run_at = _next_daily_run(task.next_run_at, now)
        task.run_status = "pending"
    else:
        task.next_run_at = None
        task.completed = True
        task.status = "done"


def _handle_failed_run(task: models.Task, now: datetime, *, retryable: bool) -> None:
    if retryable and (task.retry_count or 0) < TASK_MAX_RETRIES:
        # 瞬时错误：退避后重试；调度器会在 next_run_at 到期时重新入队。
        task.retry_count = (task.retry_count or 0) + 1
        task.next_run_at = now + _retry_backoff(task.retry_count)
        task.run_status = "pending"
        return

    # 不可重试或次数耗尽。
    task.retry_count = 0
    task.run_status = "failed"
    if task.recurrence_rule == "daily" and task.next_run_at is not None:
        # 保住重复能力：记为失败，但明天照常执行，而不是永久停用。
        task.next_run_at = _next_daily_run(task.next_run_at, now)
    else:
        task.next_run_at = None


def finish_task_run(
    db: Session,
    *,
    task: models.Task,
    run: models.TaskRun,
    now: datetime,
    output_ok: bool,
    output: str | None = None,
    error_message: str | None = None,
    email_sent: bool = False,
    retryable: bool = False,
    tools_used: list[str] | None = None,
):
    """收尾一次执行。"""
    run.status = "success" if output_ok else "failed"
    run.output = output
    run.error_message = error_message
    run.email_sent = email_sent
    run.tools_used = tools_used or []
    run.finished_at = now

    task.last_run_at = now
    task.run_count = (task.run_count or 0) + 1
    task.run_started_at = None
    task.run_error = error_message

    if output_ok:
        task.run_status = "success"
        task.retry_count = 0
        _advance_after_success(task, now)
    else:
        _handle_failed_run(task, now, retryable=retryable)

    db.commit()
    db.refresh(run)
    db.refresh(task)
    return run


def list_task_runs(
    db: Session,
    *,
    task_id: int,
    user_id: int | None = None,
    skip: int = 0,
    limit: int = 20,
):
    query = db.query(models.TaskRun).filter(models.TaskRun.task_id == task_id)
    if user_id is not None:
        query = query.filter(models.TaskRun.user_id == user_id)
    return (
        query.order_by(models.TaskRun.started_at.desc(), models.TaskRun.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_task(db: Session, task_id: int, *, user_id: int | None = None):
    """删除指定任务；不存在时返回 None。"""
    task = get_task(db, task_id, user_id=user_id)

    if task is None:
        return None

    db.delete(task)
    db.commit()
    return task
