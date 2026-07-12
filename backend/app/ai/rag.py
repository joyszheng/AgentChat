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
RAG_TOP_K = int(os.getenv("AGENTCHAT_RAG_TOP_K", "4"))
RAG_FETCH_K = max(RAG_TOP_K, int(os.getenv("AGENTCHAT_RAG_FETCH_K", "16")))
RAG_SEARCH_TYPE = os.getenv("AGENTCHAT_RAG_SEARCH_TYPE", "similarity").lower()
RAG_CONTEXT_MAX_CHARS = int(os.getenv("AGENTCHAT_RAG_CONTEXT_MAX_CHARS", "12000"))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
)

chunks = splitter.split_documents([document])
for index, chunk in enumerate(chunks):
    chunk.metadata = {
        **chunk.metadata,
        "chunk_index": index,
        "chunk_total": len(chunks),
        "document_type": "default",
    }

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
        if file_hash:
            chunk_index = doc.metadata.get("chunk_index", index)
            fingerprint = f"{file_hash}:{element_index}:{chunk_index}:{doc.page_content}"
        else:
            fingerprint = f"{source}:{file_hash}:{element_index}:{index}:{doc.page_content}"
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        ids.append(digest)

    return ids


def _log_scope(document_id: int | None) -> str:
    return f"upload:{document_id}" if document_id is not None else "rag"


def _tag_chunks_metadata(chunks: list[Document], *, document_id: int | None = None) -> None:
    chunk_total = len(chunks)
    for index, chunk in enumerate(chunks):
        metadata = {
            **chunk.metadata,
            "chunk_index": index,
            "chunk_total": chunk_total,
        }
        if document_id is not None:
            metadata["document_id"] = document_id
        chunk.metadata = metadata


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


def _vector_ids_exist(
    ids: list[str],
    *,
    embedding_function=None,
) -> bool:
    if not ids:
        return True

    store = get_vector_store(embedding_function)
    if not store.client.has_collection(collection_name=AGENTCHAT_MILVUS_COLLECTION):
        return False

    try:
        records = store.client.get(
            collection_name=AGENTCHAT_MILVUS_COLLECTION,
            ids=ids,
            output_fields=["pk"],
            timeout=VECTOR_OPERATION_TIMEOUT,
        )
    except Exception as exc:
        logger.warning(
            "[rag] Vector existence lookup failed collection=%s ids=%s error_type=%s error=%s",
            AGENTCHAT_MILVUS_COLLECTION,
            len(ids),
            type(exc).__name__,
            exc,
        )
        return False

    found_ids = {str(record.get("pk")) for record in records if record.get("pk") is not None}
    return set(ids).issubset(found_ids)


def ensure_default_documents_indexed(embedding_function=None) -> None:
    global default_documents_indexed

    # Let get_vector_store invalidate the default-document flag when the
    # administrator switches to a different embedding configuration.
    get_vector_store(embedding_function)
    if default_documents_indexed:
        return

    default_chunk_ids = _chunk_ids(chunks)
    if _vector_ids_exist(default_chunk_ids, embedding_function=embedding_function):
        default_documents_indexed = True
        logger.info(
            "[rag] Default document indexing skipped reason=already_indexed documents=%s chunks=%s",
            len(chunks),
            len(default_chunk_ids),
        )
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
    _tag_chunks_metadata(chunks, document_id=document_id)
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
    document_id: int | None = None,
    file_sha256: str | None,
    source: str,
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

    selectors: list[tuple[str, str]] = []
    if document_id is not None:
        selectors.append((
            f'metadata["document_id"] == {json.dumps(document_id)}',
            f"document_id:{document_id}",
        ))
    if file_sha256:
        selectors.append((
            f'metadata["file_sha256"] == {json.dumps(file_sha256)}',
            f"sha256:{file_sha256[:12]}",
        ))
    selectors.append((
        f'metadata["source"] == {json.dumps(source)}',
        "source_path",
    ))

    started_at = time.perf_counter()
    ids = []
    matched_selector = selectors[-1][1]
    for expression, selector in selectors:
        logger.info(
            "[%s] Vector cleanup lookup collection=%s selector=%s",
            scope,
            AGENTCHAT_MILVUS_COLLECTION,
            selector,
        )
        ids = store.get_pks(expression, timeout=VECTOR_OPERATION_TIMEOUT) or []
        if ids:
            matched_selector = selector
            break

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
        "[%s] Vector cleanup completed selector=%s deleted_chunks=%s elapsed=%.2fs",
        scope,
        matched_selector,
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


def _document_dedupe_key(doc: Document) -> tuple[str, ...]:
    metadata = doc.metadata
    file_hash = str(metadata.get("file_sha256") or "")
    chunk_index = metadata.get("chunk_index")
    element_index = metadata.get("element_index")
    source = str(metadata.get("original_filename") or metadata.get("source") or "")
    text_hash = hashlib.sha256(doc.page_content.strip().encode("utf-8")).hexdigest()

    if file_hash and chunk_index is not None:
        return ("file_chunk", file_hash, str(chunk_index))
    if file_hash and element_index is not None:
        return ("legacy_element", file_hash, str(element_index), text_hash)
    return ("content", source, text_hash)


def _dedupe_documents(documents: list[Document]) -> list[Document]:
    seen: set[tuple[str, ...]] = set()
    unique_documents: list[Document] = []
    for doc in documents:
        key = _document_dedupe_key(doc)
        if key in seen:
            continue
        seen.add(key)
        unique_documents.append(doc)
    return unique_documents


def retrieve_documents(question: str, *, embedding_function=None) -> list[Document]:
    ensure_default_documents_indexed(embedding_function)
    store = get_vector_store(embedding_function)
    search_kwargs = {"k": RAG_TOP_K}
    if RAG_SEARCH_TYPE == "mmr":
        search_kwargs = {
            "k": RAG_TOP_K,
            "fetch_k": RAG_FETCH_K,
            "lambda_mult": 0.5,
        }
        retriever = store.as_retriever(search_type="mmr", search_kwargs=search_kwargs)
    else:
        search_kwargs = {"k": RAG_FETCH_K}
        retriever = store.as_retriever(search_kwargs=search_kwargs)

    documents = retriever.invoke(question)
    return _dedupe_documents(documents)[:RAG_TOP_K]


def documents_to_context(documents: list[Document]) -> str:
    parts: list[str] = []
    used_characters = 0
    for index, doc in enumerate(documents, start=1):
        metadata = doc.metadata
        source = metadata.get("original_filename") or metadata.get("source", "未知来源")
        location_parts = []
        if metadata.get("page_number") is not None:
            location_parts.append(f"page={metadata['page_number']}")
        if metadata.get("element_index") is not None:
            location_parts.append(f"element={metadata['element_index']}")
        if metadata.get("chunk_index") is not None:
            location_parts.append(f"chunk={metadata['chunk_index']}")
        location = f" | {' | '.join(location_parts)}" if location_parts else ""
        body = doc.page_content.strip()
        if not body:
            continue

        block = f"[{index}] 来源: {source}{location}\n{body}"
        remaining = RAG_CONTEXT_MAX_CHARS - used_characters
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip()
        parts.append(block)
        used_characters += len(block)

    return "\n\n".join(parts)


def document_sources(documents: list[Document]) -> list[str]:
    return sorted({
        doc.metadata.get("original_filename") or doc.metadata.get("source", "未知来源")
        for doc in documents
    })


def ask_document(question: str, *, llm, embedding_function=None) -> tuple[str, list[str]]:
    documents = retrieve_documents(question, embedding_function=embedding_function)
    context = documents_to_context(documents)
    answer = _generate_answer(context=context, question=question, llm=llm)
    sources = document_sources(documents)

    return answer, sources
