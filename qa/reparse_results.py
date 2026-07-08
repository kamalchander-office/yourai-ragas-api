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

from qa.paths import RESULTS_FILE, ensure_results_dir, migrate_legacy_outputs


def main() -> None:
    migrate_legacy_outputs()
    ensure_results_dir()

    if not RESULTS_FILE.exists():
        sys.exit(f"ERROR: {RESULTS_FILE} not found")

    rows = json.loads(RESULTS_FILE.read_text())
    updated = 0
    with_contexts = 0

    for i, row in enumerate(rows):
        if row.get("contexts"):
            with_contexts += 1
            continue
        raw = row.get("raw_response")
        if not isinstance(raw, dict):
            continue
        normalized = parse_chat_response(
            question=row.get("question", ""),
            raw=raw,
            http_status=200,
        )
        contexts = normalized.get("contexts") or []
        if contexts:
            row["contexts"] = contexts
            updated += 1
            with_contexts += 1

    RESULTS_FILE.write_text(json.dumps(rows, indent=2))
    print(f"✓ Updated {updated} row(s) with contexts ({with_contexts}/{len(rows)} total have contexts)")
    print(f"  Saved → {RESULTS_FILE}")


if __name__ == "__main__":
    main()
