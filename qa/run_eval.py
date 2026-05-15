"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  run_eval.py — Score every answer with RAGAs and produce the final report   ║
║                                                                              ║
║  WHAT THIS FILE DOES:                                                        ║
║  This is the SCORER. It reads results.json (produced by client.py),         ║
║  sends every question+answer pair to RAGAs, and produces two output files:  ║
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
║  THE 6 RAGAs METRICS AND WHEN EACH IS ACTIVE:                               ║
║                                                                              ║
║  ── TIER 1 (active now — no document retrieval needed) ──────────────────   ║
║  answer_relevancy   → Is the answer on-topic? Did it address the question?  ║
║  answer_correctness → Does it match the ground truth? Is it accurate?       ║
║  answer_similarity  → Semantic closeness to ground truth (meaning, not words)║
║                                                                              ║
║  ── TIER 2 (coming later — needs document retrieval / vector store) ──────  ║
║  faithfulness       → Is the answer grounded in retrieved documents?        ║
║                        Catches hallucination — AI making up confident facts ║
║  context_precision  → Were the retrieved documents actually relevant?       ║
║                        Catches noise — pulling irrelevant documents          ║
║  context_recall     → Did we retrieve ALL the documents we needed?          ║
║                        Catches gaps — missing important source material      ║
║                                                                              ║
║  PASS THRESHOLD: 0.70 — industry standard starting point.                   ║
║  Raise to 0.80+ as YourAI matures and improves.                             ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python run_eval.py                                                       ║
║    (must run client.py first to generate results.json)                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json       # reads results.json
import os         # reads environment variables
import sys        # exits with error messages
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

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-replace"):
    sys.exit(
        "ERROR: OPENAI_API_KEY is not set in .env.\n"
        "RAGAs uses OpenAI as the judge LLM — it needs a real key to work."
    )

# The score a metric must reach to be considered passing.
# 0.70 = 70% quality threshold — standard starting point for LLM evaluation.
# Raise this to 0.80 as the product matures.
PASS_THRESHOLD = 0.70


# ── STEP 2: FILE PATHS ────────────────────────────────────────────────────────

QA_DIR       = Path(__file__).parent
RESULTS_FILE = QA_DIR / "results.json"   # input — produced by client.py
SCORES_CSV   = QA_DIR / "scores.csv"     # output — raw scores for Excel/Sheets
REPORT_HTML  = QA_DIR / "report.html"    # output — formatted report for browser


# ── STEP 3: LOAD RESULTS ──────────────────────────────────────────────────────

if not RESULTS_FILE.exists():
    sys.exit(
        f"ERROR: {RESULTS_FILE} not found.\n"
        "Run  python client.py  first to collect API responses.\n"
        "run_eval.py scores answers — it needs answers to already exist."
    )

# json.loads reads the file and converts JSON text → Python list of dicts
raw = json.loads(RESULTS_FILE.read_text())
print(f"Loaded {len(raw)} results from {RESULTS_FILE.name}\n")


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

from datasets import Dataset          # HuggingFace datasets library
from ragas import evaluate            # the main RAGAs scoring function
from ragas.metrics import (           # the specific metrics we're running
    answer_correctness,   # Tier 1: how accurate vs ground truth
    answer_relevancy,     # Tier 1: how on-topic vs the question
    answer_similarity,    # Tier 1: semantic closeness to ground truth
    # faithfulness,       # Tier 2: grounded in retrieved documents (needs contexts)
    # context_precision,  # Tier 2: retrieved docs were relevant (needs contexts)
    # context_recall,     # Tier 2: all needed docs were retrieved (needs contexts)
)

dataset = Dataset.from_dict({
    "question":     [r["question"]     for r in raw],
    "answer":       [r["answer"]       for r in raw],
    "contexts":     [r["contexts"]     for r in raw],   # list of lists — [] in Tier 1
    "ground_truth": [r["ground_truth"] for r in raw],
})

print(f"Dataset: {len(dataset)} rows, columns: {dataset.column_names}\n")


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

print("Running RAGAs evaluation (calling OpenAI as judge LLM)...")
print("This takes 2-5 minutes depending on number of test cases.")
print("─" * 60)

result = evaluate(
    dataset,
    metrics=[
        answer_relevancy,    # Is the answer on-topic?
        answer_correctness,  # Is the answer accurate vs ground truth?
        answer_similarity,   # Semantic closeness to ground truth
    ],
)

# to_pandas() converts RAGAs result → pandas DataFrame (a table)
# Each row = one test case. Columns = question, answer, each metric score
df = result.to_pandas()

# Add our metadata columns back (RAGAs doesn't carry these through)
# We look them up from raw (results.json) by position — same order guaranteed
df["id"]        = [r["id"]                           for r in raw]
df["case_type"] = [r.get("case_type", "positive")    for r in raw]
df["intent"]    = [r.get("intent",    "General Chat") for r in raw]
df["source"]    = [r.get("source",    "human")        for r in raw]


# ── STEP 6: SAVE CSV ──────────────────────────────────────────────────────────
#
# df.to_csv() saves the entire DataFrame as a comma-separated file.
# index=False means don't add an extra row-number column.
# The QA team can open this in Excel or Google Sheets.

df.to_csv(SCORES_CSV, index=False)

# ── STEP 7: PRINT SCORES TO TERMINAL ─────────────────────────────────────────
#
# Print a human-readable summary immediately so the QA team gets quick feedback
# without needing to open the HTML report.

# Human-readable labels for each metric column name
METRIC_LABELS = {
    "answer_relevancy":   "Answer Relevancy   (on-topic?)",
    "answer_correctness": "Answer Correctness (matches ground truth?)",
    "answer_similarity":  "Answer Similarity  (semantically close?)",
}

print("\n✓ Evaluation complete!\n")
print("=" * 60)
print("AGGREGATE SCORES  (average across all test cases)")
print("=" * 60)

agg_scores = {}   # store the aggregate scores so we can use them in the HTML report later

for key, label in METRIC_LABELS.items():
    if key not in df.columns:
        continue   # skip if this metric wasn't computed (shouldn't happen normally)

    val = df[key].mean()   # mean() = average of all values in this column
    agg_scores[key] = val

    status = "✓ PASS" if val >= PASS_THRESHOLD else "✗ FAIL"

    # Visual bar: each █ block = 5% (20 blocks = 100%)
    # int(val * 20) = number of filled blocks
    bar = "█" * int(val * 20)

    print(f"  {label}")
    print(f"  {bar:<20} {val:.3f}  {status}")
    # :.3f = format as decimal with 3 places (e.g. 0.847)
    # :<20 = left-align in a 20-character field (so bars line up)
    print()

# Overall pass = ALL metrics must pass (not just some)
overall_pass = all(v >= PASS_THRESHOLD for v in agg_scores.values())
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

def score_color(val):
    """
    Map a score (0-1) to a Bootstrap colour class name.
    Bootstrap colour classes control the background colour of badges and cards.
      success = green  (score ≥ 0.85 = excellent)
      warning = yellow (score ≥ 0.70 = acceptable, passes threshold)
      danger  = red    (score < 0.70 = failing)
      secondary = grey (no score / N/A)
    """
    if val is None or str(val) == "nan":
        return "secondary"   # grey — no data
    if val >= 0.85:
        return "success"     # green — excellent
    if val >= PASS_THRESHOLD:
        return "warning"     # yellow — acceptable
    return "danger"          # red — failing


def score_badge(val):
    """
    Return an HTML badge showing the score with colour coding.
    Example output: <span class='badge bg-success'>0.847</span>
    """
    if val is None:
        return "<span class='badge bg-secondary'>N/A</span>"
    color = score_color(val)
    return f"<span class='badge bg-{color}'>{val:.3f}</span>"
    # :.3f = 3 decimal places (0.847, not 0.8473214...)


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
    avg = lambda col: sum(r[col] for r in rows if col in r and str(r[col]) != "nan") / max(len(rows), 1)
    rel  = avg("answer_relevancy")
    cor  = avg("answer_correctness")
    sim  = avg("answer_similarity")
    type_pass = all(v >= PASS_THRESHOLD for v in [rel, cor, sim])
    type_summary_rows += f"""
      <tr>
        <td><span class="badge bg-{'info' if ctype=='positive' else 'warning' if ctype=='edge' else 'danger' if ctype in ['negative','adversarial'] else 'secondary'} text-dark">{ctype}</span></td>
        <td>{len(rows)}</td>
        <td>{score_badge(rel)}</td>
        <td>{score_badge(cor)}</td>
        <td>{score_badge(sim)}</td>
        <td><span class="badge bg-{'success' if type_pass else 'danger'}">{'PASS' if type_pass else 'FAIL'}</span></td>
      </tr>"""

# Per-question rows
question_rows = ""
for _, row in df.iterrows():
    rel = row.get("answer_relevancy")
    cor = row.get("answer_correctness")
    sim = row.get("answer_similarity")
    row_pass = all(
        (v >= PASS_THRESHOLD) for v in [rel, cor, sim]
        if v is not None and str(v) != "nan"
    )
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
        <td>{score_badge(rel)}</td>
        <td>{score_badge(cor)}</td>
        <td>{score_badge(sim)}</td>
        <td><span class="badge bg-{'success' if row_pass else 'danger'}">{'PASS' if row_pass else 'FAIL'}</span></td>
      </tr>"""

# Recommendations
recs = []
if agg_scores.get("answer_relevancy", 1) < PASS_THRESHOLD:
    recs.append(("danger", "Low Answer Relevancy",
        "The AI is going off-topic. Review the system prompt in .env — "
        "it may be too vague. Add explicit scope constraints ('only answer US legal questions')."))
if agg_scores.get("answer_correctness", 1) < PASS_THRESHOLD:
    recs.append(("danger", "Low Answer Correctness",
        "The AI is giving inaccurate answers. Consider: upgrading to GPT-4o, "
        "adding a Tier 2 retrieval layer with authoritative legal documents, "
        "or expanding the system prompt with more domain context."))
if agg_scores.get("answer_similarity", 1) < PASS_THRESHOLD:
    recs.append(("warning", "Low Answer Similarity",
        "The AI's phrasing is far from the expected answers. This can mean the model "
        "uses very different terminology. Review whether your ground_truth entries "
        "are written in plain language vs. legal jargon — they should match the expected output style."))
neg_rows = type_groups.get("negative", []) + type_groups.get("adversarial", [])
if neg_rows:
    neg_rel = sum(r.get("answer_relevancy", 0) for r in neg_rows) / len(neg_rows)
    if neg_rel > 0.7:
        recs.append(("warning", "AI may not be refusing harmful requests",
            "Negative/adversarial cases scored HIGH on relevancy — this could mean "
            "the AI is engaging with requests it should refuse. Review the per-question "
            "answers for negative cases manually."))
if not recs:
    recs.append(("success", "All metrics passing",
        "All three Tier-1 metrics are above the 0.70 threshold. "
        "Consider raising the threshold to 0.80, adding more edge cases, "
        "or moving to Tier 2 (retrieval) for higher accuracy."))

# Intent summary rows
INTENT_ORDER = ["General Chat","Legal Q&A","Legal Research","Case Law Analysis","Find Document","Clause Analysis","Clause Comparison"]
intent_summary_rows = ""
for intent in INTENT_ORDER:
    rows = intent_groups.get(intent, [])
    if not rows:
        continue
    avg = lambda col: sum(r[col] for r in rows if col in r and str(r[col]) != "nan") / max(len(rows),1)
    rel  = avg("answer_relevancy")
    cor  = avg("answer_correctness")
    sim  = avg("answer_similarity")
    ipass = all(v >= PASS_THRESHOLD for v in [rel, cor, sim])
    intent_summary_rows += f"""
      <tr>
        <td><strong>{intent}</strong></td>
        <td class="text-center">{len(rows)}</td>
        <td class="text-center">{score_badge(rel)}</td>
        <td class="text-center">{score_badge(cor)}</td>
        <td class="text-center">{score_badge(sim)}</td>
        <td class="text-center"><span class="badge bg-{'success' if ipass else 'danger'}">{'PASS' if ipass else 'FAIL'}</span></td>
      </tr>"""

rec_html = ""
for level, title, body in recs:
    rec_html += f"""
      <div class="alert alert-{level} mb-3">
        <strong>{title}</strong><br>{body}
      </div>"""

# Aggregate metric cards
card_html = ""
for key, label in METRIC_LABELS.items():
    val = agg_scores.get(key)
    if val is None:
        continue
    color = score_color(val)
    status = "PASS" if val >= PASS_THRESHOLD else "FAIL"
    card_html += f"""
      <div class="col-md-4">
        <div class="card text-center border-{color} mb-3">
          <div class="card-header bg-{color} text-white">{status}</div>
          <div class="card-body">
            <h2 class="card-title">{val:.3f}</h2>
            <p class="card-text small">{label}</p>
          </div>
        </div>
      </div>"""

now = datetime.now().strftime("%Y-%m-%d %H:%M")
overall_color = "success" if overall_pass else "danger"
overall_label = "ALL METRICS PASSING" if overall_pass else "ONE OR MORE METRICS FAILING"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YourAI RAGAs Evaluation Report</title>
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
      <h1 class="mb-1">YourAI — RAGAs Evaluation Report</h1>
      <p class="mb-0 text-light">Generated: {now} &nbsp;·&nbsp; Model: {os.getenv('OPENAI_MODEL','gpt-4o-mini')} &nbsp;·&nbsp; Test cases: {len(raw)}</p>
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
          <th class="text-center">Relevancy</th><th class="text-center">Correctness</th><th class="text-center">Similarity</th><th class="text-center">Result</th>
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
          <th class="text-center">Relevancy</th><th class="text-center">Correctness</th><th class="text-center">Similarity</th><th class="text-center">Result</th>
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
            <th>Relevancy</th><th>Correctness</th><th>Similarity</th><th>Result</th>
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
      YourAI RAGAs Evaluation &nbsp;·&nbsp; Tier 1 (no retrieval) &nbsp;·&nbsp;
      Metrics: answer_relevancy, answer_correctness, answer_similarity &nbsp;·&nbsp;
      Pass threshold: {PASS_THRESHOLD}
    </p>
  </div>
</body>
</html>"""

REPORT_HTML.write_text(html)

print(f"\n✓ CSV saved   → {SCORES_CSV}")
print(f"✓ HTML report → {REPORT_HTML}")
print(f"\n  Open report.html in any browser for the full formatted report.")
print(f"  Share scores.csv with the team in Excel / Google Sheets.")
