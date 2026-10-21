# Telaah benchmark v1 (600 questions)

Goal: 600 hand-checked Indonesian document questions with gold answers and gold pages: 450 dev (includes the 50
seed questions) + 150 test. The 60 dev agent tasks and held-out sets #1/#2 stay separate (`HELDOUT.md`).

## Composition

| Type | Total | Dev (seed) | Test | How it is made |
| --- | --- | --- | --- | --- |
| text_fact | 120 | 90 (12) | 30 | Gemini draft from one narrative page |
| table_lookup | 120 | 90 (15) | 30 | Gemini draft from one table page |
| chart | 90 | 67 (5) | 23 | Gemini draft from one page IMAGE with a chart |
| calculation | 90 | 68 | 22 | Gemini picks two or more figures on one page; Python computes the gold |
| cross_doc | 90 | 68 (8) | 22 | Gemini draft from two pages of two banks (or one bank, two reports) |
| regulation | 60 | 45 | 15 | Gemini draft from one OJK/BI regulation page |
| unanswerable | 30 | 22 (10) | 8 | Written by the user (models draft these badly) |

New questions to check: 550. Drafts are over-produced (~1.4x) because rejects are expected.

## Pipeline

    .venv/Scripts/python eval/bench/sample_pages.py      # pages.jsonl: sampled pages, split fixed per page
    .venv/Scripts/python eval/bench/draft.py --limit 50   # Gemini drafts -> candidates_{dev,test}.jsonl
    .venv/Scripts/python eval/bench/review_app.py         # local Gradio app: accept / fix / reject
    .venv/Scripts/python eval/bench/build.py              # dev.jsonl + test.jsonl, quotas, hashes
    .venv/Scripts/telaah eval --router --file eval/bench/dev.jsonl   # per-type scores in eval/runs/bench-dev-*.json

1. **Sample** (`sample_pages.py`, seed 20261021): pages by kind (narrative, table, chart candidate, regulation,
   cross-bank pair) from the 2024/2025 annual reports and the regulations. bca_2024 is left out (only 12 pages
   parsed, so the system cannot answer from it). The split is fixed per **page** before any draft exists:
   `sha256(seed:doc:page) < 25%` -> test. A cross_doc pair goes to test only if both pages do. Pages that are gold
   pages of the seed questions, the agent tasks or held-out sets #1/#2 are never test pages (the system was tuned
   on them).
2. **Draft** (`draft.py`): `DRAFT_MODEL` (default `gemini-3.5-flash`), never the model under test (7B qwen) nor the
   chart reader (`VISION_MODEL`, gemini-3.5-flash-lite). The drafter gets the page image and its parsed text and
   returns JSON: question, answer, verbatim evidence, figures for calculations. Automatic filter: the evidence must
   occur in the page text (charts: skipped, image only), questions must name the bank/regulation and year.
   Resumable; throttled to the free tier (15 req/min, 500 req/day).
3. **Review** (`review_app.py`, the user only): page image(s) beside the draft; fix wording, answer, pages;
   calculation golds are recomputed from the checked figures. Reject ambiguous, trivial or not self-contained
   questions. Other pages that print the same answer are suggested as extra gold pages.
4. **Build** (`build.py`; calculation golds from `gold.py`, Indonesian format, 2 decimals): fills the quotas per type and split (deterministic order), writes `eval/bench/dev.jsonl`
   and `eval/bench/test.jsonl` in the seed schema, prints counts and sha256.

Row schema = `seed_questions.jsonl` plus `split`, `source` (`seed`, `draft+review`, `user`), and for calculation
and cross_doc rows `extra: {figures, op}` (the checked figures the gold was computed from).

## Rules (keep the numbers honest)

1. Every gold answer and page is checked by the user. Claude writes the tools, never verifies golds.
2. **Claude never reads the test split** (`candidates_test.jsonl`, `reviewed_test.jsonl`, `test.jsonl`): scripts
   print counts only. Sessions see test scores, not questions or failures.
3. Test runs only at milestones, every run reported. If a test result motivates a change, the split is spent:
   record it here and write fresh test questions before quoting test numbers again.
4. Dev may be used for tuning; report dev and test side by side.
5. Frozen files get their sha256 below; changing them after freezing is a new version (v1.1).

## Status
- 2026-10-21: design + tools. Gemini key in `.env` is invalid (400 API_KEY_INVALID): new key needed to draft.
