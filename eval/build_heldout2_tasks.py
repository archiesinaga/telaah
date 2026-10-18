"""Build eval/heldout2_tasks.jsonl: held-out set #2, 40 tasks, frozen before any system run (see HELDOUT.md).

New vs the dev tasks and held-out set #1: the 2024 reports as the source (they carry 2020 figures, which the 2025
reports do not have), restatement comparisons between the 2024 and 2025 reports (four real restatements: BRI total
assets 2023/2024, BRI NIM 2024, BTN KPMM 2023; two unchanged figures), a growth rate (CAGR), a
two-indicator ratio from one report. Gold: the dev builder's row parser on a hand-written page/row spec
(regex-checked); the facts table (src/telaah/facts.py) is not used. BCA 2024 is left out: its parsed file has no
summary tables.

    .venv/Scripts/python eval/build_heldout2_tasks.py
"""
import json
import re
from collections import Counter
from pathlib import Path

import build_agent_tasks as dev  # gold parser; rewrites agent_tasks.jsonl identically

HERE = Path(__file__).parent
OUT = HERE / "heldout2_tasks.jsonl"
NAME, DESC5, idnum = dev.NAME, dev.DESC5, dev.idnum
Y24 = [2024, 2023, 2022, 2021, 2020]  # columns of the 2024 reports
BNI24 = [2024, 2023, None, 2022, 2021, 2020]  # BNI 2024: a YoY column after 2023, Indonesian decimals

# (bank, metric@2024) -> rows of the 2024 reports
dev.S.update({
    ("bri", "aset@24"): ("bri_2024", 22, r"^TOTAL ASET$", Y24, "id", "jt"),
    ("bri", "laba@24"): ("bri_2024", 24, r"^LABA BERSIH$", Y24, "id", "jt"),
    ("bri", "ldr@24"): ("bri_2024", 27, r"^LDR$", Y24, "id", "pct"),
    ("bri", "npl@24"): ("bri_2024", 27, r"^NPL Gross$", Y24, "id", "pct"),
    ("bri", "nim@24"): ("bri_2024", 28, r"^NIM$", Y24, "id", "pct"),
    ("bri", "roa@24"): ("bri_2024", 28, r"^ROA$", Y24, "id", "pct"),
    ("bri", "car@24"): ("bri_2024", 28, r"^Rasio Kewajiban Penyediaan Modal Minimum", Y24, "id", "pct"),
    ("mandiri", "aset@24"): ("mandiri_2024", 30, r"^Jumlah Aset$", Y24, "id", "jt"),
    ("mandiri", "laba@24"): ("mandiri_2024", 33, r"^Laba Tahun Berjalan$", Y24, "id", "jt"),
    ("mandiri", "car@24"): ("mandiri_2024", 34, r"^Kewajiban Penyediaan Modal Minimum \(KPMM\)$", Y24, "id", "pct"),
    ("mandiri", "npl@24"): ("mandiri_2024", 34, r"^NPL Gross$", Y24, "id", "pct"),
    ("mandiri", "roa@24"): ("mandiri_2024", 35, r"^Imbal Hasil Aktiva \(ROA\)$", Y24, "id", "pct"),
    ("mandiri", "nim@24"): ("mandiri_2024", 35, r"^Marjin Bunga Bersih \(NIM\)$", Y24, "id", "pct"),
    ("mandiri", "ldr@24"): ("mandiri_2024", 35, r"^Loan to Deposit Ratio \(LDR\)$", Y24, "id", "pct"),
    ("btn", "aset@24"): ("btn_2024", 21, r"^TOTAL ASET$", Y24, "id", "jt"),
    ("btn", "laba@24"): ("btn_2024", 24, r"^LABA TAHUN BERJALAN$", Y24, "id", "jt"),
    ("btn", "ldr@24"): ("btn_2024", 27, r"^Loan to Deposit Ratio \(LDR\)$", Y24, "id", "pct"),
    ("btn", "roa@24"): ("btn_2024", 27, r"^Return On Asset \(ROA\)$", Y24, "id", "pct"),
    ("btn", "nim@24"): ("btn_2024", 27, r"^Net Interest Margin \(NIM\)$", Y24, "id", "pct"),
    ("btn", "npl@24"): ("btn_2024", 27, r"^Non Performing Loan \(NPL\) Gross$", Y24, "id", "pct"),
    ("btn", "car@24"): ("btn_2024", 27, r"^Rasio Kewajiban Penyediaan Modal Minimum", Y24, "id", "pct"),
    ("bni", "aset@24"): ("bni_2024", 24, r"^Jumlah Aset$", BNI24, "id", "mi"),
    ("bni", "laba@24"): ("bni_2024", 26, r"^Laba Tahun Berjalan$", BNI24, "id", "mi"),
    ("bni", "car@24"): ("bni_2024", 26, r"^Rasio Kewajiban Penyediaan Modal Minimum", BNI24, "id", "pct"),
    ("bni", "npl@24"): ("bni_2024", 26, r"^NPL Bruto$", BNI24, "id", "pct"),
    ("bni", "roa@24"): ("bni_2024", 27, r"^Return on Assets \(ROA\)$", BNI24, "id", "pct"),
    ("bni", "nim@24"): ("bni_2024", 27, r"^Net Interest Margin \(NIM\)$", BNI24, "id", "pct"),
})
dev._cache.clear()
v, shown, fact, names = dev.v, dev.shown, dev.fact, dev.names
LABEL = {"npl": "NPL gross", "ldr": "LDR", "nim": "NIM", "roa": "ROA", "car": "KPMM (CAR)", "aset": "total aset",
         "laba": "laba bersih (laba tahun berjalan)"}
SRC = ["Gunakan Laporan Tahunan 2024 masing-masing bank.", "Sumber: laporan tahunan 2024 tiap bank.",
       "Pakai angka dari Laporan Tahunan 2024."]
TASKS: list[dict] = []


def add(cat, q, a, numbers, facts_, steps, extra_pages=(), src=True):
    pages = []
    for f in facts_:
        if [f["doc"], f["page"]] not in pages:
            pages.append([f["doc"], f["page"]])
    pages += [list(p) for p in extra_pages if list(p) not in pages]
    if src:
        q = q + " " + SRC[len(TASKS) % len(SRC)]
    TASKS.append({"id": f"k{len(TASKS) + 1:03d}", "type": "agent_task", "category": cat, "question": q,
                  "gold_answer": a, "gold_numbers": numbers, "gold_facts": facts_, "gold_pages": pages,
                  "min_steps": steps, "answerable": True})


def m24(m):
    return m + "@24"


def pct(b, m, y):
    return shown(b, m, y).rstrip("%")


def trill(b, m, y):
    s = dev.series(b, m)
    return s["vals"][y][0] / (1e6 if s["unit"] == "jt" else 1e3)


# ---------------------------------------------------------------- restatement: 2024 vs 2025 report (6)
def restated(b, m25, m24_, y, q):
    """Both reports' figure for one year; gold numbers in Indonesian notation. A real restatement adds the
    difference; an unchanged figure has no "0" in its gold (a stray zero in the answer must not pass)."""
    s24, s25 = dev.series(b, m24_), dev.series(b, m25)
    a, z = s24["vals"][y][0], s25["vals"][y][0]
    pct_ = s24["unit"] == "pct"
    dec = 2 if pct_ else 0
    nums = [idnum(a, dec), idnum(z, dec)]
    d = round(z - a, 2)
    if d:
        nums.append(idnum(abs(d), dec))
    add("restatement", q, f"LT 2024: {idnum(a, dec)}; LT 2025: {idnum(z, dec)}; selisih {idnum(d, dec)}.",
        nums, [fact(b, m24_, y), fact(b, m25, y)], 2, src=False)


restated("bri", "aset", "aset@24", 2024,
         "Total aset BRI akhir 2024 tercatat berapa di Laporan Tahunan 2024, berapa setelah disajikan kembali di "
         "Laporan Tahunan 2025, dan berapa juta Rupiah selisihnya?")
restated("bri", "aset", "aset@24", 2023,
         "Bandingkan total aset BRI tahun 2023 menurut Laporan Tahunan 2024 dan menurut Laporan Tahunan 2025. "
         "Berapa selisihnya dalam juta Rupiah?")
restated("bri", "nim", "nim@24", 2024,
         "NIM BRI tahun 2024 dilaporkan berapa di Laporan Tahunan 2024 dan berapa di Laporan Tahunan 2025? Berapa "
         "poin persen perbedaannya?")
restated("btn", "car", "car@24", 2023,
         "Berapa KPMM BTN tahun 2023 menurut Laporan Tahunan 2024 dan menurut Laporan Tahunan 2025, dan berapa "
         "poin persen selisihnya?")
restated("mandiri", "laba", "laba@24", 2023,
         "Apakah laba tahun berjalan Bank Mandiri tahun 2023 di Laporan Tahunan 2024 sama dengan yang tercantum di "
         "Laporan Tahunan 2025? Sebutkan kedua angkanya.")
restated("btn", "laba", "laba@24", 2022,
         "Apakah laba tahun berjalan BTN tahun 2022 berubah antara Laporan Tahunan 2024 dan Laporan Tahunan 2025? "
         "Sebutkan angka di kedua laporan.")


# ---------------------------------------------------------------- trend 2020-2024 from the 2024 report (4)
def trend(b, m, q):
    s = dev.series(b, m24(m))
    ys = [2020, 2021, 2022, 2023, 2024]
    vals = {y: s["vals"][y][0] for y in ys}
    peak = max(ys, key=vals.get)
    assert list(vals.values()).count(vals[peak]) == 1, (b, m)
    nominal = s["unit"] != "pct"
    ch = round((vals[2024] / vals[2020] - 1) * 100, 2) if nominal else round(vals[2024] - vals[2020], 2)
    add("trend", q, ", ".join(f"{y}: {shown(b, m24(m), y)}" for y in ys) + f". Puncak {peak}. Perubahan {idnum(ch, 2)}.",
        [pct(b, m24(m), y) for y in ys] + [idnum(ch, 2)], [fact(b, m24(m), y) for y in ys], 1)


trend("mandiri", "npl", "Bagaimana NPL gross Bank Mandiri bergerak dari 2020 sampai 2024? Sebutkan tiap tahun, "
      "tahun tertinggi, dan perubahan 2020 ke 2024 dalam poin persen.")
trend("btn", "roa", "Sebutkan ROA BTN untuk 2020 hingga 2024, kapan ROA tertinggi, dan berapa poin persen "
      "perubahannya antara 2020 dan 2024.")
trend("bni", "nim", "NIM BNI tahun 2020-2024: berapa per tahun, tahun puncaknya, dan selisih 2024 terhadap 2020 "
      "(poin persen)?")
trend("bri", "aset", "Berapa total aset BRI tiap akhir tahun 2020 s.d. 2024, tahun tertinggi, dan pertumbuhan "
      "2020 ke 2024 dalam persen?")


# ---------------------------------------------------------------- multi-bank 2020 vs 2024 (4)
def multi(m, bs, q):
    nominal = dev.series(bs[0], m24(m))["unit"] != "pct"
    chg = {b: round((v(b, m24(m), 2024) / v(b, m24(m), 2020) - 1) * 100, 2) if nominal
           else round(v(b, m24(m), 2024) - v(b, m24(m), 2020), 2) for b in bs}
    s = sorted(map(abs, chg.values()))
    assert s[-1] != s[-2], (m, bs)
    nums = []
    for b in bs:
        nums += [pct(b, m24(m), 2020), pct(b, m24(m), 2024), idnum(chg[b], 2)]
    add("multi_trend", q, "; ".join(f"{NAME[b]} {idnum(chg[b], 2)}" for b in bs), nums,
        [fact(b, m24(m), y) for b in bs for y in (2020, 2024)], len(bs))


multi("car", ["bri", "mandiri", "btn"], "Bandingkan KPMM BRI, Bank Mandiri, dan BTN pada 2020 dan 2024: nilai "
      "kedua tahun, perubahan poin persen, dan bank yang berubah paling besar (absolut).")
multi("npl", ["bri", "btn", "bni"], "Berapa NPL gross BRI, BTN, dan BNI pada 2020 dan 2024, berapa perubahannya "
      "(poin persen), dan bank mana yang turun paling banyak?")
multi("roa", ["mandiri", "btn", "bni"], "Untuk Bank Mandiri, BTN, dan BNI, sebutkan ROA 2020 dan 2024, perubahannya "
      "dalam poin persen, dan bank dengan perubahan terbesar (absolut).")
multi("laba", ["bri", "mandiri", "btn"], "Berapa laba bersih BRI, Bank Mandiri, dan BTN tahun 2020 dan 2024, "
      "berapa persen pertumbuhannya, dan siapa yang tumbuh paling tinggi?")


# ---------------------------------------------------------------- ranking (4)
def rank(m, y, bs, q, desc=False, gap=True):
    vals = {b: v(b, m24(m), y) for b in bs}
    assert len(set(vals.values())) == len(bs), ("tie", m, y)
    order = sorted(bs, key=vals.get, reverse=desc)
    g = round(max(vals.values()) - min(vals.values()), 2)
    add("ranking", q, "; ".join(f"{NAME[b]} {shown(b, m24(m), y)}" for b in order),
        [pct(b, m24(m), y) for b in order] + ([idnum(g, 2)] if gap else []), [fact(b, m24(m), y) for b in bs], len(bs))


rank("roa", 2020, ["bri", "mandiri", "btn", "bni"], "Urutkan ROA tahun 2020 dari BRI, Bank Mandiri, BTN, dan BNI dari "
     "yang tertinggi, beserta angkanya, dan selisih ROA tertinggi dengan terendah.", desc=True)
rank("npl", 2020, ["bri", "mandiri", "btn", "bni"], "Pada 2020, bank mana yang NPL gross-nya paling tinggi di antara "
     "BRI, Bank Mandiri, BTN, dan BNI? Urutkan dari terendah dan hitung jaraknya.")
rank("nim", 2024, ["bri", "mandiri", "btn", "bni"], "Peringkatkan NIM 2024 BRI, Bank Mandiri, BTN, dan BNI dari "
     "terbesar ke terkecil dan sebutkan selisih NIM terbesar dan terkecil.", desc=True)
rank("ldr", 2022, ["bri", "mandiri", "btn"], "Susun LDR tahun 2022 untuk BRI, Bank Mandiri, dan BTN dari yang "
     "terendah, sebutkan nilainya, lalu hitung selisih tertinggi dan terendah.")

# ---------------------------------------------------------------- compute (10)
r = round(v("bri", "laba@24", 2020) / v("bri", "aset@24", 2020) * 100, 2)
add("compute", "Hitung laba bersih BRI tahun 2020 dibagi total aset akhir 2020 dalam persen (dua desimal).",
    f"{idnum(r, 2)}%.", [idnum(r, 2)], [fact("bri", "laba@24", 2020), fact("bri", "aset@24", 2020)], 2)
g = round((v("mandiri", "aset@24", 2024) / v("mandiri", "aset@24", 2020) - 1) * 100, 2)
add("compute", "Berapa persen pertumbuhan total aset Bank Mandiri dari akhir 2020 ke akhir 2024 (dua desimal)?",
    f"{idnum(g, 2)}%.", [idnum(g, 2)], [fact("mandiri", "aset@24", 2020), fact("mandiri", "aset@24", 2024)], 2)
t = round(trill("bri", "laba@24", 2020) + trill("mandiri", "laba@24", 2020), 2)
add("compute", "Berapa triliun Rupiah laba bersih BRI dan Bank Mandiri tahun 2020 bila dijumlahkan (dua desimal)?",
    f"Rp{idnum(t, 2)} triliun.", [idnum(t, 2)], [fact("bri", "laba@24", 2020), fact("mandiri", "laba@24", 2020)], 2)
bs = ["bri", "mandiri", "btn", "bni"]
avg = round(sum(v(b, "npl@24", 2020) for b in bs) / 4, 2)
add("compute", "Berapa rata-rata sederhana NPL gross 2020 dari BRI, Bank Mandiri, BTN, dan BNI (dua desimal)?",
    f"{idnum(avg, 2)}%.", [idnum(avg, 2)], [fact(b, "npl@24", 2020) for b in bs], 4)
k = round(v("bri", "laba@24", 2024) / v("bri", "laba@24", 2020), 2)
add("compute", "Laba bersih BRI tahun 2024 berapa kali lipat laba bersih tahun 2020 (dua desimal)?",
    f"{idnum(k, 2)} kali.", [idnum(k, 2)], [fact("bri", "laba@24", 2024), fact("bri", "laba@24", 2020)], 2)
d = round(v("bri", "roa@24", 2020) - v("mandiri", "roa@24", 2020), 2)
add("compute", "Pada 2020, berapa poin persen ROA BRI berbeda dari ROA Bank Mandiri?",
    f"{idnum(d, 2)} poin persen.", [idnum(abs(d), 2)], [fact("bri", "roa@24", 2020), fact("mandiri", "roa@24", 2020)], 2)
cagr = round(((v("bri", "aset@24", 2024) / v("bri", "aset@24", 2020)) ** (1 / 4) - 1) * 100, 2)
add("compute", "Berapa pertumbuhan tahunan majemuk (CAGR) total aset BRI dari 2020 ke 2024 dalam persen (dua desimal)?",
    f"{idnum(cagr, 2)}% per tahun.", [idnum(cagr, 2)], [fact("bri", "aset@24", 2020), fact("bri", "aset@24", 2024)], 2)
mn = round(sum(v("btn", "nim@24", y) for y in Y24) / 5, 2)
add("compute", "Berapa rata-rata NIM BTN selama 2020-2024 (dua desimal)?", f"{idnum(mn, 2)}%.", [idnum(mn, 2)],
    [fact("btn", "nim@24", y) for y in Y24], 1)
d = round(trill("mandiri", "aset@24", 2024) - trill("bri", "aset@24", 2024), 2)
add("compute", "Berapa selisih total aset Bank Mandiri dan BRI per akhir 2024 dalam triliun Rupiah (dua desimal)?",
    f"Rp{idnum(d, 2)} triliun.", [idnum(abs(d), 2)], [fact("mandiri", "aset@24", 2024), fact("bri", "aset@24", 2024)], 2)
g = round((v("bni", "laba@24", 2024) / v("bni", "laba@24", 2023) - 1) * 100, 2)
add("compute", "Berapa persen kenaikan laba tahun berjalan BNI dari 2023 ke 2024 (dua desimal)?", f"{idnum(g, 2)}%.",
    [idnum(g, 2)], [fact("bni", "laba@24", 2023), fact("bni", "laba@24", 2024)], 2)

# ---------------------------------------------------------------- regulation + 2024-report data (6)
REG = {
    "p1": ("ojk_pojk_11_2016", 7, r"8% \(delapan persen\) dari Aset Tertimbang Menurut Risiko \(ATMR\) bagi Bank dengan profil risiko Peringkat 1", 8),
    "p45": ("ojk_pojk_11_2016", 7, r"11% \(sebelas persen\) sampai dengan 14% \(empat belas persen\)", 14),
    "padg_npl": ("bi_padg_23_2025", 8, r"rasio kredit bermasalah secara bruto lebih kecil dari 5%", 5),
    "padg_kpmm": ("bi_padg_23_2025", 7, r"KPMM Insentif sebesar 14%", 14),
}
for key, (doc, page, rx, _) in REG.items():
    assert re.search(rx, dev.page_text(doc, page), re.I), key


def reg(key, b, m, y, q):
    doc, page, _, thr = REG[key]
    d = round(v(b, m24(m), y) - thr, 2)
    add("regulation", q, f"batas {thr}%; {NAME[b]} {shown(b, m24(m), y)}; selisih {idnum(abs(d), 2)}.",
        [idnum(thr, 0), pct(b, m24(m), y), idnum(abs(d), 2)], [fact(b, m24(m), y)], 2, extra_pages=[(doc, page)])


reg("p1", "bni", "car", 2020, "Berapa KPMM minimum untuk bank berprofil risiko Peringkat 1 menurut POJK "
    "11/POJK.03/2016, dan berapa poin persen KPMM BNI 2020 di atasnya?")
reg("p45", "bri", "car", 2020, "Dengan batas atas KPMM minimum POJK 11/POJK.03/2016 sebagai acuan, berapa selisih "
    "KPMM BRI tahun 2020 terhadap acuan itu?")
reg("padg_npl", "btn", "npl", 2020, "Jika ambang rasio kredit bermasalah bruto dalam PADG 23 Tahun 2025 diterapkan "
    "pada NPL gross BTN tahun 2020, berapa ambangnya dan berapa jarak NPL BTN 2020 ke ambang itu?")
reg("padg_npl", "bni", "npl", 2020, "Berapa ambang NPL bruto pada parameter insentif PADG 23 Tahun 2025, dan berapa "
    "poin persen NPL gross BNI 2020 di bawahnya?")
reg("padg_kpmm", "mandiri", "car", 2022, "Berapa KPMM Insentif dalam PADG 23 Tahun 2025, dan berapa kelebihan KPMM "
    "Bank Mandiri 2022 dibandingkan angka itu?")
reg("p1", "btn", "car", 2020, "POJK 11/POJK.03/2016 menetapkan KPMM minimum bagi bank dengan profil risiko Peringkat "
    "1. Berapa angkanya dan berapa selisih KPMM BTN tahun 2020 terhadapnya?")

# ---------------------------------------------------------------- unanswerable (6)
UNANS = [
    ("Berapa NPL gross Bank Neo Commerce tahun 2024 dan bandingkan dengan BRI.", ["bank neo commerce"]),  # Bank Raya (BRI subsidiary) is in the corpus
    ("Berapa realisasi laba bersih BTN tahun 2027 dan pertumbuhannya dari 2024?", ["laba bersih btn tahun 2027", "laba btn 2027"]),
    ("Berapa jumlah agen BRILink di Kabupaten Teluk Bintuni pada akhir 2024?", ["teluk bintuni"]),
    ("Berapa rasio NPL kredit untuk startup fintech di BNI pada 2024, dan berapa selisihnya dengan NPL gross BNI?", ["npl kredit startup", "npl startup fintech"]),
    ("Berapa gaji bulanan Komisaris Utama Bank Mandiri pada 2024 dalam Rupiah?", ["gaji bulanan komisaris utama"]),
    ("Berapa ROA BRI tahun 2015 menurut laporan tahunan, dan berapa perubahannya hingga 2024?", ["roa bri tahun 2015", "tahun 2015 sebesar", "roa 2015"]),
]
corpus = "".join(p.read_text(encoding="utf-8").lower() for p in dev.PROC.glob("*.jsonl"))
for q, absent in UNANS:
    for term in absent:
        assert term not in corpus, f"{term!r} occurs in the corpus"
    TASKS.append({"id": f"k{len(TASKS) + 1:03d}", "type": "agent_task", "category": "unanswerable", "question": q,
                  "gold_answer": "TIDAK DITEMUKAN", "gold_numbers": [], "gold_facts": [], "gold_pages": [],
                  "min_steps": 1, "answerable": False})

assert len(TASKS) == 40, len(TASKS)
OUT.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in TASKS) + "\n", encoding="utf-8")
print(Counter(t["category"] for t in TASKS), "->", OUT)
