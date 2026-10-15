# GenAI Flagship Roadmap: Indonesian Multimodal Document Research Agent

Oct 12, 2026 · @Archie PH Sinaga

## Overview

Build an agent that reads messy Indonesian documents (scanned PDFs, tables, charts) and answers multi-step questions with verifiable citations. By month 3 it ships as a live demo, a published benchmark and a fine-tuned small model.

Working name: **Telaah** (Indonesian for "close examination"). Rename freely.

**First data domain: IDX annual reports + OJK/BI regulations.** It is the best starting set because:

- It is public and free to download.
- It mixes every hard case at once: dense financial tables, charts, scanned pages, legal Bahasa Indonesia and English.
- Questions naturally need several steps (find, extract, calculate, compare), which is what agents are for.

The system is domain-agnostic by design. A second collection (BPS publications or UTBK materials) is added after month 3 to prove it generalises.

**What makes it stand out:** most portfolio projects are English-only RAG chatbots with no measurement. This one is multimodal, Indonesian, agentic, fine-tuned and evaluated on a benchmark you publish yourself.

## Setup and constraints

Zero budget, 20+ hours a week, a first showable version within 3 months (12 weeks from mid-October 2026).

| Resource | Used for |
| --- | --- |
| Acer Nitro V15, RTX 4060 laptop (8 GB VRAM) | Daily development, RAG stack, local 7–8B models in 4-bit, small VLMs (2–4B), QLoRA on 1–4B models, eval runs |
| Kaggle / Colab free GPUs | QLoRA and DPO on 7–8B models, larger VLM experiments |
| Free LLM API tiers (Gemini, Groq, OpenRouter free models) | Synthetic data generation, frontier "hard reasoning" route, LLM-as-judge |
| GitHub, Hugging Face Hub, Hugging Face Spaces (free CPU) | Code, dataset, model and live demo hosting |

Work environment: WSL2 (Ubuntu) on Windows, latest NVIDIA driver, laptop plugged in with NitroSense on Performance mode for long runs.

Free-tier limits change often; check each provider's current limits in week 1 and keep a local model as the fallback for every API call.

## Tech stack

Every component is free and open source or has a free tier; pick one option per layer and swap later only if an eval says so.

| Layer | Main choice | Alternative / comparison |
| --- | --- | --- |
| Document parsing | Docling or Marker (PDF to structured text + tables) | Plain OCR baseline (Tesseract / PaddleOCR) |
| Visual page understanding | Small open VLM (Qwen-VL family, 2–4B) | Frontier VLM via free API |
| Visual retrieval | ColPali / ColQwen (page-image embeddings) | Text-only retrieval |
| Text embeddings | Multilingual model (e.g. BGE-M3 or multilingual-E5) | — |
| Vector store | Qdrant (Docker, local) | Chroma |
| Keyword search | BM25 (built into Qdrant or rank-bm25) | — |
| Reranker | Multilingual cross-encoder (e.g. bge-reranker) | — |
| Agent framework | LangGraph | Plain Python loop (good for learning) |
| Tools | MCP servers via the official Python SDK | — |
| Local model serving | Ollama or llama.cpp | vLLM on cloud GPU |
| Fine-tuning | Unsloth + Hugging Face TRL (SFT, DPO) with QLoRA | Axolotl |
| Evaluation | Ragas + custom pytest-style eval scripts | DeepEval |
| Tracing | Langfuse (self-hosted) or Arize Phoenix | — |
| Demo UI | Gradio on Hugging Face Spaces | Streamlit |

Check each library's current version when you install it; this space moves monthly.

## 12-week plan

Four phases of three weeks, starting Monday 19 October 2026 and ending 10 January 2027. Each phase ends with a gate: a measurable result you must hit before moving on.

| Phase | Weeks | Dates | Focus | Gate |
| --- | --- | --- | --- | --- |
| 1 | 1–3 | 19 Oct – 8 Nov | Foundations + baseline RAG | Baseline scores on 50 seed questions |
| 2 | 4–6 | 9 Nov – 29 Nov | Multimodal + hybrid retrieval | Beats baseline on table + chart questions |
| 3 | 7–9 | 30 Nov – 20 Dec | Agent + MCP tools | **MVP demo live**: agent beats single-shot RAG on multi-step tasks |
| 4 | 10–12 | 21 Dec – 10 Jan | Fine-tuning, routing, release | v1.0 release: benchmark + fine-tuned model published |

If the schedule slips, protect Gate 3: the week-9 MVP demo is already a complete, showable project.

### Phase 1 · Weeks 1–3 · Foundations and baseline RAG

Gate: a working text-only RAG with baseline scores on a 50-question seed set.

**Week 1 (19–25 Oct): environment and data**

- [ ] Set up WSL2, CUDA, Python env, Docker, Ollama; confirm the 4060 runs a 7–8B 4-bit model
- [ ] Create the GitHub repo with a clear README skeleton and project structure
- [ ] Download 15–20 IDX annual reports (mix of banks and non-banks, some scanned) and 10–15 OJK/BI regulations
- [ ] Write a document inventory: source, year, language, pages, has tables/charts/scans

**Week 2 (26 Oct–1 Nov): baseline pipeline**

- [ ] Parse PDFs with Docling or Marker; store chunks with page numbers and document IDs
- [ ] Embed with a multilingual model, index in Qdrant, answer with a local 7–8B model
- [ ] Force every answer to cite document + page

**Week 3 (2–8 Nov): seed eval set and baseline numbers**

- [ ] Hand-write 50 questions with gold answers and gold pages: text facts, table lookups, chart reading, cross-document comparisons, unanswerable questions
- [ ] Measure retrieval recall@5, answer correctness and citation accuracy
- [ ] Blog post 1: "Why English RAG breaks on Indonesian financial documents"

### Phase 2 · Weeks 4–6 · Multimodal and advanced retrieval

Gate: clear improvement over the baseline on table and chart questions, shown in a results table.

**Week 4 (9–15 Nov): hybrid retrieval**

- [ ] Add BM25 + vector hybrid search and a multilingual reranker
- [ ] Add query rewriting (Indonesian ↔ English terms, e.g. "kredit bermasalah" ↔ NPL)

**Week 5 (16–22 Nov): multimodal**

- [ ] Add ColPali/ColQwen visual page retrieval
- [ ] Use a small VLM to read retrieved page images for table and chart questions
- [ ] Compare three pipelines: OCR text, structured parsing, page-image retrieval

**Week 6 (23–29 Nov): ablation and write-up**

- [ ] Run the full ablation on the seed set; record cost and latency per query
- [ ] Expand the benchmark to 250 verified questions
- [ ] Blog post 2: the ablation results table and what won on which document types

### Phase 3 · Weeks 7–9 · Agent and MCP tools

Gate: the agent solves multi-step questions better than single-shot RAG, and a public MVP demo is live.

**Week 7 (30 Nov–6 Dec): tools as MCP servers**

- [ ] Build MCP servers: document search, page reader (text + image), Python calculator sandbox, citation checker
- [ ] Test each tool on its own with unit tests

**Week 8 (7–13 Dec): the agent**

- [ ] Build a LangGraph planner → executor → verifier loop
- [ ] Verifier checks every number in the answer against a cited page before responding
- [ ] Add tracing (Langfuse or Phoenix) to inspect each step

**Week 9 (14–20 Dec): agent evals and MVP demo**

- [ ] Write 60 multi-step agent tasks, e.g. "Compare NPL ratio trends of three banks over 2021–2025 and cite each figure"
- [ ] Measure task success rate, steps per task, cost, failure types
- [ ] Expand the benchmark to 450 verified questions; deploy the MVP Gradio demo on Hugging Face Spaces
- [ ] Post the demo video on LinkedIn

### Phase 4 · Weeks 10–12 · Fine-tuning, routing and release

Gate: v1.0 release with a published benchmark and a fine-tuned model that beats its base model on your evals.

**Week 10 (21–27 Dec): synthetic data and SFT**

- [ ] Generate 2,000–5,000 Indonesian Q&A pairs with citations from your corpus using a frontier API
- [ ] Filter them automatically (answer must be supported by its cited page) and spot-check 100 by hand
- [ ] QLoRA SFT on a 3–8B open model (Unsloth; Kaggle/Colab for 7–8B)

**Week 11 (28 Dec–3 Jan): DPO and routing**

- [ ] Build preference pairs: faithful, cited answers vs hallucinated or uncited ones; also correct refusals
- [ ] DPO training; compare base vs SFT vs SFT+DPO on faithfulness and refusal accuracy
- [ ] Add a router: the fine-tuned small model handles simple lookups, the frontier model handles hard reasoning; report cost saved

**Week 12 (4–10 Jan): release v1.0**

- [ ] Publish the 600-question benchmark (plus 60 agent tasks) and the fine-tuned model on Hugging Face with dataset and model cards
- [ ] Final README: architecture diagram, results tables, how to reproduce
- [ ] Long-form write-up (blog or arXiv-style technical report) and a LinkedIn launch post

## Evaluation plan

The benchmark is the project's most valuable output: 600 verified Indonesian document questions plus 60 multi-step agent tasks, each with gold answers and gold pages, published on Hugging Face in week 12. At that size you can report results per question type with real confidence, which small benchmarks cannot.

**Growth schedule**

| By | Verified questions | Agent tasks |
| --- | --- | --- |
| Week 3 | 50 (seed set) | — |
| Week 6 | 250 | — |
| Week 9 | 450 | 60 |
| Week 12 | 600 (150 held out as the test split) | 60 |

**How to reach 600 without burning out:** an LLM drafts candidate questions from sampled pages, and you verify or fix each answer and its page (about 2–3 minutes each, roughly 25–30 hours across the 12 weeks), rejecting anything ambiguous. Write all unanswerable and cross-document questions yourself, since models draft those badly.

**Question types in the benchmark**

| Type | Example | Share |
| --- | --- | --- |
| Text fact | Who is the president director in the 2024 report? | 20% |
| Table lookup | Total third-party funds (DPK) at year end 2024 | 20% |
| Chart reading | Which year had the highest NIM in the five-year chart? | 15% |
| Calculation | Year-on-year loan growth from two tables | 15% |
| Cross-document | Compare CAR of two banks for the same year | 15% |
| Regulation | What minimum ratio does this OJK rule set? | 10% |
| Unanswerable | A figure the documents do not contain (correct answer: refuse) | 5% |

**Metrics, tracked for every pipeline version**

| Metric | What it measures |
| --- | --- |
| Retrieval recall@5 | Gold page appears in the top 5 results |
| Answer correctness | Matches the gold answer (exact for numbers, LLM-judge for text) |
| Faithfulness | Every claim is supported by the cited page |
| Citation accuracy | Cited page is the right page |
| Refusal accuracy | Refuses on unanswerable questions, answers on the rest |
| Agent task success | Multi-step task fully correct |
| Cost and latency | Tokens, seconds and estimated USD per query |

Rules that keep the numbers honest:

- Verify every gold answer and gold page by hand; never draft candidates with the model you are testing.
- Keep the 150-question held-out test split that is never used for prompt tuning or training data.
- Spot-check the LLM judge against 50 of your own manual grades and report the agreement rate.
- Log every run (config, commit hash, scores) so results tables are reproducible.

## Portfolio outputs

Each phase produces something public, so the project builds credibility while it grows rather than only at the end.

| When | Output | Where |
| --- | --- | --- |
| Week 3 | Blog post 1: why English RAG fails on Indonesian financial documents, with baseline numbers | Medium / personal site, shared on LinkedIn |
| Week 6 | Blog post 2: OCR vs structured parsing vs visual retrieval, ablation table | Medium / personal site, LinkedIn |
| Week 9 | Live MVP demo + 2-minute demo video | Hugging Face Spaces, LinkedIn |
| Week 12 | Benchmark dataset with dataset card | Hugging Face Hub |
| Week 12 | Fine-tuned model with model card and eval results | Hugging Face Hub |
| Week 12 | Technical report + launch post | GitHub, blog, LinkedIn, portfolio website |
| Ongoing | Clean repo: README with architecture diagram, results, reproduce steps | GitHub |

On your CV this becomes one strong line, for example: "Built a multimodal agentic RAG system for Indonesian financial documents; published a 600-question benchmark and a fine-tuned model that improved faithfulness by X% over its base." Fill in X from your own results.

## After month 3

After v1.0 the project becomes a platform you keep extending, roughly one extension per month. Pick based on which roles you are targeting at the time.

- **Second domain:** add BPS publications or UTBK materials and rerun the benchmark to show the system generalises.
- **GraphRAG:** build a knowledge graph of entities (banks, ratios, years, regulations) for questions that connect many documents.
- **Voice interface:** speech-in, speech-out questions in Bahasa Indonesia.
- **Regional languages:** test and adapt for Javanese or Sundanese queries, a genuinely under-served area.
- **Red-teaming:** probe the agent with prompt injection hidden in documents and unsafe tool calls; publish the findings.
- **Distillation to 1–3B:** make the small model run fast enough on CPU for a cheaper demo.
- **Continuous evaluation:** a CI job that reruns the benchmark on every commit and blocks regressions.

## Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| 8 GB VRAM runs out (VLMs, long context) | Smaller or more quantized models locally; move the run to Kaggle/Colab |
| Free API tier gets cut or rate-limited | Local 7–8B model for every route; generate synthetic data slowly in batches |
| Kaggle/Colab session limits interrupt training | Save checkpoints often; keep runs under a few hours; a few dollars of RunPod only if truly stuck |
| Scanned reports parse badly | That is a finding, not a failure: report it and let the visual-retrieval pipeline handle those pages |
| Verifying 600 questions takes too long | Ship at least 400 verified questions at v1.0 and reach 600 the following month |
| Agent loops or wanders | Cap steps per task, add a verifier, log failure types and report them honestly |
| Schedule slips (job applications, tutoring, interviews) | Protect the gates, not the weeks: Phase 3's MVP demo is the minimum showable version |
