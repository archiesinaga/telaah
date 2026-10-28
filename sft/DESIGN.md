# SFT data design (roadmap week 10)

Status: step 1 done (page pool); steps 2-7 not started. Written 2026-10-28.

## Goal and gate

Fine-tune the model the pipeline already uses (Qwen2.5-7B-Instruct, served as `qwen2.5:7b-gpu`) on the one job it
does on every route: **read 5 retrieved pages, answer with `[doc_id p.N]` citations, or reply `TIDAK DITEMUKAN`**
(`answer.SYSTEM`, used by `ask`, `answer_entity` and the second look).

Why this job: the dev failures are reading failures, not planning ones. Wrong row or wrong year from look-alike tables
(bd0257, step pool losses), wrong refusals with the gold page in context (refusal 0.82 on the 10-28 full run), citing a
neighbouring page (citation 0.56). Arithmetic stays in code (facts sheet, calculator); SFT does not teach it.

Gate (roadmap phase 4): on the full dev set (439), SFT beats base on numeric and citation, refusal does not drop, and
all 22 dev unanswerables stay refused. Measured with the same pipeline, defaults and `JUDGE_MODEL` pinned to the base
model (by default the judge is `LLM_MODEL`, so the fine-tuned model would grade itself). The test split is run once,
at the end, for both models.

## One training example

Exactly what the pipeline sends at run time, so nothing differs between training and use:

- system: `answer.SYSTEM` (verbatim)
- user: `Konteks:\n{build_context(top 5 retrieved pages, question)}\n\nPertanyaan: {question}` (real retrieval with
  the shipped defaults and transcripts ON, real page caps, chart transcriptions where the pipeline adds them)
- assistant: one or two sentences in the question's language, every claim followed by its citation, or exactly
  `TIDAK DITEMUKAN`

## Example mix (target ~2,200 after filtering)

| kind | share | how the context is built | target |
|---|---|---|---|
| answer, gold page in top 5 | 55% | real retrieval | cited answer |
| answer, gold page pushed in | 15% | real retrieval missed it; gold page replaces a random rank 1-5 | cited answer |
| answer with look-alike tables | 10% | real retrieval where another context page has the same row label but another year/entity (found by code) | cited answer from the right page |
| refusal, fact removed | 12% | real retrieval with every page holding the gold figure removed and refilled from ranks 6+ | `TIDAK DITEMUKAN` |
| refusal, out of scope | 8% | question rewritten by template to a year, bank or regulation not in the corpus | `TIDAK DITEMUKAN` |

Question types follow the benchmark shares (text fact, table, chart, regulation, per-bank sub-question). Calculation
and cross-document questions enter only as their per-entity reading steps.

The refusal share (20%) matches the dev unanswerable rate plus wrong-refusal pressure; too many refusals would teach
over-refusing, which is already the larger error.

## Generation (Gemini, never the model under test)

1. **Page pool (code, no LLM).** All corpus pages except: test-split pages (`common.page_split == "test"`, a hash, so
   the test files are never opened), every dev/seed/agent/held-out gold page, extra gold pages, and all 920 pages in
   `pages.jsonl` / `pages2.jsonl`. Sample ~800 pages, spread over documents and types like `sample_pages.py`.
2. **Draft (Gemini flash-lite, 1 call per page, 3 Q&A each).** Reuse `draft.py` (quota memory, resume, JSON mode).
   New prompt: question, short answer in house style with the page's citation, the exact figure or phrase, and the
   line it comes from. Chart pages send the page image as `draft.py` does.
3. **Context (code, local).** Run `retrieve()` on each question, build the context per the mix table.
4. **Automatic filters (code).** Keep an example only if: the figure/phrase is on the cited page (`check_text`,
   `numeric_match`); the citation label exists in the context; for refusals, the gold figure is on no context page;
   no near-duplicate question (normalized text); answer under `MAX_ANSWER_TOKENS`.
5. **Review.** Claude reviews a 200-example sample (Opus 5.5, like `bulk_review.py`); you spot-check 50 of them by
   hand. Pass: >= 95% of the sample correct; else fix the prompt or filter and redraw.
6. **Split.** 90% train / 10% validation by document page (no page in both).

Cost: ~800 Gemini calls = about 2 days of the 500/day free quota, if nothing else uses the key those days.

## Training (Kaggle, later step)

- Unsloth QLoRA on Qwen2.5-7B-Instruct, Kaggle T4/P100 (16 GB); max length ~7k tokens (context is up to 8k); loss on
  the assistant turn only; LoRA r=16, 1-2 epochs, early stop on validation loss.
- Export to GGUF Q4_K_M, `ollama create qwen2.5:7b-sft` with the same Modelfile (8k context, all layers on GPU).
- Fallback if 7B does not fit or is too slow: Qwen2.5-3B-Instruct locally (6 GB GPU).

DPO (week 11) reuses this pool: chosen = the filtered target, rejected = the base model's own wrong answer or wrong
refusal on the same input (generated locally, no Gemini).

## Leakage controls

- No test page, no dev gold page, no benchmark-drafted page is ever a gold page in training.
- Remaining risk: the same figure printed on another page (restated tables, summaries). Filter step 4 drops a training
  example whose answer figure equals a dev gold answer for the same bank and year; report the count.

## Decisions (2026-10-28)

1. Base model: Qwen2.5-7B-Instruct, trained on Kaggle.
2. Size: ~2,200 examples.
3. Open: Gemini key for drafting (the eval key or a separate one, so drafting can run beside evals with vision).

## Step 1 result (`sft/page_pool.py` -> `sft/pages.jsonl`)

800 pages: text_fact 160, table_lookup 200, calculation (multi-year tables) 200, chart 140, regulation 100; 9 bank
reports 61-84 pages each (bca_2024 is skipped, as in the benchmark), 26 regulations 1-5 each. Excluded before
sampling: 1,242 benchmark pages (46 tuned, 212 dev gold, 118 extra gold, 866 drafted) and every test-split page.
Eligible pools are 2-14x larger than needed (chart is the tightest: 643 for 140).

## Steps (ask before each)

1. Page pool script + counts. Sonnet 5.5.
2. Draft prompt, 10-page pilot, look at outputs. Opus 5.5 for the prompt, Sonnet 5.5 to run.
3. Full draft run (~2 days quota). Sonnet 5.5.
4. Context builder + filters + mix; counts per kind. Sonnet 5.5.
5. Review sample (Opus 5.5) + your 50-example spot-check.
6. Training notebook on Kaggle (move to the Claude desktop app for this phase). Sonnet 5.5.
7. Base vs SFT on the full dev set. Sonnet 5.5 runs, Opus 5.5 reads.
