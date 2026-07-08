"""YourVault listing, resolution, and URL helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_UUID_IN_PATH = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def parse_comma_separated(value: str | None) -> list[str]:
    """Split comma/newline-separated config into stripped non-empty tokens."""
    if not value or not str(value).strip():
        return []
    parts = re.split(r"[,;\n]+", str(value))
    return [p.strip() for p in parts if p.strip()]


def parse_document_id_from_url(url: str) -> str | None:
    """
    Extract vault document UUID from a media URL, e.g.
    https://media-qa.yourai.com/documents/{uuid}/file.docx
    """
    text = (url or "").strip()
    if not text:
        return None
    match = _UUID_IN_PATH.search(text)
    return match.group(0) if match else None


def vault_list_data(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize GET /vault response to a list of document dicts."""
    data = body.get("data", body)
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("documents", "items", "results"):
            items = data.get(key)
            if isinstance(items, list):
                return [d for d in items if isinstance(d, dict)]
    return []


def vault_folder_list_data(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data", body)
    if isinstance(data, list):
        return [f for f in data if isinstance(f, dict)]
    if isinstance(data, dict):
        items = data.get("folders") or data.get("items")
        if isinstance(items, list):
            return [f for f in items if isinstance(f, dict)]
    return []


def document_is_ready(doc: dict[str, Any]) -> bool:
    status = (doc.get("status") or "").upper()
    processing = (
        doc.get("processingStatus") or doc.get("processing_status") or ""
    ).lower()
    return status == "READY" and processing == "ready"


def infer_filename_from_url(file_url: str, *, fallback: str = "document.bin") -> str:
    path = urlparse(file_url).path
    name = path.rsplit("/", 1)[-1] if path else fallback
    return name or fallback
