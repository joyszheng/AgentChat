import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app import crud
from app.database import SessionLocal
from app.main import app
from app.services import task_executor
from app.services.auth import create_access_token, get_password_hash

client = TestClient(app)


def _auth_headers(username: str = "task-user"):
    with SessionLocal() as db:
        user = crud.get_user_by_username(db, username)
        if user is None:
            user = crud.create_user(
                db,
                username=username,
                password_hash=get_password_hash("task-password"),
                role="user",
            )
        token = create_access_token({"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


def _future_schedule_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()


def _mark_task_due(task_id: int) -> datetime:
    due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task is not None
        task.schedule_at = due_at
        task.next_run_at = due_at
        task.run_status = "pending"
        db.commit()
    return due_at


def _aware(value: datetime) -> datetime:
    """SQLite 读回的 datetime 是 naive 的，统一按 UTC 处理以便比较。"""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def test_read_root():
    """根路径应能作为服务存活检查使用。"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


def test_create_task():
    """创建任务后应返回生成的 ID 和原始字段。"""
    response = client.post(
        "/tasks",
        headers=_auth_headers(),
        json={
            "title": "测试任务",
            "description": "用TestClient创建的测试任务",
            "completed": False,
            "priority": "high",
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "测试任务"
    assert data["description"] == "用TestClient创建的测试任务"
    assert data["completed"] is False
    assert data["status"] == "todo"
    assert data["priority"] == "high"
    assert data["user_id"] is not None
    assert "id" in data  # 确认返回的数据中包含任务 ID。


def test_get_not_found_task():
    """查询不存在的任务应返回 404。"""

    response = client.get(
        "/tasks/9999",
        headers=_auth_headers(),
    )  # 使用远大于测试数据量的 ID。
    assert response.status_code == 404
    assert response.json() == {"detail": "任务不存在"}


def test_list_update_and_delete_own_tasks():
    """任务列表、局部更新和删除应只作用于当前登录用户的数据。"""

    headers = _auth_headers("task-owner")
    other_headers = _auth_headers("task-other")

    own_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "整理任务模块",
            "description": "补充筛选和状态",
            "priority": "urgent",
        },
    )
    other_response = client.post(
        "/tasks",
        headers=other_headers,
        json={"title": "其他用户任务"},
    )
    assert own_response.status_code == 201
    assert other_response.status_code == 201
    task_id = own_response.json()["id"]

    list_response = client.get(
        "/tasks?status=todo&priority=urgent&search=任务模块",
        headers=headers,
    )
    assert list_response.status_code == 200
    tasks = list_response.json()
    assert [task["id"] for task in tasks] == [task_id]

    isolated_response = client.get(f"/tasks/{other_response.json()['id']}", headers=headers)
    assert isolated_response.status_code == 404

    update_response = client.patch(
        f"/tasks/{task_id}",
        headers=headers,
        json={"status": "done"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["completed"] is True
    assert update_response.json()["status"] == "done"

    delete_response = client.delete(f"/tasks/{task_id}", headers=headers)
    assert delete_response.status_code == 204


def test_tasks_require_login():
    response = client.get("/tasks")

    assert response.status_code == 401


def test_due_ai_task_is_enqueued(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.jobs = []

        async def enqueue_job(self, name, task_id, _job_id=None):
            self.jobs.append((name, task_id, _job_id))
            return SimpleNamespace(job_id=_job_id)

    monkeypatch.setattr(task_executor, "SCHEDULER_BATCH_SIZE", 100)
    headers = _auth_headers("ai-queue-owner")
    schedule_at = _future_schedule_at()

    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "队列执行测试",
            "execution_mode": "ai_auto",
            "schedule_at": schedule_at,
            "recurrence_rule": "none",
            "ai_prompt": "确认任务会进入后台队列。",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    _mark_task_due(task_id)

    fake_redis = FakeRedis()
    queued_count = asyncio.run(task_executor.enqueue_due_ai_tasks(fake_redis))

    assert queued_count >= 1
    assert any(job[0] == "execute_ai_task_job" and job[1] == task_id for job in fake_redis.jobs)
    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task is not None
        assert task.run_status == "queued"
        assert task.run_count == 0


def test_list_tasks_allows_existing_past_ai_schedule():
    headers = _auth_headers("ai-past-list-owner")
    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "已到期自动任务列表回归",
            "execution_mode": "ai_auto",
            "schedule_at": _future_schedule_at(),
            "recurrence_rule": "none",
            "ai_prompt": "用于验证旧任务列表不会因为过去执行时间报错。",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    _mark_task_due(task_id)

    list_response = client.get("/tasks?limit=100", headers=headers)

    assert list_response.status_code == 200
    assert any(task["id"] == task_id for task in list_response.json())


def test_cleanup_stale_ai_task_jobs(monkeypatch):
    class FakeRedis:
        def __init__(self, jobs):
            self._jobs = jobs
            self.deleted = []

        async def queued_jobs(self, *, queue_name=None):
            return self._jobs

        async def zrem(self, queue_name, job_id):
            self.deleted.append(("zrem", queue_name, job_id))

        async def delete(self, key):
            self.deleted.append(("delete", key))

    headers = _auth_headers("ai-cleanup-owner")
    schedule_at = _future_schedule_at()
    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "清理旧队列任务",
            "execution_mode": "ai_auto",
            "schedule_at": schedule_at,
            "recurrence_rule": "none",
            "ai_prompt": "验证 Redis 旧任务清理。",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task is not None
        expected_job_id = task_executor.build_task_job_id(task.id, task.next_run_at)

    stale_job_id = f"ai-task:{task_id}:2020-01-01T00:00:00+00:00"
    fake_redis = FakeRedis([
        SimpleNamespace(job_id=expected_job_id),
        SimpleNamespace(job_id=stale_job_id),
        SimpleNamespace(job_id="some-other-job"),
    ])

    async def fake_create_pool():
        return fake_redis

    monkeypatch.setattr(task_executor, "create_task_queue_pool", fake_create_pool)

    removed_count = asyncio.run(task_executor.cleanup_stale_ai_task_jobs())

    assert removed_count == 1
    assert ("zrem", "arq:queue", stale_job_id) in fake_redis.deleted
    assert ("delete", f"arq:job:{stale_job_id}") in fake_redis.deleted
    assert all(expected_job_id not in item for item in fake_redis.deleted)


def test_ai_auto_task_executes_and_records_run(monkeypatch):
    """AI 自动任务应能执行、发送通知并保存执行记录。"""

    async def fake_send_email(*args, **kwargs):
        return True

    async def fake_agent(_snapshot):
        return "今日任务总结：优先处理紧急事项。", ["amap_maps_weather"]

    monkeypatch.setattr(task_executor, "_run_task_agent", fake_agent)
    monkeypatch.setattr(task_executor, "send_email", fake_send_email)

    headers = _auth_headers("ai-auto-owner")
    schedule_at = _future_schedule_at()

    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "每日任务总结",
            "description": "由 AI 定时汇总",
            "execution_mode": "ai_auto",
            "schedule_at": schedule_at,
            "recurrence_rule": "none",
            "ai_prompt": "总结当前未完成任务，并给出下一步建议。",
            "notify_email": "owner@example.com",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    _mark_task_due(task_id)

    asyncio.run(task_executor.execute_ai_task(task_id))

    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task is not None
        assert task.run_count == 1
        assert task.run_status == "success"
        assert task.status == "done"

    runs_response = client.get(f"/tasks/{task_id}/runs", headers=headers)
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["email_sent"] is True
    assert "今日任务总结" in runs[0]["output"]
    # 记录 agent 实际用到的工具 + 邮件动作
    assert "amap_maps_weather" in runs[0]["tools_used"]
    assert "email" in runs[0]["tools_used"]


def test_ai_auto_task_uses_email_from_prompt(monkeypatch):
    sent_email = {}
    captured = {}

    async def fake_send_email(to, subject, body, **kwargs):
        sent_email["to"] = to
        sent_email["subject"] = subject
        sent_email["body"] = body
        return True

    async def fake_agent(snapshot):
        captured["snapshot"] = snapshot
        return "今日天气摘要：请携带雨具，注意通勤时间。", ["amap_maps_weather"]

    monkeypatch.setattr(task_executor, "_run_task_agent", fake_agent)
    monkeypatch.setattr(task_executor, "send_email", fake_send_email)

    headers = _auth_headers("ai-prompt-email-owner")
    schedule_at = _future_schedule_at()

    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "天气邮件",
            "execution_mode": "ai_auto",
            "schedule_at": schedule_at,
            "recurrence_rule": "none",
            "ai_prompt": "请整理今天上海天气，并发送到 weather.owner@example.com。",
        },
    )
    assert create_response.status_code == 201

    task_id = create_response.json()["id"]
    _mark_task_due(task_id)
    asyncio.run(task_executor.execute_ai_task(task_id))

    assert sent_email["to"] == ["weather.owner@example.com"]
    assert sent_email["subject"] == "【AgentChat】天气邮件"
    assert "今日天气摘要" in sent_email["body"]
    assert "AI 定时任务已执行完成" not in sent_email["body"]
    # 从执行说明里解析出的收件邮箱应进入任务快照与 agent 输入
    assert captured["snapshot"]["recipient_emails"] == ["weather.owner@example.com"]
    task_input = task_executor._build_task_input(captured["snapshot"])
    assert "邮件收件人：weather.owner@example.com" in task_input


def test_ai_auto_task_email_failure_does_not_fail_run(monkeypatch):
    """邮件发送失败不再判 run 失败，也不影响结果与后续调度。"""

    async def fake_send_email(*args, **kwargs):
        return False

    async def fake_agent(_snapshot):
        return "天气结果已生成。", []

    monkeypatch.setattr(task_executor, "_run_task_agent", fake_agent)
    monkeypatch.setattr(task_executor, "send_email", fake_send_email)

    headers = _auth_headers("ai-email-failure-owner")
    schedule_at = _future_schedule_at()

    create_response = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "邮件失败测试",
            "execution_mode": "ai_auto",
            "schedule_at": schedule_at,
            "recurrence_rule": "none",
            "ai_prompt": "生成结果并发送邮件。",
            "notify_email": "owner@example.com",
        },
    )
    assert create_response.status_code == 201

    task_id = create_response.json()["id"]
    _mark_task_due(task_id)
    asyncio.run(task_executor.execute_ai_task(task_id))

    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task is not None
        # 生成成功即成功；一次性任务照常完成，邮件失败仅作提示。
        assert task.run_status == "success"
        assert task.status == "done"
        assert task.run_error == "AI 结果已生成，但邮件发送失败"

    runs_response = client.get(f"/tasks/{task_id}/runs", headers=headers)
    assert runs_response.status_code == 200
    run = runs_response.json()[0]
    assert run["status"] == "success"
    assert run["output"] == "天气结果已生成。"
    assert run["email_sent"] is False


def test_reset_stuck_ai_tasks_recovers_running_and_queued():
    """崩溃/丢 job 后卡死的 running/queued 应被 reaper 复位为 pending。"""

    headers = _auth_headers("reaper-owner")

    def _make(title):
        resp = client.post(
            "/tasks",
            headers=headers,
            json={
                "title": title,
                "execution_mode": "ai_auto",
                "schedule_at": _future_schedule_at(),
                "recurrence_rule": "none",
                "ai_prompt": "保持在队列/执行中以验证 reaper。",
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    running_id = _make("卡死执行中")
    queued_id = _make("卡死排队中")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        running = crud.get_task(db, running_id)
        running.next_run_at = now - timedelta(minutes=5)
        running.run_status = "running"
        running.run_started_at = now - timedelta(hours=1)
        dangling = crud.models.TaskRun(
            task_id=running.id,
            user_id=running.user_id,
            status="running",
            input_snapshot={},
        )
        db.add(dangling)

        queued = crud.get_task(db, queued_id)
        queued.next_run_at = now - timedelta(minutes=5)
        queued.run_status = "queued"
        db.commit()
        dangling_id = dangling.id
        # onupdate 只填未显式赋值的列，这里显式把 updated_at 压到过去。
        db.query(crud.models.Task).filter(crud.models.Task.id == queued_id).update(
            {crud.models.Task.updated_at: now - timedelta(hours=1)}
        )
        db.commit()

    with SessionLocal() as db:
        recovered = crud.reset_stuck_ai_tasks(
            db,
            now=now,
            running_timeout=timedelta(minutes=15),
            queued_timeout=timedelta(minutes=30),
        )

    assert recovered >= 2
    with SessionLocal() as db:
        running = crud.get_task(db, running_id)
        assert running.run_status == "pending"
        assert running.run_started_at is None
        assert running.run_error is not None

        queued = crud.get_task(db, queued_id)
        assert queued.run_status == "pending"

        dangling = db.get(crud.models.TaskRun, dangling_id)
        assert dangling.status == "failed"
        assert dangling.finished_at is not None


def test_retryable_generation_failure_retries_then_preserves_daily(monkeypatch):
    """可重试错误应退避重试，耗尽后每日任务保住重复而非死亡。"""

    async def timing_out(_snapshot):
        raise TimeoutError("upstream timed out")

    monkeypatch.setattr(task_executor, "_run_task_agent", timing_out)

    headers = _auth_headers("retry-owner")
    resp = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "每日任务重试",
            "execution_mode": "ai_auto",
            "schedule_at": _future_schedule_at(),
            "recurrence_rule": "daily",
            "ai_prompt": "生成每日总结。",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    due = _mark_task_due(task_id)
    asyncio.run(task_executor.execute_ai_task(task_id))

    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task.run_status == "pending"       # 排定重试，未死亡
        assert task.retry_count == 1
        assert task.next_run_at is not None
        assert _aware(task.next_run_at) > due     # 退避到未来
        assert task.run_count == 1

    # 持续失败直到耗尽重试次数。
    for _ in range(crud.TASK_MAX_RETRIES):
        _mark_task_due(task_id)
        asyncio.run(task_executor.execute_ai_task(task_id))

    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task.retry_count == 0
        assert task.run_status == "failed"
        # 每日重复保住：仍排定了下一次执行，而不是被清空。
        assert task.next_run_at is not None
        assert _aware(task.next_run_at) > datetime.now(timezone.utc)


def test_non_retryable_generation_failure_does_not_retry(monkeypatch):
    """不可重试错误不应重试；一次性任务失败即终止。"""

    async def bad_value(_snapshot):
        raise ValueError("deterministic failure")

    monkeypatch.setattr(task_executor, "_run_task_agent", bad_value)

    headers = _auth_headers("no-retry-owner")
    resp = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "一次性不可重试",
            "execution_mode": "ai_auto",
            "schedule_at": _future_schedule_at(),
            "recurrence_rule": "none",
            "ai_prompt": "生成结果。",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]
    _mark_task_due(task_id)
    asyncio.run(task_executor.execute_ai_task(task_id))

    with SessionLocal() as db:
        task = crud.get_task(db, task_id)
        assert task.run_status == "failed"
        assert task.retry_count == 0
        assert task.next_run_at is None           # 一次性任务：不重试即终止
