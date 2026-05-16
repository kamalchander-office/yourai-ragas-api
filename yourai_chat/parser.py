"""
Normalize YourAI chat API responses for downstream validators and RAGAs.

Handles missing source/reference fields without raising.
"""

from __future__ import annotations

from typing import Any


def _first_str(*candidates: Any) -> str | None:
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return None


def _dig(data: Any, *paths: tuple[str | int, ...]) -> Any:
    for path in paths:
        node: Any = data
        for key in path:
            if isinstance(node, dict) and isinstance(key, str):
                node = node.get(key)
            elif isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
                node = node[key]
            else:
                node = None
                break
        if node is not None:
            return node
    return None


def parse_chat_response(
    *,
    question: str,
    raw: dict[str, Any] | None,
    http_status: int | None = None,
) -> dict[str, Any]:
    """
  Return framework-normalized record.

  Downstream contracts:
    - `answer` / `actual_answer` for run_eval.py (RAGAs)
    - `actual_*` / `reference*` for future rule & retrieval validators
    """
    raw = raw or {}

    # Common answer locations (API shape may evolve)
    answer = _first_str(
        raw.get("answer"),
        raw.get("message"),
        raw.get("content"),
        raw.get("response"),
        _dig(raw, ("data", "answer")),
        _dig(raw, ("data", "message")),
        _dig(raw, ("result", "answer")),
        _dig(raw, ("result", "message")),
        _dig(raw, ("response", "message")),
        _dig(raw, ("response", "content")),
    )

    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    retrieval = raw.get("retrieval") if isinstance(raw.get("retrieval"), dict) else {}
    citation = raw.get("citation") if isinstance(raw.get("citation"), dict) else {}

    actual_source = _first_str(
        raw.get("source"),
        raw.get("actual_source"),
        metadata.get("source"),
        retrieval.get("source"),
        _dig(raw, ("sources", 0, "type")) if isinstance(raw.get("sources"), list) and raw["sources"] else None,
    )

    actual_doc_id = _first_str(
        raw.get("doc_id"),
        raw.get("document_id"),
        metadata.get("doc_id"),
        metadata.get("document_id"),
        retrieval.get("doc_id"),
        retrieval.get("document_id"),
        _dig(raw, ("sources", 0, "doc_id")) if isinstance(raw.get("sources"), list) and raw["sources"] else None,
        _dig(raw, ("sources", 0, "document_id")) if isinstance(raw.get("sources"), list) and raw["sources"] else None,
    )

    reference = _first_str(
        raw.get("reference"),
        citation.get("reference"),
        metadata.get("reference"),
        _dig(raw, ("citations", 0, "reference")) if isinstance(raw.get("citations"), list) and raw["citations"] else None,
    )

    reference_text = _first_str(
        raw.get("reference_text"),
        citation.get("text"),
        citation.get("reference_text"),
        metadata.get("reference_text"),
        _dig(raw, ("citations", 0, "text")) if isinstance(raw.get("citations"), list) and raw["citations"] else None,
    )

    contexts: list[str] = []
    chunks = raw.get("contexts") or raw.get("chunks") or retrieval.get("chunks")
    if isinstance(chunks, list):
        for item in chunks:
            if isinstance(item, str) and item.strip():
                contexts.append(item.strip())
            elif isinstance(item, dict):
                text = _first_str(item.get("text"), item.get("content"), item.get("chunk"))
                if text:
                    contexts.append(text)

    return {
        "question": question,
        "actual_answer": answer or "",
        "answer": answer or "",  # run_eval.py contract
        "actual_source": actual_source,
        "actual_doc_id": actual_doc_id,
        "reference": reference,
        "reference_text": reference_text,
        "contexts": contexts,
        "raw_response": raw,
        "http_status": http_status,
    }
