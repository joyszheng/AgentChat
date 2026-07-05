from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud
from app.ai.config import get_embeddings_from_config, get_llm_from_config
from app.database import Base
from app.main import app
from app.routers import ai as ai_router
from app.services.config import migrate_legacy_llm_api_key


def test_llm_config_reads_latest_database_model():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="llm_model",
            value="database/model-one",
            category="ai",
            is_encrypted=False,
            description=None,
        )
        crud.upsert_system_setting(
            db,
            key="llm_api_key",
            value="database-api-key",
            category="ai",
            is_encrypted=False,
            description=None,
        )
        configured_llm = get_llm_from_config(db)
        assert configured_llm.model_name == "database/model-one"
        assert configured_llm.openai_api_key.get_secret_value() == "database-api-key"

        crud.upsert_system_setting(
            db,
            key="llm_model",
            value="database/model-two",
            category="ai",
            is_encrypted=False,
            description=None,
        )
        assert get_llm_from_config(db).model_name == "database/model-two"


def test_llm_and_embeddings_use_independent_providers():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    values = {
        "llm_base_url": "https://llm.example.com/v1",
        "llm_model": "vendor-a/chat-model",
        "llm_api_key": "llm-secret",
        "embedding_base_url": "https://embedding.example.com/v1",
        "embedding_model": "vendor-b/embedding-model",
        "embedding_api_key": "embedding-secret",
        "agentchat_embedding_dimensions": "1536",
    }

    with session_factory() as db:
        for key, value in values.items():
            crud.upsert_system_setting(
                db,
                key=key,
                value=value,
                category="ai",
                is_encrypted=False,
                description=None,
            )

        configured_llm = get_llm_from_config(db)
        configured_embeddings = get_embeddings_from_config(db)

    assert str(configured_llm.openai_api_base) == "https://llm.example.com/v1"
    assert configured_llm.model_name == "vendor-a/chat-model"
    assert configured_llm.openai_api_key.get_secret_value() == "llm-secret"
    assert str(configured_embeddings.openai_api_base) == "https://embedding.example.com/v1"
    assert configured_embeddings.model == "vendor-b/embedding-model"
    assert configured_embeddings.openai_api_key.get_secret_value() == "embedding-secret"
    assert configured_embeddings.dimensions == 1536


def test_legacy_llm_api_key_setting_is_migrated():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="glm_api_key",
            value="encrypted-value-is-preserved",
            category="ai",
            is_encrypted=True,
            description="AI API 密钥",
        )

        assert migrate_legacy_llm_api_key(db) is True
        assert crud.get_system_setting(db, "glm_api_key") is None
        migrated = crud.get_system_setting(db, "llm_api_key")
        assert migrated is not None
        assert migrated.value == "encrypted-value-is-preserved"
        assert migrated.is_encrypted is True


def test_chat_endpoint_builds_chain_from_request_llm(monkeypatch):
    selected_llm = object()
    received_llms = []
    fake_chain = SimpleNamespace(
        invoke=lambda _input: SimpleNamespace(content="动态模型回答")
    )

    monkeypatch.setattr(ai_router, "get_llm_from_config", lambda _db: selected_llm)

    def fake_create_chat_chain(llm):
        received_llms.append(llm)
        return fake_chain

    monkeypatch.setattr(ai_router, "create_chat_chain", fake_create_chat_chain)

    response = TestClient(app).post(
        "/ai/chat",
        json={"message": "[TEST] 使用后台模型"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "动态模型回答"
    assert received_llms == [selected_llm]
