"""
Analyse a local fixture document to determine which intents the harness can test.
"""

from __future__ import annotations

import json
import re
from typing import Any

from qa.local_documents import DocumentContext

_HEURISTIC_SAMPLE_CHARS = 12_000


def _head(text: str, limit: int = _HEURISTIC_SAMPLE_CHARS) -> str:
    return (text or "")[:limit]


def heuristic_document_profile(doc: DocumentContext) -> dict[str, Any]:
    """Fast classification from filename + text headers (no LLM)."""
    text = _head(doc.text)
    upper = text.upper()
    filename = (doc.filename or "").lower()
    types: set[str] = set()
    topics: list[str] = []

    court_markers = (
        "SUPERIOR COURT",
        "COURT OF APPEALS",
        "APPELLANT",
        "APPELLEE",
        "MEMORANDUM BY",
        "NON-PRECEDENTIAL",
        "PLAINTIFF",
        "DEFENDANT",
    )
    if any(m in upper for m in court_markers) or " v. " in text[:2000]:
        types.update({"case_law", "court_opinion", "judicial_opinion"})

    contract_markers = (
        "WHEREAS",
        "INDEMNIF",
        "THIS AGREEMENT",
        "PARTIES HERETO",
        "MASTER SERVICE",
        "NON-DISCLOSURE",
        "CONFIDENTIALITY AGREEMENT",
    )
    if any(m in upper for m in contract_markers) or any(
        x in filename for x in ("nda", "msa", "contract", "agreement", "lease")
    ):
        types.add("contract")
        if "nda" in filename or "NON-DISCLOSURE" in upper:
            types.add("nda")
        if "msa" in filename or "MASTER SERVICE" in upper:
            types.add("msa")

    policy_markers = ("GDPR", "HIPAA", "PRIVACY POLICY", "COMPLIANCE POLICY", "SOC 2")
    if any(m in upper for m in policy_markers):
        types.update({"policy", "compliance_document"})

    if "PCRA" in upper or "POST CONVICTION" in upper:
        topics.append("criminal procedure")
    if "MIRANDA" in upper:
        topics.append("Miranda")

    # Docket / caption line as weak topic hint
    caption = re.search(r"COMMONWEALTH OF [A-Z ]+ v\.", upper)
    if caption:
        topics.append("criminal appeal")

    if not types:
        types.add("general_legal_document")

    summary = f"Local fixture {doc.filename} classified as {', '.join(sorted(types))}."
    confidence = 0.85 if len(types) > 1 or "case_law" in types or "contract" in types else 0.6

    return {
        "filename": doc.filename,
        "document_types": sorted(types),
        "topics": topics,
        "summary": summary,
        "confidence": confidence,
        "source": "heuristic",
    }


def _llm_document_profile(doc: DocumentContext) -> dict[str, Any]:
    from llm.router import chat_json

    sample = doc.prompt_block(max_chars=6000)
    prompt = (
        "You classify legal documents for automated QA test planning.\n"
        "Read the sample below and return JSON only:\n"
        "{\n"
        '  "document_types": ["case_law", "court_opinion"],\n'
        '  "topics": ["short topic phrases"],\n'
        '  "summary": "one sentence",\n'
        '  "confidence": 0.0 to 1.0\n'
        "}\n\n"
        "Use document_types from this vocabulary when applicable:\n"
        "case_law, court_opinion, judicial_opinion, appellate_opinion, contract, nda, msa,\n"
        "lease, agreement, policy, compliance_document, regulatory_filing, deal_document,\n"
        "general_legal_document\n\n"
        f"{sample}\n"
    )
    raw = chat_json(prompt, temperature=0.1)
    data = json.loads(raw or "{}")
    types = data.get("document_types") if isinstance(data.get("document_types"), list) else []
    types = [str(t).strip().lower() for t in types if str(t).strip()]
    topics = data.get("topics") if isinstance(data.get("topics"), list) else []
    topics = [str(t).strip() for t in topics if str(t).strip()]
    summary = str(data.get("summary") or "").strip()
    try:
        confidence = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7

    if not types:
        types = ["general_legal_document"]

    return {
        "filename": doc.filename,
        "document_types": types,
        "topics": topics,
        "summary": summary or f"LLM-classified {doc.filename}.",
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "llm",
    }


def merge_profiles(heuristic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    """Combine heuristic + LLM types (union) for safer matching."""
    types = sorted(
        {
            *(t.lower() for t in heuristic.get("document_types") or []),
            *(t.lower() for t in llm.get("document_types") or []),
        }
    )
    topics = list(dict.fromkeys([*(heuristic.get("topics") or []), *(llm.get("topics") or [])]))
    summary = llm.get("summary") or heuristic.get("summary") or ""
    try:
        confidence = max(float(heuristic.get("confidence", 0)), float(llm.get("confidence", 0)))
    except (TypeError, ValueError):
        confidence = 0.7
    return {
        "filename": heuristic.get("filename") or llm.get("filename"),
        "document_types": types,
        "topics": topics,
        "summary": summary,
        "confidence": confidence,
        "source": "hybrid",
    }


def analyze_document(
    doc: DocumentContext,
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Build a document profile for intent compatibility filtering.

    use_llm=False → heuristics only (fast, for unit tests).
    """
    heuristic = heuristic_document_profile(doc)
    if not use_llm:
        return heuristic

    try:
        llm = _llm_document_profile(doc)
        return merge_profiles(heuristic, llm)
    except Exception as exc:
        heuristic["llm_error"] = str(exc)[:200]
        heuristic["source"] = "heuristic_fallback"
        return heuristic
