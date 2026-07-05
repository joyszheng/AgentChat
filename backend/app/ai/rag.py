import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient, connections

from .chains import create_rag_chain
from .document_processing import ProcessedDocument, load_upload_documents
from .models import embeddings as default_embeddings


logger = logging.getLogger("uvicorn.error")
ProgressCallback = Callable[..., None]

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

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
)

chunks = splitter.split_documents([document])

DEFAULT_MILVUS_URI = "http://localhost:19530"
AGENTCHAT_MILVUS_URI = os.getenv("AGENTCHAT_MILVUS_URI", DEFAULT_MILVUS_URI)
AGENTCHAT_MILVUS_COLLECTION = os.getenv("AGENTCHAT_MILVUS_COLLECTION", "agentchat_documents")
AGENTCHAT_MILVUS_TOKEN = os.getenv("AGENTCHAT_MILVUS_TOKEN")
AGENTCHAT_MILVUS_DB = os.getenv("AGENTCHAT_MILVUS_DB")
VECTOR_OPERATION_TIMEOUT = float(os.getenv("AGENTCHAT_VECTOR_TIMEOUT_SECONDS", "60"))

if AGENTCHAT_MILVUS_URI.endswith(".db"):
    Path(AGENTCHAT_MILVUS_URI).parent.mkdir(parents=True, exist_ok=True)

vector_store: Milvus | None = None
vector_store_embedding = None
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


def get_vector_store(embedding_function=None) -> Milvus:
    global default_documents_indexed, vector_store, vector_store_embedding

    selected_embedding = embedding_function or default_embeddings
    if vector_store_embedding is not selected_embedding:
        vector_store = None
        vector_store_embedding = selected_embedding
        default_documents_indexed = False

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
                embedding_function=selected_embedding,
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


def _log_scope(document_id: int | None) -> str:
    return f"upload:{document_id}" if document_id is not None else "rag"


def _upsert_documents(
    documents: list[Document],
    *,
    document_id: int | None = None,
    embedding_function=None,
) -> None:
    selected_embedding = embedding_function or default_embeddings
    store = get_vector_store(selected_embedding)
    ids = _chunk_ids(documents)
    started_at = time.perf_counter()
    scope = _log_scope(document_id)
    total_characters = sum(len(document.page_content) for document in documents)
    collection_exists = store.client.has_collection(
        collection_name=AGENTCHAT_MILVUS_COLLECTION
    )
    operation = "upsert" if collection_exists else "create_and_add"
    logger.info(
        "[%s] Vector indexing started collection=%s operation=%s chunks=%s "
        "characters=%s embedding_dimensions=%s",
        scope,
        AGENTCHAT_MILVUS_COLLECTION,
        operation,
        len(documents),
        total_characters,
        getattr(selected_embedding, "dimensions", "provider_default"),
    )

    try:
        if collection_exists:
            store.upsert(
                ids=ids,
                documents=documents,
                timeout=VECTOR_OPERATION_TIMEOUT,
            )
        else:
            store.add_documents(
                documents=documents,
                ids=ids,
                timeout=VECTOR_OPERATION_TIMEOUT,
            )
    except Exception as exc:
        logger.exception(
            "[%s] Vector indexing failed collection=%s operation=%s chunks=%s "
            "elapsed=%.2fs error_type=%s error=%s",
            scope,
            AGENTCHAT_MILVUS_COLLECTION,
            operation,
            len(documents),
            time.perf_counter() - started_at,
            type(exc).__name__,
            exc,
        )
        raise

    logger.info(
        "[%s] Vector indexing completed collection=%s operation=%s chunks=%s "
        "elapsed=%.2fs",
        scope,
        AGENTCHAT_MILVUS_COLLECTION,
        operation,
        len(documents),
        time.perf_counter() - started_at,
    )


def ensure_default_documents_indexed(embedding_function=None) -> None:
    global default_documents_indexed

    # Let get_vector_store invalidate the default-document flag when the
    # administrator switches to a different embedding configuration.
    get_vector_store(embedding_function)
    if default_documents_indexed:
        return

    logger.info("[rag] Default document indexing started documents=%s", len(chunks))
    _upsert_documents(chunks, embedding_function=embedding_function)
    default_documents_indexed = True
    logger.info("[rag] Default document indexing completed documents=%s", len(chunks))


def add_documents_to_index(
    documents: list[Document],
    *,
    document_id: int | None = None,
    progress_callback: ProgressCallback | None = None,
    embedding_function=None,
) -> int:
    """Split cleaned documents and add them to the Milvus vector store."""

    started_at = time.perf_counter()
    scope = _log_scope(document_id)
    source_characters = sum(len(document.page_content) for document in documents)
    logger.info(
        "[%s] Chunking started documents=%s characters=%s chunk_size=%s overlap=%s",
        scope,
        len(documents),
        source_characters,
        CHUNK_SIZE,
        CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(documents)
    chunk_lengths = [len(chunk.page_content) for chunk in chunks]
    logger.info(
        "[%s] Chunking completed documents=%s chunks=%s min_chars=%s max_chars=%s "
        "avg_chars=%.1f elapsed=%.2fs",
        scope,
        len(documents),
        len(chunks),
        min(chunk_lengths, default=0),
        max(chunk_lengths, default=0),
        sum(chunk_lengths) / len(chunk_lengths) if chunk_lengths else 0,
        time.perf_counter() - started_at,
    )
    if not chunks:
        logger.warning("[%s] Indexing skipped reason=no_chunks", scope)
        return 0

    if progress_callback is not None:
        progress_callback("indexing", chunk_count=len(chunks))

    ensure_default_documents_indexed(embedding_function)
    _upsert_documents(
        chunks,
        document_id=document_id,
        embedding_function=embedding_function,
    )
    return len(chunks)


def delete_document_from_index(
    *,
    file_sha256: str | None,
    source: str,
    document_id: int | None = None,
) -> int:
    """按文件哈希（旧记录回退到源路径）删除文档的全部向量分片。"""

    scope = _log_scope(document_id)
    store = get_vector_store()
    if not store.client.has_collection(collection_name=AGENTCHAT_MILVUS_COLLECTION):
        logger.info(
            "[%s] Vector cleanup skipped reason=collection_not_found collection=%s",
            scope,
            AGENTCHAT_MILVUS_COLLECTION,
        )
        return 0

    if file_sha256:
        expression = f'metadata["file_sha256"] == {json.dumps(file_sha256)}'
        selector = f"sha256:{file_sha256[:12]}"
    else:
        expression = f'metadata["source"] == {json.dumps(source)}'
        selector = "source_path"

    started_at = time.perf_counter()
    logger.info(
        "[%s] Vector cleanup started collection=%s selector=%s",
        scope,
        AGENTCHAT_MILVUS_COLLECTION,
        selector,
    )
    ids = store.get_pks(expression, timeout=VECTOR_OPERATION_TIMEOUT) or []
    if not ids:
        logger.info(
            "[%s] Vector cleanup completed deleted_chunks=0 elapsed=%.2fs",
            scope,
            time.perf_counter() - started_at,
        )
        return 0

    if not store.delete(ids=ids, timeout=VECTOR_OPERATION_TIMEOUT):
        raise RuntimeError("Milvus 向量分片删除失败")

    logger.info(
        "[%s] Vector cleanup completed deleted_chunks=%s elapsed=%.2fs",
        scope,
        len(ids),
        time.perf_counter() - started_at,
    )
    return len(ids)


def ingest_upload(
    file_path: Path,
    *,
    original_filename: str | None = None,
    content_type: str | None = None,
    document_id: int | None = None,
    progress_callback: ProgressCallback | None = None,
    embedding_function=None,
) -> tuple[ProcessedDocument, int]:
    started_at = time.perf_counter()
    scope = _log_scope(document_id)
    display_name = original_filename or file_path.name
    logger.info(
        "[%s] Ingestion pipeline started file=%r stored=%s content_type=%s size=%s bytes",
        scope,
        display_name,
        file_path.name,
        content_type or "unknown",
        file_path.stat().st_size,
    )

    if progress_callback is not None:
        progress_callback("parsing")

    parse_started_at = time.perf_counter()
    processed = load_upload_documents(
        file_path,
        original_filename=original_filename,
        content_type=content_type,
    )
    parsed_characters = sum(len(document.page_content) for document in processed.documents)
    logger.info(
        "[%s] Parse stage completed file=%r documents=%s characters=%s warnings=%s "
        "elapsed=%.2fs",
        scope,
        display_name,
        len(processed.documents),
        parsed_characters,
        len(processed.warnings),
        time.perf_counter() - parse_started_at,
    )

    if progress_callback is not None:
        progress_callback("chunking")

    chunk_count = add_documents_to_index(
        processed.documents,
        document_id=document_id,
        progress_callback=progress_callback,
        embedding_function=embedding_function,
    )
    logger.info(
        "[%s] Ingestion pipeline completed file=%r documents=%s chunks=%s "
        "elapsed=%.2fs",
        scope,
        display_name,
        len(processed.documents),
        chunk_count,
        time.perf_counter() - started_at,
    )

    return processed, chunk_count


def _generate_answer(*, context: str, question: str, llm) -> str:
    rag_chain = create_rag_chain(llm)
    for _ in range(2):
        response = rag_chain.invoke({
            "context": context,
            "question": question,
        })
        if isinstance(response.content, str) and response.content.strip():
            return response.content

    raise RuntimeError("RAG model returned an empty response")


def ask_document(question: str, *, llm, embedding_function=None) -> tuple[str, list[str]]:
    ensure_default_documents_indexed(embedding_function)
    retriever = get_vector_store(embedding_function).as_retriever(search_kwargs={"k": 4})
    documents = retriever.invoke(question)

    context = "\n\n".join(
        doc.page_content
        for doc in documents
    )

    answer = _generate_answer(context=context, question=question, llm=llm)

    sources = sorted({
        doc.metadata.get("original_filename") or doc.metadata.get("source", "未知来源")
        for doc in documents
    })

    return answer, sources
