import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..ai.agents import task_agent
from ..ai.chains import chat_chain
from ..ai.rag import ask_document
from ..database import get_db

router = APIRouter(prefix="/ai", tags=["AI"])


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
