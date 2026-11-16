# Kaggle setup: ColPali page-image indexing (Phase 2)

Purpose: index PDF pages as images with ColPali/ColQwen on a free Kaggle GPU, then download the index and use it locally. The RTX 4050 (6 GB) is too small for this and is busy with the 7B LLM. This is a one-off job.

Why: text extraction cannot read values from charts. The baseline eval shows chart questions (q028-q032) get `correct_numeric` 0 and the model refuses all of them. Chart gold pages: `bri_2025` p.328, p.315; `btn_2025` p.248; `bni_2024` p.34.

## Facts about this project
- PDFs: `data/raw/*.pdf`, 588 MB total. Use only the 44 files WITHOUT the `_en` suffix (the `_en` copies are skipped on purpose). That is 13,784 pages.
- Page numbers must match the text index: page N in `data/processed/<doc_id>.jsonl` is page N of the PDF (1-based). Keep `doc_id` = file name without `.pdf`.
- Local machine: Windows, Python 3.13, venv at `.venv`.

## What you do (Kaggle side)
1. Create a Kaggle account and verify your phone number (needed to enable GPU and internet in notebooks).
2. Create a new Dataset named `telaah-pdfs`; upload the 44 non-`_en` PDFs (about half of the 588 MB). Keep it private.
3. Create a new Notebook and add the `telaah-pdfs` dataset as input.
4. In the notebook settings: Accelerator = GPU (T4 x2 or P100, whichever is offered), Internet = On (needed to download the model), Persistence = Files only.
5. Check your weekly GPU quota under your profile > Settings/Account. Limits change; look at the current numbers.

## What the notebook does (Claude writes this later)
1. `pip install colpali-engine pdf2image pymupdf` and download the model (`vidore/colqwen2-v1.0`, or `vidore/colpali-v1.3` as a fallback).
2. Render each page to an image at moderate resolution.
3. Embed pages in small batches, fp16, and save shards (for example every 500 pages) to `/kaggle/working/` so a session timeout does not lose work.
4. Save a manifest mapping each row to `(doc_id, page)`.
5. At the end, zip `/kaggle/working/colpali_index/` for download.

## Rough estimates (unverified; confirm on the first run)
- Multi-vector embedding is about 250 KB per page in fp16, so about 3-4 GB for all 13,784 pages.
- Speed on a T4 is perhaps 1-3 pages/s, so all pages could take 2-4+ hours, which is near session limits.
- Recommended staged plan: **stage 1** index only the pages needed for charts/tables (the 3 annual reports behind q028-q032, roughly 3-4k pages, or just pages 1-400 of each) and test retrieval; **stage 2** extend to all documents only if stage 1 helps.

## Return to local
1. Download the zip from the notebook Output tab (or save it as a Kaggle Dataset and download with the Kaggle CLI).
2. Unzip into `data/colpali/` in this project.
3. Claude adds a `colpali` retrieval path in `src/telaah/retrieve.py`. Query embedding on 6 GB VRAM is likely fine for ColQwen2 in fp16 or 4-bit; to be tested.
4. Run `eval/retrieval_eval.py` to compare against text retrieval, then read the retrieved page images with a VLM (small Qwen-VL) for chart questions.

## Questions for Cowork / Claude to help with
- Walk me through creating the dataset and notebook step by step.
- What are my current Kaggle GPU quota and session limit?
- Why is a notebook run failing (out of memory, internet off, input path)?

## Decisions (2026-10-13)
- Stage 1 scope: the 3 chart reports only: `bri_2025` (1407 pages), `btn_2025` (1449), `bni_2024` (1540) = 4,396 pages, ~146 MB of PDFs. Extend to all 44 only if stage 1 helps.
- Model: `vidore/colqwen2-v1.0`, fp16 on T4 (no native bf16); the notebook falls back to float32 if fp16 gives NaN.

## Stage 1 notebook: `kaggle/colpali_index_stage1.ipynb`
1. Dataset `telaah-pdfs`: upload at least `bri_2025.pdf`, `btn_2025.pdf`, `bni_2024.pdf` (uploading all 44 non-`_en` PDFs now saves a re-upload for stage 2; the notebook only uses the 3).
2. Kaggle > Create > New Notebook > File > Import Notebook > pick `kaggle/colpali_index_stage1.ipynb`.
3. Add input `telaah-pdfs`. Settings: Accelerator = GPU T4 x2 (NOT P100), Internet = On.
4. Optional: run the first 3 cells interactively to check install, PDF paths and the fp16 sanity check, then stop the session.
5. Save Version > Save & Run All (Commit). Runs in the background with the browser closed.
6. Read the log: per-shard progress + ETA, then the chart-question retrieval test (recall@5 for q028-q032, all reports and filtered to the question's report).
7. Output tab: download `colpali_index.zip`, unzip to `data/colpali/` (gitignore it).
- Output format: `<doc_id>_<startpage>.pt` shards of 200 pages, each `{doc_id, pages, lengths, emb (fp16, sum(lengths) x 128)}`; `manifest.json` maps every (doc_id, page) to shard + row offset.
- Resume after a crash: add the failed version's output as an extra input; existing shards are copied and skipped.
- Untested on Kaggle yet: package versions, speed, and memory at BATCH=4 (lower to 2 on OOM).

# Kaggle setup: SFT of Qwen2.5-7B (roadmap week 10, step 6 of `sft/DESIGN.md`)

Notebook: `kaggle/sft_qwen7b_qlora.ipynb` (Unsloth QLoRA, `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`, r=16, max 8,448
tokens, 1 epoch, effective batch 8, lr 2e-4, loss on the answer only, val loss every 50 steps, checkpoints every 50).
Data: `python sft/split_sft.py` -> `sft/kaggle_upload/train.jsonl` (1,213) + `val.jsonl` (111), split by page hash
(482 / 45 pages, no overlap). The upload folder is git-ignored.

1. Check the weekly GPU quota (profile > Settings).
2. Datasets > New Dataset: upload `sft/kaggle_upload/train.jsonl` and `val.jsonl`, name `telaah-sft`, Private.
3. Create > New Notebook > File > Import Notebook > `kaggle/sft_qwen7b_qlora.ipynb`.
4. Add Input > Your Datasets > `telaah-sft`. Settings: GPU T4 x2 (Unsloth uses one; not P100), Internet On.
5. Smoke test: Run All in the editor (interactive session = 20 steps, no export). Read cell 5 (token lengths),
   cell 6 (trained tokens = the answer only), cell 7 (s/step, peak memory, estimated full-run hours), cell 9.
   Then STOP the session.
6. Full run: Save Version > Save & Run All (Commit). The mode switches to FULL by itself
   (`KAGGLE_KERNEL_RUN_TYPE=Batch`; `FORCE_FULL=True` in cell 2 overrides in an editor session).
7. Version page > Output: `lora_adapter.zip`, `qwen2.5-7b-telaah-sft-Q4_K_M.gguf` (~4.7 GB), `train_log.json`,
   `val_samples.jsonl`.
- Resume after a crash: add the failed version's output as an input; the newest checkpoint is picked up.
- If the GGUF cell fails, the adapter zip is still saved; redo merge + conversion in a short second run.
- Untested on Kaggle yet: package versions, memory at 6,144 tokens on a T4, speed. The smoke test checks all three.
