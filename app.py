"""Telaah demo (Gradio): questions on Indonesian bank annual reports and OJK/BI regulations, answered only from
the documents with page citations. Same router as the evals (`telaah.router.run_routed`).

    .venv/Scripts/python app.py          # http://127.0.0.1:7860

LLM from env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL): Ollama locally, Gemini on a Space. Chart reading (vision)
is off unless TELAAH_DEMO_VISION=1, so the demo never spends the vision quota; ColPali is never loaded.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TELAAH_COLPALI_CACHE_ONLY", "1")  # never load ColQwen2 (4.4 GB) in the demo
sys.path.insert(0, str(Path(__file__).parent / "src"))

import gradio as gr  # noqa: E402
import openai  # noqa: E402

from telaah import demo, vision  # noqa: E402
from telaah.filters import doc_ids  # noqa: E402
from telaah.router import run_routed  # noqa: E402

VISION_ON = os.getenv("TELAAH_DEMO_VISION", "0") == "1"
if not VISION_ON:
    vision.enabled = lambda: False

EXAMPLES = [  # seed (dev) questions, one per route
    "Berapa total aset konsolidasian BRI per 31 Desember 2025 (dalam jutaan Rupiah)?",
    "Berapa rasio NPL gross BRI pada tahun 2025?",
    "Menurut POJK 17 Tahun 2023, berapa jumlah minimum anggota Dewan Komisaris bank umum?",
    "Menurut POJK 22 Tahun 2023, berapa lama batas waktu PUJK menyelesaikan pengaduan yang disampaikan secara lisan?",
    "Berapa selisih total aset BRI dan BCA per akhir 2025 (dalam miliar Rupiah), dan bank mana yang lebih besar?",
    "Bandingkan rasio NPL gross BRI dan BTN pada tahun 2025. Bank mana yang lebih tinggi?",
    "Apakah Rasio Intermediasi Makroprudensial (RIM) Bank Mandiri pada akhir 2025 berada dalam rentang Target RIM "
    "yang ditetapkan PADG 23 Tahun 2025?",
    "Berapa rasio NPL gross PT Bank Danamon Indonesia Tbk pada akhir 2025?",
]
ABOUT = """Telaah menjawab pertanyaan tentang laporan tahunan bank dan regulasi OJK/BI **hanya dari dokumen**, dengan
sitasi halaman, dan menolak bila jawabannya tidak ada. *Answers come only from the documents, with page citations;
it refuses when the answer is not there.*

- Pencarian: bge-m3 + BM25, tabel fakta dari laporan, agen perencana/verifikator untuk perbandingan dan hitungan.
- Model: `{model}`. Dikembangkan dan diuji pada set pertanyaan kecil; jawaban bisa salah, selalu cek halaman sumber.
  *Tuned on a small question set: answers can be wrong, check the source page.*
- Batas: 1 pertanyaan per {gap} detik dan {cap} per sesi; kuota harian LLM dipakai bersama semua pengunjung."""


def ask(question: str, times: list[float]):
    """Generator: a 'working' state first, then the answer, trust line, source pages and the how-panel."""
    question = (question or "").strip()
    empty = ("", "", gr.Radio(choices=[], value=None), "", "")
    if not question:
        yield ("Tulis pertanyaan dulu. *Type a question first.*", *empty[1:], times, "")
        return
    if msg := demo.check_limit(times):
        yield (msg, *empty[1:], times, "")
        return
    times = times + [time.time()]
    yield ("⏳ Mencari halaman dan menyusun jawaban… *Searching and answering…*", *empty[1:], times, "")
    t0 = time.time()
    try:
        r = run_routed(question)
    except openai.RateLimitError:
        yield ("Kuota harian model bahasa habis; coba lagi besok. *The daily LLM quota is used up.*", *empty[1:], times, "")
        return
    except openai.APIConnectionError:
        yield ("Model bahasa tidak bisa dihubungi. *The language model is unreachable.*", *empty[1:], times, "")
        return
    except Exception as e:  # noqa: BLE001 - show a message, keep the app alive
        print(f"[demo] error on {question!r}: {e!r}")
        yield (f"Terjadi kesalahan: `{type(e).__name__}`. *Something went wrong.*", *empty[1:], times, "")
        return
    choices = demo.source_choices(r)
    first = choices[0][1] if choices else None
    answer = r.get("answer", "")
    yield (
        demo.display_answer(r),
        demo.trust_line(r),
        gr.Radio(choices=choices, value=first, label="Halaman sumber / source pages"
                 if not demo.is_refusal(r) else "Halaman yang diperiksa / pages searched"),
        demo.page_view(first, answer),
        demo.how_md(r, time.time() - t0, chart_note=vision.wants_image(question) and not VISION_ON),
        times,
        answer,
    )


with gr.Blocks(title="Telaah · riset dokumen keuangan") as app:
    gr.Markdown("# Telaah\n### Asisten riset laporan keuangan bank & regulasi OJK/BI\n"
                "*Research assistant for Indonesian bank annual reports and OJK/BI regulations*")
    times, last_answer = gr.State([]), gr.State("")
    with gr.Row():
        question = gr.Textbox(label="Pertanyaan / question", placeholder="Contoh: Berapa rasio NPL gross BRI pada tahun 2025?",
                              scale=5, lines=2)
        go = gr.Button("Tanya / Ask", variant="primary", scale=1)
    gr.Examples(EXAMPLES, inputs=question, label="Contoh / examples")
    with gr.Row():
        with gr.Column(scale=1):
            answer_md = gr.Markdown(label="Jawaban")
            trust_md = gr.Markdown()
        with gr.Column(scale=1):
            sources = gr.Radio(choices=[], label="Halaman sumber / source pages")
            page_md = gr.Markdown(max_height=520)
    with gr.Accordion("Cara menjawab / how it answered", open=False):
        how = gr.Markdown()
    with gr.Accordion("Dokumen yang tersedia / documents", open=False):
        gr.Markdown(demo.corpus_md(list(doc_ids())))
    with gr.Accordion("Tentang demo ini / about", open=False):
        gr.Markdown(ABOUT.format(model=os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"), gap=demo.MIN_GAP_S, cap=demo.SESSION_MAX))

    outs = [answer_md, trust_md, sources, page_md, how, times, last_answer]
    go.click(ask, [question, times], outs, concurrency_limit=1)
    question.submit(ask, [question, times], outs, concurrency_limit=1)
    sources.change(demo.page_view, [sources, last_answer], page_md)


if __name__ == "__main__":
    from telaah.retrieve import retrieve

    t0 = time.time()
    print("[demo] memuat indeks / loading the index ...", flush=True)
    retrieve("total aset BRI 2025")  # loads bge-m3, BM25 and Qdrant before the first visitor
    print(f"[demo] ready in {time.time() - t0:.0f} s", flush=True)
    app.queue(default_concurrency_limit=1).launch(server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"))
