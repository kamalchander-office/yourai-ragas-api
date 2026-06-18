"""
Load QA fixture documents from a local folder (PDF, DOCX, TXT).

Used by generate_cases.py for corpus-grounded questions and ground_truth.
YourAI chat eval still uses documents attached to the conversation in the product;
manifest.json links local files to YourAI document_id for expected_doc_id checks.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from yourai_chat.document_text import extract_text_from_bytes

log = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}


@dataclass
class DocumentContext:
    """Local document text ready for LLM prompts and test case metadata."""

    document_id: str
    filename: str
    local_path: str
    text: str
    text_truncated: bool
    source_type: str = "local_fixture"

    def prompt_block(self, max_chars: int | None = None) -> str:
        body = self.text
        truncated = self.text_truncated
        if max_chars and len(body) > max_chars:
            body = body[:max_chars] + "\n\n[... document truncated for prompt size ...]"
            truncated = True
        note = " (truncated)" if truncated else ""
        return (
            f"DOCUMENT: {self.filename}{note}\n"
            f"document_id: {self.document_id}\n"
            f"local_path: {self.local_path}\n"
            f"---\n{body}\n---"
        )


class LocalDocumentStore:
    """
    Read files from DOCUMENTS_DIR (default: project documents/).

    Optional manifest.json maps YourAI document_id → filename:
      {"3b0d30b1-...": "CaseFile.pdf"}
    """

    def __init__(self, documents_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        default_dir = root / "documents"
        self.documents_dir = Path(
            documents_dir or os.getenv("DOCUMENTS_DIR", str(default_dir))
        ).expanduser().resolve()
        self._max_text_chars = int(os.getenv("GENERATE_MAX_DOCUMENT_CHARS", "80000"))
        self._manifest = self._load_manifest()

    def _manifest_path(self) -> Path:
        return self.documents_dir / "manifest.json"

    def _load_manifest(self) -> dict[str, str]:
        path = self._manifest_path()
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if isinstance(v, str) and v.strip():
                out[str(k).strip()] = v.strip()
        return out

    def _read_file(self, path: Path, *, document_id: str) -> DocumentContext:
        if not path.is_file():
            raise FileNotFoundError(f"Document not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported file type {suffix!r} for {path.name}. "
                f"Use one of: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
            )

        data = path.read_bytes()
        if suffix == ".docx":
            text = self._extract_docx(data, path.name)
        else:
            mime = "application/pdf" if suffix == ".pdf" else "text/plain"
            text = extract_text_from_bytes(
                data, filename=path.name, content_type=mime
            )

        text = text.strip()
        truncated = False
        if len(text) > self._max_text_chars:
            text = text[: self._max_text_chars]
            truncated = True

        if not text:
            raise ValueError(f"No text extracted from {path.name}")

        rel = path.relative_to(self.documents_dir) if path.is_relative_to(self.documents_dir) else path.name
        return DocumentContext(
            document_id=document_id,
            filename=path.name,
            local_path=str(rel),
            text=text,
            text_truncated=truncated,
        )

    @staticmethod
    def _extract_docx(data: bytes, filename: str = "document.docx") -> str:
        import io
        import zipfile

        if data[:2] != b"PK":
            log.warning(
                "%s has .docx extension but is not a Word file; reading as plain text",
                filename,
            )
            return extract_text_from_bytes(
                data, filename=filename, content_type="text/plain"
            )

        try:
            from docx import Document

            doc = Document(io.BytesIO(data))
            return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        except zipfile.BadZipFile:
            log.warning(
                "%s is not a valid .docx zip archive; reading as plain text",
                filename,
            )
            return extract_text_from_bytes(
                data, filename=filename, content_type="text/plain"
            )

    def _resolve_path(self, filename: str) -> Path:
        name = filename.strip()
        direct = self.documents_dir / name
        if direct.is_file():
            return direct
        # allow nested paths in manifest
        for path in self.documents_dir.rglob(Path(name).name):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                return path
        raise FileNotFoundError(
            f"File {name!r} not under {self.documents_dir}. "
            "Place PDF/DOCX/TXT in the documents folder."
        )

    def load_by_filename(self, filename: str, *, document_id: str | None = None) -> DocumentContext:
        path = self._resolve_path(filename)
        doc_id = document_id or self._id_for_filename(filename) or path.stem
        return self._read_file(path, document_id=doc_id)

    def _id_for_filename(self, filename: str) -> str | None:
        for doc_id, fname in self._manifest.items():
            if fname == filename or Path(fname).name == Path(filename).name:
                return doc_id
        return None

    def load_by_document_id(self, document_id: str) -> DocumentContext:
        doc_id = document_id.strip()
        if doc_id in self._manifest:
            return self.load_by_filename(self._manifest[doc_id], document_id=doc_id)
        raise KeyError(
            f"document_id {doc_id!r} not in manifest.json. "
            f"Add: \"{doc_id}\": \"YourFile.pdf\""
        )

    def list_fixture_files(self) -> list[Path]:
        if not self.documents_dir.is_dir():
            return []
        files: list[Path] = []
        for path in sorted(self.documents_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                if path.name == "manifest.json":
                    continue
                files.append(path)
        return files

    def load_all_fixtures(self) -> dict[str, DocumentContext]:
        """Load every supported file in the documents folder."""
        if not self.documents_dir.is_dir():
            raise FileNotFoundError(
                f"Documents folder not found: {self.documents_dir}\n"
                "Create it and add PDF/DOCX/TXT files (see documents/README.md)."
            )

        out: dict[str, DocumentContext] = {}
        for path in self.list_fixture_files():
            filename = path.name
            doc_id = self._id_for_filename(filename) or path.stem
            ctx = self._read_file(path, document_id=doc_id)
            out[doc_id] = ctx
            out[filename] = ctx
        return out

    def load_many(
        self,
        *,
        filenames: list[str] | None = None,
        document_ids: list[str] | None = None,
        load_all: bool = False,
    ) -> dict[str, DocumentContext]:
        if load_all:
            return self.load_all_fixtures()

        out: dict[str, DocumentContext] = {}
        for fname in filenames or []:
            ctx = self.load_by_filename(fname)
            out[ctx.document_id] = ctx
            out[ctx.filename] = ctx

        for doc_id in document_ids or []:
            ctx = self.load_by_document_id(doc_id)
            out[ctx.document_id] = ctx
            out[ctx.filename] = ctx

        return out

    def load_for_cases(self, cases: list[dict]) -> dict[str, DocumentContext]:
        """Load documents referenced by document_file / document_id on test cases."""
        filenames: list[str] = []
        doc_ids: list[str] = []
        for c in cases:
            df = (c.get("document_file") or c.get("document") or "").strip()
            if df:
                filenames.append(df)
            for key in ("document_id", "expected_doc_id"):
                v = (c.get(key) or "").strip()
                if v:
                    doc_ids.append(v)
        return self.load_many(filenames=filenames, document_ids=doc_ids)
