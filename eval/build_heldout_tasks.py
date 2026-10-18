"""Build eval/heldout_tasks.jsonl: 40 held-out multi-step tasks, frozen before any system run (see HELDOUT.md).

Same gold method as build_agent_tasks.py (every figure parsed from the cited page row, derived numbers computed
here), but new wordings, indicators (ROA, ROE, NPL net, equity), year pairs and regulation thresholds. The facts
table (src/telaah/facts.py) is NOT used: the page/row spec below is written by hand and checked by regex.

    .venv/Scripts/python eval/build_heldout_tasks.py
"""
import json
import re
from collections import Counter
from pathlib import Path

import build_agent_tasks as dev  # gold parser (row_cells, num, idnum); rewrites agent_tasks.jsonl identically

HERE = Path(__file__).parent
OUT = HERE / "heldout_tasks.jsonl"
NAME, DESC5, ASC5, BNI6 = dev.NAME, dev.DESC5, dev.ASC5, dev.BNI6
idnum = dev.idnum

# extra rows for indicators the dev tasks never ask about; BNI ROE (two ROE rows) and BNI equity (a 2025 table
# with two 2024 columns but six cells per row) are left out as ambiguous
dev.S.update({
    ("bri", "roa"): ("bri_2025", 31, r"^ROA$", DESC5, "id", "pct"),
    ("mandiri", "roa"): ("mandiri_2025", 40, r"^Imbal Hasil Aktiva \(ROA\)$", ASC5, "id", "pct"),
    ("btn", "roa"): ("btn_2025", 28, r"^Return On Asset \(ROA\)$", DESC5, "id", "pct"),
    ("bca", "roa"): ("bca_2025", 16, r"Return on Asset - ROA", DESC5, "id", "pct"),
    ("bni", "roa"): ("bni_2025", 29, r"^Return on Assets \(ROA\)$", BNI6, "en", "pct"),
    ("bri", "roe"): ("bri_2025", 31, r"^ROE B/S$", DESC5, "id", "pct"),
    ("mandiri", "roe"): ("mandiri_2025", 40, r"^Imbal Hasil Ekuitas \(ROE\)$", ASC5, "id", "pct"),
    ("btn", "roe"): ("btn_2025", 28, r"^Return On Equity \(ROE\)$", DESC5, "id", "pct"),
    ("bca", "roe"): ("bca_2025", 16, r"Return on Equity - ROE", DESC5, "id", "pct"),
    ("bri", "nplnet"): ("bri_2025", 31, r"^NPL Nett$", DESC5, "id", "pct"),
    ("mandiri", "nplnet"): ("mandiri_2025", 39, r"^NPL Neto$", ASC5, "id", "pct"),
    ("bca", "nplnet"): ("bca_2025", 16, r"NPL\) - neto", DESC5, "id", "pct"),
    ("bni", "nplnet"): ("bni_2025", 28, r"^Net NPL$", BNI6, "en", "pct"),
    ("bri", "ekuitas"): ("bri_2025", 27, r"^TOTAL EKUITAS$", DESC5, "id", "jt"),
    ("mandiri", "ekuitas"): ("mandiri_2025", 37, r"^Total Ekuitas$", ASC5, "id", "jt"),
    ("btn", "ekuitas"): ("btn_2025", 24, r"^TOTAL EKUITAS$", DESC5, "id", "jt"),
    ("bca", "ekuitas"): ("bca_2025", 15, r"^Total Ekuitas$", DESC5, "id", "mi"),
})
dev._cache.clear()
LABEL = {**dev.LABEL, "roa": "ROA (return on assets)", "roe": "ROE (return on equity)", "nplnet": "rasio NPL net",
         "ekuitas": "total ekuitas"}
SOURCES = ["Pakai angka dari Laporan Tahunan 2025 tiap bank.", "Sumber: laporan tahunan 2025 masing-masing bank.",
           "Gunakan laporan tahunan 2025 sebagai sumber."]

v, shown, fact, names = dev.v, dev.shown, dev.fact, dev.names
TASKS: list[dict] = []


def trill(b: str, m: str, y: int) -> float:
    return dev.series(b, m)["vals"][y][0] / (1e6 if dev.series(b, m)["unit"] == "jt" else 1e3)


def add(cat, q, a, numbers, facts_, steps, extra_pages=()):
    pages = []
    for f in facts_:
        if [f["doc"], f["page"]] not in pages:
            pages.append([f["doc"], f["page"]])
    pages += [list(p) for p in extra_pages if list(p) not in pages]
    q = q + " " + SOURCES[len(TASKS) % len(SOURCES)]
    TASKS.append({"id": f"h{len(TASKS) + 1:03d}", "type": "agent_task", "category": cat, "question": q,
                  "gold_answer": a, "gold_numbers": numbers, "gold_facts": facts_, "gold_pages": pages,
                  "min_steps": steps, "answerable": True})


def pct(b, m, y):
    return shown(b, m, y).rstrip("%")


# ---------------------------------------------------------------- ranking (6)
def rank(m, y, bs, q, desc=False, gap=True):
    vals = {b: v(b, m, y) for b in bs}
    assert len(set(vals.values())) == len(bs), ("tie", m, y)
    order = sorted(bs, key=lambda b: vals[b], reverse=desc)
    g = round(max(vals.values()) - min(vals.values()), 2)
    a = "; ".join(f"{NAME[b]} {shown(b, m, y)}" for b in order) + (f". Selisih {idnum(g, 2)} poin persen." if gap else ".")
    add("ranking", q, a, [pct(b, m, y) for b in order] + ([idnum(g, 2)] if gap else []), [fact(b, m, y) for b in bs], len(bs))


rank("roa", 2025, ["bri", "mandiri", "btn", "bca", "bni"],
     "Susun BRI, Bank Mandiri, BTN, BCA, dan BNI menurut ROA 2025 dari yang tertinggi ke yang terendah, cantumkan "
     "angkanya, dan hitung jarak antara ROA tertinggi dan terendah dalam poin persen.", desc=True)
rank("roe", 2024, ["bri", "mandiri", "bca"],
     "Dilihat dari ROE tahun 2024, bank mana yang paling menguntungkan di antara BRI, Bank Mandiri, dan BCA? "
     "Sebutkan ROE ketiganya.", desc=True, gap=False)
rank("nplnet", 2025, ["bri", "mandiri", "bca"],  # BNI left out: 0,7% ties with BCA
     "Di antara BRI, Bank Mandiri, dan BCA, siapa yang punya NPL net paling rendah pada 2025, dan berapa "
     "selisihnya dengan NPL net paling tinggi (poin persen)? Sebutkan nilai ketiga bank.")
rank("ldr", 2023, ["bri", "btn", "bca", "mandiri"],
     "Urutkan LDR (loan to deposit ratio) tahun 2023 milik BRI, BTN, BCA, dan Bank Mandiri dari yang terbesar, "
     "lalu berapa beda LDR terbesar dan terkecil?", desc=True)
rank("bopo", 2023, ["bri", "bca", "bni"],
     "Bank mana yang paling efisien (BOPO terendah) pada 2023: BRI, BCA, atau BNI? Tampilkan BOPO masing-masing "
     "dan selisih BOPO terendah dengan tertinggi.")
ek = {b: round(trill(b, "ekuitas", 2025), 2) for b in ["bri", "mandiri", "btn", "bca"]}
order = sorted(ek, key=ek.get, reverse=True)
add("ranking", "Peringkatkan total ekuitas akhir 2025 BRI, Bank Mandiri, BTN, dan BCA dari yang terbesar, dalam "
    "triliun Rupiah dengan dua desimal.",
    "; ".join(f"{NAME[b]} Rp{idnum(ek[b], 2)} triliun" for b in order) + ".",
    [idnum(ek[b], 2) for b in order], [fact(b, "ekuitas", 2025) for b in order], 4)


# ---------------------------------------------------------------- single-bank trend (6)
def trend(b, m, q, years=ASC5):
    s = dev.series(b, m)
    vals = {y: s["vals"][y][0] for y in years}
    peak = max(years, key=vals.get)
    assert list(vals.values()).count(vals[peak]) == 1
    nominal = s["unit"] != "pct"
    ch = round((vals[years[-1]] / vals[years[0]] - 1) * 100, 2) if nominal else round(vals[years[-1]] - vals[years[0]], 2)
    a = ", ".join(f"{y}: {shown(b, m, y)}" for y in years) + f". Puncak {peak}. Perubahan {years[0]} ke {years[-1]}: {idnum(ch, 2)}."
    add("trend", q, a, [pct(b, m, y) for y in years] + [idnum(ch, 2)], [fact(b, m, y) for y in years], 1)


trend("bri", "roa", "Bagaimana perkembangan ROA BRI sepanjang 2021–2025? Kapan puncaknya, dan berapa poin persen "
      "perubahan ROA dari 2021 ke 2025?")
trend("mandiri", "roe", "Tampilkan ROE Bank Mandiri tiap tahun dari 2021 hingga 2025, tahun berapa ROE-nya paling "
      "tinggi, dan naik atau turun berapa poin persen antara 2021 dan 2025?")
trend("bca", "nplnet", "Ceritakan pergerakan NPL net BCA 2021-2025: angka tiap tahun, tahun dengan NPL net tertinggi, "
      "dan perubahannya dari 2021 ke 2025 (poin persen).")
trend("btn", "ekuitas", "Berapa total ekuitas BTN setiap tahun 2021 s.d. 2025, kapan tertinggi, dan berapa persen "
      "pertumbuhannya dari 2021 ke 2025?")
trend("bni", "nim", "Lihat NIM BNI dari 2021 sampai 2025: sebutkan nilainya per tahun, tahun puncaknya, dan selisih "
      "NIM 2025 dibanding 2021 dalam poin persen.")
trend("btn", "car", "Bagaimana tren KPMM (CAR) BTN 2021 hingga 2025? Sebutkan tiap tahun, tahun tertingginya, dan "
      "perubahan poin persen dari 2021 ke 2025.")


# ---------------------------------------------------------------- multi-bank trend (6)
def multi(m, bs, y0, y1, q):
    nominal = dev.series(bs[0], m)["unit"] != "pct"
    chg = {b: round((v(b, m, y1) / v(b, m, y0) - 1) * 100, 2) if nominal else round(v(b, m, y1) - v(b, m, y0), 2) for b in bs}
    big = max(bs, key=lambda b: abs(chg[b]))
    assert sorted(map(abs, chg.values()))[-1] != sorted(map(abs, chg.values()))[-2]
    nums = []
    for b in bs:
        nums += [pct(b, m, y0), pct(b, m, y1), idnum(chg[b], 2)]
    a = "; ".join(f"{NAME[b]} {shown(b, m, y0)} -> {shown(b, m, y1)} ({idnum(chg[b], 2)})" for b in bs) + f". Terbesar: {NAME[big]}."
    add("multi_trend", q, a, nums, [fact(b, m, y) for b in bs for y in (y0, y1)], len(bs))


multi("roa", ["bri", "mandiri", "bca"], 2022, 2025,
      "Seberapa besar perubahan ROA BRI, Bank Mandiri, dan BCA antara 2022 dan 2025? Sebutkan ROA kedua tahun "
      "per bank, perubahannya dalam poin persen, dan bank dengan perubahan paling besar (nilai absolut).")
multi("roe", ["bri", "btn", "bca"], 2021, 2024,
      "Bandingkan ROE 2021 dan 2024 untuk BRI, BTN, dan BCA: nilai tiap tahun, selisih poin persen per bank, dan "
      "bank yang ROE-nya berubah paling banyak (nilai absolut).")
multi("nplnet", ["bri", "mandiri", "bca"], 2021, 2025,
      "Untuk BRI, Bank Mandiri, dan BCA, berapa NPL net pada 2021 dan 2025, berapa perubahannya (poin persen), dan "
      "bank mana yang perubahannya terbesar secara absolut?")
multi("npl", ["mandiri", "btn", "bca"], 2023, 2025,
      "Bagaimana NPL gross Bank Mandiri, BTN, dan BCA bergeser dari 2023 ke 2025? Beri nilai kedua tahun, perubahan "
      "poin persen, dan bank dengan pergeseran terbesar (absolut).")
multi("ekuitas", ["bri", "mandiri", "bca"], 2021, 2025,
      "Berapa total ekuitas BRI, Bank Mandiri, dan BCA pada 2021 dan 2025, berapa persen pertumbuhannya masing-"
      "masing, dan bank mana yang tumbuh paling besar?")
multi("bopo", ["bri", "mandiri", "bni"], 2022, 2025,
      "Bandingkan BOPO 2022 dengan 2025 untuk BRI, Bank Mandiri, dan BNI. Sebutkan angka kedua tahun, perubahan "
      "dalam poin persen, dan bank dengan perubahan terbesar (nilai absolut).")


# ---------------------------------------------------------------- compute (10)
def one(q, a, numbers, facts_, steps):
    add("compute", q, a, numbers, facts_, steps)


g = round((v("bca", "ekuitas", 2025) / v("bca", "ekuitas", 2024) - 1) * 100, 2)
one("Berapa persen kenaikan total ekuitas BCA dari akhir 2024 ke akhir 2025 (dua desimal)?",
    f"{shown('bca', 'ekuitas', 2024)} -> {shown('bca', 'ekuitas', 2025)}: {idnum(g, 2)}%.", [idnum(g, 2)],
    [fact("bca", "ekuitas", 2024), fact("bca", "ekuitas", 2025)], 2)
bs = ["bri", "mandiri", "btn", "bca"]
avg = round(sum(v(b, "roe", 2025) for b in bs) / 4, 2)
one("Hitung rata-rata ROE 2025 dari BRI, Bank Mandiri, BTN, dan BCA (dua desimal).",
    f"rata-rata {idnum(avg, 2)}%.", [idnum(avg, 2)], [fact(b, "roe", 2025) for b in bs], 4)
tot = round(trill("bri", "ekuitas", 2025) + trill("mandiri", "ekuitas", 2025), 2)
one("Jika total ekuitas BRI dan Bank Mandiri per akhir 2025 dijumlahkan, berapa hasilnya dalam triliun Rupiah (dua desimal)?",
    f"Rp{idnum(tot, 2)} triliun.", [idnum(tot, 2)], [fact("bri", "ekuitas", 2025), fact("mandiri", "ekuitas", 2025)], 2)
d = round(v("bca", "roa", 2023) - v("bri", "roa", 2023), 2)
one("Pada 2023, berapa poin persen ROA BCA lebih tinggi atau lebih rendah daripada ROA BRI?",
    f"BCA {shown('bca', 'roa', 2023)} vs BRI {shown('bri', 'roa', 2023)}: {idnum(d, 2)} poin persen.", [idnum(abs(d), 2)],
    [fact("bca", "roa", 2023), fact("bri", "roa", 2023)], 2)
r = round(v("bri", "ekuitas", 2025) / v("bri", "aset", 2025) * 100, 2)
one("Berapa porsi total ekuitas terhadap total aset BRI pada akhir 2025, dalam persen (dua desimal)?",
    f"{idnum(r, 2)}%.", [idnum(r, 2)], [fact("bri", "ekuitas", 2025), fact("bri", "aset", 2025)], 2)
k = round(v("bca", "laba", 2025) / v("bca", "laba", 2021), 2)
one("Laba bersih BCA tahun 2025 berapa kali lipat laba bersih tahun 2021 (dua desimal)?",
    f"{idnum(k, 2)} kali.", [idnum(k, 2)], [fact("bca", "laba", 2025), fact("bca", "laba", 2021)], 2)
mean_nim = round(sum(v("bri", "nim", y) for y in ASC5) / 5, 2)
one("Berapa rata-rata NIM BRI selama lima tahun 2021–2025 (dua desimal)?",
    f"{idnum(mean_nim, 2)}%.", [idnum(mean_nim, 2)], [fact("bri", "nim", y) for y in ASC5], 1)
d = round(trill("bca", "laba", 2025) - trill("btn", "laba", 2025), 2)
one("Berapa triliun Rupiah selisih laba bersih BCA dan BTN tahun 2025 (dua desimal)?",
    f"Rp{idnum(d, 2)} triliun.", [idnum(d, 2)], [fact("bca", "laba", 2025), fact("btn", "laba", 2025)], 2)
g = round((v("mandiri", "laba", 2025) / v("mandiri", "laba", 2023) - 1) * 100, 2)
one("Berapa persen pertumbuhan laba tahun berjalan konsolidasian (total) Bank Mandiri dari 2023 ke 2025 (dua desimal)?",
    f"{idnum(g, 2)}%.", [idnum(g, 2)], [fact("mandiri", "laba", 2023), fact("mandiri", "laba", 2025)], 2)
d = round(v("btn", "npl", 2025) - v("btn", "npl", 2024), 2)
one("Apakah NPL gross BTN 2025 naik dibanding 2024, dan berapa poin persen perubahannya?",
    f"{shown('btn', 'npl', 2024)} -> {shown('btn', 'npl', 2025)}: {idnum(d, 2)} poin persen.", [idnum(abs(d), 2)],
    [fact("btn", "npl", 2024), fact("btn", "npl", 2025)], 2)

# ---------------------------------------------------------------- regulation + data (6)
REG = {
    "pojk11_p1": ("ojk_pojk_11_2016", 7, r"8% \(delapan persen\) dari Aset Tertimbang Menurut Risiko \(ATMR\) bagi Bank dengan profil risiko Peringkat 1", 8, "KPMM minimum profil risiko Peringkat 1: 8%"),
    "pojk11_14": ("ojk_pojk_11_2016", 7, r"11% \(sebelas persen\) sampai dengan 14% \(empat belas persen\)", 14, "batas atas KPMM minimum 14%"),
    "pojk11_core": ("ojk_pojk_11_2016", 14, r"modal inti paling rendah sebesar 6%", 6, "modal inti paling rendah 6%"),
    "padg_kpmm": ("bi_padg_23_2025", 7, r"KPMM Insentif sebesar 14%", 14, "KPMM Insentif 14%"),
    "padg_npl": ("bi_padg_23_2025", 8, r"rasio kredit bermasalah secara bruto lebih kecil dari 5%", 5, "ambang NPL bruto 5%"),
}
for key, (doc, page, rx, _, _) in REG.items():
    assert re.search(rx, dev.page_text(doc, page), re.I), f"regulation fact {key} not on {doc} p{page}"


def reg(key, bank, m, y, q):
    doc, page, _, thr, desc = REG[key]
    d = round(v(bank, m, y) - thr, 2)
    add("regulation", q, f"{desc} ({doc} hal. {page}); {NAME[bank]} {shown(bank, m, y)}; selisih {idnum(abs(d), 2)} poin persen.",
        [idnum(thr, 0), pct(bank, m, y), idnum(abs(d), 2)], [fact(bank, m, y)], 2, extra_pages=[(doc, page)])


reg("pojk11_p1", "mandiri", "car", 2024, "Untuk bank dengan profil risiko Peringkat 1, POJK 11/POJK.03/2016 mensyaratkan "
    "KPMM minimum berapa persen? Seberapa jauh KPMM Bank Mandiri 2024 di atas syarat itu (poin persen)?")
reg("pojk11_p1", "btn", "car", 2023, "Bandingkan KPMM BTN tahun 2023 dengan KPMM minimum bagi bank berprofil risiko "
    "Peringkat 1 menurut POJK 11/POJK.03/2016: berapa syaratnya dan berapa kelebihannya?")
reg("pojk11_14", "bca", "car", 2023, "Kalau batas tertinggi KPMM minimum dalam POJK 11/POJK.03/2016 dipakai sebagai "
    "patokan, berapa selisih CAR BCA 2023 terhadap patokan itu?")
reg("pojk11_core", "bca", "tier1", 2024, "Berapa persen modal inti minimum terhadap ATMR yang diwajibkan POJK "
    "11/POJK.03/2016, dan berapa poin persen CAR Tier 1 BCA 2024 melebihinya?")
reg("padg_kpmm", "btn", "car", 2025, "Apakah KPMM BTN 2025 memenuhi KPMM Insentif dalam PADG 23 Tahun 2025? Sebutkan "
    "angka KPMM Insentif itu dan selisihnya.")
reg("padg_npl", "mandiri", "npl", 2025, "PADG 23 Tahun 2025 memakai batas rasio kredit bermasalah bruto untuk insentif. "
    "Berapa batas itu, dan berapa ruang NPL gross Bank Mandiri 2025 di bawahnya (poin persen)?")

# ---------------------------------------------------------------- unanswerable (6)
UNANS = [
    ("Berapa NPL gross Allo Bank tahun 2025 dan bandingkan dengan BRI.", ["allo bank"]),  # Danamon is in the corpus (165x)
    ("Berapa realisasi ROA BRI tahun 2028, dan berapa perubahannya dari 2025?", ["roa bri tahun 2028", "realisasi roa"]),  # 2026 guidance exists in the corpus
    ("Berapa jumlah mesin ATM BNI di Provinsi Maluku Utara pada akhir 2025?", ["atm bni di maluku utara"]),
    ("Berapa NPL kredit kendaraan listrik BCA pada kuartal III 2025, dan berapa selisihnya dengan NPL gross BCA?", ["npl kredit kendaraan listrik", "kendaraan listrik bca"]),
    ("Berapa total bonus tahunan Direktur Utama BTN 2025 dalam Rupiah, dan berapa persen dari laba BTN?", ["bonus tahunan direktur utama"]),
    ("Berapa rasio LDR kantor cabang Bank Mandiri Surabaya pada 2025?", ["cabang bank mandiri surabaya", "mandiri surabaya"]),
]
corpus = "".join(p.read_text(encoding="utf-8").lower() for p in dev.PROC.glob("*.jsonl"))
for q, absent in UNANS:
    for term in absent:
        assert term not in corpus, f"{term!r} occurs in the corpus"
    TASKS.append({"id": f"h{len(TASKS) + 1:03d}", "type": "agent_task", "category": "unanswerable", "question": q,
                  "gold_answer": "TIDAK DITEMUKAN", "gold_numbers": [], "gold_facts": [], "gold_pages": [],
                  "min_steps": 1, "answerable": False})

assert len(TASKS) == 40, len(TASKS)
OUT.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in TASKS) + "\n", encoding="utf-8")
print(Counter(t["category"] for t in TASKS), "->", OUT)
