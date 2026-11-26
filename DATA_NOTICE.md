# Data notice

`telaah-data-v1.zip` (GitHub Release `data-v1`) holds the text extracted from the public documents below,
the vector index built from it, and the facts table. It exists so the demo can run without downloading and parsing about
1 GB of PDFs. The source PDFs are not redistributed.

- The annual reports and regulations belong to their publishers (the banks, OJK and Bank Indonesia). The extracted text
  is provided for research and evaluation of this project only. Indonesian laws and regulations are not subject to
  copyright (UU 28/2014 art. 42), the annual reports are.
- If you are a rights holder and want a document removed, open an issue in this repository and it will be removed from
  the bundle and from the Release.
- `tests/fixtures/corpus/` in the repository holds a copy of the facts table (figures read from the bank reports above: ratios and totals with their page numbers, no running text) and the text of POJK 11/POJK.03/2016, so the tests run without the download. The same removal request applies.
- The original files can be fetched again from the URLs below with `python corpus/download_corpus.py`.

| doc_id | issuer | title | year | source |
| --- | --- | --- | --- | --- |
| bca_2024 | BCA | Laporan Tahunan 2024 PT Bank Central Asia Tbk | 2024 | https://www.bca.co.id/-/media/Feature/Report/File/S8/Laporan-Tahunan/2025/20250306-BCA-AR-2024-ID.pdf |
| bca_2025 | BCA | Laporan Tahunan 2025 PT Bank Central Asia Tbk | 2025 | https://www.bca.co.id/-/media/Feature/Report/File/S8/Laporan-Tahunan/2026/20260212-BCA-AR-2025-ID.pdf |
| bi_padg_20_2023 | Bank Indonesia | PADG 20 Tahun 2023 tentang Tata Cara Pelaksanaan Pelindungan Konsumen Bank Indonesia | 2023 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PADG_202023.pdf |
| bi_padg_22_2026 | Bank Indonesia | PADG 22 Tahun 2026 tentang Perubahan atas PADG 27 Tahun 2025 (PADG KLM) | 2026 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PADG_222026.pdf |
| bi_padg_23_2025 | Bank Indonesia | PADG 23 Tahun 2025 tentang Rasio Intermediasi Makroprudensial dan Penyangga Likuiditas Makroprudensial bagi Bank Umum | 2025 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PADG_232025.pdf |
| bi_padg_26_2026 | Bank Indonesia | PADG 26 Tahun 2026 tentang perubahan lanjutan atas PADG 27 Tahun 2025 (PADG KLM) | 2026 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PADG-262026.pdf |
| bi_padg_27_2025 | Bank Indonesia | PADG 27 Tahun 2025 tentang Peraturan Pelaksanaan Kebijakan Insentif Likuiditas Makroprudensial | 2025 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PADG_272025.pdf |
| bi_pbi_11_2023 | Bank Indonesia | PBI 11 Tahun 2023 tentang Kebijakan Insentif Likuiditas Makroprudensial | 2023 | https://peraturan.go.id/files/peraturan-bi-no-11-tahun-2023.pdf |
| bi_pbi_2_2026 | Bank Indonesia | PBI 2 Tahun 2026 tentang Perubahan Kelima atas PBI 20/4/PBI/2018 tentang RIM dan PLM | 2026 | https://www.peraturan.go.id/files/peraturan-bi-no-2-tahun-2026.pdf |
| bi_pbi_2_2026__faq | Bank Indonesia | FAQ PBI 2 Tahun 2026 RIM dan PLM | 2026 | https://www.bi.go.id/id/publikasi/peraturan/Documents/FAQ-PBI-022026.pdf |
| bi_pbi_3_2023 | Bank Indonesia | PBI 3 Tahun 2023 tentang Pelindungan Konsumen Bank Indonesia | 2023 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PBI_032023.pdf |
| bi_pbi_3_2023__ringkasan | Bank Indonesia | Ringkasan PBI 3 Tahun 2023 | 2023 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PBI_032023_Ringkasan.pdf |
| bi_pbi_6_2026 | Bank Indonesia | PBI 6 Tahun 2026 tentang Pelindungan Konsumen Bank Indonesia | 2026 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PBI-062026.pdf |
| bi_pbi_6_2026__faq | Bank Indonesia | FAQ PBI 6 Tahun 2026 Pelindungan Konsumen Bank Indonesia | 2026 | https://www.bi.go.id/id/publikasi/peraturan/Documents/FAQ-PBI-062026.pdf |
| bi_pbi_9_2025 | Bank Indonesia | PBI 9 Tahun 2025 tentang Kebijakan Insentif Likuiditas Makroprudensial | 2025 | https://www.bi.go.id/id/publikasi/peraturan/Documents/PBI_092025.pdf |
| bi_pbi_9_2025__faq | Bank Indonesia | FAQ PBI 9 Tahun 2025 KLM | 2025 | https://www.bi.go.id/id/publikasi/peraturan/Documents/FAQ_PBI_092025.pdf |
| bni_2024 | BNI | Laporan Tahunan 2024 PT Bank Negara Indonesia (Persero) Tbk | 2024 | https://www.bni.co.id/Portals/1/BNI/Perusahaan/HubunganInvestor/Docs/AR-BNI-2024-IND.pdf |
| bni_2025 | BNI | Laporan Tahunan 2025 PT Bank Negara Indonesia (Persero) Tbk | 2025 | https://www.bni.co.id/Portals/1/BNI/Perusahaan/HubunganInvestor/Docs/BNI-AR2025-Indonesia.pdf |
| bri_2024 | BRI | Laporan Tahunan 2024 PT Bank Rakyat Indonesia (Persero) Tbk | 2024 | https://ir-bri.com/misc/AR/AR2024-ID.pdf |
| bri_2025 | BRI | Laporan Tahunan 2025 PT Bank Rakyat Indonesia (Persero) Tbk | 2025 | https://ir-bri.com/misc/AR/AR2025-ID.pdf |
| btn_2024 | BTN | Laporan Tahunan 2024 PT Bank Tabungan Negara (Persero) Tbk | 2024 | https://www.btn.co.id/-/media/Files/Laporan-Perusahaan/laporan-tahunan/2024/AR-2024--BBTNIND-Lengkap-040325-LR.pdf |
| btn_2025 | BTN | Laporan Tahunan 2025 PT Bank Tabungan Negara (Persero) Tbk | 2025 | https://www.btn.co.id/-/media/Files/Laporan-Perusahaan/laporan-tahunan/2026/AR-2025-BBTN-IND-Lengkap-290626-HR.pdf |
| mandiri_2024 | Bank Mandiri | Laporan Tahunan 2024 PT Bank Mandiri (Persero) Tbk | 2024 | https://www.bankmandiri.co.id/documents/38265486/0/%5BFINAL+-+2105%5D+LAPORAN+TAHUNAN+BMRI+2024+-+SINGLE+%281%29.pdf/d1f0352d-29f4-ec99-18c6-851feb558801?t=1747897885508 |
| mandiri_2025 | Bank Mandiri | Laporan Tahunan 2025 PT Bank Mandiri (Persero) Tbk | 2025 | https://www.bankmandiri.co.id/documents/38265486/0/%5BFINAL+-+2904%5D+LAPORAN+TAHUNAN+BMRI+2025+%281%29.pdf/426c8cf0-9a2c-ff75-a54b-e7ab87bbbb01?t=1777514291618 |
| ojk_pedoman_ai_perbankan_2025 | OJK | Tata Kelola Kecerdasan Artifisial Perbankan Indonesia | 2025 | https://www.ojk.go.id/id/Publikasi/Roadmap-dan-Pedoman/Perbankan/Documents/Tata%20Kelola%20Kecerdasan%20Artifisial%20Perbankan%20Indonesia.pdf |
| ojk_pojk_11_2016 | OJK | POJK 11/POJK.03/2016 tentang Kewajiban Penyediaan Modal Minimum Bank Umum | 2016 |  |
| ojk_pojk_11_2022 | OJK | POJK 11/POJK.03/2022 tentang Penyelenggaraan Teknologi Informasi oleh Bank Umum | 2022 |  |
| ojk_pojk_17_2023 | OJK | POJK 17 Tahun 2023 tentang Penerapan Tata Kelola bagi Bank Umum | 2023 |  |
| ojk_pojk_17_2023__ringkasan | OJK | Ringkasan POJK 17 Tahun 2023 Tata Kelola Bank Umum | 2023 | https://ojk.go.id/id/regulasi/Documents/Pages/Penerapan-Tata-Kelola-Bagi-Bank-Umum/Ringkasan%20POJK%2017%20Tahun%202023.%20PENERAPAN%20TATA%20KELOLA%20BAGI%20BANK%20UMUM.pdf |
| ojk_pojk_18_2016 | OJK | POJK 18/POJK.03/2016 tentang Penerapan Manajemen Risiko bagi Bank Umum | 2016 |  |
| ojk_pojk_21_2023 | OJK | POJK 21 Tahun 2023 tentang Layanan Digital oleh Bank Umum | 2023 |  |
| ojk_pojk_22_2023 | OJK | POJK 22 Tahun 2023 tentang Pelindungan Konsumen dan Masyarakat di Sektor Jasa Keuangan | 2023 |  |
| ojk_pojk_22_2023__faq | OJK | FAQ POJK 22 Tahun 2023 Pelindungan Konsumen | 2023 | https://ojk.go.id/id/regulasi/Documents/Pages/Pelindungan-Konsumen-dan-Masyarakat-di-Sektor-Jasa-Keuangan/FAQ%20POJK%20Nomor%2022%20Tahun%202023%20PKM%20SJK.pdf |
| ojk_pojk_27_2022 | OJK | POJK 27 Tahun 2022 tentang Perubahan Kedua atas POJK 11/POJK.03/2016 KPMM Bank Umum | 2022 | https://ojk.go.id/id/regulasi/Documents/Pages/Perubahan-Kedua-Atas-Peraturan-Otoritas-Jasa-Keuangan-Nomor-11POJK.032016-Tentang-Kewajiban-Penyediaan-Modal-Minimum-Bank/POJK%2027%20Tahun%202022.%20Tentang%20Kewajiban%20Penyediaan%20Modal%20Minimum%20Bank%20Umum.pdf |
| ojk_pojk_27_2022__ringkasan | OJK | Ringkasan POJK 27 Tahun 2022 KPMM | 2022 | https://ojk.go.id/id/regulasi/Documents/Pages/Perubahan-Kedua-Atas-Peraturan-Otoritas-Jasa-Keuangan-Nomor-11POJK.032016-Tentang-Kewajiban-Penyediaan-Modal-Minimum-Bank/RINGKASAN%20POJK%2027%20Tahun%202022.%20Tentang%20Kewajiban%20Penyediaan%20Modal%20Minimum%20Bank%20Umum.pdf |
| ojk_pojk_34_2016 | OJK | POJK 34/POJK.03/2016 tentang Perubahan atas POJK 11/POJK.03/2016 KPMM Bank Umum | 2016 | https://peraturan.go.id/files/ojk34-2016bt.pdf |
| ojk_pojk_40_2019 | OJK | POJK 40/POJK.03/2019 tentang Penilaian Kualitas Aset Bank Umum | 2019 | https://www.ojk.go.id/id/regulasi/Documents/Pages/Penilaian-Kualitas-Aset-Bank-Umum/pojk%2040-2019.pdf |
| ojk_pojk_40_2019__penjelasan | OJK | Penjelasan POJK 40/POJK.03/2019 Penilaian Kualitas Aset Bank Umum | 2019 | https://peraturan.go.id/files/ojk40-2019pjl.pdf |
| ojk_seojk_14_2025 | OJK | SEOJK 14/SEOJK.03/2025 tentang Penerapan Tata Kelola bagi Bank Umum | 2025 | https://ojk.go.id/id/regulasi/Documents/Pages/SEOJK-14-SEOJK032025-Penerapan-Tata-Kelola-Bagi-Bank-Umum/SEOJK%2014-SEOJK.03.2025%20Penerapan%20Tata%20Kelola%20Bagi%20Bank%20Umum.pdf |
| ojk_seojk_14_2025__faq | OJK | FAQ SEOJK 14/SEOJK.03/2025 Tata Kelola Bank Umum | 2025 | https://ojk.go.id/id/regulasi/Documents/Pages/SEOJK-14-SEOJK032025-Penerapan-Tata-Kelola-Bagi-Bank-Umum/FAQ%20SEOJK%2014-SEOJK.03.2025%20Penerapan%20Tata%20Kelola%20Bagi%20Bank%20Umum.pdf |
| ojk_seojk_26_2016 | OJK | SEOJK 26/SEOJK.03/2016 tentang KPMM sesuai Profil Risiko dan Pemenuhan CEMA | 2016 | https://ojk.go.id/id/regulasi/Documents/Pages/SEOJK-tentang-Kewajiban-Penyediaan-Modal-Minimum-Sesuai-Profil-Risiko-dan-Pemenuhan-Capital-Equivalency-Maintaned-Assets/seojk%2026-2016.pdf |
| ojk_seojk_29_2022 | OJK | SEOJK 29/SEOJK.03/2022 tentang Ketahanan dan Keamanan Siber bagi Bank Umum | 2022 | https://www.ojk.go.id/id/regulasi/Documents/Pages/Ketahanan-dan-Keamanan-Siber-Bagi-Bank-Umum/SEOJK%2029%20SEOJK.03%202022.pdf |
| ojk_seojk_29_2022__ringkasan | OJK | Ringkasan SEOJK 29/SEOJK.03/2022 Ketahanan dan Keamanan Siber | 2022 | https://www.ojk.go.id/id/regulasi/Documents/Pages/Ketahanan-dan-Keamanan-Siber-Bagi-Bank-Umum/RINGKASAN%20SEOJK%2029%20-%2003%20-%202022-1.pdf |
| ojk_seojk_34_2016 | OJK | SEOJK 34/SEOJK.03/2016 tentang Penerapan Manajemen Risiko bagi Bank Umum | 2016 | https://ojk.go.id/id/regulasi/Documents/Pages/Penerapan-Manajemen-Risiko-Bagi-Bank-Umum/SAL%20-%20SEOJK%20MANAJEMEN%20RISIKO%20FINAL%20.pdf |
