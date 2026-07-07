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
    assert captured["kwargs"]["document_id"] == 7


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
