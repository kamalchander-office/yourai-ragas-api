"""Local document fixture loading."""

import json
from pathlib import Path

from qa.local_documents import LocalDocumentStore


def test_load_txt_fixture(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "sample.txt").write_text(
        "Miranda v. Arizona requires warnings before custodial interrogation.",
        encoding="utf-8",
    )
    store = LocalDocumentStore(docs)
    ctx = store.load_by_filename("sample.txt")
    assert "Miranda" in ctx.text
    assert ctx.document_id == "sample"


def test_load_misnamed_plain_text_docx(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "CaseFile.docx").write_text(
        "Miranda warnings apply before custodial interrogation.",
        encoding="utf-8",
    )
    store = LocalDocumentStore(docs)
    ctx = store.load_by_filename("CaseFile.docx")
    assert "Miranda" in ctx.text


def test_manifest_maps_document_id(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "CaseFile.txt").write_text("Clause 3.2 indemnity applies.", encoding="utf-8")
    (docs / "manifest.json").write_text(
        json.dumps({"uuid-123": "CaseFile.txt"}),
        encoding="utf-8",
    )
    store = LocalDocumentStore(docs)
    ctx = store.load_by_document_id("uuid-123")
    assert ctx.document_id == "uuid-123"
    assert "indemnity" in ctx.text
