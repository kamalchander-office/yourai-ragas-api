"""Load/save qa/session.json and bind platform intents onto test cases."""

from __future__ import annotations

import json
import re
from pathlib import Path

from yourai_pwa.intents import intent_by_key

from qa.paths import SESSION_FILE, TEST_CASES_FILE

QA_DIR = Path(__file__).parent

# Spreadsheet labels / typos → platform intent key (from GET /knowledge-base/intents)
_INTENT_ALIASES: dict[str, str] = {
    "general chat": "GENERAL_CHAT",
    "legal q&a": "LEGAL_QA",
    "legal qa": "LEGAL_QA",
    "legal q a": "LEGAL_QA",
    "legal research": "LEGAL_RESEARCH",
    "legal reserach": "LEGAL_RESEARCH",
    "legal reserch": "LEGAL_RESEARCH",
    "find document": "FIND_DOCUMENT",
    "find documents": "FIND_DOCUMENT",
    "document summarisation": "DOCUMENT_SUMMARISATION",
    "document summarization": "DOCUMENT_SUMMARISATION",
    "contract review": "CONTRACT_REVIEW",
    "clause analysis": "CLAUSE_ANALYSIS",
    "clause comparison": "CLAUSE_COMPARISON",
    "case law analysis": "CASE_LAW_ANALYSIS",
    "case law": "CASE_LAW_ANALYSIS",
}


def load_session(path: Path | None = None) -> dict:
    session_path = path or SESSION_FILE
    if not session_path.exists():
        raise FileNotFoundError(
            f"{session_path} not found.\n"
            "Run: python qa/bootstrap_session.py --document documents/YourFile.docx"
        )
    return json.loads(session_path.read_text())


def save_session(session: dict, path: Path | None = None) -> Path:
    session_path = path or SESSION_FILE
    session_path.write_text(json.dumps(session, indent=2))
    return session_path


def _norm_hint(value: str) -> str:
    text = (value or "").strip().upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return text.strip("_")


def _is_uuid(value: str) -> bool:
    v = (value or "").strip()
    return len(v) >= 32 and v.count("-") >= 4


def _intent_label(intent: dict) -> str:
    raw = intent.get("raw") if isinstance(intent.get("raw"), dict) else {}
    return (
        raw.get("label")
        or intent.get("name")
        or intent.get("key")
        or ""
    ).strip()


def find_platform_intent(session: dict, test_case: dict) -> dict | None:
    """Match a test case to a platform intent from session.json."""
    intents = session.get("intents") or []
    if not intents:
        return None

    intent_id = (test_case.get("intent_id") or "").strip()
    if _is_uuid(intent_id):
        for intent in intents:
            if intent.get("id") == intent_id:
                return intent

    intent_key = (test_case.get("intent_key") or "").strip()
    if intent_key:
        hit = intent_by_key(intents, intent_key)
        if hit:
            return hit

    hint = (test_case.get("intent") or "").strip()
    if not hint and intent_id and not _is_uuid(intent_id):
        hint = intent_id
    if not hint:
        return None

    alias_key = _INTENT_ALIASES.get(hint.lower())
    if alias_key:
        hit = intent_by_key(intents, alias_key)
        if hit:
            return hit

    norm_hint = _norm_hint(hint)
    for intent in intents:
        key = intent.get("key") or ""
        if _norm_hint(key) == norm_hint:
            return intent
        label = _intent_label(intent)
        if label and (_norm_hint(label) == norm_hint or norm_hint in _norm_hint(label)):
            return intent

    return None


def bind_intent_to_case(
    case: dict,
    session: dict,
    *,
    default_if_missing: bool = False,
) -> bool:
    """Set intent_id (UUID), intent_key, and intent label on a test case."""
    intent = find_platform_intent(session, case)
    if not intent and default_if_missing:
        default_key = session.get("default_intent_key") or "GENERAL_CHAT"
        intent = intent_by_key(session.get("intents") or [], default_key)
        if not intent and session.get("intents"):
            intent = session["intents"][0]

    if not intent or not intent.get("id"):
        return False

    case["intent_id"] = intent["id"]
    case["intent_key"] = intent.get("key") or ""
    case["intent"] = _intent_label(intent) or intent.get("key") or ""
    return True


def bind_intents_to_cases(
    cases: list[dict],
    session: dict | None = None,
    *,
    default_if_missing: bool = False,
) -> tuple[int, list[str]]:
    """
    Bind platform intent UUIDs onto all test cases.

    Returns (bound_count, case_ids that could not be resolved).
    """
    if session is None:
        try:
            session = load_session()
        except FileNotFoundError:
            return 0, []

    bound = 0
    misses: list[str] = []
    for case in cases:
        had_hint = bool(
            case.get("intent_key")
            or case.get("intent")
            or (_is_uuid(case.get("intent_id") or ""))
            or (
                case.get("intent_id")
                and not _is_uuid(case.get("intent_id") or "")
            )
        )
        if bind_intent_to_case(case, session, default_if_missing=default_if_missing or not had_hint):
            bound += 1
        elif had_hint:
            misses.append(case.get("id") or "?")
    return bound, misses


def resolve_intent_id(session: dict, test_case: dict) -> str:
    """Platform intent UUID for POST /chat — required for PWA backend."""
    intent = find_platform_intent(session, test_case)
    if intent and intent.get("id"):
        return intent["id"]
    return (session.get("default_intent_id") or "").strip()


def get_session_scope(session: dict) -> dict[str, Any]:
    """
    Normalized vault scope for pwa_collector.

    Returns document_ids, folder_id, and primary document_id (backward compatible).
    """
    attachment = session.get("attachment") or {}
    doc_ids = attachment.get("document_ids")
    if not doc_ids:
        legacy_id = (session.get("document") or {}).get("id")
        doc_ids = [legacy_id] if legacy_id else []
    doc_ids = [str(d) for d in doc_ids if d]

    folder_id = attachment.get("folder_id")
    primary = doc_ids[0] if doc_ids else (session.get("document") or {}).get("id")

    return {
        "document_ids": doc_ids,
        "folder_id": folder_id,
        "folder_name": attachment.get("folder_name"),
        "primary_document_id": str(primary) if primary else None,
    }

