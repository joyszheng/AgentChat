import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.ai.document_processing import DocumentProcessingError, ProcessedDocument


def test_upload_indexes_saved_file(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)
    reported_stages = []

    def fake_ingest_upload(
        file_path,
        *,
        original_filename=None,
        content_type=None,
        document_id=None,
        progress_callback=None,
        embedding_function=None,
    ):
        assert file_path.exists()
        assert original_filename == "guide.md"
        assert content_type == "text/markdown"
        assert embedding_function is not None
        assert isinstance(document_id, int)
        for stage in ("parsing", "chunking", "indexing"):
            progress_callback(stage)
            reported_stages.append(stage)
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
    assert reported_stages == ["parsing", "chunking", "indexing"]

    download_response = TestClient(main_module.app).get(
        f"/documents/{data['document_id']}/download",
        headers={"Origin": "https://frp-six.com:46189"},
    )
    assert download_response.status_code == 200
    assert download_response.content == b"# title\n\nbody"
    assert download_response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in download_response.headers["content-disposition"]
    assert "guide.md" in download_response.headers["content-disposition"]
    assert download_response.headers["access-control-expose-headers"] == "Content-Disposition"

    progress_response = TestClient(main_module.app).get(
        f"/documents/{data['document_id']}/progress"
    )
    assert progress_response.status_code == 200
    assert progress_response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(progress_response.text)
    assert events == [
        {
            "event": "complete",
            "data": {
                "document_id": data["document_id"],
                "filename": "guide.md",
                "status": "indexed",
                "progress": 100,
                "message": "文档处理完成",
                "document_count": 1,
                "chunk_count": 1,
                "warnings": [],
                "error_message": None,
                "updated_at": events[0]["data"]["updated_at"],
            },
        }
    ]

    vector_cleanup_calls = []

    def fake_delete_document_from_index(**kwargs):
        vector_cleanup_calls.append(kwargs)
        return 1

    monkeypatch.setattr(
        main_module,
        "delete_document_from_index",
        fake_delete_document_from_index,
    )
    delete_response = TestClient(main_module.app).delete(
        f"/documents/{data['document_id']}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {
        "document_id": data["document_id"],
        "deleted": True,
        "file_deleted": True,
        "vector_chunks_deleted": 1,
    }
    assert vector_cleanup_calls[0]["file_sha256"]
    assert not Path(data["saved_to"]).exists()
    assert TestClient(main_module.app).get("/documents").json() == []
    assert (
        TestClient(main_module.app)
        .get(f"/documents/{data['document_id']}/download")
        .status_code
        == 404
    )
    assert (
        TestClient(main_module.app)
        .get(f"/documents/{data['document_id']}/progress")
        .status_code
        == 404
    )


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

    progress_response = TestClient(main_module.app).get(
        f"/documents/{documents[0]['id']}/progress"
    )
    events = _parse_sse_events(progress_response.text)
    assert events[0]["event"] == "failed"
    assert events[0]["data"]["status"] == "failed"
    assert events[0]["data"]["progress"] == 100
    assert events[0]["data"]["error_message"] == "未提取到可用文本，当前版本暂未启用 OCR"

    delete_response = TestClient(main_module.app).delete(
        f"/documents/{documents[0]['id']}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["file_deleted"] is True
    assert delete_response.json()["vector_chunks_deleted"] == 0
    assert not Path(documents[0]["saved_to"]).exists()


def test_upload_rejects_same_filename_and_same_content(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)

    client = TestClient(main_module.app)
    first_response = client.post(
        "/upload",
        files={"file": ("guide.md", b"# title\n\nbody", "text/markdown")},
    )
    duplicate_response = client.post(
        "/upload",
        files={"file": ("guide.md", b"# title\n\nbody", "text/markdown")},
    )
    renamed_response = client.post(
        "/upload",
        files={"file": ("guide-copy.md", b"# title\n\nbody", "text/markdown")},
    )

    assert first_response.status_code == 202
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "同名且内容相同的文档已存在，请勿重复上传"
    }
    assert renamed_response.status_code == 202
    assert len(client.get("/documents").json()) == 2
    assert len(list(upload_dir.iterdir())) == 2


def test_upload_rejects_unsupported_format_before_saving(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)

    client = TestClient(main_module.app)
    response = client.post(
        "/upload",
        files={"file": ("legacy.doc", b"legacy word content", "application/msword")},
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": (
            "暂不支持 .doc 文件，当前支持格式：.docx、.md、.pdf、.txt；"
            "旧版 .doc 文件请先转换为 .docx"
        )
    }
    assert list(upload_dir.iterdir()) == []
    assert client.get("/documents").json() == []
    assert client.get("/documents/999/progress").status_code == 404


def test_delete_document_rejects_active_processing(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    crud = importlib.import_module("app.crud")
    database = importlib.import_module("app.database")
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)
    file_path = upload_dir / "processing.txt"
    file_path.write_text("processing", encoding="utf-8")

    with database.SessionLocal() as db:
        document = crud.create_uploaded_document(
            db,
            original_filename="processing.txt",
            stored_filename=file_path.name,
            content_type="text/plain",
            file_ext=".txt",
            size_bytes=file_path.stat().st_size,
            saved_to=str(file_path),
        )
        crud.mark_uploaded_document_processing(db, document.id)
        document_id = document.id

    response = TestClient(main_module.app).delete(f"/documents/{document_id}")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "文档正在处理中，请等待处理完成或失败后再删除"
    }
    assert file_path.exists()
    assert len(TestClient(main_module.app).get("/documents").json()) == 1

    monkeypatch.setattr(main_module, "DOCUMENT_PROGRESS_STREAM_LIFETIME", 0)
    progress_response = TestClient(main_module.app).get(
        f"/documents/{document_id}/progress"
    )
    progress_events = _parse_sse_events(progress_response.text)
    assert [event["event"] for event in progress_events] == ["progress", "reconnect"]


def test_startup_marks_interrupted_upload_as_failed(monkeypatch, tmp_path):
    main_module = _load_main_with_fake_rag(monkeypatch, tmp_path)
    crud = importlib.import_module("app.crud")
    database = importlib.import_module("app.database")
    file_path = tmp_path / "interrupted.txt"
    file_path.write_text("interrupted", encoding="utf-8")

    with database.SessionLocal() as db:
        document = crud.create_uploaded_document(
            db,
            original_filename="interrupted.txt",
            stored_filename=file_path.name,
            content_type="text/plain",
            file_ext=".txt",
            size_bytes=file_path.stat().st_size,
            saved_to=str(file_path),
        )
        crud.mark_uploaded_document_stage(db, document.id, stage="indexing")
        document_id = document.id

    with TestClient(main_module.app) as client:
        documents = client.get("/documents").json()
        progress_response = client.get(f"/documents/{document_id}/progress")

    assert documents[0]["status"] == "failed"
    assert documents[0]["error_message"] == "服务重启导致后台处理任务中断，请删除后重新上传"
    progress_events = _parse_sse_events(progress_response.text)
    assert progress_events[0]["event"] == "failed"


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for raw_event in body.strip().split("\n\n"):
        lines = raw_event.splitlines()
        event_name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append({"event": event_name, "data": json.loads(data)})
    return events


def _load_main_with_fake_rag(monkeypatch, tmp_path):
    fake_rag = ModuleType("app.ai.rag")
    fake_rag.ask_document = lambda _question, **_kwargs: ("", [])
    fake_rag.ingest_upload = lambda *_args, **_kwargs: (ProcessedDocument(documents=[]), 0)
    fake_rag.delete_document_from_index = lambda **_kwargs: 0

    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("SMTP_ENABLED", "false")
    monkeypatch.setitem(sys.modules, "app.ai.rag", fake_rag)
    sys.modules.pop("app.crud", None)
    sys.modules.pop("app.database", None)
    sys.modules.pop("app.ai.models", None)
    sys.modules.pop("app.models", None)
    sys.modules.pop("app.routers.ai", None)
    sys.modules.pop("app.main", None)

    main_module = importlib.import_module("app.main")
    main_module.app.dependency_overrides[main_module.require_auth] = (
        lambda: SimpleNamespace(id=1, username="tester", role="admin")
    )
    return main_module
