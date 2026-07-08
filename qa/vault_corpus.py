"""Download YourVault fileUrl bytes and build DocumentContext for case generation."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path

from yourai_chat.document_text import extract_text_from_bytes
from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.vault import document_is_ready, infer_filename_from_url

from qa.local_documents import DocumentContext

log = logging.getLogger(__name__)

from qa.paths import CORPUS_CACHE_DIR, QA_DIR, ROOT

DEFAULT_CACHE_DIR = CORPUS_CACHE_DIR


def corpus_cache_dir() -> Path:
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CORPUS_CACHE_DIR


def _max_text_chars() -> int:
    return int(os.getenv("GENERATE_MAX_DOCUMENT_CHARS", "80000"))


def _extract_docx(data: bytes, filename: str) -> str:
    if data[:2] != b"PK":
        log.warning("%s is not a Word zip; trying plain decode", filename)
        return extract_text_from_bytes(data, filename=filename, content_type="text/plain")
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    except zipfile.BadZipFile:
        log.warning("%s invalid docx zip; trying plain decode", filename)
        return extract_text_from_bytes(data, filename=filename, content_type="text/plain")


def extract_text_from_download(
    data: bytes,
    *,
    filename: str,
    mime_type: str | None = None,
    file_type: str | None = None,
) -> str:
    name = filename.lower()
    ft = (file_type or "").lower()
    mime = (mime_type or "").lower()

    if name.endswith(".docx") or ft == "docx":
        text = _extract_docx(data, filename)
    elif name.endswith(".pdf") or ft == "pdf" or "pdf" in mime:
        text = extract_text_from_bytes(data, filename=filename, content_type="application/pdf")
    else:
        text = extract_text_from_bytes(
            data,
            filename=filename,
            content_type=mime or "text/plain",
        )
    return text.strip()


def cache_path_for_document(document_id: str) -> Path:
    return corpus_cache_dir() / f"{document_id}.txt"


def download_vault_document_text(
    client: YourAIPWAClient,
    vault_doc: dict,
    *,
    force_download: bool = False,
) -> DocumentContext:
    """Download fileUrl (if needed), extract text, cache under qa/results/corpus_cache/."""
    document_id = str(vault_doc.get("id") or "")
    if not document_id:
        raise ValueError("vault document missing id")

    cache_file = cache_path_for_document(document_id)
    file_url = (vault_doc.get("fileUrl") or vault_doc.get("file_url") or "").strip()
    name = (vault_doc.get("name") or "").strip()
    if file_url:
        filename = infer_filename_from_url(file_url, fallback=f"{name or document_id}.bin")
    else:
        filename = f"{name or document_id}.txt"

    if cache_file.is_file() and not force_download:
        text = cache_file.read_text(encoding="utf-8")
        truncated = len(text) >= _max_text_chars()
        return DocumentContext(
            document_id=document_id,
            filename=filename,
            local_path=str(cache_file.relative_to(ROOT)),
            text=text,
            text_truncated=truncated,
            source_type="vault_cache",
        )

    if not file_url:
        raise ValueError(f"Vault document {document_id} has no fileUrl to download")

    if not document_is_ready(vault_doc):
        raise ValueError(
            f"Vault document {document_id} is not READY "
            f"(status={vault_doc.get('status')}, processing={vault_doc.get('processingStatus')})"
        )

    data = client.download_url(file_url)
    text = extract_text_from_download(
        data,
        filename=filename,
        mime_type=vault_doc.get("mimeType") or vault_doc.get("mime_type"),
        file_type=vault_doc.get("fileType") or vault_doc.get("file_type"),
    )
    if not text:
        raise ValueError(f"No text extracted from vault document {document_id} ({filename})")

    truncated = False
    max_chars = _max_text_chars()
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    cache_file.write_text(text, encoding="utf-8")
    log.info("Cached vault corpus %s (%s chars)", document_id[:8], len(text))

    return DocumentContext(
        document_id=document_id,
        filename=filename,
        local_path=str(cache_file.relative_to(ROOT)),
        text=text,
        text_truncated=truncated,
        source_type="vault_download",
    )


def build_combined_document_context(
    contexts: list[DocumentContext],
    *,
    label: str = "vault_combined",
) -> DocumentContext:
    """Merge multiple vault documents into one prompt corpus."""
    if not contexts:
        raise ValueError("No document contexts to combine")
    if len(contexts) == 1:
        return contexts[0]

    parts: list[str] = []
    for ctx in contexts:
        parts.append(f"=== DOCUMENT: {ctx.filename} (id={ctx.document_id}) ===\n{ctx.text}")

    combined = "\n\n".join(parts)
    truncated = any(c.text_truncated for c in contexts)
    max_chars = _max_text_chars()
    if len(combined) > max_chars:
        combined = combined[:max_chars]
        truncated = True

    primary = contexts[0]
    combined_id = primary.document_id
    cache_file = corpus_cache_dir() / f"combined_{combined_id[:8]}_{len(contexts)}docs.txt"
    cache_file.write_text(combined, encoding="utf-8")

    return DocumentContext(
        document_id=combined_id,
        filename=f"{label} ({len(contexts)} docs)",
        local_path=str(cache_file.relative_to(ROOT)),
        text=combined,
        text_truncated=truncated,
        source_type="vault_combined",
    )


def load_document_context_from_session(
    session: dict,
    client: YourAIPWAClient | None = None,
) -> DocumentContext:
    """
    Resolve corpus for generate_cases from session.json.

    Supports vault pick (attachment + cache), combined multi-doc corpus, and legacy upload local_path.
    """
    corpus = session.get("corpus") or {}
    combined_path = corpus.get("combined_cache_path")
    if combined_path:
        path = Path(combined_path)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            primary_id = corpus.get("primary_document_id") or (session.get("document") or {}).get("id", "")
            return DocumentContext(
                document_id=str(primary_id),
                filename=path.name,
                local_path=str(combined_path),
                text=text,
                text_truncated=len(text) >= _max_text_chars(),
                source_type="vault_combined_cache",
            )

    attachment = session.get("attachment") or {}
    docs_meta = attachment.get("documents") or []

    def _context_from_cache(meta: dict) -> DocumentContext | None:
        cache_rel = meta.get("corpus_cache_path")
        if not cache_rel:
            return None
        path = ROOT / cache_rel
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        return DocumentContext(
            document_id=str(meta.get("id") or ""),
            filename=meta.get("name") or path.name,
            local_path=str(cache_rel),
            text=text,
            text_truncated=len(text) >= _max_text_chars(),
            source_type="vault_cache",
        )

    if docs_meta:
        contexts: list[DocumentContext] = []
        for meta in docs_meta:
            cached = _context_from_cache(meta)
            if cached:
                contexts.append(cached)
                continue
            if client is None:
                raise FileNotFoundError(
                    f"Corpus cache missing for {meta.get('id')} — re-run bootstrap_session.py "
                    "(vault mode downloads fileUrl into qa/results/corpus_cache/)."
                )
            contexts.append(download_vault_document_text(client, meta))
        if len(contexts) > 1:
            return build_combined_document_context(contexts)
        if contexts:
            return contexts[0]

    if client is not None and attachment.get("document_ids"):
        # Session has ids but no cached metadata — resolve and download
        vault_docs = client.resolve_vault_documents(document_ids=attachment.get("document_ids"))
        contexts = [download_vault_document_text(client, d) for d in vault_docs]
        if len(contexts) > 1:
            return build_combined_document_context(contexts)
        if contexts:
            return contexts[0]

    # Legacy upload bootstrap — local file on disk
    doc_meta = session.get("document") or {}
    local_path = Path(doc_meta.get("local_path") or "")
    if local_path.is_file():
        return _document_from_session_legacy(session)

    raise FileNotFoundError(
        "No corpus in session — run bootstrap with vault pick or upload, "
        "or ensure qa/results/corpus_cache/ exists."
    )


def _document_from_session_legacy(session: dict) -> DocumentContext:
    """Original local-path-only loader (used by generate_cases)."""
    doc_meta = session.get("document") or {}
    local_path = Path(doc_meta.get("local_path") or "")
    if not local_path.is_file():
        raise FileNotFoundError(f"Session document not found on disk: {local_path}")

    from qa.local_documents import LocalDocumentStore

    store = LocalDocumentStore()
    loaded = store.load_many(filenames=[local_path.name])
    if local_path.name not in loaded:
        raw = local_path.read_bytes()
        text = extract_text_from_bytes(raw, filename=local_path.name)
        max_chars = _max_text_chars()
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return DocumentContext(
            document_id=doc_meta.get("id") or local_path.stem,
            filename=local_path.name,
            local_path=str(local_path),
            text=text,
            text_truncated=truncated,
        )

    doc = loaded[local_path.name]
    return DocumentContext(
        document_id=doc_meta.get("id") or doc.document_id,
        filename=doc.filename,
        local_path=str(local_path),
        text=doc.text,
        text_truncated=doc.text_truncated,
    )
