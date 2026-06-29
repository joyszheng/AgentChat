from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.main import app
from app.routers import ai as ai_router

client = TestClient(app)


def test_ai_chat():
    response = client.post(
        "/ai/chat",
        json={"message": "请用一句话介绍 FastAPI"},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data["answer"], str)
    assert data["answer"]


def test_tasks_assistant_query():
    response = client.post(
        "/ai/tasks-assistant",
        json={"message": "查询前 3 条未完成任务"},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data["answer"], str)
    assert data["answer"]


def test_rag_answer():
    response = client.post(
        "/ai/rag",
        json={"question": "AgentChat 项目的内部代号是什么？"},
    )

    assert response.status_code == 200

    data = response.json()
    assert "萤火虫 8868" in data["answer"]
    assert isinstance(data["sources"], list)
    assert data["sources"]

def test_chat_rejects_empty_message():
    response = client.post(
        "/ai/chat",
        json={"message": ""},
    )

    assert response.status_code == 422


def test_rag_rejects_empty_question():
    response = client.post(
        "/ai/rag",
        json={"question": ""},
    )

    assert response.status_code == 422

def test_chat_returns_500_when_model_fails(monkeypatch):
    def raise_model_error(_input):
        raise RuntimeError("模拟模型故障")

    fake_chain = SimpleNamespace(invoke=raise_model_error)
    monkeypatch.setattr(ai_router, "chat_chain", fake_chain)

    response = client.post(
        "/ai/chat",
        json={"message": "你好"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "AI 服务暂时不可用，请稍后重试"
    }

def test_tasks_assistant_returns_500_when_agent_fails(monkeypatch):
    def raise_agent_error(_input):
        raise RuntimeError("模拟 Agent 故障")

    fake_agent = SimpleNamespace(invoke=raise_agent_error)
    monkeypatch.setattr(ai_router, "task_agent", fake_agent)

    response = client.post(
        "/ai/tasks-assistant",
        json={"message": "查询未完成任务"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "任务助手暂时不可用，请稍后再试"
    }

def test_rag_returns_500_when_service_fails(monkeypatch):
    def raise_rag_error(_question):
        raise RuntimeError("模拟 RAG 故障")

    monkeypatch.setattr(ai_router, "ask_document", raise_rag_error)

    response = client.post(
        "/ai/rag",
        json={"question": "内部代号是什么？"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "文档问答服务暂时不可用"
    }