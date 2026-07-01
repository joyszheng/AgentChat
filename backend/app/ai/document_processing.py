from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
logger = logging.getLogger("uvicorn.error")


class DocumentProcessingError(ValueError):
    """Raised when an uploaded document cannot be prepared for indexing."""


@dataclass(frozen=True)
class ProcessedDocument:
    documents: list[Document]
    warnings: list[str] = field(default_factory=list)


def clean_text(text: str) -> str:
    """Normalize extracted text without destroying paragraph boundaries."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()


def load_upload_documents(
    file_path: Path,
    *,
    original_filename: str | None = None,
    content_type: str | None = None,
) -> ProcessedDocument:
    """Extract, clean, and wrap an uploaded file as LangChain documents."""

    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentProcessingError(f"暂不支持 {suffix or '无扩展名'} 文件，支持格式：{supported}")

    if suffix == ".pdf":
        return _load_pdf_documents(
            path,
            original_filename=original_filename,
            content_type=content_type,
        )

    return _load_unstructured_documents(
        path,
        original_filename=original_filename,
        content_type=content_type,
    )


def _load_pdf_documents(
    path: Path,
    *,
    original_filename: str | None,
    content_type: str | None,
) -> ProcessedDocument:
    """Extract text-layer PDF pages without loading OCR/inference dependencies."""

    display_name = original_filename or path.name
    import_started_at = time.perf_counter()
    logger.info("[document] PDF parser import started file=%r parser=pypdf", display_name)
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        logger.exception(
            "[document] PDF parser import failed file=%r elapsed=%.2fs error=%s",
            display_name,
            time.perf_counter() - import_started_at,
            exc,
        )
        raise DocumentProcessingError("缺少 pypdf 依赖，请先安装 AI 可选依赖") from exc
    logger.info(
        "[document] PDF parser import completed file=%r elapsed=%.2fs",
        display_name,
        time.perf_counter() - import_started_at,
    )

    started_at = time.perf_counter()
    logger.info(
        "[document] Parsing started file=%r type=.pdf parser=pypdf size=%s bytes",
        display_name,
        path.stat().st_size,
    )
    try:
        reader = PdfReader(path)
    except Exception as exc:
        logger.exception(
            "[document] Parsing failed file=%r elapsed=%.2fs error=%s",
            display_name,
            time.perf_counter() - started_at,
            exc,
        )
        raise DocumentProcessingError(f"文档解析失败：{exc}") from exc

    documents: list[Document] = []
    warnings: list[str] = []
    file_hash = _file_sha256(path)

    for index, page in enumerate(reader.pages):
        text = clean_text(page.extract_text() or "")
        if not text:
            continue

        metadata = _clean_metadata({
            "source": str(path),
            "original_filename": display_name,
            "content_type": content_type,
            "file_ext": ".pdf",
            "element_index": index,
            "element_type": "Page",
            "page_number": index + 1,
            "file_sha256": file_hash,
            "parser": "pypdf",
        })

        documents.append(Document(page_content=text, metadata=metadata))

    if not documents:
        warnings.append("未提取到可用文本，当前版本暂未启用 OCR")
        logger.warning(
            "[document] Parsing produced no text file=%r pages=%s elapsed=%.2fs",
            display_name,
            len(reader.pages),
            time.perf_counter() - started_at,
        )
        raise DocumentProcessingError(warnings[0])

    logger.info(
        "[document] Parsing completed file=%r pages=%s documents=%s elapsed=%.2fs",
        display_name,
        len(reader.pages),
        len(documents),
        time.perf_counter() - started_at,
    )
    return ProcessedDocument(documents=documents, warnings=warnings)


def _load_unstructured_documents(
    path: Path,
    *,
    original_filename: str | None,
    content_type: str | None,
) -> ProcessedDocument:
    """Extract supported non-PDF formats with unstructured."""

    display_name = original_filename or path.name
    import_started_at = time.perf_counter()
    logger.info("[document] Parser dependency import started file=%r", display_name)
    try:
        from unstructured.partition.auto import partition
    except ImportError as exc:
        logger.exception(
            "[document] Parser dependency import failed file=%r elapsed=%.2fs error=%s",
            display_name,
            time.perf_counter() - import_started_at,
            exc,
        )
        raise DocumentProcessingError("缺少 unstructured 依赖，请先安装 AI 可选依赖") from exc
    logger.info(
        "[document] Parser dependency import completed file=%r elapsed=%.2fs",
        display_name,
        time.perf_counter() - import_started_at,
    )

    started_at = time.perf_counter()
    logger.info(
        "[document] Parsing started file=%r type=%s parser=unstructured size=%s bytes",
        display_name,
        path.suffix.lower(),
        path.stat().st_size,
    )
    try:
        elements = partition(filename=str(path))
    except Exception as exc:
        logger.exception(
            "[document] Parsing failed file=%r elapsed=%.2fs error=%s",
            display_name,
            time.perf_counter() - started_at,
            exc,
        )
        raise DocumentProcessingError(f"文档解析失败：{exc}") from exc

    documents: list[Document] = []
    warnings: list[str] = []
    file_hash = _file_sha256(path)

    for index, element in enumerate(elements):
        text = clean_text(str(getattr(element, "text", "") or ""))
        if not text:
            continue

        metadata = _clean_metadata({
            "source": str(path),
            "original_filename": display_name,
            "content_type": content_type,
            "file_ext": path.suffix.lower(),
            "element_index": index,
            "element_type": element.__class__.__name__,
            "file_sha256": file_hash,
            "parser": "unstructured",
        })
        metadata.update(_element_metadata(element))

        documents.append(Document(page_content=text, metadata=metadata))

    if not documents:
        warnings.append("未提取到可用文本")
        logger.warning(
            "[document] Parsing produced no text file=%r elements=%s elapsed=%.2fs",
            display_name,
            len(elements),
            time.perf_counter() - started_at,
        )
        raise DocumentProcessingError(warnings[0])

    logger.info(
        "[document] Parsing completed file=%r elements=%s documents=%s elapsed=%.2fs",
        display_name,
        len(elements),
        len(documents),
        time.perf_counter() - started_at,
    )
    return ProcessedDocument(documents=documents, warnings=warnings)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _element_metadata(element: Any) -> dict[str, Any]:
    metadata = getattr(element, "metadata", None)
    if metadata is None:
        return {}

    if hasattr(metadata, "to_dict"):
        return _clean_metadata(metadata.to_dict())

    if isinstance(metadata, dict):
        return _clean_metadata(metadata)

    return {}


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if value is not None and isinstance(value, str | int | float | bool)
    }
