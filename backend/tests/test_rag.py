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
