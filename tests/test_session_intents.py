from qa.session_store import bind_intent_to_case, find_platform_intent


def _session():
    return {
        "default_intent_key": "GENERAL_CHAT",
        "default_intent_id": "aaa-bbb",
        "intents": [
            {
                "key": "LEGAL_QA",
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "LEGAL_QA",
                "raw": {"label": "Legal Q&A"},
            },
            {
                "key": "LEGAL_RESEARCH",
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "LEGAL_RESEARCH",
                "raw": {"label": "Legal Research"},
            },
        ],
    }


def test_bind_by_intent_key():
    case = {"id": "TC-1", "intent_key": "LEGAL_QA", "question": "q"}
    assert bind_intent_to_case(case, _session())
    assert case["intent_id"] == "11111111-1111-1111-1111-111111111111"
    assert case["intent"] == "Legal Q&A"


def test_bind_by_typo_alias():
    case = {"id": "TC-2", "intent": "legal reserach", "question": "q"}
    hit = find_platform_intent(_session(), case)
    assert hit is not None
    assert hit["key"] == "LEGAL_RESEARCH"
    bind_intent_to_case(case, _session())
    assert case["intent_id"].startswith("22222222")
