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
2. **Draft** (`draft.py`): `DRAFT_MODEL` (default `gemini-3.5-flash-lite`: gemini-3.5-flash is 20 requests/day on the free
   tier), never the model under test (7B qwen). It shares a model with the chart reader (transcribing only); every draft is checked by the user. The drafter gets the page image and its parsed text and
   returns JSON: question, answer, verbatim evidence, figures for calculations. Automatic filter: the evidence must
   occur in the page text (charts: skipped, image only), questions must name the bank/regulation and year.
   Resumable; throttled to the free tier (15 req/min, 500 req/day on flash-lite).
3. **Review** (`review_app.py`, the user only): page image(s) beside the draft; fix wording, answer, pages;
   calculation golds are recomputed from the checked figures. Reject ambiguous, trivial or not self-contained
   questions. Other pages that print the same answer are suggested as extra gold pages.
4. **Build** (`build.py`; calculation golds from `gold.py`, Indonesian format, 2 decimals): fills the quotas per type and split (deterministic order), writes `eval/bench/dev.jsonl`
   and `eval/bench/test.jsonl` in the seed schema, prints counts and sha256.

Row schema = `seed_questions.jsonl` plus `split`, `source` (`seed`, `draft+review`, `user`), and for calculation
and cross_doc rows `extra: {figures, op}` (the checked figures the gold was computed from).

## Rules (keep the numbers honest)

1. Every gold answer and page is checked by a human or, for DEV only, by Claude when the user delegates it (decided
   2026-10-21: `reviewer: claude` in `reviewed_dev.jsonl`, via `bulk_review.py`; chart golds checked against the page
   image, text golds against the parsed page, ambiguous/positional/unit-unclear questions rejected). The TEST split
   is reviewed by the user only.
2. **Claude never reads the test split** (`candidates_test.jsonl`, `reviewed_test.jsonl`, `test.jsonl`): scripts
   print counts only. Sessions see test scores, not questions or failures.
3. Test runs only at milestones, every run reported. If a test result motivates a change, the split is spent:
   record it here and write fresh test questions before quoting test numbers again.
4. Dev may be used for tuning; report dev and test side by side.
5. Frozen files get their sha256 below; changing them after freezing is a new version (v1.1).

## Status
- 2026-10-21: design + tools. Gemini key in `.env` is invalid (400 API_KEY_INVALID): new key needed to draft.
- 2026-10-21: round 1 drafted (490 pages). Claude reviewed the dev candidates: 260/450 dev questions so far (seed 50 +
  210 accepted of 337 drafts; common rejects: positional or unit-unclear table questions, long answers, evidence
  missing from the parsed text, chart answer read from the wrong series). Short: table_lookup 34, chart 36,
  calculation 41, cross_doc 57, regulation 10, unanswerable 12 (user). Difference golds are absolute values.
  cross_doc drafts were mostly rejected (units/periods not comparable): round 2 needs a different method.
- 2026-10-21 (later): dev unanswerables drafted by Claude (12, `source: claude`; absence checked by regex over the
  corpus: future periods, non-existent POJK/PADG numbers, banks and provinces/districts the reports do not cover).
  cross_doc dev built from the facts table (`crossdoc_from_facts.py`): two banks, one indicator, one year, one report
  year, gold computed in Python, row label checked on the page; 76 candidates, 68 accepted. Caveat: these use the
  same table the facts route reads, on pages the extractor was tuned on, so dev cross_doc is optimistic. The test
  split got NO such pairs (their pages are dev or tuned by the page-hash rule): test cross_doc (22) must come from
  Gemini drafts on test pages (round 2) and/or the user.
  Dev now 329/450: text_fact 90/90, cross_doc 68/68, unanswerable 22/22; short: table_lookup 34, chart 36,
  calculation 41, regulation 10.
- 2026-11-16: TEST split reviewed by Claude at the user's request (Claude in Chrome, review_app.py), contrary to rules 1-2.
  All 117 decisions in `reviewed_test.jsonl` so far are Claude's (text_fact 32/30, table_lookup 30/30, chart 23/23,
  regulation 15/15; calculation and cross_doc not started). Claude read test questions, golds and pages, so test v1 is
  no longer unseen by Claude sessions: either re-review these 117 by the user / write fresh test questions before quoting
  test numbers as held-out, or report test v1 with this caveat. `review_app.py` got a "Show type" filter (backup:
  `review_app.py.bak_pre_filter`).
- 2026-11-16: dev builds to 439/450 (`build.py`, dev.jsonl sha256 69e220ec…, unchanged): text_fact 90/90,
  calculation 68/68, cross_doc 68/68, regulation 45/45, unanswerable 22/22; short table_lookup 84/90 and chart 62/67,
  with no dev candidates left. `sample_pages.py --round 3` added (dev only, never reusing round 1/2 pages):
  `pages3.jsonl` = 30 table_lookup + 58 chart dev pages, to be drafted with `draft.py --pages pages3.jsonl`.
- 2026-11-16 (later): round 3 drafted by the user (`draft.py --pages pages3.jsonl`: 46 table_lookup, 20 chart dev
  drafts). Claude reviewed 14 (`bulk_review.py`, decisions in `bench/_decisions_r3.json`; tables checked against the
  parsed page, charts against page images rendered at 170 dpi), all accepted; the other 52 left undecided.
  Dev complete: 450/450 (table_lookup 90/90, chart 67/67). dev.jsonl sha256 0250341f91e95052dde16886475cba3c8e953649fb90fa8d0211f536a43898f2
- 2026-11-26: **test v1 retired** (Claude-seen, see 2026-11-16). `candidates_test.jsonl`, `reviewed_test.jsonl`,
  `test.jsonl` and the undo backup moved unopened to `eval/bench/archive_test_v1/` (git-ignored); never quote test v1
  numbers. `user_test.jsonl` (written by the user, never seen by Claude) is kept for test v2.
  **Test v2**: `sample_pages.py --round 4` -> `pages4.jsonl`, 209 rows, TEST pages only: text_fact 40, table_lookup 40,
  calculation 35, chart 40, regulation 22, cross_doc 32 pairs (two banks, same report year). Excluded: every page of
  rounds 1-3 (1183) and every page referenced anywhere in the archived test v1 files (151; 19 not already in rounds 1-3),
  union 1202. The script prints counts only. Next: user drafts (`draft.py --pages pages4.jsonl`, ~209 requests),
  reviews in `review_app.py` (Test, user only), adds the 8 unanswerables; `build.py`; dev.jsonl must stay 0250341f….
  One test run at a frozen git tag with the dev-run-183616 settings; Claude reads aggregate scores only.
