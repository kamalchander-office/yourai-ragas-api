"""Tests for YourAI response parser."""

from yourai_chat.parser import parse_chat_response


def test_parse_full_response():
    raw = {
        "answer": "The document contains indemnity terms.",
        "source": "chat_document",
        "doc_id": "doc-123",
        "reference": "Section 4.2",
        "reference_text": "Party A shall indemnify...",
        "contexts": ["chunk one"],
    }
    out = parse_chat_response(question="What is in the doc?", raw=raw, http_status=200)
    assert out["actual_answer"] == "The document contains indemnity terms."
    assert out["answer"] == out["actual_answer"]
    assert out["actual_source"] == "chat_document"
    assert out["actual_doc_id"] == "doc-123"
    assert out["reference"] == "Section 4.2"
    assert out["reference_text"] == "Party A shall indemnify..."
    assert out["contexts"] == ["chunk one"]


def test_parse_missing_attribution_fields():
    raw = {"message": "Hello"}
    out = parse_chat_response(question="Hi?", raw=raw)
    assert out["actual_answer"] == "Hello"
    assert out["actual_source"] is None
    assert out["actual_doc_id"] is None
    assert out["reference"] is None
    assert out["reference_text"] is None
    assert out["contexts"] == []


def test_parse_empty_response():
    out = parse_chat_response(question="Q", raw=None)
    assert out["actual_answer"] == ""
    assert out["raw_response"] == {}
