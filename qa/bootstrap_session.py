"""
Bootstrap a PWA QA session: API login → new chat → vault attach → intents.

Prerequisites (.env):
  YOURAI_PWA_LOGIN_EMAIL / YOURAI_PWA_LOGIN_PASSWORD / YOURAI_PWA_OTP_BYPASS
  (or ya_access + ya_refresh cookies)

Usage:
  # Legacy — upload local file to vault
  python qa/bootstrap_session.py --mode upload --document documents/CaseFile.docx

  # Pick from YourVault (comma-separated ids, names, or media URLs)
  python qa/bootstrap_session.py --mode vault \\
    --vault-document-ids acf2061e-...,ebdc511f-...
  python qa/bootstrap_session.py --mode vault \\
    --vault-document-names CaseFile
  python qa/bootstrap_session.py --mode vault \\
    --vault-file-urls "https://media-qa.yourai.com/documents/.../file.docx"
  python qa/bootstrap_session.py --mode vault \\
    --vault-document-ids acf2061e-... --vault-folder-name "Discovery Documents"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from qa.session_store import save_session
from yourai_pwa.bootstrap import bootstrap_qa_session, bootstrap_vault_session
from yourai_pwa.vault import parse_comma_separated

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap YourAI PWA QA session.")
    parser.add_argument(
        "--mode",
        choices=["upload", "vault"],
        default="upload",
        help="upload = local file to vault (legacy); vault = pick existing YourVault doc/folder",
    )
    parser.add_argument(
        "--document",
        default=None,
        help="Local file to upload (required for --mode upload)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Display name in vault on upload (default: filename stem)",
    )
    parser.add_argument(
        "--vault-document-ids",
        default="",
        help="Comma-separated vault document UUIDs",
    )
    parser.add_argument(
        "--vault-document-names",
        default="",
        help="Comma-separated vault document display names",
    )
    parser.add_argument(
        "--vault-file-urls",
        default="",
        help="Comma-separated media fileUrl values (UUID parsed from path)",
    )
    parser.add_argument(
        "--vault-folder-id",
        default="",
        help="Vault folder UUID for folder attach (optional, combinable with docs)",
    )
    parser.add_argument(
        "--vault-folder-name",
        default="",
        help="Vault folder display name (optional)",
    )
    parser.add_argument(
        "--reuse-chat",
        action="store_true",
        help="Reuse existing conversation (default: start fresh with reuse=false)",
    )
    parser.add_argument(
        "--default-intent",
        default="GENERAL_CHAT",
        help="Intent key stored as default for chat (default: GENERAL_CHAT)",
    )
    parser.add_argument(
        "--skip-corpus-download",
        action="store_true",
        help="Vault mode only: attach without downloading fileUrl for case generation",
    )
    args = parser.parse_args()

    if args.mode == "upload":
        if not args.document:
            sys.exit("ERROR: --document is required for --mode upload")
        doc = Path(args.document).expanduser()
        if not doc.is_file() and not (ROOT / doc).is_file():
            sys.exit(f"ERROR: document not found: {doc}")
        doc_path = doc if doc.is_file() else ROOT / doc
        print(f"Bootstrapping PWA QA session (upload): {doc_path.name}\n")
        session = bootstrap_qa_session(
            doc_path,
            new_chat=not args.reuse_chat,
            document_name=args.name,
            default_intent_key=args.default_intent,
        )
    else:
        doc_ids = parse_comma_separated(args.vault_document_ids)
        doc_names = parse_comma_separated(args.vault_document_names)
        file_urls = parse_comma_separated(args.vault_file_urls)
        folder_id = (args.vault_folder_id or "").strip() or None
        folder_name = (args.vault_folder_name or "").strip() or None
        print("Bootstrapping PWA QA session (vault pick)\n")
        session = bootstrap_vault_session(
            new_chat=not args.reuse_chat,
            default_intent_key=args.default_intent,
            document_ids=doc_ids or None,
            document_names=doc_names or None,
            file_urls=file_urls or None,
            folder_id=folder_id,
            folder_name=folder_name,
            download_corpus=not args.skip_corpus_download,
        )

    out = save_session(session)

    scope = session.get("attachment") or {}
    doc_ids = scope.get("document_ids") or []
    folder = scope.get("folder_id") or "—"

    print("\n✓ Session ready")
    print(f"  mode            : {session.get('bootstrap_mode', 'upload')}")
    print(f"  conversation_id : {session['conversation_id']}")
    print(f"  document_ids    : {', '.join(doc_ids) if doc_ids else '—'}")
    print(f"  folder_id       : {folder}")
    if session.get("document", {}).get("id"):
        print(f"  primary doc     : {session['document']['id']}")
    print(f"  intents loaded  : {len(session.get('intents') or [])}")
    print(f"  saved           : {out.resolve()}")
    print("\nNext:")
    print("  python qa/generate_cases.py --from-session --refill-ground-truth")
    print("  python qa/client.py --backend pwa")


if __name__ == "__main__":
    main()
