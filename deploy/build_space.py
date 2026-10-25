"""Stage the Hugging Face Space folder in space_build/ (git-ignored). Local file work only: nothing is uploaded.

    .venv/Scripts/python deploy/build_space.py

The folder is what a Space repo needs: app.py, the telaah package without the ingest / CLI / MCP parts, the
data the retrieval reads (Qdrant, BM25, page text, facts table), requirements.txt, the Space README (YAML header
+ model card) and .gitattributes (Git LFS for data/). No chart reading, no ColPali, no .env.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "space_build"
SKIP_CODE = {"ingest", "cli.py", "mcp_server.py", "__pycache__"}
DATA = ["qdrant", "processed", "bm25.pkl", "facts.sqlite"]  # read at run time; page_transcripts stay off

REQUIREMENTS = """--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.11.0
sentence-transformers==6.1.0
qdrant-client==1.19.1
openai==3.29.0
langgraph==1.2.15
python-dotenv==1.2.4
"""  # gradio comes from sdk_version in README.md; versions = the ones the demo was tested with locally

GITATTRIBUTES = "data/** filter=lfs diff=lfs merge=lfs -text\n"

README = """---
title: Telaah
emoji: 📑
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Indonesian bank report & OJK/BI regulation Q&A with citations
---

# Telaah — riset dokumen keuangan Indonesia

Ask questions about the annual reports of five Indonesian banks (BRI, Bank Mandiri, BNI, BCA, BTN; 2024-2025) and
about OJK / Bank Indonesia regulations. Answers come **only from the documents**, carry page citations, and the app
refuses when the answer is not there. Each answer shows whether its figures are on the cited pages.

## How it works
- Retrieval: BAAI/bge-m3 dense search + BM25, fused with reciprocal rank fusion, per-document filtering.
- Router: single figures are read from a facts table extracted from the reports; comparisons and arithmetic go to a
  planner → executor → verifier agent (arithmetic is done in Python); everything else is plain RAG.
- Verifier: every figure in an answer is checked against the page it cites.

## Limits
- Developed and tuned on a small question set; answers can be wrong. Always check the source page.
- Chart reading (vision) is off in this demo: questions that need a chart image are usually refused.
- The language model is shared by all visitors and has a daily quota; the app limits each visitor to one question
  per 15 seconds and 30 per session.
- The documents are public annual reports and regulations; the text shown is extracted from them and may contain
  extraction errors.

## Configuration (Space settings)
| Name | Kind | Value |
|---|---|---|
| `LLM_API_KEY` | secret | key of the OpenAI-compatible API |
| `LLM_BASE_URL` | variable | e.g. `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `LLM_MODEL` | variable | model name at that API |
| `TELAAH_DEVICE` | variable | `cpu` |
"""


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "src").mkdir(parents=True)
    shutil.copy(ROOT / "app.py", OUT / "app.py")
    shutil.copytree(ROOT / "src" / "telaah", OUT / "src" / "telaah",
                    ignore=lambda d, names: [n for n in names if n in SKIP_CODE])
    for name in DATA:
        src, dst = ROOT / "data" / name, OUT / "data" / name
        dst.parent.mkdir(exist_ok=True)
        if src.is_dir():  # .lock is held by a running Qdrant client
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".lock"))
        else:
            shutil.copy(src, dst)
    (OUT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (OUT / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
    (OUT / "README.md").write_text(README, encoding="utf-8")
    files = [p for p in OUT.rglob("*") if p.is_file()]
    print(f"{len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.0f} MB in {OUT}")


if __name__ == "__main__":
    main()
