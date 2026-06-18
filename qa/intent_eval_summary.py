"""Build detailed intent_eval_summary.json from per-case evaluation results."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def _pattern_key(issue: dict[str, str]) -> str:
    """Cross-case dedupe key — same violation type, not same case."""
    source = issue.get("prompt_source") or "unknown"
    violation = re.sub(r"\s+", " ", (issue.get("violation") or "").strip().lower())[:160]
    rule = re.sub(r"\s+", " ", (issue.get("prompt_rule") or "").strip().lower())[:120]
    return f"{source}|{violation}|{rule}"


def _preview(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_summary(
    *,
    case_results: list[dict[str, Any]],
    judge_provider: str,
    issues_csv_name: str,
) -> dict[str, Any]:
    """
    case_results items:
      id, intent_key, intent_label, question, response, compliant, issues[], prompts{}
    """
    total = len(case_results)
    compliant_count = sum(1 for c in case_results if c.get("compliant"))
    unmapped = sum(
        1
        for c in case_results
        if not c.get("compliant")
        and any(
            (i.get("violation") or "").startswith("Intent not mapped")
            for i in c.get("issues") or []
        )
    )

    all_issues: list[dict[str, Any]] = []
    by_source: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)

    cases_out: list[dict[str, Any]] = []
    for case in case_results:
        issues = case.get("issues") or []
        for issue in issues:
            enriched = {
                **issue,
                "case_id": case.get("id"),
                "intent_key": case.get("intent_key"),
                "question_preview": _preview(case.get("question") or ""),
            }
            all_issues.append(enriched)
            by_source[issue.get("prompt_source") or "unknown"] += 1
            by_severity[issue.get("severity") or "medium"] += 1

        checks = case.get("checks") or {}
        prompt_compliance = {
            key: {
                "evaluated": chk.get("evaluated", False),
                "skipped": chk.get("skipped", False),
                "followed": chk.get("followed"),
                "compliant": chk.get("compliant"),
                "issue_count": chk.get("issue_count", 0),
            }
            for key, chk in checks.items()
        }

        cases_out.append(
            {
                "id": case.get("id"),
                "intent_key": case.get("intent_key"),
                "intent_label": case.get("intent_label"),
                "compliant": bool(case.get("compliant")),
                "question": case.get("question"),
                "response_preview": _preview(case.get("response") or "", 400),
                "opening_behaviour": (case.get("prompts") or {}).get("opening_behaviour"),
                "prompt_compliance": prompt_compliance,
                "issue_count": len(issues),
                "issues": issues,
            }
        )

    # Unique violation patterns across the run (group similar issues)
    patterns: dict[str, dict[str, Any]] = {}
    for issue in all_issues:
        key = _pattern_key(issue)
        if key not in patterns:
            patterns[key] = {
                "pattern_key": key,
                "prompt_source": issue.get("prompt_source"),
                "severity": issue.get("severity"),
                "violation": issue.get("violation"),
                "prompt_rule": issue.get("prompt_rule"),
                "why": issue.get("why"),
                "fix": issue.get("fix"),
                "occurrence_count": 0,
                "affected_cases": [],
                "examples": [],
            }
        pat = patterns[key]
        pat["occurrence_count"] += 1
        cid = issue.get("case_id")
        if cid and cid not in pat["affected_cases"]:
            pat["affected_cases"].append(cid)
        if len(pat["examples"]) < 3:
            pat["examples"].append(
                {
                    "case_id": issue.get("case_id"),
                    "location": issue.get("location"),
                    "response_excerpt": issue.get("response_excerpt"),
                    "issue": issue.get("issue"),
                }
            )

    unique_violations = sorted(
        patterns.values(),
        key=lambda p: (-p["occurrence_count"], p.get("violation") or ""),
    )

    non_compliant_cases = [c for c in cases_out if not c["compliant"]]

    def _check_failures(key: str) -> int:
        n = 0
        for case in case_results:
            chk = (case.get("checks") or {}).get(key) or {}
            if chk.get("evaluated") and not chk.get("followed"):
                n += 1
        return n

    return {
        "run": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "judge_provider": judge_provider,
            "evaluation_type": "intent_prompt_compliance",
        },
        "statistics": {
            "total_evaluated": total,
            "compliant": compliant_count,
            "non_compliant": total - compliant_count,
            "unmapped_intent": unmapped,
            "total_issues": len(all_issues),
            "unique_violation_patterns": len(unique_violations),
            "by_prompt_source": dict(sorted(by_source.items())),
            "by_severity": dict(sorted(by_severity.items())),
            "system_prompt_failures": _check_failures("system_prompt"),
            "tone_prompt_failures": _check_failures("tone_prompt"),
            "custom_instruction_failures": _check_failures("custom_instruction"),
        },
        "cases": cases_out,
        "non_compliant_cases": non_compliant_cases,
        "all_issues": all_issues,
        "unique_violations": unique_violations,
        "issues_file": issues_csv_name,
    }
