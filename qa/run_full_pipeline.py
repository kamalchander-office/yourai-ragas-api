#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  run_full_pipeline.py — Run the FULL YourAI QA flow from ONE place          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  HOW TO USE                                                                  ║
║  ──────────                                                                  ║
║  1. Edit the CONFIG section below (limits, which steps to run, file paths).  ║
║  2. From project root:                                                       ║
║       python3 qa/run_full_pipeline.py                                        ║
║  3. Or override limit without editing the file:                              ║
║       python3 qa/run_full_pipeline.py --limit 5                              ║
║  4. Preview commands only (no execution):                                    ║
║       python3 qa/run_full_pipeline.py --dry-run                              ║
║                                                                              ║
║  PREREQUISITES (.env in project root)                                        ║
║  ───────────────────────────────────                                         ║
║  PWA QA (app-qa.yourai.com) — set in .env:                                   ║
║    API_BACKEND=pwa                                                           ║
║    YOURAI_PWA_BASE_URL, YOURAI_PWA_LOGIN_EMAIL/PASSWORD, YOURAI_PWA_OTP_BYPASS║
║                                                                              ║
║  PIPELINE STEPS (in order)                                                   ║
║  ─────────────────────────                                                   ║
║  Step 1  Test PWA login          → pwa_login.py                              ║
║  Step 2  Bootstrap session       → bootstrap_session.py (upload or vault pick) ║
║  Step 3  Import Excel/Word cases → ingest_cases.py                           ║
║  Step 4  Generate / fill GT      → generate_cases.py (doc → intent filter)  ║
║  Step 5  Collect API answers     → client.py                                 ║
║  Step 6  RAGAs + DeepEval eval   → run_eval.py                               ║
║  Step 7  Intent prompt compliance→ run_intent_eval.py                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qa.paths import (
    QA_DIR,
    RESULTS_DIR,
    ROOT,
    SESSION_FILE,
    TEST_CASES_FILE,
    ensure_results_dir,
    migrate_legacy_outputs,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — edit these values for your run (CLI --limit overrides LIMIT below)
#
# QUICK PRESETS (copy one block into the flags above):
#
# ► Smoke test (5 cases, no bootstrap):
#     LIMIT = 5
#     RUN_STEP_2_BOOTSTRAP = False
#     RUN_STEP_3_INGEST = False
#     RUN_STEP_4_GENERATE = False
#
# ► First-time PWA setup (bootstrap + Excel ingest + full run):
#     LIMIT = None
#     RUN_STEP_2_BOOTSTRAP = True
#     RUN_STEP_3_INGEST = True
#     RUN_STEP_4_GENERATE = True
#     GENERATE_FILL_GROUND_TRUTH_ONLY = True
#
# ► Re-score only (already have results.json):
#     RUN_STEP_1_LOGIN_TEST = False
#     RUN_STEP_5_COLLECT = False
#     RUN_STEP_6_RAGAS_EVAL = True
#     RUN_STEP_7_INTENT_EVAL = True
#
# ► Collect + evaluate all cases (typical daily run):
#     LIMIT = None
#     RUN_STEP_2_BOOTSTRAP = False
#     RUN_STEP_3_INGEST = False
#     RUN_STEP_5_COLLECT = True
#     RUN_STEP_6_RAGAS_EVAL = True
#     RUN_STEP_7_INTENT_EVAL = True
#
# ► Vault pick — attach existing YourVault doc(s) + optional folder (no upload):
#     BOOTSTRAP_MODE = "vault"
#     VAULT_DOCUMENT_IDS = "acf2061e-...,ebdc511f-..."
#     VAULT_FOLDER_NAME = "Discovery Documents"
#     # Or use names / media URLs:
#     # VAULT_DOCUMENT_NAMES = "CaseFile"
#     # VAULT_FILE_URLS = "https://media-qa.yourai.com/documents/{uuid}/file.docx"
#     RUN_STEP_2_BOOTSTRAP = True
#     GENERATE_FROM_SESSION = True
#
# ► One document — full E2E (recommended, upload mode):
#     GENERATE_FROM_SESSION = True
#     GENERATE_COUNT = 2
#     Step 4 analyses the document and generates cases ONLY for compatible intents.
#     FIND_DOCUMENT is always skipped (manual QA). Incompatible Excel rows go to
#     qa/results/test_cases_ineligible.json.
# ═══════════════════════════════════════════════════════════════════════════════

# How many test cases to run for collect + both evaluators (Steps 5–7).
#   None  → all cases in test_cases.json after Step 4
#   5     → first 5 only (good first E2E verification — Steps 1–4 still run fully)
LIMIT: int | None = 11

# API backend for collecting answers (Step 5).
#   "pwa"    → QA PWA with cookies + session.json (recommended)
#   "yourai" → dev M2M API
#   "mock"   → local main.py mock server
BACKEND = "pwa"

# ── Step 2: bootstrap mode ────────────────────────────────────────────────────
#   "upload" → upload local DOCUMENT to vault (legacy — unchanged behaviour)
#   "vault"  → pick existing YourVault doc(s) / folder (no local upload)
BOOTSTRAP_MODE = "upload"

# Vault pick (BOOTSTRAP_MODE = "vault") — comma-separated; all optional but need
# at least one document id/name/url OR a folder id/name.
VAULT_DOCUMENT_IDS = ""
VAULT_DOCUMENT_NAMES = ""
VAULT_FILE_URLS = ""
VAULT_FOLDER_ID = ""
VAULT_FOLDER_NAME = ""

# Upload mode only (BOOTSTRAP_MODE = "upload")
DOCUMENT = "documents/CaseFile.docx"

# Excel/Word source for human-written test cases (Step 3)
INGEST_FILE = "documents/TestCases.xlsx"  # relative to project root, or absolute path
INGEST_MERGE = False  # True = add to existing test_cases.json; False = replace

# ── Which steps to run (True = run, False = skip) ─────────────────────────────
RUN_STEP_1_LOGIN_TEST = True
RUN_STEP_2_BOOTSTRAP = True      # True on first run or when doc/intents change
RUN_STEP_3_INGEST = True         # True when loading from Excel/Word
RUN_STEP_4_GENERATE = True       # True to AI-generate cases or fill ground_truth
RUN_STEP_5_COLLECT = True
RUN_STEP_6_RAGAS_EVAL = True
RUN_STEP_7_INTENT_EVAL = True

# ── Step 2: bootstrap_session.py options ─────────────────────────────────────
BOOTSTRAP_REUSE_CHAT = False      # True = reuse conversation; False = fresh chat
BOOTSTRAP_DEFAULT_INTENT = "GENERAL_CHAT"

# All pipeline outputs land in qa/results/ (see qa/paths.py)
# Override with QA_RESULTS_DIR in .env if needed.

# ── Step 4: generate_cases.py options (only if RUN_STEP_4_GENERATE = True) ───
# Mode A — generate from PWA session (needs session.json from Step 2):
# Analyses DOCUMENT, filters intents (FIND_DOCUMENT always skipped), then generates.
GENERATE_FROM_SESSION = True
GENERATE_COUNT = 2                # questions per eligible intent per type (~5 intents for CaseFile.docx)
GENERATE_TYPES = "positive"       # space-separated: positive negative edge adversarial
GENERATE_ALL_INTENTS = False      # True = disable doc→intent filter (--all-intents; not recommended)
GENERATE_SKIP_DOC_ANALYSIS = False  # True = heuristics only, no LLM doc classification

# Mode B — fill empty ground_truth on existing test_cases.json (ignored when FROM_SESSION=True):
GENERATE_FILL_GROUND_TRUTH_ONLY = False
GENERATE_REFILL_GROUND_TRUTH = False  # True = overwrite ALL ground_truth

# ── Step 5: client.py options ─────────────────────────────────────────────────
CLIENT_SKIP_VALIDATION = False    # True = skip rule/retrieval validators
# True  = new PWA chat per test case (recommended — avoids 504 timeouts)
# False = reuse the single conversation_id from qa/session.json for all cases
PWA_FRESH_CONVERSATION_PER_CASE = False

# ── Step 6: run_eval.py options ───────────────────────────────────────────────
RAGAS_REPORT_ONLY = False         # True = rebuild report.html from scores.csv only

# ═══════════════════════════════════════════════════════════════════════════════
# End of CONFIG — usually no need to edit below this line
# ═══════════════════════════════════════════════════════════════════════════════

PYTHON = sys.executable


def _run_step(
    step_num: int,
    title: str,
    cmd: list[str],
    *,
    cwd: Path = QA_DIR,
    dry_run: bool,
) -> None:
    display = " ".join(cmd)
    print(f"\n{'=' * 70}")
    print(f"STEP {step_num}: {title}")
    print(f"  $ {display}")
    print("=" * 70)
    if dry_run:
        print("  (dry-run — skipped)\n")
        return
    result = subprocess.run(cmd, cwd=cwd, env=os.environ.copy())
    if result.returncode != 0:
        sys.exit(f"\nERROR: Step {step_num} failed (exit {result.returncode}). Stopping pipeline.")


def _limit_args(limit: int | None) -> list[str]:
    if limit is not None and limit > 0:
        return ["--limit", str(limit)]
    return []


def _preflight(limit: int | None, *, root: Path = ROOT) -> None:
    """Fail fast on missing files / config before any network or LLM steps."""
    import json

    errors: list[str] = []
    warnings: list[str] = []

    doc = root / DOCUMENT if not Path(DOCUMENT).is_absolute() else Path(DOCUMENT)
    ingest = root / INGEST_FILE if not Path(INGEST_FILE).is_absolute() else Path(INGEST_FILE)
    session_path = SESSION_FILE

    if RUN_STEP_2_BOOTSTRAP and BOOTSTRAP_MODE == "upload" and not doc.is_file():
        errors.append(f"Bootstrap document not found: {doc}")

    if RUN_STEP_2_BOOTSTRAP and BOOTSTRAP_MODE == "vault":
        has_doc = any(
            str(v).strip()
            for v in (
                VAULT_DOCUMENT_IDS,
                VAULT_DOCUMENT_NAMES,
                VAULT_FILE_URLS,
            )
        )
        has_folder = bool(str(VAULT_FOLDER_ID).strip() or str(VAULT_FOLDER_NAME).strip())
        if not has_doc and not has_folder:
            errors.append(
                "BOOTSTRAP_MODE=vault requires VAULT_DOCUMENT_IDS, VAULT_DOCUMENT_NAMES, "
                "VAULT_FILE_URLS, and/or VAULT_FOLDER_ID / VAULT_FOLDER_NAME in CONFIG."
            )

    if RUN_STEP_3_INGEST and not ingest.is_file():
        errors.append(f"Ingest file not found: {ingest}")

    if RUN_STEP_4_GENERATE and GENERATE_FROM_SESSION:
        if not RUN_STEP_2_BOOTSTRAP and not session_path.is_file():
            errors.append(
                "GENERATE_FROM_SESSION=True needs qa/session.json — "
                "enable RUN_STEP_2_BOOTSTRAP or run bootstrap_session.py first."
            )

    if RUN_STEP_5_COLLECT and BACKEND == "pwa":
        if not RUN_STEP_2_BOOTSTRAP and not session_path.is_file():
            errors.append(
                "PWA collect needs qa/session.json — enable RUN_STEP_2_BOOTSTRAP first."
            )

    intent_count = 0
    if session_path.is_file():
        try:
            session = json.loads(session_path.read_text())
            intent_count = len(session.get("intents") or [])
        except json.JSONDecodeError:
            warnings.append(f"{session_path.name} is invalid JSON — Step 2 will recreate it.")

    ingest_rows = 0
    if RUN_STEP_3_INGEST and ingest.is_file() and ingest.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import openpyxl

            wb = openpyxl.load_workbook(ingest, read_only=True)
            ws = wb.active
            ingest_rows = len(
                [
                    r
                    for r in ws.iter_rows(min_row=2, values_only=True)
                    if any(c is not None and str(c).strip() for c in r)
                ]
            )
        except Exception:
            warnings.append(f"Could not count rows in {ingest.name} — ingest may still work.")

    if RUN_STEP_4_GENERATE and GENERATE_FROM_SESSION and GENERATE_ALL_INTENTS:
        warnings.append(
            "GENERATE_ALL_INTENTS=True — doc→intent filter disabled (FIND_DOCUMENT still skipped)."
        )

    if RUN_STEP_4_GENERATE and GENERATE_FROM_SESSION and intent_count:
        type_count = len([t for t in GENERATE_TYPES.split() if t.strip()])
        eligible_intent_count = intent_count
        profile_types: list[str] = []
        if session_path.is_file():
            try:
                from qa.document_profile import analyze_document, heuristic_document_profile
                from qa.intent_compatibility import filter_intents_for_document
                from qa.local_documents import DocumentContext

                session_data = json.loads(session_path.read_text())
                profile = session_data.get("document_profile")
                if not profile and BOOTSTRAP_MODE == "upload" and doc.is_file():
                    # Estimate from local file before Step 4 runs
                    try:
                        from yourai_chat.document_text import extract_text_from_bytes

                        raw = doc.read_bytes()
                        text = extract_text_from_bytes(raw, doc.suffix)
                        stub = DocumentContext(
                            document_id="preflight",
                            filename=doc.name,
                            local_path=str(doc),
                            text=text[:12000],
                            text_truncated=len(text) > 12000,
                        )
                        profile = heuristic_document_profile(stub)
                    except Exception:
                        profile = None
                if profile:
                    profile_types = profile.get("document_types") or []
                    eligible, _skipped = filter_intents_for_document(
                        session_data.get("intents") or [],
                        profile,
                    )
                    eligible_intent_count = len(eligible)
            except Exception:
                pass

        ai_cases = eligible_intent_count * GENERATE_COUNT * max(type_count, 1)
        total_est = ingest_rows + ai_cases if RUN_STEP_3_INGEST else ai_cases
        type_hint = f" ({', '.join(profile_types[:4])})" if profile_types else ""
        warnings.append(
            f"After Step 4, expect ~{total_est} harness-eligible case(s) "
            f"({ingest_rows} from Excel + ~{ai_cases} AI across "
            f"{eligible_intent_count} compatible intents{type_hint}). "
            f"FIND_DOCUMENT skipped (manual QA)."
        )
        if limit is None:
            warnings.append(
                f"LIMIT=None will collect and score all ~{total_est} cases "
                "(many PWA + judge LLM calls — set LIMIT=5 for a cheaper first run)."
            )
        elif limit > 0:
            warnings.append(
                f"LIMIT={limit}: Steps 5–7 use the first {limit} case(s) only; "
                "Steps 1–4 still run fully."
            )

    if errors:
        print("\nPreflight FAILED:\n")
        for msg in errors:
            print(f"  ✗ {msg}")
        sys.exit(1)

    print("\nPreflight OK:")
    if RUN_STEP_2_BOOTSTRAP:
        if BOOTSTRAP_MODE == "vault":
            print(f"  bootstrap  : vault pick")
            if VAULT_DOCUMENT_IDS:
                print(f"  doc ids    : {VAULT_DOCUMENT_IDS}")
            if VAULT_DOCUMENT_NAMES:
                print(f"  doc names  : {VAULT_DOCUMENT_NAMES}")
            if VAULT_FILE_URLS:
                print(f"  file urls  : {VAULT_FILE_URLS[:80]}...")
            if VAULT_FOLDER_ID or VAULT_FOLDER_NAME:
                print(f"  folder     : {VAULT_FOLDER_ID or VAULT_FOLDER_NAME}")
        else:
            print(f"  document   : {doc}")
    if RUN_STEP_3_INGEST:
        print(f"  ingest     : {ingest} ({ingest_rows or '?'} row(s))")
    if intent_count:
        print(f"  intents    : {intent_count} in session.json (FIND_DOCUMENT excluded from harness)")
    for msg in warnings:
        print(f"  ⚠ {msg}")
    print()


def build_pipeline_commands(limit: int | None, *, root: Path = ROOT) -> list[tuple[int, str, list[str]]]:
    """Return ordered (step_num, title, command) tuples from CONFIG."""
    doc = root / DOCUMENT if not Path(DOCUMENT).is_absolute() else Path(DOCUMENT)
    ingest = root / INGEST_FILE if not Path(INGEST_FILE).is_absolute() else Path(INGEST_FILE)
    steps: list[tuple[int, str, list[str]]] = []
    n = 0

    if RUN_STEP_1_LOGIN_TEST:
        n += 1
        steps.append((n, "Test PWA API login (pwa_login.py)", [PYTHON, "pwa_login.py"]))

    if RUN_STEP_2_BOOTSTRAP:
        n += 1
        if BOOTSTRAP_MODE == "vault":
            cmd = [
                PYTHON,
                "bootstrap_session.py",
                "--mode",
                "vault",
                "--default-intent",
                BOOTSTRAP_DEFAULT_INTENT,
            ]
            if VAULT_DOCUMENT_IDS.strip():
                cmd.extend(["--vault-document-ids", VAULT_DOCUMENT_IDS.strip()])
            if VAULT_DOCUMENT_NAMES.strip():
                cmd.extend(["--vault-document-names", VAULT_DOCUMENT_NAMES.strip()])
            if VAULT_FILE_URLS.strip():
                cmd.extend(["--vault-file-urls", VAULT_FILE_URLS.strip()])
            if VAULT_FOLDER_ID.strip():
                cmd.extend(["--vault-folder-id", VAULT_FOLDER_ID.strip()])
            if VAULT_FOLDER_NAME.strip():
                cmd.extend(["--vault-folder-name", VAULT_FOLDER_NAME.strip()])
            title = "Bootstrap PWA session — vault pick, download corpus (bootstrap_session.py)"
        else:
            cmd = [
                PYTHON,
                "bootstrap_session.py",
                "--mode",
                "upload",
                "--document",
                str(doc),
                "--default-intent",
                BOOTSTRAP_DEFAULT_INTENT,
            ]
            title = "Bootstrap PWA session — upload doc, fetch intents (bootstrap_session.py)"
        if BOOTSTRAP_REUSE_CHAT:
            cmd.append("--reuse-chat")
        steps.append((n, title, cmd))

    if RUN_STEP_3_INGEST:
        n += 1
        cmd = [PYTHON, "ingest_cases.py", "--file", str(ingest)]
        if INGEST_MERGE:
            cmd.append("--merge")
        steps.append((n, "Import test cases from Excel/Word (ingest_cases.py)", cmd))

    if RUN_STEP_4_GENERATE:
        n += 1
        cmd = [PYTHON, "generate_cases.py"]
        if GENERATE_FROM_SESSION:
            cmd.append("--from-session")
            cmd.extend(["--types", *GENERATE_TYPES.split()])
            cmd.extend(["--count", str(GENERATE_COUNT)])
            if GENERATE_REFILL_GROUND_TRUTH:
                cmd.append("--refill-ground-truth")
            if GENERATE_ALL_INTENTS:
                cmd.append("--all-intents")
            if GENERATE_SKIP_DOC_ANALYSIS:
                cmd.append("--skip-doc-analysis")
        elif GENERATE_FILL_GROUND_TRUTH_ONLY:
            cmd.append("--fill-ground-truth-only")
            if GENERATE_REFILL_GROUND_TRUTH:
                cmd.append("--refill-ground-truth")
        else:
            cmd.extend(["--types", *GENERATE_TYPES.split()])
            cmd.extend(["--count", str(GENERATE_COUNT)])
        steps.append((n, "Generate cases — doc profile + intent filter (generate_cases.py)", cmd))

    if RUN_STEP_5_COLLECT:
        n += 1
        cmd = [PYTHON, "client.py", "--backend", BACKEND, *_limit_args(limit)]
        if CLIENT_SKIP_VALIDATION:
            cmd.append("--skip-validation")
        if BACKEND == "pwa":
            if PWA_FRESH_CONVERSATION_PER_CASE:
                cmd.append("--fresh-conversation-per-case")
            else:
                cmd.append("--reuse-session-conversation")
        steps.append((n, f"Collect YourAI answers (client.py --backend {BACKEND})", cmd))

    if RUN_STEP_6_RAGAS_EVAL:
        n += 1
        cmd = [PYTHON, "run_eval.py", *_limit_args(limit)]
        if RAGAS_REPORT_ONLY:
            cmd.append("--report-only")
        steps.append((n, "RAGAs + DeepEval scoring + report.html (run_eval.py)", cmd))

    if RUN_STEP_7_INTENT_EVAL:
        n += 1
        cmd = [PYTHON, "run_intent_eval.py", *_limit_args(limit)]
        steps.append((n, "Intent prompt compliance (run_intent_eval.py)", cmd))

    return steps


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full YourAI QA pipeline from one script.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Individual commands (for manual runs):
  python3 qa/pwa_login.py
  python3 qa/bootstrap_session.py --document documents/CaseFile.docx
  python3 qa/ingest_cases.py --file TestCases.xlsx
  python3 qa/ingest_cases.py --file TestCases.xlsx --merge
  python3 qa/generate_cases.py --fill-ground-truth-only
  python3 qa/generate_cases.py --from-session --types positive --count 3
  python3 qa/generate_cases.py --from-session --skip-doc-analysis
  python3 qa/client.py --backend pwa
  python3 qa/client.py --backend pwa --limit 5
  python3 qa/run_eval.py
  python3 qa/run_eval.py --limit 5
  python3 qa/run_eval.py --report-only
  python3 qa/run_intent_eval.py
  python3 qa/run_intent_eval.py --limit 5
        """.strip(),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Override CONFIG LIMIT — first N cases for collect + eval steps",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print each step command without executing",
    )
    args = parser.parse_args()

    limit = args.limit if args.limit is not None else LIMIT

    print("YourAI QA — full pipeline")
    print(f"  Project root : {ROOT}")
    print(f"  Backend      : {BACKEND}")
    print(f"  Case limit   : {limit if limit else 'ALL'}")
    if RUN_STEP_5_COLLECT and BACKEND == "pwa":
        print(
            f"  PWA chats    : "
            f"{'fresh per test case' if PWA_FRESH_CONVERSATION_PER_CASE else 'reuse session conversation'}"
        )
    if args.dry_run:
        print("  Mode         : DRY RUN (commands only)")

    steps = build_pipeline_commands(limit)
    if not steps:
        sys.exit("ERROR: All steps are disabled in CONFIG. Enable at least one RUN_STEP_* flag.")

    if not args.dry_run:
        migrated = migrate_legacy_outputs()
        if migrated:
            print(f"Migrated legacy outputs → qa/results/: {', '.join(migrated)}")
        ensure_results_dir()
        _preflight(limit)

    for step_num, title, cmd in steps:
        _run_step(step_num, title, cmd, dry_run=args.dry_run)

    if args.dry_run:
        print("\nDry run complete. Re-run without --dry-run to execute.")
        return

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print("Outputs:")
    print(f"  qa/session.json                   — conversation, vault attach, intents")
    print(f"  qa/test_cases.json                — harness-eligible cases")
    print(f"  {RESULTS_DIR.relative_to(ROOT)}/")
    print(f"    results.json                    — API answers")
    print(f"    scores.csv                      — RAGAs + DeepEval scores")
    print(f"    report.html                     — RAGAs + DeepEval report")
    print(f"    intent_eval_issues.csv          — intent bugs (1 row per question)")
    print(f"    intent_eval_summary.json        — intent compliance detail")
    print(f"    test_cases_ineligible.json      — skipped intent/doc rows")
    print(f"    corpus_cache/                   — vault document text cache")
    print("=" * 70)


if __name__ == "__main__":
    main()
