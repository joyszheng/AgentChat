import asyncio

from fastapi.testclient import TestClient
from types import SimpleNamespace

from app import crud
from app.ai import rag
from app.ai import orchestrator
from app.ai.orchestrator import AssistantResult, AssistantStreamEvent
from app.database import SessionLocal
from app.main import app
from app.routers import ai as ai_router
from app.services.auth import create_access_token, get_password_hash

client = TestClient(app)


def _auth_headers(username: str = "ai-task-user"):
    with SessionLocal() as db:
        user = crud.get_user_by_username(db, username)
        if user is None:
            user = crud.create_user(
                db,
                username=username,
                password_hash=get_password_hash("ai-task-password"),
                role="user",
            )
        token = create_access_token({"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


def test_ai_chat(monkeypatch):
    fake_chain = SimpleNamespace(
        invoke=lambda _input: SimpleNamespace(content="FastAPI 是现代 Python Web 框架。")
    )
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "create_chat_chain", lambda _llm: fake_chain)

    response = client.post(
        "/ai/chat",
        json={"message": "[TEST] 请用一句话介绍 FastAPI"},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data["answer"], str)
    assert data["answer"]


def test_tasks_assistant_query(monkeypatch):
    fake_agent = SimpleNamespace(
        invoke=lambda _input: {
            "messages": [
                SimpleNamespace(content="前 3 条未完成任务如下。"),
            ]
        }
    )
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "create_task_agent", lambda _llm, **_kwargs: fake_agent)

    response = client.post(
        "/ai/tasks-assistant",
        headers=_auth_headers(),
        json={"message": "[TEST] 查询前 3 条未完成任务"},
    )

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data["answer"], str)
    assert data["answer"]


def test_rag_answer(monkeypatch):
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "get_embeddings_from_config", lambda _db: object())
    monkeypatch.setattr(
        ai_router,
        "ask_document",
        lambda *_args, **_kwargs: ("项目内部代号是萤火虫 8868。", ["guide.md"]),
    )

    response = client.post(
        "/ai/rag",
        json={"question": "[TEST] AgentChat 项目的内部代号是什么？"},
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
    monkeypatch.setattr(ai_router, "create_chat_chain", lambda _llm: fake_chain)

    response = client.post(
        "/ai/chat",
        json={"message": "[TEST] 你好"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "AI 服务暂时不可用，请稍后重试"
    }

def test_tasks_assistant_returns_500_when_agent_fails(monkeypatch):
    def raise_agent_error(_input):
        raise RuntimeError("模拟 Agent 故障")

    fake_agent = SimpleNamespace(invoke=raise_agent_error)
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "create_task_agent", lambda _llm, **_kwargs: fake_agent)

    response = client.post(
        "/ai/tasks-assistant",
        headers=_auth_headers("ai-task-failure-user"),
        json={"message": "[TEST] 查询未完成任务"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "任务助手暂时不可用，请稍后再试"
    }

def test_rag_returns_500_when_service_fails(monkeypatch):
    def raise_rag_error(_question, *, llm, embedding_function):
        raise RuntimeError("模拟 RAG 故障")

    monkeypatch.setattr(ai_router, "ask_document", raise_rag_error)

    response = client.post(
        "/ai/rag",
        json={"question": "[TEST] 内部代号是什么？"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "文档问答服务暂时不可用"
    }


def test_unified_assistant_persists_route_sources_and_tools(monkeypatch):
    async def fake_run_unified_assistant(**kwargs):
        assert kwargs["model_input"]
        assert kwargs["mcp_tools"] == []
        return SimpleNamespace(
            answer="统一助手回答",
            route="rag+mcp",
            sources=["guide.md"],
            tools_used=["search_knowledge_base", "demo__echo"],
        )

    monkeypatch.setattr(ai_router, "run_unified_assistant", fake_run_unified_assistant)
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "get_embeddings_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router.mcp_registry, "get_tools", lambda **_kwargs: [])

    response = client.post(
        "/ai/assistant",
        json={"message": "[TEST] 需要自动选择工具"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "统一助手回答"
    assert data["route"] == "rag+mcp"
    assert data["sources"] == ["guide.md"]
    assert data["tools_used"] == ["search_knowledge_base", "demo__echo"]

    messages_response = client.get(f"/ai/sessions/{data['session_id']}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[-1]["content"] == "统一助手回答"
    assert messages[-1]["message_metadata"] == {
        "model": "assistant",
        "route": "rag+mcp",
        "sources": ["guide.md"],
        "tools_used": ["search_knowledge_base", "demo__echo"],
    }


def test_unified_assistant_streams_and_persists_metadata(monkeypatch):
    async def fake_stream_unified_assistant(**kwargs):
        assert kwargs["model_input"]
        yield AssistantStreamEvent(delta="统一助手")
        yield AssistantStreamEvent(progress="正在处理任务工具...")
        yield AssistantStreamEvent(delta="流式回答")
        yield AssistantStreamEvent(
            result=AssistantResult(
                answer="统一助手流式回答",
                route="task",
                sources=[],
                tools_used=["list_uncompleted_tasks"],
            )
        )

    monkeypatch.setattr(ai_router, "stream_unified_assistant", fake_stream_unified_assistant)
    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router, "get_embeddings_from_config", lambda _db: object())
    monkeypatch.setattr(ai_router.mcp_registry, "get_tools", lambda **_kwargs: [])

    response = client.post(
        "/ai/assistant/stream",
        json={"message": "[TEST] 流式智能助手"},
    )

    assert response.status_code == 200
    body = response.text
    assert "event: start" in body
    assert "event: metadata" in body
    assert '"route":"task"' in body
    assert "event: token" in body
    assert "event: progress" in body
    assert '"message":"正在处理任务工具..."' in body
    assert '"delta":"统一助手"' in body
    assert '"delta":"流式回答"' in body
    assert "event: done" in body

    done_line = next(line for line in body.splitlines() if '"session_id":' in line and '"assistant_message_id":' in line)
    session_id = int(done_line.split('"session_id":', 1)[1].split(",", 1)[0])
    messages_response = client.get(f"/ai/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[-1]["content"] == "统一助手流式回答"
    assert messages[-1]["message_metadata"] == {
        "model": "assistant",
        "streamed": True,
        "route": "task",
        "sources": [],
        "tools_used": ["list_uncompleted_tasks"],
    }


def test_default_document_indexing_skips_existing_vectors(monkeypatch):
    indexed = []

    monkeypatch.setattr(rag, "default_documents_indexed", False)
    monkeypatch.setattr(rag, "get_vector_store", lambda _embedding: object())
    monkeypatch.setattr(rag, "_vector_ids_exist", lambda _ids, **_kwargs: True)
    monkeypatch.setattr(
        rag,
        "_upsert_documents",
        lambda *_args, **_kwargs: indexed.append("upsert"),
    )

    rag.ensure_default_documents_indexed(embedding_function=object())

    assert rag.default_documents_indexed is True
    assert indexed == []


def test_unified_assistant_stream_filters_tool_call_intermediate_output(monkeypatch):
    class FakeAgent:
        async def astream(self, *_args, **_kwargs):
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(
                        type="ai",
                        content='{"city":"武汉市"}',
                        tool_call_chunks=[{"name": "map_tool__maps_weather"}],
                    ),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content='{"city":"武汉市"}',
                            tool_calls=[{"name": "search_knowledge_base"}],
                        ),
                    ],
                },
            }
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(type="ai", content="武汉今天小雨转多云。"),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content="武汉今天小雨转多云。",
                        ),
                    ],
                },
            }

    monkeypatch.setattr(orchestrator, "create_unified_agent", lambda *_args, **_kwargs: FakeAgent())
    monkeypatch.setattr(orchestrator, "create_task_tools", lambda **_kwargs: [])

    async def collect_events():
        events = []
        async for event in orchestrator.stream_unified_assistant(
            llm=object(),
            model_input="介绍武汉",
            embedding_function=object(),
            mcp_tools=[],
        ):
            events.append(event)
        return events

    events = asyncio.run(collect_events())
    deltas = [event.delta for event in events if event.delta]
    progress_messages = [event.progress for event in events if event.progress]

    assert deltas == ["武汉今天小雨转多云。"]
    assert progress_messages == ["正在检索知识库...", "工具调用完成"]
    assert events[-1].result is not None
    assert events[-1].result.answer == "武汉今天小雨转多云。"


def test_unified_assistant_stream_sanitizes_mcp_raw_payload(monkeypatch):
    tool_name = "map_tool__maps_weather"

    class FakeAgent:
        async def astream(self, *_args, **_kwargs):
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(
                        type="ai",
                        content='{"city":"武汉市"}',
                        tool_call_chunks=[{"name": tool_name}],
                    ),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content="",
                            tool_calls=[{"name": tool_name}],
                        ),
                    ],
                },
            }
            final = '{"city":"武汉市","forecasts":[{"dayweather":"小雨"}]}\n武汉今天小雨，气温偏高。'
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(type="ai", content=final),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content=final,
                            tool_calls=[{"name": tool_name}],
                        ),
                    ],
                },
            }

    monkeypatch.setattr(orchestrator, "create_unified_agent", lambda *_args, **_kwargs: FakeAgent())
    monkeypatch.setattr(orchestrator, "create_task_tools", lambda **_kwargs: [])

    async def collect_events():
        events = []
        async for event in orchestrator.stream_unified_assistant(
            llm=object(),
            model_input="介绍武汉天气",
            embedding_function=object(),
            mcp_tools=[SimpleNamespace(name=tool_name)],
        ):
            events.append(event)
        return events

    events = asyncio.run(collect_events())
    streamed_text = "".join(event.delta or "" for event in events)

    assert '"city"' not in streamed_text
    assert "forecasts" not in streamed_text
    assert "武汉今天小雨，气温偏高。" in streamed_text
    assert events[-1].result is not None
    assert events[-1].result.answer == "武汉今天小雨，气温偏高。"


def test_unified_assistant_stream_sanitizes_knowledge_raw_payload(monkeypatch):
    class FakeAgent:
        async def astream(self, *_args, **_kwargs):
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(
                        type="ai",
                        content='{"query":"毕博控股"}',
                        tool_call_chunks=[{"name": "search_knowledge_base"}],
                    ),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content="",
                            tool_calls=[{"name": "search_knowledge_base"}],
                        ),
                    ],
                },
            }
            raw_answer = (
                '调用完成\nsearch_knowledge_base\n'
                '{"context":"简历内容片段","sources":["简历.pdf"]}\n'
                '{"context":"重复的简历内容片段","sources":["简历.pdf"]}\n'
                "知识库中没有找到毕博控股的相关信息。"
            )
            yield {
                "type": "messages",
                "data": (
                    SimpleNamespace(type="ai", content=raw_answer),
                    {},
                ),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content="",
                            tool_calls=[{"name": "search_knowledge_base"}],
                        ),
                        SimpleNamespace(type="ai", content=raw_answer),
                    ],
                },
            }

    monkeypatch.setattr(orchestrator, "create_unified_agent", lambda *_args, **_kwargs: FakeAgent())
    monkeypatch.setattr(orchestrator, "create_task_tools", lambda **_kwargs: [])

    async def collect_events():
        events = []
        async for event in orchestrator.stream_unified_assistant(
            llm=object(),
            model_input="毕博控股是什么",
            embedding_function=object(),
            mcp_tools=[],
        ):
            events.append(event)
        return events

    events = asyncio.run(collect_events())
    streamed_text = "".join(event.delta or "" for event in events)

    assert "search_knowledge_base" not in streamed_text
    assert "调用完成" not in streamed_text
    assert '"context"' not in streamed_text
    assert '"sources"' not in streamed_text
    assert "知识库中没有找到毕博控股的相关信息。" in streamed_text
    assert events[-1].result is not None
    assert events[-1].result.answer == "知识库中没有找到毕博控股的相关信息。"
