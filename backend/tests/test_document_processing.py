import sys
from types import ModuleType

import pytest

from app.ai.document_processing import (
    DocumentProcessingError,
    clean_text,
    load_upload_documents,
)


def test_clean_text_normalizes_whitespace():
    text = "  第一段\r\n\r\n\r\n  第二段\t内容\x00  "

    assert clean_text(text) == "第一段\n\n第二段 内容"


def test_load_upload_documents_rejects_unsupported_extension(tmp_path):
    file_path = tmp_path / "data.xlsx"
    file_path.write_text("name,value", encoding="utf-8")

    with pytest.raises(DocumentProcessingError, match="暂不支持"):
        load_upload_documents(file_path)


def test_load_upload_documents_uses_pypdf_for_pdf(monkeypatch, tmp_path):
    file_path = tmp_path / "guide.pdf"
    file_path.write_text("# 标题\n\n正文", encoding="utf-8")

    calls = []

    class FakePage:
        def extract_text(self):
            calls.append("extract_text")
            return "  文档正文\r\n\r\n"

    class FakePdfReader:
        def __init__(self, path):
            calls.append(path)
            self.pages = [FakePage()]

    pypdf_module = ModuleType("pypdf")
    pypdf_module.PdfReader = FakePdfReader

    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)

    processed = load_upload_documents(
        file_path,
        original_filename="guide.pdf",
        content_type="application/pdf",
    )

    assert calls == [file_path, "extract_text"]
    assert len(processed.documents) == 1
    assert processed.documents[0].page_content == "文档正文"
    assert processed.documents[0].metadata["original_filename"] == "guide.pdf"
    assert processed.documents[0].metadata["page_number"] == 1
    assert processed.documents[0].metadata["parser"] == "pypdf"
