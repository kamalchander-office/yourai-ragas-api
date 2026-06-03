"""
Fill empty contexts from raw_response.source_attribution in results.json.

  python qa/reparse_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from yourai_chat.parser import parse_chat_response

QA_DIR = Path(__file__).parent
RESULTS_FILE = QA_DIR / "results.json"


def main() -> None:
    if not RESULTS_FILE.exists():
        sys.exit(f"ERROR: {RESULTS_FILE} not found")

    rows = json.loads(RESULTS_FILE.read_text())
    updated = 0
    with_contexts = 0

    for i, row in enumerate(rows):
        raw = row.get("raw_response")
        if not isinstance(raw, dict) or not raw:
            continue
        if row.get("contexts"):
            with_contexts += 1
            continue
        norm = parse_chat_response(question=row.get("question", ""), raw=raw)
        contexts = norm.get("contexts") or []
        if not contexts:
            continue
        row["contexts"] = contexts
        rows[i] = row
        updated += 1
        with_contexts += 1

    RESULTS_FILE.write_text(json.dumps(rows, indent=2))
    print(f"✓ Reparsed {len(rows)} rows — {updated} gained contexts ({with_contexts} total with contexts).")
    print("Next: python3 qa/run_eval.py")


if __name__ == "__main__":
    main()
