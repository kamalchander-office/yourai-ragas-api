"""Tests for YourVault helpers and scope resolution."""

from yourai_pwa.vault import (
    parse_comma_separated,
    parse_document_id_from_url,
)


def test_parse_comma_separated():
    assert parse_comma_separated("") == []
    assert parse_comma_separated("a,b, c") == ["a", "b", "c"]
    assert parse_comma_separated("id1;\nid2") == ["id1", "id2"]


def test_parse_document_id_from_url():
    url = (
        "https://media-qa.yourai.com/documents/"
        "acf2061e-6bc1-45db-997e-1a16861be168/ANWqOT4ijNzBatLM.docx"
    )
    assert parse_document_id_from_url(url) == "acf2061e-6bc1-45db-997e-1a16861be168"
    assert parse_document_id_from_url("") is None


def test_get_session_scope_legacy():
    from qa.session_store import get_session_scope

    session = {"document": {"id": "doc-1"}}
    scope = get_session_scope(session)
    assert scope["document_ids"] == ["doc-1"]
    assert scope["primary_document_id"] == "doc-1"
    assert scope["folder_id"] is None


def test_get_session_scope_vault_attachment():
    from qa.session_store import get_session_scope

    session = {
        "attachment": {
            "document_ids": ["d1", "d2"],
            "folder_id": "folder-1",
            "folder_name": "Discovery",
        }
    }
    scope = get_session_scope(session)
    assert scope["document_ids"] == ["d1", "d2"]
    assert scope["folder_id"] == "folder-1"
    assert scope["primary_document_id"] == "d1"
