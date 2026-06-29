from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .chains import rag_chain

# 1. 加载文档
# path = Path("docs/agentchat-guide.md")
path = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "agentchat-guide.md"
)

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


def ask_document(question: str) -> tuple[str, list[str]]:
    documents = retriever.invoke(question)

    context = "\n\n".join(
        doc.page_content
        for doc in documents
    )

    response = rag_chain.invoke({
        "context": context,
        "question": question,
    })

    sources = sorted({
        doc.metadata.get("source", "未知来源")
        for doc in documents
    })

    return response.content, sources