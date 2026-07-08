"""
Fix results.json question/ground_truth fields from test_cases.json (no API calls).

  python3 qa/align_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qa.align import align_results, find_alignment_errors
from qa.paths import RESULTS_FILE, TEST_CASES_FILE, ensure_results_dir, migrate_legacy_outputs


def main() -> None:
    migrate_legacy_outputs()
    ensure_results_dir()

    if not RESULTS_FILE.exists():
        sys.exit(f"ERROR: {RESULTS_FILE} not found")
    if not TEST_CASES_FILE.exists():
        sys.exit(f"ERROR: {TEST_CASES_FILE} not found")

    test_cases = json.loads(TEST_CASES_FILE.read_text())
    results = json.loads(RESULTS_FILE.read_text())

    drift = find_alignment_errors(results, test_cases)
    if not drift:
        print("✓ results.json already matches test_cases.json for all ids and questions.")
        return

    print(f"Aligning {len(drift)} issue(s) …")
    for msg in drift[:10]:
        print(f"  • {msg.splitlines()[0]}")
    if len(drift) > 10:
        print(f"  • … and {len(drift) - 10} more")

    fixed = align_results(results, test_cases)
    RESULTS_FILE.write_text(json.dumps(fixed, indent=2))
    print(f"\n✓ Wrote aligned rows → {RESULTS_FILE}")


if __name__ == "__main__":
    main()
