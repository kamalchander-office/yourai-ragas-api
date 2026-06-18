"""Tests for RAGAs + DeepEval metric selection from YourAI response fields."""

from __future__ import annotations

from qa.eval_metrics import (
    DEEPEVAL_METRIC_NAMES,
    PROJECT_METRIC_NAMES,
    RAGAS_METRIC_NAMES,
    build_deepeval_test_case,
    build_ragas_dataset_dict,
    combine_active_metric_names,
    metric_passes,
    prepare_eval_row,
    resolve_reference_contexts,
    select_deepeval_metric_names,
    select_ragas_metrics,
    metric_names_from_df,
)


def test_ragas_scope_is_six_metrics():
    assert len(RAGAS_METRIC_NAMES) == 6


def test_project_metric_names_include_deepeval_addons():
    assert len(PROJECT_METRIC_NAMES) == len(RAGAS_METRIC_NAMES) + len(DEEPEVAL_METRIC_NAMES)
    assert "non_advice" in PROJECT_METRIC_NAMES
    assert "hallucination" in PROJECT_METRIC_NAMES
    assert "contextual_relevancy" in PROJECT_METRIC_NAMES


def test_select_tier1_only_without_contexts():
    rows = [
        {
            "id": "TC-1",
            "question": "Q?",
            "answer": "A.",
            "ground_truth": "GT.",
            "contexts": [],
        }
    ]
    metrics, names = select_ragas_metrics(rows)
    assert names == [
        "answer_relevancy",
        "answer_correctness",
        "answer_similarity",
    ]
    assert len(metrics) == 3


def test_select_deepeval_tier1_only_without_contexts():
    rows = [
        {
            "id": "TC-1",
            "question": "Q?",
            "answer": "A.",
            "contexts": [],
        }
    ]
    assert select_deepeval_metric_names(rows) == ["non_advice"]


def test_select_deepeval_tier2_when_contexts_present():
    rows = [
        {
            "id": "TC-1",
            "question": "Q?",
            "answer": "A.",
            "contexts": ["snippet from source_attribution"],
        }
    ]
    names = select_deepeval_metric_names(rows)
    assert names == ["non_advice", "hallucination", "contextual_relevancy"]


def test_select_tier2_when_contexts_present():
    rows = [
        {
            "id": "TC-1",
            "question": "Q?",
            "answer": "A.",
            "ground_truth": "GT.",
            "contexts": ["snippet from source_attribution"],
        }
    ]
    _, names = select_ragas_metrics(rows)
    assert names == [
        "answer_relevancy",
        "answer_correctness",
        "answer_similarity",
        "faithfulness",
        "context_precision",
        "context_recall",
    ]


def test_combine_active_metric_names_order():
    combined = combine_active_metric_names(
        ["answer_relevancy", "answer_correctness"],
        ["non_advice", "hallucination"],
    )
    assert combined == [
        "answer_relevancy",
        "answer_correctness",
        "non_advice",
        "hallucination",
    ]


def test_metric_passes_hallucination_is_inverted():
    assert metric_passes("hallucination", 0.2, 0.7) is True
    assert metric_passes("hallucination", 0.8, 0.7) is False
    assert metric_passes("non_advice", 0.8, 0.7) is True
    assert metric_passes("non_advice", 0.5, 0.7) is False


def test_build_deepeval_test_case_uses_reference_context_for_hallucination():
    row = {
        "question": "Q?",
        "answer": "A.",
        "contexts": ["retrieved snippet"],
        "reference_contexts": ["gold document chunk"],
    }
    tc = build_deepeval_test_case(row, "hallucination")
    assert tc.context == ["gold document chunk"]


def test_prepare_eval_row_backfills_contexts_from_raw_response():
    row = {
        "id": "TC-1",
        "answer": "",
        "raw_response": {
            "answer": "From API",
            "source_attribution": [
                {"snippet": "Miranda rights include silence.", "document_id": "doc-1"}
            ],
        },
    }
    test_case = {
        "id": "TC-1",
        "question": "Miranda?",
        "ground_truth": "Silence.",
        "case_type": "positive",
    }
    out = prepare_eval_row(row, test_case)
    assert out["answer"] == "From API"
    assert len(out["contexts"]) == 1
    assert "Miranda" in out["contexts"][0]


def test_build_dataset_includes_reference_contexts_when_present():
    rows = [
        {
            "question": "Q",
            "answer": "A",
            "contexts": ["ctx"],
            "ground_truth": "GT",
            "reference_contexts": ["doc chunk"],
        }
    ]
    data = build_ragas_dataset_dict(rows)
    assert "reference_contexts" in data
    assert data["reference_contexts"] == [["doc chunk"]]


def test_resolve_reference_contexts_from_test_case():
    test_case = {
        "reference_contexts": ["  chunk one  ", ""],
        "question": "Q",
    }
    refs = resolve_reference_contexts(test_case)
    assert refs == ["chunk one"]


def test_metric_names_from_df_skips_empty_deepeval_columns():
    import pandas as pd

    df = pd.DataFrame(
        {
            "answer_relevancy": [0.8],
            "non_advice": [0.9],
            "hallucination": [0.1],
            "contextual_relevancy": [None],
        }
    )
    names = metric_names_from_df(df.columns, df)
    assert "contextual_relevancy" not in names
    assert names == ["answer_relevancy", "non_advice", "hallucination"]
