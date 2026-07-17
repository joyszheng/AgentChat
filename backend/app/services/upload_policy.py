import os
from pathlib import Path


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_DOCX_BYTES = 30 * 1024 * 1024
DEFAULT_MAX_TEXT_BYTES = 10 * 1024 * 1024
DEFAULT_CHUNK_READ_BYTES = 1024 * 1024
DEFAULT_DOCUMENT_MAX_TEXT_CHARS = 1_000_000
DEFAULT_DOCUMENT_MAX_CHUNKS = 3_000
MULTIPART_OVERHEAD_ALLOWANCE_BYTES = 1024 * 1024

SUPPORTED_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".md", ".txt")


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def get_default_max_upload_bytes() -> int:
    return _get_int_env("AGENTCHAT_UPLOAD_MAX_BYTES", DEFAULT_MAX_UPLOAD_BYTES)


def get_upload_chunk_read_bytes() -> int:
    return _get_int_env("AGENTCHAT_UPLOAD_CHUNK_READ_BYTES", DEFAULT_CHUNK_READ_BYTES)


def get_document_max_text_chars() -> int:
    return _get_int_env("AGENTCHAT_DOCUMENT_MAX_TEXT_CHARS", DEFAULT_DOCUMENT_MAX_TEXT_CHARS)


def get_document_max_chunks() -> int:
    return _get_int_env("AGENTCHAT_DOCUMENT_MAX_CHUNKS", DEFAULT_DOCUMENT_MAX_CHUNKS)


def upload_limit_for_suffix(suffix: str) -> int:
    normalized = suffix.lower()
    default = get_default_max_upload_bytes()
    if normalized == ".pdf":
        return _get_int_env("AGENTCHAT_UPLOAD_MAX_PDF_BYTES", default)
    if normalized == ".docx":
        return _get_int_env("AGENTCHAT_UPLOAD_MAX_DOCX_BYTES", DEFAULT_MAX_DOCX_BYTES)
    if normalized in {".md", ".txt"}:
        return _get_int_env("AGENTCHAT_UPLOAD_MAX_TEXT_BYTES", DEFAULT_MAX_TEXT_BYTES)
    return default


def upload_policy() -> dict:
    type_limits = {
        extension: upload_limit_for_suffix(extension)
        for extension in SUPPORTED_UPLOAD_EXTENSIONS
    }
    return {
        "max_bytes": max(type_limits.values()),
        "allowed_extensions": list(SUPPORTED_UPLOAD_EXTENSIONS),
        "type_limits": type_limits,
        "chunk_read_bytes": get_upload_chunk_read_bytes(),
        "document_max_text_chars": get_document_max_text_chars(),
        "document_max_chunks": get_document_max_chunks(),
    }


def content_length_is_definitely_too_large(content_length: str | None, max_bytes: int) -> bool:
    if not content_length:
        return False
    try:
        request_bytes = int(content_length)
    except ValueError:
        return False

    allowance = max(MULTIPART_OVERHEAD_ALLOWANCE_BYTES, get_upload_chunk_read_bytes())
    return request_bytes > max_bytes + allowance


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024


def limit_message(filename: str | Path, max_bytes: int, actual_bytes: int | None = None) -> str:
    suffix = Path(filename).suffix.upper().lstrip(".") or "file"
    base = f"{suffix} file exceeds the upload limit of {format_bytes(max_bytes)}"
    if actual_bytes is not None:
        return f"{base}; received at least {format_bytes(actual_bytes)}"
    return base
