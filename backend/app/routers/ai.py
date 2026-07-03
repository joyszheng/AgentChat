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
from ..ai.agents import task_agent
from ..ai.chains import chat_chain
from ..ai.rag import ask_document
from ..database import SessionLocal, get_db

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
            async for text in _stream_chat_text(model_input):
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


def _prepare_chat_request(request: schemas.ChatRequest, db: Session):
    session = crud.get_or_create_chat_session(
        db,
        session_id=request.session_id,
        title=_default_session_title(request.message),
        mode="chat",
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
def tasks_assistant(request: schemas.ChatRequest) -> TextResponse:
    try:
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
    

class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RagResponse(BaseModel):
    answer: str
    sources: list[str]

@router.post("/rag", response_model=RagResponse)
def rag(request: RagRequest) -> RagResponse:
    try:
        answer, sources = ask_document(request.question)

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


async def _stream_chat_text(model_input: str) -> AsyncIterator[str]:
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


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
