"""Draft candidate questions from the sampled pages with Gemini -> candidates_{dev,test}.jsonl.

The drafter sees each page as an image plus its parsed text and returns JSON. Calculation golds are NOT taken
from the drafter: build.py computes them from the figures the user checked. Resumable (pages already drafted
are skipped), throttled for the free tier. Prints counts only (the test split is not shown, BENCHMARK.md rule 2).

    .venv/Scripts/python eval/bench/draft.py --limit 20          # first pages, to check quality on dev
    .venv/Scripts/python eval/bench/draft.py                     # everything left (stops on the daily quota)

Env: GEMINI_API_KEY, DRAFT_MODEL (default gemini-3.5-flash; never the model under test or VISION_MODEL),
DRAFT_MIN_INTERVAL (seconds between requests, default 4.5).
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from collections import Counter

from dotenv import load_dotenv
from openai import OpenAI

from common import BANK, HERE, ROOT, append_jsonl, norm, pages, read_jsonl

sys.path.insert(0, str(ROOT / "src"))
from telaah.vision import render_page  # noqa: E402

load_dotenv(ROOT / ".env")
MODEL = os.getenv("DRAFT_MODEL", "gemini-3.5-flash")
INTERVAL = float(os.getenv("DRAFT_MIN_INTERVAL", "4.5"))
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PAGES = HERE / "pages.jsonl"
OUT = {s: HERE / f"candidates_{s}.jsonl" for s in ("dev", "test")}
DONE = HERE / "drafted_pages.jsonl"  # page ids drafted (also those with zero questions), split-free log
OPS = ["growth_pct", "difference", "sum", "ratio_pct", "ratio", "mean"]

COMMON = """Kamu menyusun soal benchmark untuk menguji sistem tanya-jawab dokumen keuangan dan regulasi Indonesia.
Sistem itu mencari di SELURUH korpus (laporan tahunan BRI, Bank Mandiri, BNI, BTN, BCA 2024 dan 2025, serta
peraturan OJK dan BI), jadi setiap soal harus berdiri sendiri: sebut nama bank atau nomor peraturan, dan tahun
laporan atau periode datanya. Soal dalam Bahasa Indonesia baku, satu jawaban yang jelas dan tunggal.
Jangan membuat soal yang jawabannya ambigu, bergantung pada tata letak ("tabel di atas"), atau sepele (judul bab).
Jawaban harus tertulis di halaman ini. "evidence" = kutipan PERSIS dari teks halaman (salin apa adanya, maks 200
karakter) yang memuat jawabannya. Angka ditulis seperti tercetak di halaman, beserta satuannya.
Jika halaman tidak cocok untuk soal jenis ini, kembalikan {"questions": []}.
Balas HANYA JSON: {"questions": [...]}."""

TASK = {
    "text_fact": """Buat sampai 2 soal FAKTA TEKS dari paragraf naratif halaman {ref} (bukan dari tabel): nama, tanggal,
jumlah, kebijakan, alasan, atau peristiwa. Objek: {{"question", "answer", "evidence", "numeric": bool}}""",
    "table_lookup": """Buat sampai 2 soal PEMBACAAN TABEL dari halaman {ref}: satu angka di satu sel (sebut baris, kolom/tahun,
dan satuan bila tercetak). Objek: {{"question", "answer", "evidence", "numeric": true}}""",
    "chart": """Halaman {ref}. Lihat GAMBAR halaman. Jika ada grafik/diagram dengan label data angka, buat sampai 2 soal yang
jawabannya hanya bisa dibaca dari grafik itu (sebut judul grafik dan periodenya). Jika tidak ada grafik berlabel
angka, kembalikan daftar kosong. "evidence" = judul grafik dan label data yang dibaca, apa adanya.
Objek: {{"question", "answer", "evidence", "numeric": true}}""",
    "calculation": """Buat sampai 2 soal PERHITUNGAN dari tabel halaman {ref}: pertumbuhan antartahun, selisih, jumlah,
rasio, atau rata-rata dari 2-5 angka di halaman ini. Jangan menulis hasil akhirnya sendiri; tulis angka-angkanya.
Objek: {{"question", "figures": [{{"label", "value" (seperti tercetak), "value_float" (angka desimal biasa,
tanpa pemisah ribuan), "unit"}}], "op": salah satu {ops} ("growth_pct" dan "difference": figures = [lama, baru];
"ratio"/"ratio_pct": [pembilang, penyebut]), "evidence"}}""",
    "regulation": """Buat sampai 2 soal tentang isi PERATURAN di halaman {ref}: batas/ambang/persentase, kewajiban,
jangka waktu, sanksi, definisi, atau tanggal berlaku. Sebut nomor dan tahun peraturannya di soal.
Objek: {{"question", "answer", "evidence", "numeric": bool}}""",
    "cross_doc": """Ada DUA halaman: A = {ref_a} dan B = {ref_b}, dari dua bank berbeda. Jika keduanya memuat angka yang
sebanding untuk "{term}" (atau indikator lain yang sama di kedua halaman, periode sama), buat 1 soal yang
membandingkan kedua bank (mana lebih tinggi dan selisihnya, atau keduanya). Jika tidak sebanding, kembalikan
daftar kosong. Objek: {{"question", "figures": [{{"bank", "label", "value", "value_float", "unit", "page": "A"|"B"}}],
"op": "difference", "answer" (kalimat jawaban), "evidence": [kutipan A, kutipan B]}}""",
}


def ref(doc: str, page: int) -> str:
    bank = BANK.get(doc.split("_")[0])
    name = f"Laporan Tahunan {doc[-4:]} {bank}" if bank and doc[-4:].isdigit() else doc
    return f"{name} (dokumen {doc}, halaman {page})"


def prompt(row: dict) -> str:
    (doc, page), *rest = row["pages"]
    if row["kind"] == "cross_doc":
        task = TASK["cross_doc"].format(ref_a=ref(doc, page), ref_b=ref(*rest[0]), term=row["term"])
    else:
        task = TASK[row["kind"]].format(ref=ref(doc, page), ops=OPS)
    texts = "\n\n".join(f"--- TEKS {ref(d, p)} ---\n{pages(d)[p][:12000]}" for d, p in row["pages"])
    return f"{COMMON}\n\n{task}\n\n{texts}"


def call(client: OpenAI, row: dict) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": prompt(row)}]
    for d, p in row["pages"]:
        b64 = base64.b64encode(render_page(d, p, dpi=110)).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": content}],
                                       response_format={"type": "json_object"}, temperature=0.4)
    text = r.choices[0].message.content or "{}"
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    return json.loads(text).get("questions", [])


def check(row: dict, q: dict) -> list[str]:
    """Automatic filter; problems are kept on the candidate so the reviewer sees them."""
    problems = []
    if not q.get("question"):
        return ["no question"]
    if row["kind"] in ("calculation", "cross_doc"):
        figs = q.get("figures") or []
        if len(figs) < 2 or any(not isinstance(f.get("value_float"), (int, float)) for f in figs):
            problems.append("figures missing or not numeric")
        if q.get("op") not in OPS:
            problems.append(f"unknown op {q.get('op')}")
    elif not q.get("answer"):
        problems.append("no answer")
    if row["kind"] != "chart":  # chart evidence is read from the image, not the parsed text
        ev = q.get("evidence") or []
        if not ev:
            problems.append("no evidence")
        text = norm(" ".join(pages(d)[p] for d, p in row["pages"]).replace("|", " "))
        if any(norm(e.replace("|", " "))[:80] not in text for e in (ev if isinstance(ev, list) else [ev])):
            problems.append("evidence not found verbatim")
    names = ["bri", "mandiri", "bni", "btn", "bca", "pojk", "seojk", "pbi", "padg", "ojk", "bank indonesia"]
    if not any(n in q["question"].lower() for n in names) or not re.search(r"20\d\d", q["question"]):
        problems.append("not self-contained (bank/regulation or year missing)")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="draft at most this many pages")
    ap.add_argument("--kinds", nargs="*", help="only these kinds")
    args = ap.parse_args()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY missing in .env")
    client = OpenAI(api_key=key, base_url=BASE_URL, max_retries=3)
    done = {r["id"] for r in read_jsonl(DONE)}
    todo = [r for r in read_jsonl(PAGES) if r["id"] not in done and (not args.kinds or r["kind"] in args.kinds)]
    if args.limit:
        todo = todo[: args.limit]
    stats = Counter()
    for n, row in enumerate(todo, 1):
        t0 = time.time()
        try:
            qs = call(client, row)
        except Exception as e:  # quota or a bad reply: stop on quota, skip a bad reply
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                print(f"quota reached after {n - 1} pages: {msg[:200]}")
                break
            print(f"[{n}/{len(todo)}] {row['id']} error: {msg[:160]}")
            stats["errors"] += 1
            continue
        for i, q in enumerate(qs[:2], 1):
            cand = {"cid": f"{row['id']}-{i}", "page_id": row["id"], "type": row["kind"], "split": row["split"],
                    "pages": row["pages"], "draft": q, "problems": check(row, q), "model": MODEL}
            append_jsonl(OUT[row["split"]], cand)
            stats[("ok" if not cand["problems"] else "flagged", row["kind"])] += 1
        append_jsonl(DONE, {"id": row["id"], "n": len(qs[:2]), "model": MODEL, "at": time.strftime("%Y-%m-%d %H:%M")})
        print(f"[{n}/{len(todo)}] {row['id']} {row['kind']}: {len(qs[:2])} drafts", flush=True)
        time.sleep(max(0.0, INTERVAL - (time.time() - t0)))
    print(dict(stats))


if __name__ == "__main__":
    main()
