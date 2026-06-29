import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..ai.agents import task_agent
from ..ai.chains import chat_chain
from ..ai.rag import ask_document

router = APIRouter(prefix="/ai", tags=["AI"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="user message")


class ChatResponse(BaseModel):
    answer: str = Field(description="AI response")

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        response = chat_chain.invoke({"message": request.message})
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="AI 服务暂时不可用，请稍后重试")

    return ChatResponse(answer=response.content)


@router.post("/tasks-assistant", response_model=ChatResponse)
def tasks_assistant(request: ChatRequest) -> ChatResponse:
    try:
        result = task_agent.invoke({
            "messages": [{
                "role": "user",
                "content": request.message
            }]
        })

        answer = result["messages"][-1].content
        return ChatResponse(answer=answer)
    
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