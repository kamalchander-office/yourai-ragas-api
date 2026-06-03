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

QA_DIR = Path(__file__).parent
RESULTS_FILE = QA_DIR / "results.json"
TEST_CASES_FILE = QA_DIR / "test_cases.json"


def main() -> None:
    if not RESULTS_FILE.exists():
        sys.exit(f"ERROR: {RESULTS_FILE} not found")
    if not TEST_CASES_FILE.exists():
        sys.exit(f"ERROR: {TEST_CASES_FILE} not found")

    test_cases = json.loads(TEST_CASES_FILE.read_text())
    results = json.loads(RESULTS_FILE.read_text())
    errors = find_alignment_errors(results, test_cases)

    if not errors:
        print("✓ results.json already matches test_cases.json for all ids and questions.")
        return

    print(f"Fixing {len(errors)} drift issue(s):")
    for msg in errors[:10]:
        print(f"  • {msg.splitlines()[0]}")
    if len(errors) > 10:
        print(f"  • … and {len(errors) - 10} more")

    try:
        fixed = align_results(results, test_cases)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")

    RESULTS_FILE.write_text(json.dumps(fixed, indent=2))
    print(f"\n✓ Wrote aligned rows → {RESULTS_FILE}")
    print("Next: python3 qa/run_eval.py")


if __name__ == "__main__":
    main()
