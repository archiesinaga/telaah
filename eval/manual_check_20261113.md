# Manual check of 30 answers (2026-11-13)

Run: `eval/runs/bench-dev-20261112-075716.json` (base qwen2.5:7b-gpu, defaults ON). Sample: 5 random answers per
answerable type, `random.Random(20261113)`. Checked by Claude against the gold answer and the text of the cited PDF
pages (pymupdf on `data/raw/<doc>.pdf`). Verdicts: R = right, D = defensible, W = wrong; cite = cited page supports
the answer (Y / partly / N).

| id | type | auto num | auto cite | judge | manual | cite | note |
|---|---|---|---|---|---|---|---|
| bd0086 | table_lookup | 1 | 1 | - | R | Y | |
| q003 | table_lookup | 1 | 1 | - | R | Y | facts route |
| bd0080 | table_lookup | 0 | 0 | 0 | W | - | gave retail loan interest income (p.1267), not total loans |
| bd0110 | table_lookup | 1 | 1 | 1 | R | Y | |
| bd0145 | table_lookup | 1 | 1 | - | R | Y | |
| q017 | text_fact | 1 | 1 | - | R | Y | |
| bd0047 | text_fact | - | 1 | 1 | R | Y | |
| q024 | text_fact | 1 | 1 | - | R | Y | omits the 10-day extension in the gold; core answer right |
| bd0054 | text_fact | 1 | 1 | - | R | Y | |
| bd0005 | text_fact | - | 1 | 1 | R | Y | |
| bd0217 | calculation | 0 | 0 | 0 | D | Y | 5,3% is printed on p.333 (MD&A); gold 4,53% from notes figures |
| bd0211 | calculation | 1 | 1 | - | R | Y | |
| bd0255 | calculation | 1 | 0 | 1 | R | partly | btn_2025 p.28 prints both figures; btn_2024 p.899 does not |
| bd0219 | calculation | 0 | 0 | 0 | W | - | wrong table (p.390/413) |
| bd0244 | calculation | 1 | 1 | - | R | Y | |
| q029 | chart | 1 | 1 | - | R | Y | |
| bd0162 | chart | 1 | 1 | - | R | Y | |
| bd0199 | chart | 0 | 0 | 0 | W | - | 27.937 incl. subsidiaries; gold 26.435 bank only |
| bd0174 | chart | 1 | 0 | 1 | R | N | 1,4% not on cited p.32 |
| q028 | chart | 1 | 1 | - | R | Y | |
| bd0303 | cross_doc | 1 | 1 | - | R | Y | |
| bd0329 | cross_doc | 0 | 1 | 1 | R | Y | scorer: gold lists both LDRs; answer gives difference + bank |
| bd0320 | cross_doc | 0 | 1 | 1 | R | Y | scorer: "23,5%" vs gold "23,50%" |
| bd0298 | cross_doc | 0 | 0 | 0 | W | - | BNI consolidated LCR 150,67% instead of bank-only 147,95% |
| q039 | cross_doc | - | 1 | 1 | R | Y | restatement route |
| bd0364 | regulation | 1 | 0 | 1 | R | N | right number (2); cited p.26 is a different rule |
| bd0358 | regulation | - | 1 | 1 | R | Y | |
| bd0354 | regulation | - | 1 | 1 | R | Y | |
| bd0376 | regulation | - | 1 | 1 | R | Y | |
| bd0351 | regulation | - | 1 | 1 | R | Y | |

Totals: 25 R, 1 D, 4 W. Numeric (23 scored): auto 16 right; manual 18 R, 1 D, 4 W (no false positives).
Citation (26 R/D): auto 22; manual 23 Y, 1 partly, 2 N. Judge: agrees on all 17 judged clear cases.
