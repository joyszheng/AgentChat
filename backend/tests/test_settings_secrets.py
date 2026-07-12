from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, schemas
from app.database import Base
from app.routers.settings import (
    _fetch_model_options,
    _resolve_model_options_config,
    _value_for_storage,
)
from app.services.encryption import decrypt_value, encrypt_value, mask_sensitive_value


def test_masked_secret_keeps_existing_ciphertext():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    plaintext = "sk-original-secret"
    ciphertext = encrypt_value(plaintext)

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="llm_api_key",
            value=ciphertext,
            category="ai",
            is_encrypted=True,
            description=None,
        )
        masked = mask_sensitive_value(plaintext, show_first=3, show_last=3)
        setting_data = schemas.SystemSettingCreate(
            key="llm_api_key",
            value=masked,
            category="ai",
            is_encrypted=True,
        )

        assert _value_for_storage(db, setting_data) == ciphertext


def test_changed_secret_is_encrypted_as_new_value():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="llm_api_key",
            value=encrypt_value("sk-old-secret"),
            category="ai",
            is_encrypted=True,
            description=None,
        )
        setting_data = schemas.SystemSettingCreate(
            key="llm_api_key",
            value="sk-new-secret",
            category="ai",
            is_encrypted=True,
        )

        stored_value = _value_for_storage(db, setting_data)

    assert decrypt_value(stored_value) == "sk-new-secret"


def test_mask_lookalike_value_is_never_stored_as_secret():
    """回传的掩码即使与当前掩码格式不一致，也不能被当成新密钥加密（smtp 密码被污染的根因）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    ciphertext = encrypt_value("sk-real-secret")

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="llm_api_key",
            value=ciphertext,
            category="ai",
            is_encrypted=True,
            description=None,
        )
        setting_data = schemas.SystemSettingCreate(
            key="llm_api_key",
            value="abc******xyz",
            category="ai",
            is_encrypted=True,
        )

        stored = _value_for_storage(db, setting_data)

    assert stored == ciphertext  # 保留原密文，未把掩码加密存储


def test_masked_value_without_existing_secret_is_not_stored():
    """没有可保留的已有密钥时，掩码值也不能被存成密钥（应为空，回退到 env/默认）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        setting_data = schemas.SystemSettingCreate(
            key="smtp_password",
            value="wxw******fd",
            category="email",
            is_encrypted=True,
        )

        stored = _value_for_storage(db, setting_data)

    assert stored == ""


def test_model_options_uses_database_secret_when_request_has_mask(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        crud.upsert_system_setting(
            db,
            key="llm_base_url",
            value="https://llm.example.com/v1",
            category="ai",
            is_encrypted=False,
            description=None,
        )
        crud.upsert_system_setting(
            db,
            key="llm_api_key",
            value=encrypt_value("sk-real-secret"),
            category="ai",
            is_encrypted=True,
            description=None,
        )
        request = schemas.ModelOptionsRequest(
            kind="llm",
            base_url="https://new.example.com/v1",
            api_key="sk-***ret",
        )

        base_url, api_key = _resolve_model_options_config(db, request)

    assert base_url == "https://new.example.com/v1"
    assert api_key == "sk-real-secret"


def test_fetch_model_options_parses_openai_models_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "vendor/chat-a", "owned_by": "vendor"},
                    {"id": "vendor/chat-a", "owned_by": "vendor"},
                    {"id": "vendor/chat-b"},
                ]
            }

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.routers.settings.httpx.get", fake_get)

    models = _fetch_model_options("https://llm.example.com/v1/", "sk-test")

    assert captured["url"] == "https://llm.example.com/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["timeout"] == 10
    assert [model.id for model in models] == ["vendor/chat-a", "vendor/chat-b"]
