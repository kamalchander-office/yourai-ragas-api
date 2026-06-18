"""Tests for intent prompt extraction."""

from __future__ import annotations

from qa.intent_prompts import extract_intent_prompts, has_any_prompt


def test_extract_prompts_from_session_shape():
    intent = {
        "key": "GENERAL_CHAT",
        "id": "uuid-1",
        "tone_prompt": "wrong-copy",
        "custom_instruction": "wrong-copy",
        "raw": {
            "label": "General Chat",
            "systemPrompt": "You are Alex.",
            "tonePrompt": "Be warm.",
            "customInstruction": "Say thanks at end.",
            "openingBehaviour": "START_IMMEDIATELY",
        },
    }
    bundle = extract_intent_prompts(intent)
    assert bundle["system_prompt"] == "You are Alex."
    assert bundle["tone_prompt"] == "Be warm."
    assert bundle["custom_instruction"] == "Say thanks at end."
    assert bundle["opening_behaviour"] == "START_IMMEDIATELY"
    assert has_any_prompt(bundle)


def test_has_any_prompt_false_when_empty():
    assert not has_any_prompt(extract_intent_prompts({}))
