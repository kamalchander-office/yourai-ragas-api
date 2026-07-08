"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  client.py — API Runner + Response Collector (orchestrator entrypoint)        ║
║                                                                              ║
║  Backends:                                                                   ║
║    mock   → local main.py  POST /v1/query  (Bearer token)                   ║
║    yourai → dev API POST /api/v1/chat/respond (client headers)              ║
║    pwa    → QA PWA POST /api/v1/chat (cookies + qa/session.json)          ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python client.py --backend pwa                      # QA PWA (recommended)║
║    python client.py --backend yourai                   # dev M2M API         ║
║    python client.py --api-url http://127.0.0.1:8001    # mock base URL       ║
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
from qa.collectors.pwa_collector import collect_with_pwa_api
from qa.collectors.yourai_collector import collect_with_yourai_api
from qa.session_store import bind_intents_to_cases
from validators.rule_validator import RuleValidator
from validators.retrieval_validator import RetrievalValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("qa.client")

from qa.paths import (
    INELIGIBLE_CASES_FILE,
    RESULTS_FILE,
    TEST_CASES_FILE,
    ensure_results_dir,
    migrate_legacy_outputs,
)

parser = argparse.ArgumentParser(description="Collect YourAI answers for evaluation.")
parser.add_argument(
    "--backend",
    choices=["mock", "yourai", "pwa"],
    default=os.getenv("API_BACKEND", "pwa"),
    help="API backend: pwa (QA cookies+session), yourai (dev M2M), or mock",
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
parser.add_argument(
    "--limit",
    type=int,
    default=None,
    metavar="N",
    help="Collect answers for only the first N test cases (saves API quota)",
)
pwa_chat = parser.add_mutually_exclusive_group()
pwa_chat.add_argument(
    "--fresh-conversation-per-case",
    action="store_true",
    default=None,
    help="PWA: start a new chat for each test case (run_full_pipeline default)",
)
pwa_chat.add_argument(
    "--reuse-session-conversation",
    action="store_true",
    default=None,
    help="PWA: reuse conversation_id from qa/session.json for all cases",
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


def _filter_harness_eligible(cases: list[dict]) -> list[dict]:
    """Keep cases marked harness_eligible; if field absent, keep (backward compatible)."""
    if not any("harness_eligible" in c for c in cases):
        return cases
    eligible = [c for c in cases if c.get("harness_eligible", True)]
    skipped = len(cases) - len(eligible)
    if skipped:
        print(
            f"Skipping {skipped} case(s) not compatible with session document "
            "(see test_cases_ineligible.json or harness_skip_reason on case)."
        )
    return eligible


def main() -> None:
    migrated = migrate_legacy_outputs()
    if migrated:
        print(f"Migrated legacy outputs → qa/results/: {', '.join(migrated)}")
    ensure_results_dir()

    test_cases = json.loads(TEST_CASES_FILE.read_text())
    test_cases = _filter_harness_eligible(test_cases)
    if args.limit is not None and args.limit > 0:
        test_cases = test_cases[: args.limit]
        print(f"Limiting collection to first {len(test_cases)} test case(s) (--limit {args.limit}).")
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

    if args.backend in ("pwa", "yourai"):
        bound, misses = bind_intents_to_cases(test_cases, default_if_missing=True)
        if bound:
            print(f"Intents bound from session.json: {bound}/{len(test_cases)} case(s)")
            TEST_CASES_FILE.write_text(json.dumps(test_cases, indent=2))
        if misses:
            sys.exit(
                f"ERROR: Could not map platform intent for: {', '.join(misses[:8])}\n"
                "Add intent_key column in Excel (e.g. LEGAL_QA) or run bootstrap_session.py first."
            )

    if args.backend == "pwa":
        if args.reuse_session_conversation:
            fresh_per_case = False
        elif args.fresh_conversation_per_case:
            fresh_per_case = True
        else:
            fresh_per_case = None  # env default in pwa_collector
        results = collect_with_pwa_api(
            test_cases,
            fresh_conversation_per_case=fresh_per_case,
        )
    elif args.backend == "yourai":
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
