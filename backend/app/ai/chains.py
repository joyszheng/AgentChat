from .models import llm
from .prompts import chat_prompt, rag_prompt


chat_chain = chat_prompt | llm
rag_chain = rag_prompt | llm