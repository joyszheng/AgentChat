import importlib
import json
import sys
from types import ModuleType, SimpleNamespace

from fastapi.testclient import TestClient


def test_chat_persists_session_messages_and_uses_recent_history(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    ai_router = importlib.import_module("app.routers.ai")
    prompts = []

    def fake_invoke(input_data):
        prompts.append(input_data["message"])
        return SimpleNamespace(content=f"回答 {len(prompts)}")

    fake_chain = SimpleNamespace(invoke=fake_invoke)
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)
    monkeypatch.setattr(main_module.ai, "chat_chain", fake_chain)

    client = TestClient(main_module.app)

    first_response = client.post("/ai/chat", json={"message": "我的项目叫 AgentChat"})
    assert first_response.status_code == 200
    first_data = first_response.json()
    assert first_data["answer"] == "回答 1"
    assert isinstance(first_data["session_id"], int)

    second_response = client.post(
        "/ai/chat",
        json={
            "session_id": first_data["session_id"],
            "message": "我刚才说项目叫什么？",
        },
    )
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["session_id"] == first_data["session_id"]
    assert second_data["answer"] == "回答 2"
    assert "用户：我的项目叫 AgentChat" in prompts[1]
    assert "助手：回答 1" in prompts[1]

    messages_response = client.get(f"/ai/sessions/{first_data['session_id']}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "我的项目叫 AgentChat"
    assert messages[-1]["content"] == "回答 2"


def test_delete_chat_session_cascades_messages(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    ai_router = importlib.import_module("app.routers.ai")
    database = importlib.import_module("app.database")
    models = importlib.import_module("app.models")

    fake_chain = SimpleNamespace(
        invoke=lambda _input_data: SimpleNamespace(content="待删除回答")
    )
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)
    monkeypatch.setattr(main_module.ai, "chat_chain", fake_chain)

    client = TestClient(main_module.app)
    chat_response = client.post("/ai/chat", json={"message": "创建待删除会话"})
    session_id = chat_response.json()["session_id"]

    delete_response = client.delete(f"/ai/sessions/{session_id}")

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert client.get(f"/ai/sessions/{session_id}/messages").status_code == 404
    assert client.delete(f"/ai/sessions/{session_id}").status_code == 404

    with database.SessionLocal() as db:
        message_count = (
            db.query(models.ChatMessage)
            .filter(models.ChatMessage.session_id == session_id)
            .count()
        )
    assert message_count == 0


def test_chat_stream_emits_sse_and_persists_complete_answer(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    ai_router = importlib.import_module("app.routers.ai")
    prompts = []

    async def fake_astream(input_data):
        prompts.append(input_data["message"])
        yield SimpleNamespace(content="你好")
        yield SimpleNamespace(content=[{"type": "text", "text": "，世界"}])

    fake_chain = SimpleNamespace(astream=fake_astream)
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)
    monkeypatch.setattr(main_module.ai, "chat_chain", fake_chain)

    client = TestClient(main_module.app)
    response = client.post("/ai/chat/stream", json={"message": "流式回答我"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["start", "token", "token", "done"]
    assert events[1]["data"] == {"delta": "你好"}
    assert events[2]["data"] == {"delta": "，世界"}
    assert events[0]["data"]["session_id"] == events[-1]["data"]["session_id"]
    assert isinstance(events[-1]["data"]["assistant_message_id"], int)
    assert "当前用户问题：\n流式回答我" in prompts[0]

    session_id = events[0]["data"]["session_id"]
    messages_response = client.get(f"/ai/sessions/{session_id}/messages")
    messages = messages_response.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "你好，世界"
    assert messages[-1]["message_metadata"] == {"model": "chat", "streamed": True}


def test_chat_stream_emits_error_without_persisting_partial_answer(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    ai_router = importlib.import_module("app.routers.ai")

    async def failing_astream(_input_data):
        yield SimpleNamespace(content="未完成")
        raise RuntimeError("模拟流式模型故障")

    fake_chain = SimpleNamespace(astream=failing_astream)
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)
    monkeypatch.setattr(main_module.ai, "chat_chain", fake_chain)

    client = TestClient(main_module.app)
    response = client.post("/ai/chat/stream", json={"message": "触发错误"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["start", "token", "error"]
    assert events[-1]["data"] == {
        "code": "ai_service_unavailable",
        "message": "AI 服务暂时不可用，请稍后重试",
    }

    session_id = events[0]["data"]["session_id"]
    messages = client.get(f"/ai/sessions/{session_id}/messages").json()
    assert [message["role"] for message in messages] == ["user"]


def test_chat_stream_falls_back_when_follow_up_returns_no_chunks(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    ai_router = importlib.import_module("app.routers.ai")
    stream_calls = 0
    fallback_prompts = []

    async def fake_astream(_input_data):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            yield SimpleNamespace(content="第一轮回答")
            return

        raise ValueError("No generation chunks were returned")

    async def fake_ainvoke(input_data):
        fallback_prompts.append(input_data["message"])
        return SimpleNamespace(content="第二轮兜底回答")

    fake_chain = SimpleNamespace(astream=fake_astream, ainvoke=fake_ainvoke)
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)
    monkeypatch.setattr(main_module.ai, "chat_chain", fake_chain)

    client = TestClient(main_module.app)
    first_response = client.post("/ai/chat/stream", json={"message": "第一轮问题"})
    first_events = _parse_sse_events(first_response.text)
    session_id = first_events[0]["data"]["session_id"]

    second_response = client.post(
        "/ai/chat/stream",
        json={"session_id": session_id, "message": "第二轮问题"},
    )
    second_events = _parse_sse_events(second_response.text)

    assert second_response.status_code == 200
    assert [event["event"] for event in second_events] == ["start", "token", "done"]
    assert second_events[1]["data"] == {"delta": "第二轮兜底回答"}
    assert "用户：第一轮问题" in fallback_prompts[0]
    assert "助手：第一轮回答" in fallback_prompts[0]
    assert "当前用户问题：\n第二轮问题" in fallback_prompts[0]

    messages = client.get(f"/ai/sessions/{session_id}/messages").json()
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert messages[-1]["content"] == "第二轮兜底回答"


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for raw_event in body.strip().split("\n\n"):
        lines = raw_event.splitlines()
        event_name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append({"event": event_name, "data": json.loads(data)})
    return events


def _load_main_with_fake_rag(monkeypatch, tmp_path):
    fake_rag = ModuleType("app.ai.rag")
    fake_rag.ask_document = lambda _question: ("", [])
    fake_rag.ingest_upload = lambda *_args, **_kwargs: (None, 0)
    fake_rag.delete_document_from_index = lambda **_kwargs: 0

    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GLM_API_KEY", "test-api-key")
    monkeypatch.setitem(sys.modules, "app.ai.rag", fake_rag)
    sys.modules.pop("app.crud", None)
    sys.modules.pop("app.database", None)
    sys.modules.pop("app.ai.models", None)
    sys.modules.pop("app.models", None)
    sys.modules.pop("app.routers.ai", None)
    sys.modules.pop("app.main", None)

    return importlib.import_module("app.main")
