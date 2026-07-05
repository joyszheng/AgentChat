from .prompts import chat_prompt, rag_prompt


def create_chat_chain(llm):
    """Create a chat chain for the LLM selected for the current request."""
    return chat_prompt | llm


def create_rag_chain(llm):
    """Create a RAG chain for the LLM selected for the current request."""
    return rag_prompt | llm
