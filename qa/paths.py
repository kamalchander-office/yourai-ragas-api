"""
Central paths for the QA pipeline.

Working inputs (editable between runs):
  qa/session.json
  qa/test_cases.json

All run outputs:
  qa/results/
    results.json
    scores.csv
    report.html
    intent_eval_issues.csv
    intent_eval_summary.json
    test_cases_ineligible.json
    corpus_cache/          — vault fileUrl text cache

Override output root: QA_RESULTS_DIR=/path/to/dir
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
ROOT = QA_DIR.parent

# ── Working inputs (stay in qa/) ─────────────────────────────────────────────
SESSION_FILE = QA_DIR / "session.json"
TEST_CASES_FILE = QA_DIR / "test_cases.json"

# ── Output directory ─────────────────────────────────────────────────────────
_raw_results = os.getenv("QA_RESULTS_DIR", "").strip()
if _raw_results:
    RESULTS_DIR = Path(_raw_results).expanduser()
    if not RESULTS_DIR.is_absolute():
        RESULTS_DIR = (ROOT / RESULTS_DIR).resolve()
else:
    RESULTS_DIR = (QA_DIR / "results").resolve()

RESULTS_FILE = RESULTS_DIR / "results.json"
SCORES_CSV = RESULTS_DIR / "scores.csv"
REPORT_HTML = RESULTS_DIR / "report.html"
INTENT_EVAL_ISSUES_CSV = RESULTS_DIR / "intent_eval_issues.csv"
INTENT_EVAL_SUMMARY_JSON = RESULTS_DIR / "intent_eval_summary.json"
INELIGIBLE_CASES_FILE = RESULTS_DIR / "test_cases_ineligible.json"
CORPUS_CACHE_DIR = RESULTS_DIR / "corpus_cache"

_LEGACY_OUTPUT_FILES = (
    ("results.json", RESULTS_FILE),
    ("scores.csv", SCORES_CSV),
    ("report.html", REPORT_HTML),
    ("intent_eval_issues.csv", INTENT_EVAL_ISSUES_CSV),
    ("intent_eval_summary.json", INTENT_EVAL_SUMMARY_JSON),
    ("test_cases_ineligible.json", INELIGIBLE_CASES_FILE),
)


def ensure_results_dir() -> Path:
    """Create qa/results/ (and corpus_cache/) if missing."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def migrate_legacy_outputs() -> list[str]:
    """
    Move outputs from qa/*.json|csv|html into qa/results/ when still at old paths.
    Returns list of migrated relative paths (for logging).
    """
    moved: list[str] = []
    ensure_results_dir()
    for name, dest in _LEGACY_OUTPUT_FILES:
        legacy = QA_DIR / name
        if legacy.is_file() and not dest.exists():
            shutil.move(str(legacy), str(dest))
            moved.append(name)
    legacy_cache = QA_DIR / "corpus_cache"
    if legacy_cache.is_dir() and any(legacy_cache.iterdir()):
        for item in legacy_cache.iterdir():
            target = CORPUS_CACHE_DIR / item.name
            if not target.exists():
                shutil.move(str(item), str(target))
        try:
            legacy_cache.rmdir()
        except OSError:
            pass
        moved.append("corpus_cache/")
    return moved
