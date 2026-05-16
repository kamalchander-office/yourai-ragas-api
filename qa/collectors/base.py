"""Shared result-row builder for collectors."""

from __future__ import annotations

from typing import Any


def build_result_row(
    test_case: dict[str, Any],
    normalized: dict[str, Any],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Merge normalized API fields with dataset metadata.

    Preserves run_eval.py contract: question, answer, contexts, ground_truth.
    Adds actual_* fields for future rule/retrieval validators.
    """
    answer = error if error else normalized.get("answer", "")
    row = {
        "id": test_case["id"],
        "question": test_case["question"],
        "answer": answer,
        "contexts": normalized.get("contexts", []) if not error else [],
        "ground_truth": test_case.get("ground_truth", ""),
        "case_type": test_case.get("case_type", "positive"),
        "intent": test_case.get("intent", "General Chat"),
        "source": test_case.get("source", "human"),
        # Normalized attribution fields (validators / future tiers)
        "actual_answer": normalized.get("actual_answer", answer),
        "actual_source": normalized.get("actual_source"),
        "actual_doc_id": normalized.get("actual_doc_id"),
        "reference": normalized.get("reference"),
        "reference_text": normalized.get("reference_text"),
        "raw_response": normalized.get("raw_response", {}),
        "http_status": normalized.get("http_status"),
        "latency_ms": normalized.get("latency_ms"),
        "conversation_id": normalized.get("conversation_id"),
        "message_id": normalized.get("message_id"),
        "intent_id": test_case.get("intent_id") or test_case.get("intent", ""),
        "retrieval_mode": normalized.get("retrieval_mode"),
        "api_backend": normalized.get("api_backend"),
    }
    if error:
        row["error"] = error
    return row
