from qa.document_profile import heuristic_document_profile
from qa.local_documents import DocumentContext


def test_heuristic_classifies_court_opinion():
    text = (
        "COMMONWEALTH OF PENNSYLVANIA v. DHRUVAL T. PATEL\n"
        "IN THE SUPERIOR COURT OF PENNSYLVANIA\n"
        "MEMORANDUM BY OLSON, J.\n"
        "Appellant appeals from the PCRA order.\n"
    )
    doc = DocumentContext(
        document_id="x",
        filename="CaseFile.docx",
        local_path="/tmp/CaseFile.docx",
        text=text,
        text_truncated=False,
    )
    profile = heuristic_document_profile(doc)
    assert "case_law" in profile["document_types"]
    assert "court_opinion" in profile["document_types"]
    assert "contract" not in profile["document_types"]


def test_heuristic_classifies_contract():
    text = "THIS AGREEMENT is entered into WHEREAS the Parties hereto agree to INDEMNIFY..."
    doc = DocumentContext(
        document_id="x",
        filename="SampleNDA.docx",
        local_path="/tmp/SampleNDA.docx",
        text=text,
        text_truncated=False,
    )
    profile = heuristic_document_profile(doc)
    assert "contract" in profile["document_types"]
