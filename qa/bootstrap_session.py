"""
Bootstrap a PWA QA session: API login → new chat → upload doc → scope → intents.

Prerequisites (.env):
  YOURAI_PWA_LOGIN_EMAIL / YOURAI_PWA_LOGIN_PASSWORD / YOURAI_PWA_OTP_BYPASS
  (or ya_access + ya_refresh cookies)

Usage:
  python qa/bootstrap_session.py --document documents/CaseFile.docx
  python qa/bootstrap_session.py --document documents/CaseFile.docx --reuse-chat
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
from yourai_pwa.bootstrap import bootstrap_qa_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap YourAI PWA QA session.")
    parser.add_argument(
        "--document",
        required=True,
        help="Local file to upload to vault (PDF/DOCX/TXT)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Display name in vault (default: filename stem)",
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
    args = parser.parse_args()

    doc = Path(args.document).expanduser()
    if not doc.is_file() and not (ROOT / doc).is_file():
        sys.exit(f"ERROR: document not found: {doc}")
    doc_path = doc if doc.is_file() else ROOT / doc

    print(f"Bootstrapping PWA QA session with: {doc_path.name}\n")

    session = bootstrap_qa_session(
        doc_path,
        new_chat=not args.reuse_chat,
        document_name=args.name,
        default_intent_key=args.default_intent,
    )
    out = save_session(session)

    print("\n✓ Session ready")
    print(f"  conversation_id : {session['conversation_id']}")
    print(f"  document_id     : {session['document']['id']}")
    print(f"  intents loaded  : {len(session.get('intents') or [])}")
    print(f"  saved           : {out.resolve()}")
    print("\nNext:")
    print("  python qa/generate_cases.py --from-session --refill-ground-truth")
    print("  python qa/client.py --backend pwa")


if __name__ == "__main__":
    main()
