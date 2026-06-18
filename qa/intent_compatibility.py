"""
Match PWA intents to document types for harness-eligible test cases.

FIND_DOCUMENT is excluded from automated harness runs (manual QA only).
"""

from __future__ import annotations

from typing import Any

# Never auto-generate or collect via API harness — tested manually in the PWA UI.
HARNESS_SKIP_INTENTS: frozenset[str] = frozenset({"FIND_DOCUMENT"})

# Intents that are not exercised via an uploaded scoped document in this harness.
DOC_SESSION_EXCLUDED_INTENTS: frozenset[str] = frozenset(
    {
        "FIND_DOCUMENT",
        "DOCUMENT_DRAFTING",
        "EMAIL_DRAFTING",
    }
)

# "*" = any attached document is valid for this intent in the harness.
# list = at least one profile document_type must match (case-insensitive substring).
INTENT_DOCUMENT_TYPES: dict[str, str | list[str]] = {
    "GENERAL_CHAT": "*",
    "LEGAL_QA": "*",
    "LEGAL_RESEARCH": "*",
    "DOCUMENT_SUMMARISATION": "*",
    "CASE_LAW_ANALYSIS": [
        "case_law",
        "court_opinion",
        "judicial_opinion",
        "appellate_opinion",
        "court_decision",
        "legal_memo",
    ],
    "CONTRACT_REVIEW": ["contract", "nda", "msa", "lease", "agreement"],
    "RISK_ASSESSMENT": ["contract", "nda", "msa", "lease", "agreement"],
    "CLAUSE_ANALYSIS": ["contract", "nda", "msa", "lease", "agreement"],
    "CLAUSE_COMPARISON": ["contract", "nda", "msa", "lease", "agreement"],
    "DUE_DILIGENCE": [
        "contract",
        "nda",
        "msa",
        "lease",
        "agreement",
        "deal_document",
        "data_room",
    ],
    "COMPLIANCE_CHECK": [
        "policy",
        "compliance_document",
        "regulatory_filing",
        "contract",
        "privacy_policy",
    ],
}

# Intent-specific question shape for AI generation (task, not just keywords).
INTENT_TASK_INSTRUCTIONS: dict[str, str] = {
    "GENERAL_CHAT": (
        "Questions MUST be greetings, meta/help about the assistant, or light conversational "
        "follow-ups — NOT deep document analysis. Examples: hello, what can you do, thanks."
    ),
    "LEGAL_QA": (
        "Questions MUST ask a specific legal question answerable from this document. "
        "Use direct Q&A phrasing."
    ),
    "LEGAL_RESEARCH": (
        "Questions MUST request research-style analysis (statutes, precedents, procedural impact) "
        "grounded in this document. Phrase like a research request."
    ),
    "DOCUMENT_SUMMARISATION": (
        "Questions MUST explicitly ask to summarize, brief, or overview the uploaded document "
        "(e.g. 'Summarize this opinion for a partner', 'Give me an executive summary of this file')."
    ),
    "CASE_LAW_ANALYSIS": (
        "Questions MUST ask to analyze, brief, or explain this case/ruling — holdings, reasoning, "
        "procedural posture, or impact."
    ),
    "CONTRACT_REVIEW": (
        "Questions MUST ask to review, triage, or audit the uploaded agreement/contract "
        "(e.g. 'Review this contract for risk', 'Should we sign this NDA?')."
    ),
    "RISK_ASSESSMENT": (
        "Questions MUST ask to assess legal/business risks in the uploaded document or situation "
        "described therein, with mitigation."
    ),
    "CLAUSE_ANALYSIS": (
        "Questions MUST ask to analyze a specific clause or provision in the uploaded document."
    ),
    "CLAUSE_COMPARISON": (
        "Questions MUST ask to compare clauses or versions within or against the uploaded document."
    ),
    "DUE_DILIGENCE": (
        "Questions MUST ask for due-diligence style issue extraction from the uploaded deal/transaction document."
    ),
    "COMPLIANCE_CHECK": (
        "Questions MUST ask to check the uploaded document against a regulatory or policy framework."
    ),
}


def _norm_types(profile: dict[str, Any]) -> set[str]:
    raw = profile.get("document_types") or []
    return {str(t).strip().lower() for t in raw if str(t).strip()}


def _type_matches(required: str, doc_types: set[str]) -> bool:
    req = required.strip().lower()
    if not req:
        return False
    for dt in doc_types:
        if req in dt or dt in req:
            return True
    return False


def intent_compatible_with_profile(intent_key: str, profile: dict[str, Any]) -> tuple[bool, str]:
    """Return (eligible, reason)."""
    key = (intent_key or "").strip().upper()
    if not key:
        return False, "missing intent_key"

    if key in HARNESS_SKIP_INTENTS:
        return False, "manual QA only (FIND_DOCUMENT)"

    if key in DOC_SESSION_EXCLUDED_INTENTS:
        return False, "not tested via scoped-document harness"

    requirement = INTENT_DOCUMENT_TYPES.get(key)
    if requirement is None:
        return False, f"no document compatibility rule for {key}"

    if requirement == "*":
        return True, "compatible with any uploaded document"

    doc_types = _norm_types(profile)
    if not doc_types:
        return False, "document profile has no document_types"

    required_list = requirement if isinstance(requirement, list) else [requirement]
    for req in required_list:
        if _type_matches(req, doc_types):
            return True, f"document type matches {req}"

    need = ", ".join(required_list)
    have = ", ".join(sorted(doc_types)) or "(none)"
    return False, f"document types [{have}] do not match intent requirement [{need}]"


def filter_intents_for_document(
    intents: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    explicit_keys: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """
    Return (eligible intents, skipped records with key + reason).

    explicit_keys: if set, only consider these intent keys (still compatibility-filtered).
    """
    wanted: set[str] | None = None
    if explicit_keys:
        wanted = {k.upper() for k in explicit_keys if k}

    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for intent in intents:
        key = (intent.get("key") or "").strip().upper()
        if not key:
            continue
        if wanted is not None and key not in wanted:
            continue

        ok, reason = intent_compatible_with_profile(key, profile)
        if ok:
            eligible.append(intent)
        else:
            skipped.append({"intent_key": key, "reason": reason})

    return eligible, skipped


def annotate_case_harness_eligibility(
    case: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Set harness_eligible and harness_skip_reason on a test case."""
    key = (case.get("intent_key") or "").strip().upper()
    if not key and case.get("intent_id"):
        key = (case.get("intent") or "").strip().upper()

    ok, reason = intent_compatible_with_profile(key, profile) if key else (False, "missing intent_key")
    case["harness_eligible"] = ok
    case["harness_skip_reason"] = "" if ok else reason
    return case


def intent_task_instruction(intent_key: str) -> str:
    key = (intent_key or "").strip().upper()
    return INTENT_TASK_INSTRUCTIONS.get(
        key,
        "Questions MUST match the user task implied by this intent (not generic unrelated Q&A).",
    )
