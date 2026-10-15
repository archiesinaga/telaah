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
