"""Extract plain text from local document bytes for LLM prompts."""

from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)


def extract_text_from_bytes(
    data: bytes,
    *,
    filename: str = "",
    mime_hint: str | None = None,
    content_type: str | None = None,
) -> str:
    """
    Best-effort text extraction for QA prompts.

    Supports plain text and PDF. Other types return empty string with a log warning.
    """
    mime = (content_type or mime_hint or "").lower()
    name = (filename or "").lower()

    if "pdf" in mime or name.endswith(".pdf"):
        return _extract_pdf(data)

    if "text/" in mime or name.endswith(".txt"):
        return _decode_text(data)

    # Some uploads are sniffed as text/plain even when filename suggests .doc
    if "plain" in mime:
        return _decode_text(data)

    if data[:5] == b"%PDF-":
        return _extract_pdf(data)

    # Last resort: try UTF-8 decode if mostly printable
    try:
        text = _decode_text(data)
        if len(text.strip()) > 50:
            return text
    except Exception:
        pass

    log.warning(
        "Unsupported document type for text extraction mime=%s filename=%s len=%s",
        mime or mime_hint,
        filename,
        len(data),
    )
    return ""


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)
