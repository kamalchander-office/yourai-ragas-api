# QA run outputs

All pipeline outputs are written here (not in the parent `qa/` folder).

| File | Produced by |
|------|-------------|
| `results.json` | `client.py` — API answers |
| `scores.csv` | `run_eval.py` — RAGAs + DeepEval scores |
| `report.html` | `run_eval.py` — formatted report |
| `intent_eval_issues.csv` | `run_intent_eval.py` |
| `intent_eval_summary.json` | `run_intent_eval.py` |
| `test_cases_ineligible.json` | `generate_cases.py` — skipped intent/doc rows |
| `corpus_cache/` | vault bootstrap — downloaded document text |

Working inputs stay in `qa/`:

- `qa/session.json` — PWA bootstrap (conversation, vault attach, intents)
- `qa/test_cases.json` — test questions and ground truth

Override this folder: set `QA_RESULTS_DIR` in `.env` or the environment.
