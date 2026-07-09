from langchain_core.prompts import ChatPromptTemplate


chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位简洁、准确、耐心的 AI 助手。"),
    ("human", "{message}"),
])

rag_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是严谨的文档问答助手。只能根据用户提供的文档片段回答，不能使用片段外的知识补全。\n"
        "回答前先判断证据是否足够；如果文档片段中没有答案，必须明确回答：文档中没有相关信息。\n"
        "如果片段之间存在冲突或只能部分回答，请说明不确定之处。\n"
        "回答要简洁、准确，使用 Markdown，并在需要时列出依据的来源编号，例如 [1]、[2]。"
    ),
    (
        "human",
        "文档内容：\n{context}\n\n用户问题：{question}"
    ),
])
