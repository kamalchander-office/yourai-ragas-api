"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  client.py — API Runner + Response Collector (orchestrator entrypoint)        ║
║                                                                              ║
║  Backends:                                                                   ║
║    mock   → local main.py  POST /v1/query  (Bearer token)                   ║
║    yourai → YourAI product POST /api/v1/chat/respond (client headers)       ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python client.py                                    # mock (default)    ║
║    python client.py --backend yourai                   # real YourAI API   ║
║    python client.py --api-url http://127.0.0.1:8001    # mock base URL     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from qa.align import align_results, find_alignment_errors
from qa.collectors.mock_collector import collect_with_mock_api
from qa.collectors.yourai_collector import collect_with_yourai_api
from validators.rule_validator import RuleValidator
from validators.retrieval_validator import RetrievalValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("qa.client")

QA_DIR = Path(__file__).parent
TEST_CASES_FILE = QA_DIR / "test_cases.json"
RESULTS_FILE = QA_DIR / "results.json"

parser = argparse.ArgumentParser(description="Collect YourAI answers for evaluation.")
parser.add_argument(
    "--backend",
    choices=["mock", "yourai"],
    default=os.getenv("API_BACKEND", "mock"),
    help="API backend: mock (local main.py) or yourai (product chat API)",
)
parser.add_argument(
    "--api-url",
    default=os.getenv("MOCK_API_URL", "http://127.0.0.1:8001"),
    help="Base URL for mock backend (default: http://127.0.0.1:8001)",
)
parser.add_argument(
    "--skip-validation",
    action="store_true",
    help="Skip rule/retrieval validator pass (collect only)",
)
parser.add_argument(
    "--align-only",
    action="store_true",
    help="Fix results.json metadata from test_cases.json without calling the API",
)
args = parser.parse_args()


def _run_validators(test_cases: list[dict], results: list[dict]) -> None:
    rule = RuleValidator()
    retrieval = RetrievalValidator()
    rule_failures = 0
    results_by_id = {r["id"]: r for r in results if r.get("id")}
    for tc in test_cases:
        row = results_by_id.get(tc.get("id"))
        if not row:
            continue
        if row.get("answer", "").startswith("ERROR:"):
            continue
        rr = rule.validate(tc, row)
        tr = retrieval.validate(tc, row)
        row["rule_validation_passed"] = rr.passed
        row["rule_validation_failures"] = rr.failures
        row["retrieval_validation_passed"] = tr.passed
        if not rr.passed:
            rule_failures += 1
            log.warning("Rule validation failed %s: %s", tc["id"], rr.failures)
    if rule_failures:
        print(f"\n  ⚠ Rule validation failures: {rule_failures} case(s)")


def main() -> None:
    test_cases = json.loads(TEST_CASES_FILE.read_text())
    print(f"Loaded {len(test_cases)} test cases from {TEST_CASES_FILE.name}")

    if args.align_only:
        if not RESULTS_FILE.exists():
            sys.exit(f"ERROR: {RESULTS_FILE} not found — run client.py first.")
        results = json.loads(RESULTS_FILE.read_text())
        drift = find_alignment_errors(results, test_cases)
        if drift:
            print(f"Aligning {len(drift)} issue(s) from test_cases.json …")
        results = align_results(results, test_cases)
        RESULTS_FILE.write_text(json.dumps(results, indent=2))
        print(f"✓ Aligned results saved → {RESULTS_FILE}")
        return

    print(f"Backend: {args.backend}\n")

    if args.backend == "yourai":
        results = collect_with_yourai_api(test_cases)
    else:
        bearer = os.environ.get("API_BEARER_TOKEN", "")
        if not bearer:
            sys.exit(
                "ERROR: API_BEARER_TOKEN not found in .env (required for mock backend).\n"
                "Or use: python client.py --backend yourai"
            )
        print(f"Sending to mock API: {args.api_url.rstrip('/')}\n")
        results = collect_with_mock_api(
            test_cases,
            api_url=args.api_url,
            bearer_token=bearer,
        )

    drift = find_alignment_errors(results, test_cases)
    if drift:
        print("\n⚠ Fixing stale question/ground_truth fields from test_cases.json:")
        for msg in drift[:5]:
            print(f"  • {msg.splitlines()[0]}")
        if len(drift) > 5:
            print(f"  • … and {len(drift) - 5} more")
    results = align_results(results, test_cases)

    if not args.skip_validation:
        _run_validators(test_cases, results)

    RESULTS_FILE.write_text(json.dumps(results, indent=2))

    errors = sum(1 for r in results if str(r.get("answer", "")).startswith("ERROR:"))
    success = len(results) - errors
    print(f"\n✓ Done — {success}/{len(results)} answers collected successfully.")
    if errors:
        print(f"  ⚠ {errors} errors — check the output above.")
    print(f"✓ Results saved → {RESULTS_FILE}")
    print("\nNext step: run  python run_eval.py  to score with RAGAs.")


if __name__ == "__main__":
    main()
