import importlib
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


def _load_main_with_fake_rag(monkeypatch, tmp_path):
    fake_rag = ModuleType("app.ai.rag")
    fake_rag.ask_document = lambda _question: ("", [])
    fake_rag.ingest_upload = lambda *_args, **_kwargs: (None, 0)

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
