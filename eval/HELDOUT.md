# Held-out agent tasks (frozen 2026-10-18)

> **Set #1 is SPENT (2026-10-18 16:45).** Its run-1 failures motivated two fixes (unknown-bank refusal, mean over
> years). Its run-1 score (0.925) stays the honest held-out number for commit b61f6e4; any later run on this set is
> contaminated. Build held-out set #2 before quoting held-out numbers again.

`eval/heldout_tasks.jsonl`: 40 tasks (ranking 6, trend 6, multi_trend 6, compute 10, regulation 6,
unanswerable 6), built by `eval/build_heldout_tasks.py` BEFORE any system run on them.

- sha256 heldout_tasks.jsonl: `de930b82de0afc5a9b6cbfb6aeef035d5fbcb6647cf4bbe09b714833bf077f9b`
- sha256 build_heldout_tasks.py: `c9aa8bf0fedbee450ad642cd42ecf071b113df2929b598c4e923a0027f491725`

## What is new vs the 60 dev tasks (`agent_tasks.jsonl`)
- Wordings written fresh (descending order, "kapan puncaknya", "naik atau turun", "berapa kali lipat",
  "porsi ... terhadap", "s.d.", en dash ranges, three source phrasings).
- Indicators the dev tasks never use: ROA, ROE, NPL net, total equity; year pairs 2022/2025, 2021/2024, 2023/2025;
  single years 2023/2024; a mean over five years; regulation threshold KPMM Peringkat 1 = 8%.
- Gold: same row parser as the dev builder (hand-written page/row spec, regex-checked), not the facts table.
  Ambiguous rows left out (BNI ROE: two rows; BNI equity: 2025 table with two 2024 columns). Ties and corpus
  presence of unanswerable terms are asserted.

## Rules
1. Never tune on these tasks or their failures. Fixes come from the dev tasks or the seed questions.
2. Run only at milestones: `python eval/run_agent_tasks.py --mode router --tasks heldout_tasks.jsonl`
   (files `eval/runs/tasks-heldout-*.json`). Report every run, including bad ones.
3. Failures may be classified in the notes, but if a held-out result motivates a change, the set is spent:
   mark it here, and build a new held-out set before quoting held-out numbers again.
4. Known bias: written by the same author (Claude) who built the system, after seeing the dev failures, so it is
   easier than truly external questions.

## Runs
- 2026-10-18 16:37, commit b61f6e4+bfe0fa9, 7B router (`eval/runs/tasks-heldout-router-20261018-163737.json`):
  **0.925 (37/40)**, 10.7 s/task. ranking 6/6, trend 6/6, multi_trend 6/6, compute 9/10, regulation 5/6,
  unanswerable 5/6. Failures (classified, NOT fixed under rule 1):
  - h035 unanswerable: "NPL gross Allo Bank 2025 vs BRI" answered with BRI's NPL only. The facts parser ignores
    an entity it does not know (same family as the t060 sub-scope bug). Serious: a confident answer to an
    unanswerable question.
  - h025 compute: mean over YEARS of one bank; `facts.derive` only averages across banks, the 7B averaged and
    rounded wrong (6,74 vs 6,76).
  - h033 regulation: KPMM Insentif threshold not found by any fallback, refused (dev t050, same threshold, passed).

---

# Held-out set #2 (frozen 2026-10-18)

`eval/heldout2_tasks.jsonl`: 40 tasks (restatement 6, trend 4, multi_trend 4, ranking 4, compute 10, regulation 6,
unanswerable 6), built by `eval/build_heldout2_tasks.py` before any system run on them. Same rules as set #1.

- sha256 heldout2_tasks.jsonl: `ece6ae58bf2eb271d30604757b798a1878389c4108a4f4e0ed816ece0844fcec`
- sha256 build_heldout2_tasks.py: `4afa40b4225d6b5899208a95c2bc17feef4ac71388526381801eba9ef3869d8b`

## What is new
- Source: the **2024 reports** (every task except restatement names "Laporan Tahunan 2024"). They carry 2020
  figures, which the 2025 reports do not have, so a 2020 question can only be answered from the 2024 report.
- **Restatement** tasks: the same figure in the 2024 and the 2025 report. Four real restatements (BRI total assets
  2023 and 2024, BRI NIM 2024: 6,47% vs 6,75%, BTN KPMM 2023: 20,07 vs 20,16) and two unchanged figures (their gold
  has no "0", so a stray zero cannot pass). BRI profit 2024 is left out: it is seed question q039.
- New operations: CAGR, a two-indicator ratio from one report (profit / assets 2020), "berapa kali lipat" over 2020-2024.
- Gold numbers all in Indonesian notation (the scorer would misread "1,086,664").
- Left out: BCA 2024 (its parsed file has no summary tables). Kept: BTN 2024 profit, whose table header merges
  "2024 2023" into one cell (the gold parser reads the row by position).

## Known bias
Written by the same author (Claude) who built the system, knowing its routing rules and its known misses
(t046 two-indicator ratios; restated figures). Questions were written as an analyst would ask them, not to pass or
to break those rules, but that knowledge cannot be unlearned.

## Runs (set #2)
- 2026-10-18 17:20, commit ea0e29a, 7B router (`eval/runs/tasks-heldout-router-20261018-172027.json`):
  **0.625 (25/40)**, 12.5 s/task. unanswerable 6/6, regulation 5/6, trend 3/4, restatement 4/6, ranking 2/4,
  compute 4/10, multi_trend 1/4. Failures (classified, NOT fixed under rule 1):
  - ~12 of 15: BRI 2024 report labels its 2020 column "2020 *)"; `facts.YEAR_CELL` rejects the ")", so every BRI
    2020 figure is missing from the table. Those tasks fall back to the 7B-planned agent, which cites wrong rows:
    BRI 2020 profit "(27,47)" from a subsidiary table on bri_2024 p30 (not caught by the segment filter: no
    "entitas anak" heading), ROA 1,59% / NPL 2,19% (p198) and KPMM 23,89% (p197), likely another basis.
  - k001: both report figures right, difference not computed (two named reports -> no sheet). k002 refused.
  - k012: one missing (bank, year) fact disables the whole sheet, so the 7B plans and misses BTN/BNI 2020.
  Conclusion: set #1 (0.925) overstated generalization; it stayed inside the 2025 reports.
