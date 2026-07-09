import json
import logging
import traceback
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from .. import crud, schemas
from ..ai.agents import create_mcp_agent, create_task_agent
from ..ai.chains import create_chat_chain, create_rag_chain
from ..ai.config import get_embeddings_from_config, get_llm_from_config
from ..ai.orchestrator import run_unified_assistant
from ..ai.rag import ask_document, document_sources, documents_to_context, retrieve_documents
from ..database import SessionLocal, get_db
from ..mcp import mcp_registry
from ..services.dependencies import get_current_user, require_auth

router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)

NO_GENERATION_CHUNKS_ERROR = "No generation chunks were returned"


class TextResponse(BaseModel):
    answer: str = Field(description="AI response")


@router.post("/sessions", response_model=schemas.ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_chat_session(
    request: schemas.ChatSessionCreate,
    db: Session = Depends(get_db),
) -> schemas.ChatSessionResponse:
    return crud.create_chat_session(db, title=request.title, mode=request.mode)


@router.get("/sessions", response_model=list[schemas.ChatSessionResponse])
def list_chat_sessions(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> list[schemas.ChatSessionResponse]:
    return crud.list_chat_sessions(db, skip=skip, limit=limit)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(session_id: int, db: Session = Depends(get_db)) -> Response:
    deleted = crud.delete_chat_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions/{session_id}/messages", response_model=list[schemas.ChatMessageResponse])
def list_chat_messages(
    session_id: int,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Session = Depends(get_db),
) -> list[schemas.ChatMessageResponse]:
    session = crud.get_chat_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    return crud.list_chat_messages(db, session_id=session_id, skip=skip, limit=limit)


@router.post("/chat", response_model=schemas.ChatResponse)
def chat(request: schemas.ChatRequest, db: Session = Depends(get_db)) -> schemas.ChatResponse:
    session, user_message, model_input = _prepare_chat_request(request, db)
    chat_chain = create_chat_chain(get_llm_from_config(db))

    try:
        response = chat_chain.invoke({"message": model_input})
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="AI 服务暂时不可用，请稍后重试")

    assistant_message = crud.create_chat_message(
        db,
        session_id=session.id,
        role="assistant",
        content=response.content,
        message_metadata={"model": "chat"},
    )

    return schemas.ChatResponse(
        answer=response.content,
        session_id=session.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """以 SSE 逐段返回聊天结果，并在完整生成后保存助手消息。"""

    session, user_message, model_input = _prepare_chat_request(request, db)
    chat_chain = create_chat_chain(get_llm_from_config(db))
    session_id = session.id
    user_message_id = user_message.id

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_event(
            "start",
            {
                "session_id": session_id,
                "user_message_id": user_message_id,
            },
        )

        answer_parts: list[str] = []

        try:
            async for text in _stream_chat_text(model_input, chat_chain):
                answer_parts.append(text)
                yield _sse_event("token", {"delta": text})

            answer = "".join(answer_parts)
            with SessionLocal() as stream_db:
                assistant_message = crud.create_chat_message(
                    stream_db,
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    message_metadata={"model": "chat", "streamed": True},
                )
                assistant_message_id = assistant_message.id
        except Exception:
            traceback.print_exc()
            yield _sse_event(
                "error",
                {
                    "code": "ai_service_unavailable",
                    "message": "AI 服务暂时不可用，请稍后重试",
                },
            )
            return

        yield _sse_event(
            "done",
            {
                "session_id": session_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _prepare_chat_request(
    request: schemas.ChatRequest,
    db: Session,
    *,
    mode: str = "chat",
):
    session = crud.get_or_create_chat_session(
        db,
        session_id=request.session_id,
        title=_default_session_title(request.message),
        mode=mode,
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    history = crud.get_recent_chat_messages(db, session.id, limit=10)
    user_message = crud.create_chat_message(
        db,
        session_id=session.id,
        role="user",
        content=request.message,
    )
    model_input = _build_chat_model_input(
        current_message=request.message,
        history=history,
        summary=session.summary,
    )

    return session, user_message, model_input


@router.post("/tasks-assistant", response_model=TextResponse)
def tasks_assistant(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
) -> TextResponse:
    try:
        task_agent = create_task_agent(get_llm_from_config(db))
        result = task_agent.invoke({
            "messages": [{
                "role": "user",
                "content": request.message
            }]
        })

        answer = result["messages"][-1].content
        return TextResponse(answer=answer)
    
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="任务助手暂时不可用，请稍后再试"
        )


@router.post("/assistant", response_model=schemas.AssistantResponse)
async def assistant(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> schemas.AssistantResponse:
    """Unified assistant that can answer directly, search RAG, and call tools."""

    session, user_message, model_input = _prepare_chat_request(request, db, mode="assistant")
    is_admin = bool(user and user.role == "admin")
    mcp_tools = mcp_registry.get_tools(is_admin=is_admin)

    try:
        result = await run_unified_assistant(
            llm=get_llm_from_config(db),
            model_input=model_input,
            embedding_function=get_embeddings_from_config(db),
            mcp_tools=mcp_tools,
        )
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="智能助手暂时不可用，请稍后重试",
        )

    assistant_message = crud.create_chat_message(
        db,
        session_id=session.id,
        role="assistant",
        content=result.answer,
        message_metadata={
            "model": "assistant",
            "route": result.route,
            "sources": result.sources,
            "tools_used": result.tools_used,
        },
    )
    return schemas.AssistantResponse(
        answer=result.answer,
        session_id=session.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        route=result.route,
        sources=result.sources,
        tools_used=result.tools_used,
    )


@router.post("/mcp-assistant", response_model=schemas.MCPAssistantResponse)
async def mcp_assistant(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
) -> schemas.MCPAssistantResponse:
    """Use enabled MCP tools through a request-scoped LangChain agent."""

    tools = mcp_registry.get_tools(is_admin=user.role == "admin")
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="当前没有可用的 MCP 工具",
        )

    session, user_message, model_input = _prepare_chat_request(request, db)
    agent = create_mcp_agent(get_llm_from_config(db), tools)

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": model_input}]}
        )
        messages = result.get("messages", [])
        answer = _last_assistant_text(messages)
        tools_used = _tools_used(messages)
        if not answer:
            raise ValueError("MCP agent returned an empty response")
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="MCP 工具助手暂时不可用，请稍后重试",
        )

    assistant_message = crud.create_chat_message(
        db,
        session_id=session.id,
        role="assistant",
        content=answer,
        message_metadata={
            "model": "mcp-assistant",
            "tools_used": tools_used,
        },
    )
    return schemas.MCPAssistantResponse(
        answer=answer,
        session_id=session.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        tools_used=tools_used,
    )
    

class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RagResponse(BaseModel):
    answer: str
    sources: list[str]


@router.post("/rag", response_model=RagResponse)
def rag(request: RagRequest, db: Session = Depends(get_db)) -> RagResponse:
    try:
        answer, sources = ask_document(
            request.question,
            llm=get_llm_from_config(db),
            embedding_function=get_embeddings_from_config(db),
        )

        return RagResponse(
            answer=answer,
            sources=sources,
        )
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="文档问答服务暂时不可用",
        )


@router.post("/rag/stream")
async def rag_stream(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """以 SSE 逐段返回 RAG 答案，并保存用户问题、助手答案和引用来源。"""

    session, user_message, _model_input = _prepare_chat_request(request, db, mode="rag")
    rag_chain = create_rag_chain(get_llm_from_config(db))
    embedding_function = get_embeddings_from_config(db)
    session_id = session.id
    user_message_id = user_message.id
    question = request.message

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_event(
            "start",
            {
                "session_id": session_id,
                "user_message_id": user_message_id,
            },
        )

        answer_parts: list[str] = []

        try:
            documents = retrieve_documents(question, embedding_function=embedding_function)
            context = documents_to_context(documents)
            sources = document_sources(documents)
            yield _sse_event("sources", {"sources": sources})

            async for text in _stream_rag_text(context, question, rag_chain):
                answer_parts.append(text)
                yield _sse_event("token", {"delta": text})

            answer = "".join(answer_parts)
            with SessionLocal() as stream_db:
                assistant_message = crud.create_chat_message(
                    stream_db,
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    message_metadata={
                        "model": "rag",
                        "streamed": True,
                        "sources": sources,
                    },
                )
                assistant_message_id = assistant_message.id
        except Exception:
            traceback.print_exc()
            yield _sse_event(
                "error",
                {
                    "code": "rag_service_unavailable",
                    "message": "文档问答服务暂时不可用",
                },
            )
            return

        yield _sse_event(
            "done",
            {
                "session_id": session_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _default_session_title(message: str) -> str:
    title = message.strip().replace("\n", " ")
    return title[:50] or "新会话"


def _build_chat_model_input(
    *,
    current_message: str,
    history: list,
    summary: str | None,
) -> str:
    parts = [
        "请基于以下会话上下文回答用户当前问题。回答要自然、准确、简洁。",
    ]

    if summary:
        parts.append(f"\n长期记忆摘要：\n{summary}")

    if history:
        lines = []
        for message in history:
            role = "用户" if message.role == "user" else "助手"
            lines.append(f"{role}：{message.content}")
        parts.append("\n最近对话：\n" + "\n".join(lines))

    parts.append(f"\n当前用户问题：\n{current_message}")

    return "\n".join(parts)


def _chunk_text(chunk) -> str:
    """从 LangChain 消息分片中提取文本，兼容字符串和内容块格式。"""

    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            text_parts.append(block["text"])

    return "".join(text_parts)


def _last_assistant_text(messages: list) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "ai":
            text = _chunk_text(message)
            if text:
                return text
    return ""


def _tools_used(messages: list) -> list[str]:
    names: list[str] = []
    for message in messages:
        for tool_call in getattr(message, "tool_calls", []) or []:
            name = tool_call.get("name")
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names


async def _stream_chat_text(model_input: str, chat_chain) -> AsyncIterator[str]:
    """流式读取模型文本；上游未返回分片时降级为一次性异步调用。"""

    received_text = False
    try:
        async for chunk in chat_chain.astream({"message": model_input}):
            text = _chunk_text(chunk)
            if not text:
                continue

            received_text = True
            yield text
    except ValueError as exc:
        if received_text or str(exc) != NO_GENERATION_CHUNKS_ERROR:
            raise

        logger.warning("模型流式响应未返回内容分片，降级为非流式异步调用")
    else:
        if received_text:
            return

        logger.warning("模型流式响应内容为空，降级为非流式异步调用")

    response = await chat_chain.ainvoke({"message": model_input})
    text = _chunk_text(response)
    if not text:
        raise ValueError("AI model returned an empty response")

    yield text


async def _stream_rag_text(context: str, question: str, rag_chain) -> AsyncIterator[str]:
    """流式读取 RAG 模型文本；上游未返回分片时降级为一次性异步调用。"""

    payload = {
        "context": context,
        "question": question,
    }
    received_text = False
    try:
        async for chunk in rag_chain.astream(payload):
            text = _chunk_text(chunk)
            if not text:
                continue

            received_text = True
            yield text
    except ValueError as exc:
        if received_text or str(exc) != NO_GENERATION_CHUNKS_ERROR:
            raise

        logger.warning("RAG 模型流式响应未返回内容分片，降级为非流式异步调用")
    else:
        if received_text:
            return

        logger.warning("RAG 模型流式响应内容为空，降级为非流式异步调用")

    response = await rag_chain.ainvoke(payload)
    text = _chunk_text(response)
    if not text:
        raise ValueError("RAG model returned an empty response")

    yield text


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
