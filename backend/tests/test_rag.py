from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.ai import rag


def test_generate_answer_retries_empty_model_response(monkeypatch):
    responses = iter([SimpleNamespace(content=""), SimpleNamespace(content="answer")])
    fake_chain = SimpleNamespace(invoke=lambda _input: next(responses))
    monkeypatch.setattr(rag, "create_rag_chain", lambda _llm: fake_chain)

    assert rag._generate_answer(
        context="context",
        question="question",
        llm=object(),
    ) == "answer"


def test_generate_answer_rejects_repeated_empty_responses(monkeypatch):
    fake_chain = SimpleNamespace(invoke=lambda _input: SimpleNamespace(content=""))
    monkeypatch.setattr(rag, "create_rag_chain", lambda _llm: fake_chain)

    with pytest.raises(RuntimeError, match="empty response"):
        rag._generate_answer(context="context", question="question", llm=object())


def test_add_documents_to_index_tags_chunks_with_document_id(monkeypatch):
    captured = {}

    def fake_upsert(documents, **kwargs):
        captured["documents"] = documents
        captured["kwargs"] = kwargs

    monkeypatch.setattr(rag, "ensure_default_documents_indexed", lambda *_args: None)
    monkeypatch.setattr(rag, "_upsert_documents", fake_upsert)

    chunk_count = rag.add_documents_to_index(
        [Document(page_content="hello world", metadata={"source": "guide.md"})],
        document_id=7,
    )

    assert chunk_count == 1
    assert captured["documents"][0].metadata["document_id"] == 7
    assert captured["documents"][0].metadata["chunk_index"] == 0
    assert captured["documents"][0].metadata["chunk_total"] == 1
    assert captured["kwargs"]["document_id"] == 7


def test_chunk_ids_use_file_hash_for_stable_duplicate_upserts():
    first = Document(
        page_content="same content",
        metadata={
            "source": "uploads/first.txt",
            "file_sha256": "abc123",
            "element_index": 0,
            "chunk_index": 0,
        },
    )
    duplicate_upload = Document(
        page_content="same content",
        metadata={
            "source": "uploads/second.txt",
            "file_sha256": "abc123",
            "element_index": 0,
            "chunk_index": 0,
        },
    )

    assert rag._chunk_ids([first]) == rag._chunk_ids([duplicate_upload])


def test_retrieve_documents_fetches_then_dedupes(monkeypatch):
    first = Document(
        page_content="alpha",
        metadata={"file_sha256": "file-a", "chunk_index": 0},
    )
    duplicate = Document(
        page_content="alpha",
        metadata={"file_sha256": "file-a", "chunk_index": 0},
    )
    second = Document(
        page_content="beta",
        metadata={"file_sha256": "file-a", "chunk_index": 1},
    )
    third = Document(
        page_content="gamma",
        metadata={"file_sha256": "file-a", "chunk_index": 2},
    )
    calls = {}

    class FakeRetriever:
        def invoke(self, question):
            calls["question"] = question
            return [first, duplicate, second, third]

    class FakeStore:
        def as_retriever(self, **kwargs):
            calls["kwargs"] = kwargs
            return FakeRetriever()

    monkeypatch.setattr(rag, "ensure_default_documents_indexed", lambda *_args: None)
    monkeypatch.setattr(rag, "get_vector_store", lambda _embedding: FakeStore())
    monkeypatch.setattr(rag, "RAG_SEARCH_TYPE", "similarity")
    monkeypatch.setattr(rag, "RAG_FETCH_K", 4)
    monkeypatch.setattr(rag, "RAG_TOP_K", 2)

    documents = rag.retrieve_documents("question", embedding_function=object())

    assert documents == [first, second]
    assert calls["question"] == "question"
    assert calls["kwargs"] == {"search_kwargs": {"k": 4}}


def test_documents_to_context_includes_source_metadata(monkeypatch):
    monkeypatch.setattr(rag, "RAG_CONTEXT_MAX_CHARS", 1000)

    context = rag.documents_to_context([
        Document(
            page_content="answer evidence",
            metadata={
                "original_filename": "guide.pdf",
                "page_number": 3,
                "element_index": 5,
                "chunk_index": 2,
            },
        )
    ])

    assert "[1] 来源: guide.pdf | page=3 | element=5 | chunk=2" in context
    assert "answer evidence" in context


def test_delete_document_from_index_prefers_document_id(monkeypatch):
    calls = {"expressions": []}

    class FakeClient:
        def has_collection(self, *, collection_name):
            calls["collection"] = collection_name
            return True

    class FakeStore:
        client = FakeClient()

        def get_pks(self, expression, **kwargs):
            calls["expressions"].append(expression)
            calls["get_pks_kwargs"] = kwargs
            return ["chunk-1", "chunk-2"]

        def delete(self, *, ids, **kwargs):
            calls["ids"] = ids
            calls["delete_kwargs"] = kwargs
            return True

    monkeypatch.setattr(rag, "get_vector_store", lambda: FakeStore())

    deleted = rag.delete_document_from_index(
        file_sha256="abc123",
        source="unused.txt",
        document_id=7,
    )

    assert deleted == 2
    assert calls["expressions"] == ['metadata["document_id"] == 7']
    assert calls["ids"] == ["chunk-1", "chunk-2"]


def test_delete_document_from_index_falls_back_to_file_hash(monkeypatch):
    calls = {"expressions": []}

    class FakeClient:
        def has_collection(self, *, collection_name):
            calls["collection"] = collection_name
            return True

    class FakeStore:
        client = FakeClient()

        def get_pks(self, expression, **kwargs):
            calls["expressions"].append(expression)
            if expression == 'metadata["file_sha256"] == "abc123"':
                return ["chunk-1"]
            return []

        def delete(self, *, ids, **kwargs):
            calls["ids"] = ids
            return True

    monkeypatch.setattr(rag, "get_vector_store", lambda: FakeStore())

    deleted = rag.delete_document_from_index(
        document_id=7,
        file_sha256="abc123",
        source="unused.txt",
    )

    assert deleted == 1
    assert calls["expressions"] == [
        'metadata["document_id"] == 7',
        'metadata["file_sha256"] == "abc123"',
    ]
    assert calls["ids"] == ["chunk-1"]
