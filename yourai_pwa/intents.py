"""Normalize intent records from GET /knowledge-base/intents."""

from __future__ import annotations

from typing import Any


def _first_list(*values: Any) -> list[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_intent(raw: dict[str, Any]) -> dict[str, Any]:
    """Map PWA intent payload to a stable shape for test generation and chat."""
    key = _first_str(raw.get("key"), raw.get("intentKey"), raw.get("code"), raw.get("name"))
    intent_id = _first_str(raw.get("id"), raw.get("intentId"), raw.get("uuid"))
    keywords = _first_list(
        raw.get("triggerKeywords"),
        raw.get("trigger_keywords"),
        raw.get("keywords"),
        raw.get("keywordList"),
    )

    return {
        "key": key or "UNKNOWN",
        "id": intent_id or "",
        "name": _first_str(raw.get("name"), raw.get("displayName"), raw.get("title")) or key or "",
        "trigger_keywords": keywords,
        "tone_prompt": _first_str(
            raw.get("tonePrompt"),
            raw.get("tone_prompt"),
            raw.get("tone"),
        ),
        "custom_instruction": _first_str(
            raw.get("customInstruction"),
            raw.get("custom_instruction"),
            raw.get("customInstructions"),
            raw.get("systemPrompt"),
        ),
        "opening_behaviour": _first_str(
            raw.get("openingBehaviour"),
            raw.get("opening_behaviour"),
            raw.get("openingBehavior"),
        ),
        "raw": raw,
    }


def parse_intents_response(body: Any) -> list[dict[str, Any]]:
    """Extract intent list from various API response shapes."""
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        data = body.get("data", body)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("intents")
                or data.get("items")
                or data.get("results")
                or []
            )
        else:
            items = body.get("intents") or []
    else:
        items = []

    return [normalize_intent(item) for item in items if isinstance(item, dict)]


def intent_by_key(intents: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    target = (key or "").strip().upper()
    for intent in intents:
        if (intent.get("key") or "").upper() == target:
            return intent
    return None
