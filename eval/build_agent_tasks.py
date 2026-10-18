"""Build eval/agent_tasks.jsonl: 60 multi-step agent tasks (Phase 3, week 9).

Every gold figure is parsed from the cited page in data/processed (nothing typed by hand) and every
derived number (gaps, growth, sums) is computed here, so the gold answers can be regenerated and re-checked:

    .venv/Scripts/python eval/build_agent_tasks.py

Categories (count): ranking 12, trend 10, multi_trend 10, compute 14, regulation 8, unanswerable 6.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PROC = HERE.parent / "data" / "processed"
OUT = HERE / "agent_tasks.jsonl"

NAME = {"bri": "BRI", "mandiri": "Bank Mandiri", "btn": "BTN", "bca": "BCA", "bni": "BNI"}
DESC5 = [2025, 2024, 2023, 2022, 2021]
ASC5 = [2021, 2022, 2023, 2024, 2025]
BNI6 = [2025, 2024, None, 2023, 2022, 2021]  # BNI tables carry a "change" column after 2024

# (bank, metric) -> (doc, page, label regex on the first cell, year order of the cells, decimal style, unit)
# unit: "pct" ratio, "jt" million Rp, "mi" billion Rp
S = {
    ("bri", "aset"): ("bri_2025", 26, r"^TOTAL ASET$", DESC5, "id", "jt"),
    ("btn", "aset"): ("btn_2025", 21, r"^TOTAL ASET$", DESC5, "id", "jt"),
    ("bca", "aset"): ("bca_2025", 15, r"^Total Aset$", DESC5, "id", "mi"),
    ("mandiri", "aset"): ("mandiri_2025", 36, r"^Total Aset$", ASC5, "id", "jt"),
    ("bri", "laba"): ("bri_2025", 28, r"^LABA BERSIH$", DESC5, "id", "jt"),
    ("btn", "laba"): ("btn_2025", 25, r"^LABA TAHUN BERJALAN$", DESC5, "id", "jt"),
    ("bca", "laba"): ("bca_2025", 15, r"^Laba Bersih$", DESC5, "id", "mi"),
    ("mandiri", "laba"): ("mandiri_2025", 38, r"^Laba Tahun Berjalan$", ASC5, "id", "jt"),
    ("bri", "npl"): ("bri_2025", 31, r"^NPL Gross$", DESC5, "id", "pct"),
    ("btn", "npl"): ("btn_2025", 28, r"Non Performing Loan \(NPL\) Gross", DESC5, "id", "pct"),
    ("bca", "npl"): ("bca_2025", 16, r"NPL\) - bruto", DESC5, "id", "pct"),
    ("mandiri", "npl"): ("mandiri_2025", 39, r"^NPL Gross$", ASC5, "id", "pct"),
    ("bni", "npl"): ("bni_2025", 28, r"^Gross NPL$", BNI6, "en", "pct"),
    ("bri", "ldr"): ("bri_2025", 31, r"^LDR$", DESC5, "id", "pct"),
    ("btn", "ldr"): ("btn_2025", 28, r"^Loan to Deposit Ratio \(LDR\)$", DESC5, "id", "pct"),
    ("bca", "ldr"): ("bca_2025", 16, r"Loan to Deposit Ratio - LDR", DESC5, "id", "pct"),
    ("mandiri", "ldr"): ("mandiri_2025", 40, r"^Loan to Deposit Ratio \(LDR\)$", ASC5, "id", "pct"),
    ("bni", "ldr"): ("bni_2025", 29, r"Loan to Deposit Ratio \(LDR\)", BNI6, "en", "pct"),
    ("bri", "car"): ("bri_2025", 32, r"^Rasio Kewajiban Penyediaan Modal Minimum \(KPMM\)$", DESC5, "id", "pct"),
    ("btn", "car"): ("btn_2025", 28, r"^Rasio Kewajiban Penyediaan Modal Minimum \(KPMM\)$", DESC5, "id", "pct"),
    ("bca", "car"): ("bca_2025", 15, r"^Rasio Kecukupan Modal \(Capital Adequacy", DESC5, "id", "pct"),
    ("mandiri", "car"): ("mandiri_2025", 39, r"^Kewajiban Penyediaan Modal Minimum \(KPMM\)$", ASC5, "id", "pct"),
    ("bri", "nim"): ("bri_2025", 31, r"^NIM$", DESC5, "id", "pct"),
    ("bca", "nim"): ("bca_2025", 16, r"^Marjin Bunga Bersih", DESC5, "id", "pct"),
    ("mandiri", "nim"): ("mandiri_2025", 40, r"^Marjin Bunga Bersih \(NIM\)$", ASC5, "id", "pct"),
    ("bni", "nim"): ("bni_2025", 29, r"^Net Interest Margin \(NIM\)$", BNI6, "en", "pct"),
    ("bri", "bopo"): ("bri_2025", 31, r"^BOPO$", DESC5, "id", "pct"),
    ("bca", "bopo"): ("bca_2025", 16, r"^Beban Operasional terhadap Pendapatan Operasional", DESC5, "id", "pct"),
    ("mandiri", "bopo"): ("mandiri_2025", 40, r"^Beban Operasional terhadap Penghasilan Operasional", ASC5, "id", "pct"),
    ("bni", "bopo"): ("bni_2025", 29, r"^Operating Cost/Operating Income", BNI6, "en", "pct"),
    ("bri", "casa"): ("bri_2025", 31, r"^CASA$", DESC5, "id", "pct"),
    ("bca", "casa"): ("bca_2025", 16, r"^Rasio CASA terhadap", DESC5, "id", "pct"),
    ("bni", "casa"): ("bni_2025", 29, r"^Current Account/Saving Account \(CASA\) Ratio", BNI6, "en", "pct"),
    ("bri", "tier1"): ("bri_2025", 32, r"^Rasio Kecukupan Modal Tier 1", DESC5, "id", "pct"),
    ("bca", "tier1"): ("bca_2025", 15, r"^CAR Tier 1$", DESC5, "id", "pct"),
}
LABEL = {
    "npl": "rasio NPL gross", "ldr": "Loan to Deposit Ratio (LDR)", "car": "rasio kecukupan modal (CAR/KPMM)",
    "nim": "Net Interest Margin (NIM)", "bopo": "rasio BOPO", "casa": "rasio CASA",
    "aset": "total aset", "laba": "laba bersih (laba tahun berjalan)",
}

_cache: dict[str, dict[int, str]] = {}


def page_text(doc: str, page: int) -> str:
    if doc not in _cache:
        _cache[doc] = {}
        for line in open(PROC / f"{doc}.jsonl", encoding="utf-8"):
            r = json.loads(line)
            _cache[doc][r["page"]] = r["text"]
    return _cache[doc][page]


def num(s: str, style: str) -> float:
    s = s.strip().rstrip("%").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    v = float(s.replace(",", "")) if style == "en" else float(s.replace(".", "").replace(",", "."))
    return -v if neg else v


def row_cells(doc: str, page: int, label: str) -> list[str]:
    found = []
    for line in page_text(doc, page).split("\n"):
        if line.lstrip().startswith("|"):
            parts = [c.strip() for c in line.strip().strip("|").split("|")]
            if parts and re.search(label, parts[0], re.I):
                found.append(parts[1:])
    assert found, f"no row {label!r} on {doc} p{page}"
    assert all(f == found[0] for f in found), f"ambiguous row {label!r} on {doc} p{page}"
    return found[0]


def series(bank: str, metric: str) -> dict:
    """{year: (value, raw cell)} plus provenance, parsed from the report page."""
    doc, page, label, order, style, unit = S[(bank, metric)]
    cells = row_cells(doc, page, label)
    assert len(cells) >= len(order), (bank, metric, cells)
    vals = {}
    for y, c in zip(order, cells):
        if y is not None and c not in ("", "-"):
            vals[y] = (num(c, style), c)
    return {"doc": doc, "page": page, "label": label, "unit": unit, "style": style, "vals": vals}


def v(bank: str, metric: str, year: int) -> float:
    return series(bank, metric)["vals"][year][0]


def idnum(x: float, dec: int) -> str:
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if x < 0 and float(s.replace(".", "").replace(",", ".")) != 0 else "") + s


def shown(bank: str, metric: str, year: int) -> str:
    """The value as the report prints it (BNI uses dot decimals: rewrite with a comma)."""
    s = series(bank, metric)
    raw = s["vals"][year][1]
    if s["style"] == "en":
        raw = raw.replace(".", ",")
    pct = s["unit"] == "pct" and not raw.endswith("%")
    return raw + ("%" if pct else "")


def fact(bank: str, metric: str, year: int) -> dict:
    s = series(bank, metric)
    return {"doc": s["doc"], "page": s["page"], "label": metric, "year": year, "value": s["vals"][year][1]}


def to_triliun(bank: str, x: float) -> float:
    return x / 1e6 if series(bank, "aset")["unit"] == "jt" else x / 1e3


TASKS: list[dict] = []


def add(cat: str, question: str, answer: str, numbers: list[str], facts: list[dict], steps: int, extra_pages=()) -> None:
    pages = []
    for f in facts:
        p = [f["doc"], f["page"]]
        if p not in pages:
            pages.append(p)
    for p in extra_pages:
        if list(p) not in pages:
            pages.append(list(p))
    # restated prior-year figures differ between reports (BRI 2024 total assets: 1.992.983.447 in the 2024 report,
    # 1.992.186.906 in the 2025 report), so the question must name its source
    question += " Gunakan data dari Laporan Tahunan 2025 masing-masing bank."
    TASKS.append({"id": f"t{len(TASKS) + 1:03d}", "type": "agent_task", "category": cat, "question": question,
                  "gold_answer": answer, "gold_numbers": numbers, "gold_facts": facts, "gold_pages": pages,
                  "min_steps": steps, "answerable": True})


def names(banks: list[str]) -> str:
    n = [NAME[b] for b in banks]
    return ", ".join(n[:-1]) + " dan " + n[-1] if len(n) > 1 else n[0]


# ---------------------------------------------------------------- 1. ranking (12)
RANKING = [
    ("npl", 2025, ["bri", "mandiri", "btn", "bca"]), ("npl", 2024, ["bri", "mandiri", "btn", "bni"]),
    ("ldr", 2025, ["bri", "mandiri", "btn", "bca"]), ("ldr", 2025, ["bri", "mandiri", "bni"]),
    ("car", 2025, ["bri", "btn", "bca", "mandiri"]), ("car", 2024, ["bri", "mandiri", "bca"]),
    ("nim", 2025, ["bri", "mandiri", "bca", "bni"]), ("nim", 2023, ["bri", "bca", "bni"]),
    ("bopo", 2025, ["bri", "mandiri", "bca", "bni"]), ("bopo", 2024, ["bri", "bca", "mandiri"]),
    ("casa", 2025, ["bri", "bca", "bni"]), ("npl", 2025, ["bca", "bni", "mandiri"]),
]
for m, y, bs in RANKING:
    vals = {b: v(b, m, y) for b in bs}
    order = sorted(bs, key=lambda b: vals[b])
    assert len({vals[b] for b in bs}) == len(bs), ("tie", m, y, bs)
    gap = round(vals[order[-1]] - vals[order[0]], 2)
    q = (f"Urutkan {names(bs)} berdasarkan {LABEL[m]} pada {y} dari yang terendah ke tertinggi, "
         f"sebutkan nilai masing-masing, lalu hitung selisih antara yang tertinggi dan terendah (dalam poin persen).")
    a = "; ".join(f"{NAME[b]} {shown(b, m, y)}" for b in order) + f". Selisih tertinggi dan terendah {idnum(gap, 2)} poin persen."
    add("ranking", q, a, [shown(b, m, y).rstrip("%") for b in order] + [idnum(gap, 2)],
        [fact(b, m, y) for b in bs], len(bs))

# ---------------------------------------------------------------- 2. single-bank trend (10)
TREND = [("bri", "npl"), ("mandiri", "npl"), ("btn", "npl"), ("bca", "npl"), ("bri", "nim"),
         ("mandiri", "nim"), ("bca", "laba"), ("bri", "aset"), ("btn", "laba"), ("bni", "ldr")]
for b, m in TREND:
    s = series(b, m)
    ys = [y for y in ASC5 if y in s["vals"]]
    assert ys == ASC5, (b, m, ys)
    peak = max(ys, key=lambda y: s["vals"][y][0])
    assert sum(1 for y in ys if s["vals"][y][0] == s["vals"][peak][0]) == 1
    nominal = s["unit"] != "pct"
    if nominal:
        ch = round((s["vals"][2025][0] / s["vals"][2021][0] - 1) * 100, 2)
        unit_txt, chtxt = "persen", f"{idnum(ch, 2)}%"
    else:
        ch = round(s["vals"][2025][0] - s["vals"][2021][0], 2)
        unit_txt, chtxt = "poin persen", f"{idnum(ch, 2)} poin persen"
    q = (f"Sebutkan {LABEL[m]} {NAME[b]} untuk setiap tahun 2021 sampai 2025, tahun mana yang tertinggi, "
         f"dan berapa perubahannya dari 2021 ke 2025 ({'pertumbuhan dalam persen' if nominal else 'dalam poin persen'})?")
    a = ", ".join(f"{y}: {shown(b, m, y)}" for y in ASC5) + f". Tertinggi {peak}. Perubahan 2021 ke 2025: {chtxt}."
    add("trend", q, a, [shown(b, m, y).rstrip("%") for y in ASC5] + [idnum(ch, 2)],
        [fact(b, m, y) for y in ASC5], 1)

# ---------------------------------------------------------------- 3. multi-bank trend (10)
MULTI = [("npl", ["bri", "mandiri", "btn"]), ("npl", ["bca", "bni", "bri"]), ("ldr", ["bri", "mandiri", "btn"]),
         ("ldr", ["bca", "bni", "mandiri"]), ("nim", ["bri", "mandiri", "bca"]), ("bopo", ["bri", "bca", "mandiri"]),
         ("car", ["bri", "mandiri", "bca"]), ("nim", ["bca", "bni", "bri"]), ("laba", ["bri", "btn", "bca"]),
         ("aset", ["bri", "bca", "btn"])]
for m, bs in MULTI:
    nominal = series(bs[0], m)["unit"] != "pct"
    chg = {}
    for b in bs:
        a0, a1 = v(b, m, 2021), v(b, m, 2025)
        chg[b] = round((a1 / a0 - 1) * 100, 2) if nominal else round(a1 - a0, 2)
    big = max(bs, key=lambda b: abs(chg[b]))
    assert sorted(abs(c) for c in chg.values())[-1] != sorted(abs(c) for c in chg.values())[-2]
    word = "pertumbuhan (persen)" if nominal else "perubahan (poin persen)"
    q = (f"Bandingkan {LABEL[m]} {names(bs)} pada 2021 dan 2025. Sebutkan nilai kedua tahun untuk tiap bank, "
         f"{word} dari 2021 ke 2025, dan bank mana yang mengalami perubahan terbesar (dalam nilai absolut).")
    a = "; ".join(f"{NAME[b]} {shown(b, m, 2021)} -> {shown(b, m, 2025)} ({idnum(chg[b], 2)})" for b in bs)
    a += f". Perubahan terbesar: {NAME[big]}."
    nums = []
    for b in bs:
        nums += [shown(b, m, 2021).rstrip("%"), shown(b, m, 2025).rstrip("%"), idnum(chg[b], 2)]
    add("multi_trend", q, a, nums, [fact(b, m, y) for b in bs for y in (2021, 2025)], len(bs))

# ---------------------------------------------------------------- 4. computation (14)
def growth_task(b, m, label):
    a0, a1 = v(b, m, 2024), v(b, m, 2025)
    g = round((a1 / a0 - 1) * 100, 2)
    q = f"Berapa pertumbuhan {label} {NAME[b]} pada 2025 dibandingkan 2024 dalam persen (dua desimal)?"
    add("compute", q, f"{NAME[b]}: {shown(b, m, 2024)} -> {shown(b, m, 2025)}, pertumbuhan {idnum(g, 2)}%.",
        [idnum(g, 2)], [fact(b, m, 2024), fact(b, m, 2025)], 1)


growth_task("bri", "aset", "total aset")
growth_task("btn", "aset", "total aset")
growth_task("mandiri", "aset", "total aset")
growth_task("bca", "laba", "laba bersih")


def sum_task(bs, m, label):
    tot = round(sum(to_triliun(b, v(b, m, 2025)) for b in bs), 2)
    q = (f"Berapa total {label} 2025 gabungan {names(bs)} dalam triliun Rupiah (dua desimal)? "
         f"Perhatikan satuan tiap laporan.")
    add("compute", q, f"{' + '.join(NAME[b] + ' ' + shown(b, m, 2025) for b in bs)} = Rp{idnum(tot, 2)} triliun.",
        [idnum(tot, 2)], [fact(b, m, 2025) for b in bs], len(bs))


sum_task(["bri", "mandiri"], "laba", "laba tahun berjalan konsolidasian (total, sebelum pembagian ke kepentingan non-pengendali)")
sum_task(["bri", "mandiri", "btn", "bca"], "laba", "laba tahun berjalan konsolidasian (total, sebelum pembagian ke kepentingan non-pengendali)")
sum_task(["bri", "btn", "bca"], "aset", "aset")

diff = round(abs(to_triliun("bri", v("bri", "aset", 2025)) - to_triliun("mandiri", v("mandiri", "aset", 2025))), 2)
add("compute", "Berapa selisih total aset Bank Mandiri dan BRI pada akhir 2025 dalam triliun Rupiah (dua desimal), "
    "dan bank mana yang lebih besar?",
    f"Bank Mandiri {shown('mandiri', 'aset', 2025)} lebih besar dari BRI {shown('bri', 'aset', 2025)}; selisih Rp{idnum(diff, 2)} triliun.",
    [idnum(diff, 2)], [fact("bri", "aset", 2025), fact("mandiri", "aset", 2025)], 2)


def roa(b):
    return round(v(b, "laba", 2025) / v(b, "aset", 2025) * 100, 2)


for b in ["bri", "mandiri", "btn", "bca"]:
    add("compute", f"Hitung laba tahun berjalan konsolidasian 2025 (total, sebelum pembagian ke kepentingan non-pengendali) dibagi total aset akhir 2025 untuk {NAME[b]} dalam persen (dua desimal).",
        f"{shown(b, 'laba', 2025)} / {shown(b, 'aset', 2025)} = {idnum(roa(b), 2)}%.",
        [idnum(roa(b), 2)], [fact(b, "laba", 2025), fact(b, "aset", 2025)], 1)

bs4 = ["bri", "mandiri", "btn", "bca"]
avg = round(sum(v(b, "npl", 2025) for b in bs4) / 4, 2)
add("compute", "Berapa rata-rata sederhana rasio NPL gross 2025 dari BRI, Bank Mandiri, BTN, dan BCA (dua desimal)?",
    f"({' + '.join(shown(b, 'npl', 2025).rstrip('%') for b in bs4)}) / 4 = {idnum(avg, 2)}%.",
    [idnum(avg, 2)], [fact(b, "npl", 2025) for b in bs4], 4)
bs3 = ["bri", "mandiri", "bca"]
best = max(bs3, key=roa)
add("compute", "Di antara BRI, Bank Mandiri, dan BCA, bank mana yang memiliki laba tahun berjalan konsolidasian 2025 (total) dibagi total aset akhir 2025 "
    "tertinggi, dan berapa nilainya (persen, dua desimal)?",
    f"{NAME[best]} dengan {idnum(roa(best), 2)}% (" + ", ".join(f"{NAME[b]} {idnum(roa(b), 2)}%" for b in bs3) + ").",
    [idnum(roa(b), 2) for b in bs3],
    [fact(b, m, 2025) for b in bs3 for m in ("laba", "aset")], 3)

# ---------------------------------------------------------------- 5. regulation + data (8)
REG = {
    "pojk11_14": ("ojk_pojk_11_2016", 7, r"11% \(sebelas persen\) sampai dengan 14% \(empat belas persen\)", "batas atas KPMM minimum 14%"),
    "pojk11_core": ("ojk_pojk_11_2016", 14, r"modal inti paling rendah sebesar 6%", "modal inti paling rendah 6% dari ATMR"),
    "padg_kpmm": ("bi_padg_23_2025", 7, r"KPMM Insentif sebesar 14%", "KPMM Insentif 14%"),
    "padg_npl": ("bi_padg_23_2025", 8, r"rasio kredit bermasalah secara bruto lebih kecil dari 5%", "ambang NPL bruto 5%"),
}
for k, (doc, page, rx, _) in REG.items():
    assert re.search(rx, page_text(doc, page), re.I), f"regulation fact {k} not on {doc} p{page}"


def reg_task(key, bank, metric, q, thr, kind):
    doc, page, _, desc = REG[key]
    x = v(bank, metric, 2025)
    d = round(x - thr, 2)
    a = f"{desc} ({doc} hal. {page}); {NAME[bank]} {shown(bank, metric, 2025)}; selisih {idnum(abs(d), 2)} poin persen, {kind(d)}."
    add("regulation", q, a, [idnum(thr, 0), shown(bank, metric, 2025).rstrip("%"), idnum(abs(d), 2)],
        [fact(bank, metric, 2025)], 2, extra_pages=[(doc, page)])


above = lambda d: "di atas batas" if d > 0 else "di bawah batas"
below = lambda d: "di bawah ambang" if d < 0 else "di atas ambang"
reg_task("pojk11_14", "bca", "car", "Menurut POJK 11/POJK.03/2016, berapa batas atas KPMM minimum untuk bank dengan profil risiko "
         "Peringkat 4 atau 5, dan berapa selisih CAR BCA 2025 terhadap batas tersebut (poin persen)?", 14, above)
reg_task("pojk11_14", "bri", "car", "POJK 11/POJK.03/2016 menetapkan KPMM minimum paling tinggi 14% untuk profil risiko terburuk. "
         "Berapa selisih KPMM BRI 2025 terhadap angka 14% itu (poin persen)?", 14, above)
reg_task("pojk11_14", "btn", "car", "Berdasarkan batas atas KPMM minimum dalam POJK 11/POJK.03/2016, apakah KPMM BTN 2025 lebih tinggi, "
         "dan berapa selisihnya (poin persen)?", 14, above)
reg_task("padg_kpmm", "mandiri", "car", "Berapa KPMM Insentif menurut PADG 23 Tahun 2025, dan berapa selisih KPMM Bank Mandiri 2025 "
         "terhadapnya (poin persen)?", 14, above)
reg_task("padg_npl", "btn", "npl", "PADG 23 Tahun 2025 menyebut ambang rasio kredit bermasalah bruto tertentu pada parameter insentif. "
         "Berapa ambang itu dan berapa selisih NPL gross BTN 2025 terhadapnya (poin persen)?", 5, below)
reg_task("padg_npl", "bri", "npl", "Berapa ambang rasio kredit bermasalah bruto dalam PADG 23 Tahun 2025, dan apakah NPL gross BRI 2025 "
         "berada di bawahnya? Sebutkan selisihnya (poin persen).", 5, below)
reg_task("pojk11_core", "bca", "tier1", "POJK 11/POJK.03/2016 mewajibkan modal inti paling rendah sekian persen dari ATMR. "
         "Berapa selisih CAR Tier 1 BCA 2025 terhadap angka itu (poin persen)?", 6, above)
reg_task("pojk11_core", "bri", "tier1", "Berapa batas minimum modal inti terhadap ATMR dalam POJK 11/POJK.03/2016, dan berapa selisih "
         "CAR Tier 1 BRI 2025 terhadapnya (poin persen)?", 6, above)

# ---------------------------------------------------------------- 6. unanswerable (6)
UNANS = [
    ("Hitung rata-rata NPL gross kuartal I 2027 dari BRI, BCA, dan BTN, lalu bandingkan dengan 2025.", ["Triwulan I 2027", "kuartal I 2027"]),
    ("Berapa selisih total gaji pokok Direksi BRI dan Bank Mandiri per orang per bulan pada 2025?", ["gaji pokok direksi"]),
    ("Berapa jumlah nasabah kredit BTN di Kabupaten Natuna dan Kabupaten Kepulauan Anambas pada 2025, dan berapa totalnya?", ["Natuna"]),
    ("Berapa harga penutupan saham BBCA pada 31 Desember 2029 dan berapa persen kenaikannya dari 2025?", ["31 Desember 2029"]),
    ("Berapa target laba bersih BNI tahun 2030 menurut laporan, dan berapa pertumbuhan tahunan majemuk dari 2025 ke 2030?", ["target laba bersih 2030"]),
    ("Berapa NPL gross BRI di Kecamatan Pulau Tiga per 2025 dan berapa selisihnya dengan NPL gross konsolidasian?", ["Pulau Tiga"]),
]
corpus_text = ""
for p in PROC.glob("*.jsonl"):
    if "_en" not in p.stem.split("__")[0][-3:]:
        corpus_text += p.read_text(encoding="utf-8").lower()
for q, absent in UNANS:
    for term in absent:
        assert term.lower() not in corpus_text, f"term {term!r} exists in the corpus; pick another unanswerable task"
    TASKS.append({"id": f"t{len(TASKS) + 1:03d}", "type": "agent_task", "category": "unanswerable", "question": q,
                  "gold_answer": "TIDAK DITEMUKAN", "gold_numbers": [], "gold_facts": [], "gold_pages": [],
                  "min_steps": 1, "answerable": False})

assert len(TASKS) == 60, len(TASKS)
OUT.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in TASKS) + "\n", encoding="utf-8")
from collections import Counter  # noqa: E402

print(Counter(t["category"] for t in TASKS), "->", OUT)
