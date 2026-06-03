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


def _contexts_from_attribution(raw: dict[str, Any]) -> list[str]:
    """Build RAGAs context list from YourAI source_attribution snippets."""
    contexts: list[str] = []
    seen: set[str] = set()

    attribution = raw.get("source_attribution")
    if isinstance(attribution, list):
        for item in attribution:
            if not isinstance(item, dict):
                continue
            snippet = _first_str(item.get("snippet"), item.get("text"), item.get("content"))
            if not snippet:
                continue
            doc_id = item.get("document_id") or item.get("container_id") or ""
            page = item.get("page_number")
            clause = item.get("clause_ref")
            prefix_parts = [p for p in (doc_id, clause, f"p.{page}" if page else None) if p]
            prefix = " | ".join(prefix_parts)
            block = f"[{prefix}]\n{snippet}" if prefix else snippet
            if block not in seen:
                seen.add(block)
                contexts.append(block)

    return contexts


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
      - `actual_*` / `reference*` for rule & retrieval validators
      - `contexts` for faithfulness / context metrics
    """
    raw = raw or {}

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

    source_types = raw.get("source_types_used")
    first_source_type = (
        source_types[0]
        if isinstance(source_types, list) and source_types
        else None
    )

    sources_used = raw.get("sources_used")
    first_source = (
        sources_used[0] if isinstance(sources_used, list) and sources_used else None
    )
    first_source_kind = (
        first_source.get("kind") if isinstance(first_source, dict) else None
    )
    first_source_id = (
        first_source.get("id") if isinstance(first_source, dict) else None
    )

    attribution = raw.get("source_attribution")
    first_attr = (
        attribution[0] if isinstance(attribution, list) and attribution else None
    )
    attr_doc_id = (
        first_attr.get("document_id") or first_attr.get("container_id")
        if isinstance(first_attr, dict)
        else None
    )

    actual_source = _first_str(
        raw.get("source"),
        raw.get("actual_source"),
        first_source_type,
        first_source_kind,
        metadata.get("source"),
        retrieval.get("source"),
        _dig(raw, ("sources", 0, "type")) if isinstance(raw.get("sources"), list) and raw["sources"] else None,
    )

    actual_doc_id = _first_str(
        raw.get("doc_id"),
        raw.get("document_id"),
        attr_doc_id,
        first_source_id,
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
        _first_str(
            first_attr.get("clause_ref") if isinstance(first_attr, dict) else None
        ),
        _dig(raw, ("citations", 0, "reference")) if isinstance(raw.get("citations"), list) and raw["citations"] else None,
    )

    reference_text = _first_str(
        raw.get("reference_text"),
        citation.get("text"),
        citation.get("reference_text"),
        metadata.get("reference_text"),
        _first_str(
            first_attr.get("snippet") if isinstance(first_attr, dict) else None
        ),
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

    if not contexts:
        contexts = _contexts_from_attribution(raw)

    tier = _first_str(raw.get("tier"))
    answer_status = _first_str(raw.get("answer_status"))
    confidence_score = raw.get("confidence_score")
    grounding_passed = None
    debug = raw.get("debug_data")
    if isinstance(debug, dict):
        gr = debug.get("grounding_result")
        if gr is not None:
            grounding_passed = str(gr).lower() == "passed"

    return {
        "question": question,
        "actual_answer": answer or "",
        "answer": answer or "",
        "actual_source": actual_source,
        "actual_doc_id": actual_doc_id,
        "reference": reference,
        "reference_text": reference_text,
        "contexts": contexts,
        "tier": tier,
        "answer_status": answer_status,
        "confidence_score": confidence_score,
        "grounding_passed": grounding_passed,
        "raw_response": raw,
        "http_status": http_status,
    }
