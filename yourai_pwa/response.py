"""Normalize PWA POST /chat responses for yourai_chat.parser."""

from __future__ import annotations

from typing import Any


def _unwrap_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    if isinstance(data, dict):
        merged = dict(data)
        for key in ("success", "message"):
            if key in raw and key not in merged:
                merged[key] = raw[key]
        return merged
    return raw


def normalize_chat_response(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert PWA camelCase chat body to the shape expected by parse_chat_response.
    """
    body = _unwrap_data(raw)

    retrieval = body.get("retrievalSummary") or body.get("retrieval_summary") or {}
    if not isinstance(retrieval, dict):
        retrieval = {}

    debug = body.get("debugData") or body.get("debug_data") or {}
    if not isinstance(debug, dict):
        debug = {}

    sources_used = body.get("sourcesUsed") or body.get("sources_used") or []
    unused = body.get("unusedSources") or body.get("unused_sources") or []
    attribution = body.get("sourceAttribution") or body.get("source_attribution") or []

    return {
        "answer": body.get("answer") or body.get("message") or "",
        "output_intent": body.get("outputIntent") or body.get("output_intent"),
        "output_intent_confidence": body.get("outputIntentConfidence"),
        "output_intent_classification_source": (
            body.get("outputIntentClassificationSource")
            or body.get("output_intent_classification_source")
        ),
        "answer_status": body.get("answerStatus") or body.get("answer_status"),
        "source_types_used": body.get("sourceTypesUsed") or body.get("source_types_used") or [],
        "sources_used": sources_used,
        "unused_sources": unused,
        "source_attribution": attribution,
        "confidence_score": body.get("confidenceScore") or body.get("confidence_score"),
        "tier": body.get("tier"),
        "status": body.get("status"),
        "success": body.get("success"),
        "retrieval_summary": {
            "chunks_retrieved": retrieval.get("chunks_retrieved") or retrieval.get("chunksRetrieved"),
            "chunks_used": retrieval.get("chunks_used") or retrieval.get("chunksUsed"),
            "retrieval_mode": retrieval.get("retrieval_mode") or retrieval.get("retrievalMode"),
            "scope_locked": retrieval.get("scope_locked") or retrieval.get("scopeLocked"),
        },
        "user_warnings": body.get("userWarnings") or body.get("user_warnings") or [],
        "warnings": body.get("warnings") or [],
        "latency_ms": body.get("latencyMs") or body.get("latency_ms"),
        "inference_id": body.get("inferenceId") or body.get("inference_id"),
        "debug_data": debug,
    }
