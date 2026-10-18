# Held-out agent tasks (frozen 2026-10-18)

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
