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
args = parser.parse_args()


def _run_validators(test_cases: list[dict], results: list[dict]) -> None:
    rule = RuleValidator()
    retrieval = RetrievalValidator()
    rule_failures = 0
    for tc, row in zip(test_cases, results):
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
