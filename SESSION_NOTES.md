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

# Update — 2026-10-23 (late afternoon): non-chart delta eval done
## Done
- Non-chart delta eval finished (99 questions, router + judge-on-fail, 7B): `eval/runs/bench-dev-20261023-090544.json` (resumed twice; final shutdown ImportError from qdrant is harmless). Needed `llama-server` killed first (5 GB, Ollama restarts it) to get >= 7 GB free; during the run free RAM was ~0.4 GB (eval python 5.6 GB + llama-server 2.4 GB; GPU 4.9/6.1 GB).
- `extra_gold_dev.json` was keyed by OLD ids (built 10-21, before build.py renumbered): 12 of the 99 ids collided. Rebuilt it (260 checked, 70 gained, 112 pages). Recall rechecked for the 13 affected questions: rag route re-retrieved exactly (bd0123 0->1), agent route checked via citations (no inflation).
- Final by type (recall@5 / citation / numeric): calculation n=53 0.38 / 0.30 / 0.17; table_lookup n=23 0.57 / 0.39 / 0.43; regulation n=23 0.65 / 0.39 / 0.67. Older dev run (001829): calc 0.30/0.30/0.22, table 0.67/0.52/0.57, regulation 0.83/0.54/1.00. Judge scores not comparable (judge-on-fail). Calc latency average (394 s) is distorted by the crash/resume.
## Findings
- ColPali loads (on CPU) for ANY question whose wording trips `wants_image`, even calculation (bd0264: 150 s, failed with os error 1450, then disabled for the run). Probably what pushed the first attempt over the RAM limit.
- Agent recall understates: `recall_at_k` looks at the first 5 of all steps' retrieved pages combined (mostly step 1). bd0128 and bd0206 cite a gold page but score recall 0.
## Next
1. Chart run (57, `_new_ids_chart.txt`): needs ColPali + eval + llama-server in RAM. Check free RAM first; if short, two-pass idea: ColPali rankings alone with Ollama stopped (GPU), cache them, then eval reads the cache (code change, ask first).
2. Optional: agent recall = top-5 per step (changes calc recall measurement; ask first).
3. User: review test candidates (review_app.py, Test), write 8 test unanswerables. Gradio demo plan step 1.

# Update — 2026-10-23 (evening): chart delta eval + vision fix
## Done
- ColPali query cache (commit 07a2a08): `eval/bench/colpali_cache.py` encodes the `wants_image` questions on the GPU (Ollama idle) into `data/colpali/query_cache.pt` (gitignored); `TELAAH_COLPALI_CACHE_ONLY=1` never loads ColQwen2 (a miss logs and skips ColPali). Avoids the ~4.4 GB CPU load that does not fit beside the eval. Re-run colpali_cache.py whenever chart questions change.
- Chart run, 57 questions (`eval/runs/bench-dev-20261023-155954.json`, 0 cache misses): recall 0.56, citation 0.25, refusal 0.49, numeric 0.32. Split: chart wording + report in the ColPali index (11): recall 1.0, numeric 1.0; chart wording + other report (28): numeric 0.14, 20 wrong refusals; no chart word (18): recall 0.22, numeric 0.17.
- Cause: `answer.add_page_images` only sent pages in the ColPali index (3 reports) to Gemini vision. Fix (commit 3e5858d): any report with a PDF (`vision.has_pdf`). Rerun of the 28 (`bench-dev-20261023-162414.json`, ids `eval/bench/_ids_chart_vision.txt`): citation 0.14 -> 0.54, refusal 0.29 -> 0.75, numeric 0.14 -> 0.68, wrong refusals 20 -> 7, 15 questions wrong -> right, none the other way; latency 12 -> 39 s (up to VISION_PAGES=5 Gemini calls). All 57 together: numeric ~0.58 (was 0.32).
## Next
1. The 18 chart questions without a chart word (recall 0.22, vision never triggers): look at their wording; widen `wants_image` only if ordinary questions stay fast (Opus 5.5).
2. Remaining 7 wrong refusals in the 28: 6 are retrieval misses (gold page not in top 5).
3. Optional: agent recall = top-5 per step. User: review test candidates, write 8 test unanswerables. Gradio demo plan step 1.

# Update — 2026-10-23 (night): chart-page transcription pilot (handoff)
## Done (commits 07a2a08, 3e5858d, 37783cf, 5d3aac9)
- Chart-heavy pages are transcribed once by Gemini and added as page text. Switch `TELAAH_TRANSCRIPTS=1` (default OFF). Code: `src/telaah/transcripts.py` (rule: >= 2 images or < 1000 chars text; side BM25 `data/bm25_tx.pkl`; transcription vectors `data/page_transcripts/embeddings.pt`; dense score = max(page, transcription); context shows the transcription first), `vision.transcribe_page` / `DailyQuota`, CLI `telaah transcribe --docs ...` and `telaah transcripts-index`. pytest 82.
- Measurement basis: 13,011 bank pages; image count is the best chart signal (chart gold pages median 3 images, text/table gold pages 90% <= 1). Rule flags 2,207 pages (17%) of all 10 reports; pilot = bca_2025 + mandiri_2025 = 332 pages.
- Pilot transcription: 288/332 done (125 with chart text, 163 "no chart", 10 junk page-number strings, harmless), stopped on the Gemini daily quota. Pending 44 pages are all mandiri_2025 p.700-1467 (no dev chart gold page among them). Gold pages spot-checked from text only (bca p.8/12/13, mandiri p.22/35/293 correct); not yet compared against page images.
- Retrieval-only recall@5, switch OFF -> ON, 87 dev questions with gold in the two pilot reports: chart 0.27 -> 0.50 (22, +5, lost 0), text_fact 0.55 -> 0.60, table_lookup 0.81 = 0.81, calculation 0.89 = 0.89. Passes the bar (chart +0.15, others >= -0.02). Script: scratchpad `tx_compare.py` (not saved in repo).
- Earlier today: chart run 57 -> vision fix (any report with a PDF) lifted the 28 non-ColPali chart questions numeric 0.14 -> 0.68; ColPali query cache for the 11 indexed-report questions (`TELAAH_COLPALI_CACHE_ONLY=1`, `eval/bench/colpali_cache.py`).
## Next
1. Full eval on the 22 chart questions of the two pilot reports with `TELAAH_TRANSCRIPTS=1` (+ `TELAAH_COLPALI_CACHE_ONLY=1`), router + judge-on-fail; compare with runs 155954/162414 (numeric ~0.5-0.68 with run-time vision). Kill `llama-server` first (Ollama restarts it); need >= 7 GB free RAM.
2. After the Gemini reset (14:00 local on 10-24): `telaah transcribe --docs bca_2025 mandiri_2025` finishes the 44 pages, then `telaah transcripts-index`.
3. Only if step 1 confirms: scale to the other 8 reports (~1,900 pages, several days of free quota, resumable), then a full dev re-eval (all retrieval numbers shift) before turning the switch on by default. Spot-check some transcriptions against the page images first.
4. Still open: agent recall = top-5 per step; calculation levers; user reviews test candidates (review_app.py) and writes 8 test unanswerables; Gradio demo plan step 1.
## Notes
- Uncommitted scratch: `eval/bench/_*.py`, `_new_ids*.txt`, `eval/bench/transcribe_pilot.log`, `eval_dev_*.log`; `data/page_transcripts/` is data (check .gitignore before committing it).
- Working rules unchanged (see memory): numbered plan first, ask before each step, model recommendation per step (also in global CLAUDE.md).

# Update — 2026-10-23 (22:10): transcription pilot confirmed end to end
## Done
- Eval of the 22 chart questions in bca_2025 / mandiri_2025 with `TELAAH_TRANSCRIPTS=1` + `TELAAH_COLPALI_CACHE_ONLY=1`, router + judge-on-fail: `eval/runs/bench-dev-20261023-215353.json` (ids in scratchpad `pilot_ids.txt`: dev chart, answerable, gold in those two reports).
- Numeric 0.36 -> 0.50 (8 -> 11 of 22) vs runs 155954/162414 (run-time vision); 3 wrong -> right (bd0163, bd0181, bd0195), 0 right -> wrong. Recall@5 0.41. Summary: recall 0.409, citation 0.227, refusal 0.773, judge 0.75, faithful 0.9.
- CAVEAT: the Gemini daily quota (500/day) ran out at about question 7, so run-time vision was skipped for most of the run (429 in the log). The 0.50 is transcripts with little or no vision = likely a floor. Small sample (22), direction only.
- 11 questions are wrong in both runs, mostly recall 0 (gold page not retrieved): more transcription will not fix those.
- Committed `data/page_transcripts/` (1.2 MB, cost quota to make); `data/bm25_tx.pkl` (92 MB) is now git-ignored (rebuild with `telaah transcripts-index`).
## Next
1. After the Gemini reset (14:00 local on 10-24): `telaah transcribe --docs bca_2025 mandiri_2025` (44 pages), then `telaah transcripts-index`. Optionally rerun the 22 with working vision.
2. Spot-check some transcriptions against page images, then scale to the other 8 reports (~1,900 pages, several days of quota, resumable); full dev re-eval before the switch goes default-on.
3. Still open: agent recall = top-5 per step; calculation levers; user reviews test candidates (review_app.py) and writes 8 test unanswerables; Gradio demo plan step 1 (separate Gemini key).

# Update — 2026-10-24 (~10:00): quota check, transcription spot-check, scaling plan
## Done
- `telaah transcribe --docs bca_2025 mandiri_2025` ran once: 1 of 44 pending pages done (mandiri_2025 p.700, "no chart"), then the Gemini daily quota refused. Reset is 14:00 local (midnight Pacific, UTC+7), NOT already passed at 09:46 (I misread the earlier note). Log: `eval/bench/transcribe_pilot2.log` (untracked). 43 pages left (mandiri_2025 p.701-1467, no dev chart gold page among them).
- Spot-check of 10 transcriptions vs rendered page images (bca p3/46/155/307/422/604, mandiri p99/196/350/441): 9 correct (real chart p350, table p155, profile p196, covers p3, flow p307, and 4 "no chart" pages all right). One flaw: bca p422 ownership diagram loses which company each % applies to (numbers right, targets dropped). PNGs in the old scratchpad `.../scratchpad/spot/` (temp, not needed).
- Pending pages for the other 8 reports (`chart_heavy_pages`, none transcribed yet): btn_2024 396, mandiri_2024 358, bni_2024 239, btn_2025 208, bri_2024 205, bri_2025 198, bni_2025 190, bca_2024 81 = 1,875 pages (~500 requests/day, est. 4-6 days).
## Decisions
- Transcription prompt stays AS IS (user declined adding a "who -> whom" line for ownership diagrams).
- User wants to RE-CONFIRM EACH DAY before running transcription (no auto-runs).
- Do not run evals or drafting on the same Gemini key while transcribing (run-time vision and transcription share the 500/day quota; this ended the 22-question eval early on 10-23).
- Build the index only once, after all reports are done (a partial index makes reports uneven in the re-eval).
## Next
1. After 14:00 local (a session-only reminder was set for 14:03, lost on /clear): ask OK, then `.venv/Scripts/telaah.exe transcribe --docs bca_2025 mandiri_2025` (43 pages). Model: Sonnet 5.5.
2. Ask OK each day: `telaah transcribe --docs bca_2024 bni_2025 bni_2024 bri_2025 bri_2024 btn_2025 mandiri_2024 btn_2024` (smallest first, resumable, stops itself at quota).
3. When all done: `telaah transcripts-index`, then full dev re-eval (all retrieval numbers shift) before turning `TELAAH_TRANSCRIPTS` on by default. Model: Sonnet 5.5 (Opus 5.5 to read results).
4. Still open: 18 chart questions without a chart word (`wants_image`, Opus 5.5); agent recall = top-5 per step; calculation levers; user reviews test candidates (review_app.py) and writes 8 test unanswerables; Gradio demo plan step 1 (separate Gemini key); decide keep/delete of untracked scratch (`eval/bench/_*.py`, `_new_ids*.txt`, logs).

# Update — 2026-10-24 (16:10): transcription scaling day 1
## Done
- Pilot finished: `telaah transcribe --docs bca_2025 mandiri_2025` completed the 43 pending pages (log `eval/bench/transcribe_pilot3.log`).
- Scale run on the 8 other reports started after the 14:00 reset: 457 of 1,875 pages, then daily quota refused (log `eval/bench/transcribe_scale1.log`, untracked). bca_2024 and bni_2025 complete; bni_2024 stopped at p.553. 1,418 pages left.
- Committed `data/page_transcripts/` as fee9fee (only that folder; scratch files still untracked).
## Decisions
- Index NOT built yet (build once after all reports are done). User still wants to re-confirm each day before transcribing.
## Next
1. After 14:00 local on 10-25: ask OK, then `.venv/Scripts/telaah.exe transcribe --docs bni_2024 bri_2025 bri_2024 btn_2025 mandiri_2024 btn_2024` (resumable, stops at quota; ~3 more days). No evals/drafting on the same key meanwhile. Commit `data/page_transcripts/` after each run. Model: Sonnet 5.5.
2. When all done: `telaah transcripts-index`, then full dev re-eval before `TELAAH_TRANSCRIPTS` goes default-on (Sonnet 5.5 run, Opus 5.5 to read results).
3. Still open: 18 chart questions without chart word (`wants_image`); agent recall top-5 per step; calculation levers; user reviews test candidates and writes 8 test unanswerables; Gradio demo step 1; decide keep/delete of untracked scratch.

# Update — 2026-10-25 (19:05): transcription scaling day 2
## Done
- `telaah transcribe --docs bni_2024 bri_2025 bri_2024 btn_2025 mandiri_2024 btn_2024`: 500 pages, then daily quota (log `eval/bench/transcribe_scale2.log`, untracked). ~45 min, ~0.6 GB RAM, no GPU.
- bri_2025, bri_2024 complete; bni_2024 238/239 (p.602 failed on a connection error; retried on next run); btn_2025 45/208 (stopped at p.88). Committed as cb683bc.
- 918 pages left: btn_2025 ~163, mandiri_2024 358, btn_2024 396 (~2 more days).
## Next
1. After 14:00 local on 10-26: ask OK, then `.venv/Scripts/telaah.exe transcribe --docs bni_2024 btn_2025 mandiri_2024 btn_2024`; commit `data/page_transcripts/`. Model: Sonnet 5.5.
2. Rest unchanged (see 10-24 16:10 Next 2-3).

# Update — 2026-10-25 (evening): the 18 chart questions without a chart word
## Findings
- Their wording is plain factoid ("Berapakah total pekerja BCA ...?"): no wording rule can tell them apart, so widening `wants_image` is dropped.
- With the (pilot) transcripts: 6/18 gold in top 5, 7 at rank 11-20, 5 not in top 50. Of those 5: bd0159 is a real image-only value (btn_2025 p.246, pending transcription); bd0183/0199/0202 have the value in text on other pages; bd0203 was answered right but scored wrong.
## Done
- `extra_gold.py` now includes `chart` (it skipped them): +12 chart entries, bd0193 removed by hand (coincidental "40"). Commit 579d8a0. Chart recall@5 (switch OFF) 0.596 -> 0.614.
- `numeric_match` accepts a figure written in another unit word (juta vs triliun), rounded or truncated to gold's last digit; exact path unchanged. Commit fcce0e1, pytest 83. Re-score of the 10-23 runs: 0 right->wrong; chart 155954 0.316 -> 0.351, 215353 0.500 -> 0.591 (bd0171, bd0203). Runs before 10-23 cannot be re-scored against the current dev.jsonl (ids renumbered).
## Next
1. Count dev questions with gold at rank 6-15 (retrieval only) to decide on a "second look on refusal" (answer again with ranks 6-15; default OFF; must keep unanswerable refusals). Model: Sonnet 5.5, Opus 5.5 to decide.
2. Transcription day 3 after 14:00 on 10-26 (see day-2 Next).

# Update — 2026-10-25 (20:15): chart-question follow-ups, scorer fixes, second-look experiment (RUNNING)
## Done (commits 579d8a0, fcce0e1, 0ec3629, 92b3bc5, 1d3263a)
- 18 chart questions without a chart word: wording cannot separate them from plain factoids, `wants_image` NOT widened. Real causes: retrieval rank (7 at rank 11-20), image-only values (btn_2025 p.246 pending transcription), scoring errors.
- `eval/bench/extra_gold.py` now includes `chart` (+12 entries, bd0193 pruned by hand); chart recall@5 0.596 -> 0.614.
- `src/telaah/metrics.py` `numeric_match`: same figure in another unit word (juta vs triliun) passes, rounded or truncated to gold's last digit; same-unit/unitless stay exact. Re-score of 10-23 runs: 0 right->wrong, chart 155954 0.316->0.351, 215353 0.500->0.591. Runs before 10-23 cannot be re-scored (ids renumbered).
- Agent/multi-entity recall: `recall_at_k_groups` scores each step's/entity's own top 5 (`agent.py`, `answer.py` return `retrieved_groups`; `eval/run_eval.py` stores `retrieved_top`). Old runs have no per-step pages, so no offline re-score; takes effect in the next eval. pytest 84.
- Scratch cleanup: deleted `_boost/_rerank/_rerank_variants/_twoyear_check.py`; committed `_retr_dev/_miss/_calc_diag.py` + `_new_ids*.txt`. `test.jsonl` and `candidates_test.jsonl` still untracked, user has not decided commit vs .gitignore (do not read them).
- Rank count (retrieval only, 317 answerable dev, 10-23 gold): 221 at rank 1-5, 60 at rank 6-15, 36 beyond 15. Of the 60: 27 were wrongly refused, 18 wrong, 14 right.
## Running / pending
- "Second look" experiment (no pipeline change): answer from ranks 1-5; if refused, again from 6-10, then 11-15. RAG path, vision off, transcripts off, 27 refusal candidates + 22 dev unanswerables, local `qwen2.5:7b-gpu`. Script `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-genai-project/b9271d08-07fb-422f-9e48-84ec859479c4/scratchpad/second_look.py` (copy in `eval/bench/_second_look.py`, untracked, writes next to itself), results `.../scratchpad/second_look.jsonl` (same folder; 44/49 lines at 20:10), log `second_look.log`. Resumable: rerun the script. Finishes within minutes. Do not start other GPU jobs.
- Partial result (38/49): rescue candidates: 19 of 24 answered (15 at look 2, 4 at look 3); 12 numeric-correct (bar was 5), 2 answered with a wrong number, 5 text answers to check by hand (bd0028, 0047, 0053, 0056, 0359); 3 multi-entity skipped (bd0220/0225/0226); 5 still refused (bd0041, 0148, 0169, 0180, 0195). Unanswerables: q050 LEAKED (refused at look 1, answered at look 2 with an invented POJK 12/2024 fine); 10 of 11 so far stay refused; 11 left to count.
## Decisions
- Do not widen `wants_image`. Build the second look only if the leak rate on unanswerables stays low, and then with a safeguard: accept a look 2/3 answer only if a cited page contains the figure (reuse the agent's `unsupported` check), default OFF, evaluated after the transcript index is rebuilt.
## Next
1. Read `second_look.jsonl` when done (Opus 5.5): final leak count over all 22 unanswerables, hand-check the 5 text answers, then decide on the second look + safeguard.
2. Transcription day 3 after 14:00 local on 10-26: ask the user OK, then `.venv/Scripts/telaah.exe transcribe --docs bni_2024 btn_2025 mandiri_2024 btn_2024` (918 pages left, ~2 days), commit `data/page_transcripts/`. No evals/drafting on the same Gemini key meanwhile. Then `telaah transcripts-index` and full dev re-eval (new recall and numeric_match change the baseline).
3. User: decide test.jsonl handling, review test candidates (review_app.py), write 8 test unanswerables. Gradio demo step 1 (separate Gemini key). Commit `_second_look.py`/`_rank615.py` if wanted.

# Update — 2026-10-25 (night): second look, local Gradio demo, Space packaged (NOT published)
## Done (commits f15e912, 05647f5, 170b686)
- Second look built, default OFF (`TELAAH_SECOND_LOOK=1`): `answer.ask` re-asks a refusal on ranks 6-10, then 11-15 (text only, single-entity questions). A later answer is kept only if `later_look_ok` accepts it: cites a page, every figure on a cited page (`repair_text` first), and every cited doc matches the bank/regulation the question names (`filters.named_prefixes`). Replay on the 10-25 experiment: 17 right kept, q050 leak and bd0190 rejected, bd0163 (wrong figure that is on the cited page) still passes. `ask` result has a new `look` field; `retrieved` keeps the first look's 5 pages first. Not evaluated yet. pytest 90.
- Local Gradio demo: `app.py` + `src/telaah/demo.py` (`tests/test_demo.py`, pytest 98). Runs `router.run_routed`; Indonesian UI with English subtitles; readable citations; trust line (agent: its own verifier; else `check_text`); cited page text with answer figures in bold; "how it answered" panel; 15 s gap and 30 questions per visitor; vision OFF unless `TELAAH_DEMO_VISION=1`, ColPali never loaded. Start: `.venv/Scripts/python app.py` -> http://127.0.0.1:7860 (~20 s warm-up). Uses the LLM from `.env` (local Ollama 7B).
- Known demo gaps: plain RAG answers can cite a neighbouring page (RIM question cited PADG p.4, figures on p.7; the trust line flags it); growth question "pertumbuhan kredit BRI" answers 56,2% (wrong, pipeline issue), so it is not an example.
- Space packaging: `deploy/build_space.py` stages `space_build/` (git-ignored, 71 files, 394 MB: app, package minus ingest/cli/mcp, qdrant, processed, bm25.pkl, facts.sqlite, requirements.txt, Space README, LFS rules). Staged copy tested locally on port 7862 with docling/pymupdf/mcp/colpali_engine blocked: same answers on all routes. No secrets inside.
## Decisions
- Publishing the extracted text: user OK'd it, but the Space was NOT created. Hugging Face answered 402: Gradio/Docker Spaces on free cpu-basic need PRO (static Spaces are free but cannot run this app). User chose option 1: keep the demo local, record the 2-minute demo video from it; revisit the Space only if the user subscribes to PRO and has a separate Gemini key (then rerun the upload: create_repo private, upload_folder `space_build`, variables TELAAH_DEVICE=cpu and GRADIO_SERVER_NAME=0.0.0.0, secret LLM_API_KEY; HF login is `archiesinaga`).
- Unverified for a future Space: pip install on Space (torch CPU, Python 3.12), LFS push, bge-m3 first download (~2 GB), free-tier RAM.
## Next
1. Transcription day 3 after 14:00 local on 10-26: ask the user OK, then `.venv/Scripts/telaah.exe transcribe --docs bni_2024 btn_2025 mandiri_2024 btn_2024` (918 pages left, ~2 days); commit `data/page_transcripts/`. No evals/drafting on the same Gemini key meanwhile. Then `telaah transcripts-index` and the full dev re-eval (second look ON vs OFF, new recall scoring, `numeric_match`). Sonnet 5.5 runs, Opus 5.5 reads.
2. Optional, no Gemini: opt-in repair of the cited page in plain RAG answers (`repair_text`), evaluated in the same re-eval (Opus 5.5 decides, Sonnet 5.5 codes).
3. User: record the 2-minute demo video from the local app; review test candidates (`review_app.py`, Test) and write 8 test unanswerables; decide test.jsonl / candidates_test.jsonl (commit vs .gitignore). Then SFT data (roadmap week 10; Opus 5.5 for the design).

# Update — 2026-10-25 (21:05): citation repair, quota check, handoff
## Done (commit f284d0d)
- `TELAAH_CITE_REPAIR=1` (default OFF): in RAG answers a citation moves to the retrieved page of the same document that holds the figures. `answer.repair_cites` = `agent.repair_text` + new `agent.repair_split` (sentences citing several pages, e.g. bank figure + regulation threshold: a cited page holding none of the figures is swapped for a candidate page of the same doc holding the uncovered figures). Applied in `answer.ask` (first look) and `answer.ask_entities` (final compose text). Only the page number changes; refusals, retrieval and unmatched figures untouched. README switch list updated. pytest 102.
- Check case (RIM Mandiri vs PADG 23/2025, goes through `ask_entities`): cites PADG p.4 -> p.7, trust line warning -> ok. Not measured on the dev set: old runs do not store retrieved pages (runs from 10-25 on store `retrieved_top`).
## Decisions
- Space stays unpublished (HF needs PRO for Gradio Spaces); see the 10-25 night update above. Demo video comes from the local app.
- Gemini quota: not refreshed. Last refusal was the end of transcription day 2 (log `eval/bench/transcribe_scale2.log`); reset = midnight Pacific = 14:00 local (UTC+7) on 10-26, 15:00 local after US daylight saving ends on 11-01. No test request was sent.
## Lessons
- The local demo (`app.py`, port 7860) holds the Qdrant lock: stop it before any other script that queries (CLI, evals, smoke scripts) or you get "Storage folder ... already accessed by another instance". Stop with PowerShell: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -like '*app.py*' | % { Stop-Process -Id $_.ProcessId -Force }`.
- Python on this Windows console needs `PYTHONIOENCODING=utf-8` to print the demo's check marks. `deploy/build_space.py` cannot run while a shell has `space_build/` as its working directory.
## Running / pending
- Local demo app is running in the background (port 7860) from this session; it dies with the session or stop it as above.
- `test.jsonl` / `candidates_test.jsonl` and `eval/bench/_second_look.py`, `_rank615.py` still untracked (user decides commit vs .gitignore; do not read the test files).
## Next
1. After 14:00 local on 10-26: ask the user OK, then `.venv/Scripts/telaah.exe transcribe --docs bni_2024 btn_2025 mandiri_2024 btn_2024` (918 pages left, ~2 days); commit `data/page_transcripts/` after each run. No evals/drafting on the same Gemini key meanwhile. Model: Sonnet 5.5.
2. When transcription is done: `telaah transcripts-index`, then the full dev re-eval with second look ON vs OFF, `TELAAH_CITE_REPAIR` ON vs OFF, new agent recall and `numeric_match`. Sonnet 5.5 runs, Opus 5.5 reads the results.
3. User: record the 2-minute demo video from the local app; review test candidates (`review_app.py`, Test) and write 8 test unanswerables; decide on the untracked files. Then SFT data / DPO design (roadmap weeks 10-11, Opus 5.5).

# Update — 2026-10-26 (15:35): transcription day 3, second look and cite repair A/B
## Done
- Transcription day 3: started 11:04 by mistake (quota resets 14:00 local; 1 page, bni_2024 p.602), real run after 14:05: 492 pages, then daily quota (log `eval/bench/transcribe_scale4.log`, untracked). bni_2024 and btn_2025 complete; mandiri_2024 done to p.1206. Committed as 2cd5a60. Left: ~425 pages = mandiri_2024 p.1207+ (~29) and btn_2024 (396).
- A/B on the non-chart dev set (99 ids `_new_ids_nochart.txt`, router + judge-on-fail, `qwen2.5:7b-gpu`, vision OFF via blank GEMINI_API_KEY/VISION_API_KEY, `TELAAH_COLPALI_CACHE_ONLY=1`, transcripts OFF; no Gemini used). Second look and cite repair runs also include the 22 dev unanswerables (121 ids, scratchpad `ids_sl.txt`).
  - Baseline `eval/runs/bench-dev-20261026-111017.json`: recall 0.657, citation 0.333, refusal 0.677, numeric 0.266 (n=79), calc numeric 0.17, table 0.43. Calc recall 0.68 vs 0.38 on 10-23 is the new per-step scoring, not a better pipeline.
  - Second look (`TELAAH_SECOND_LOOK=1`, `...124102.json`): numeric 0.329, refusal 0.747, citation 0.404, recall unchanged. 5 numeric wrong->right (bd0089, 0099, 0137, 0140, 0344), 0 right->wrong. All 22 dev unanswerables stay refused (no leak).
  - Cite repair (`TELAAH_CITE_REPAIR=1`, `...143916.json`): numeric/refusal/recall identical to baseline; citation 0.333 -> 0.354 after rescore (+2 questions, table_lookup). No unanswerable leak.
- bd0224 looked like a cite-repair regression but was a scoring gap: the figure -1,03% is also on btn_2024 p.304 (KAS row, "(1,03%)"), which extra_gold missed. Added `bd0224: [btn_2024, 304]` to `extra_gold_dev.json` (hand edit; rebuilding with `extra_gold.py` would drop it). Commit f2d437b. Rescore: `PYTHONIOENCODING=utf-8 .venv/Scripts/python eval/bench/extra_gold.py --rescore <run.json>` (no `-I`, it imports `common`).
## Decisions
- Not decided: defaults for `TELAAH_SECOND_LOOK` (leaning ON) and `TELAAH_CITE_REPAIR` (safe, small gain). Decide after the full re-eval with new transcripts (Opus 5.5).
## Lessons
- Check the clock before asking to run transcription: quota resets 14:00 local (15:00 after 11-01).
- Ollama was not running at session start; `ollama serve` (hidden window) before any eval. `.env` has `LLM_MODEL=qwen2.5:7b-gpu`.
- Free RAM was 0.8 GB with Chrome open, 4.5 GB after closing it; the eval ran fine at ~0.5 GB free (no crash). Run durations: baseline ~90 min, 121-id runs ~1.5-2 h.
- To disable Gemini vision without editing `.env`: set GEMINI_API_KEY and VISION_API_KEY to empty strings in the shell (dotenv does not override).
## Next
1. After 14:00 local on 10-27: ask OK, then `.venv/Scripts/telaah.exe transcribe --docs mandiri_2024 btn_2024` (~425 pages, ~1 day); commit `data/page_transcripts/`. Model: Sonnet 5.5.
2. Then `telaah transcripts-index` and the full dev re-eval (second look ON vs OFF, cite repair ON vs OFF, transcripts ON, new recall and `numeric_match`); Opus 5.5 reads it and decides the defaults.
3. User: record the demo video; review test candidates (`review_app.py`); write 8 test unanswerables; decide `test.jsonl` / `candidates_test.jsonl` (commit vs .gitignore). Then SFT data (roadmap week 10, Opus 5.5).

## Addendum (15:45): calculation diagnosis, paused (not run)
- Goal: bucket the 53 calc failures of the baseline run (`bench-dev-20261026-111017.json`; calc numeric 0.17) into retrieval / read / plan / compute / gold, to pick a lever (stronger step model, EPS in facts table).
- `eval/bench/_calc_diag.py` is hardwired to the 10-22 run and traces of 10-21/22 (dev ids were renumbered since), so it cannot be used as is. A scratchpad copy with the run switched to `20261026-111017`, traces glob `20261026.jsonl` and an absolute `sys.path` for `common` is at `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-genai-project/ff3d8456-f9f2-42da-8407-99968b86d224/scratchpad/calc_diag_1026.py` (temp, may be gone).
- First run failed with `KeyError: 'bd0207'`: dev.jsonl has calc questions that were not in the 99-id run. Fix = keep only calc questions whose id is in the run (`... if q["type"] == "calculation" and q["id"] in run`). That edit was NOT applied (user stopped the call); the script has not produced output.
- Caveat: `data/agent_traces/20261026.jsonl` holds the baseline, second look and cite repair runs; "latest wins" per question text, so agent steps shown come from the cite repair run (same questions and routes).
- Needs Qdrant (stop the demo app first) and the bge-m3 embedder on CPU; Ollama not needed.
## Next (replaces the 15:35 list order)
1. Resume the calculation diagnosis (Sonnet 5.5 runs, Opus 5.5 designs the lever), or do the user tasks below.
2. After 14:00 local on 10-27: ask OK, then `telaah transcribe --docs mandiri_2024 btn_2024`; commit `data/page_transcripts/`.
3. Then `telaah transcripts-index` and the full dev re-eval (defaults decision for second look and cite repair).

# Update — 2026-10-26 (23:10): calculation diagnosis, year union, calculator fix
## Findings
- Diagnosis of the 53 dev calc questions (baseline `bench-dev-20261026-111017.json`, calc numeric 9/53): 44 failures = 29 retrieval (24 agent, 5 rag), 6 read, 9 compute/compose. Script `calc_diag_1026.py` (scratchpad, needs an output path as argv[1]).
- `TELAAH_STEP_POOL` (original question's top 5 added to RAG steps): every first try 9 -> 8 (bd0237 +, bd0206/0263 -: the extra summary page, e.g. mandiri_2024 p.30, pulled the 7B off its own page); retry-only 0 of 44 gained. Kept in the code, default OFF, no measured benefit. It never reaches per-entity steps (they use `answer_entity`).
- Real cause of 16 of the 24 agent misses: `entity_groups` splits "bank + two years" into one entity per report, so the earlier-year step can only search the OLDER report, while the comparison table with both columns is in the NEWER one. Retrieval-only check: reading both reports puts the gold page in every step for 10 of 16 (3 of 3 passing kept).
- Second bug: the per-entity plan path set `calc` from `CALC_RE`/`DERIVE_RE` only, so growth questions (pertumbuhan/kenaikan) never reached the calculator; the 7B did the arithmetic from correct figures and got it wrong (bd0210 259,9% vs 258,65%, bd0261 10,10% vs 10,11%).
## Done
- `TELAAH_YEAR_UNION=1` (default OFF): `agent.year_split` + `answer_entity(..., later=...)`: the earlier year's step reads its own report's top 5 first, then the newer report's. Run 214017 (53 ids): numeric 9 -> 12, refusal 0.623 -> 0.755, recall unchanged; 4 gained (bd0205, 0236, 0246, 0270), 1 lost (bd0257, one step read a different figure, not yet inspected).
- Calculator fix (not behind a switch): `facts.CHANGE_RE` added to the per-entity `calc` check. Re-run of the 19 year-split ids (run 222633, year union ON): right 3 (baseline) -> 6 (union) -> 9 (union + fix); gained bd0210, 0242, 0261 vs the union run, lost none. Projected calc numeric on all 53: 15 (was 9). pytest 109.
## Decisions
- `TELAAH_YEAR_UNION` default is not decided; it also changes non-calc questions that name two years. Decide after the full dev re-eval with the new transcripts (Opus 5.5).
## Lessons
- An empty `$(cat ids.txt)` after `--ids` starts a full dev run: build the list safely (assert non-empty) and kill with `Get-CimInstance ... telaah*eval* | Stop-Process` if it happens.
- The "background command completed" notice for `cmd &` only means the shell wrapper exited, not the eval; check the `.json` next to the `.partial.jsonl`.
## Addendum (23:40): bd0257, and two ideas that were already tried
- bd0257 (right at baseline, wrong with year union): the 2024 step's own pages are identical in both runs (bri_2024 p.994 rank 1, holds 128.886 = 31 Dec 2024). The union adds 5 look-alike bond tables from bri_2025 (p.1131 even holds the right 128.886), and with ~10 "Indah Kiat" rows in context the 7B took p.995 (118.877, the 2023 comparison table). Reading noise from similar tables, same as the step-pool regressions (bd0206, bd0263). Possible cap (newer report's top 2 instead of 5) NOT tried: tuning on 19 questions to win back 1 overfits; revisit only if the full re-eval shows more such losses.
- `TELAAH_STEP_POOL` repeats experiment A of 10-21 ("each step also reads the whole question's pages", reverted, see "Tried and REVERTED" above) with the same outcome. "Growth questions -> agent" (router) is experiment B (0.222 -> 0.111, reverted) and was NOT re-run. Before proposing a method, grep these notes for "Tried and REVERTED" / "kept OFF".
- Calc work paused at a projected 15/53. Untried levers: planner fixes for the per-entity path (bd0225/0226 unsplit, bd0239/0266 lose the entity; Opus 5.5 designs the prompt), table-row excerpt for steps (reading errors bd0257/0213/0272), Gemini for calc steps (after transcription).
## Next
1. After 14:00 local on 10-27: ask OK, then `telaah transcribe --docs mandiri_2024 btn_2024` (~425 pages); commit `data/page_transcripts/`.
2. Then `telaah transcripts-index` and the full dev re-eval: second look, cite repair, year union ON vs OFF (step pool stays OFF); decide the defaults (Opus 5.5 reads). Model: Sonnet 5.5 runs.
3. Calc, later: see the untried levers in the 23:40 addendum.
4. User: record the demo video; review test candidates; write 8 test unanswerables; decide test.jsonl / candidates_test.jsonl.

# Update — 2026-10-26 (23:45): handoff
- Full state is in the 23:10 update and the 23:40 addendum above (commits 7c3561e, f2bab0f). Nothing running; Ollama `serve` was started this session (hidden window) and may still be up.
- Scratch from today (temp, may be gone): `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-genai-project/ff3d8456-f9f2-42da-8407-99968b86d224/scratchpad/` holds `calc_diag_1026.py/.json`, `pool_check.py`, `union_check.py`, id lists `ids_calc.txt` (53), `ids_calc_fail.txt` (44), `ids_yearsplit.txt` (19). Untracked logs: `eval/bench/eval_calc_*.log`.
- Runs: baseline `bench-dev-20261026-111017`, step pool `...202751` (53) and `...210306` (44, retry-only), year union `...214017` (53), year union + calc fix `...222633` (19).
- Next: step 1 of the list above (transcription after 14:00 on 10-27, ask OK first). Model: Sonnet 5.5.

# Update — 2026-10-28 (10:15): second look result, eval --workers, progress PDF, SFT design + steps 1-2 code
## Done (all UNCOMMITTED)
- `eval/run_eval.py` + `src/telaah/cli.py`: `telaah eval --workers N` (thread pool, default 1 = old behaviour; lock on results/partial file; results sorted back into question order; `client()`/`embedder()` warmed once before threads because `lru_cache` is not atomic). NOT tested: the first test (q001-q006, 3 workers) crashed because a running eval held the Qdrant lock ("Storage folder ... already accessed"), a stray `eval/runs/bench-dev-20261028-095425.partial.jsonl` was left (delete it). Rerun the test only when no other eval runs; compare scores with workers=1 on the same ids. `latency_s` under threads is wall time under contention.
- `Telaah_Progress_2026-10-28.pdf` (project root, untracked): plan from the start to v1.0 with % per step. Overall ~65% (phase 1 90, 2 80, 3 75, 4 15). Source HTML in the session scratchpad (temp).
- `sft/DESIGN.md`: SFT data design (decisions: Qwen2.5-7B on Kaggle, ~2,200 examples). Training example = `answer.SYSTEM` + real retrieved context (5 pages, defaults, transcripts ON) + cited answer or `TIDAK DITEMUKAN`; mix 55% gold in top 5, 15% gold pushed in, 10% look-alike tables, 20% refusals. Gate: beats base on numeric+citation on full dev, refusal not lower, 22 dev unanswerables still refused; pin `JUDGE_MODEL` to the base model (default judge = `LLM_MODEL`, the tuned model would grade itself).
- Step 1 done: `sft/page_pool.py` -> `sft/pages.jsonl` (800 pages: text_fact 160, table_lookup 200, calculation/multi-year 200, chart 140, regulation 100; excludes test-split pages by hash without opening test files, 46 tuned + 212 dev gold + 118 extra gold + 866 benchmark-drafted pages).
- Step 2 code written, NOT run: `sft/draft_sft.py` (Gemini drafts 3 Q&A per page, house-style answer with `[doc p.N]`, automatic checks stored in `problems`; `--pilot` = 2 pages per kind = 10 requests; resumable; own quota file `sft/.quota_hit`, git-ignored via `sft/.gitignore`). Offline smoke test passed. Outputs go to `sft/drafts.jsonl` and `sft/drafted.jsonl`.
## Results
- Full dev run with transcripts ON (`bench-dev-20261028-065918.json`, 439 q): recall 0.774, citation 0.560, refusal 0.818, numeric 0.470, judge 0.715, faithful 0.853. Weakest: calculation numeric 0.206, cross_doc numeric 0.283.
- Second look ON (`bench-dev-20261028-090429.json`, 174 ids, 65 min) vs the baseline on the same 174: citation 0.494 -> 0.557, refusal 0.770 -> 0.851, numeric 0.408 -> 0.474, judge 0.359 -> 0.421, faithful 0.758 -> 0.783, recall unchanged. Numeric 10 wrong -> right (bd0089, 0091, 0094, 0099, 0108, 0110, 0118, 0126, 0140, 0214), 0 right -> wrong. All 22 dev unanswerables still refused (q050 no longer leaks). Recommendation: default ON (not changed yet, user OK needed; leaning to decide after the other two variants).
## Decisions
- SFT base: Qwen2.5-7B on Kaggle; size ~2,200 examples; drafting uses a SEPARATE Gemini key in a NEW Google project (same project = shared 500/day quota).
## Lessons
- A queue script chains the variant evals: `eval/bench/variants_run.log` showed START/END lines; I wrongly assumed cite repair / year union would not start by themselves.
- Only one eval at a time can use the vector store (`data/qdrant`); the `--workers` test must wait for the queue.
- Do not claim the token/key situation without checking: the only Gemini key on the machine is `GEMINI_API_KEY`; I cannot create a second one (user creates it at aistudio.google.com/apikey -> "Create API key in new project").
## Running/pending
- Variant queue running in the background (not by this session's own shell): cite repair `TELAAH_CITE_REPAIR=1` started 10:09:07 (partial `eval/runs/bench-dev-20261028-100915.partial.jsonl`), ~1 h; year union may follow. Watch `eval/bench/variants_run.log` (END lines). Do not start another eval or the demo app meanwhile.
- Untracked scratch: `eval/bench/_rank615.py`, `_second_look.py`, `eval_ab_*.err`; `test.jsonl` / `candidates_test.jsonl` are the blind test split (never read them; user decides commit vs .gitignore).
## Next
1. User: add `SFT_GEMINI_API_KEY=...` to `.env` (new project), tell me; then run `sft/draft_sft.py --pilot` (10 requests) and read the drafts together (Opus 5.5 judges, Sonnet 5.5 runs).
2. When the variant queue ends: read cite repair / year union results vs baseline (Opus 5.5), decide defaults for `TELAAH_SECOND_LOOK` (leaning ON), `TELAAH_CITE_REPAIR`, `TELAAH_YEAR_UNION`; then test `--workers 3` on q001-q006 and commit run_eval/cli changes.
3. SFT steps 3-7 per `sft/DESIGN.md` (full draft ~2 days of quota, context builder + filters, review sample, Kaggle training in the Claude desktop app, base vs SFT on full dev).
4. Refresh README results from the 439-question run; user: review `candidates_test.jsonl` in `review_app.py`, write 8 test unanswerables, record the demo video.

# Update — 2026-10-28 (afternoon): SFT pilot, checker fixes, full draft started
## Done
- `SFT_GEMINI_API_KEY` (new Google project) in `.env`. Pilot 1 (10 pages, 30 drafts): regulation 5/6 flagged, all false alarms from list markers / line breaks.
- `sft/draft_sft.py` checks: evidence compared on letters+digits only; long clause values (regulation) by key-word overlap; `column` field required for table_lookup and calculation (must be on the page); calculation: the column's year must be in the question; "value not in evidence". Fixed: the JSON field list in the prompt never included the extra fields.
- Pilot 2: regulation 6/6 pass; calculation re-draft 4/6 pass, both flags correct (BNI Tier II bond "2021" column asked as 2024).
## Decisions
- Calculation pages stay READING questions (older year column of a multi-year table), not arithmetic: DESIGN.md "Arithmetic stays in code". An arithmetic prompt was tried in pilot 2 and reverted (I had proposed it wrongly after pilot 1).
- Known gap: the column check proves the label exists on the page, not that it is the value's column (s0162-3). Step-5 review sample covers table/calculation first.
## Running
- Full draft in the background: `.venv/Scripts/python sft/draft_sft.py` -> `sft/drafts.jsonl`, log `sft/draft_full.log`; stops on the daily quota (`sft/.quota_hit`), rerun the same command after the reset. Pilot rows are kept (resumable by page id); pilot 1 in `sft/drafts_pilot1.jsonl`. Drafts are git-ignored.
## Next
1. Tomorrow: rerun the draft until all ~800 pages are done. Model: Sonnet 5.5.
2. Variant evals (cite repair, year union) when the GPU is free; then the defaults decision (Opus 5.5) and the `--workers 3` test.
3. SFT steps 3-4 (context builder + filters) while drafting runs.

# Update — 2026-10-28 (13:40): SFT drafting + builder, variant results, stacked eval RUNNING
## Done (commits ce58bd2, fb5cae1; SFT code only)
- `SFT_GEMINI_API_KEY` (new project) is in `.env` (git-ignored). `sft/draft_sft.py` final checks: evidence compared on letters+digits; long clause values by word overlap; `column` field required for table_lookup + calculation (must be on the page); calculation = READING questions on an older year column (arithmetic stays in code, DESIGN.md; an arithmetic prompt was tried and reverted); column's year must be in the question; "value not in evidence".
- `sft/build_sft.py` (step 3-4, tested offline with fake retrieval only; NOT run for real): wraps checked drafts in the exact `answer.ask` prompt; answer top 5 / gold pushed in / refusal with value pages removed (12%) / refusal by bank swap (8%); filters duplicates, multi-entity, short or leaking refusal context, length, 3+ digit figure equal to a dev gold answer. Retrieval cached in `sft/retrieved.jsonl`. Needs Qdrant: never while an eval runs.
## Results
- Draft so far (page 479 of 790, quota hit 12:50): 1,008 drafts, 903 pass. text_fact 413 ok/61 flag, table_lookup 478/66, calculation 187/167 (main flag "column year not in question" 133), chart 3, regulation 6 (pilot only). Chart + regulation pages come last.
- Variants alone vs base on the same 174 ids (runs `bench-dev-20261028-` 065918 base, 090429 second look, 100915 cite repair, 123629 year union): numeric 0.408 / 0.474 / 0.428 / 0.454; citation 0.494 / 0.557 / 0.523 / 0.506; refusal 0.770 / 0.851 / 0.764 / 0.799; all 22 unanswerables refused in every run. Second look: +10 numeric, 0 lost. Cite repair: +3 numeric 0 lost, citation +6 -1 (bd0208). Year union: numeric +10 -3 (bd0128, bd0230, bd0257), gains mostly calculation.
## Decisions
- Recommendation (not applied, defaults unchanged): SECOND_LOOK ON, CITE_REPAIR ON, YEAR_UNION undecided until the stacked run. The `faithful` row is NOT comparable across runs (judge-on-fail grades only failures; n differs 27-46).
## Lessons
- Each variant ran alone, not stacked: "second look vs cite repair" differences are just the missing second-look gains.
- `eval --resume <partial.jsonl>` works (cite repair resumed at 119/174). Ollama had to be started (`ollama serve`) after the PC restarted.
## Running/pending (started from this session's shell; check they survived /clear)
- Stacked eval (SECOND_LOOK+CITE_REPAIR+YEAR_UNION, 174 ids from scratchpad `ids_var.txt`, started 13:36, ~65 min): log `eval/bench/eval_tx_STACKED.log`, END line in `eval/bench/variants_run.log`, result `eval/runs/bench-dev-<time>.json`. Check `ids_var.txt` copy at `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-genai-project/861974ac-3449-4a7f-a62c-a3df746e4672/scratchpad/` (may be gone; it holds the 174 ids = ids of run 090429).
- Draft resume scheduled to start by itself at 14:01 (waiting loop + `python sft/draft_sft.py --force`, log appended to `sft/draft_full.log`): ~311 pages left (chart, regulation, 2 errored pages). If /clear killed it, rerun `.venv/Scripts/python sft/draft_sft.py` after 14:00 (resumable).
- Uncommitted: `eval/run_eval.py`, `src/telaah/cli.py` (`--workers`, untested), scratch `eval/bench/_rank615.py`, `_second_look.py`, `eval_ab_*.err`, stray `eval/runs/bench-dev-20261028-095425.partial.jsonl` (delete). `test.jsonl` / `candidates_test.jsonl` = blind test split, never read.
## Next
1. When the stacked eval ends: compare with second look alone (same 174 ids; right->wrong list, 22 unanswerables); decide defaults for SECOND_LOOK / CITE_REPAIR / YEAR_UNION; change them and commit. Model: Opus 5.5.
2. Then `eval --workers 3` on q001-q006 vs workers=1 (no other eval running); commit run_eval/cli if equal. Model: Sonnet 5.5.
3. When the draft finishes: `.venv/Scripts/python sft/build_sft.py` for real (no eval running), read mix counts (answer_pushed share, lookalike), then step 5 review sample (200, Opus 5.5) + user spot-check of 50, table/calculation first (column label check proves the label exists, not that it is the value's column).
4. User: review `candidates_test.jsonl`, write 8 test unanswerables, record demo video; refresh README from the 439 run.

# Update — 2026-10-29 (01:15): defaults ON, --workers, SFT draft done, data review + filters
## Done (commits 26b5cd9, 25d2876, 54a1da6, e37d04d)
- Defaults ON: `TELAAH_SECOND_LOOK`, `TELAAH_CITE_REPAIR` (`src/telaah/answer.py`), `TELAAH_YEAR_UNION` (`src/telaah/agent.py`); `=0` turns each off; README switches updated. pytest 109.
- `telaah eval --workers N` committed after test on q001-q006 (seed file, `--agent --router`, vision off): identical scores and answer texts to workers=1, 35 s vs 1m55s. Stray partial `bench-dev-20261028-095425` deleted.
- SFT draft finished (resumed 23:08, no quota hit): 799/800 pages (1 errored page, s0181, not retried), `sft/drafts.jsonl` 1,983 drafts, 1,539 pass checks. ok/flagged: text_fact 413/61, table_lookup 478/66, calculation 291/285, chart 81/8 (only ~21% of chart pages had a labelled chart; empty answers are by design), regulation 276/24.
- `sft/build_sft.py` run for real (retrieval cached in `sft/retrieved.jsonl`, ~10 min; rebuilds take seconds). New filters from the Opus review: value cut out of the `build_context` excerpt (54), figure on a dev gold page of the same bank (49), English-format figure + Indonesian unit e.g. "35,415,779 miliar" (23, BNI), question names doc id/page (13), layout question "baris pertama" (8), table/calc Q/A year mismatch (3). 1,507 -> **1,357 examples** in `sft/sft.jsonl`: answer_top5 600 (44%), answer_pushed 485 (36%), refusal_removed 169, refusal_scope 103 (20%), lookalike 130 (10%). Re-audit: 0 unsupported targets.
- `sft/spot_check.py` -> `sft/spot_check.md` (git-ignored): 50 examples (13 calc, 13 table, 6 text, 5 chart, 5 regulation, 8 refusals) with the source row + header, "Verdict:" lines for the user.
## Results
- Stacked run `bench-dev-20261028-133614` (174 ids) vs base / second look alone: numeric 0.408 / 0.474 / 0.480, citation 0.494 / 0.557 / 0.580, refusal 0.770 / 0.851 / 0.879, recall 0.741 unchanged; 22 unanswerables refused. Stacked vs SL alone numeric +5 (bd0236, 0246, 0254, 0261, 0270) -4 (bd0128, 0214, 0230, 0257); calc numeric 0.221 -> 0.250; latency +7%.
- Hand review (39 answers + 8 refusals): calc 14/14 right row and year column; chart 6/6, text 5/5, refusals 8/8 valid; wrong: s0200-2 (year mismatch, now filtered), s0716-3 (regulation answer does not match question, not filterable).
## Decisions
- All three switches ON (user). YEAR_UNION is a close call on 174 ids (+1 net numeric); recheck on the next full 439 run.
- Pushed share 36% (design 15%) kept: every pushed example has the value in context; the gate (refusal not lower, 22 unanswerables refused) decides. Train on ~1,357 first; draft more pages only if the gate shows a data-size problem.
## Lessons
- `build_context` excerpts long pages: a draft value on the page is not always in the context; always check the rendered block (`block_of`).
- Background "command completed" notices for `nohup ... &` are the shell wrapper; check the process (`Get-CimInstance Win32_Process ... CommandLine -like '*draft_sft*'`) or the output file.
- Draft log is written only per page; speed 1-4 pages/min (chart pages slowest).
## Next
1. User: fill the verdicts in `sft/spot_check.md`; Opus 5.5 reads them. If < ~3/50 wrong, data is ready.
2. SFT step 6: Kaggle training notebook (Qwen2.5-7B LoRA, `sft/sft.jsonl`) — do it in the Claude desktop app (memory note). Model: Sonnet 5.5 for the notebook.
3. Step 7: base vs SFT on the full 439 dev with the new defaults, `JUDGE_MODEL` pinned to the base model; also re-check YEAR_UNION there. Opus 5.5 reads.
4. User: review `candidates_test.jsonl`, write 8 test unanswerables, record demo video; decide commit vs .gitignore for `test.jsonl` / `candidates_test.jsonl`; refresh README from the 439 run. Untracked scratch: `eval/bench/_rank615.py`, `_second_look.py`, `eval_ab_*.err`.

# Update — 2026-10-29: spot check passed, doc-id filter, SFT data ready
## Done
- Spot check of 50 examples (`sft/spot_check.md`, verdicts filled) checked against the PDF pages: 48 OK, 2 WRONG. s0622-2: BTN "ROE 2019 20%" is footnoted as a 2025 aspiration (not filterable). s0784-2: question names a file id.
- `sft/build_sft.py` PAGE_REF_RE now also drops `ojk_…` / `bi_…` ids in questions (33 examples). Rebuilt: **1,324 examples** in `sft/sft.jsonl` (answer_top5 582, answer_pushed 472, refusal_removed 167, refusal_scope 103, lookalike 130). 42 others differ only in the pushed rank (shared rng), labels unchanged.
- Docling header misreads seen in the check (s0492-2 columns are 2024/2023/2022, not Stage 1-3): the values were right.
- Committed as 1e556eb (`sft/build_sft.py`, this note). `sft/sft.jsonl` and `sft/spot_check.md` are git-ignored; backup of the 1,357 set in this session's scratchpad only (may be gone).
## Decisions
- Data ready for training (2/50 wrong, gate was < ~3). Minor wording issues kept as OK: s0391-3 no unit, s0527-2 "saldo awal per 31 Desember 2024", s0597-3 national IKK called "BTN's".
## Lessons
- The user's first verdict pass never reached the file (unchanged 01:13 timestamp; likely Markdown preview or unsaved tab). Check the file's LastWriteTime before reading verdicts.
- Checking against PDFs: `p.N` = PDF page index (1-based, Docling page_no), so pymupdf `doc[N-1]`; `data/raw/<doc_id>.pdf`. Text lines settle most rows; render ambiguous tables (`get_pixmap(dpi=110)`) and read the image for column headers and footnotes. Script kept in scratchpad `pdf_check.py` (may be gone).
## Next
1. KAGGLE SFT PHASE STARTS NOW. Move to the Claude desktop app on `C:\Users\User\genai-project`; read SESSION_NOTES.md, ROADMAP.md, KAGGLE_SETUP.md, `sft/DESIGN.md`. Build the Qwen2.5-7B LoRA training notebook for `sft/sft.jsonl` (upload it as a Kaggle dataset; lessons from the ColPali run: uninstall torchao in cell 1, output zip is under the version page > Output). Model: Sonnet 5.5.
2. Step 7: base vs SFT on the full 439 dev with the new defaults, `JUDGE_MODEL` pinned to the base model; re-check YEAR_UNION. Opus 5.5 reads.
3. User: review `candidates_test.jsonl`, write 8 test unanswerables, record demo video; decide on the untracked files.

# Update — 2026-11-09 (21:50): Kaggle SFT notebook written (step 6 prep), not run yet
## Done (UNCOMMITTED)
- `sft/split_sft.py` -> `sft/kaggle_upload/train.jsonl` 1,213 / `val.jsonl` 111, by page hash (482 / 45 pages, no overlap). Val: calc 15, chart 4, regulation 16, table 36, text 40; refusal_scope only 6. `kaggle_upload/` added to `sft/.gitignore`.
- `kaggle/sft_qwen7b_qlora.ipynb`: smoke mode in an interactive session (20 steps + time estimate), full mode under Save & Run All; loss-mask assert; resume from checkpoint input; sanity answers on val; adapter zip + GGUF Q4_K_M built in /tmp. Steps in KAGGLE_SETUP.md (SFT section). Not tested against the real Qwen tokenizer (HF blocked from the session sandbox); the smoke test is the first real run.
- Decisions (user): 1 epoch first, second only if val loss still falls; GGUF export on Kaggle.
## Next
1. User: upload `telaah-sft` dataset, import notebook, smoke test, report cells 5-7 output.
2. Full run; download GGUF; `ollama create qwen2.5:7b-sft` with the `qwen2.5:7b-gpu` Modelfile settings (copy TEMPLATE/PARAMETER from `ollama show --modelfile qwen2.5:7b-gpu`).
3. Step 7: base vs SFT on full 439 dev, `JUDGE_MODEL` pinned to base; re-check YEAR_UNION.

# Update — 2026-11-10 (13:40): Kaggle SFT smoke tests, MAX_LEN raised, smoke 2 RUNNING (handoff)
## How we work in this phase (user's choice)
- The USER does every Kaggle step by hand; Claude only explains step by step and reads the outputs the user pastes. Do NOT automate Kaggle or the browser.
- User does not need to edit code unless Claude gives an exact line to change; when pasting a line into a cell, it must start at the left margin (an indent gave IndentationError once).
## Done
- Kaggle dataset `telaah-sft` (private) uploaded: `train.jsonl` + `val.jsonl` from `sft/kaggle_upload/`. Notebook imported from `kaggle/sft_qwen7b_qlora.ipynb` (Kaggle name still `notebookc479198ca7`; rename suggested). GPU T4 x2, Internet On.
- Kaggle queue lesson: "Draft Session Error" / "failed to authorize" on 11-09 evening = no free T4; the interactive session sat "Queued" all night (21:56 -> 08:23). Stopped and restarted on 11-10 morning: it started at once. Active sessions = stacked-squares icon bottom-left (badge count). If queued > ~15 min: stop and retry later, or Save & Run All (background starts by itself).
- Env on Kaggle (11-10): Unsloth 2026.11.3, transformers 5.17.0, torch 2.11.0+cu130, Tesla T4 14.56 GB, bf16 False (fp16). Warning: preinstalled xformers built for torch 2.10 -> Unsloth falls back to PyTorch attention (harmless; maybe slower / more memory). HF downloads unauthenticated (slow but fine).
- Smoke test 1 (MAX_LEN 6144, interactive, 20 steps) ran end to end, no error. Cell 6 loss mask OK (74 of 4,710 tokens trained = answer + `<|im_end|>`). Cell 9 sample answers well formed with citations after 20 steps (s0527-2 cited bri_2024 p.1194 instead of bri_2025 p.1339, same figure: prior-year closing balance). Cell 7 timing/memory lines were NOT reported.
- PROBLEM found in smoke 1, cell 5: real token lengths train min 1505 / median 5323 / p99 8228 / max 10327; val max 8413. At MAX_LEN 6144, 315 train (26%) and 37 val were DROPPED (kept 898 / 74). My earlier ~5k-token estimate was wrong (Indonesian + numbers tokenize longer).
- Fix applied (on Kaggle by the user AND in the local notebook file): cell 2 `MAX_LEN = 8448` (keeps ~99%); cell 6 in SMOKE mode trains on the 160 LONGEST examples (worst-case memory/speed): `train_ds = Dataset.from_list([{"text": r["text"]} for r in (sorted(train_rows, key=lambda r: -r["n_tok"])[:160] if SMOKE else train_rows)])`. KAGGLE_SETUP.md updated to 8,448.
- Smoke 2: cells 2, 4, 5, 6 re-run; cell 6 OK (72 of 8,410 tokens trained). Cell 7 (20 steps on the longest examples, est. 15-30 min) was RUNNING at 13:35.
## Running/pending
- Smoke 2 cell 7 on Kaggle (interactive session). The user must stop the session after cells 7-9 to save GPU quota.
## Next
1. Read smoke 2 output: cell 5 "kept" line (expect ~1,200 train / ~110 val, over MAX_LEN ~1-3) and cell 7 last lines (`train time`, `peak GPU memory`, `s/step`, `about X h`).
   - Peak < ~14 GB and estimate well under 12 h (incl. ~14 evals of the full val set + ~30-45 min GGUF export) -> full run at 8448.
   - CUDA OOM -> MAX_LEN 7168 (keeps ~90%), or drop examples > 8448 only.
   - If the estimate is near 12 h: raise EVAL_STEPS (e.g. 100) or eval on a val subset.
2. Full run: cell 6 smoke line can stay (it only applies in SMOKE). Save Version > Save & Run All (Commit) -> mode FULL automatically (KAGGLE_KERNEL_RUN_TYPE=Batch). If the user had set `SMOKE = True` in cell 2, change it back to `SMOKE = (RUN_TYPE != "Batch") and not FORCE_FULL` first.
3. Download from the version page > Output: GGUF Q4_K_M (~4.7 GB), lora_adapter.zip, train_log.json, val_samples.jsonl. Then `ollama create qwen2.5:7b-sft` (copy TEMPLATE/PARAMETER from `ollama show --modelfile qwen2.5:7b-gpu`), sanity questions.
4. Step 7: base vs SFT on the full 439 dev, `JUDGE_MODEL` pinned to base; re-check YEAR_UNION. Opus 5.5 reads.
5. Then: PAPER for the user (requested 11-10): concise English paper (~8-10 pages) for his own interview prep. Sections: Introduction; Background theory in depth (RAG + hallucination, page chunking + bge-m3 embeddings, hybrid BM25 + dense in Qdrant, ColPali/ColQwen vision retrieval, QLoRA: 4-bit + LoRA adapters + answer-only loss, metrics: numeric match / citation / refusal / recall); System design (ingest, retrieval, router, planner/executor/verifier agent, facts table); Development procedure (phases, dev vs blind test discipline); Experiments incl. rejected ones (reranker, calc levers, two-year read); Fine-tuning (data mix, page split, base vs SFT); Limitations; Interview Q&A. Build it from SESSION_NOTES.md, ROADMAP.md, sft/DESIGN.md, README.md and eval runs — numbers from the files, not from memory.
## Uncommitted (local)
- `sft/split_sft.py`, `kaggle/sft_qwen7b_qlora.ipynb`, `KAGGLE_SETUP.md`, `sft/.gitignore`, this note. Commit when the user says so.

# Update — 2026-11-11 (22:20): smoke 2 passed, full run is next
## Results (smoke 2, MAX_LEN 8448, 20 steps on the 160 LONGEST train examples)
- Cell 5: train 1,213 -> kept 1,205 (8 over MAX_LEN), val 111 -> kept 111. Tokens train median 5,323, p99 8,228; val max 8,413.
- Cell 7: 66.7 min for 20 steps = 200 s/step, peak GPU 7.5 GB of 14.6 GB (no OOM risk). Train loss 0.54 -> 0.25, val loss 0.361 at step 20 (val subset of 8).
- Estimate printed: 151 steps + evals of 111 -> ~9.0 h training, + ~30-45 min GGUF export, + install/download -> ~10 h worst case, under the 12 h limit. Real run should be faster (smoke used the longest examples; full-set median is ~5.3k tokens).
- Harmless warnings: tokenizer bos_token_id None (Qwen has no BOS); `num_items_in_batch` could not be counted (eval only).
## Next
1. User: stop the interactive session; check cell 2 still has `SMOKE = (RUN_TYPE != "Batch") and not FORCE_FULL` and FORCE_FULL False; check GPU quota left (~10 h needed); Save Version > Save & Run All (Commit). Accelerator GPU T4 x2, Internet On, dataset telaah-sft attached.
2. Watch the version log: eval_loss at steps 50/100/150. Second epoch only if val loss still falls at 150.
3. Download GGUF + lora_adapter.zip + train_log.json + val_samples.jsonl; `ollama create qwen2.5:7b-sft`; then step 7 (base vs SFT on 439 dev, JUDGE_MODEL pinned to base).

## Full run committed (2026-11-12 00:08)
- Kaggle notebook renamed `telaah-sft-qwen7b`. A second interactive smoke ran by accident (185 s/step, est. 8.4 h + export, same losses); then Version #3 committed (Save & Run All), status Queued at 00:08; interactive session cancelled. Expected done ~09:00-10:00 if it starts soon.
- Check: version Logs should show `run type Batch -> FULL RUN`, `kept 1205 train, 111 val`, `Num examples = 1205 | Total steps = 151`. Outputs on the version page > Output tab.
- Version #3 started Running at ~00:16 on 2026-11-12 (queued ~8 min). Expected finish ~09:30-10:30 local.
- 00:34 check of Version #3 Logs: `trained tokens 74 of 4710` (first example of the FULL train order; smoke shows 72 of 8410), then "offload gradients" / "Double buffering" lines = trainer.train() started (~203 s into the run). The Logs tab may stay quiet for long stretches during training: normal, not a stall.
- Kaggle lessons from tonight: editor "Run All" = interactive session = SMOKE (cell 2 reads KAGGLE_KERNEL_RUN_TYPE; only a commit gives "Batch" -> FULL). Editor output panel shows the interactive session, not the commit; the commit log is on the version page (Save Version "3" counter > Version #3 > Logs). Do not click Run All / Save Version while a commit runs.
## Next (when Version #3 is Complete, ~09:30-10:30 on 2026-11-12)
1. Version #3 > Output: download `qwen2.5-7b-telaah-sft-Q4_K_M.gguf`, `lora_adapter.zip`, `train_log.json`, `val_samples.jsonl` into `sft/` (or a new `sft/out/`). Paste the end of the Logs (eval_loss at steps 50/100/150, cell 9 samples, cell 11 GGUF line, cell 12 file list).
2. Decide second epoch: only if val loss still falls at step 150.
3. `ollama create qwen2.5:7b-sft` from the GGUF with TEMPLATE/PARAMETER copied from `ollama show --modelfile qwen2.5:7b-gpu` (num_gpu 99, num_ctx 8192); sanity questions.
4. Step 7: base vs SFT on full 439 dev, JUDGE_MODEL pinned to the base model; re-check YEAR_UNION. Opus 5.5 reads. Then the interview paper.
5. If Error: paste the last log lines; adapter zip may still be in Output if only GGUF export failed (cell 11 catches it).

# Update — 2026-11-12 (07:30): Version #3 finished, outputs downloaded (2 files missing)
## Done
- Version #3 (full run) finished earlier than expected: output files are dated ~07:23-07:26 WIB (about 7 h after the ~00:16 start, not ~09:30-10:30).
- Downloaded into `telaah-sft-qwen7b_notebook/` (NOT yet moved to `sft/out/`):
  - `qwen2.5-7b-telaah-sft-Q4_K_M.gguf` (4,683,073,664 bytes). Checked: valid GGUF v3, file_type 15 = Q4_K_M, 339 tensors, 28 blocks (= full Qwen2.5-7B), context_length 32768. general.name is just "Gguf" (cosmetic).
  - LoRA adapter, already unzipped: `adapter_model.safetensors` (161,533,192 bytes; 392 F32 tensors = 28 layers x 7 modules x A/B; size matches its header, not truncated), `adapter_config.json` (r 16, alpha 16, dropout 0, q/k/v/o/gate/up/down, base `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`), `chat_template.jinja` (Qwen ChatML), `tokenizer.json`, `tokenizer_config.json` (eos `<|im_end|>`, pad `<|vision_pad|>`). `README.md` is the empty auto-generated PEFT model card.
## Problem: train_log.json and val_samples.jsonl could NOT be downloaded
- User could not download `train_log.json` and `val_samples.jsonl` from Version #3 > Output: every time he clicks download, the browser goes to a Google Cloud Storage signed link instead of saving the file, e.g. `https://storage.googleapis.com/kaggle-script-versions/368514710/output/train_log.json?X-Goog-Algorithm=GOOG4-RSA-SHA256&...&X-Goog-Date=20261112T002738Z&X-Goog-Expires=3600&...` (full signature not copied here; it is a temporary credential).
- Likely cause (not confirmed): small text files (.json/.jsonl) are served from GCS and the browser opens them inline as a page instead of saving them; the big GGUF/zip downloaded normally. The signed link expires 1 h after it is made (X-Goog-Expires=3600), so an old link stops working; clicking download on Kaggle again makes a fresh one.
- To try (user, by hand): (1) on the storage.googleapis.com page that opens, press Ctrl+S and save as `train_log.json` / `val_samples.jsonl` (Save as type: "All files", keep the exact name); (2) or on Kaggle Output, right-click the file > "Save link as..."; (3) or select-all the text on that page and paste into a new file with that name.
- Fallback if none works: the eval_loss values (steps 50/100/150) and the cell 9 sample answers are also printed in Version #3 > Logs; copy them from there. These are needed to decide the second epoch.
## Next
1. Get `train_log.json` + `val_samples.jsonl` (above) or paste the end of Version #3 Logs (eval_loss 50/100/150, cell 9 samples, cell 11 GGUF line, cell 12 file list).
2. Move the downloaded outputs into `sft/out/` (gitignored? check `sft/.gitignore`, the GGUF is 4.7 GB and must not be committed).
3. Decide second epoch (only if val loss still falls at 150), then `ollama create qwen2.5:7b-sft` and step 7 as in the 11-12 00:08 list.

## Addendum (07:35): the 2 files obtained, results read
- Download issue SOLVED: user got both files (the browser saved them as `.txt`); renamed to `train_log.json` (valid JSON array) and `val_samples.jsonl` (4 lines, valid JSONL) in `telaah-sft-qwen7b_notebook/`. All Version #3 outputs are now local.
- Run: 151 steps, 1 epoch, train_runtime 22,790 s = 6.3 h (incl. 4 evals x ~550 s on the 111 val); smoke estimate was ~9 h. Final mean train_loss 0.223.
- eval_loss: step 50 0.1949 -> step 100 0.1807 -> step 150 0.1733 (step 151 0.1734). Still falling, but by less each time (-0.014, then -0.007), while the LR decayed to ~0 (linear). Train loss at the end ~0.17-0.20, close to val -> no sign of overfitting.
- Train loss: 0.527 (step 5) -> ~0.24 by step 25 -> 0.15-0.24 for the rest (noisy, by batch).
- Cell 9 val samples (4 only, too few to judge): 2 of 4 right.
  - s0225-1 table_lookup: right value (58,905,232) and right citation [bni_2024 p.1228]. OK.
  - s0343-1 table_lookup: right page [bni_2025 p.616] but WRONG number (9,595,520 vs gold 4.191.996) -> read the wrong cell/row of the table.
  - s0132-1 refusal_removed (evidence page removed, gold TIDAK DITEMUKAN): model HALLUCINATED an SK number with a citation [bri_2024 p.518]. Watch the refusal rate in step 7.
  - s0128-1 refusal_scope: correctly answered TIDAK DITEMUKAN. OK.
- Second epoch: by the rule ("only if val loss still falls at 150") it qualifies, but the gain is shrinking and it would cost another ~6-7 h of GPU quota. Suggested: run step 7 (base vs SFT on 439 dev) with this epoch-1 model first, then decide. Not decided yet (user).
## Next (replaces the list above)
1. User decides: step 7 first (suggested) or a second epoch now.
2. Move outputs to `sft/out/` (check the GGUF is gitignored), `ollama create qwen2.5:7b-sft` (TEMPLATE/PARAMETER from `ollama show --modelfile qwen2.5:7b-gpu`, num_gpu 99, num_ctx 8192), sanity questions incl. s0343-1 and s0132-1.
3. Step 7: base vs SFT on full 439 dev, JUDGE_MODEL pinned to base; compare numeric match, citation and refusal (refusal_removed especially); re-check YEAR_UNION.

# Update — 2026-11-12 (07:50): Step 7 started (user runs every command by hand, Claude checks each part)
## Done
- Outputs moved to `sft/out/` (9 files); `out/` added to `sft/.gitignore` (git does not list the GGUF). `telaah-sft-qwen7b_notebook/` is empty (user may delete).
- `sft/out/Modelfile.sft` = `ollama show --modelfile qwen2.5:7b-gpu` with FROM -> `./qwen2.5-7b-telaah-sft-Q4_K_M.gguf` (same ChatML TEMPLATE, num_gpu 99, num_ctx 8192; written UTF-8 without BOM via [IO.File]::WriteAllLines). `ollama create qwen2.5:7b-sft -f Modelfile.sft` OK (id 3587555c35f7, 4.7 GB).
- Sanity via `telaah ask` with `$env:LLM_MODEL="qwen2.5:7b-sft"`, `$env:TELAAH_TRANSCRIPTS="1"`: q008 137,40% [mandiri_2025 p.782] (value right; gold page is p.40, base also cited 782); q016 "paling sedikit 3 (tiga) orang" [ojk_pojk_17_2023 p.15] = gold page (base run 065918 cited p.56); q043 bare "TIDAK DITEMUKAN". Stops cleanly. The QdrantClient.__del__ "sys.meta_path is None" traceback at exit is shutdown noise.
## Step 7 run settings (both runs identical except LLM_MODEL)
- `$env:JUDGE_MODEL="qwen2.5:7b-gpu"`, `$env:TELAAH_TRANSCRIPTS="1"`, defaults ON (SECOND_LOOK, CITE_REPAIR, YEAR_UNION), vision as in .env (Gemini key set, VISION_PAGES 5), `telaah eval --file eval/bench/dev.jsonl --agent --router --judge-on-fail` with workers 1 (SFT run swaps the SFT and judge models in the 6 GB VRAM; threads would thrash). Base first, then SFT. The run JSON does not record JUDGE_MODEL or env switches: they are listed here.
- After both: grep the logs for "vision step skipped" (Gemini quota) and compare counts between the runs.

# Update — 2026-11-12 (10:05): Step 7 part 5 DONE (base run on 439), SFT run NOT started yet (handoff)
## Results: base `qwen2.5:7b-gpu`, new defaults, run `eval/runs/bench-dev-20261112-075716.json` (439 q, 07:57-~10:00)
- Settings: `$env:LLM_MODEL="qwen2.5:7b-gpu"`, `$env:JUDGE_MODEL="qwen2.5:7b-gpu"`, `$env:TELAAH_TRANSCRIPTS="1"`, `telaah eval --file eval\bench\dev.jsonl --agent --router --judge-on-fail`, workers 1, vision as in .env. Log `eval/bench/eval_step7_base.log` (UTF-16, Tee-Object): 0 error / traceback / quota / "vision step skipped" lines.
- Overall (vs old base 065918, defaults OFF): recall 0.777 (0.774), citation 0.629 (0.560), refusal 0.918 (0.818), numeric 0.566 (0.470), judge 0.717 (0.715), faithful 0.837 (0.853, not comparable: judge-on-fail), 16.8 s/q.
- By type, numeric old -> new: calculation 0.206 -> 0.309, chart 0.516 -> 0.742, cross_doc 0.283 -> 0.283, regulation 0.889 -> 1.000, table_lookup 0.571 -> 0.667, text_fact 0.755 -> 0.796. Citation: table 0.524 -> 0.714, text 0.500 -> 0.589, chart 0.468 -> 0.532. 22/22 unanswerables refused.
- THIS run is the baseline the SFT run must beat (gate: numeric + citation up, refusal not lower than 0.918, 22/22 unanswerables refused).
## Next (part 6, user runs by hand; Claude checks)
1. SFT run on 439, same settings except LLM_MODEL. New PowerShell window in C:\Users\User\genai-project:
   `$env:LLM_MODEL="qwen2.5:7b-sft"`; `$env:JUDGE_MODEL="qwen2.5:7b-gpu"`; `$env:TELAAH_TRANSCRIPTS="1"`; `powercfg /change standby-timeout-ac 0`; `ollama list` (Ollama running?); then
   `.venv\Scripts\telaah.exe eval --file eval\bench\dev.jsonl --agent --router --judge-on-fail | Tee-Object -FilePath eval\bench\eval_step7_sft.log`
   Expect `0 questions already done, 439 to run`. Slower than base (SFT and judge models swap in the 6 GB VRAM): est. 2.5-3.5 h. Laptop plugged in, lid open, internet on (Gemini vision for chart questions). If interrupted: Ctrl+C, then same env lines + `--resume eval\runs\<that run's>.partial.jsonl`.
2. Claude (Opus 5.5) compares SFT vs base 075716: overall + by type, right->wrong / wrong->right lists, refusal_removed-style hallucinations, 22 unanswerables, vision-skipped counts in both logs; re-check YEAR_UNION if needed. Then decide: keep SFT / second epoch / drop.
3. Afterwards: restore sleep (`powercfg /change standby-timeout-ac <minutes>`, user's old value unknown); commit `sft/.gitignore`, `sft/split_sft.py`, KAGGLE_SETUP.md, notebook, this note when the user says so; then the interview paper.

# Update — 2026-11-13 (00:20): Step 7 DONE, SFT does NOT pass the gate, base model stays
## Results: SFT `qwen2.5:7b-sft` (epoch 1) on 439 dev, run `eval/runs/bench-dev-20261112-215223.json` (21:52-~00:15), log `eval/bench/eval_step7_sft.log`
- Same settings as base run 075716 except LLM_MODEL (JUDGE_MODEL=qwen2.5:7b-gpu, TELAAH_TRANSCRIPTS=1, defaults ON, workers 1). Both logs: 0 error/traceback/quota/"vision step skipped" lines -> fair comparison.
- Overall base -> SFT: recall 0.777 -> 0.772, citation 0.629 -> 0.683, refusal 0.918 -> 0.902, numeric 0.566 -> 0.557, judge 0.717 -> 0.712, faithful 0.837 -> 0.759 (judge-on-fail, not comparable), 16.8 -> 19.6 s/q. Unanswerables 22/22 refused in both.
- By type numeric: calculation 0.31 -> 0.34, chart 0.74 -> 0.66, cross_doc 0.28 -> 0.25, regulation 1.00 -> 1.00, table 0.67 -> 0.69, text 0.80 -> 0.80. Citation: regulation 0.53 -> 0.71, text 0.59 -> 0.71, calc 0.34 -> 0.38, table 0.71 -> 0.69, chart 0.53 -> 0.53.
- Numeric flips: 19 wrong->right, 22 right->wrong. Refusal flips: 18 worse (over-refusal on answerable questions, e.g. chart bd0156/bd0160 with a Gemini transcript in context; bd0034, bd0091, bd0211, bd0242), 11 better.
- Failure kinds in the 22 losses: over-refusal 7, wrong row/cell on the right page 15 (bd0118 HQLA, bd0127/bd0129 Stage-1, bd0146 31 vs 2 meetings, bd0183 credit). Some chart losses may be scorer artifacts (bd0204 "82%" vs base "82,00%", bd0193 39,90% vs 40%), unchecked against gold; does not change the verdict.
## Decision (user, 00:19)
- Gate FAILED (numeric not up, refusal lower). KEEP base `qwen2.5:7b-gpu` as the default LLM. No second epoch (val loss gains small; failures are behaviour: over-refusal + misread cells).
- Report SFT as a mixed/negative result in README and the interview paper: citations up (+0.05 overall, regulation/text +0.12-0.18), accuracy and refusal not; the eval gate stopped a regression.
- Optional later (not planned): SFT data v2 with a smaller refusal share (now 20%) and more look-alike table examples; costs ~7 h Kaggle GPU.
## Next
1. Restore sleep: `powercfg /change standby-timeout-ac 10` (old value per earlier notes).
2. Interview paper (spec in the 2026-11-10 13:40 entry, Next item 5); numbers from the run files, incl. this SFT result. Model: Opus 5.5.
3. README: add Step 7 / SFT section; commit uncommitted SFT/Kaggle files when the user says so (`sft/.gitignore`, `sft/split_sft.py`, KAGGLE_SETUP.md, `kaggle/sft_qwen7b_qlora.ipynb`, this note). `sft/out/` (GGUF 4.7 GB) stays git-ignored; `ollama rm qwen2.5:7b-sft` only if disk space is needed.
4. Still open from before: user reviews `candidates_test.jsonl`, writes 8 test unanswerables, demo video; stray `eval/runs/bench-dev-20261112-074815.partial.jsonl` can be deleted.

# Update — 2026-11-13 (morning): interview paper started (Claude Doc), no-RAG baseline switch, manual check of 30
## Done (UNCOMMITTED)
- Paper format decided by the user's guide (`rag-perbankan-paper-guide.md`): arXiv-style technical report, 6-10 pages, applied-deep theory (what / why / alternative, no maths), recruiters as readers; interview Q&A per role is a SEPARATE deliverable, made AFTER the paper. Personas: financial/credit analyst + compliance.
- Paper is a Claude Doc: https://claude.ai/artifact/8LcJgmQJA7g4EMXp8aW3x7 . All sections written except the Abstract and 6.1's closed-book row (waiting for the no-RAG run). Architecture diagram (sec 4) and retrieval-ablation chart (sec 6.2) drawn.
- `telaah eval --no-rag` added: `answer.ask_no_rag` (NO_RAG_SYSTEM: same 7B, no documents, `TIDAK DITEMUKAN` if unknown); `run_eval.run(no_rag=True)` sets recall and faithfulness to None, file prefix `bench-dev-norag-`, config records `no_rag`. Files: `src/telaah/answer.py`, `eval/run_eval.py`, `src/telaah/cli.py`. Syntax-checked only; the user's smoke run (7 ids) is the first real test.
- Manual check of 30 answers from base run 075716 (5 per answerable type, seed 20261113): `eval/manual_check_20261113.md`. 25 right, 1 defensible (bd0217: report p.333 prints 5,3%), 4 wrong (scope/row). Numeric scorer: 0 false positives, 2 false negatives (bd0320 "23,5%" vs "23,50%", bd0329 gives difference only). Citation auto 22 vs manual 23 supported. Judge agrees on 17/17 judged clear cases.
## Running/pending
- User runs the no-RAG smoke (`--no-rag --ids q016 q001 q028 bd0205 q033 bd0333 q041`), then the full 439 with `Tee-Object eval\bench\eval_norag.log`. Sleep is set to 0 for it; restore with `powercfg /change standby-timeout-ac 10` afterwards.
## Next
1. Read the no-RAG results; fill 6.1 closed-book row + the Abstract; final read-through of the doc.
2. Then the interview Q&A document (AI engineer / data analyst / banking).
3. Commit when the user says so (no-RAG switch, manual check file, SFT/Kaggle files listed in the 11-13 00:20 entry).

## No-RAG baseline DONE (2026-11-13 ~09:00, `eval/runs/bench-dev-norag-20261113-083031.json`, 439 q, 4.1 s/q)
- Smoke run first: `bench-dev-norag-20261113-082808` (7 ids; can be deleted). The `--no-rag` switch works.
- Closed book, same qwen2.5:7b-gpu: numeric 0.012, refusal 0.109, citation 0.050 (only the 22 unanswerables), judge 0.308 (over the 26 answered only). Refused 391/417 answerable (94%) and 22/22 unanswerable; 0 invented page citations. The 4 numeric hits are all POJK 17/2023 board rules (q016, q017, bd0353, bd0364); 0 bank figures right.
- Paper: 6.1 row + paragraph, Intro sentence and Abstract written. All sections of the doc are now filled.
- Restore sleep: `powercfg /change standby-timeout-ac 10`.

## Interview Q&A doc written (2026-11-13 ~09:30)
- https://claude.ai/artifact/VFAnMHyJs14bsnfx2MvTwM : pitch (30 s / 2 min + numbers), common questions, AI engineer, data analyst, banking/risk/compliance (incl. IT audit angle), tricky follow-ups. Numbers from the paper. McNemar on base vs SFT flips (19 vs 22): p = 0.76.

# Update — 2026-11-13 (09:15): handoff — paper and interview Q&A drafted (this block replaces the morning "Running/pending" and "Next")
## Done
- PAPER (Claude Doc, complete draft): https://claude.ai/artifact/8LcJgmQJA7g4EMXp8aW3x7 — Abstract; 1 Intro; 2 Related work (12 refs); 3 Background (design-choice table); 4 System design + architecture diagram; 5 Eval setup; 6 Results (6.1 main table incl. closed-book row, 6.2 retrieval-ablation chart, 6.3 defaults, 6.4 agent tasks, 6.5 manual check); 7 Error analysis; 8 Fine-tuning; 9 Limitations; References. All numbers from run files.
- INTERVIEW Q&A (Claude Doc): https://claude.ai/artifact/VFAnMHyJs14bsnfx2MvTwM — pitch, common, AI engineer, data analyst, banking/risk/compliance, tricky follow-ups.
- Format decisions (user's guide): arXiv-style report, 6-10 pages, applied-deep theory, recruiters as readers; personas analyst + compliance; Q&A separate from the paper.
- No-RAG baseline (`bench-dev-norag-20261113-083031`): numeric 0.012, refused 391/417 answerable, 22/22 unanswerable, 0 invented citations.
- Manual check of 30: `eval/manual_check_20261113.md` (25 R, 1 D, 4 W; scorer conservative).
## Uncommitted (commit when the user says so)
- `--no-rag`: `src/telaah/answer.py`, `eval/run_eval.py`, `src/telaah/cli.py`; `eval/manual_check_20261113.md`; this note; plus the SFT/Kaggle files from the 11-13 00:20 entry (`sft/.gitignore`, `sft/split_sft.py`, KAGGLE_SETUP.md, `kaggle/sft_qwen7b_qlora.ipynb`).
- Deletable: `eval/runs/bench-dev-norag-20261113-082808.*` (7-question smoke), `eval/runs/bench-dev-20261112-074815.partial.jsonl`.
## Next
1. User reads the paper and the Q&A; comments in the docs -> Claude revises. Export to PDF when final.
2. Restore sleep if not done: `powercfg /change standby-timeout-ac 10`.
3. README: add Step 7 / SFT section and the closed-book row; commit.
4. Companion pieces (guide): README results section, 2-3 min demo video/GIF, LinkedIn post.
5. Strengthen the numbers: user reviews `candidates_test.jsonl` + writes 8 test unanswerables -> run the blind test split once (base model), report beside dev; held-out set #3 written by someone else.

# Update — 2026-11-13 (11:30): two rule fixes from the 36 wrongly refused answerable questions (UNCOMMITTED, not yet evaluated)
## Diagnosis (base run 075716, 417 answerable dev q, 36 answered TIDAK DITEMUKAN)
- 6 refused by the router's unknown-bank guard before any search (bd0033 "Bank Raya", bd0045 "Keuangan Bank", bd0079/bd0100 "Bank Secara Individu", bd0101 "Bank Syariah Indonesia", bd0103 "Dana Bank").
- 16 retrieval misses (recall@5 0), 14 reading misses (gold page in top 5). Of the misses: `filters.REG_RE` did not read "PADG No. 27", spelled-out names ("Peraturan Bank Indonesia Nomor 6", "Surat Edaran Otoritas Jasa Keuangan Nomor 34/SEOJK.03/2016", "Peraturan Anggota Dewan Gubernur (PADG) Nomor 26") or "PADG Bank Indonesia No. 20" -> no document filter on 21 dev questions (8 with recall 0).
- Not fixed (noted for later): neighbour-page misses (bd0137, bd0148, bd0180); agent placeholder leak "[doc_id p.N]" (bd0271) and non-existent `mandiri_2023` cite (bd0228); growth questions on the rag route with the gold page (bd0227, bd0267); line-chart month/year reads (q031, bd0154, bd0169); bd0167 gold may be wrong (model read Rp14.820 miliar as 2023, gold says 2022): check bni_2024 p.340.
## Done (UNCOMMITTED)
- `facts.unknown_banks`: "secara" in NOT_A_BANK; X_NOT_A_BANK (keuangan, dana, kredit, aset, modal, likuiditas, kesehatan) for "<Word> Bank"; no unknown bank when the question names a corpus bank AND "laporan tahunan" (a bank named inside that report). Known trade-off: "NPL Bank X vs BRI menurut Laporan Tahunan BRI" is no longer refused by the router.
- `filters.REG_RE` + `reg_kind()`: "No."/"No", spelled-out names, "(PADG)", "PADG Bank Indonesia". 
- Regex replay over dev + agent_tasks + heldout + heldout2 + seed (629 q; test files NOT read): only the 6 guard releases and 20 new regulation groups changed; all unknown-bank unanswerables still flagged (q041, q042, bd0381, bd0388, h035, k035). New asserts in tests/test_facts.py and tests/test_second_look.py (pass with a stub loader; full pytest needs the Windows venv).
## Next
1. User: `.venv\Scripts\python.exe -m pytest -q`.
2. User: re-run the 26 changed dev ids with the base-run settings (LLM_MODEL and JUDGE_MODEL qwen2.5:7b-gpu, TELAAH_TRANSCRIPTS=1, `--agent --router --judge-on-fail --ids ...`); Claude compares with 075716 on those ids. Keep only if no regression; dev is tuned on, so a gain counts only after the blind test.

## Result of the two rule fixes (2026-11-13 14:30, run `eval/runs/bench-dev-20261113-141653.json`, 26 ids, base-run settings)
- 26 changed ids, base 075716 -> new: recall@5 0.46 -> 0.85, citation 0.35 -> 0.65, refusal 0.65 -> 0.88, numeric 0.43 -> 0.57 (7 numeric q), judge 0.94 -> 0.95.
- Bank guard (6): bd0033 and bd0079 now right (bd0079 found by second look on p.456); bd0101 right figure but written Rp7,442,650,000 (unit x1000) and cited p.33 instead of p.492; bd0100 now a WRONG figure (518.873.804 from p.457, gold 445.431.375 on p.456) instead of a refusal; bd0045 (gold page retrieved) and bd0103 still refuse.
- Regulation (20): recall 0 -> 1 on 7 (bd0341, bd0344, bd0357, bd0359, bd0367, bd0368, bd0370); bd0368, bd0370, bd0373 refused -> right. One loss: bd0361 now refuses; its base answer ("PBI 6/2026") was actually wrong vs gold "Peraturan Anggota Dewan Gubernur" but the judge scored it 1.0 (lenient judge).
- The other 413 dev questions route and filter exactly as before (regex replay), so they are unaffected apart from run-to-run noise.
- Verdict (Claude): keep both fixes. Pending: user's pytest result; commit when the user says so.
- 14:35 pytest (user): 1 failed / 108 passed. `test_step_year_must_be_asked_by_the_question` failed because my new `REPORT_RE` in facts.py shadowed the existing `REPORT_RE` (line 22, report-id pattern used by `extract_doc` and by `answer_step` when an agent step passes `docs`). Renamed mine to `ANNUAL_REPORT_WORDS_RE`; the test case now gives bri_2025 again (stub check); regex replay unchanged. The 26-id run is still valid: all 26 went through route rag/refuse, and `answer_step` hits the shadowed line only with `docs` (agent entity steps); `extract_doc` runs only at ingest. Lesson: grep a module for a name before adding a module-level constant.

# Update — 2026-11-13 (14:40): handoff — rule fixes committed (this block replaces the earlier 11-13 "Next" lists)
## Done
- Commit eae09ff "Router: fewer false bank refusals, read spelled-out regulation names": `facts.unknown_banks` (generic phrases, banks named inside a corpus bank's report; constant `ANNUAL_REPORT_WORDS_RE`), `filters.REG_RE` + `reg_kind()` (No., spelled-out names, (PADG), PADG Bank Indonesia), tests (pytest 109 passed), notes. 26-id re-run `bench-dev-20261113-141653`: recall@5 0.46 -> 0.85, citation 0.35 -> 0.65, refusal 0.65 -> 0.88.
- Decision (user): the paper stays as it is (numbers from base run 075716); the rule fixes are post-eval and not added to the paper.
- PowerShell tip for the user: paste only the command, never the `PS C:\...>` prompt or git's output (`ps` = Get-Process alias; harmless errors otherwise).
## Uncommitted (commit when the user says so)
- `--no-rag` switch (`src/telaah/answer.py`, `eval/run_eval.py`, `src/telaah/cli.py`), `eval/manual_check_20261113.md`, SFT/Kaggle files (`sft/.gitignore`, `sft/split_sft.py`, KAGGLE_SETUP.md, `kaggle/sft_qwen7b_qlora.ipynb`). Scratch `eval/bench/_*.py`, `eval_ab_*.err`. `test.jsonl` / `candidates_test.jsonl`: blind test, never read.
- Deletable: `eval/runs/bench-dev-norag-20261113-082808.*`, `eval/runs/bench-dev-20261112-074815.partial.jsonl`, `eval/runs/bench-dev-20261113-141428.partial.jsonl` (empty, Ollama was not running).
## Next (suggested order; user picks)
1. User reads the paper (https://claude.ai/artifact/8LcJgmQJA7g4EMXp8aW3x7) and the interview Q&A (https://claude.ai/artifact/VFAnMHyJs14bsnfx2MvTwM), comments in the docs -> Claude revises -> PDF export.
2. Commit the uncommitted work above; README: add Step 7 / SFT section and the closed-book row.
3. 2-3 min demo video from the local Gradio app (`.venv\Scripts\python.exe app.py` -> http://127.0.0.1:7860), then LinkedIn post.
4. Blind test: user reviews `candidates_test.jsonl` in `review_app.py` (Test) + writes 8 test unanswerables -> one base-model run, report beside dev.
5. Optional fixes from the 36-refusal diagnosis: agent placeholder leak "[doc_id p.N]" (bd0271) and `mandiri_2023` cite (bd0228); neighbour-page misses (bd0137, bd0148, bd0180); bd0167 gold check (bni_2024 p.340: Rp14.820 miliar is 2022 or 2023?); bd0045/bd0103 still refuse; bd0100 wrong row (p.457 vs p.456).
## Reminders
- Ollama must be running (`ollama serve` or the app) before any eval: "Connection error / WinError 10061" = Ollama not started. Start evals from `C:\Users\User\genai-project`.
- Restore sleep if not done: `powercfg /change standby-timeout-ac 10`.

# Update — 2026-11-16: benchmark review session (Claude in Chrome + linked folder)
## Done
- `eval/bench/review_app.py`: new "Show type" dropdown (filter the queue to one type; decisions still go to reviewed_{split}.jsonl). Backup `review_app.py.bak_pre_filter`.
- TEST split reviewed by Claude at the user's request (against BENCHMARK.md rules 1-2; recorded in BENCHMARK.md Status). 117 decisions: text_fact 32/30 (2 chart drafts retyped as text_fact), table_lookup 30/30, chart 23/23, regulation 15/15; calculation and cross_doc NOT started (cross_doc has only 14 test drafts for a quota of 22). Questions rewritten without page numbers, answers in Indonesian format, extra gold pages added where the same figure/meaning is on other pages. 4 extra chart accepts undone (backup `_reviewed_test.backup_before_undo.jsonl`). Consequence: test v1 is "Claude-seen".
- Dev completed: `sample_pages.py --round 3` (dev only, no reuse of rounds 1/2; backup `_sample_pages.py.bak_pre_r3`) -> `pages3.jsonl` (30 table_lookup + 58 chart). User drafted it (66 drafts). Claude accepted 14 via `bulk_review.py` (`_decisions_r3.json`; 52 left undecided). `build.py`: dev 450/450, dev.jsonl sha256 0250341f91e95052dde16886475cba3c8e953649fb90fa8d0211f536a43898f2 (11 new questions vs the 439-question file; old copy `_dev.jsonl.bak_20261116`).
## In progress
- User started the full dev eval: `.venv/Scripts/telaah eval --router --file eval/bench/dev.jsonl` (first attempt 14:42 failed: Ollama not running; `bench-dev-20261116-144253.partial.jsonl` is empty and deletable). Note: these are NOT the base-run settings of 075716 (no LLM_MODEL/JUDGE_MODEL/TELAAH_TRANSCRIPTS/--agent/--judge-on-fail); for comparability run the same settings, or only the 11 new ids with `--ids`.
## Next
1. When the eval finishes: Claude summarises per-type scores from `eval/runs/bench-dev-*.json` and compares with 075716.
2. Test split decision (user): (a) user re-checks the 117 Claude decisions and reports test v1 with the "Claude-seen" caveat, (b) fresh test split (new test pages, Gemini drafts, user review) — Claude's recommendation, or (c) accept as is with caveat. Do not continue calculation/cross_doc on the current test split.
3. Deletable scratch: `eval/bench/_tmp_render/` (page renders), the backups above once satisfied.
## Reminders
- Claude cannot run commands in the Windows terminal (computer use is click-only for terminals) and the linked VM/cloud cannot reach Gemini or local Ollama: drafting and evals are run by the user.

# Update — 2026-11-16 (evening): full dev eval 450/450 finished
## Result (`eval/runs/bench-dev-20261116-144623.json`, dev.jsonl 450 q, router + agent, `qwen2.5:7b-gpu`, 19.7 s/q)
- This is the DEV split (not the blind test). Overall: recall@5 0.769, citation 0.582, refusal 0.918, numeric 0.534, judge 0.811, faithful 0.827.
- vs base run 075716 (439 q): recall 0.777, citation 0.629, refusal 0.918, numeric 0.566, judge 0.717, faithful 0.837, 16.8 s/q.
- Caveats: judge and faithful are NOT comparable (base used `--judge-on-fail`, this run did not; the judge jump 0.717 -> 0.811 is mostly that). Dev grew by 11 questions (table 84 -> 90, chart 62 -> 67). Base predates the 11-13 rule fixes (eae09ff).
## By type (this run; base 075716 in brackets)
- calculation n=68: recall 0.662 (0.691), citation 0.265 (0.338), refusal 0.794 (0.824), numeric 0.265 (0.309).
- chart n=67: recall 0.672 (0.758), citation 0.418 (0.532), refusal 0.806 (0.887), numeric 0.627 (0.742).
- cross_doc n=68: recall 0.985 (0.985), citation 0.926 (0.926), refusal 0.971 (0.985), numeric 0.267 (0.283).
- regulation n=45: recall 0.933 (0.778), citation 0.644 (0.533), refusal 0.978 (0.911), numeric 1.0 (1.0). Gain from the 11-13 rule fixes.
- table_lookup n=90: recall 0.667 (0.702), citation 0.611 (0.714), refusal 0.944 (0.893), numeric 0.678 (0.667).
- text_fact n=90: recall 0.722 (0.711), citation 0.544 (0.589), refusal 0.978 (0.967), numeric 0.755 (0.796).
- unanswerable n=22: refusal 1.0 (1.0).
## Reading
- Regulation clearly up; unanswerables unchanged at 22/22. Chart numeric/refusal and table citation are down; 5 of the new chart questions may explain part of the chart drop. Calculation moves within the known +-1-2 question noise.
- Not diagnosed yet: which questions flipped right -> wrong per type (needs a per-id diff against 075716, mapping new ids via `_dev.jsonl.bak_20261116`).
## Next
1. Optional: re-run with base-run settings (`--judge-on-fail`) for comparable judge/faithful, or diff per id for chart/table.
2. Test-split decision (a/b/c in the 11-16 review entry) still open. Deletable: `eval/runs/bench-dev-20261116-144253.partial.jsonl` (empty).

## Per-question diff vs base 075716 (2026-11-16 18:40; matched by question text, 439/439 mapped, 14 new ids: 7 table, 7 chart)
- Numeric flips: 14 wrong->right, 24 right->wrong. Chart 4 / 11, calculation 3 / 6, table 7 / 4, text 0 / 2, cross_doc 0 / 1.
- Main cause: this run was NOT started with `TELAAH_TRANSCRIPTS=1` (base was). Evidence: chart recall drops on 8 questions (bd0165 bd0169 bd0191 bd0202 bd0203 bd0207 ...) and all 8 chart gold pages checked have a file in `data/page_transcripts/`; 8 chart questions now refuse with the gold page in or near the top 5. Also no `--judge-on-fail` (judge None 59 vs 195 in base), so judge/faithful are not comparable.
- Regulation gains (recall +7, refusal +3, citation +7) = the 11-13 rule fixes (eae09ff), as expected.
- Other losses look like 7B noise: calc agent answers "0" (bd0216, bd0252), format "1.669,55 juta" vs gold 1.669.546 (bd0249), over-refusals (bd0220, bd0229, bd0306).
- Verdict: no code regression shown; this run is not comparable with 075716. Fair rerun = base settings (LLM_MODEL/JUDGE_MODEL qwen2.5:7b-gpu, TELAAH_TRANSCRIPTS=1, `--agent --router --judge-on-fail`), ~2.5 h.

# Update — 2026-11-16 (19:50): fair 450-question rerun PAUSED at 268/450 (resume later)
- Rerun with the base-run settings of 075716 started 18:36: progress file `eval/runs/bench-dev-20261116-183616.partial.jsonl` (268 questions done; the user stops it with Ctrl+C). Log `eval/bench/eval_dev450.log`.
- To resume (new PowerShell window in `C:\Users\User\genai-project`, Ollama running; the env lines are REQUIRED again, otherwise the second half runs with other settings):
  `$env:LLM_MODEL="qwen2.5:7b-gpu"; $env:JUDGE_MODEL="qwen2.5:7b-gpu"; $env:TELAAH_TRANSCRIPTS="1"`
  `.venv\Scripts\telaah.exe eval --file eval\bench\dev.jsonl --agent --router --judge-on-fail --resume eval\runs\bench-dev-20261116-183616.partial.jsonl 2>&1 | Tee-Object -Append eval\bench\eval_dev450.log`
  Expect ~268 done, ~182 to run (~1-1.5 h).
- When finished: Claude compares the final `bench-dev-20261116-183616.json` with 075716 per type and per question (match by question text via `_dev.jsonl.bak_20261116`; 14 ids are new). The earlier no-transcripts run `bench-dev-20261116-144623` is not comparable (see the diff entry above).

# Update — 2026-11-17: fair 450-question rerun finished + per-id diff vs base 075716
- Run `eval/runs/bench-dev-20261116-183616.json` (dev, base-run settings, resumed at 295). Overall recall 0.782, citation 0.607, refusal 0.938, numeric 0.557, judge 0.725, faithful 0.854, 17.3 s/q. Unanswerables 22/22. Per type numeric: calc 0.309, chart 0.687, cross_doc 0.283, regulation 1.0, table 0.667, text 0.776.
- Per-id diff on 436 matched questions (matched by text; 3 base questions no longer in dev): numeric 6 wrong->right (table 4, calc 2), 6 right->wrong (bd0052, bd0092, bd0120, bd0156, bd0217, bd0229) = noise. Refusal 13 better (regulation 3, table 4, calc 4) vs 5 worse. Recall 11 up (regulation 7) / 10 down. Citation 15 up (regulation 8) / 22 down (table 9, calc 5, chart 4): not diagnosed.
- 14 new questions: table 2/7 numeric, chart 3/7 -> they explain the chart numeric drop 0.74 -> 0.687 (matched chart: 0 up, 1 down). No code regression; rule fixes (eae09ff) visible in regulation + refusal.
- 450-question dev baseline for later comparisons = this run.

## CORRECTION (2026-11-17): extra-gold id shift; run re-scored (supersedes the citation/recall lines above)
- Bug: `eval/bench/extra_gold_dev.json` is keyed by question id; the dev-450 rebuild shifted 307 ids, so extra gold pages sat on neighbour questions during run 183616 (and 144623). Fixed in commit 95fcd26 (81 entries remapped by question text; old bd0147 dropped, its question is no longer in dev).
- `eval/runs/bench-dev-20261116-183616.json` re-scored offline (citation_acc + recall@5 only; 23 fields changed; parse of the stored answers reproduced the original scores 450/450 first). Original kept as `bench-dev-20261116-183616.before_rescore.json`. Caveat: `--judge-on-fail` skip decisions used the old citation/recall, so a few judge values may be missing/present differently (judge not re-run).
- Corrected overall: recall@5 0.798 (base 075716 0.777), citation 0.638 (0.629); numeric/refusal/judge unchanged. By type recall/citation: calc 0.662/0.324, chart 0.791/0.507, cross_doc 0.985/0.926, regulation 0.933/0.711, table 0.711/0.700, text 0.733/0.589.
- Of the "22 citation drops", 13 were the id shift. Real drops ~9: refusals with no cite (bd0064, bd0092, bd0229), wrong page same doc (bd0035 p.1006 vs 993, bd0052 p.194, bd0211 p.85/182 vs 87), one page off (bd0086 p.597 vs 598), agent adds a 2024 cite beside the right 2025 page (bd0216, bd0217). Verdict unchanged: no regression.
- Next: guard so extra gold cannot silently drift from question ids (store question text, assert on load). Model: Opus 5.5.
- Guard added (2026-11-17): `extra_gold_dev.json` is now `{id: {"q": question text, "pages": [...]}}`; `telaah.metrics.load_extra_gold` raises if a text does not match its id (used by run_eval, extra_gold.py --rescore, sft/page_pool.py, _calc_diag/_miss/_retr_dev). After any dev rebuild run `python eval/bench/extra_gold.py --remap`. Tests: tests/test_extra_gold.py (pytest 115 passed). A plain `extra_gold.py` rebuild overwrites hand edits (bd0224).

# Update — 2026-11-17 (handoff): dev-450 baseline fixed and guarded
## Done (all committed, last commit 2a337a5)
- Fair 450-question rerun finished (`eval/runs/bench-dev-20261116-183616.json`, base-run settings). Per-id diff vs 075716: numeric 6 up / 6 down (noise), refusal 13 better / 5 worse; no regression.
- Found and fixed the extra-gold id shift (95fcd26); run re-scored offline. CORRECTED numbers (use these): recall@5 0.798, citation 0.638, refusal 0.938, numeric 0.557, judge 0.725, faithful 0.854, 17.3 s/q. Base 075716: 0.777 / 0.629 / 0.918 / 0.566 / 0.717 / 0.837.
- Guard (2a337a5): extra gold stores question text; eval raises on mismatch; `extra_gold.py --remap` after any dev rebuild. pytest 115 passed.
- Benchmark work committed (eb2d1b3), blind test files git-ignored (fe1193c), scratch files deleted. Only `eval/bench/_decisions_r3.json` is untracked (kept on purpose).
## Next (user picks; model per CLAUDE.md)
1. Test-split decision: (a) fresh test split (new pages, Gemini drafts, user review; Claude's recommendation) or (b) report test v1 with a "Claude-seen" caveat. Calculation/cross_doc NOT done on the current test split (cross_doc 14 drafts of 22). Model: Opus 5.5.
2. README: Step 7 / SFT section + closed-book row; use the corrected dev-450 numbers only if the paper/README are meant to move off 075716 (the paper stays on 075716 by user decision). Model: Sonnet 5.5.
3. Demo video from the local Gradio app (`.venv\Scripts\python.exe app.py` -> http://127.0.0.1:7860), then LinkedIn post. Model: Sonnet 5.5.
4. Optional: real citation drops (bd0064, bd0092, bd0229 refusals; bd0035, bd0052, bd0211 wrong page; bd0086 one page off; bd0216/bd0217 extra 2024 cite), the 36-refusal fixes listed on 11-13.
## Reminders
- Restore sleep: `powercfg /change standby-timeout-ac 10`. Ollama must be running before any eval.
