# Session notes — 2026-10-12

Handoff for continuing the Telaah project (see `ROADMAP.md`). Not a verbatim transcript.

## Decisions
- Scope this session: Phase 1 only (scaffold + baseline text RAG + eval harness).
- Run everything on native Windows (no WSL2).
- LLM: Ollama local, `qwen2.5:7b-instruct`, via OpenAI-compatible client (swap to Gemini/Groq through `.env`).
- Vector store: embedded Qdrant (`data/qdrant`), since Docker is not installed.
- Parser: Docling, one chunk per page. Embeddings: BAAI/bge-m3.

## Environment findings
- Python 3.13.3, git 2.49 installed.
- Docker: NOT installed. Ollama: NOT installed.
- GPU is RTX 4050 Laptop, 6 GB VRAM (roadmap assumed 4060 / 8 GB). If 7B runs out of memory, use `qwen2.5:3b-instruct`.

## Done
- Project scaffold: `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/telaah/*`, `eval/*`, `tests/test_core.py`.
- `.venv` created with light deps only (pytest, openai, python-dotenv, qdrant-client); `pip install -e . --no-deps`.
- `pytest`: 5 passed.

## Not done / next steps
1. Install Ollama (ollama.com) and `ollama pull qwen2.5:7b-instruct`.
2. Put IDX annual reports + OJK/BI regulation PDFs in `data/raw/` (user task).
3. DONE (2026-10-13): heavy deps installed. torch 2.11.0+cu128, CUDA works on the 4050; docling 2.138, sentence-transformers 6.1; pytest 5 passed. Torch was installed first from the cu128 index, then `pip install -e ".[dev]"`.
   Decision: run Phase 1 locally; use Kaggle only for the one-off ColPali indexing in Phase 2.
4. Smoke test: `telaah ingest` -> `inventory` -> `index` -> `ask`.
5. Write the 50 seed questions in `eval/seed_questions.jsonl` (user task; replace the 2 `CONTOH` rows), then `telaah eval` for baseline numbers.
6. Not built yet: LLM-judge for text answers (roadmap metrics: correctness, faithfulness).
7. Then Phase 2: hybrid BM25 + reranker, query rewriting, ColPali.

## Notes
- Bash tool failed on a very long heredoc; use the Write tool for multi-file scaffolding.
- PDF copy of the roadmap could not be read (poppler not installed); `ROADMAP.md` has the same content.

# Update — 2026-10-13 (afternoon)

## Done
- Ollama installed; `qwen2.5:7b-instruct` pulled.
- Ingest complete: all 44 non-`_en` PDFs parsed to `data/processed/*.jsonl` (13,784 pages). `_en` copies skipped on purpose.
- `bri_2025` gold values for q001/q002 verified present on pages 26/28.
- `telaah inventory` run (`data/inventory.csv`, 44 docs).
- `telaah index` complete: 13,784 points in `data/qdrant`, matches page count. The `ImportError: sys.meta_path is None` at exit is harmless Qdrant cleanup noise.
- 50 seed questions written in `eval/seed_questions.jsonl`.

## Lessons
- 3 ingest workers ran out of RAM (15.7 GB laptop) on the big annual reports and broke the pool. Use `--workers 2`. `ingest` skips finished files, so just rerun after a crash.
- `parse.py` now sorts files smallest-first.
- Docling is GPU-bound (RTX 4050, 6 GB VRAM, ~99% util); more workers do not add speed.
- `bni_2024` took 77 min because the page split fell back to the slow per-page export.
- Power settings changed for long jobs: idle sleep/hibernate = never, lid close = do nothing. Restore later: idle sleep 10 min, lid action = Sleep.

## Next
1. Verify gold pages in `eval/seed_questions.jsonl` (user task).
2. `telaah eval` for baseline numbers.
3. Check `judge.py` is complete (LLM judge for correctness/faithfulness).
4. Phase 2: hybrid BM25 + reranker, query rewriting, ColPali (index on Kaggle, not locally).

# Update — 2026-10-13 (evening): baseline eval + Phase 2 started

## Verified
- Gold pages in `eval/seed_questions.jsonl` all checked (text/table/cross-doc exact; chart values by eye on rendered pages). No errors found.
- Unanswerable q041-q050: no real answer in corpus. q050 is borderline (`bni_2024` p.403 mentions late-reporting fines only).

## Baseline eval (`eval/runs/20261013-165625.json`, 7B, dense only)
recall@5 0.34, citation_acc 0.22, refusal_acc 0.72, correct_numeric 0.32, correct_judge 0.27, faithful 0.60, latency 138 s/question (~100 min total).
By type: table_lookup recall 0.00; text_fact 0.42; chart 0.20; cross_doc 0.12; unanswerable refusal_acc only 0.20 (model answers instead of refusing).

## Phase 2 code added
- `src/telaah/filters.py`: detects bank/year/regulation in the question -> doc_id groups.
- `src/telaah/bm25.py`: own BM25 over all pages, cached in `data/bm25.pkl`.
- `src/telaah/retrieve.py`: `retrieve(q, filter_docs, hybrid, rerank)`; dense + BM25 fused by RRF; optional bge-reranker-v2-m3 (raw logits); per-entity retrieval interleaved for multi-entity questions.
- `eval/retrieval_eval.py`: retrieval-only ablation, no LLM, fast. Run: `.venv\Scripts\python eval\retrieval_eval.py dense +filter +bm25 +rerank` (set `HF_HUB_DISABLE_SYMLINKS_WARNING=1`). Also prints "answer-in-context".
- `config.py`: `RERANK_MODEL`.
- `retrieve()` defaults are still filter+hybrid+rerank all ON. Reranker did not help overall, so consider defaulting `rerank=False`.

## Retrieval ablation (answerable questions, recall@5)
| variant | overall | table | text | chart | cross_doc | answer-in-ctx (table) |
|---|---|---|---|---|---|---|
| dense | 0.17 | 0.00 | 0.42 | 0.20 | 0.12 | 0.40 |
| +filter | 0.30 | 0.00 | 0.83 | 0.40 | 0.00 | 0.40 |
| +bm25 | 0.42 | 0.20 | 0.83 | 0.80 | 0.00 | 0.53 |
| +rerank | 0.38 | 0.00 | 0.92 | 0.60 | 0.12 | 0.53 |
- Gold-page recall understates table_lookup: the same figure appears on several pages (e.g. BRI total assets also in narrative p.315).
- Reranker (bge-reranker-v2-m3) saturated to 1.0 with sigmoid; switched to raw logits, still no overall gain.

## BUG found: Ollama truncates prompts (fix pending, needs user OK)
- Ollama default context 4096 split across 2 slots (~2048 each). `server.log` shows 56x "truncating input prompt" (limit=2050, prompt~4100, keep=4) -> retrieved pages dropped. Baseline generation scores are therefore unreliable.
- Fix: restart Ollama with `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`. Recommended: session-only first (stop Ollama, run `ollama serve` with the env vars set), make permanent later if good. Ollama log: `%LOCALAPPDATA%\Ollama\server.log`.
- Ollama was currently running with defaults (CONTEXT_LENGTH 0, FLASH_ATTENTION false, KV type empty).

## Next
1. Apply the Ollama fix above, verify no more "truncating input prompt" lines in the log.
2. Re-run baseline-comparable full eval (`telaah eval`) with the new retrieval; compare to the 20261013-165625 run. Add per-question progress printing to `eval/run_eval.py`.
3. Cross_doc retrieval: groups are detected but recall stays ~0; inspect per-entity results (q033-q040).
4. Refusal rule: refuse when retrieved pages do not support an answer (unanswerable refusal_acc was 0.20).
5. Speed: run the query embedder on CPU to free VRAM for the 7B; use `qwen2.5:3b-instruct` only for quick retrieval tests; run LLM judges only on final evals.
6. Later: query rewriting, ColPali (Kaggle). Restore power settings when long jobs are done (idle sleep 10 min, lid = Sleep).

# Update — 2026-10-13 (night): Ollama fix, GPU speedup, cross_doc retrieval

## Done
- Ollama truncation fixed (session-only): restarted `ollama serve` with `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`. Verified a 7837-token prompt is processed in full. NOT permanent: after an Ollama/PC restart, redo it (start from PowerShell with those env vars set, hidden window).
- Full-GPU 7B: the default scheduler left ~0.9 GB on CPU; `num_gpu=99` fits all in VRAM (4.77 GB). Created model `qwen2.5:7b-gpu` (Modelfile: num_gpu 99, num_ctx 8192). Eval run with `LLM_MODEL=qwen2.5:7b-gpu`.
- Closed Spotify/NVIDIA Broadcast/Copilot/widgets/Phone Link for RAM (free RAM 4.8 -> 6.5 GB).
- `src/telaah/index.py`, `retrieve.py`: embedder + reranker on CPU via `TELAAH_DEVICE` (default cpu). Set `TELAAH_DEVICE=cuda` before `telaah index`.
- `retrieve()` defaults: `rerank=False`, new `summary=True`, `per_entity=3`. `bm25.search` got `max_page`.
- Summary-page boost: for bank annual reports, extra dense+BM25 rankings limited to pages 1-45 (top 8) fused by RRF. Multi-entity questions: 3 pages per entity, interleaved (max 6 pages, ~6k tokens).
- `eval/run_eval.py`: per-question progress. `eval/retrieval_eval.py`: variants `+quota`, `+summary`, plus `all-gold-in-context`.
- Skill `~/.claude/skills/session-handoff/SKILL.md`; SessionStart hook in `~/.claude/settings.json` prints last 150 lines of SESSION_NOTES.md.
- pytest: 6 passed.

## Results
- Eval 1 (`eval/runs/20261013-201756.json`, Ollama fixed, old retrieval): recall@5 0.54, citation 0.32, refusal 0.74, numeric 0.43, judge 0.79, faithful 0.93, 12.5 s/question (was 138 s). Chart refusal_acc fell to 0.0 (model refuses all charts); cross_doc recall 0.0.
- Retrieval ablation (answerable, recall): +quota only: overall 0.42 (table 0.20, cross 0.00, chart 0.80). +summary: overall 0.65 (table 0.60, text 0.83, chart 0.60, cross 0.50). cross_doc all-gold-in-context still 0.00.
- Cross_doc diagnosis: entity detection is right; gold pages are front "highlights" pages ranked 12-25+ inside each doc. q040 locks onto revoked PBI 11/2023, answer is in PBI 9/2025 (not named in question).

## Running/pending
- Eval 2 (new retrieval, started 20:26) running in background: log `%TEMP%\eval2_out.log`, result will be a new file in `eval/runs/`. ~15-25 s/question, expected done ~20:50. /clear does not stop it; do not sleep/reboot PC or stop Ollama.

## Next
1. Read eval 2 result; compare per type vs eval 1 (`20261013-201756.json`) and baseline (`20261013-165625.json`). Watch chart (retrieval recall dropped 0.80 -> 0.60).
2. Cross_doc: both gold pages still rarely together. Ideas: per-entity query rewrite (drop "selisih/bandingkan"), rerank only within front pages, handle revoked regulations (include replacement doc for "dicabut/menggantikan").
3. Chart questions: refusal rule / ColPali (Kaggle).
4. Refusal rule: refuse when retrieved pages do not support the answer.
5. Make Ollama env permanent if the setup works; restore power settings (idle sleep 10 min, lid = Sleep) when long jobs are done.

# Update — 2026-10-13 (night, ~20:55): eval 2 results + power settings

## Done
- Power: idle sleep (AC+DC) and hibernate timeout set to Never via `powercfg /change`. Lid-close action could NOT be set (no lid setting exposed in the Acer plan; `setacvalueindex` silently did nothing). User should set "Do nothing" manually in Control Panel > Power Options, or keep lid open. Restore: `powercfg /change standby-timeout-ac 10` and `-dc 10`.

## Results
- Eval 2 (`eval/runs/20261013-204429.json`, new retrieval w/ summary boost + per-entity quota, `qwen2.5:7b-gpu`) vs eval 1 (`20261013-201756.json`):
  recall@5 0.54 -> 0.72, citation 0.32 -> 0.36, refusal 0.74 -> 0.76, numeric 0.43 -> 0.57, judge 0.79 -> 0.79, faithful 0.93 -> 0.90, latency 12.5 -> 21.9 s/q.
- Per type (recall e1 -> e2): table_lookup 0.20 -> 0.60 (judge 0.67 -> 0.85); text_fact 0.83 -> 0.83 (judge 0.92); cross_doc 0.00 -> 0.50 (judge 0.75 -> 0.25, n=8, noisy; refusal_acc 0.50); chart 0.80 -> 0.60 (refusal_acc 0, numeric 0: model refuses all charts); unanswerable refusal 0.90.
- Example: q001 recall 1.0 but model said "TIDAK DITEMUKAN" -> generation/prompt issue, not only retrieval. Citation acc low even on text_fact (0.5).

## Lessons
- Compare runs per type by grouping `results[]` in the run JSON on `type` (fields: recall@5, citation_acc, refusal_acc, correct_numeric, correct_judge, faithful). In PowerShell avoid a bare `}} | Sort` pipe after foreach; assign to `$out` first.

## Running/pending
- Nothing running. Ollama still running with session-only env fix (redo after restart; see earlier note).

## Next
1. Refusal rule: refuse only when retrieved pages do not support the answer; also stop the model refusing chart/cross_doc questions when evidence is present (affects ~13 questions). Check why q001 refused despite recall 1.0 (prompt wording).
2. Cross_doc: per-entity query rewrite (drop "selisih/bandingkan"), rerank within front pages, include replacement regulation for "dicabut/menggantikan" (q040).
3. Improve citation accuracy (prompt format for [doc pN] citations).
4. Chart questions: ColPali on Kaggle (Phase 2).
5. Investigate latency rise (21.9 s/q): summary retrieval vs longer prompts.
6. Make Ollama env permanent if setup works; restore power settings when long jobs done.

# Update — 2026-10-13 (late night): eval 3, fixes, Kaggle prep

## Done
- `src/telaah/answer.py`: `compact()` collapses table padding (spaces, dash runs) before the 3000-char per-page cap. Root cause of q001 refusal: answer was at char 5071 of a 9262-char page. Also added a citation example + "use label exactly" to the SYSTEM prompt.
- `src/telaah/retrieve.py`: `_with_replacements()` + `REPLACE_RE`: for "dicabut/menggantikan/pengganti" questions, add the other docs of the same regulation series as an extra group (fixes q040 retrieval).
- Per-entity query rewrite (strip "selisih/bandingkan", other bank names) was tried and REMOVED: cross_doc any-gold-hit 4/8 vs 5/8 without it.
- `KAGGLE_SETUP.md` written (ColPali plan; estimates unverified). User created Kaggle account.
- Memory: `kaggle-phase-move-to-desktop.md` (remind user to move to Claude desktop/Cowork at Kaggle phase).
- pytest: 6 passed.

## Results
- Eval 3 (`eval/runs/20261013-213811.json`, compact fix only) vs eval 2: recall 0.72 -> 0.72, citation 0.36 -> 0.42, refusal 0.76 -> 0.78, numeric 0.57 -> 0.64, judge 0.79 -> 0.90, faithful 0.90 -> 0.86, latency 21.9 -> 13.0 s/q.
- Per type: table judge 0.92, text_fact judge 1.0, unanswerable refusal 1.0, cross_doc judge 0.50 but faithful 0.25 (n=8), chart all 0 (refuses all).
- Metric note: per-question recall@5 = any gold page hit (not fraction).
- Cross_doc still missing both gold pages: q036, q037, q038 (q035 sometimes).

## Running/pending
- Eval 4 (replacement fix + citation prompt) running in background; log `%TEMP%\eval4_out.log`; result = newest file in `eval/runs/` (after `20261013-213811.json`). ~11-15 min. Do not sleep PC or stop Ollama. Ollama runs `qwen2.5:7b-gpu` (num_gpu 99, num_ctx 8192) with default env; fine.

## Next
1. Read eval 4; compare with eval 3 per type (check citation_acc up, nothing regressed).
2. Cross_doc q036-q038: inspect where gold pages rank inside each doc.
3. Refusal rule: refuse only when pages do not support answer; stop chart over-refusal where evidence exists.
4. When text fixes are done and chart questions still fail: TELL USER the Kaggle phase starts and remind them to move to Claude desktop (Cowork) on this folder (read SESSION_NOTES.md, ROADMAP.md, KAGGLE_SETUP.md). User sets up Kaggle themselves (dataset of 44 non-`_en` PDFs).
5. Restore power settings later (idle sleep 10 min; lid = Sleep).

# Update — 2026-10-13 (22:40): text pipeline finished, ready for Kaggle/ColPali

## Done
- Eval 4 (`eval/runs/20261013-215316.json`, replacement fix + citation prompt) was NOT better than eval 3: judge 0.90 -> 0.80, but most flips were judge/citation noise. One real regression: q026.
- q026 cause: `_with_replacements` added unrelated PBI series when the question already names the revoker ("dicabut oleh PBI 6/2026"); the model then picked "22/20/PBI/2020" from the added pages. Fix: `REVOKER_RE` in `src/telaah/retrieve.py` skips the replacement group for "dicabut oleh" / "mencabut". Verified q025/q026 OK. q040 still wrong (model picks PADG 27/2025 instead of PBI 9/2025); left as a hard case.
- Refusal diagnosis: all 10 refusal errors in eval 4 were over-refusals, but in 9/10 the gold numbers were NOT in the context (retrieval miss, or chart value only in the image). Do NOT loosen the refusal prompt (would hallucinate; unanswerable refusal is 1.0).
- New retrieval signal: `table_pages(doc_id)` in `retrieve.py` finds front pages (<= page 60) with a multi-year table (a header row with >= 4 distinct years). Annual-report questions get 2 extra RRF rankings (dense + BM25, `TABLE_N=4`) limited to those pages. Gold pages for q013/q035/q036 now retrieved.
- Eval 5 (`eval/runs/20261013-223239.json`, current code, `qwen2.5:7b-gpu`) vs eval 3: recall 0.72 -> 0.86, citation 0.42 -> 0.48, refusal 0.78 -> 0.82, numeric 0.64 -> 0.75, judge 0.90 -> 0.81, faithful 0.86 -> 0.93, 14.1 s/q.
  Per type: table recall 1.00, numeric 0.93, refusal 1.00; text_fact judge 0.83; cross_doc recall 0.75 but judge 0.33, refusal 0.38 (n=8, noisy); chart all 0 (recall 0.40); unanswerable refusal 1.00.
- pytest: 6 passed.

## Lessons
- The file-writing path strips backslashes inside Python/bash heredocs (a regex `\b` became a literal backspace char and silently matched nothing). Write regexes without backslashes (`(?<![0-9])`, `[0-9]`) or verify with `grep -c $'\x08'`.
- Background wait loops: exclude ALL existing files in `eval/runs/`. A launcher shell exiting also triggers a false "completed" notification; check the log.
- Per-entity quota is 3 pages (max 6 pages ~ 6k tokens for 8192 ctx). q037 gold pages (bri_2025 p26, bca_2025 p15) lose to sibling table pages under this quota.

## Known remaining issues
- Chart questions (q028-q032): values only in images; text retrieval cannot fix. Needs ColPali.
- cross_doc: q033/q038 flipped to refusals in eval 5; q037, q040 still wrong; citation_acc 0.00 for cross_doc (check citation format).
- Judge noise (q026/q027 style): identical answers can score differently; n is small.

## Next
1. KAGGLE/COLPALI PHASE STARTS NOW. Move to Claude desktop (Cowork) on `C:\Users\User\genai-project`; read SESSION_NOTES.md, ROADMAP.md, KAGGLE_SETUP.md. User uploads the 44 non-`_en` PDFs as a Kaggle dataset, runs the ColPali indexing notebook, downloads embeddings.
2. Later: merge ColPali page retrieval for chart/table-image questions into `retrieve.py`; re-run eval.
3. Optional text-side: cross_doc citation format, q040, metric split ("refused while evidence in context").
4. Ollama env fix is session-only (num_ctx 8192 via model `qwen2.5:7b-gpu`); redo after restart. Restore power settings when done: `powercfg /change standby-timeout-ac 10` and `-dc 10`; set lid action = Sleep manually.

# Update - 2026-10-13 (23:00): Kaggle/ColPali stage 1 prepared

## Done
- Session continued with the project folder linked (no separate desktop session needed); read SESSION_NOTES.md, ROADMAP.md, KAGGLE_SETUP.md.
- User decisions: stage 1 = 3 chart reports only (`bri_2025`, `btn_2025`, `bni_2024`); model = `vidore/colqwen2-v1.0`.
- Verified PDF page counts = max page in `data/processed`: bri_2025 1407, btn_2025 1449, bni_2024 1540 (4,396 pages). Some pages are missing from the jsonl (empty pages), so line count < page count; page numbers still align.
- Wrote `kaggle/colpali_index_stage1.ipynb` (fp16 on T4 with NaN check and float32 fallback, 200-page shards, resume from previous output, manifest.json, in-notebook recall test on q028-q032, zip). KAGGLE_SETUP.md updated with steps and output format.

## Next
1. User: upload PDFs as dataset `telaah-pdfs`, import + commit-run the notebook on T4 x2, share the log (versions, ETA, recall test), download `colpali_index.zip` to `data/colpali/`.
2. Add `data/colpali/` to .gitignore; add a `colpali` retrieval path in `retrieve.py` (query embedding locally, ColQwen2 on 6 GB; test fp16 vs 4-bit) and compare with `eval/retrieval_eval.py`.
3. Then VLM reading of retrieved page images for chart questions.

# Update - 2026-10-13 (23:25): Kaggle run queued

## Done
- Kaggle (user ran it themselves, step by step): dataset `telaah-pdfs` uploaded (3 PDFs, user archiesinaga). Notebook imported, GPU T4 x2, Internet on. Cells 1-3 passed interactively (torch 2.11.0+cu128, transformers 5.16.1, colpali-engine 0.3.18, pymupdf 1.28.2; Tesla T4).
- Fix needed: Kaggle's preinstalled `torchao` 0.10.0 breaks `peft` when loading ColQwen2 (ImportError). Added `!pip uninstall -y -q torchao` to cell 1, in both the Kaggle notebook and `kaggle/colpali_index_stage1.ipynb`.
- Saved Version #1 via "Save & Run All (Commit)"; it was still **Queued** for a GPU at 23:23. Do not cancel or re-save (loses queue place).

## Next
1. When Version #1 is Running: read its Logs tab; check the ETA lines (`<doc>_<start>.pt: n/4396 pages`). Speed and quota are still unverified.
2. When done: download `colpali_index.zip` from the Output tab, unzip to `data/colpali/`, share the q028-q032 recall lines from the log.
3. Then add the `colpali` path in `retrieve.py` and compare with `eval/retrieval_eval.py`.

# Update - 2026-10-14 (11:00): ColPali retrieval + Gemini page reader written (NOT yet run on this PC)

## Done
- Kaggle stage 1 finished (56 min, T4 x2, 0.78 GB zip). In-notebook test on q028-q032: recall@5 5/5 when filtered to the question's report, 4/5 over all 3 reports (text retrieval had 0.40-0.60 on charts). Index unzipped to `data/colpali/` (24 shards + manifest.json, 4,396 pages, 747 vectors/page, fp16). Verified.
- User decisions: chart values are read by Gemini vision (free key); ColPali is merged into the existing RRF ranking.
- New `src/telaah/colpali.py`: loads shards, MaxSim per page (scatter_reduce amax), `covers(doc_ids)`, query encoder ColQwen2 on CPU bf16 (`TELAAH_COLPALI_DEVICE=cuda` to change). `search()` returns dicts with page text from the BM25 pages (or a no-text note).
- `retrieve.py`: `retrieve(..., colpali=True, colpali_weight=1)`; the ColPali ranking joins the RRF only when ALL doc_ids of the group are indexed; any ColPali error disables it with one warning (text pipeline unchanged). Existing eval variants now set `colpali=False` so old numbers stay comparable; new variants `+colpali`, `+colpali2`, `+colpali3` (weight = times the ranking is added).
- Smoke test with stubs showed weight 1 cannot promote a page only ColPali finds (p.328 stayed out of top 5, entered at weight 2): so the ablation decides the weight.
- New `src/telaah/vision.py`: `wants_image()` (grafik/chart/diagram/bagan/gambar...), renders PDF page via pymupdf, Gemini through the OpenAI-compatible API (`VISION_MODEL=gemini-3.8-flash`, key `GEMINI_API_KEY` in .env), transcribes only, disk cache in `data/vision_cache/`. `answer.py add_page_images()`: for chart questions the top `VISION_PAGES=2` retrieved pages that are in the ColPali index get the transcription PREPENDED to their context (3000-char cap), `ask()` returns `vision` pages.
- Tests: `tests/test_colpali.py` (4 tests, synthetic index) passed in the cloud container with torch 2.14; stubbed smoke test passed. NOT run with the local venv, real ColQwen2, or real Gemini yet.
- colpali-engine 0.3.18 requires torch<2.14, transformers>=5.3,<6, peft>=0.18,<0.21: compatible with local torch 2.11 / transformers 5.19; only peft is new. Originals backed up in `.bak_pre_colpali/`.
- Free-tier note: Google says free-tier content may be used to improve its products (reports are public). Rate limits are shown in AI Studio, not published as numbers.

## Next (user runs on this PC)
1. `.venv/Scripts/pip install colpali-engine pymupdf`, then `.venv/Scripts/python -m pytest -q` (expect 10 passed).
2. `.venv/Scripts/python eval/retrieval_eval.py +summary +colpali +colpali2 +colpali3` (first run loads ColQwen2 once, several minutes). Compare chart recall and overall vs +summary (0.65 overall, chart 0.60).
3. Pick the weight; make it the default if better. Then put `GEMINI_API_KEY=` in `.env` and run a chart question end to end (`telaah ask`), then `telaah eval` with `LLM_MODEL=qwen2.5:7b-gpu`.
4. Check disk cache `data/vision_cache/` after the run; transcription quality on q028-q032 is unverified.

# Update - 2026-10-14 (11:12): ColPali ablation result + auto weight

## Results (retrieval_eval, 40 answerable questions, recall@5; run on this PC, ColQwen2 on cuda, Ollama stopped)
| variant | overall | table | text | chart | cross_doc |
|---|---|---|---|---|---|
| +summary (no ColPali) | 0.82 | 1.00 | 0.83 | 0.40 | 0.75 |
| +colpali (weight 1) | 0.82 | 1.00 | 0.83 | 0.40 | 0.75 (identical: one extra ranking cannot lift a page) |
| +colpali2 | 0.85 | 0.93 | 0.83 | 0.80 | 0.75 |
| +colpali3 | 0.82 | 0.87 | 0.83 | 0.80 | 0.75 (all-gold cross_doc 0.12, worse) |
- answer-in-context for chart stays 0.00 for all: chart values are only in the image, so the Gemini transcription step is what must produce the number.
- Weight 2 on every question: chart +2 questions but -1 table question; net +1 of 40. Noisy (n=5 chart).
- Seed check: all 5 chart questions contain chart words (grafik...), none of the other 45 questions do. That is partly circular (the seed questions were written that way).

## Decision / code
- `retrieve(colpali_weight=None)` = auto: weight `COLPALI_CHART_WEIGHT=2` when `vision.wants_image(query)` else 0 (ColPali not called, ColQwen2 not even loaded). Explicit ints still work. New eval variant `+auto` = default; expected from the above: overall ~0.875, table 1.00, chart 0.80 (prediction, not yet run).
- tests/test_colpali.py: 5 tests (new: auto weight only for chart questions). Passed in cloud container with the real modules; user ran the earlier 4 on the PC (10 passed total before this).

## Next
1. User: `.venv/Scripts/python eval/retrieval_eval.py +auto` (check it matches the prediction), pytest -q (expect 11 passed).
2. Get GEMINI_API_KEY (Google AI Studio), put in .env; run one chart question end to end (`telaah ask` on q028) and inspect `data/vision_cache/`.
3. Then full `telaah eval` with `LLM_MODEL=qwen2.5:7b-gpu` and compare with eval 5 (`eval/runs/20261013-223239.json`): chart numeric/judge, refusal, and make sure other types did not regress.
4. Still open: which chart question misses at 0.80; cross_doc (needs docs outside the 3 indexed reports, ColPali cannot help there); latency of the vision call.

## Lessons / how to run (2026-10-14, added at 11:15)
- ColQwen2 query encoder on CPU (bf16) made the Python process ~5.7 GB and RAM hit 95% of 15.7 GB (committed 26/28.8 GB): too risky. Cancelled with Ctrl+C.
- Working recipe for retrieval-only evals (no LLM needed): in PowerShell `ollama stop qwen2.5:7b-gpu` (frees 4.8 GB VRAM), `$env:TELAAH_COLPALI_DEVICE="cuda"` (ColQwen2 fp16 ~4.4 GB of the 6 GB VRAM; keep TELAAH_DEVICE unset so bge-m3 stays on CPU), `$env:HF_HUB_DISABLE_SYMLINKS_WARNING="1"`, then `.venv/Scripts/python eval/retrieval_eval.py <variants>`. It ran fine; RAM was ~53% idle before the run. Env vars last only for that PowerShell window.
- For full `telaah eval` (LLM) run with ColPali on CPU or leave it off for non-chart questions: with auto weight ColQwen2 loads only when a chart question appears. Ollama reloads the 7B by itself after `ollama stop`. If both must be on the GPU at once, VRAM (6 GB) is not enough.
- Do not close the Claude desktop app (links the cloud session to this PC) or Vmmem (the Linux VM used for the file shell).
- The Windows venv cannot be run from the Linux file shell used by the assistant, so test runs on this PC are done by the user in PowerShell; the assistant tests logic in its own container with the same code.
- Kaggle lessons (for stage 2 if ever needed): Save & Run All queues for a GPU (minutes); Kaggle's old torchao breaks peft (uninstall torchao in cell 1); output zip is in the version page > Output tab, not in the editor's Output panel; indexing speed ~1.4 pages/s on T4, 4,396 pages in ~56 min, 0.78 GB.
- ColPali weight ablation and the auto-weight decision are in the 11:12 entry above.

# Update - 2026-10-14 (23:30): Gemini vision working, chart questions 4/5

## Done
- `.env` created (gitignored) with `GEMINI_API_KEY` and `VISION_MODEL=gemini-3.5-flash-lite`, `VISION_PAGES=5`. The free key only accepts `gemini-3.5-flash-lite` / `gemini-flash-lite-latest` (tested by a real call; `gemini-2.5-flash` returns 404 for new users; 3.8/3.7/3.5-flash and 3.1-flash-lite fail). `.env.example` updated. The key was pasted in chat: rotate it in AI Studio when convenient.
- Chart failure causes found and fixed:
  1. Prompt overflow: 5 transcribed pages + 3000-char texts exceeded num_ctx 8192, Ollama dropped the front (gold page). `build_context()` now keeps the full transcription and only `VISION_TEXT_CAP=800` chars of page text for transcribed pages (`answer.py`).
  2. Irrelevant transcripts distracted the 7B: Gemini now answers "TIDAK RELEVAN" for pages without a matching chart and `add_page_images` drops them (`vision.py`; prompt is part of the cache key).
  3. `VISION_HINT` line in the user message when transcribed pages exist (transcription = valid evidence). Fixed q030.
  4. `filters.py`: a year right after the bank name ("BTN 2025") wins over other years in the question (q031 pulled in `btn_2024`, which is not in the ColPali index, so ColPali was skipped).
- ColPali alone does not rank the gold chart page first (q028 gold is rank 5), so vision pages are chosen from the fused ranking, not ColPali order.

## Results
- Retrieval ablation `+auto`: overall 0.88 -> 0.90, chart 0.80 -> 1.00, others unchanged.
- Eval 6 (`eval/runs/20261014-224132.json`, vision on, before fixes): recall 0.90, citation 0.50, refusal 0.84, numeric 0.82, judge 0.84, faithful 0.90, 20.6 s/q. Chart numeric 0.40.
- Eval 7 (`eval/runs/20261014-231926.json`, with fixes): recall 0.92, citation 0.56, refusal 0.90, numeric 0.89, judge 0.83, faithful 0.91, 16.5 s/q.
  Per type vs eval 6: chart recall 0.80 -> 1.00, citation 0.20 -> 0.80, numeric/judge 0.40 -> 0.80, refusal 0.40 -> 0.80; table, text_fact, unanswerable identical; cross_doc recall 0.75, judge 0.13, refusal 0.38 -> 0.50.
- Only numeric flips: q030, q032 (0 -> 1). Remaining chart miss: q031 (gold 5,80%): transcript has "Jan 2024 (DPK): 5,80" but no "yoy" unit, so the model refuses. Left as is (refusing beats guessing a unit).
- Eval 5 -> 7 overall: recall 0.86 -> 0.92, numeric 0.75 -> 0.89, refusal 0.82 -> 0.90, citation 0.48 -> 0.56.

## Lessons
- Vision transcripts are question-conditioned and cached in `data/vision_cache/`; changing PROMPT or VISION_MODEL invalidates the cache automatically (~25 Gemini calls per full chart run).
- Debug scripts live in the session scratchpad; useful pattern: print `build_context()` for one question to see exactly what the LLM receives.
- Running ColQwen2 on cuda and the 7B at once does not fit 6 GB VRAM: for retrieval-only runs `ollama stop` first; for `telaah eval`/`ask` leave `TELAAH_COLPALI_DEVICE` unset (CPU).

## Next
1. cross_doc is the biggest gap (judge 0.13, citation 0.00, refusal 0.50, n=8). Models refuse even when recall is 1.0 (q036, q038); check context size/ordering with the per-entity quota and citation format.
2. Optional: q031 unit issue, q040 (picks PADG instead of PBI 9/2025).
3. Phase 2 left: ColPali stage 2 for the other docs (only if needed), then README/results write-up.
4. Housekeeping: rotate Gemini key; restore power settings (`powercfg /change standby-timeout-ac 10` and `-dc 10`, lid = Sleep manually); make Ollama env permanent.

# Update - 2026-10-15 (00:10): cross_doc split-and-compose path

## Done
- Diagnosis (eval 7): per-entity gold pages sit at rank 1-6 of their own entity's ranking (q033 BRI p28 rank 4, q037 BCA p15 rank 5, q038 BTN p248 rank 17, q037 BRI p26 not in top 25). Quota 3 cut too early; quota 5 in ONE prompt (10 pages) removed refusals but the 7B mixed up banks (same total for BRI and BCA, wrong doc labels).
- Tried and dropped: per-entity fact EXTRACTION against the full comparison question. The 7B answered KOSONG/TIDAK DITEMUKAN even with the gold page in context.
- Final design (`answer.py` `ask_entities`, `retrieve.py` `entity_groups` + `retrieve_entity`): LLM splits the question into one simple question per entity (`split_question`, JSON array, fallback = original question), each sub-question runs the normal pipeline on that entity's docs only (`ENTITY_PAGES=5`, vision step included), then one compose call over the sub-answers. `ask()` returns `sub_questions`. Questions with dicabut/menggantikan (q040) keep the old single-prompt path. A bank named with two report years ("laporan 2024 ... laporan 2025") becomes two entities (q039).
- `PER_ENTITY` stays 3 on the old path; `build_context` shares `CONTEXT_CHARS=16000` across pages (cap = min(3000, 16000 / pages)); 5 pages unchanged.
- pytest: 11 passed.

## Results
- Eval 8 (`eval/runs/20261014-235115.json`) vs eval 7 (`20261014-231926.json`): recall 0.92 -> 0.90, citation 0.56 -> 0.54, refusal 0.90 -> 0.92, numeric 0.89 -> 0.86, judge 0.83 -> 0.83, faithful 0.91 -> 0.93, 16.5 -> 18.0 s/q.
- cross_doc: judge 0.13 -> 0.38, refusal_acc 0.50 -> 0.63, faithful 0.25 -> 0.00 (n=8, noisy; faithful judge sees raw pages of each entity), recall 0.75 -> 0.63 (recall counts pages of the sub-question retrieval), citation still 0.00. Flips: q033 and q035 now correct (q035 = 10,44).
- Only non-cross_doc flip: q002 (table) wrong in eval 8, but 3/3 correct when re-run with identical retrieval -> run noise, not caused by this change (q002 does not use the new path).
- Spot check before the last split-prompt tweak: q033/q034/q035 correct; q039 first figure right, second wrong (sub-question lost the bank name -> prompt now requires bank + report year in every sub-question).

## Known remaining cross_doc issues
- q037: BRI gold p26 not retrieved (BRI total assets wrong). q038: wrong figures (NPL industri is on btn_2025 p248, rank 17). q036: refuses (padg 23/2025 p7 rank 6; sub-question 1 asks about the regulation alone). q040: old path, refuses.
- citation_acc 0.00 for cross_doc: partly metric (answers cite another page with the same value, e.g. bri_2025 p.342 vs gold p31); check how citation_acc is scored before tuning.

## Next
1. Decide whether cross_doc needs more (q036/q037/q038 retrieval) or move on to write-up/README (Phase 2 results table: baseline 0.34 recall -> 0.90).
2. Housekeeping still open: rotate Gemini key; restore power settings (`powercfg /change standby-timeout-ac 10` and `-dc 10`, lid = Sleep manually); make Ollama env permanent.

# Update - 2026-10-15 (01:30): final eval + README

## Done
- Bug: the 7B can fall into a repetition loop at temperature 0 and never stop (q004 hung >10 min, no `max_tokens`). Added `MAX_ANSWER_TOKENS=800`, `MAX_JUDGE_TOKENS=300` (`config.py`, used in `answer.py`, `judge.py`).
- Regression found by a fresh eval of the 00:22 code (`20261015-010229.json`: table numeric 0.87 -> 0.67, citation 0.60 -> 0.27, numeric 0.86 -> 0.71 overall). Cause: `year_rows` (rewrites year-header tables as `label: 2025=value`) + larger caps. A/B on q004/q005: wrong with it, right without. Now opt-in (`YEAR_ROWS=1`, default off); `PAGE_CAP` 3000, `CONTEXT_CHARS` 16000 restored (eval 8 values).
- Final eval (`eval/runs/20261015-012031.json`, `qwen2.5:7b-gpu`): recall 0.92, citation 0.56, refusal 0.96, numeric 0.86, judge 0.82, faithful 0.93, 18.1 s/q. vs eval 8: same or better on every overall metric. cross_doc judge 0.43, refusal 0.88, citation 0.00 (strict metric).
- Remaining misses: numeric q002, q009, q027, q031; refusal errors q031, q040.
- New: `eval/summarize.py` (markdown tables from run JSONs), `ollama/Modelfile`, README rewritten with results, progression, architecture, setup, limitations.
- pytest: 11 passed.

## Next
1. Phase 3 (ROADMAP): MCP tools + planner/executor/verifier agent; grow the benchmark with a held-out split (the 50 seed questions were used for development).
2. Housekeeping: rotate the Gemini key (it was pasted in chat); make Ollama env permanent; lid action = Sleep manually; `git init` not done (project is not a git repo).

## Addendum (01:45): decisions, lessons, pending
- Decisions: `year_rows` kept in code but opt-in (rejected as default: hurts the 7B); no cross_doc tuning (n=8, noisy); no git/publish actions taken (user must decide).
- Lessons: `python -m telaah.cli` does nothing (no `__main__` guard); use `.venv/Scripts/telaah.exe`. In Git Bash `powercfg /change` is mangled (path conversion); use PowerShell. Always re-run a full eval after any answer.py edit before quoting numbers. Watch a running eval for stalls (log mtime) because of the repetition-loop bug.
- Running/pending: nothing running. Power: idle sleep restored to 10 min. Ollama env still session-only.

# Update - 2026-10-15: Phase 3 week 7, MCP tools

## Done
- `src/telaah/tools.py` (plain functions): `list_documents`, `search_documents`, `read_page_text`, `read_page_image`, `calculate` (AST whitelist, no eval), `check_citation` (page exists + every claim number occurs on the page, ID/EN separators both tried).
- `src/telaah/mcp_server.py`: FastMCP stdio server exposing the 6 tools; entry point `telaah-mcp` (reinstall with `pip install -e .` to get the script) or `python -m telaah.mcp_server`. Verified over a real stdio client (list_tools, calculate, check_citation).
- `mcp` pinned `<2` (mcp 2.x renamed FastMCP to MCPServer and changed APIs).
- `tests/test_tools.py`; pytest: 19 passed. `search_documents` / `read_page_image` not unit-tested (need Qdrant/embedder and Gemini).

## Next
1. Week 8: LangGraph planner -> executor -> verifier using these tools; verifier runs `check_citation` on every cited number; tracing (Langfuse or Phoenix).
2. Housekeeping unchanged: rotate Gemini key, Ollama env permanent, lid = Sleep, no git repo.

# Update - 2026-10-15: Phase 3 week 8, planner/executor/verifier agent

## Done
- `src/telaah/agent.py` (LangGraph): plan -> execute -> verify_steps -> (retry once with larger top-k) -> compute -> compose -> verify_final; refuse if no step verified. CLI: `telaah agent "<q>"`, `telaah eval --agent [--types ...]`. Traces (per node, timings, steps, issues) go to `data/agent_traces/<date>.jsonl` (own JSONL tracing; Langfuse/Phoenix NOT added, optional).
- Design decisions: entity questions (`entity_groups`) reuse the tuned `split_question` + per-entity retrieval (`answer.answer_entity`, refactored out of `ask_entities`); other questions use an LLM planner, but a 0/1-step plan keeps the ORIGINAL question (planner rewrites hurt: dropped "bank only", "grafik"). Calculator: LLM writes one expression over facts converted by `plain_numbers` (7B read `61.346.133` as 61346.133), `tools.calculate` evaluates, result formatted Indonesian (`fmt_id`).
- Verifier: only "figures" are checked (numbers with Rp/%/unit word/separator; bare integers, years, dates ignored), a number counts as missing only if NO cited page has it; `repair_text` re-points a citation to a retrieved page that holds the number; figures from vision steps are checked against the vision-augmented context; calculator results are allowed in the final answer; `[a p.1, b p.2]` split into separate cites.
- `ask(question, k=None)` got an optional k. pytest: 28 passed (`tests/test_agent.py` mocks LLM/ask).

## Results (seed 50, same 7B)
- Single-shot RAG (`20261015-012031`): recall 0.92, citation 0.56, refusal 0.96, numeric 0.86, judge 0.82, faithful 0.93, 18 s/q.
- Agent v1 (`20261015-034304`): numeric 0.68, refusal 0.78, chart recall 0.20 (verifier too strict on dates/article numbers; planner dropped "grafik").
- Agent v2 (`20261015-073337`): recall 0.88, citation 0.68, refusal 0.90, numeric 0.79, judge 0.75, faithful 0.96, ~29 s/q (one 1228 s outlier in unanswerable = stall/sleep?). 32/50 answers fully verified.
- cross_doc (n=8, noisy): judge 0.43-0.57 vs 0.43 RAG, citation 0.62 vs 0.00 (repair_text + page-level cites), refusal 0.88 both.
- Regressions v2 vs RAG: q005 (table numeric), q026 (text refusal), q030 (chart numeric), q050 (unanswerable answered; verified=True because the number was on a page, so number-on-page != right indicator).
- Takeaway: on single-fact seed questions the agent does not beat single-shot RAG (extra LLM hops + 7B errors); its case rests on multi-step tasks (Week 9 agent benchmark). Verifier checks that figures exist on the cited page, NOT that the right indicator was read (BCA CAR 25,8 passed).

## Lessons
- Do not let the agent rewrite already-simple questions; reuse the tuned prompts. Never put `\b` through shell heredoc/`python -` strings (became a backspace char); use the Edit tool.
- `faithful` judge returns None for agent runs on long cross-doc contexts (context > 7B window); use `verified` instead.
- A full agent eval takes ~25-30 min; run it in background and poll.

## Next
1. Week 9: write 60 multi-step agent tasks (e.g. NPL trend of 3 banks 2021-2025), run RAG vs agent, report success rate, steps, cost, failure types; then 450-question benchmark and Gradio demo on HF Spaces.
2. Optional: stronger verifier (indicator check via the LLM), investigate q050/q026, Langfuse tracing, router that sends single-fact questions to plain RAG and only multi-step ones to the agent (likely the best fix for the regressions).
3. Housekeeping unchanged (Gemini key rotation, Ollama env, lid = Sleep, no git repo). Logs `agent_*.log` in project root can be deleted.

# Update - 2026-10-15: router default + 60 agent tasks written

## Done
- `src/telaah/router.py`: rule-based router (no extra LLM call): agent for entity comparisons (`entity_groups`), `selisih/perbedaan/berapa kali/total gabungan`, and multi-year trends; else plain RAG. `telaah ask` uses it by default (`--rag` to bypass); `telaah eval --router [--ids ...]`. pytest: 30 passed.
- Full eval with router (`eval/runs/20261015-080930.json`): recall 0.92, citation 0.62, refusal 0.96, numeric 0.89, judge 0.82, faithful 0.93, 19.5 s/q (RAG 0.92/0.56/0.96/0.86/0.82/0.93/18 s; agent v2 0.88/0.68/0.90/0.79/0.75/0.96/29 s). 42 questions to RAG, 8 to agent (7 cross_doc + q027). Numeric +0.03 = 1 question, within noise; the 50 seed questions were also used to develop the router.
- `eval/build_agent_tasks.py` -> `eval/agent_tasks.jsonl`: 60 multi-step tasks (ranking 12, trend 10, multi_trend 10, compute 14, regulation 8, unanswerable 6). All gold figures are parsed from the cited pages in `data/processed` and derived numbers (gaps, growth, sums, ratios) are computed in the script; unanswerable tasks assert their key terms are absent from the corpus. Fields: `gold_answer`, `gold_numbers` (Indonesian-format strings to find in the answer), `gold_facts` (doc, page, value), `gold_pages`, `min_steps`, `answerable`. Rerun the script to regenerate/re-verify.
- Source tables: bri_2025 p26-32, btn_2025 p21-28, bca_2025 p15-16, mandiri_2025 p36-40, bni_2025 p28-29; regulations POJK 11/2016 p7/p14, PADG 23/2025 p7/p8 (checked by regex in the script).

## Next
1. Write `eval/run_agent_tasks.py`: per task success = all `gold_numbers` present in the answer (and refusal for unanswerable), plus steps, seconds, failure type (refused / missing number / wrong number), for RAG vs agent vs router. Iterate on a subset (--ids) first, full run once.
2. Spot-check the gold of a few tasks by eye on the PDF pages (the script checks parsing, not table-column semantics for BNI/Mandiri).
3. Housekeeping unchanged: rotate Gemini key, Ollama env permanent, lid = Sleep, no git repo.

# Update - 2026-10-15 (10:10): agent-task fixes, Gemini experiment, 3 x 60-task runs in progress

## Done
- `src/telaah/router.py` + `telaah ask` uses it by default (`--rag` bypasses); `telaah eval --router --ids ...`. `agent.DERIVE_RE` (hitung/dibagi/gabungan/dua desimal/selisih) sends arithmetic questions to the agent; planner has few-shots that split growth/sum/ratio into one raw figure per step; calculator prompt knows units (BRI/Mandiri/BTN juta Rp, BCA/BNI miliar Rp).
- `eval/build_agent_tasks.py` -> `eval/agent_tasks.jsonl` (60 tasks, gold parsed from pages). Questions end with "Gunakan data dari Laporan Tahunan 2025 masing-masing bank" (prior-year columns are restated between reports); profit tasks say "laba tahun berjalan konsolidasian (total, ...)" because Mandiri attributable profit (~56 T) differs from total (61.346.133 juta).
- `eval/run_agent_tasks.py` (modes rag|agent|router, `--ids`, `--cats`, `--compare`), scores by gold_numbers present in answer; logs LLM name in config. `tests/test_agent_tasks.py`, `tests/test_router.py`, `tests/test_step_retrieval.py`; pytest 42 passed.
- Retrieval fixes for one-figure steps: `answer.refine_step` (adds "(konsolidasian)" + "menurut Laporan Tahunan YYYY"), `filters.SOURCE_RE` (named source report beats other years), `answer.excerpt` (question-aware page window when the row lies beyond the 3000-char cap), `retrieve.expand_aliases` (NPL/CAR/KPMM/LDR/NIM/BOPO/CASA long forms for BM25 only; `TELAAH_ALIASES=0` disables). `eval/step_retrieval_check.py`: retrieval-only check, 7/12 -> 11/12 figures in context (alias gave the last +1). retrieval_eval `+summary` unchanged (0.85 overall) with aliases on/off.
- LLM client knobs: `LLM_MAX_RETRIES`, `LLM_MIN_INTERVAL` (throttle; Gemini flash-lite free tier = 15 requests/min per project per model; use 4.5). Any OpenAI-compatible LLM works via `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `MAX_ANSWER_TOKENS=2500` for Gemini.
- Gemini key rotated: new key in `.env`, old key deleted by the user. The new key was also pasted in chat once (consider rotating again, low urgency).

## Results
- Router on 50 seed questions (`eval/runs/20261015-080930.json`): recall 0.92, citation 0.62, refusal 0.96, numeric 0.89, judge 0.82, faithful 0.93, 19.5 s/q (RAG 0.92/0.56/0.96/0.86/0.82/0.93; agent v2 worse).
- 8-task dev subset (t001 t013 t023 t033 t037 t041 t047 t055; these were used to tune, so optimistic): 7B router 1/8 -> 4/8 after fixes; Gemini router 4/8 -> 8/8 (`tasks-router-20261015-091125.json`). Conclusion: most earlier failures were 7B limits plus step retrieval, not agent design.
- 60 tasks, RAG biasa 7B (`eval/runs/tasks-rag-20261015-093405.json`): success 0.383 (23/60), partial 0.52, pages_hit 0.87, 19.8 s/task. By category: ranking 0.33, trend 0.50, multi_trend 0.00 (9 refusals), compute 0.21, regulation 0.63, unanswerable 1.00.

## Lessons
- Embedded Qdrant allows ONE process at a time: never run two evals in parallel (second fails with "already accessed by another instance"). Chain runs sequentially.
- Gemini free tier 429 even with 8 retries when an agent fires several calls per second; the throttle fixes it.
- In PowerShell, stderr from native commands shows as NativeCommandError; judge by the printed results, not that text.
- Do not claim a fix helps before measuring it (alias claim was verified later: NPL BTN 2021 OK only with aliases).
- Known retrieval miss left: BCA "laba bersih" 2024 (p15 loses to EPS pages p17/p18).

## Running/pending (do NOT stop Ollama, sleep the PC, or start another eval)
- Background chain, log `C:\Users\User\AppData\Local\Temp\claude\C--Users-User-genai-project\d0e8220c-4349-44ec-9ea5-fa50b9b0f71c\tasks\bxql0uoa9.output`: run 1/3 rag 7B DONE; run 2/3 router 7B at task 41/60 at 10:09 (ends ~10:20, file `eval/runs/tasks-router-<ts>.json`); run 3/3 router Gemini (throttled 4.5 s, ends ~10:55, same naming, config.llm = gemini-3.5-flash-lite). Chain prints "##### ALL DONE" at the end. /clear does not stop it.

## Next
1. When both files exist: `.venv/Scripts/python eval/run_agent_tasks.py --compare eval/runs/tasks-rag-20261015-093405.json eval/runs/tasks-router-<7B>.json eval/runs/tasks-router-<gemini>.json` and report per category (success, partial, steps, s/task, failures). Honest framing: the 8 dev tasks inflate router numbers slightly; 52 tasks are unseen.
2. Look at failure types of the router runs (refused / partial_numbers / no_gold_number) and fix the most frequent; model: Sonnet 5.5 (Opus 5.5 only for a verifier redesign).
3. Then: benchmark growth to 450 questions with a held-out split (Opus 5.5 for the design), Gradio demo on HF Spaces. Housekeeping: Ollama env permanent, lid action = Sleep, no git repo, delete `agent_*.log` in project root.

# Update - 2026-10-15 (13:00): run 3 crashed on Gemini daily quota; new plan; git + resumable task runs

## Results
- Run 2 router 7B (`eval/runs/tasks-router-20261015-101830.json`): success 0.267 (RAG 0.383). compute 0.43 (RAG 0.21) but trend 0.00 (0.50), regulation 0.13 (0.63). All 19 refusals were agent route, pages_hit 0.93: right pages found, 7B fails to read/synthesize.
- Run 3 router Gemini stopped at task 41: free tier = 500 requests/day/model (429 GenerateRequestsPerDay). Rebuilt t001-t040 from the log into `eval/runs/tasks-router-20261015-101935-gemini.partial.jsonl` (scores only, answers empty, `reconstructed_from_log`). Same 40 tasks: Gemini router 0.70, RAG 7B 0.275, router 7B 0.175. Conclusion: agent design works; the 7B is the bottleneck.

## Done
- `git init`, baseline commit `61a8f85` (.gitignore + bm25.pkl, agent_traces, *.log, .bak_pre_colpali). `.env` not committed; staged files scanned for keys.
- `eval/run_agent_tasks.py`: appends each task to `<run>.partial.jsonl`; on any exception (quota/network) it stops cleanly and still writes `<run>.json` with `incomplete` + `error`; `--resume <partial>` runs only missing tasks. Tested with a fake model (crash at task 3, resume completes). pytest 42 passed.

## Plan (agreed direction: keep what works, minimum risk, compact steps)
Keep: hybrid retrieval, filters, ColPali + Gemini vision, eval harness, verifier idea.
1. DONE: safety net (git, resumable runs).
2. Generator: API model as main LLM (paid tier, or another provider); 7B only offline fallback. Needs user decision on provider/cost.
3. Structured facts table (SQLite: bank, year, indicator, value, unit, doc, page) built at ingest, reusing the parsing in `eval/build_agent_tasks.py`; trend/ranking/compute = lookup + Python arithmetic. Design with Opus 5.5.
4. Replace regex routing with one LLM query-parser call returning JSON (banks, years, indicator, operation, chart, regulation).
5. Freeze a held-out test split before more tuning.

## Next
- Finish Gemini run when quota resets (~07:00 on 2026-10-16): `.venv/Scripts/python eval/run_agent_tasks.py --mode router --resume eval/runs/tasks-router-20261015-101935-gemini.partial.jsonl` with the Gemini env (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL, LLM_MIN_INTERVAL=4.5, MAX_ANSWER_TOKENS=2500).
- Then step 2 decision, then step 3.

# Update — 2026-10-15 (afternoon): decisions on LLM cost; next = router fix (local, free)

## Done
- Power: idle sleep + hibernate = Never on AC and DC (`powercfg /change ... 0`, verified). Lid action not settable by powercfg on this Acer: keep lid open or set "Do nothing" manually. Undo: `powercfg /change standby-timeout-ac 10` / `-dc 10`.
- Correction to the 13:00 entry: the Gemini quota resets ~07:00 on 2026-10-16 (429 said "retry in 18h6m" at 12:53).

## Decisions
- Paid Gemini: user leaned to "Gemini paid tier" but then chose to continue TODAY free and local only (7B, no API). Gemini key stays reserved so tomorrow's 500 free requests finish the Gemini run.
- Gemini paid facts (checked 2026-10-15): no trial credit usable for AI Studio Gemini API ($300 GCP credit excluded for accounts after 2026-03-02; it only covers Vertex AI). `gemini-3.5-flash-lite` paid = $0.30 in / $2.50 out per 1M tokens (Batch -50%). Tier 1 = link billing, $250/month cap. Estimate (unmeasured): ~$1.5 per full 60-task agent run, ~$0.2 per seed eval, ~$70-130 for the whole roadmap (most in Phase 4 synthetic data + 600-question evals). If enabled: budget alert ~$20/month.
- Today's direction: work that does not need a strong LLM. Router fix first, then facts table (step 3), both on the 7B.

## Next
1. Router fix (`src/telaah/router.py`, maybe `agent.DERIVE_RE`): send `regulation` and single-bank `trend` tasks to plain RAG (7B router: regulation 0.13 vs RAG 0.63, trend 0.00 vs 0.50; see `eval/runs/tasks-router-20261015-101830.json` failures, e.g. t051 PADG threshold). Keep compute/ranking/multi_trend on the agent. Add router tests, pytest, commit. Test: `.venv/Scripts/python eval/run_agent_tasks.py --mode router --cats regulation trend` (7B, ~18 tasks, background), compare with `--compare` against the rag and router-7B runs. Also check the 50 seed questions' routing does not change (router unit tests / `telaah eval --router` only if routing changed for seed questions).
2. Facts table (SQLite: bank, year, indicator, value, unit, doc, page) parsed by code from the summary pages (reuse `eval/build_agent_tasks.py` parsing), `lookup_facts` agent tool, fallback to RAG when not covered. Subset of 10 tasks, then full 60 on 7B in background. Then one seed eval to confirm no regression. Model: Opus 5.5 for the design.
3. 2026-10-16 after 07:00: finish Gemini run with `--resume eval/runs/tasks-router-20261015-101935-gemini.partial.jsonl` (Gemini env vars, `LLM_MIN_INTERVAL=4.5`); do not use Gemini for anything else before it.
- Rules: commit before each change; one eval process at a time (Qdrant lock); keep Ollama running.

# Update - 2026-10-18: router fix + Gemini 60-task run complete

## Done
- Router (`c7b09c1`): questions naming POJK/PADG/PBI/SEOJK and single-bank trends go to plain RAG; `TREND_RE` removed. Changes 18 tasks (t013-t022, t047-t054) and 1 seed question (q036). pytest 43 passed.
- 7B check, regulation+trend (`eval/runs/tasks-router-20261018-115642.json`, 18 tasks): success 0.50 (regulation 0.50, trend 0.50; old router 0.125/0.00, RAG 0.625/0.50), 17 s/task.
- Gemini router run finished via `--resume` (`eval/runs/tasks-router-20261015-101935-gemini.json`, 60/60): success 0.733, partial 0.80, pages_hit 0.90. By category: compute 0.64, multi_trend 0.80, ranking 0.58, regulation 0.75, trend 0.80, unanswerable 1.00. Failures: refused 9, partial_numbers 5, no_gold_number 2. Caveats: t001-t040 used the OLD router and were rebuilt from the log (answers empty); t041-t060 used the new router (regulation on RAG). s/task 160.9 is inflated by the old throttled/retry tasks; new tasks were ~20 s.
- Comparison (60 tasks): RAG 7B 0.383, router 7B (old) 0.267, router Gemini 0.733.

## Next
1. Facts table (SQLite: bank, year, indicator, value, unit, doc, page) + `lookup_facts` agent tool, reusing `eval/build_agent_tasks.py` parsing; design with Opus 5.5. Subset of 10 tasks on 7B, then full 60.
2. Optional: full 60-task router run on 7B with the new router (projected ~0.38-0.40, unmeasured).
3. Housekeeping: restore power settings (`powercfg /change standby-timeout-ac 10` / `-dc 10`), lid action manually; delete `eval/runs/*.partial.jsonl.bak` once happy.

# Update - 2026-10-18 (13:15): facts table + facts sheet -> 7B 0.90 on the 60 agent tasks

## Done
- `src/telaah/facts.py`: generic extractor over every markdown table of the bank reports (year header row, label aliases per indicator, no per-page spec), skips segment/subsidiary tables, coverage ratios (LLR/NPL), negative balance cells, nominal rows named like a ratio. 997 facts in `data/facts.sqlite` (gitignored; `python -m telaah.facts`). 14 indicators: npl_gross/net, car, tier1, cet1, ldr, nim, bopo, casa, roa, roe, total_aset, laba, ekuitas. DPK and total loans left out on purpose (rows spread over segment/sub-total tables, lookups were wrong).
- Lookup: named report else latest; value printed on most pages wins, tie -> earliest page. `eval/check_facts.py`: 102/102 gold values, 100/102 gold page. Caveat: aliases written after seeing these reports, not held-out.
- Agent: `answer_step` answers one-figure steps from the table; `sheet` + `derive`: one indicator over banks x years, all in the table -> plan by code, change/growth/order/gap/mean/sum computed in Python in the asked unit; the 7B only writes. Router sends sheet questions to the agent (regulation still RAG). `TELAAH_FACTS=0` disables. Q_SKIP: grafik, kuartal, atribusi, industri, and any scope below the bank (kecamatan, kabupaten, cabang, ...) after t060 hallucinated.
- pytest 53 passed. Commits a834a79 and later.

## Results (7B, 60 tasks; the 60 tasks are now a DEV set: tuned on them)
- `eval/runs/tasks-router-20261018-130101.json`: success 0.90, 11.1 s/task (RAG 0.383, old router 0.267, Gemini router 0.733). ranking 1.00, trend 1.00, multi_trend 1.00, compute 0.86, regulation 0.63, unanswerable 0.83 -> after Q_SKIP fix rerun 6/6 (`tasks-router-20261018-131305.json`), so ~0.917 combined.
- Remaining misses: t039 (7B rewrote 4.249,99 as 4.25), t046 (ratio of two indicators, not a sheet, refused), t048/t051/t053 regulation on RAG.

## Next
1. Seed 50-question regression check with the facts path: `telaah eval --router` (q033/q034/q035/q037 now use the sheet; q038 skipped on purpose). ~16 min, background.
2. Freeze a held-out task set (new banks/years/indicators combos, written before looking at results) before quoting final numbers; Opus 5.5 for the design.
3. Optional: final answer template for sheet questions (avoid 7B number rewriting, t039); two-indicator ratios (t046) in `derive`.
4. Housekeeping: restore power settings, delete `eval/runs/*.bak`.

## Seed check with facts path (2026-10-18 15:37, `eval/runs/20261018-153747.json`)
- vs router 20261015-080930: recall 0.92 -> 0.94, citation 0.62 -> 0.64, judge 0.82 -> 0.89, numeric 0.89 -> 0.82, refusal 0.96 -> 0.92, faithful 0.93 -> 0.88, 16.9 s/q.
- Facts-path seed questions q033 q034 q035 q037 q039: judge 5/5, citation 5/5 (q035/q037/q039 were wrong before).
- Drops are RAG path (code unchanged): q002 read p42 (60,64 T) instead of p28 (known flaky), q009 and q030 refused (q030 chart + Gemini vision; rerun: q030 answered but wrong figure). Not caused by the facts change.
- Faithful 0 on sheet questions was the context: full report pages overflowed the 7B context window. Fix: `facts.row_excerpt` (header + fact row, <600 chars) + derived lines in the agent context. Faithful on the 5 sheet questions 1/5 -> 3/5; rest is the 7B judge (q035, q039). These 5 were unscored (None) before, so the faithful average is not comparable.
- Idea: route single-figure questions covered by the table (q002 laba BRI 2025) to `facts.answer_step` too -> fixes the flaky q002 class. Measure on seed + tasks.

## Single-figure questions -> facts table (2026-10-18)
- `router.route` returns "facts" for one bank + one indicator + one year in the table (`facts.answer_step`); falls back to RAG on no hit. No report named -> that year's own report (q010/q011 cite bni_2024 like the gold), sheets keep the latest report.
- 10 seed questions take it (q001 q002 q003 q006 q007 q010 q011 q012 q014 q015): all metrics 1.0 (before: q002 wrong, q003/q011 citation 0), ~5 s/q incl. judge (was ~17 s). No agent task changes route. pytest 54 passed.
- Not yet re-measured: full seed run with all changes (expected: q002/q003/q011 fixed, rest = RAG noise).

## 60 tasks after the q039 step fix (2026-10-18 16:05, `eval/runs/tasks-router-20261018-160536.json`)
- success 0.90 (54/60), 11.5 s/task: ranking/trend/multi_trend 1.00, unanswerable 1.00 (t060 fix holds), compute 0.86, regulation 0.50 (t050 new miss vs 13:01 run; regulation is the RAG path, unchanged code -> 7B noise).
- Remaining misses: t039 (7B rewrote 4.249,99 as "4.25"), t046 (two-indicator ratio, not in derive), t048/t050/t051/t053 regulation on RAG.
- Next: regulation is now the weakest category (all RAG on the 7B); then held-out task set before quoting 0.90.

## Regulation path (2026-10-18 16:30)
- `src/telaah/regulation.py`, route "regulation": regulation threshold vs ONE bank ratio in the facts table. Bank figure from the table; threshold = percentage in a sentence of the full-question RAG answer that cites/names the regulation and is written AS A PERCENT on a regulation page (`states_pct`; a bare "14" on POJK 11/2016 p.43 is an item number), else one stated in the question, else regulation-only RAG (only when the first refused). Difference + above/below in Python, template answer. No threshold typed by hand. No threshold -> plain RAG answer unchanged.
- Regulation tasks 7B: 0.50-0.63 -> 7/8 (`tasks-router-20261018-163007.json`), all threshold citations = gold page. t053 still misses (RAG wrote only 22,6 and no threshold sentence). No seed question changes route (q036 RIM not in the table). pytest 60 passed.
- Projected 60-task total: 0.90 -> ~0.93 (56/60), not measured in one run.

## Held-out set frozen + first run (2026-10-18 16:37)
- `eval/heldout_tasks.jsonl` (40, built by `eval/build_heldout_tasks.py`, rules + hashes in `eval/HELDOUT.md`, commit bfe0fa9).
- First run, 7B router: 0.925 (37/40); dev 0.90. Failures h035 (unknown bank -> answered the known half: serious), h025 (mean over years), h033 (threshold not found). Not fixed: fixing them from this run spends the set (rule 3).
- Decision pending: fix these gaps (then build held-out set #2 before quoting held-out numbers again), or keep the set clean and look for the same gaps in dev/seed first.

## After unknown-bank refusal + mean over years (2026-10-18 17:11, commit 871a3d6)
- Dev 60 (`tasks-router-20261018-164809.json`): 0.95 (57/60). Misses t039 (7B rewrote 4.249,99), t046 (two-indicator ratio), t053 (no threshold).
- Seed 50 (`20261018-171128.json`): recall 0.94, citation 0.70, refusal 0.92, numeric 0.857, judge 0.917, faithful 0.912, 13.5 s/q. q039 fixed; q041/q042 refuse by route "refuse"; q030 (chart, RAG + Gemini vision) refused again: flaky (wrong 15:37, right 16:01), the only cause of numeric/refusal dropping vs 16:01.
- Held-out #1 spent (0.925 on b61f6e4). Next: held-out set #2 (written before running; new wordings + ideally 2024-report sources), then README/results write-up; optional fixes: q030 chart flakiness, t046 two-indicator ratios, t039 final-number rewriting (template the sheet answer).

## Held-out set #2 (2026-10-18 17:20)
- Built + frozen (ea0e29a): 40 tasks, 2024-report sources (2020 figures), restatements, CAGR. First run 0.625 (25/40). Main cause: BRI 2024 header "2020 *)" not parsed (YEAR_CELL) -> BRI 2020 missing -> 7B fallback cites wrong rows (subsidiary table p30, other-basis p197/198). Details in eval/HELDOUT.md. Not fixed yet (would spend set #2).

## Fixes from held-out #2 (2026-10-18 17:55, commit c9c75a5)
- Extractor: footnoted year headers ("2020 *)"), first column wins on duplicate years, skip month/quarter (industry) tables, segment flag carried across page breaks. 795 facts; check_facts 102/102; BRI 2020 figures correct.
- Router: restatement route (one figure, two named reports, template + difference); partial sheets (<= half missing -> RAG steps; no sheet when a missing year is after every report).
- Dev 60: 0.95 (`tasks-router-20261018-173251.json`). Seed (`20261018-175554.json`): only q039 changed (restatement route, faithful 0 -> 1); faithful 0.94.
- README updated: set #2 0.63 quoted as the more honest held-out number; both sets spent.

## Missing-years report + extractor fixes it surfaced (2026-10-18 18:20)
- `facts.coverage()` / `python -m telaah.facts [--coverage]`: per bank report x indicator, years of the 5-year span missing (also printed by every build).
- It found more silent misses, now fixed: merged header cells ("Uraian 2024 2023", "2025 331.743.367", "2023 Pertumbuhan Rp %") -> years in order, row mapped by position; budget tables (Target/Realisasi, mandiri_2025 p362, mandiri_2024 p438) had inherited the previous page's year header (now: inherit only when the table opens with a data row; target/realisasi/RKAP columns skipped); capital components/requirements read as ratios (buffer, "sesuai profil risiko", "Dari CET 1", Tier II).
- 887 facts, check_facts 102/102 value AND page (was 100/102 page). Lookups vs previous commit: 0 changed, 0 lost, 12 added (BTN assets 2021-23 and profit/equity 2023-24 from the 2024/2025 reports, BCA CET1, BNI NPL net). Routing identical, offline dev coverage 41/41 -> dev/seed evals not rerun (same lookups). pytest 67.
- Remaining gaps (14): mostly real (CET1/Tier 1/NPL net/CASA not published for all years), two empty parsed cells (mandiri_2025 total_aset 2022, btn_2025 nim/bopo 2021).

# Update — 2026-10-18 (evening): handoff summary of today

## Done (all committed, last commit 01e60ea + this note)
- Router fix (regulation/single-bank trend), facts table `src/telaah/facts.py` (generic extractor, lookup, sheets, derive, restatement, unknown-bank refusal, coverage report), regulation path `src/telaah/regulation.py`, router routes: refuse / facts / restatement / regulation / agent / rag.
- Held-out sets: `eval/heldout_tasks.jsonl` (#1) and `eval/heldout2_tasks.jsonl` (#2), builders `eval/build_heldout*_tasks.py`, rules + runs in `eval/HELDOUT.md`. BOTH SPENT.
- README rewritten for Phase 3 results; `eval/run_agent_tasks.py --tasks`.

## Results (7B qwen2.5:7b-gpu)
- Dev 60 tasks: RAG 0.38 -> 0.95 (`eval/runs/tasks-router-20261018-173251.json`). Gemini router was 0.73.
- Held-out #1 0.925 (b61f6e4), held-out #2 0.625 (ea0e29a; quoted in README as the honest number). Fixes from both since.
- Seed 50 (`eval/runs/20261018-175554.json`): recall 0.94, citation 0.70, refusal 0.92, numeric 0.857, judge 0.917, faithful 0.941, 13.2 s/q.
- Facts: 887 rows, 14 indicators, check_facts 102/102 value+page; coverage report: 14 gaps, mostly real.

## Decisions
- No hand-typed thresholds or gold-spec reuse in the system; gold only via builders.
- Held-out sets spent once a result motivates a fix; next honest number needs set #3 written by someone else.
- Last extractor changes (merged headers, budget tables, capital rows) not re-evaluated end-to-end: lookups vs previous commit 0 changed / 12 added, routing identical.

## Lessons
- Bash heredocs with python containing `\b`, `\n` or `)` broke edits several times: use Edit/Write or a script file in the scratchpad.
- Silent extractor gaps are the main risk (header formats); always run `python -m telaah.facts` and read the coverage list after changes.
- Never run two evals at once (embedded Qdrant lock). Evals use 4-7 GB RAM.

## Running/pending
- Nothing running. Power settings still "never sleep" (restore: `powercfg /change standby-timeout-ac 10` and `-dc 10`). NVIDIA Overlay restarts until disabled in the NVIDIA App.

## Next
1. Held-out set #3 written by someone other than Claude (or real user questions); run once, report.
2. t039: template the final answer for sheet questions (7B rewrites numbers); t046: two-indicator ratios in `facts.derive`.
3. q030 chart flakiness (Gemini vision path); fill parse gaps (mandiri_2025 total_aset 2022, btn_2025 nim/bopo 2021) from another report.
4. ROADMAP Phase 4 (benchmark growth) + Gradio demo.

## Ratio route + total guard (2026-10-18 night)
- `facts.ratio_sheet`/`derive_ratio`: two money indicators joined by "dibagi" (laba / total aset), per bank in Python; `agent.plan` uses it, `compose` keeps the calculator's "Total gabungan" figure (t039), appends per-bank ratios, and replaces a 7B refusal with the computed lines (t044).
- Dev 60: 0.95 -> 0.967 before the t044 fix (`tasks-router-20261018-224430.json`); t039/t044/t046 all 1.0 after (`...-225615.json`); remaining miss t053 (regulation threshold). Seed not rerun (no seed question uses the ratio route). pytest 68.
- Next: set #3 by someone else; parse gaps (mandiri_2025 total_aset 2022, btn_2025 nim/bopo 2021); q030 chart flakiness; Phase 4 + Gradio.

# Update — 2026-10-18 (night): ratio route, handoff

## Done
- Commit 3f951e0: `facts.ratio_sheet`/`derive_ratio` (laba / total aset in Python), `agent.plan` ratio branch, `agent.compose` guards (keep "Total gabungan" figure, append per-bank ratios, replace 7B refusal with computed lines), test in `tests/test_facts.py`.

## Results
- Dev 60: 0.95 -> 0.967 (`eval/runs/tasks-router-20261018-224430.json`); t039/t044/t046 = 1.0 after the t044 fix (`...-225615.json`, not a full rerun, est. ~0.98). Miss left: t053. pytest 68. Seed not rerun.

## Decisions
- Ratio answers use the calculator lines as the answer when the 7B refuses (figures come from table rows).
- Held-out sets #1/#2 spent; set #3 must be written by the user or real questions.

## Lessons
- Run Python via `.venv/Scripts/python.exe` (bare `python` lacks telaah). Pyright "not required key"/import warnings are noise.

## Running/pending
- Nothing running. Power settings still "never sleep".

## Next
1. Parse gaps: mandiri_2025 total_aset 2022, btn_2025 nim/bopo 2021 (check `python -m telaah.facts`).
2. Phase 4 benchmark design (~450 questions, held-out split; use Opus 5.5), held-out #3 by the user.
3. Gradio demo on HF Spaces. Optional: q030 chart flakiness.

## Parse gaps checked (2026-10-21)
- mandiri_2025 total_aset 2022: source cell is empty (p36). btn_2025 nim/bopo 2021: source row misaligned (BOPO cell reads "3,99 89,28", NIM 2021 blank, p28). Both are defects in the PDFs, not extractor bugs.
- `facts.lookup` already answers all three from the 2024 reports (mandiri_2024 p30 1.992.544.687; btn_2024 p27 NIM 3,99, BOPO 89,28), so no answer is affected. No code change; the 14 coverage gaps are accepted as real/harmless.
- Next: Phase 4 benchmark design (Opus 5.5), held-out #3 by the user, Gradio demo.

# Update — 2026-10-21: Phase 4 started (benchmark v1 tools)

## Done
- Design `eval/BENCHMARK.md`: 600 = 450 dev (incl. 50 seed) + 150 test; per-type quotas; split fixed per PAGE by hash before drafting; tuned pages (seed/agent/held-out golds) never test; Claude never reads the test split (memory saved).
- Tools in `eval/bench/`: `common.py`, `sample_pages.py` (490 pages/pairs -> `pages.jsonl`, 125 test), `draft.py` (Gemini, image + text, JSON, auto-filter, resumable, throttled), `review_app.py` (Gradio 6.30, port 7861, accept/fix/reject + unanswerable tab), `gold.py` (calc golds in Python), `build.py` (quotas -> dev.jsonl/test.jsonl + sha256).
- `telaah eval --file eval/bench/dev.jsonl`; run logs now have `by_type`; bench runs saved as `eval/runs/bench-<split>-*.json`. gradio installed (`[bench]` extra). pytest 68.

## Blocker
- Gemini key in `.env` is INVALID (400 API_KEY_INVALID, even on gemini-3.5-flash-lite). The user must create a new key at aistudio.google.com/apikey and put it in `.env` as GEMINI_API_KEY themselves (not in chat). The chart path of the system (vision) is also off until then.

## Next
1. New key -> `.venv/Scripts/python eval/bench/draft.py --limit 10 --kinds table_lookup` and check DRAFT_MODEL exists; read only candidates_dev.jsonl for quality, tune prompts; then full draft (~490 requests, ~37 min, 1 day of quota).
2. User reviews in the app (~25 h total), writes 20 unanswerables. Then build.py, freeze hashes in BENCHMARK.md.
3. Dev eval per type; test only at milestones. Then SFT data (roadmap week 10).

## Drafting round 1 done (2026-10-21)
- 490 pages drafted with gemini-3.5-flash-lite (flash is 20 req/day free): 336 dev + 136 test candidates (counts only for test), ~90% pass the auto-filter. Draft quality on dev trial OK.
- Shortfall vs quotas even if every draft is accepted: chart (dev 27/62, test 14/23), cross_doc (dev 28/60, test 9/22), calculation dev 54/68. Need round 2: more chart/cross_doc/calc pages (rerun sample_pages with larger COUNT, new ids) after seeing the user's accept rate.
- Next: user reviews in `.venv/Scripts/python eval/bench/review_app.py`; then round 2; unanswerables (user writes).

## Dev review by Claude (2026-10-21)
- The user delegated the DEV review to Claude (test stays with the user, unread). `bulk_review.py` records decisions (`reviewer: claude`); `dev.jsonl` now 260/450. Shortfalls: table_lookup 34, chart 36, calculation 41, cross_doc 57, regulation 10, unanswerable 12.
- Findings: Gemini flash-lite drafts need heavy rejection for table questions (positional "baris pertama", unit unclear), cross_doc (units/periods differ), calc (year columns unclear). One chart gold was wrong (series mix-up), caught by viewing the image.
- Round 2 (next, needs fresh Gemini quota): more table/chart/calc/regulation pages; cross_doc better built from two same-indicator table rows of two banks (maybe via the facts table + page check) instead of free drafting. Unanswerables: user (12 dev + 8 test), or Claude drafts the dev ones if delegated.
- Test split: 136 candidates unread; the user reviews them in `review_app.py` (Test radio).

## Dev unanswerables + cross_doc from facts (2026-10-21)
- `user_dev.jsonl`: 12 unanswerables drafted by Claude (absence regex-checked). `eval/bench/crossdoc_from_facts.py`: facts-table pairs -> candidates (dev reviewed by Claude: 68 accepted, 8 rejected for wrong row labels). Dev = 329/450. No test pairs possible this way (pages tuned or dev): test cross_doc needs round-2 Gemini drafts on test pages or the user.
- Next: round 2 drafting (table 34, chart 36, calc 41, regulation 10 short on dev; test shortfalls cross_doc 22, chart ~9) after the Gemini daily reset; then user reviews the test candidates.

## Round 2 drafting (2026-10-21 evening)
- `sample_pages.py --round 2` -> `pages2.jsonl` (430 pages, ids q0001..q0430; cross_doc pairs test-only). `draft.py --pages pages2.jsonl` stopped after 12 pages: Gemini flash-lite daily quota (500/day) already used by round 1 + tests. Resume after the reset (earlier note: ~07:00 local): `.venv/Scripts/python eval/bench/draft.py --pages pages2.jsonl` (418 pages left, ~35 min).
- Reviewed the 16 new dev table drafts: 5 accepted (stage/composite tables are ambiguous). Table yield is low; consider fewer table pages / more text-heavy tables.

# Update — 2026-10-22 (night): dev eval, gold pages, retrieval boost

## Dev eval of the new non-seed, non-chart questions (258, router, 7B; `eval/runs/bench-dev-20261021-180735.json`)
- recall@5 0.61, citation 0.51, refusal 0.78, numeric 0.37, judge 0.87, faithful 0.84. Weak: calculation (recall 0.15, 35 s/q), table_lookup 0.41, text_fact 0.45. Strong: cross_doc 0.98, regulation 0.80, unanswerable 1.0.
- Run was resumed after a crash (`--resume <partial.jsonl>`; use `.venv/Scripts/telaah.exe eval ...`, `python -m telaah` does not work). New flag `--judge-on-fail`: skips the LLM judges when numeric match + gold page retrieved + cited already pass (judge averages then cover harder questions only; not comparable with older runs).

## Extra gold pages (duplicated facts)
- ~20 of the 70 table/text recall failures were correct answers citing another page with the same fact. `eval/bench/extra_gold.py` finds those pages (gold text + >=50% of question words; >5 matches = generic, dropped) -> `eval/bench/extra_gold_dev.json` (56 questions, 98 pages). `run_eval.py` reads `extra_gold_<stem>.json` beside the question file (dev only). Rebuilding dev.jsonl -> rerun extra_gold.py. `--rescore <run.json>`: citation_acc with extras (table 0.35->0.46, text 0.30->0.36).
- Old runs (before this) are not comparable on recall/citation.

## Retrieval: the front-page summary boost hurts detail questions
- Retrieval-only recall@5 on 186 dev questions (extra gold): current default 0.570; no summary boost (+quota) 0.763. Grid SUMMARY_N,TABLE_N (seed / dev): 8,4 0.90/0.57 · 4,4 0.85/0.66 · 2,4 0.85/0.68 · 0,4 0.85/0.72 · 2,2 0.78/0.71 · 0,0 0.43/0.76. TABLE_N is what the seed needs (0,0: seed table_lookup 1.0 -> 0.13).
- APPLIED: `retrieve.SUMMARY_N = 0` (0 skips the ranking), TABLE_N stays 4. pytest 68.
- Seed eval after (`eval/runs/20261021-234733.json`): recall 0.94 (same), citation 0.70->0.74, refusal 0.92->0.94, numeric 0.857->0.821, judge 0.917->0.865, faithful 0.941->0.971. Changed: q004/q036/q050/q030 better; q018 was noise (fine on rerun); q005 (BRI EPS, gold 376 p.29) now WRONG: p.29 still rank 1 but pp.334/1389 replace the front pages and the 7B answers 398 from p.334. Seed latency 13 -> 21 s only from chart questions q028-q032 (60-121 s; probably the invalid Gemini key, not checked).
- Fix idea for q005: put EPS in the facts table. Not done.

## Agent tasks 60 re-run with SUMMARY_N=0 (2026-10-22)
- `eval/runs/tasks-router-20261022-094842.json`: success 0.983 (59/60) vs 0.967 before (`...224430.json`); t044 compute fixed, nothing worse; regulation 7/8 (one partial_numbers). 11.2 s/task. Dev-tuned set: shows no regression, not generalisation.
- Dev 258 re-run with new retrieval (`bench-dev-20261022-001829.json`): recall@5 0.75, refusal 0.78->0.85, numeric 0.37->0.41, citation (extra gold, both sides) 0.51->0.61; text_fact refusal 0.68->0.87, numeric 0.51->0.66. Weak still: calculation (recall 0.30, numeric 0.22, 34 s/q), table_lookup judge 0.44.

## Drafting round 2 blocked by Gemini quota (2026-10-22 10:04)
- `draft.py --pages pages2.jsonl` drafted 1 page (q0013) then "daily quota reached" at 10:04 local. The earlier "reset ~07:00" note was wrong: it has not reset by 10:04. Free-tier daily quotas usually reset at midnight Pacific time (likely mid-afternoon here, unverified). Retry once after ~15:00 local; do not loop on it.

# Update — 2026-10-22 (afternoon): reranker and calculation experiments (both closed, nothing kept)

## Reranker (retrieval-only, GPU: `TELAAH_DEVICE=cuda`, Ollama stopped)
- Recall@5 with SUMMARY_N=0 (seed 40 answerable / dev 186 non-seed with extra gold): current 0.850 / 0.720 · full rerank 0.375 / 0.855 · A (rerank only if route=="rag") 0.675 / 0.823 · B (RRF blend of fused + rerank order) 0.550 / 0.844 · C (B only on rag route) 0.775 / 0.833. 23 of 40 seed questions are on the rag route, so limiting to RAG does not protect the headline questions. Pass rule (seed >= 0.85 AND dev >= 0.80) failed by all -> reranker stays OFF.
- Gold page is usually in the top 25 (dev @10 0.74-0.89, @25 0.89-0.96): the order is the problem, but the reranker also moves summary-table pages out. A future try: rerank only after the facts table says no.

## Calculation diagnosis (27 dev questions, `eval/bench/_calc_diag.py`, uncommitted scratch)
- 6 correct, 14 a step misses the gold page, 4 page found but the 7B misread/refused, 2 steps right but final wrong (RAG did the arithmetic), 1 plan problem. Gold wrong: 0 (all figures are on the gold page).
- Agent route: full question finds gold in top 5 for 12/19, but every step hits it for only 4/19. Both years are usually on ONE page (later report prints the prior year), so the per-year step queries lose it.

## Tried and REVERTED (all 27 calc questions, router, judge-on-fail; numeric original 0.222)
- A: each step also reads the whole question's pages (interleaved, 6 pages): 0.185, refusal 0.70->0.59. Retrieval-only said all-steps-hit 4->11 of 19, but it did not become answers.
- B: growth questions (pertumbuhan/kenaikan + 2 years) -> agent: 0.111 (26 on the agent, 3 right). The 7B does growth arithmetic better on plain RAG than through the agent steps. It also moved agent tasks t058/t059 (unanswerable) to the agent.
- A+B: 0.185. Runs differ by 1-2 questions without code change (bd0154/bd0156 flip): noise on n=27, so only large effects count.
- Conclusion: for calculation the bottleneck is the 7B reading figures, not retrieval. `git checkout` restored the code; pytest 68.
- Ideas not tried: give the 7B the table row only (excerpt) for steps; put line items from notes into the facts table; Gemini for the calculation steps.

## Drafting round 2: still blocked by the Gemini daily quota at 10:04 (one try after ~15:00 local).

# Update — 2026-10-22 (noon): two-year read (kept, OFF) and numeric_match fix

## Two-year read (`src/telaah/twoyear.py`, switch `TELAAH_TWOYEAR=1`, default OFF; router hook only for rag/agent paths)
- Idea: one bank, two years, growth or difference -> ONE retrieval + ONE JSON read of both numbers + Python arithmetic, fall back to the normal path if any check fails (page retrieved, both numbers on the cited page).
- Upper limit (retrieval-only, 27 dev calc): both gold figures in the prompt for 16/27 (gold page in top 5: 13/27).
- Run with the switch on (`bench-dev-20261022-115925.json`) was invalid: the 7B writes doc as "btn_2024 p.25", the parser rejected it (fixed, test added). After the fix, direct check on the 23 questions of this shape: 2 right (+1 right but mis-scored, see below), 1 real wrong (bd0167 read two other rows on a non-gold page), 19 fall back (figures not in the top-5 pages / 7B says null). Verdict: no meaningful gain (<= +3/27, within noise) -> kept OFF, tests in `tests/test_twoyear.py`.
- Conclusion for calculation: 7B + top-5 retrieval cannot reach the figures for ~11/27; remaining levers are a stronger model for the steps (Gemini, quota-bound) or facts-table line items. Not planned yet.

## `metrics.numeric_match` fix
- Old `_nums` chose the number format once per STRING (any "d.ddd" -> all commas are decimals, else all commas dropped), so "14,76% (nilai 6.139.468)" read 14,76 as 1476 and missed the gold. Now each number token is read on its own (mixed "1.234,56"; "2,416,792"; "14,76" decimal; "1.227" thousands). Tests added (74 pass).
- Effect on saved runs (re-scored, non-cross_doc numeric questions): seed runs 0 changes; dev runs +1 each (bd0038 / bd0152). Old run JSONs keep their old stored scores.

# Plan — Gradio demo on Hugging Face Spaces (2026-10-22, planned, NOT started; user continues later)

Roadmap week 9 deliverable. Needs the user's OK before each step; step 5 (publish) is outward-facing, ask explicitly first.

## Constraint and decisions
- Free Spaces = CPU only (2 vCPU, 16 GB RAM, no GPU). Cannot run the local 7B (Ollama), ColPali (803 MB) or ship `data/raw` PDFs (588 MB, size/copyright).
- Fits: `data/qdrant` 210 MB + `bm25.pkl` 92 MB + `processed` 75 MB + `facts.sqlite` 104 KB (~380 MB, Git LFS).
- LLM on the Space: Gemini through the existing OpenAI-compatible env (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`), key as a Space secret (never in the repo). Free quota 500 req/day is shared by all visitors -> daily-limit message + per-session rate limit. Use a SEPARATE key from the drafting key.
- Same retrieval code (bge-m3 on CPU `TELAAH_DEVICE=cpu`, BM25, facts table, SUMMARY_N=0). ColPali/chart path OFF with a graceful "not available" message. No page images: show the cited page TEXT next to the answer.
- UI: question box, answer with clickable citations, expandable agent-steps panel (route, steps, verified), 6-8 seed examples, short "what this is / tuned on a small set / refuses when unsure" note, loading state (bge-m3 cold start 1-2 min).

## Steps
1. Feasibility, local (~20 min, ~30 Gemini calls): 10 seed questions on CPU with Gemini, ColPali off. Pass: retrieval < 5 s, peak RAM < 12 GB, answers match the 7B on >= 8/10.
2. Build `app.py` (~1.5 h, Opus 5.5): question, answer, citations + page text, steps panel, examples, limit messages. Pass: runs at 127.0.0.1:7860.
3. Local test pass (~30 min): 10 examples, 1 unanswerable, 1 chart question, empty input, Gemini-quota failure. Pass: no crash, clear messages.
4. Package for Spaces (~1 h): `requirements.txt` (no docling/colpali), README/model-card text, LFS data, secret names. Stop and ask before upload.
5. Publish to the user's Hugging Face account (~30 min; needs HF login/token). Pass: Space builds and answers 3 test questions.
6. Notes + commit.

## Risks
- Gemini quota is the same one that blocks round 2 drafting: run step 1/3 only when the quota allows; demo needs its own key.
- Cold start of bge-m3 on a free Space; show a loading state.
- Be honest on the page about quality (tuned on a small set; refusals).

# STATUS (2026-10-22 noon, keep this block current; read it first)
## Done — do NOT redo
- Seed 50 eval with the NEW retrieval (SUMMARY_N=0): `eval/runs/20261021-234733.json` (baseline before: `20261018-175554.json`).
- Agent tasks 60 with new retrieval: `tasks-router-20261022-094842.json` (0.983). Held-out #1/#2 spent.
- Dev 258 new questions with new retrieval: `bench-dev-20261022-001829.json`.
- Reranker variants (rejected); calculation diagnosis; step-pages, growth-route (reverted) and two-year read (kept OFF): all with no gain. Do not repeat.
- Benchmark tools, round 1 drafting (490 pages), Claude dev review, dev unanswerables (12), cross_doc from facts (68), extra gold pages, summary-boost fix, numeric_match fix.
- Round 2 drafting: 14/430 pages (q0001-q0014); q0013/q0014 drafts not reviewed.
- Dev set `eval/bench/dev.jsonl`: 334/450. Test split: candidates only, unread (user reviews).
## Next (in order)
1. Gemini round 2 drafting retry. `draft.py` now remembers the last quota refusal (`eval/bench/.quota_hit`, git-ignored) and a rerun before the expected reset (midnight Pacific = 14:00 local, UTC+7) exits without a request and prints the time; `--force` overrides. Quota was refused at 12:33 on 2026-10-22: `.venv/Scripts/python eval/bench/draft.py --pages pages2.jsonl` (416 pages, ~35 min, resumable). Then Claude reviews the new dev drafts (Opus 5.5).
2. User: review test candidates in `review_app.py` (Test); write 8 test unanswerables.
3. Gradio demo: PLAN WRITTEN above (not started); begin with its step 1 when the Gemini quota allows. Then SFT data (roadmap week 10).
4. Calculation only if a new lever is chosen (see above); EPS into the facts table (seed q005).

# Update — 2026-10-22 (12:45): handoff after retrieval, calculation and demo-planning day

## Done (all committed; last commit 195a4f3)
- Summary boost off (`retrieve.SUMMARY_N=0`), extra gold pages, `--resume` / `--judge-on-fail`, `numeric_match` per-token fix, `twoyear.py` (OFF), `draft.py` quota memory. Details and numbers are in the sections above; the STATUS block ("2026-10-22 noon") is the one to trust.

## Running/pending
- Nothing is running (no Python job, GPU empty, Ollama unloaded).
- Gemini quota refused at 12:33 local; expected reset 14:00 local (midnight Pacific, UTC+7). `draft.py` refuses to run before then unless `--force`.
- Uncommitted: `eval/bench/candidates_dev.jsonl`, `drafted_pages.jsonl` (2 morning drafts, q0013/q0014, not reviewed) and scratch scripts `eval/bench/_*.py` (ablation helpers: `_boost.py`, `_rerank*.py`, `_calc_diag.py`, `_twoyear_check.py`, `_miss.py`, `_retr_dev.py`) — delete or commit as the user prefers. `test.jsonl` / `candidates_test.jsonl` are the blind test split: never read them.

## Working rules the user set (also in memory)
- Plan first, ask consent before EACH step (`plan-then-consent` memory). Models: Opus 5.5 for design/diagnosis/review, Sonnet 5.5 for routine runs.
- One GPU job at a time (6 GB card: the 7B needs ~5 GB, retrieval models ~3.6 GB). `TELAAH_DEVICE=cuda` only for retrieval-only tests with `ollama stop qwen2.5:7b-gpu` first; RAM is tight (15.7 GB, a retrieval test took 7 GB).
- Run long jobs once and check once at the end; `--resume <partial.jsonl>` after any crash. Entry point is `.venv/Scripts/telaah.exe` (`python -m telaah` does not work).

## Lessons
- A retrieval-only gain does not guarantee an end-to-end gain (merged step pages: 4/19 -> 11/19 step hits, answers got worse). Always confirm end-to-end before keeping.
- Seed set is tuned (optimistic); dev set (non-seed) is the honest signal. Runs on 27 calc questions differ by 1-2 questions without code changes: only large effects count.
- When a background run finishes in seconds, read its log; a typo in the command (or an undefined name) can fail silently.

## Next
1. After 14:00 local: `.venv/Scripts/python eval/bench/draft.py --pages pages2.jsonl` (416 pages left, ~35 min), then Claude reviews the new dev drafts (Opus 5.5).
2. User: review test candidates in `review_app.py` (Test), write 8 test unanswerables.
3. Gradio demo: follow the plan above, step 1 when the Gemini quota allows (needs a separate demo key).
4. Calculation: only with a new lever (stronger model for steps, or line items in the facts table); EPS into the facts table fixes seed q005.

# Update — 2026-10-23: round 2 drafting done, dev review done
- Gemini quota was open (reset 14:00 local the day before). `draft.py --pages pages2.jsonl` drafted all 416 remaining pages in one run (no quota stop); drafted_pages.jsonl now covers pages.jsonl + pages2.jsonl (920 rows).
- Claude reviewed all 237 unreviewed dev drafts (`bulk_review.py`): 164 accepted, 73 rejected. Chart golds were checked against the rendered page images: 2 draft golds were wrong (q0213-2 BOPO value was 2021 not 2022 -> question edited to 2021; q0261-2 draft said 7.932, chart shows 7.832 -> rejected). Calc figures all verified present on the page and same table row; rejected stage tables, negative growth, nonsense sums (equity + profit, rates added), garbled questions.
- `dev.jsonl` = 439/450, sha256 69e220ec7c5950a03bf0b096f3f46bac090ea1814490d49d68ab824e75af5f85. Quotas full: text_fact 90, calculation 68 (101 accepted, extras unused), cross_doc 68, regulation 45, unanswerable 22. Short: table_lookup 84/90, chart 62/67.
- Test split untouched and unread (`test.jsonl` is empty until the user reviews `candidates_test.jsonl` in review_app.py). Note: running `build.py` rewrites dev.jsonl/test.jsonl (it has no --help flag).
- Not committed yet. Not run yet: dev eval on the 105 new questions (the 258-question run `bench-dev-20261022-001829.json` covered the older ones).
## Next
1. Decide: commit (dev review + dev.jsonl), then dev eval on the new questions only (delta), router + judge-on-fail.
2. User: review test candidates (Test radio in review_app.py), write 8 test unanswerables.
3. Gradio demo plan step 1 (needs a separate Gemini key); calculation levers as before.

# Update — 2026-10-23 (afternoon): dev delta eval in progress, chart run pending
## Done (committed 8a0bd60)
- Round 2 drafting finished (416 pages, one run). Claude reviewed 237 dev drafts: 164 accepted; chart golds checked on rendered images (q0213-2 edited to 2021, q0261-2 rejected, draft gold was wrong). `dev.jsonl` 439/450, sha256 69e220ec...5af5f85. Test split untouched/unread.
- IMPORTANT: `build.py` renumbers `bdNNNN` ids when dev grows (the 50 seed ids are stable). The old run `bench-dev-20261022-001829.json` has OLD ids and stores no question text: map via `git show HEAD~1:eval/bench/dev.jsonl` (id -> question) and compare by question text.
- `build.py` has no --help: running it rewrites dev.jsonl/test.jsonl.

## Delta eval (156 dev questions never evaluated: chart 57, calculation 53, table 23, regulation 23)
- ids saved: `eval/bench/_new_ids.txt`, `_new_ids_nochart.txt` (99), `_new_ids_chart.txt` (57), all uncommitted scratch.
- Non-chart run (router + judge-on-fail, 7B): log `eval/bench/eval_dev_delta.log`, progress `eval/runs/bench-dev-20261023-090544.partial.jsonl`. First attempt was killed at 51/99 by the low-memory reaper (not a bug); resumed with `--resume`. At 15:31 the log showed 62/99 (calculation) and a telaah process was still alive; check whether it is really progressing. If it died: rerun the same command with `--resume eval/runs/bench-dev-20261023-090544.partial.jsonl --ids $(cat eval/bench/_new_ids_nochart.txt)`. Check free RAM first (>= 7 GB).
- Partial results on the first 50 (23 table, 27 calc): table numeric 0.43, recall 0.52, citation 0.39, refusal 0.78; calculation numeric 0.19, recall 0.33, citation 0.26, refusal 0.70 (same level as the earlier 27-question calc set: 0.22). Regulation (23) not run yet.
- Chart run (57, Gemini vision, ~60 flash-lite requests) NOT started. A one-shot cron (14:07) fired but the user interrupted it; cron is session-only and gone after /clear. Run it only when no other GPU job is running and the quota has reset (it did at 14:00): `.venv/Scripts/telaah.exe eval --file eval/bench/dev.jsonl --router --judge-on-fail --ids $(cat eval/bench/_new_ids_chart.txt) > eval/bench/eval_dev_chart.log 2>&1` (background).

## Lessons
- One telaah eval at a time; the eval plus other apps can exhaust 15.7 GB RAM and the harness kills background jobs. Close heavy apps first.
- Do not write temp files to `/` (`/tmp_x` triggers the rm safety check); use the scratchpad.

## Next
1. Confirm the non-chart eval finished (final json in `eval/runs/bench-dev-*.json`), then show the 99-question table by type (and combine with the first 50). Then run the chart set (ask first), then report per type vs the older dev run.
2. Commit scratch ids only if wanted (otherwise delete `_new_ids*.txt`).
3. User: review test candidates (review_app.py, Test) and write 8 test unanswerables.
4. Gradio demo plan step 1 (needs a separate Gemini key); calculation levers (stronger model for steps; EPS into facts table).
