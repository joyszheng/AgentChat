from types import SimpleNamespace

import pytest

from app.ai import rag


def test_generate_answer_retries_empty_model_response(monkeypatch):
    responses = iter([SimpleNamespace(content=""), SimpleNamespace(content="answer")])
    fake_chain = SimpleNamespace(invoke=lambda _input: next(responses))
    monkeypatch.setattr(rag, "rag_chain", fake_chain)

    assert rag._generate_answer(context="context", question="question") == "answer"


def test_generate_answer_rejects_repeated_empty_responses(monkeypatch):
    fake_chain = SimpleNamespace(invoke=lambda _input: SimpleNamespace(content=""))
    monkeypatch.setattr(rag, "rag_chain", fake_chain)

    with pytest.raises(RuntimeError, match="empty response"):
        rag._generate_answer(context="context", question="question")


def test_delete_document_from_index_uses_file_hash(monkeypatch):
    calls = {}

    class FakeClient:
        def has_collection(self, *, collection_name):
            calls["collection"] = collection_name
            return True

    class FakeStore:
        client = FakeClient()

        def get_pks(self, expression, **kwargs):
            calls["expression"] = expression
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
    assert calls["expression"] == 'metadata["file_sha256"] == "abc123"'
    assert calls["ids"] == ["chunk-1", "chunk-2"]
