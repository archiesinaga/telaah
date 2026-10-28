"""Draft SFT question-answer pairs from sft/pages.jsonl with Gemini -> sft/drafts.jsonl (sft/DESIGN.md, step 2).

Gemini sees each page as an image plus its parsed text and returns up to 3 questions, each with an answer written
the way the pipeline must answer (house style, `[doc_id p.N]` citation), the exact value and a verbatim quote.
Every draft gets automatic checks; the problems are kept on the row (filtering happens in step 4).
Uses its own key and quota memory, so drafting never spends the eval key. Resumable.

    .venv/Scripts/python sft/draft_sft.py --pilot        # 2 pages per kind (10 requests)
    .venv/Scripts/python sft/draft_sft.py                # everything left (stops on the daily quota)

Env: SFT_GEMINI_API_KEY, DRAFT_MODEL (default gemini-3.5-flash-lite), DRAFT_MIN_INTERVAL (default 4.5 s).
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "eval" / "bench"))
from common import append_jsonl, norm, pages, read_jsonl  # noqa: E402
from draft import BASE_URL, INTERVAL, MODEL, next_reset, ref, render_page  # noqa: E402
from openai import OpenAI  # noqa: E402
from telaah.metrics import numeric_match  # noqa: E402

PAGES = HERE / "pages.jsonl"
OUT = HERE / "drafts.jsonl"
DONE = HERE / "drafted.jsonl"
QUOTA_FILE = HERE / ".quota_hit"
TRANSCRIPTS = HERE.parent / "data" / "page_transcripts"

COMMON = """Kamu menyusun data latih untuk asisten tanya-jawab dokumen keuangan dan regulasi Indonesia.
Asisten itu mencari di SELURUH korpus (laporan tahunan BRI, Bank Mandiri, BNI, BTN, BCA 2024 dan 2025, serta
peraturan OJK dan BI), jadi setiap soal harus berdiri sendiri: sebut nama bank atau nomor peraturan, dan tahun
laporan atau periode datanya. Satu soal = satu jawaban yang jelas dan tunggal. Jangan membuat soal yang ambigu,
bergantung pada tata letak ("tabel di atas"), menyebut nomor halaman, sepele (judul bab), atau meminta daftar panjang.
Variasikan gaya soal: soal 1 formal dan lengkap, soal 2 singkat seperti diketik pengguna ("NPL gross BRI 2025?"),
soal 3 dengan kata yang berbeda dari teks halaman (sinonim atau singkatan, misalnya DPK, kredit bermasalah, CAR).
Tahun di soal harus tahun data/peristiwa yang ditanyakan (bukan sekadar tahun terbit laporan), dan soal singkat tetap
menyebut bank atau nomor peraturan.

Untuk tiap soal tulis:
- "answer": jawaban 1-2 kalimat dalam Bahasa Indonesia, angka seperti tercetak beserta satuannya, dan sitasi
  {cite} di akhir kalimat yang memuat angka atau fakta itu. Tanpa basa-basi, tanpa informasi di luar halaman.
- "value": angka atau frasa jawaban persis seperti tercetak di halaman (tanpa sitasi).
- "evidence": kutipan PERSIS dari teks halaman (salin apa adanya, maks 200 karakter) yang memuat jawabannya.
Jika halaman tidak cocok, kembalikan {{"questions": []}}. Balas HANYA JSON: {{"questions": [{{{fields}}}]}}."""

TASK = {
    "text_fact": "Buat sampai 3 soal FAKTA dari paragraf naratif halaman {ref} (bukan tabel): nama, tanggal, jumlah, kebijakan, alasan, peristiwa.",
    "table_lookup": """Buat sampai 3 soal PEMBACAAN TABEL dari halaman {ref}: tiap soal satu angka di satu sel; sebut baris, periode, dan satuan bila tercetak.
Tambahkan "column": judul kolom/periode sel itu PERSIS seperti tercetak di halaman (misalnya "31 Desember 2024" atau "TW IV"). Pastikan angka
itu memang di kolom tersebut (lihat GAMBAR halaman), bukan kolom di sebelahnya.""",
    # reading steps only: arithmetic stays in code (DESIGN.md); the skill is picking the right year column
    "calculation": """Halaman {ref} memuat tabel dengan beberapa tahun. Buat sampai 3 soal PEMBACAAN satu sel (BUKAN perhitungan).
Minimal 2 soal menanyakan tahun yang BUKAN kolom terbaru, dan sebut tahunnya dengan jelas: asisten harus memilih kolom tahun yang benar.
Tambahkan "column": judul kolom tahun/periode sel itu PERSIS seperti tercetak di halaman (misalnya "2024" atau "31 Desember 2024").
Pastikan angka itu memang di kolom tersebut (lihat GAMBAR halaman), bukan kolom di sebelahnya.""",
    "chart": """Halaman {ref}. Lihat GAMBAR halaman. Jika ada grafik/diagram dengan label data angka, buat sampai 3 soal yang jawabannya
dibaca dari grafik itu (sebut judul grafik dan periodenya); "evidence" = judul grafik dan label data, apa adanya.
Jika tidak ada grafik berlabel angka, kembalikan daftar kosong.""",
    "regulation": """Buat sampai 3 soal tentang isi PERATURAN di halaman {ref}: batas/ambang/persentase, kewajiban, jangka waktu,
sanksi, definisi, atau tanggal berlaku. Sebut nomor dan tahun peraturannya di soal.""",
}
FIELDS = {"table_lookup": ', "column"', "calculation": ', "column"'}
STOP = {"sebagaimana", "dimaksud", "dalam", "pasal", "ayat", "huruf", "yang", "dengan", "dari", "untuk", "pada", "atau", "dan"}
NAMES = ["bri", "mandiri", "bni", "btn", "bca", "pojk", "seojk", "pbi", "padg", "ojk", "bank indonesia",
         "central asia", "rakyat indonesia", "negara indonesia", "tabungan negara", "pedoman"]


def page_text(doc: str, page: int) -> str:
    """Parsed text plus the index-time chart transcription, if the page has one (what the pipeline can read)."""
    tx = TRANSCRIPTS / f"{doc}_p{page}.txt"
    return pages(doc)[page] + ("\n" + tx.read_text(encoding="utf-8") if tx.exists() else "")


def prompt(row: dict) -> str:
    doc, page = row["pages"][0]
    fields = '"question", "answer", "value", "evidence"' + FIELDS.get(row["kind"], "")
    common = COMMON.format(cite=f"[{doc} p.{page}]", fields=fields)
    return f"{common}\n\n{TASK[row['kind']].format(ref=ref(doc, page))}\n\n--- TEKS {ref(doc, page)} ---\n{pages(doc)[page][:12000]}"


def call(client: OpenAI, row: dict) -> list[dict]:
    doc, page = row["pages"][0]
    b64 = base64.b64encode(render_page(doc, page, dpi=110)).decode()
    content = [{"type": "text", "text": prompt(row)}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": content}],
                                       response_format={"type": "json_object"}, temperature=0.4)
    text = re.sub(r"^```(?:json)?|```$", "", (r.choices[0].message.content or "{}").strip()).strip()
    return json.loads(text).get("questions", [])


def alnum(s: str) -> str:
    """Text reduced to letters and digits: ignores layout, list markers ("- a.") and punctuation."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def covered(part: str, whole: str) -> float:
    w = words(part)
    return len(w & words(whole)) / len(w) if w else 1.0


def check(row: dict, q: dict) -> list[str]:
    """Problems that step 4 filters on; an empty list means the draft is usable as is."""
    doc, page = row["pages"][0]
    if not q.get("question") or not q.get("answer") or not q.get("value"):
        return ["missing field"]
    problems = []
    kind = row["kind"]
    cite = f"[{doc} p.{page}]"
    if cite not in q["answer"]:
        problems.append("citation missing")
    if re.findall(r"\[[^\]]+ p\.\d+\]", q["answer"].replace(cite, "")):
        problems.append("other citation")
    text, value, answer = page_text(doc, page), str(q["value"]), q["answer"].replace(cite, "")
    long = len(value.split()) > 6  # a clause or list (regulation), not a figure
    numeric = bool(re.search(r"\d", value)) and not long
    on_page = covered(value, text) >= 0.9 if long else numeric_match(text, value) if numeric else norm(value) in norm(text)
    if not on_page:
        problems.append("value not on page")
    if (numeric and not numeric_match(answer, value)) or (long and covered(value, answer) < 0.5):
        problems.append("value not in answer")
    column = str(q.get("column") or "")
    if kind in ("table_lookup", "calculation") and not (column and alnum(column) in alnum(text)):
        problems.append("column not on page")
    if kind == "calculation":
        # the asked year must be the column the value was read from (look-alike year columns)
        years = re.findall(r"20\d\d", column)
        if not years or not all(y in q["question"] for y in years):
            problems.append("column year not in question")
    if kind != "chart":
        ev = alnum(str(q.get("evidence", "")))[:70]
        if not ev or ev not in alnum(text):
            problems.append("evidence not verbatim")
        elif numeric and not numeric_match(str(q["evidence"]), value):
            problems.append("value not in evidence")
    if not any(n in q["question"].lower() for n in NAMES) or not re.search(r"20\d\d", q["question"]):
        problems.append("not self-contained")
    return problems


def blocked_until() -> datetime | None:
    if not QUOTA_FILE.exists():
        return None
    reset = next_reset(datetime.fromisoformat(QUOTA_FILE.read_text().strip()))
    return reset if reset > datetime.now().astimezone() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="only the first 2 pages of each kind")
    ap.add_argument("--limit", type=int, default=0, help="draft at most this many pages")
    ap.add_argument("--force", action="store_true", help="try although the last refusal says the quota has not reset")
    args = ap.parse_args()
    if (until := blocked_until()) and not args.force:
        sys.exit(f"daily quota refused earlier; expected reset {until:%Y-%m-%d %H:%M} local. --force to try anyway")
    key = os.getenv("SFT_GEMINI_API_KEY")
    if not key:
        sys.exit("SFT_GEMINI_API_KEY missing in .env (a separate key from GEMINI_API_KEY)")
    client = OpenAI(api_key=key, base_url=BASE_URL, max_retries=3)
    done = {r["id"] for r in read_jsonl(DONE)}
    todo = [r for r in read_jsonl(PAGES) if r["id"] not in done]
    if args.pilot:
        seen: Counter = Counter()
        todo = [r for r in todo if (seen.update([r["kind"]]) or seen[r["kind"]] <= 2)]
    if args.limit:
        todo = todo[: args.limit]
    stats: Counter = Counter()
    for n, row in enumerate(todo, 1):
        t0 = time.time()
        qs = None
        for _ in range(4):
            try:
                qs = call(client, row)
                break
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "PerDay" in msg:
                    now = datetime.now().astimezone()
                    QUOTA_FILE.write_text(now.isoformat())
                    print(f"daily quota reached after {n - 1} pages; expected reset {next_reset(now):%Y-%m-%d %H:%M} local")
                    print(dict(stats))
                    return
                if "429" in msg or "503" in msg:
                    m = re.search(r"retry in ([\d.]+)s", msg)
                    time.sleep(float(m.group(1)) + 2 if m else 30)
                    continue
                print(f"[{n}/{len(todo)}] {row['id']} error: {msg[:160]}")
                break
        if qs is None:
            stats["errors"] += 1
            continue
        for i, q in enumerate(qs[:3], 1):
            problems = check(row, q)
            append_jsonl(OUT, {"cid": f"{row['id']}-{i}", "page_id": row["id"], "kind": row["kind"],
                               "pages": row["pages"], "draft": q, "problems": problems, "model": MODEL})
            stats[("ok" if not problems else "flagged", row["kind"])] += 1
        append_jsonl(DONE, {"id": row["id"], "n": len(qs[:3]), "model": MODEL, "at": time.strftime("%Y-%m-%d %H:%M")})
        print(f"[{n}/{len(todo)}] {row['id']} {row['kind']}: {len(qs[:3])} drafts", flush=True)
        time.sleep(max(0.0, INTERVAL - (time.time() - t0)))
    print(dict(stats))


if __name__ == "__main__":
    main()
