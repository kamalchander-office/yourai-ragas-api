"""
Check that every id in results.json has the same question as test_cases.json.

  python3 qa/verify_alignment.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qa.align import find_alignment_errors
from qa.paths import RESULTS_FILE, TEST_CASES_FILE, migrate_legacy_outputs


def main() -> None:
    migrate_legacy_outputs()

    if not TEST_CASES_FILE.exists() or not RESULTS_FILE.exists():
        sys.exit(f"ERROR: need both {TEST_CASES_FILE} and {RESULTS_FILE}")

    test_cases = json.loads(TEST_CASES_FILE.read_text())
    results = json.loads(RESULTS_FILE.read_text())
    errors = find_alignment_errors(results, test_cases)

    if not errors:
        print(f"✓ All {len(test_cases)} ids match between test_cases.json and results.json")
        return

    print(f"✗ Found {len(errors)} alignment issue(s):\n")
    for msg in errors:
        print(f"  • {msg.splitlines()[0]}")
    print("\nFix:  python3 qa/align_results.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
