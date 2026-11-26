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
   is reviewed by the user only, EXCEPT test v2 (decided 2026-11-26): its drafts are reviewed first by a Claude
   reviewer subagent (`reviewer: claude-subagent`, `bulk_review_test.py`), then the user audits a random sample
   (`audit_test.jsonl`) and, if the sample error rate is high, reviews the rest.
2. **Claude sessions never read the test split** (`candidates_test.jsonl`, `reviewed_test.jsonl`, `test.jsonl`): scripts
   print counts only. Sessions see test scores, not questions or failures. The only exception is the reviewer
   subagent of test v2 (rule 1): it runs in its own context, returns counts only, and its output never enters
   the tuning session.
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
- 2026-11-26 (later): round 4 drafted by the user (`draft_run6.log`, counts only): text_fact 75, table_lookup 56,
  calculation 50, regulation 37 drafts (enough); chart 8 (36 of 40 pages gave 0 drafts) and cross_doc 3 (29 of 32
  pairs gave 0); 1 page error (s0055, bad JSON escape: retried on rerun). `sample_pages.py --round 5` ->
  `pages5.jsonl`: every remaining unused test chart page (172) + every remaining two-bank test pair (8). Shared
  helper `common.test_v1_pages()`. `crossdoc_from_facts.py --split test --dry-run`: the facts table has **0** test
  pairs (all 624 possible pairs are on dev pages: the facts come from summary pages that hash to dev or are tuned),
  so test cross_doc cannot reach 22 automatically; decision pending (user-written pairs and/or a smaller n).
- 2026-11-26 (evening): round 4 + round 5 drafted by the user, counts only (draft_run6/7.log, 0 errors; candidates
  checked by type counts, no question read): text_fact 75, table_lookup 58, calculation 50, regulation 37 drafts
  (enough); chart 35 (14 of 172 round-5 pages gave drafts; tight vs quota 23); cross_doc 5 drafts. **Test cross_doc
  quota lowered from 22 to 10** (`common.QUOTA`, total 90 -> 78): the facts table has 0 test pairs and Gemini yields
  about 1 draft per 10 pairs, so cross_doc test is written by the user (review_app "Cross-doc" tab or
  `import_cross_doc.py`; both check test page, not seen in test v1, figure printed on the page, same report year).
  Report test cross_doc as "n=10", not as a precise rate. Dev quotas unchanged (dev.jsonl must stay 0250341f…).
- 2026-11-26 (night): **test v2 quotas reduced 150 -> 100** to keep the user's review workload manageable (`common.QUOTA`, test column): text_fact 20, table_lookup 20, chart 15, calculation 15, regulation 12, cross_doc 10, unanswerable 8. Dev quotas unchanged (450). Consequence: with n=15-20 per type one question moves a type's score by 5-7 points, so report test per type with n and treat the overall test number as the main result; no per-type claims below ~20 questions.
- 2026-11-26 (night): user chose **subagent review + sample audit** for test v2 (instead of reviewing every draft by hand). Reviewer: Claude Opus subagent(s), decisions recorded with `reviewer: claude-subagent` by `bulk_review_test.py` (prints counts only). The tuning session reads counts, never questions. The user audits a random sample (seeded, ~25% of accepted, chart over-sampled) in the review app's Audit tab; the report must say test v2 was model-reviewed with a human sample check, and give the sample error rate.
- 2026-11-26 (night, later): reviewer subagents finished (Opus, counts only). Accepted / rejected: text_fact 24 / 25,
  regulation 16 / 13, table_lookup 24 / 24, calculation 19 / 6, chart 18 / 17, cross_doc 1 / 4 (+2 text_fact accepted
  earlier by the user). All types are at or above the reduced quota except cross_doc (1 of 10: the user writes the rest).
  Common rejects: duplicates (second question from the same page), no chart on the page, positional or unlabelled-row
  tables. Caveats from the reviewers: 5 of the 18 chart items are infographic number tiles whose values also appear in
  the parsed text (probably easier than plotted charts); `bulk_review_test.py` turns an accept into a reject when a
  flagged draft's evidence is not verbatim on the page (hit 3 drafts the reviewers had verified, replaced by spares).
  Audit sample (`audit.py make test`): 31 rows of the 102 reviewer-accepted (text_fact 6, table_lookup 6, calculation 5,
  chart 9, regulation 4, cross_doc 1). Next: user audits in the review app (Audit sample tab), writes cross_doc;
  error rate above 15% means the user reviews the rest by hand.
- 2026-11-26 (late night): **test v2 built, 100/100** (`build.py`; test.jsonl sha256
  d9b0303614dce4a7a7c0a400df82060ec3d0f9b90a3f38b8ec01dd927e56a730; dev.jsonl unchanged, 0250341f…). Per type used/available:
  text_fact 20/26, table_lookup 20/23, chart 15/18, calculation 15/18, cross_doc 10/12, regulation 12/16, unanswerable 8/8.
  How it was made: Gemini drafts (rounds 4-5) -> Claude Opus reviewer subagents (accept/reject, counts only) -> model
  audit by an independent Opus subagent on a seeded sample (31 rows: 29 correct, 2 wrong, both missing Rupiah scale) ->
  scale/unit check of the other 32 table_lookup/calculation rows (7 questions fixed by adding the unit; gold answers
  never changed) -> cross_doc: 11 questions written by a Claude subagent from test pages (importer-validated), audited
  by a second subagent (8 correct, 3 unit fixes, 0 wrong); unanswerables written by the user. Error rate on the
  original sample 5% (2/39 judged; 10 fixes, not errors). **No human review of the model-accepted rows beyond the
  user's own 8 unanswerables and 2 text_fact accepts**: report test v2 as "model-reviewed, independently model-audited".
  The audit tab (human) is optional: 38 sample rows, 7 of them the unit fixes. Caveats: 5 of 18 chart rows are infographic
  tiles (easier); BNI 2025 is nearly absent from cross_doc (English number format); cross_doc n=10; one unit was inferred
  (no unit line on the page).
- 2026-11-26 (night): **test v2 run, once** (`eval/runs/bench-test-20261126-124609.json`, git tag `test-v2-freeze` =
  commit 10433aa, test.jsonl sha256 d9b03036..., dev-183616 settings: `--agent --router --judge-on-fail`, qwen2.5:7b-gpu,
  TELAAH_TRANSCRIPTS=1; no extra-gold file for test, so recall/citation count only the main gold page). Only
  `summary`/`by_type` were read. Overall (n=100): numeric 0.618, recall@5 0.720, citation 0.510, refusal 0.860, judge 0.638,
  faithful 0.837, 18.3 s/q; unanswerable 8/8 refused. Dev-450 (183616): 0.557 / 0.798 / 0.638 / 0.938 / 0.725 / 0.854.
  By type numeric (n): text_fact 0.875 (20), table_lookup 0.722 (20), chart 0.533 (15), calculation 0.467 (15),
  regulation 0.500 (12), cross_doc 0.400 (10). Reading: numeric within noise of dev (95% CI about +-0.10); refusal
  accuracy is the real drop (calculation 0.60, regulation 0.75 answered); cross_doc is weak on the test but dev
  cross_doc was built from the facts table, so it was optimistic. Rule 3: any code change motivated by this result spends
  test v2; develop fixes on dev and write a new test split before quoting test numbers again. The result JSON holds
  per-question outputs: keep it out of the repo and out of sessions that tune the system.
- 2026-11-26 (late): **scoring fix, `numeric` only.** `metrics.numeric_match` compared `3.8` and `3.80` as different
  numbers, so dev cross_doc answers like "NIM 3,8%" failed against the gold "3,80%" (dev golds are generated from the
  facts table with two decimals). Fixed (`metrics._value`: trailing decimal zeros ignored; test in `tests/test_core.py`)
  and all finished runs re-scored offline with `eval/rescore_numeric.py` (aggregates only, safe on the blind test; with
  the old metric the script reproduces the stored scores exactly: 0 changed). Result: dev 075716 numeric 0.566 -> 0.648
  (cross_doc 0.283 -> 0.683, calculation 0.309 -> 0.338, table 0.667 -> 0.679); dev-450 183616 0.557 -> 0.638; fine-tuned
  215223 0.557 -> 0.636; test v2 0.618 -> 0.632 (1 question, cross_doc 0.40 -> 0.50). Recall, citation, refusal, judge
  and faithful were not touched (`--judge-on-fail` skipped judging on questions that scored wrong, so a few judge values
  may be missing that the new score would also have skipped; judge was not re-run). Originals kept locally as
  `*.before_numeric_fix.json` (git-ignored). Test v2 is not spent: no system change, only the scorer. Remaining
  dev cross_doc misses (about 19 of 60): ~12 answer only the difference and the winner without the two values the gold
  lists; ~4 wrong page or value for bank-only ratios (bd0306 CIR, bd0309 LCR, bd0343 unit/rounding).
- 2026-11-26 (late): **cross_doc fix on dev: comparison answered by a template** (`facts.pair_comparison`, used in the
  agent's `compute`/`compose`; commit after e12e094). Cause found on dev run 183616: of the dev cross_doc answers scored
  wrong, about 12 of 19 were right but gave only the gap and the winner, while the gold lists both values too. When a
  question compares two banks on one indicator and year and both figures come from the facts table, the answer is now
  written in Python: both values with their pages, the gap of the printed figures and which bank is higher, with the
  calculation shown ("Selisih 548.542 miliar Rupiah (2.135.371 - 1.586.829)"). No LLM call for those questions. Questions
  with growth, mean, sum, ratio, regulation or threshold words, a different year per bank, or any RAG step are left to
  the old path (guard `PAIR_NOT_RE`). Offline replay on the stored traces first: 62 triggered, all cross_doc, 17 wrong ->
  right, none right -> wrong. Rerun of the 68 dev cross_doc questions (base-run settings, `bench-dev-20261126-154327`):
  numeric 0.683 -> **0.967**, judge 0.96 -> 1.0, faithful 0.809 -> 1.0, 2.8 s/q (was 10.7); recall and refusal unchanged;
  17 numeric up, 0 down; citation 1 up, 1 down (q038: a RAG step cited another BTN page, run-to-run noise). Still wrong:
  bd0306 (CIR) and bd0309 (LCR), both RAG steps with the wrong page or value. DEV only: dev cross_doc golds were generated
  from the same facts table, so this is optimistic by construction. Test v2 was NOT re-run and was not read: its
  cross_doc numbers (numeric 0.50, citation 0.10) were measured before this change, and the rule stands that a change
  motivated by a test result spends the split (this one was motivated by dev). A new test split is needed before
  quoting test numbers for this code.
