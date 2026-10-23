"""Read a retrieved page IMAGE with a vision model (Gemini through its OpenAI-compatible API).

Used for chart questions: chart values exist only in the picture, so text retrieval cannot answer
them. The vision model only TRANSCRIBES what is printed on the page; the normal LLM then answers
from that text, so the answer format, citations and refusal rule stay the same.

Results are cached on disk (data/vision_cache) so re-running an eval does not spend API quota.
The page image is sent to the provider. Note: Google states that free-tier content may be used to
improve its products; the reports used here are public documents.
"""
import base64
import hashlib
import re
import time
from pathlib import Path

from openai import OpenAI

from telaah.config import (
    RAW_DIR,
    ROOT,
    VISION_API_KEY,
    VISION_BASE_URL,
    VISION_DPI,
    VISION_MODEL,
)

CACHE_DIR = ROOT / "data" / "vision_cache"
CHART_RE = re.compile(r"grafik|chart|diagram|bagan|infografik|gambar|ilustrasi", re.I)

PROMPT = """Ini adalah gambar satu halaman laporan keuangan/regulasi Indonesia.
Pertanyaan pengguna: {question}

Tugasmu HANYA mentranskripsi, bukan menjawab. Tulis sebagai teks:
1. Judul grafik/tabel yang relevan dengan pertanyaan.
2. Semua label sumbu, legenda, satuan, dan periode.
3. Semua angka yang tertera pada grafik atau tabel itu (label data), apa adanya, dipasangkan dengan
   label/periodenya, misalnya "Des 2025: 85,35%".
Aturan: jangan menghitung, jangan menebak, jangan menambahkan angka yang tidak tercetak.
Jika sebuah angka tidak terbaca jelas, tulis "tidak terbaca".
Jika halaman ini tidak memuat grafik atau tabel yang berkaitan dengan pertanyaan, jawab hanya: {irrelevant}"""
IRRELEVANT = "TIDAK RELEVAN"


def enabled() -> bool:
    return bool(VISION_API_KEY)


def wants_image(question: str) -> bool:
    return bool(CHART_RE.search(question))


def has_pdf(doc_id: str) -> bool:
    return (RAW_DIR / f"{doc_id}.pdf").exists()


def render_page(doc_id: str, page: int, dpi: int = VISION_DPI) -> bytes:
    """PNG bytes of one PDF page (1-based, same numbering as the text index)."""
    import pymupdf

    with pymupdf.open(RAW_DIR / f"{doc_id}.pdf") as doc:
        pix = doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        return pix.tobytes("png")


def _cache_path(doc_id: str, page: int, question: str) -> Path:
    key = hashlib.sha1(f"{VISION_MODEL}|{PROMPT}|{doc_id}|{page}|{question}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{doc_id}_p{page}_{key}.txt"


class DailyQuota(RuntimeError):
    """The provider refused for the day (free tier); retrying before the reset only wastes time."""


def _call(prompt: str, doc_id: str, page: int) -> str:
    png = base64.b64encode(render_page(doc_id, page)).decode()
    client = OpenAI(base_url=VISION_BASE_URL, api_key=VISION_API_KEY)
    last = None
    for attempt in range(4):  # free tiers rate-limit: back off and retry
        try:
            resp = client.chat.completions.create(
                model=VISION_MODEL,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}},
                        ],
                    }
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001 - any API error: wait and retry, then give up
            if "PerDay" in str(e):
                raise DailyQuota(str(e)) from e
            last = e
            time.sleep(5 * 2**attempt)
    raise RuntimeError(f"vision read failed for {doc_id} p.{page}: {last}")


def read_page(question: str, doc_id: str, page: int) -> str:
    cache = _cache_path(doc_id, page, question)
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    text = _call(PROMPT.format(question=question, irrelevant=IRRELEVANT), doc_id, page)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


TRANSCRIPT_DIR = ROOT / "data" / "page_transcripts"  # delete it after changing TRANSCRIBE_PROMPT or the model
NO_CHART = "TIDAK ADA GRAFIK"
TRANSCRIBE_PROMPT = """Ini adalah gambar satu halaman laporan tahunan bank di Indonesia.

Tugasmu HANYA mentranskripsi, bukan menjawab. Tulis sebagai teks biasa, untuk SETIAP grafik, diagram,
infografik, atau angka yang tercetak di dalam gambar:
1. Judul atau keterangannya.
2. Label sumbu, legenda, satuan, dan periode.
3. Semua angka yang tertera, apa adanya, dipasangkan dengan label/periodenya, misalnya "Des 2025: 85,35%".
Aturan: jangan menghitung, jangan menebak, jangan menambahkan angka yang tidak tercetak. Abaikan paragraf
teks biasa (sudah terbaca dari PDF). Jika sebuah angka tidak terbaca jelas, tulis "tidak terbaca".
Jika halaman ini tidak memuat grafik, diagram, infografik, atau angka di dalam gambar, jawab hanya: {no_chart}"""


def transcribe_page(doc_id: str, page: int) -> str:
    """Question-independent transcription of the charts on one page, cached; NO_CHART when there are none."""
    cache = TRANSCRIPT_DIR / f"{doc_id}_p{page}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    text = _call(TRANSCRIBE_PROMPT.format(no_chart=NO_CHART), doc_id, page)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text
