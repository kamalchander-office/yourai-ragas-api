"""Extract system / tone / custom prompts from platform intent records."""

from __future__ import annotations

from typing import Any


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_intent_prompts(intent: dict[str, Any] | None) -> dict[str, str]:
    """
    Return prompt bundle for intent-compliance evaluation.

    Prefer camelCase fields from intent.raw (PWA API) over normalized copies.
    """
    intent = intent or {}
    raw = intent.get("raw") if isinstance(intent.get("raw"), dict) else {}

    label = _first_str(
        raw.get("label"),
        intent.get("name"),
        intent.get("key"),
    )

    return {
        "intent_key": _first_str(intent.get("key"), raw.get("key")),
        "intent_id": _first_str(intent.get("id"), raw.get("id")),
        "intent_label": label,
        "system_prompt": _first_str(raw.get("systemPrompt"), raw.get("system_prompt")),
        "tone_prompt": _first_str(
            raw.get("tonePrompt"),
            raw.get("tone_prompt"),
            intent.get("tone_prompt"),
        ),
        "custom_instruction": _first_str(
            raw.get("customInstruction"),
            raw.get("custom_instruction"),
            intent.get("custom_instruction"),
        ),
        "opening_behaviour": _first_str(
            raw.get("openingBehaviour"),
            raw.get("opening_behaviour"),
            intent.get("opening_behaviour"),
        ),
    }


def has_any_prompt(bundle: dict[str, str]) -> bool:
    return bool(
        bundle.get("system_prompt")
        or bundle.get("tone_prompt")
        or bundle.get("custom_instruction")
        or bundle.get("opening_behaviour")
    )
