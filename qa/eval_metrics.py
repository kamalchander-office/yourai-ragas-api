"""
RAGAs + DeepEval metric selection and eval-row preparation for YourAI chat responses.

Project scope (legal RAG chatbot QA):
  RAGAs Tier 1 — golden answer quality vs test_cases ground_truth
  RAGAs Tier 2 — RAG quality when source_attribution provides contexts
  DeepEval add-ons — metrics not covered by RAGAs (hallucination, contextual
    relevancy, non-advice for legal safety)
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from yourai_chat.parser import parse_chat_response

from qa.align import align_result_row
from qa.corpus_grounding import resolve_document_for_case

QA_DIR = Path(__file__).parent
SESSION_FILE = QA_DIR / "session.json"
REFERENCE_CONTEXT_MAX_CHARS = 8000

# RAGAs metrics (six).
METRIC_LABELS: dict[str, str] = {
    "answer_relevancy": "Answer Relevancy (on-topic?)",
    "answer_correctness": "Answer Correctness (matches ground truth?)",
    "answer_similarity": "Answer Similarity (semantically close?)",
    "faithfulness": "Faithfulness (claims supported by retrieved docs?)",
    "context_precision": "Context Precision (retrieved chunks relevant?)",
    "context_recall": "Context Recall (retrieved enough for ground truth?)",
    # DeepEval add-ons (complement RAGAs; not duplicates).
    "non_advice": "Non-Advice (avoids impermissible legal advice?)",
    "hallucination": "Hallucination (contradicts source context?)",
    "contextual_relevancy": "Contextual Relevancy (retrieved chunks on-topic?)",
}

TIER1_METRIC_NAMES = (
    "answer_relevancy",
    "answer_correctness",
    "answer_similarity",
)

TIER2_METRIC_NAMES = (
    "faithfulness",
    "context_precision",
    "context_recall",
)

RAGAS_METRIC_NAMES = TIER1_METRIC_NAMES + TIER2_METRIC_NAMES

DEEPEVAL_TIER1_METRIC_NAMES = ("non_advice",)
DEEPEVAL_TIER2_METRIC_NAMES = ("hallucination", "contextual_relevancy")
DEEPEVAL_METRIC_NAMES = DEEPEVAL_TIER1_METRIC_NAMES + DEEPEVAL_TIER2_METRIC_NAMES

# All metrics that may appear in scores.csv / report.html (stable column order).
PROJECT_METRIC_NAMES = RAGAS_METRIC_NAMES + DEEPEVAL_METRIC_NAMES

# DeepEval hallucination: lower score is better (fraction of contradicting contexts).
INVERTED_PASS_METRICS = frozenset({"hallucination"})

_SHORT_HEADERS = {
    "answer_relevancy": "Relevancy",
    "answer_correctness": "Correctness",
    "answer_similarity": "Similarity",
    "faithfulness": "Faithful",
    "context_precision": "Ctx Prec",
    "context_recall": "Ctx Recall",
    "non_advice": "Non-Advice",
    "hallucination": "Halluc.",
    "contextual_relevancy": "Ctx Rel.",
}


def metric_short_header(name: str) -> str:
    return _SHORT_HEADERS.get(name, name.replace("_", " ").title()[:12])


def is_finite_score(val: Any) -> bool:
    if val is None:
        return False
    try:
        return math.isfinite(float(val))
    except (TypeError, ValueError):
        return False


def metric_passes(name: str, score: Any, threshold: float) -> bool:
    """Return whether a metric score passes (handles inverted hallucination)."""
    if not is_finite_score(score):
        return False
    value = float(score)
    if name in INVERTED_PASS_METRICS:
        return value <= threshold
    return value >= threshold


_document_store = None


def _get_document_store():
    global _document_store
    if _document_store is None:
        from qa.local_documents import LocalDocumentStore

        _document_store = LocalDocumentStore()
    return _document_store


def _non_empty_contexts(contexts: Any) -> list[str]:
    if not isinstance(contexts, list):
        return []
    return [c.strip() for c in contexts if isinstance(c, str) and c.strip()]


def _non_empty_reference_contexts(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _reference_from_session() -> list[str]:
    if not SESSION_FILE.exists():
        return []
    try:
        session = json.loads(SESSION_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    doc_meta = session.get("document") or {}
    local_path = (doc_meta.get("local_path") or "").strip()
    if not local_path:
        return []
    path = Path(local_path)
    if not path.is_file():
        return []
    try:
        store = _get_document_store()
        ctx = store.load_by_filename(
            path.name,
            document_id=(doc_meta.get("id") or path.stem),
        )
        text = ctx.text.strip()
        if text:
            return [text[:REFERENCE_CONTEXT_MAX_CHARS]]
    except Exception:
        return []
    return []


def resolve_reference_contexts(test_case: dict, row: dict | None = None) -> list[str]:
    """Optional gold document chunks for DeepEval hallucination and generate_cases."""
    row = row or {}
    for source in (
        test_case.get("reference_contexts"),
        row.get("reference_contexts"),
    ):
        refs = _non_empty_reference_contexts(source)
        if refs:
            return [r[:REFERENCE_CONTEXT_MAX_CHARS] for r in refs]

    try:
        store = _get_document_store()
        docs = store.load_all_fixtures()
        doc = resolve_document_for_case(test_case, docs)
        if doc and doc.text.strip():
            return [doc.text[:REFERENCE_CONTEXT_MAX_CHARS]]
    except Exception:
        pass

    return _reference_from_session()


def _hallucination_context(row: dict) -> list[str]:
    """Ground-truth context for DeepEval hallucination (reference doc preferred)."""
    refs = _non_empty_reference_contexts(row.get("reference_contexts"))
    if refs:
        return [r[:REFERENCE_CONTEXT_MAX_CHARS] for r in refs]
    return _non_empty_contexts(row.get("contexts"))


def _scorable_answer(row: dict) -> bool:
    answer = (row.get("answer") or "").strip()
    return bool(answer) and not answer.startswith("ERROR:")


def prepare_eval_row(row: dict, test_case: dict) -> dict:
    """Align metadata, backfill contexts from raw_response, attach reference_contexts."""
    out = align_result_row(dict(row), test_case)
    ans = (out.get("answer") or "").strip()
    if (not ans or ans.startswith("ERROR:")) and isinstance(out.get("raw_response"), dict):
        ra = (out["raw_response"].get("answer") or "").strip()
        if ra:
            out["answer"] = ra

    if not _non_empty_contexts(out.get("contexts")) and isinstance(
        out.get("raw_response"), dict
    ):
        norm = parse_chat_response(question=out.get("question", ""), raw=out["raw_response"])
        if norm.get("contexts"):
            out["contexts"] = norm["contexts"]

    out["contexts"] = _non_empty_contexts(out.get("contexts"))
    refs = resolve_reference_contexts(test_case, out)
    if refs:
        out["reference_contexts"] = refs
    else:
        out.pop("reference_contexts", None)
    return out


def rows_with_contexts(rows: list[dict]) -> int:
    return sum(1 for r in rows if _non_empty_contexts(r.get("contexts")))


def rows_with_hallucination_context(rows: list[dict]) -> int:
    return sum(1 for r in rows if _hallucination_context(r))


def build_ragas_dataset_dict(rows: list[dict]) -> dict[str, list]:
    """HuggingFace Dataset columns (RAGAs v1 names — auto-mapped to v2 internally)."""
    data: dict[str, list] = {
        "question": [r["question"] for r in rows],
        "answer": [r["answer"] for r in rows],
        "contexts": [r.get("contexts") or [] for r in rows],
        "ground_truth": [r.get("ground_truth") or "" for r in rows],
    }
    if any(r.get("reference_contexts") for r in rows):
        data["reference_contexts"] = [
            r.get("reference_contexts") or [] for r in rows
        ]
    return data


def select_ragas_metrics(rows: list[dict]) -> tuple[list[Any], list[str]]:
    """
    Return (metric objects, active metric names) for YourAI legal RAG QA.

    Tier 1 — always: answer quality vs ground_truth.
    Tier 2 — when contexts from source_attribution exist: RAG grounding + retrieval.
    """
    from ragas.metrics import (
        answer_correctness,
        answer_relevancy,
        answer_similarity,
        context_precision,
        context_recall,
        faithfulness,
    )

    metrics: list[Any] = [
        answer_relevancy,
        answer_correctness,
        answer_similarity,
    ]
    names = list(TIER1_METRIC_NAMES)

    if any(_non_empty_contexts(r.get("contexts")) for r in rows):
        metrics.extend([faithfulness, context_precision, context_recall])
        names.extend(TIER2_METRIC_NAMES)

    return metrics, names


def select_deepeval_metric_names(rows: list[dict]) -> list[str]:
    """DeepEval metrics that apply to this results batch (non-overlapping with RAGAs)."""
    names = list(DEEPEVAL_TIER1_METRIC_NAMES)
    if any(_hallucination_context(r) for r in rows):
        names.append("hallucination")
    if any(_non_empty_contexts(r.get("contexts")) for r in rows):
        names.append("contextual_relevancy")
    return names


def combine_active_metric_names(
    ragas_names: list[str],
    deepeval_names: list[str],
) -> list[str]:
    """Stable report column order: RAGAs first, then DeepEval add-ons."""
    out = list(ragas_names)
    for name in deepeval_names:
        if name not in out:
            out.append(name)
    return out


def build_deepeval_judge_model(judge_provider: str) -> Any:
    """Instantiate DeepEval judge LLM aligned with JUDGE_PROVIDER / llm.config."""
    from llm import config as llm_config

    if judge_provider == "gemini":
        from deepeval.models import GeminiModel

        return GeminiModel(
            model=llm_config.GEMINI_MODEL,
            api_key=llm_config.GEMINI_API_KEY,
            temperature=0.2,
        )
    if judge_provider == "openrouter":
        from deepeval.models import OpenRouterModel

        return OpenRouterModel(
            model=llm_config.OPENROUTER_MODEL,
            api_key=llm_config.OPENROUTER_API_KEY,
            base_url=llm_config.OPENROUTER_BASE_URL.rstrip("/"),
            temperature=0.2,
            generation_kwargs={"max_tokens": llm_config.OPENROUTER_MAX_TOKENS},
        )
    from deepeval.models import GPTModel

    return GPTModel(
        model=llm_config.OPENAI_MODEL,
        api_key=llm_config.OPENAI_API_KEY,
        temperature=0.2,
    )


def _create_deepeval_metric(name: str, judge: Any, threshold: float) -> Any:
    from deepeval.metrics import (
        ContextualRelevancyMetric,
        HallucinationMetric,
        NonAdviceMetric,
    )

    common = {
        "model": judge,
        "include_reason": False,
        "async_mode": False,
        "verbose_mode": False,
    }
    if name == "non_advice":
        return NonAdviceMetric(
            advice_types=["legal"],
            threshold=threshold,
            **common,
        )
    if name == "hallucination":
        # Hallucination threshold is a maximum (0 = no contradictions).
        return HallucinationMetric(threshold=threshold, **common)
    if name == "contextual_relevancy":
        return ContextualRelevancyMetric(threshold=threshold, **common)
    raise ValueError(f"Unknown DeepEval metric: {name}")


def build_deepeval_test_case(row: dict, metric_name: str) -> Any:
    from deepeval.test_case import LLMTestCase

    question = (row.get("question") or "").strip()
    answer = (row.get("answer") or "").strip()
    kwargs: dict[str, Any] = {
        "input": question,
        "actual_output": answer,
    }
    if metric_name == "hallucination":
        kwargs["context"] = _hallucination_context(row)
    elif metric_name == "contextual_relevancy":
        kwargs["retrieval_context"] = _non_empty_contexts(row.get("contexts"))
    return LLMTestCase(**kwargs)


def _deepeval_row_applicable(row: dict, metric_name: str) -> bool:
    if not _scorable_answer(row):
        return False
    if metric_name == "non_advice":
        return True
    if metric_name == "hallucination":
        return bool(_hallucination_context(row))
    if metric_name == "contextual_relevancy":
        return bool(_non_empty_contexts(row.get("contexts")))
    return False


def run_deepeval_scores(
    rows: list[dict],
    *,
    judge_provider: str,
    threshold: float = 0.7,
    metric_names: list[str] | None = None,
) -> list[dict[str, float | None]]:
    """
    Score each row with DeepEval metrics. Returns one dict per row (metric -> score).

    Skips API calls when a metric does not apply to a given row (score stays None).
    """
    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    os.environ.setdefault("CONFIDENT_OPEN_BROWSER", "NO")

    active = metric_names or select_deepeval_metric_names(rows)
    if not active:
        return [{name: None for name in DEEPEVAL_METRIC_NAMES} for _ in rows]

    judge = build_deepeval_judge_model(judge_provider)
    metrics = {name: _create_deepeval_metric(name, judge, threshold) for name in active}

    results: list[dict[str, float | None]] = [
        {name: None for name in DEEPEVAL_METRIC_NAMES} for _ in rows
    ]

    for name, metric in metrics.items():
        for idx, row in enumerate(rows):
            if not _deepeval_row_applicable(row, name):
                continue
            test_case = build_deepeval_test_case(row, name)
            try:
                metric.measure(test_case)
                score = getattr(metric, "score", None)
                results[idx][name] = float(score) if is_finite_score(score) else None
            except Exception as exc:
                results[idx][name] = None
                row_id = row.get("id", idx)
                print(f"  ⚠ DeepEval {name} failed for {row_id}: {exc}")

    return results


def merge_deepeval_scores_into_df(
    df: Any,
    score_rows: list[dict[str, float | None]],
    *,
    active_metric_names: list[str] | None = None,
) -> Any:
    """Add DeepEval score columns to the RAGAs results DataFrame."""
    names = active_metric_names or [
        name
        for name in DEEPEVAL_METRIC_NAMES
        if any(is_finite_score(row.get(name)) for row in score_rows)
    ]
    if not names:
        names = list(DEEPEVAL_TIER1_METRIC_NAMES)
    for name in names:
        df[name] = [row.get(name) for row in score_rows]
    return df


def labels_for_columns(column_names: list[str]) -> dict[str, str]:
    return {
        name: METRIC_LABELS[name]
        for name in column_names
        if name in METRIC_LABELS
    }


def metric_names_from_df(columns, df: Any | None = None) -> list[str]:
    """Report only project-scoped metrics present with usable scores."""
    names: list[str] = []
    for name in PROJECT_METRIC_NAMES:
        if name not in columns:
            continue
        if name in DEEPEVAL_METRIC_NAMES and df is not None:
            series = df[name]
            if not any(is_finite_score(v) for v in series):
                continue
        names.append(name)
    return names
