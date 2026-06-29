from langchain_core.prompts import ChatPromptTemplate


chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位简洁、准确、耐心的 AI 助手。"),
    ("human", "{message}"),
])

rag_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是文档问答助手。只能根据提供的文档内容回答。"
        "如果文档中没有答案，请明确回答：文档中没有相关信息。"
    ),
    (
        "human",
        "文档内容：\n{context}\n\n用户问题：{question}"
    ),
])