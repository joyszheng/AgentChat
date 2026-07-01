import hashlib
import logging
import os
import time
from pathlib import Path

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient, connections

from .chains import rag_chain
from .document_processing import ProcessedDocument, load_upload_documents
from .models import embeddings


logger = logging.getLogger("uvicorn.error")

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

splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=100,
    length_function=len,
)

chunks = splitter.split_documents([document])

DEFAULT_MILVUS_URI = "http://localhost:19530"
AGENTCHAT_MILVUS_URI = os.getenv("AGENTCHAT_MILVUS_URI", DEFAULT_MILVUS_URI)
AGENTCHAT_MILVUS_COLLECTION = os.getenv("AGENTCHAT_MILVUS_COLLECTION", "agentchat_documents")
AGENTCHAT_MILVUS_TOKEN = os.getenv("AGENTCHAT_MILVUS_TOKEN")
AGENTCHAT_MILVUS_DB = os.getenv("AGENTCHAT_MILVUS_DB")

if AGENTCHAT_MILVUS_URI.endswith(".db"):
    Path(AGENTCHAT_MILVUS_URI).parent.mkdir(parents=True, exist_ok=True)

vector_store: Milvus | None = None
default_documents_indexed = False


def _milvus_connection_args() -> dict[str, str]:
    connection_args = {"uri": AGENTCHAT_MILVUS_URI}

    if AGENTCHAT_MILVUS_TOKEN:
        connection_args["token"] = AGENTCHAT_MILVUS_TOKEN

    if AGENTCHAT_MILVUS_DB:
        connection_args["db_name"] = AGENTCHAT_MILVUS_DB

    return connection_args


def _ensure_legacy_orm_connection(connection_args: dict[str, str]) -> None:
    """Register the ORM alias still used internally by langchain-milvus."""

    client = MilvusClient(**connection_args)
    if not connections.has_connection(client._using):
        connections.connect(alias=client._using, **connection_args)


def get_vector_store() -> Milvus:
    global vector_store

    if vector_store is None:
        started_at = time.perf_counter()
        logger.info(
            "[rag] Milvus initialization started uri=%s collection=%s",
            AGENTCHAT_MILVUS_URI,
            AGENTCHAT_MILVUS_COLLECTION,
        )
        try:
            connection_args = _milvus_connection_args()
            _ensure_legacy_orm_connection(connection_args)
            vector_store = Milvus(
                embedding_function=embeddings,
                collection_name=AGENTCHAT_MILVUS_COLLECTION,
                connection_args=connection_args,
                auto_id=False,
                metadata_field="metadata",
            )
            logger.info(
                "[rag] Milvus initialization completed collection=%s elapsed=%.2fs",
                AGENTCHAT_MILVUS_COLLECTION,
                time.perf_counter() - started_at,
            )
        except Exception as exc:
            if AGENTCHAT_MILVUS_URI.endswith(".db"):
                raise RuntimeError(
                    "Milvus Lite 本地文件库初始化失败。Milvus Lite 主要支持 Linux/macOS；"
                    "Windows 本机建议使用 WSL 运行后端，或将 AGENTCHAT_MILVUS_URI "
                    "改为独立 Milvus 服务地址。"
                ) from exc
            raise

    return vector_store


def _chunk_ids(documents: list[Document]) -> list[str]:
    ids: list[str] = []
    for index, doc in enumerate(documents):
        source = doc.metadata.get("source", "")
        file_hash = doc.metadata.get("file_sha256", "")
        element_index = doc.metadata.get("element_index", "")
        digest = hashlib.sha256(
            f"{source}:{file_hash}:{element_index}:{index}:{doc.page_content}".encode("utf-8")
        ).hexdigest()
        ids.append(digest)

    return ids


def _upsert_documents(documents: list[Document]) -> None:
    store = get_vector_store()
    ids = _chunk_ids(documents)
    started_at = time.perf_counter()
    logger.info(
        "[rag] Embedding and Milvus write started collection=%s documents=%s",
        AGENTCHAT_MILVUS_COLLECTION,
        len(documents),
    )

    if store.client.has_collection(collection_name=AGENTCHAT_MILVUS_COLLECTION):
        store.upsert(ids=ids, documents=documents)
    else:
        store.add_documents(documents=documents, ids=ids)

    logger.info(
        "[rag] Embedding and Milvus write completed collection=%s documents=%s elapsed=%.2fs",
        AGENTCHAT_MILVUS_COLLECTION,
        len(documents),
        time.perf_counter() - started_at,
    )


def ensure_default_documents_indexed() -> None:
    global default_documents_indexed

    if default_documents_indexed:
        return

    logger.info("[rag] Default document indexing started documents=%s", len(chunks))
    _upsert_documents(chunks)
    default_documents_indexed = True
    logger.info("[rag] Default document indexing completed documents=%s", len(chunks))


def add_documents_to_index(documents: list[Document]) -> int:
    """Split cleaned documents and add them to the Milvus vector store."""

    started_at = time.perf_counter()
    logger.info("[rag] Chunking started documents=%s", len(documents))
    chunks = splitter.split_documents(documents)
    logger.info(
        "[rag] Chunking completed documents=%s chunks=%s elapsed=%.2fs",
        len(documents),
        len(chunks),
        time.perf_counter() - started_at,
    )
    if not chunks:
        return 0

    ensure_default_documents_indexed()
    _upsert_documents(chunks)
    return len(chunks)


def ingest_upload(
    file_path: Path,
    *,
    original_filename: str | None = None,
    content_type: str | None = None,
) -> tuple[ProcessedDocument, int]:
    processed = load_upload_documents(
        file_path,
        original_filename=original_filename,
        content_type=content_type,
    )
    chunk_count = add_documents_to_index(processed.documents)

    return processed, chunk_count


def _generate_answer(*, context: str, question: str) -> str:
    for _ in range(2):
        response = rag_chain.invoke({
            "context": context,
            "question": question,
        })
        if isinstance(response.content, str) and response.content.strip():
            return response.content

    raise RuntimeError("RAG model returned an empty response")


def ask_document(question: str) -> tuple[str, list[str]]:
    ensure_default_documents_indexed()
    retriever = get_vector_store().as_retriever(search_kwargs={"k": 4})
    documents = retriever.invoke(question)

    context = "\n\n".join(
        doc.page_content
        for doc in documents
    )

    answer = _generate_answer(context=context, question=question)

    sources = sorted({
        doc.metadata.get("source", "未知来源")
        for doc in documents
    })

    return answer, sources
