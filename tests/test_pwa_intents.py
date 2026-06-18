from yourai_pwa.intents import normalize_intent, parse_intents_response
from yourai_pwa.response import normalize_chat_response


def test_normalize_intent_camel_case():
    raw = {
        "id": "9304b526-9d94-4417-9cb0-66f06df14fa1",
        "key": "DOCUMENT_SUMMARISATION",
        "triggerKeywords": ["summarise document", "brief this contract"],
        "tonePrompt": "Be concise",
        "customInstruction": "Use document only",
        "openingBehaviour": "ASK_CLARIFYING_QUESTION",
    }
    out = normalize_intent(raw)
    assert out["id"] == raw["id"]
    assert out["key"] == "DOCUMENT_SUMMARISATION"
    assert "summarise document" in out["trigger_keywords"]
    assert out["tone_prompt"] == "Be concise"
    assert out["opening_behaviour"] == "ASK_CLARIFYING_QUESTION"


def test_parse_intents_response_wrapped():
    body = {
        "success": True,
        "data": [
            {"id": "abc", "key": "GENERAL_CHAT", "keywords": ["hello"]},
        ],
    }
    intents = parse_intents_response(body)
    assert len(intents) == 1
    assert intents[0]["key"] == "GENERAL_CHAT"


def test_normalize_chat_response_pwa_shape():
    raw = {
        "data": {
            "answer": "Summary here.",
            "answerStatus": "grounded",
            "success": True,
            "sourcesUsed": [{"kind": "UPLOADED_DOC", "id": "doc-1"}],
            "retrievalSummary": {"chunksRetrieved": 3, "scopeLocked": True},
            "latencyMs": 1200,
        }
    }
    out = normalize_chat_response(raw)
    assert out["answer"] == "Summary here."
    assert out["answer_status"] == "grounded"
    assert out["retrieval_summary"]["chunks_retrieved"] == 3
    assert out["latency_ms"] == 1200
