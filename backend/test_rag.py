import os

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

# 1. 加载文档
path = Path("docs/agentchat-guide.md")

document = Document(
    page_content=path.read_text(encoding="utf-8"),
    metadata={"source": str(path)},
)

# 2. 切分文档
splitter = RecursiveCharacterTextSplitter(
    chunk_size=60,
    chunk_overlap=15,
)

chunks = splitter.split_documents([document])

# 3. 初始化 Embedding
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# 4. 建立内存向量库
vector_store = InMemoryVectorStore(embedding=embeddings)
vector_store.add_documents(documents=chunks)

# 5. 转换为 Retriever
retriever = vector_store.as_retriever(
    search_kwargs={"k": 2}
)

# 6. 检索
# results = retriever.invoke("这个项目的内部名称是什么？")

# print("检索数量：", len(results))

# for index, result in enumerate(results, start=1):
#     print(f"\n--- 检索结果 {index} ---")
#     print(result.page_content)
#     print("来源：", result.metadata)




model = ChatOpenAI(
    model="z-ai/glm-5.1",
    base_url="https://ai.hybgzs.com/v1",
    api_key=os.environ["GLM_API_KEY"],
    timeout=30,
)

prompt = ChatPromptTemplate.from_messages([
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

rag_chain = prompt | model

question = "AgentChat 项目的负责人是谁？"
documents = retriever.invoke(question)

context = "\n\n".join(
    doc.page_content
    for doc in documents
)

response = rag_chain.invoke({
    "context": context,
    "question": question,
})

print("检索上下文：")
print(context)

print("\n最终回答：")
print(response.content)