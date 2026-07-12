import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from . import models, schemas


INTERRUPTED_DOCUMENT_STATUSES = ("uploaded", "processing", "parsing", "chunking", "indexing")

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
    limit: int = 10
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
    """恢复因崩溃/丢 job 而卡死的 AI 任务，返回恢复数量。

    没有这一步，worker OOM/重启会把任务永久留在 run_status='running'，Redis
    重启/淘汰会把任务永久留在 'queued'——两者都会被 list_due_ai_tasks 与
    start_ai_task_execution 跳过，任务再也不会执行。

    - running 超过租约（run_started_at 早于 running_timeout，或为空）→ 复位为
      pending，并把挂起的 TaskRun 收尾为 failed。
    - queued 超过 queued_timeout（用 updated_at 作入队时刻代理）→ 复位为 pending，
      让调度器重新入队。

    next_run_at 保持不变，任务仍到期，会被重新捡起。
    """
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
    """收尾一次执行。

    生成成功即视为 run 成功——邮件发送失败只作提示，不影响成败，也不再杀掉每日
    重复。生成失败时按可重试性退避重试；不可重试或次数耗尽后，daily 推进到下一次
    执行（保住重复），只有一次性任务才终止。
    """
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


def create_uploaded_document(
    db: Session,
    *,
    original_filename: str,
    stored_filename: str,
    content_type: str | None,
    file_ext: str,
    size_bytes: int,
    saved_to: str,
    file_sha256: str | None = None,
):
    """创建上传文件记录，初始状态为 uploaded。"""

    document = models.UploadedDocument(
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_ext=file_ext,
        size_bytes=size_bytes,
        saved_to=saved_to,
        file_sha256=file_sha256,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_processing(db: Session, document_id: int):
    """Mark an uploaded document as being processed by the background worker."""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "processing"
    document.error_message = None

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_stage(
    db: Session,
    document_id: int,
    *,
    stage: str,
    chunk_count: int | None = None,
):
    """更新文档处理阶段，供列表查询和 SSE 进度订阅使用。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = stage
    document.error_message = None
    if chunk_count is not None:
        document.chunk_count = chunk_count

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_indexed(
    db: Session,
    document_id: int,
    *,
    document_count: int,
    chunk_count: int,
    file_sha256: str | None,
    warnings: list[str],
):
    """标记上传文件已成功解析并加入 RAG 索引。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "indexed"
    document.document_count = document_count
    document.chunk_count = chunk_count
    if file_sha256 is not None:
        document.file_sha256 = file_sha256
    document.warnings = warnings
    document.error_message = None

    db.commit()
    db.refresh(document)

    return document


def mark_uploaded_document_failed(db: Session, document_id: int, *, error_message: str):
    """标记上传文件解析或入库失败，并保存失败原因。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return None

    document.status = "failed"
    document.error_message = error_message

    db.commit()
    db.refresh(document)

    return document


def fail_interrupted_uploaded_documents(db: Session) -> int:
    """服务重启后，将无法继续执行的后台上传任务标记为失败。"""

    interrupted_count = (
        db.query(models.UploadedDocument)
        .filter(models.UploadedDocument.status.in_(INTERRUPTED_DOCUMENT_STATUSES))
        .update(
            {
                models.UploadedDocument.status: "failed",
                models.UploadedDocument.error_message: (
                    "服务重启导致后台处理任务中断，请删除后重新上传"
                ),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return interrupted_count


def get_uploaded_document(db: Session, document_id: int):
    """按 ID 查询上传文件记录。"""

    return db.query(models.UploadedDocument).filter(models.UploadedDocument.id == document_id).first()


def get_uploaded_document_by_name_hash(
    db: Session,
    *,
    original_filename: str,
    file_sha256: str,
):
    """查询是否已存在同名且内容完全相同的上传文件。"""

    return (
        db.query(models.UploadedDocument)
        .filter(models.UploadedDocument.original_filename == original_filename)
        .filter(models.UploadedDocument.file_sha256 == file_sha256)
        .first()
    )


def list_uploaded_documents(db: Session, skip: int = 0, limit: int = 20):
    """按创建时间倒序查询上传文件记录。"""

    return (
        db.query(models.UploadedDocument)
        .order_by(models.UploadedDocument.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_uploaded_document(db: Session, document_id: int) -> bool:
    """删除上传文档记录；记录不存在时返回 False。"""

    document = get_uploaded_document(db, document_id)
    if document is None:
        return False

    db.delete(document)
    db.commit()
    return True


def create_chat_session(db: Session, *, title: str | None = None, mode: str = "chat"):
    """创建一个多轮对话会话。"""

    session = models.ChatSession(title=title, mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_chat_session(db: Session, session_id: int, *, include_deleted: bool = False):
    """按 ID 查询会话，默认排除已软删除的记录。"""

    query = db.query(models.ChatSession).filter(models.ChatSession.id == session_id)
    if not include_deleted:
        query = query.filter(models.ChatSession.deleted_at.is_(None))
    return query.first()


def delete_chat_session(db: Session, session_id: int) -> bool:
    """软删除会话并保留关联消息；会话不存在时返回 False。"""

    session = get_chat_session(db, session_id)
    if session is None:
        return False

    session.deleted_at = func.now()
    db.commit()
    return True


def get_or_create_chat_session(
    db: Session,
    *,
    session_id: int | None = None,
    title: str | None = None,
    mode: str = "chat",
):
    """传入 session_id 时复用会话；未传入时创建新会话。"""

    if session_id is not None:
        return get_chat_session(db, session_id)

    return create_chat_session(db, title=title, mode=mode)


def list_chat_sessions(db: Session, skip: int = 0, limit: int = 20):
    """按最近消息时间倒序查询会话列表。"""

    return (
        db.query(models.ChatSession)
        .filter(models.ChatSession.deleted_at.is_(None))
        .order_by(
            models.ChatSession.last_message_at.desc().nullslast(),
            models.ChatSession.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_chat_message(
    db: Session,
    *,
    session_id: int,
    role: str,
    content: str,
    message_metadata: dict | None = None,
):
    """保存一条会话消息，并刷新会话最近消息时间。"""

    message = models.ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        message_metadata=message_metadata or {},
    )
    db.add(message)

    session = get_chat_session(db, session_id)
    if session is not None:
        session.last_message_at = func.now()

    db.commit()
    db.refresh(message)

    return message


def list_chat_messages(db: Session, session_id: int, skip: int = 0, limit: int = 50):
    """按时间正序查询会话消息。"""

    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc(), models.ChatMessage.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_recent_chat_messages(db: Session, session_id: int, limit: int = 10):
    """获取最近 N 条消息，并按时间正序返回。"""

    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(messages))


def get_system_setting(db: Session, key: str):
    """按 key 查询系统配置。"""
    return db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()


def list_system_settings(db: Session, category: str | None = None):
    """查询系统配置列表，可按分类筛选。"""
    query = db.query(models.SystemSetting)

    if category is not None:
        query = query.filter(models.SystemSetting.category == category)

    return query.order_by(models.SystemSetting.category, models.SystemSetting.key).all()


def upsert_system_setting(
    db: Session,
    *,
    key: str,
    value: str,
    category: str,
    is_encrypted: bool = False,
    description: str | None = None,
):
    """创建或更新系统配置。"""
    setting = get_system_setting(db, key)

    if setting is None:
        setting = models.SystemSetting(
            key=key,
            value=value,
            category=category,
            is_encrypted=is_encrypted,
            description=description,
        )
        db.add(setting)
    else:
        setting.value = value
        setting.category = category
        setting.is_encrypted = is_encrypted
        if description is not None:
            setting.description = description

    db.commit()
    db.refresh(setting)
    return setting


def delete_system_setting(db: Session, key: str) -> bool:
    """删除系统配置；配置不存在时返回 False。"""
    setting = get_system_setting(db, key)

    if setting is None:
        return False

    db.delete(setting)
    db.commit()
    return True


def get_user_by_username(db: Session, username: str):
    """按用户名查询用户。"""
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str):
    """按邮箱查询用户。"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: int):
    """按 ID 查询用户。"""
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    email: str | None = None,
    role: str = "user",
):
    """创建用户。"""
    user = models.User(
        username=username,
        password_hash=password_hash,
        email=email,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def count_users(db: Session) -> int:
    """统计用户数量。"""
    return db.query(models.User).count()
