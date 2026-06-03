"""Document text extraction helpers."""

from yourai_chat.document_text import extract_text_from_bytes


def test_extract_plain_text():
    data = b"Section 1: The party shall indemnify the other."
    text = extract_text_from_bytes(data, filename="clause.txt", content_type="text/plain")
    assert "indemnify" in text
