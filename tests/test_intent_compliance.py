"""Tests for strict intent compliance checks."""

from __future__ import annotations

import json

from qa.intent_compliance import (
    _parse_judge_json,
    dedupe_issues,
    evaluate_response_compliance,
    normalize_issue,
    run_strict_prompt_check,
)


def test_parse_judge_json_compliant():
    data = _parse_judge_json('{"followed": true, "compliant": true, "issues": []}')
    assert data["followed"] is True
    assert data["issues"] == []


def test_parse_judge_json_detailed_issue():
    raw = """{
      "followed": false,
      "compliant": false,
      "issues": [{
        "severity": "high",
        "location": "closing line",
        "violation": "Missing required Thanks for using YourAI closing",
        "response_excerpt": "ended without thanks",
        "prompt_rule": "Add Thanks for using YourAI at the end of each answer",
        "why": "Custom instruction mandates closing phrase",
        "fix": "Append Thanks for using YourAI"
      }]
    }"""
    data = _parse_judge_json(raw)
    issue = normalize_issue(data["issues"][0], case_id="TC-1", prompt_source="custom_instruction")
    assert issue["prompt_source"] == "custom_instruction"
    assert "Thanks" in issue["violation"]


def test_dedupe_issues_drops_duplicates():
    a = normalize_issue(
        {"violation": "Missing closing", "location": "end"},
        case_id="TC-1",
        prompt_source="custom_instruction",
    )
    b = normalize_issue(
        {"violation": "Missing closing", "location": "end"},
        case_id="TC-1",
        prompt_source="custom_instruction",
    )
    assert len(dedupe_issues([a, b])) == 1


def test_run_strict_prompt_check_skips_empty_prompt():
    result = run_strict_prompt_check(
        prompt_key="custom_instruction",
        check_label="CUSTOM INSTRUCTION",
        judge_system="test",
        prompt_text="",
        question="Q?",
        response="A.",
        intent_label="LEGAL_QA",
        case_id="TC-1",
        judge_fn=lambda *a, **k: "{}",
    )
    assert result["skipped"] is True
    assert result["evaluated"] is False


def test_evaluate_runs_three_strict_checks():
    calls: list[str] = []

    def fake_judge(user_text: str, *, system_text: str) -> str:
        if "SYSTEM PROMPT" in system_text:
            calls.append("system")
            return json.dumps({"followed": False, "compliant": False, "issues": [{
                "severity": "high", "location": "structure",
                "violation": "Missing direct answer",
                "response_excerpt": "maybe", "prompt_rule": "Lead with answer",
                "why": "required", "fix": "fix it"
            }]})
        if "TONE PROMPT" in system_text:
            calls.append("tone")
            return json.dumps({"followed": True, "compliant": True, "issues": []})
        if "CUSTOM INSTRUCTION" in system_text:
            calls.append("custom")
            return json.dumps({"followed": False, "compliant": False, "issues": [{
                "severity": "high", "location": "format",
                "violation": "Not bullet-only",
                "response_excerpt": "prose", "prompt_rule": "Bullets only",
                "why": "required", "fix": "use bullets"
            }]})
        return json.dumps({"followed": True, "compliant": True, "issues": []})

    result = evaluate_response_compliance(
        question="Q?",
        response="Some answer here.",
        prompts={
            "system_prompt": "Lead with the answer.",
            "tone_prompt": "Be concise.",
            "custom_instruction": "Use bullets only.",
            "intent_key": "LEGAL_QA",
        },
        case_id="TC-1",
        judge_fn=fake_judge,
    )

    assert set(calls) == {"system", "tone", "custom"}
    assert result["compliant"] is False
    assert result["checks"]["system_prompt"]["followed"] is False
    assert result["checks"]["tone_prompt"]["followed"] is True
    assert result["checks"]["custom_instruction"]["followed"] is False
    assert len(result["issues"]) == 2
    sources = {i["prompt_source"] for i in result["issues"]}
    assert sources == {"system_prompt", "custom_instruction"}


def test_evaluate_skips_empty_answer():
    result = evaluate_response_compliance(
        question="Q?",
        response="",
        prompts={"system_prompt": "Be helpful", "tone_prompt": "", "custom_instruction": ""},
        case_id="TC-1",
    )
    assert result["compliant"] is False
    assert result["issues"][0]["violation"] == "No valid API response to evaluate"
