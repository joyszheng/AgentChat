import importlib
import sys
from types import ModuleType

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.ai.document_processing import DocumentProcessingError, ProcessedDocument


def test_upload_indexes_saved_file(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)

    def fake_ingest_upload(file_path, *, original_filename=None, content_type=None):
        assert file_path.exists()
        assert original_filename == "guide.md"
        assert content_type == "text/markdown"
        return (
            ProcessedDocument(
                documents=[
                    Document(
                        page_content="测试文档",
                        metadata={"source": str(file_path)},
                    )
                ],
            ),
            1,
        )

    monkeypatch.setattr(main_module, "ingest_upload", fake_ingest_upload)

    response = TestClient(main_module.app).post(
        "/upload",
        files={"file": ("guide.md", b"# title\n\nbody", "text/markdown")},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["original_filename"] == "guide.md"
    assert data["indexed"] is False
    assert data["status"] == "processing"
    assert isinstance(data["document_id"], int)
    assert data["document_count"] == 0
    assert data["chunk_count"] == 0

    documents_response = TestClient(main_module.app).get("/documents")
    assert documents_response.status_code == 200
    documents = documents_response.json()
    assert documents[0]["id"] == data["document_id"]
    assert documents[0]["status"] == "indexed"


def test_background_upload_records_document_processing_failure(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)

    def fake_ingest_upload(*_args, **_kwargs):
        raise DocumentProcessingError("未提取到可用文本，当前版本暂未启用 OCR")

    monkeypatch.setattr(main_module, "ingest_upload", fake_ingest_upload)

    response = TestClient(main_module.app).post(
        "/upload",
        files={"file": ("scan.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "processing"

    documents_response = TestClient(main_module.app).get("/documents")
    assert documents_response.status_code == 200
    documents = documents_response.json()
    assert documents[0]["status"] == "failed"
    assert documents[0]["error_message"] == "未提取到可用文本，当前版本暂未启用 OCR"


def _load_main_with_fake_rag(monkeypatch, tmp_path):
    fake_rag = ModuleType("app.ai.rag")
    fake_rag.ask_document = lambda _question: ("", [])
    fake_rag.ingest_upload = lambda *_args, **_kwargs: (ProcessedDocument(documents=[]), 0)

    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GLM_API_KEY", "test-api-key")
    monkeypatch.setitem(sys.modules, "app.ai.rag", fake_rag)
    sys.modules.pop("app.crud", None)
    sys.modules.pop("app.database", None)
    sys.modules.pop("app.ai.models", None)
    sys.modules.pop("app.models", None)
    sys.modules.pop("app.routers.ai", None)
    sys.modules.pop("app.main", None)

    return importlib.import_module("app.main")
