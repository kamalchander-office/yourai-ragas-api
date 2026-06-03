"""Parser tests for YourAI chat respond shape (source_attribution)."""

from yourai_chat.parser import parse_chat_response


def test_parse_source_attribution_and_tier():
    raw = {
        "answer": "Miranda rights summary.",
        "source_types_used": ["UPLOADED_DOC"],
        "sources_used": [{"kind": "UPLOADED_DOC", "id": "doc-abc", "chunks_used": 1}],
        "source_attribution": [
            {
                "document_id": "doc-abc",
                "source_kind": "UPLOADED_DOC",
                "page_number": 1,
                "clause_ref": "p. 1",
                "snippet": "Right to remain silent and attorney.",
            }
        ],
        "tier": "L1",
        "answer_status": "partial",
        "debug_data": {"grounding_result": "passed"},
    }
    out = parse_chat_response(question="Miranda?", raw=raw, http_status=200)
    assert out["actual_source"] == "UPLOADED_DOC"
    assert out["actual_doc_id"] == "doc-abc"
    assert len(out["contexts"]) == 1
    assert "remain silent" in out["contexts"][0]
    assert out["tier"] == "L1"
    assert out["answer_status"] == "partial"
    assert out["grounding_passed"] is True
