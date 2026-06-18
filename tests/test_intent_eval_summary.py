"""Tests for intent_eval_summary.json builder."""

from __future__ import annotations

from qa.intent_eval_summary import build_summary


def test_build_summary_includes_unique_violations_and_cases():
    case_results = [
        {
            "id": "TC-001",
            "intent_key": "LEGAL_QA",
            "intent_label": "Legal Q&A",
            "question": "Q1?",
            "response": "Answer one",
            "compliant": False,
            "prompts": {"opening_behaviour": "START_IMMEDIATELY"},
            "checks": {
                "system_prompt": {
                    "evaluated": True, "skipped": False, "followed": False, "issue_count": 0,
                },
                "tone_prompt": {
                    "evaluated": True, "skipped": False, "followed": True, "issue_count": 0,
                },
                "custom_instruction": {
                    "evaluated": True, "skipped": False, "followed": False, "issue_count": 1,
                },
            },
            "issues": [
                {
                    "prompt_source": "custom_instruction",
                    "severity": "high",
                    "location": "closing",
                    "violation": "Missing closing phrase",
                    "response_excerpt": "no thanks",
                    "prompt_rule": "Add thanks at end",
                    "why": "Required by custom instruction",
                    "fix": "Add thanks",
                    "issue": "[closing] Missing closing phrase",
                    "fingerprint": "TC-001|custom_instruction|closing|missing",
                }
            ],
        },
        {
            "id": "TC-002",
            "intent_key": "LEGAL_QA",
            "intent_label": "Legal Q&A",
            "question": "Q2?",
            "response": "Answer two",
            "compliant": False,
            "prompts": {},
            "checks": {
                "system_prompt": {
                    "evaluated": True, "skipped": False, "followed": False, "issue_count": 0,
                },
                "tone_prompt": {
                    "evaluated": True, "skipped": False, "followed": True, "issue_count": 0,
                },
                "custom_instruction": {
                    "evaluated": True, "skipped": False, "followed": False, "issue_count": 1,
                },
            },
            "issues": [
                {
                    "prompt_source": "custom_instruction",
                    "severity": "high",
                    "location": "closing",
                    "violation": "Missing closing phrase",
                    "response_excerpt": "also missing",
                    "prompt_rule": "Add thanks at end",
                    "why": "Required by custom instruction",
                    "fix": "Add thanks",
                    "issue": "[closing] Missing closing phrase",
                    "fingerprint": "TC-002|custom_instruction|closing|missing",
                }
            ],
        },
    ]
    summary = build_summary(
        case_results=case_results,
        judge_provider="openrouter",
        issues_csv_name="intent_eval_issues.csv",
    )
    assert summary["statistics"]["total_evaluated"] == 2
    assert summary["statistics"]["unique_violation_patterns"] == 1
    assert len(summary["cases"]) == 2
    assert summary["cases"][0]["prompt_compliance"]["system_prompt"]["followed"] is False
    assert summary["statistics"]["system_prompt_failures"] == 2
    assert len(summary["all_issues"]) == 2
    assert summary["unique_violations"][0]["occurrence_count"] == 2
    assert "TC-001" in summary["unique_violations"][0]["affected_cases"]
    assert "TC-002" in summary["unique_violations"][0]["affected_cases"]
