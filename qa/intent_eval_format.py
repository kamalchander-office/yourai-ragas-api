"""Format intent compliance issues for CSV export (one row per question)."""

from __future__ import annotations

_PROMPT_LABELS = {
    "system_prompt": "SYSTEM PROMPT",
    "tone_prompt": "TONE PROMPT",
    "custom_instruction": "CUSTOM INSTRUCTION",
    "opening_behaviour": "OPENING BEHAVIOUR",
    "unknown": "OTHER",
    "judge": "JUDGE",
}


def format_bugs_column(issues: list[dict], *, compliant: bool) -> str:
    """
    Render all issues for one question as a single multi-line bullet block.

    Grouped by prompt type (system → tone → custom) for readability in Excel/Sheets.
    """
    if compliant or not issues:
        return "✓ No issues — all prompt checks passed."

    # Preserve order: system, tone, custom, then any others
    order = ("system_prompt", "tone_prompt", "custom_instruction", "opening_behaviour", "unknown", "judge")
    by_source: dict[str, list[dict]] = {k: [] for k in order}
    for issue in issues:
        src = issue.get("prompt_source") or "unknown"
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(issue)

    sections: list[str] = []
    bug_num = 0

    for src in order:
        group = by_source.get(src) or []
        if not group:
            continue
        label = _PROMPT_LABELS.get(src, src.upper())
        sections.append(f"── {label} ({len(group)} issue{'s' if len(group) != 1 else ''}) ──")
        for issue in group:
            bug_num += 1
            severity = (issue.get("severity") or "medium").upper()
            location = issue.get("location") or "n/a"
            violation = issue.get("violation") or issue.get("issue") or "Unspecified violation"
            rule = issue.get("prompt_rule") or ""
            why = issue.get("why") or ""
            fix = issue.get("fix") or ""
            excerpt = issue.get("response_excerpt") or ""

            block = [f"• Bug {bug_num} [{severity}] {violation}"]
            block.append(f"  Where: {location}")
            if rule:
                block.append(f"  Broken rule: {rule}")
            if excerpt:
                block.append(f'  Response excerpt: "{excerpt}"')
            if why:
                block.append(f"  Why: {why}")
            if fix:
                block.append(f"  Fix: {fix}")
            sections.append("\n".join(block))

    return "\n\n".join(sections)


def case_to_csv_row(case: dict) -> dict[str, str]:
    """One CSV row per test case; all bugs in the `bugs` column."""
    prompts = case.get("prompts") or {}
    checks = case.get("checks") or {}
    issues = case.get("issues") or []
    compliant = bool(case.get("compliant"))

    def _followed(key: str) -> str:
        chk = checks.get(key) or {}
        if chk.get("skipped") or not chk.get("evaluated"):
            return "SKIP"
        return "YES" if chk.get("followed") else "NO"

    return {
        "id": case.get("id") or "",
        "intent_key": case.get("intent_key") or "",
        "question": case.get("question") or "",
        "response": case.get("response") or "",
        "system_prompt": prompts.get("system_prompt", ""),
        "tone_prompt": prompts.get("tone_prompt", ""),
        "custom_prompt": prompts.get("custom_instruction", ""),
        "system_followed": _followed("system_prompt"),
        "tone_followed": _followed("tone_prompt"),
        "custom_followed": _followed("custom_instruction"),
        "compliant": "YES" if compliant else "NO",
        "issue_count": str(len(issues)),
        "bugs": format_bugs_column(issues, compliant=compliant),
    }


CSV_COLUMNS = [
    "id",
    "intent_key",
    "question",
    "response",
    "system_prompt",
    "tone_prompt",
    "custom_prompt",
    "system_followed",
    "tone_followed",
    "custom_followed",
    "compliant",
    "issue_count",
    "bugs",
]
