"""LLM judge: strict separate checks for system, tone, and custom intent prompts."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from llm import config as llm_config
from llm import gemini_client, openai_client, openrouter_client

# ── Three dedicated strict judges (one prompt type each — no cross-contamination) ──

_STRICT_ISSUE_SCHEMA = """
Return JSON only:
{
  "followed": true or false,
  "compliant": true or false,
  "issues": [
    {
      "severity": "high | medium | low",
      "location": "where in the response",
      "violation": "what exactly failed",
      "response_excerpt": "quote from the response",
      "prompt_rule": "exact rule from the prompt that was broken",
      "why": "why this breaks compliance",
      "fix": "what the response must do to comply"
    }
  ]
}

If EVERY rule is satisfied: {"followed": true, "compliant": true, "issues": []}.
If ANY rule is violated: {"followed": false, "compliant": false, "issues": [...]}.
Each issue must be unique. Quote the response. Cite the specific broken rule."""

SYSTEM_STRICT_JUDGE = f"""You are a STRICT system-prompt compliance auditor for a legal AI chatbot.

YOUR ONLY JOB: decide if the RESPONSE follows EVERY rule in the SYSTEM PROMPT.
- Check role, routing, answer structure (all numbered sections), length limits, safety rules,
  banned behaviours, citation/confidence requirements defined in the SYSTEM PROMPT only.
- Do NOT evaluate tone prompt or custom instruction — ONLY the system prompt.
- Be strict: if a required structural element is missing, followed=false.
- List a separate issue for each distinct system-prompt rule that was violated.

{_STRICT_ISSUE_SCHEMA}"""

TONE_STRICT_JUDGE = f"""You are a STRICT tone-prompt compliance auditor for a legal AI chatbot.

YOUR ONLY JOB: decide if the RESPONSE follows EVERY rule in the TONE PROMPT.
- Check voice, formatting, bullet/prose rules, citation style, banned opening phrases,
  confidence rating, jurisdiction notes, length, closing/next-action requirements
  defined in the TONE PROMPT only.
- Do NOT evaluate system prompt or custom instruction — ONLY the tone prompt.
- Be strict: if tone requires a confidence rating and it is absent, followed=false.
- List a separate issue for each distinct tone-prompt rule that was violated.

{_STRICT_ISSUE_SCHEMA}"""

CUSTOM_STRICT_JUDGE = f"""You are a STRICT custom-instruction compliance auditor for a legal AI chatbot.

YOUR ONLY JOB: decide if the RESPONSE follows EVERY rule in the CUSTOM INSTRUCTION.
- Check mandatory phrases, formatting constraints, bullet-only rules, required closings,
  and any other explicit custom rules.
- Do NOT evaluate system prompt or tone prompt — ONLY the custom instruction.
- Be strict: if custom instruction says "every response must use bullet points" and
  the response has prose paragraphs, followed=false.
- List a separate issue for each distinct custom rule that was violated.

{_STRICT_ISSUE_SCHEMA}"""

PROMPT_CHECKS: list[tuple[str, str, str]] = [
    ("system_prompt", "SYSTEM PROMPT", SYSTEM_STRICT_JUDGE),
    ("tone_prompt", "TONE PROMPT", TONE_STRICT_JUDGE),
    ("custom_instruction", "CUSTOM INSTRUCTION", CUSTOM_STRICT_JUDGE),
]


def _judge_chat_json(user_text: str, *, system_text: str, temperature: float = 0.1) -> str:
    provider = llm_config.JUDGE_PROVIDER
    if provider == "gemini":
        return gemini_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
            json_mode=True,
        )
    if provider == "openrouter":
        return openrouter_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
            json_mode=True,
        )
    return openai_client.generate(
        user_text=user_text,
        system_text=system_text,
        temperature=temperature,
        json_mode=True,
    )


def _parse_judge_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"followed": True, "compliant": True, "issues": []}

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return {
        "followed": False,
        "compliant": False,
        "issues": [
            {
                "severity": "high",
                "location": "judge output",
                "violation": "Judge returned unparseable output",
                "response_excerpt": "",
                "prompt_rule": "n/a",
                "why": text[:500],
                "fix": "Re-run intent evaluation",
            }
        ],
    }


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def normalize_issue(
    raw: dict[str, Any],
    *,
    case_id: str = "",
    prompt_source: str = "",
) -> dict[str, str]:
    """Map judge issue to a stable, detailed record."""
    source = _norm_key(prompt_source or str(raw.get("prompt_source") or "unknown"))
    source = source.replace(" ", "_")
    if source not in ("system_prompt", "tone_prompt", "custom_instruction", "unknown", "judge"):
        source = prompt_source or "unknown"

    violation = str(raw.get("violation") or raw.get("issue") or "").strip()
    location = str(raw.get("location") or "").strip()
    why = str(raw.get("why") or raw.get("reason") or "").strip()
    fix = str(raw.get("fix") or "").strip()
    excerpt = str(raw.get("response_excerpt") or "").strip()
    rule = str(raw.get("prompt_rule") or "").strip()
    severity = _norm_key(str(raw.get("severity") or "medium"))
    if severity not in ("high", "medium", "low"):
        severity = "medium"

    if not violation:
        violation = "Unspecified prompt compliance violation"

    issue_line = violation
    if location:
        issue_line = f"[{location}] {violation}"
    if excerpt:
        issue_line = f"{issue_line} — excerpt: \"{excerpt[:120]}\""

    why_parts = [p for p in (why, f"Broken rule: {rule}" if rule else "") if p]
    why_full = " ".join(why_parts) if why_parts else "Prompt rule violated"
    if fix:
        why_full = f"{why_full} Expected fix: {fix}"

    fingerprint = "|".join(
        [case_id, source, _norm_key(location)[:80], _norm_key(violation)[:120]]
    )

    return {
        "prompt_source": source,
        "severity": severity,
        "location": location,
        "violation": violation,
        "response_excerpt": excerpt,
        "prompt_rule": rule,
        "why": why_full,
        "fix": fix,
        "issue": issue_line,
        "fingerprint": fingerprint,
    }


def dedupe_issues(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in issues:
        key = item.get("fingerprint") or _norm_key(item.get("violation", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _build_strict_user_prompt(
    *,
    check_label: str,
    prompt_text: str,
    question: str,
    response: str,
    intent_label: str,
) -> str:
    return (
        f"STRICT COMPLIANCE CHECK: {check_label}\n"
        f"Verify the RESPONSE obeys EVERY rule in the {check_label} below.\n"
        f"Ignore all other prompt types.\n\n"
        f"QUESTION:\n{question}\n\n"
        f"RESPONSE:\n{response}\n\n"
        f"INTENT: {intent_label}\n\n"
        f"{check_label}:\n{prompt_text}\n"
    )


def _empty_check_result(prompt_key: str, *, skipped: bool = True) -> dict[str, Any]:
    return {
        "prompt_key": prompt_key,
        "evaluated": False,
        "skipped": skipped,
        "followed": None,
        "compliant": None,
        "issue_count": 0,
        "issues": [],
    }


def run_strict_prompt_check(
    *,
    prompt_key: str,
    check_label: str,
    judge_system: str,
    prompt_text: str,
    question: str,
    response: str,
    intent_label: str,
    case_id: str,
    judge_fn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Run one isolated strict check for a single prompt type."""
    text = (prompt_text or "").strip()
    if not text:
        return _empty_check_result(prompt_key)

    user_prompt = _build_strict_user_prompt(
        check_label=check_label,
        prompt_text=text,
        question=question,
        response=response,
        intent_label=intent_label,
    )
    call = judge_fn or _judge_chat_json
    raw = call(user_prompt, system_text=judge_system)
    parsed = _parse_judge_json(raw)

    issues_raw = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    issues: list[dict[str, str]] = []
    for item in issues_raw:
        if isinstance(item, dict):
            issues.append(normalize_issue(item, case_id=case_id, prompt_source=prompt_key))
    issues = dedupe_issues(issues)

    followed = bool(parsed.get("followed")) and not issues
    compliant = bool(parsed.get("compliant")) and followed
    if not followed and not issues:
        issues.append(
            normalize_issue(
                {
                    "severity": "high",
                    "location": "overall response",
                    "violation": f"{check_label} marked not followed but no issues listed",
                    "prompt_rule": text[:200],
                    "why": "Strict judge flagged failure without specifics",
                    "fix": f"Revise response to satisfy all {check_label} rules",
                },
                case_id=case_id,
                prompt_source=prompt_key,
            )
        )
        compliant = False

    return {
        "prompt_key": prompt_key,
        "evaluated": True,
        "skipped": False,
        "followed": followed,
        "compliant": compliant,
        "issue_count": len(issues),
        "issues": issues,
    }


def evaluate_response_compliance(
    *,
    question: str,
    response: str,
    prompts: dict[str, str],
    case_id: str = "",
    judge_fn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """
    Run three strict isolated checks: system_prompt, tone_prompt, custom_instruction.

    Returns:
      compliant — true only if every evaluated check passed
      checks — per-prompt followed/compliant status
      issues — all violations (tagged by prompt_source)
    """
    answer = (response or "").strip()
    intent_label = prompts.get("intent_label") or prompts.get("intent_key") or "unknown"

    if not answer or answer.startswith("ERROR:"):
        issue = normalize_issue(
            {
                "prompt_source": "unknown",
                "severity": "high",
                "location": "entire response",
                "violation": "No valid API response to evaluate",
                "response_excerpt": answer[:120] if answer else "",
                "why": "Collection failed or answer is empty",
                "fix": "Re-run client.py and collect a valid answer",
            },
            case_id=case_id,
        )
        return {
            "compliant": False,
            "checks": {
                "system_prompt": _empty_check_result("system_prompt", skipped=False),
                "tone_prompt": _empty_check_result("tone_prompt", skipped=False),
                "custom_instruction": _empty_check_result("custom_instruction", skipped=False),
            },
            "issues": [issue],
            "prompts": prompts,
        }

    checks: dict[str, dict[str, Any]] = {}
    all_issues: list[dict[str, str]] = []

    for prompt_key, check_label, judge_system in PROMPT_CHECKS:
        result = run_strict_prompt_check(
            prompt_key=prompt_key,
            check_label=check_label,
            judge_system=judge_system,
            prompt_text=prompts.get(prompt_key) or "",
            question=question,
            response=answer,
            intent_label=intent_label,
            case_id=case_id,
            judge_fn=judge_fn,
        )
        checks[prompt_key] = result
        all_issues.extend(result["issues"])

    evaluated = [c for c in checks.values() if c.get("evaluated")]
    if not evaluated:
        issue = normalize_issue(
            {
                "prompt_source": "unknown",
                "severity": "high",
                "location": "intent configuration",
                "violation": "Intent has no system, tone, or custom prompts to evaluate",
                "why": "All three prompt fields are empty in session.json",
                "fix": "Re-run bootstrap_session.py to refresh intents",
            },
            case_id=case_id,
        )
        all_issues.append(issue)
        return {
            "compliant": False,
            "checks": checks,
            "issues": all_issues,
            "prompts": prompts,
        }

    compliant = all(c.get("followed") for c in evaluated)
    return {
        "compliant": compliant,
        "checks": checks,
        "issues": dedupe_issues(all_issues),
        "prompts": prompts,
    }


def check_status_label(check: dict[str, Any]) -> str:
    """PASS / FAIL / SKIP for terminal output."""
    if check.get("skipped") or not check.get("evaluated"):
        return "SKIP"
    return "PASS" if check.get("followed") else "FAIL"
