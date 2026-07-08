"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  run_eval.py — Score every answer with RAGAs + DeepEval and produce report  ║
║                                                                              ║
║  WHAT THIS FILE DOES:                                                        ║
║  This is the SCORER. It reads results.json (produced by client.py),         ║
║  sends every question+answer pair to RAGAs + DeepEval, and produces:      ║
║                                                                              ║
║  OUTPUT FILES:                                                               ║
║    scores.csv    → raw numbers, open in Excel or Google Sheets              ║
║    report.html   → full formatted report, open in any browser               ║
║                                                                              ║
║  WHAT IS RAGAs DOING UNDER THE HOOD?                                        ║
║  RAGAs uses OpenAI as a "judge" LLM. For each test case it:                 ║
║    1. Reads the question, the AI's answer, and the ground truth             ║
║    2. Asks GPT: "How relevant is this answer to the question?" (0-1)        ║
║    3. Asks GPT: "How correct is this answer vs the ground truth?" (0-1)     ║
║    4. Calculates semantic similarity between answer and ground truth (0-1)  ║
║  This is called "LLM-as-judge" — using one AI to evaluate another.         ║
║                                                                              ║
║  RAGAs METRICS (six — scoped to legal RAG chat QA)                          ║
║  TIER 1 (always): answer_relevancy, answer_correctness, answer_similarity   ║
║  TIER 2 (when contexts): faithfulness, context_precision, context_recall  ║
║                                                                              ║
║  DEEPEVAL ADD-ONS (complement RAGAs — not duplicates)                       ║
║  Always: non_advice (legal safety)                                          ║
║  When contexts/reference doc: hallucination, contextual_relevancy           ║
║                                                                              ║
║  PASS THRESHOLD: 0.70 — industry standard starting point.                   ║
║  Raise to 0.80+ as YourAI matures and improves.                             ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python run_eval.py                                                       ║
║    python run_eval.py --limit 5    # first N cases only (saves judge quota) ║
║    (must run client.py first to generate results.json)                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import sys

# RAGAs → instructor → pydantic use `str | Path` annotations (Python 3.10+).
if sys.version_info < (3, 10):
    try:
        import eval_type_backport  # noqa: F401
    except ImportError:
        sys.exit(
            "ERROR: Python 3.9 cannot run RAGAs without eval_type_backport.\n"
            "Fix:  pip3 install eval_type_backport\n"
            "Better: use Python 3.11+ (project requires-python >= 3.11)."
        )

import json       # reads results.json
import math
import os         # reads environment variables
from collections import defaultdict  # groups rows by case_type and intent
from datetime import datetime        # formats the report timestamp
from pathlib import Path             # handles file paths

from dotenv import load_dotenv   # reads .env file

# ── STEP 1: LOAD SECRETS ─────────────────────────────────────────────────────
#
# RAGAs needs an OpenAI key because it uses GPT as the judge LLM.
# Every test case costs a few fractions of a cent to score.
# For 75 test cases, expect to spend roughly $0.05–$0.15 total.

load_dotenv(Path(__file__).parent.parent / ".env")

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))
from llm import config as llm_config
from llm.env_validate import is_gemini_placeholder, is_openai_placeholder, is_openrouter_placeholder

JUDGE_PROVIDER = llm_config.JUDGE_PROVIDER

if JUDGE_PROVIDER == "gemini":
    if is_gemini_placeholder(llm_config.GEMINI_API_KEY):
        sys.exit(
            "ERROR: GEMINI_API_KEY is missing or still a placeholder in .env.\n"
            "Set LLM_PROVIDER=gemini (or JUDGE_PROVIDER=gemini) and paste your Gemini key."
        )
elif JUDGE_PROVIDER == "openrouter":
    if is_openrouter_placeholder(llm_config.OPENROUTER_API_KEY):
        sys.exit(
            "ERROR: OPENROUTER_API_KEY is missing or still a placeholder in .env.\n"
            "Set JUDGE_PROVIDER=openrouter (or LLM_PROVIDER=openrouter) and add your OpenRouter key."
        )
elif is_openai_placeholder(llm_config.OPENAI_API_KEY):
    sys.exit(
        "ERROR: OPENAI_API_KEY is missing or still a placeholder in .env.\n"
        "Add an OpenAI key or set JUDGE_PROVIDER=gemini / openrouter."
    )

# The score a metric must reach to be considered passing.
# 0.70 = 70% quality threshold — standard starting point for LLM evaluation.
# Raise this to 0.80 as the product matures.
PASS_THRESHOLD = 0.70

import argparse

_eval_parser = argparse.ArgumentParser(description="Score results with RAGAs + DeepEval.")
_eval_parser.add_argument(
    "--report-only",
    action="store_true",
    help="Rebuild report.html from existing scores.csv (skip RAGAs API calls)",
)
_eval_parser.add_argument(
    "--limit",
    type=int,
    default=None,
    metavar="N",
    help="Score only the first N rows from results.json (saves judge API quota). "
    "Overrides RUN_EVAL_MAX_CASES from .env when set.",
)
_eval_args = _eval_parser.parse_args()


# ── STEP 2: FILE PATHS ────────────────────────────────────────────────────────

from qa.paths import (
    REPORT_HTML,
    RESULTS_FILE,
    SCORES_CSV,
    ensure_results_dir,
    migrate_legacy_outputs,
)

_migrated = migrate_legacy_outputs()
if _migrated:
    print(f"Migrated legacy outputs → qa/results/: {', '.join(_migrated)}")
ensure_results_dir()


# ── STEP 3: LOAD RESULTS ──────────────────────────────────────────────────────

if not RESULTS_FILE.exists():
    sys.exit(
        f"ERROR: {RESULTS_FILE} not found.\n"
        "Run  python client.py  first to collect API responses.\n"
        "run_eval.py scores answers — it needs answers to already exist."
    )

# json.loads reads the file and converts JSON text → Python list of dicts
from qa.align import (
    align_results,
    find_alignment_errors,
    load_test_cases_by_id,
    load_test_cases_list,
)
from qa.eval_metrics import (
    build_ragas_dataset_dict,
    combine_active_metric_names,
    is_finite_score,
    labels_for_columns,
    merge_deepeval_scores_into_df,
    metric_names_from_df,
    metric_passes,
    metric_short_header,
    prepare_eval_row,
    rows_with_contexts,
    rows_with_hallucination_context,
    run_deepeval_scores,
    select_deepeval_metric_names,
    select_ragas_metrics,
)

_loaded = json.loads(RESULTS_FILE.read_text())
_test_cases_list = load_test_cases_list()
_test_cases_by_id = load_test_cases_by_id()

_drift = find_alignment_errors(_loaded, _test_cases_list)
if _drift:
    print("⚠ results.json was out of sync with test_cases.json — fixing file before scoring:")
    for msg in _drift[:8]:
        print(f"  • {msg.splitlines()[0]}")
    if len(_drift) > 8:
        print(f"  • … and {len(_drift) - 8} more")
    try:
        _loaded = align_results(_loaded, _test_cases_list)
        RESULTS_FILE.write_text(json.dumps(_loaded, indent=2))
        print(f"  ✓ Updated {RESULTS_FILE.name} from test_cases.json\n")
    except ValueError as e:
        sys.exit(f"ERROR: cannot align results — {e}")


for r in _loaded:
    rid = r.get("id")
    if rid not in _test_cases_by_id:
        sys.exit(
            f"ERROR: result id {rid!r} not in test_cases.json — "
            "re-run ingest_cases.py / client.py."
        )

raw = [prepare_eval_row(r, _test_cases_by_id[r["id"]]) for r in _loaded]
_ref_rows = sum(1 for r in raw if r.get("reference_contexts"))
if _ref_rows:
    print(
        f"Reference contexts available for {_ref_rows} row(s) "
        f"(test_cases / local document / session.json).\n"
    )

_limit = _eval_args.limit
if _limit is None:
    _env_lim = os.getenv("RUN_EVAL_MAX_CASES", "").strip()
    if _env_lim.isdigit():
        _limit = int(_env_lim)
if _limit is not None and _limit > 0:
    if _limit < len(raw):
        print(
            f"Limiting evaluation to first {_limit} of {len(raw)} results "
            f"(--limit or RUN_EVAL_MAX_CASES).\n"
        )
    raw = raw[:_limit]

print(f"Loaded {len(raw)} results from {RESULTS_FILE.resolve().name}\n")

if _eval_args.report_only:
    print(
        "NOTE: --report-only rebuilds HTML from existing scores.csv only.\n"
        "      It does NOT re-read results.json. Run without --report-only to re-score.\n"
    )



# ── STEP 4: BUILD THE RAGAs DATASET ──────────────────────────────────────────
#
# RAGAs expects a HuggingFace Dataset object — a specific table format.
# We build it from four parallel Python lists (all same length, same order).
#
# Dataset.from_dict() takes a dictionary of lists:
#   {
#     "question":     ["q1", "q2", "q3", ...],
#     "answer":       ["a1", "a2", "a3", ...],
#     "contexts":     [[], [], [], ...],        ← empty lists in Tier 1
#     "ground_truth": ["gt1", "gt2", "gt3", ...]
#   }
#
# The list comprehensions [r["question"] for r in raw] extract each field
# from every row in raw (the results.json data).

if not _eval_args.report_only:
    # RAGAs / instructor still read OPENAI_API_KEY for some metric code paths even when
    # we pass a custom llm. Point them at OpenRouter so a placeholder OPENAI_API_KEY
    # in .env does not cause 401s on platform.openai.com.
    if JUDGE_PROVIDER == "openrouter":
        _or_base = llm_config.OPENROUTER_BASE_URL.rstrip("/")
        os.environ["OPENAI_API_KEY"] = llm_config.OPENROUTER_API_KEY
        os.environ["OPENAI_BASE_URL"] = _or_base
        os.environ["OPENAI_API_BASE"] = _or_base

    from datasets import Dataset          # HuggingFace datasets library
    from ragas import evaluate            # the main RAGAs scoring function

    dataset = Dataset.from_dict(build_ragas_dataset_dict(raw))
    metrics, RAGAS_METRIC_NAMES = select_ragas_metrics(raw)
    DEEPEVAL_METRIC_NAMES_ACTIVE = select_deepeval_metric_names(raw)

    print(f"Dataset: {len(dataset)} rows, columns: {dataset.column_names}")
    print(f"RAGAs metrics: {', '.join(RAGAS_METRIC_NAMES)}")
    print(f"DeepEval metrics: {', '.join(DEEPEVAL_METRIC_NAMES_ACTIVE)}\n")


# ── STEP 5: RUN RAGAs ────────────────────────────────────────────────────────
#
# evaluate() is the core RAGAs function.
# It sends each row to the judge LLM (OpenAI) and computes scores.
#
# This is the step that takes 2-5 minutes — each metric requires multiple
# LLM calls per row. For 75 rows × 3 metrics = ~225 LLM calls total.
#
# The result is a dictionary-like object. We convert it to a pandas DataFrame
# (a table structure) for easy manipulation and CSV export.

if not _eval_args.report_only:
    if JUDGE_PROVIDER == "gemini":
        judge_label = f"Gemini ({llm_config.GEMINI_MODEL})"
    elif JUDGE_PROVIDER == "openrouter":
        judge_label = f"OpenRouter ({llm_config.OPENROUTER_MODEL})"
    else:
        judge_label = f"OpenAI ({os.getenv('OPENAI_MODEL', 'gpt-4o-mini')})"
    print(f"Running RAGAs evaluation (judge LLM: {judge_label})...")
    if JUDGE_PROVIDER == "openrouter":
        print(
            f"  (OpenRouter key + model {llm_config.OPENROUTER_MODEL}; "
            f"embeddings: {llm_config.OPENROUTER_EMBEDDING_MODEL})"
        )
    print("This takes 2-5 minutes depending on number of test cases.")
    print("─" * 60)

    _ctx_count = rows_with_contexts(raw)
    if _ctx_count:
        print(
            f"RAG contexts detected in {_ctx_count} row(s) — "
            f"including {len(RAGAS_METRIC_NAMES) - 3} RAGAs retrieval metric(s).\n"
        )
    else:
        print(
            "No non-empty contexts in results — RAGAs Tier 1 only "
            "(re-run client.py or check source_attribution in API responses).\n"
        )
        RAGAS_METRIC_NAMES = [n for n in RAGAS_METRIC_NAMES if n in (
            "answer_relevancy", "answer_correctness", "answer_similarity"
        )]

    eval_kwargs: dict = {
        "dataset": dataset,
        "metrics": metrics,
    }

    if JUDGE_PROVIDER == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from ragas.llms import LangchainLLMWrapper
        except ImportError:
            sys.exit(
                "ERROR: langchain-google-genai is required for JUDGE_PROVIDER=gemini.\n"
                "Run: uv sync   or   pip install langchain-google-genai"
            )
        judge_llm = ChatGoogleGenerativeAI(
            model=llm_config.GEMINI_MODEL,
            google_api_key=llm_config.GEMINI_API_KEY,
            temperature=0.2,
        )
        eval_kwargs["llm"] = LangchainLLMWrapper(judge_llm)
        try:
            from google import genai as google_genai
            from ragas.embeddings import GoogleEmbeddings

            eval_kwargs["embeddings"] = GoogleEmbeddings(
                client=google_genai.Client(api_key=llm_config.GEMINI_API_KEY),
                model="gemini-embedding-001",
            )
        except ImportError:
            pass  # optional google-genai; without it RAGAs may use default OpenAI embeddings

    elif JUDGE_PROVIDER == "openrouter":
        try:
            from langchain_openai import ChatOpenAI
            from ragas.llms import LangchainLLMWrapper
        except ImportError:
            sys.exit(
                "ERROR: langchain-openai is required for JUDGE_PROVIDER=openrouter.\n"
                "Run: uv sync   or   pip install langchain-openai"
            )
        judge_llm = ChatOpenAI(
            model=llm_config.OPENROUTER_MODEL,
            openai_api_key=llm_config.OPENROUTER_API_KEY,
            openai_api_base=llm_config.OPENROUTER_BASE_URL.rstrip("/"),
            temperature=0.2,
        )
        eval_kwargs["llm"] = LangchainLLMWrapper(judge_llm)
        # RAGAs defaults embeddings to OpenAI (reads OPENAI_API_KEY). Route embeddings
        # through OpenRouter using LangChain (same key/base as the judge chat model).
        try:
            from langchain_openai import OpenAIEmbeddings as LCOpenAIEmbeddings
            from ragas.embeddings import LangchainEmbeddingsWrapper
        except ImportError:
            sys.exit(
                "ERROR: langchain-openai is required for OpenRouter embeddings in RAGAs.\n"
                "Run: pip install langchain-openai"
            )
        _or_base = llm_config.OPENROUTER_BASE_URL.rstrip("/")
        _lc_emb = LCOpenAIEmbeddings(
            model=llm_config.OPENROUTER_EMBEDDING_MODEL,
            openai_api_key=llm_config.OPENROUTER_API_KEY,
            openai_api_base=_or_base,
        )
        eval_kwargs["embeddings"] = LangchainEmbeddingsWrapper(_lc_emb)

    elif JUDGE_PROVIDER == "openai":
        try:
            from langchain_openai import ChatOpenAI
            from langchain_openai import OpenAIEmbeddings as LCOpenAIEmbeddings
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
        except ImportError:
            sys.exit(
                "ERROR: langchain-openai is required for JUDGE_PROVIDER=openai.\n"
                "Run: uv sync   or   pip install langchain-openai"
            )
        judge_llm = ChatOpenAI(
            model=llm_config.OPENAI_MODEL,
            openai_api_key=llm_config.OPENAI_API_KEY,
            temperature=0.2,
            max_tokens=int(os.getenv("OPENAI_JUDGE_MAX_TOKENS", "8192")),
        )
        eval_kwargs["llm"] = LangchainLLMWrapper(judge_llm)
        _lc_emb = LCOpenAIEmbeddings(
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            openai_api_key=llm_config.OPENAI_API_KEY,
        )
        eval_kwargs["embeddings"] = LangchainEmbeddingsWrapper(_lc_emb)

    result = evaluate(**eval_kwargs)

    # to_pandas() converts RAGAs result → pandas DataFrame (a table)
    df = result.to_pandas()
    if "question" not in df.columns and "user_input" in df.columns:
        df["question"] = df["user_input"]
    if "answer" not in df.columns and "response" in df.columns:
        df["answer"] = df["response"]

    # DeepEval add-ons (complement RAGAs; same judge provider)
    print("Running DeepEval metrics (complement RAGAs)...")
    print("─" * 60)
    _hall_ctx = rows_with_hallucination_context(raw)
    if _hall_ctx:
        print(f"  Hallucination context available for {_hall_ctx} row(s).")
    deepeval_score_rows = run_deepeval_scores(
        raw,
        judge_provider=JUDGE_PROVIDER,
        threshold=PASS_THRESHOLD,
        metric_names=DEEPEVAL_METRIC_NAMES_ACTIVE,
    )
    df = merge_deepeval_scores_into_df(
        df,
        deepeval_score_rows,
        active_metric_names=DEEPEVAL_METRIC_NAMES_ACTIVE,
    )
    ACTIVE_METRIC_NAMES = combine_active_metric_names(
        RAGAS_METRIC_NAMES,
        DEEPEVAL_METRIC_NAMES_ACTIVE,
    )
    print(f"DeepEval complete — active metrics: {', '.join(DEEPEVAL_METRIC_NAMES_ACTIVE)}\n")
    # Add our metadata columns back (RAGAs doesn't carry these through)
    df["id"]        = [r["id"]                           for r in raw]
    df["case_type"] = [r.get("case_type", "positive")    for r in raw]
    df["intent"]    = [r.get("intent",    "General Chat") for r in raw]
    df["source"]    = [r.get("source",    "human")        for r in raw]
else:
    import pandas as pd

    if not SCORES_CSV.exists():
        sys.exit(
            f"ERROR: {SCORES_CSV} not found.\n"
            "Run  python run_eval.py  without --report-only first."
        )
    df = pd.read_csv(SCORES_CSV)
    # RAGAs exports user_input/response; align names used in the HTML report
    if "question" not in df.columns and "user_input" in df.columns:
        df["question"] = df["user_input"]
    if "answer" not in df.columns and "response" in df.columns:
        df["answer"] = df["response"]
    ACTIVE_METRIC_NAMES = metric_names_from_df(df.columns, df)
    print(f"Loaded {len(df)} rows from {SCORES_CSV.name} (--report-only, skipping RAGAs)\n")


# ── STEP 6: SAVE CSV ──────────────────────────────────────────────────────────
#
# df.to_csv() saves the entire DataFrame as a comma-separated file.
# index=False means don't add an extra row-number column.
# The QA team can open this in Excel or Google Sheets.

if not _eval_args.report_only:
    df.to_csv(SCORES_CSV, index=False)

# ── STEP 7: PRINT SCORES TO TERMINAL ─────────────────────────────────────────
#
# Print a human-readable summary immediately so the QA team gets quick feedback
# without needing to open the HTML report.

def _is_finite_score(val) -> bool:
    return is_finite_score(val)


def _column_mean(series) -> float | None:
    """Mean ignoring NaN; None if no valid scores (e.g. judge rate-limited)."""
    clean = series.dropna()
    if clean.empty:
        return None
    mean = float(clean.mean())
    return mean if math.isfinite(mean) else None


def _rows_metric_mean(rows: list, col: str) -> float | None:
    values = [
        float(r[col])
        for r in rows
        if col in r and _is_finite_score(r[col])
    ]
    if not values:
        return None
    return sum(values) / len(values)


REPORT_METRIC_LABELS = labels_for_columns(ACTIVE_METRIC_NAMES)

print("\n✓ Evaluation complete!\n")
print("=" * 60)
print("AGGREGATE SCORES  (average across all test cases)")
print("=" * 60)

agg_scores = {}   # store the aggregate scores so we can use them in the HTML report later

for key in ACTIVE_METRIC_NAMES:
    if key not in df.columns:
        continue
    label = REPORT_METRIC_LABELS.get(key, key)

    val = _column_mean(df[key])
    agg_scores[key] = val

    if val is None:
        print(f"  {label}")
        print(f"  {'(no valid scores — judge errors or rate limits)':<20}  N/A")
        print()
        continue

    status = "✓ PASS" if metric_passes(key, val, PASS_THRESHOLD) else "✗ FAIL"
    bar = "█" * int(val * 20)

    print(f"  {label}")
    print(f"  {bar:<20} {val:.3f}  {status}")
    # :.3f = format as decimal with 3 places (e.g. 0.847)
    # :<20 = left-align in a 20-character field (so bars line up)
    print()

# Overall pass = ALL metrics must pass (not just some)
scored = [v for v in agg_scores.values() if _is_finite_score(v)]
overall_pass = bool(scored) and all(
    metric_passes(key, agg_scores[key], PASS_THRESHOLD)
    for key in ACTIVE_METRIC_NAMES
    if key in agg_scores and _is_finite_score(agg_scores[key])
)
if not scored:
    print("  ⚠ No valid metric scores — Gemini/OpenAI rate limit or API errors.")
    print(
        "    Check judge API keys, OpenRouter/OpenAI embedding routing in run_eval.py, "
        "or rate limits; then re-run.\n"
    )
print("=" * 60)
print(f"OVERALL: {'✓ PASS' if overall_pass else '✗ FAIL'}")
print("=" * 60)

# ── STEP 8: BUILD THE HTML REPORT ────────────────────────────────────────────
#
# We build the HTML report by constructing strings of HTML.
# Bootstrap (a CSS framework loaded from CDN) handles all the visual styling —
# we just use its class names like "bg-success", "badge", "table-dark".
#
# The report has 5 sections:
#   1. Header bar (title + metadata)
#   2. Overall PASS/FAIL banner
#   3. Aggregate score cards (one per metric)
#   4. Scores broken down by intent (mode) and by case type
#   5. Per-question detail table
#   6. Recommendations

# ── Helper functions ──────────────────────────────────────────────────────────

def score_color(val, metric_name: str | None = None):
    """
    Map a score (0-1) to a Bootstrap colour class name.
    Hallucination is inverted (lower is better).
    """
    if not _is_finite_score(val):
        return "secondary"   # grey — no data
    if metric_name and not metric_passes(metric_name, val, PASS_THRESHOLD):
        return "danger"
    value = float(val)
    if metric_name in ("hallucination",):
        if value <= 0.15:
            return "success"
        if value <= PASS_THRESHOLD:
            return "warning"
        return "danger"
    if value >= 0.85:
        return "success"     # green — excellent
    if value >= PASS_THRESHOLD:
        return "warning"     # yellow — acceptable
    return "danger"          # red — failing


def score_badge(val, metric_name: str | None = None):
    """
    Return an HTML badge showing the score with colour coding.
    Example output: <span class='badge bg-success'>0.847</span>
    """
    if not _is_finite_score(val):
        return "<span class='badge bg-secondary'>N/A</span>"
    color = score_color(val, metric_name)
    return f"<span class='badge bg-{color}'>{float(val):.3f}</span>"
    # :.3f = 3 decimal places (0.847, not 0.8473214...)


def _row_passes_threshold(row, metric_names: list[str]) -> bool:
    scored_names = [
        name
        for name in metric_names
        if _is_finite_score(row.get(name) if hasattr(row, "get") else row[name])
    ]
    if not scored_names:
        return False
    return all(
        metric_passes(
            name,
            row.get(name) if hasattr(row, "get") else row[name],
            PASS_THRESHOLD,
        )
        for name in scored_names
    )


def _group_passes_threshold(rows, metric_names: list[str]) -> bool:
    if not rows or not metric_names:
        return False
    scored_keys = []
    for key in metric_names:
        mean = _rows_metric_mean(rows, key)
        if not _is_finite_score(mean):
            continue
        scored_keys.append(key)
        if not metric_passes(key, mean, PASS_THRESHOLD):
            return False
    return bool(scored_keys)


def _metric_table_headers() -> str:
    return "".join(
        f'<th class="text-center">{metric_short_header(name)}</th>'
        for name in ACTIVE_METRIC_NAMES
    )


def _metric_table_cells(row) -> str:
    return "".join(
        f'<td class="text-center">{score_badge(row.get(name), name)}</td>'
        for name in ACTIVE_METRIC_NAMES
    )


def _metric_table_cells_for_group(rows) -> str:
    return "".join(
        f'<td class="text-center">{score_badge(_rows_metric_mean(rows, name), name)}</td>'
        for name in ACTIVE_METRIC_NAMES
    )


# ── Group rows for breakdown tables ──────────────────────────────────────────
#
# defaultdict(list) is like a regular dict but automatically creates an empty
# list for any key that doesn't exist yet. Convenient for grouping.
#
# We group by case_type and intent separately so we can build two breakdown tables.

# Group rows by case_type (positive / negative / edge / adversarial)
type_groups = defaultdict(list)
for _, row in df.iterrows():
    type_groups[row["case_type"]].append(row)

# Group rows by intent (General Chat / Legal Q&A / Clause Analysis / etc.)
intent_groups = defaultdict(list)
for _, row in df.iterrows():
    intent_groups[row["intent"]].append(row)

type_summary_rows = ""
for ctype in ["positive", "negative", "edge", "adversarial"]:
    rows = type_groups.get(ctype, [])
    if not rows:
        continue
    type_pass = _group_passes_threshold(rows, ACTIVE_METRIC_NAMES)
    type_summary_rows += f"""
      <tr>
        <td><span class="badge bg-{'info' if ctype=='positive' else 'warning' if ctype=='edge' else 'danger' if ctype in ['negative','adversarial'] else 'secondary'} text-dark">{ctype}</span></td>
        <td>{len(rows)}</td>
        {_metric_table_cells_for_group(rows)}
        <td><span class="badge bg-{'success' if type_pass else 'danger'}">{'PASS' if type_pass else 'FAIL'}</span></td>
      </tr>"""

# Per-question rows
question_rows = ""
for _, row in df.iterrows():
    row_pass = _row_passes_threshold(row, ACTIVE_METRIC_NAMES)
    ctype  = row.get("case_type", "positive")
    intent = row.get("intent", "General Chat")
    src    = row.get("source", "human")
    q = str(row["question"])[:80] + ("…" if len(str(row["question"])) > 80 else "")
    question_rows += f"""
      <tr>
        <td class="text-muted small">{row.get('id','')}</td>
        <td>{q}</td>
        <td><small class="text-muted">{intent}</small></td>
        <td><span class="badge bg-{'info' if ctype=='positive' else 'warning text-dark' if ctype=='edge' else 'danger'}">{ctype}</span></td>
        <td><small class="text-muted">{src}</small></td>
        {_metric_table_cells(row)}
        <td><span class="badge bg-{'success' if row_pass else 'danger'}">{'PASS' if row_pass else 'FAIL'}</span></td>
      </tr>"""

# Recommendations
recs = []
if _is_finite_score(agg_scores.get("answer_relevancy")) and agg_scores["answer_relevancy"] < PASS_THRESHOLD:
    recs.append(("danger", "Low Answer Relevancy",
        "The AI is going off-topic. Review the system prompt in .env — "
        "it may be too vague. Add explicit scope constraints ('only answer US legal questions')."))
if _is_finite_score(agg_scores.get("answer_correctness")) and agg_scores["answer_correctness"] < PASS_THRESHOLD:
    recs.append(("danger", "Low Answer Correctness",
        "The AI is giving inaccurate answers. Consider: upgrading to GPT-4o, "
        "adding a Tier 2 retrieval layer with authoritative legal documents, "
        "or expanding the system prompt with more domain context."))
if _is_finite_score(agg_scores.get("answer_similarity")) and agg_scores["answer_similarity"] < PASS_THRESHOLD:
    recs.append(("warning", "Low Answer Similarity",
        "The AI's phrasing is far from the expected answers. This can mean the model "
        "uses very different terminology. Review whether your ground_truth entries "
        "are written in plain language vs. legal jargon — they should match the expected output style."))
if _is_finite_score(agg_scores.get("faithfulness")) and not metric_passes(
    "faithfulness", agg_scores["faithfulness"], PASS_THRESHOLD
):
    recs.append(("danger", "Low Faithfulness",
        "Answers contain claims not supported by retrieved source_attribution snippets. "
        "Review hallucination guardrails and retrieval scope locking."))
if _is_finite_score(agg_scores.get("context_precision")) and not metric_passes(
    "context_precision", agg_scores["context_precision"], PASS_THRESHOLD
):
    recs.append(("warning", "Low Context Precision",
        "Retrieved chunks are often irrelevant to the question. Tune hybrid retrieval "
        "or tighten document scope."))
if _is_finite_score(agg_scores.get("context_recall")) and not metric_passes(
    "context_recall", agg_scores["context_recall"], PASS_THRESHOLD
):
    recs.append(("warning", "Low Context Recall",
        "Retrieved contexts miss facts needed for the ground-truth answer. "
        "Check chunking, top-k, or add reference_contexts from the uploaded document."))
if _is_finite_score(agg_scores.get("non_advice")) and not metric_passes(
    "non_advice", agg_scores["non_advice"], PASS_THRESHOLD
):
    recs.append(("danger", "Low Non-Advice Score",
        "The AI may be giving specific legal advice instead of deferring to qualified counsel. "
        "Review system prompt guardrails and refusal patterns for legal questions."))
if _is_finite_score(agg_scores.get("hallucination")) and not metric_passes(
    "hallucination", agg_scores["hallucination"], PASS_THRESHOLD
):
    recs.append(("danger", "High Hallucination (DeepEval)",
        "Answers contradict the reference or retrieved context. "
        "Tighten grounding rules and verify source_attribution coverage."))
if _is_finite_score(agg_scores.get("contextual_relevancy")) and not metric_passes(
    "contextual_relevancy", agg_scores["contextual_relevancy"], PASS_THRESHOLD
):
    recs.append(("warning", "Low Contextual Relevancy (DeepEval)",
        "Retrieved chunks contain too much irrelevant material for the question. "
        "Reduce top-k or improve chunking / hybrid retrieval ranking."))
neg_rows = type_groups.get("negative", []) + type_groups.get("adversarial", [])
if neg_rows:
    neg_rel = _rows_metric_mean(neg_rows, "answer_relevancy")
    if _is_finite_score(neg_rel) and neg_rel > 0.7:
        recs.append(("warning", "AI may not be refusing harmful requests",
            "Negative/adversarial cases scored HIGH on relevancy — this could mean "
            "the AI is engaging with requests it should refuse. Review the per-question "
            "answers for negative cases manually."))
if not scored:
    recs.insert(0, ("danger", "Scoring incomplete",
        "RAGAs could not compute metrics (often Gemini free-tier daily limit: 20 requests/model). "
        "Re-run <code>python run_eval.py</code> after quota resets, or use OpenAI as judge."))
if not recs:
    tier_note = (
        "All active RAGAs + DeepEval metrics are above the 0.70 threshold."
        if len(ACTIVE_METRIC_NAMES) > 4
        else "All Tier-1 metrics are above the 0.70 threshold."
    )
    recs.append(("success", "All metrics passing",
        f"{tier_note} Consider raising the threshold to 0.80 or adding more edge cases."))

# Intent summary rows
INTENT_ORDER = ["General Chat","Legal Q&A","Legal Research","Case Law Analysis","Find Document","Clause Analysis","Clause Comparison"]
intent_summary_rows = ""
for intent in INTENT_ORDER:
    rows = intent_groups.get(intent, [])
    if not rows:
        continue
    ipass = _group_passes_threshold(rows, ACTIVE_METRIC_NAMES)
    intent_summary_rows += f"""
      <tr>
        <td><strong>{intent}</strong></td>
        <td class="text-center">{len(rows)}</td>
        {_metric_table_cells_for_group(rows)}
        <td class="text-center"><span class="badge bg-{'success' if ipass else 'danger'}">{'PASS' if ipass else 'FAIL'}</span></td>
      </tr>"""

rec_html = ""
for level, title, body in recs:
    rec_html += f"""
      <div class="alert alert-{level} mb-3">
        <strong>{title}</strong><br>{body}
      </div>"""

# Aggregate metric cards
card_col = "col-md-3" if len(ACTIVE_METRIC_NAMES) > 6 else "col-md-4"
card_html = ""
for key in ACTIVE_METRIC_NAMES:
    val = agg_scores.get(key)
    if val is None:
        continue
    label = REPORT_METRIC_LABELS.get(key, key)
    color = score_color(val, key)
    status = "PASS" if metric_passes(key, val, PASS_THRESHOLD) else "FAIL"
    card_html += f"""
      <div class="{card_col}">
        <div class="card text-center border-{color} mb-3">
          <div class="card-header bg-{color} text-white">{status}</div>
          <div class="card-body">
            <h2 class="card-title">{val:.3f}</h2>
            <p class="card-text small">{label}</p>
          </div>
        </div>
      </div>"""

metrics_footer = ", ".join(ACTIVE_METRIC_NAMES)
_has_ragas_t2 = any(n in ACTIVE_METRIC_NAMES for n in (
    "faithfulness", "context_precision", "context_recall",
))
_has_deepeval_t2 = any(n in ACTIVE_METRIC_NAMES for n in (
    "hallucination", "contextual_relevancy",
))
if _has_ragas_t2 and _has_deepeval_t2:
    tier_footer = "RAGAs Tier 1+2 + DeepEval retrieval metrics"
elif _has_ragas_t2:
    tier_footer = "RAGAs Tier 1+2 + DeepEval safety"
elif _has_deepeval_t2:
    tier_footer = "RAGAs Tier 1 + DeepEval retrieval/safety"
else:
    tier_footer = "RAGAs Tier 1 + DeepEval safety (no retrieval contexts)"

now = datetime.now().strftime("%Y-%m-%d %H:%M")
overall_color = "success" if overall_pass else "danger"
overall_label = "ALL METRICS PASSING" if overall_pass else "ONE OR MORE METRICS FAILING"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YourAI RAGAs + DeepEval Evaluation Report</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; }}
    .header-bar {{ background: #1a1a2e; color: white; padding: 2rem; margin-bottom: 2rem; }}
    .section-title {{ border-left: 4px solid #0d6efd; padding-left: 0.75rem; margin: 2rem 0 1rem; }}
    table {{ font-size: 0.875rem; }}
    .badge {{ font-size: 0.8rem; }}
  </style>
</head>
<body>
  <div class="header-bar">
    <div class="container">
      <h1 class="mb-1">YourAI — RAGAs + DeepEval Evaluation Report</h1>
      <p class="mb-0 text-light">Generated: {now} &nbsp;·&nbsp; Judge: {JUDGE_PROVIDER} / {(llm_config.GEMINI_MODEL if JUDGE_PROVIDER == 'gemini' else llm_config.OPENROUTER_MODEL if JUDGE_PROVIDER == 'openrouter' else os.getenv('OPENAI_MODEL','gpt-4o-mini'))} &nbsp;·&nbsp; Test cases: {len(raw)}</p>
    </div>
  </div>

  <div class="container">

    <!-- Executive Summary -->
    <div class="alert alert-{overall_color} text-center fs-5 mb-4">
      <strong>OVERALL RESULT: {overall_label}</strong>
      <span class="ms-3 badge bg-{overall_color} fs-6">(threshold: {PASS_THRESHOLD})</span>
    </div>

    <!-- Score Cards -->
    <h4 class="section-title">Aggregate Scores</h4>
    <div class="row">{card_html}</div>

    <!-- By Intent -->
    <h4 class="section-title">Scores by Intent (Mode)</h4>
    <table class="table table-bordered table-hover bg-white">
      <thead class="table-dark">
        <tr>
          <th>Intent / Mode</th><th class="text-center">Cases</th>
          {_metric_table_headers()}<th class="text-center">Result</th>
        </tr>
      </thead>
      <tbody>{intent_summary_rows}</tbody>
    </table>

    <!-- By Case Type -->
    <h4 class="section-title">Scores by Test Case Type</h4>
    <table class="table table-bordered table-hover bg-white">
      <thead class="table-dark">
        <tr>
          <th>Type</th><th class="text-center">Count</th>
          {_metric_table_headers()}<th class="text-center">Result</th>
        </tr>
      </thead>
      <tbody>{type_summary_rows}</tbody>
    </table>

    <!-- Per-question detail -->
    <h4 class="section-title">Per-Question Detail</h4>
    <div class="table-responsive">
      <table class="table table-sm table-bordered table-hover bg-white">
        <thead class="table-dark">
          <tr>
            <th>ID</th><th>Question</th><th>Intent</th><th>Type</th><th>Source</th>
            {_metric_table_headers()}<th>Result</th>
          </tr>
        </thead>
        <tbody>{question_rows}</tbody>
      </table>
    </div>

    <!-- Recommendations -->
    <h4 class="section-title">Recommendations</h4>
    {rec_html}

    <hr class="my-4">
    <p class="text-muted small text-center">
      YourAI RAGAs + DeepEval Evaluation &nbsp;·&nbsp; {tier_footer} &nbsp;·&nbsp;
      Metrics: {metrics_footer} &nbsp;·&nbsp;
      Pass threshold: {PASS_THRESHOLD}
    </p>
  </div>
</body>
</html>"""

REPORT_HTML.write_text(html)

if not _eval_args.report_only:
    print(f"\n✓ CSV saved   → {SCORES_CSV}")
else:
    print()
print(f"✓ HTML report → {REPORT_HTML}")
print(f"\n  Open report.html in any browser for the full formatted report.")
print(f"  Share scores.csv with the team in Excel / Google Sheets.")
