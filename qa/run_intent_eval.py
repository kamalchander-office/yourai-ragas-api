"""
Intent prompt compliance evaluation (separate from RAGAs).

Reads results.json + test_cases.json + session.json intents. Runs THREE strict
isolated LLM checks per answer: system prompt, tone prompt, custom instruction.

Outputs:
  intent_eval_issues.csv   — one row per question; all bugs in the `bugs` column
  intent_eval_summary.json — detailed per-case results + unique violation patterns

Usage:
  python qa/run_intent_eval.py
  python qa/run_intent_eval.py --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

QA_DIR = Path(__file__).parent
ROOT = QA_DIR.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from llm import config as llm_config
from llm.env_validate import is_gemini_placeholder, is_openai_placeholder, is_openrouter_placeholder

from qa.align import load_test_cases_by_id
from qa.intent_compliance import (
    check_status_label,
    evaluate_response_compliance,
    normalize_issue,
)
from qa.intent_eval_format import CSV_COLUMNS, case_to_csv_row
from qa.intent_eval_summary import build_summary
from qa.intent_prompts import extract_intent_prompts, has_any_prompt
from qa.session_store import find_platform_intent, load_session

RESULTS_FILE = QA_DIR / "results.json"
ISSUES_CSV = QA_DIR / "intent_eval_issues.csv"
SUMMARY_JSON = QA_DIR / "intent_eval_summary.json"


def _validate_judge_keys() -> None:
    provider = llm_config.JUDGE_PROVIDER
    if provider == "gemini":
        if is_gemini_placeholder(llm_config.GEMINI_API_KEY):
            sys.exit("ERROR: GEMINI_API_KEY missing for intent compliance judge.")
    elif provider == "openrouter":
        if is_openrouter_placeholder(llm_config.OPENROUTER_API_KEY):
            sys.exit("ERROR: OPENROUTER_API_KEY missing for intent compliance judge.")
    elif is_openai_placeholder(llm_config.OPENAI_API_KEY):
        sys.exit("ERROR: OPENAI_API_KEY missing for intent compliance judge.")


def _answer_from_row(row: dict) -> str:
    ans = (row.get("answer") or row.get("actual_answer") or "").strip()
    if (not ans or ans.startswith("ERROR:")) and isinstance(row.get("raw_response"), dict):
        ans = (row["raw_response"].get("answer") or "").strip()
    return ans


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate intent prompt compliance.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate first N results only")
    args = parser.parse_args()

    _validate_judge_keys()

    if not RESULTS_FILE.exists():
        sys.exit(f"ERROR: {RESULTS_FILE} not found. Run client.py first.")

    try:
        session = load_session()
    except FileNotFoundError as e:
        sys.exit(f"ERROR: {e}")

    results = json.loads(RESULTS_FILE.read_text())
    test_cases = load_test_cases_by_id()

    if args.limit and args.limit > 0:
        results = results[: args.limit]

    case_results: list[dict] = []
    compliant_count = 0

    print(f"Intent compliance eval — judge: {llm_config.JUDGE_PROVIDER}")
    print("Strict checks: system_prompt + tone_prompt + custom_instruction (isolated)")
    print(f"Cases: {len(results)}\n")

    for row in results:
        case_id = row.get("id") or ""
        test_case = test_cases.get(case_id)
        if not test_case:
            continue

        question = (test_case.get("question") or row.get("question") or "").strip()
        response = _answer_from_row(row)

        intent = find_platform_intent(session, test_case)
        if not intent:
            prompts = extract_intent_prompts(None)
            issue = normalize_issue(
                {
                    "prompt_source": "unknown",
                    "severity": "high",
                    "location": "intent binding",
                    "violation": "Intent not mapped to session.json",
                    "response_excerpt": "",
                    "prompt_rule": "Each test case must resolve to a platform intent UUID",
                    "why": "Test case intent could not be matched against session.json intents",
                    "fix": "Re-run bootstrap_session.py and client.py with intent binding",
                },
                case_id=case_id,
            )
            case_results.append(
                {
                    "id": case_id,
                    "intent_key": "",
                    "intent_label": "",
                    "question": question,
                    "response": response,
                    "compliant": False,
                    "issues": [issue],
                    "prompts": prompts,
                }
            )
            print(f"  ✗ {case_id} — intent not mapped")
            continue

        prompts = extract_intent_prompts(intent)
        if not has_any_prompt(prompts):
            issue = normalize_issue(
                {
                    "prompt_source": "unknown",
                    "severity": "high",
                    "location": "intent configuration",
                    "violation": f"Intent {prompts.get('intent_key')} has no prompts in session",
                    "prompt_rule": "Intent must expose systemPrompt, tonePrompt, or customInstruction",
                    "why": "Cannot audit compliance when all prompt fields are empty",
                    "fix": "Refresh intents via bootstrap_session.py",
                },
                case_id=case_id,
            )
            case_results.append(
                {
                    "id": case_id,
                    "intent_key": prompts.get("intent_key", ""),
                    "intent_label": prompts.get("intent_label", ""),
                    "question": question,
                    "response": response,
                    "compliant": False,
                    "issues": [issue],
                    "prompts": prompts,
                }
            )
            print(f"  ✗ {case_id} — no prompts on intent")
            continue

        result = evaluate_response_compliance(
            question=question,
            response=response,
            prompts=prompts,
            case_id=case_id,
        )

        checks = result.get("checks") or {}
        case_results.append(
            {
                "id": case_id,
                "intent_key": prompts.get("intent_key", ""),
                "intent_label": prompts.get("intent_label", ""),
                "question": question,
                "response": response,
                "compliant": result["compliant"],
                "checks": checks,
                "issues": result["issues"],
                "prompts": prompts,
            }
        )

        status = (
            f"system:{check_status_label(checks.get('system_prompt', {}))} "
            f"tone:{check_status_label(checks.get('tone_prompt', {}))} "
            f"custom:{check_status_label(checks.get('custom_instruction', {}))}"
        )

        if result["compliant"]:
            compliant_count += 1
            print(f"  ✓ {case_id} [{prompts.get('intent_key')}] {status}")
        else:
            print(
                f"  ✗ {case_id} [{prompts.get('intent_key')}] {status} — "
                f"{len(result['issues'])} issue(s)"
            )

    csv_rows = [case_to_csv_row(case) for case in case_results]

    with ISSUES_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)

    summary = build_summary(
        case_results=case_results,
        judge_provider=llm_config.JUDGE_PROVIDER,
        issues_csv_name=ISSUES_CSV.name,
    )
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    stats = summary["statistics"]
    print("\n" + "=" * 60)
    print(f"Compliant (all checks): {stats['compliant']} / {stats['total_evaluated']}")
    print(f"System prompt failures: {stats.get('system_prompt_failures', 0)}")
    print(f"Tone prompt failures:   {stats.get('tone_prompt_failures', 0)}")
    print(f"Custom instr. failures: {stats.get('custom_instruction_failures', 0)}")
    print(f"Total issues:           {stats['total_issues']}")
    print(f"Unique violation types: {stats['unique_violation_patterns']}")
    print(f"CSV rows (1 per question): {len(csv_rows)}")
    print(f"Issues CSV:             {ISSUES_CSV.name}")
    print(f"Detailed summary:       {SUMMARY_JSON.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
