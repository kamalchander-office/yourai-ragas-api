from qa.intent_compatibility import (
    HARNESS_SKIP_INTENTS,
    filter_intents_for_document,
    intent_compatible_with_profile,
)


def _intents(*keys: str):
    return [{"key": k, "id": f"id-{k}"} for k in keys]


def test_find_document_always_skipped():
    profile = {"document_types": ["contract", "nda"]}
    ok, reason = intent_compatible_with_profile("FIND_DOCUMENT", profile)
    assert not ok
    assert "manual" in reason.lower() or "find" in reason.lower()
    assert "FIND_DOCUMENT" in HARNESS_SKIP_INTENTS


def test_contract_review_requires_contract_type():
    profile = {"document_types": ["case_law", "court_opinion"]}
    ok, _ = intent_compatible_with_profile("CONTRACT_REVIEW", profile)
    assert not ok

    profile_contract = {"document_types": ["contract", "nda"]}
    ok, _ = intent_compatible_with_profile("CONTRACT_REVIEW", profile_contract)
    assert ok


def test_wildcard_intents_allow_case_law_doc():
    profile = {"document_types": ["case_law", "court_opinion"]}
    for key in ("LEGAL_QA", "DOCUMENT_SUMMARISATION", "GENERAL_CHAT"):
        ok, _ = intent_compatible_with_profile(key, profile)
        assert ok, key


def test_case_law_analysis_requires_case_type():
    profile = {"document_types": ["case_law", "court_opinion"]}
    ok, _ = intent_compatible_with_profile("CASE_LAW_ANALYSIS", profile)
    assert ok

    profile_contract = {"document_types": ["contract"]}
    ok, _ = intent_compatible_with_profile("CASE_LAW_ANALYSIS", profile_contract)
    assert not ok


def test_filter_intents_excludes_incompatible():
    intents = _intents(
        "LEGAL_QA",
        "CONTRACT_REVIEW",
        "FIND_DOCUMENT",
        "CASE_LAW_ANALYSIS",
    )
    profile = {"document_types": ["case_law", "court_opinion"]}
    eligible, skipped = filter_intents_for_document(intents, profile)
    keys = {i["key"] for i in eligible}
    assert "LEGAL_QA" in keys
    assert "CASE_LAW_ANALYSIS" in keys
    assert "CONTRACT_REVIEW" not in keys
    assert "FIND_DOCUMENT" not in keys
    assert len(skipped) == 2
