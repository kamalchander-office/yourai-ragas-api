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

QA_DIR = Path(__file__).parent


def main() -> None:
    tc_path = QA_DIR / "test_cases.json"
    res_path = QA_DIR / "results.json"
    if not tc_path.exists() or not res_path.exists():
        sys.exit("ERROR: need both qa/test_cases.json and qa/results.json")

    test_cases = json.loads(tc_path.read_text())
    results = json.loads(res_path.read_text())
    errors = find_alignment_errors(results, test_cases)

    if not errors:
        print(f"✓ All {len(test_cases)} ids match between test_cases.json and results.json")
        return

    print(f"✗ Found {len(errors)} alignment issue(s):\n")
    for msg in errors:
        print(msg)
        print()
    print("Fix:  python3 qa/align_results.py")
    print("      or python3 qa/client.py --align-only")
    sys.exit(1)


if __name__ == "__main__":
    main()
