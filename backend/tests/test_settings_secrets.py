from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, schemas
from app.database import Base
from app.routers.settings import _value_for_storage
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
