"""Retrieval-only check (no LLM): does the context for a one-figure step question contain the gold figure?

    .venv/Scripts/python eval/step_retrieval_check.py

Each case is a step question as the agent planner writes it plus the figure that must be in the context.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telaah import answer  # noqa: E402
from telaah.filters import detect_groups  # noqa: E402
from telaah.retrieve import retrieve  # noqa: E402

SRC = " (menurut Laporan Tahunan 2025)"
CASES = [
    ("Berapa total aset BRI pada akhir 2024?" + SRC, "1.992.186.906"),
    ("Berapa total aset BRI pada akhir 2025?" + SRC, "2.135.371.105"),
    ("Berapa laba tahun berjalan konsolidasian BRI tahun 2025?" + SRC, "57.132.365"),
    ("Berapa laba tahun berjalan Bank Mandiri tahun 2025?" + SRC, "61.346.133"),
    ("Berapa total aset Bank Mandiri pada akhir 2025?" + SRC, "2.829.948.026"),
    ("Berapa rasio kecukupan modal (CAR) BCA tahun 2025?" + SRC, "29,8%"),
    ("Berapa CAR Tier 1 BCA tahun 2025?" + SRC, "28,6%"),
    ("Berapa KPMM BTN tahun 2025?" + SRC, "19,02"),
    ("Berapa total aset BCA pada akhir 2025?" + SRC, "1.586.829"),
    ("Berapa NPL gross BTN tahun 2021?" + SRC, "3,70"),
    ("Berapa LDR BNI tahun 2021?" + SRC, "79.7"),
    ("Berapa laba bersih BCA tahun 2024?" + SRC, "54.851"),
]


def build(q: str, chunks: list[dict]) -> str:
    try:
        return answer.build_context(chunks, q)  # question-aware excerpt (after the fix)
    except TypeError:
        return answer.build_context(chunks)


if __name__ == "__main__":
    hit = 0
    for q0, want in CASES:
        q = answer.refine_step(q0.replace(SRC, ""), "x" + SRC)  # what the agent planner step becomes
        chunks = retrieve(q)
        ctx = build(q, chunks)
        ok = want in ctx
        hit += ok
        pages = [(c["doc_id"], c["page"]) for c in chunks]
        print(("OK  " if ok else "MISS"), want.ljust(14), q[:60], "->", pages[:5], "| groups", detect_groups(q))
    print(f"{hit}/{len(CASES)} figures in context")
