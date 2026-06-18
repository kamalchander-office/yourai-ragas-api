"""Tests for intent eval CSV formatting."""

from __future__ import annotations

from qa.intent_eval_format import case_to_csv_row, format_bugs_column


def test_format_bugs_compliant():
    assert "No issues" in format_bugs_column([], compliant=True)


def test_format_bugs_groups_by_prompt_source():
    issues = [
        {
            "prompt_source": "tone_prompt",
            "severity": "medium",
            "location": "closing",
            "violation": "Missing next action",
            "prompt_rule": "End with suggested next action",
            "why": "Tone requires it",
            "fix": "Add next step",
            "response_excerpt": "ended abruptly",
        },
        {
            "prompt_source": "system_prompt",
            "severity": "high",
            "location": "structure §1",
            "violation": "No direct answer",
            "prompt_rule": "Lead with answer",
            "why": "System structure rule",
            "fix": "Lead with conclusion",
            "response_excerpt": "According to context",
        },
    ]
    text = format_bugs_column(issues, compliant=False)
    assert "SYSTEM PROMPT" in text
    assert "TONE PROMPT" in text
    assert "Bug 1" in text
    assert "Bug 2" in text
    assert text.index("SYSTEM PROMPT") < text.index("TONE PROMPT")


def test_case_to_csv_row_one_row_per_case():
    row = case_to_csv_row(
        {
            "id": "TC-001",
            "intent_key": "LEGAL_QA",
            "question": "Q?",
            "response": "A.",
            "compliant": False,
            "prompts": {
                "system_prompt": "sys",
                "tone_prompt": "tone",
                "custom_instruction": "custom",
            },
            "checks": {
                "system_prompt": {"evaluated": True, "followed": False},
                "tone_prompt": {"evaluated": True, "followed": True},
                "custom_instruction": {"evaluated": False, "skipped": True},
            },
            "issues": [
                {
                    "prompt_source": "system_prompt",
                    "severity": "high",
                    "location": "opening",
                    "violation": "Bad opening",
                    "why": "rule broken",
                    "fix": "fix it",
                }
            ],
        }
    )
    assert row["id"] == "TC-001"
    assert row["compliant"] == "NO"
    assert row["issue_count"] == "1"
    assert "Bug 1" in row["bugs"]
    assert row["system_followed"] == "NO"
    assert row["tone_followed"] == "YES"
    assert row["custom_followed"] == "SKIP"
