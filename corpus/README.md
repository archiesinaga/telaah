# Indonesian banking corpus — download kit

54 documents for the GenAI document-research project: annual reports for BRI, Mandiri, BNI, BCA and BTN (2024 and 2025, Indonesian and English) plus core OJK and Bank Indonesia banking regulations.

## Run it (Python 3.8+, no installs)

```bash
python download_corpus.py --check        # quick link test, no full download (~1 min)
python download_corpus.py                # download everything into ./corpus/
python download_corpus.py --lang id      # Indonesian only
python download_corpus.py --skip-aux     # skip FAQ / ringkasan / penjelasan files
python download_corpus.py --category ojk bi --with-extras   # regulations + every side PDF on OJK/BI pages
```

Each file is saved as `<doc_id>.pdf` (e.g. `bri_2025.pdf`, `ojk_pojk_17_2023.pdf`, `bi_padg_23_2025.pdf`), so the filename is the doc_id for citations. English versions end in `_en`; side documents use `__faq`, `__ringkasan`, `__penjelasan`. Re-running skips files you already have. Results and SHA-256 hashes go to `corpus/download_log.csv`.

Expect about 1 GB in total; the two BTN 2025 reports are ~95 MB each.

## How sure each link is (`verification` column)

| Value | Meaning |
|---|---|
| `fetched` | Opened and confirmed as the right document |
| `listed_on_official_page` | Exact link copied from the bank's own investor-relations page |
| `search_indexed` | Exact PDF URL on ojk.go.id / bi.go.id / peraturan.go.id, found indexed |
| `landing_page_scrape` | No direct link; the script opens the official OJK page and picks the main PDF (prefers "Salinan"/POJK, skips Abstrak/FAQ/Ringkasan) |
| `pattern_candidate` | File name inferred from the issuer's naming pattern; may 404 (5 rows) |

The `legal_status` column marks superseded rules (e.g. PBI 3/2023 replaced by PBI 6/2026, PBI 11/2023 replaced by PBI 9/2025). They're kept on purpose so the agent can answer "what changed" questions — filter them out if you want only rules in force.

## If something fails

Open the row's `landing_page` (or IDX: idx.co.id → Perusahaan Tercatat → Laporan Keuangan dan Tahunan → filter by ticker and year), download by hand and save it as `<doc_id>.pdf` in `corpus/`. Some government sites have flaky TLS; `--insecure` skips certificate checks for those only if you trust the network.

## Known gaps (not in the manifest — no confirmed official URL found)

- PBI 20/4/PBI/2018 (RIM & PLM base regulation) — only its 5th amendment (PBI 2/2026) and PADG 23/2025 are included
- PBI 22/23/PBI/2020 Sistem Pembayaran and PBI 23/6/PBI/2021 Penyedia Jasa Pembayaran
- SEOJK 24/SEOJK.03/2023 Penilaian Tingkat Maturitas Digital Bank Umum
- POJK on anti-fraud strategy and POJK 4/POJK.03/2016 Tingkat Kesehatan Bank
