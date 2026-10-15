"""Parse PDFs with Docling into one markdown chunk per page."""
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

from telaah.config import PROCESSED_DIR, RAW_DIR


def page_chunks(doc_id: str, pages: dict[int, str]) -> list[dict]:
    return [
        {"doc_id": doc_id, "page": p, "text": t.strip()}
        for p, t in sorted(pages.items())
        if t.strip()
    ]


@lru_cache
def converter(threads: int):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Our PDFs are born-digital, so OCR is wasted time; FAST tables keep structure.
    opts = PdfPipelineOptions(
        do_ocr=False,
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.CUDA, num_threads=threads
        ),
    )
    opts.table_structure_options.mode = TableFormerMode.FAST
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def parse_pdf(pdf: Path, threads: int = 4) -> list[dict]:
    t0 = time.time()
    doc = converter(threads).convert(str(pdf)).document
    t1 = time.time()
    pages = export_pages(doc, pdf.stem)
    print(f"  {pdf.stem}: convert {t1 - t0:.0f}s, export {time.time() - t1:.0f}s", flush=True)
    return page_chunks(pdf.stem, pages)


_BREAK = "\x01PAGEBREAK\x01"


def export_pages(doc, name: str) -> dict[int, str]:
    """One markdown string per page.

    Per-page export_to_markdown(page_no=p) rescans the whole document each call, which is
    quadratic on 1000+ page reports. Export once with a page-break marker and split instead;
    fall back to the slow path if the pieces can't be matched to pages with certainty.
    """
    order: list[int] = []  # page of each piece, in document order
    for item, _ in doc.iterate_items():
        prov = getattr(item, "prov", None)
        if prov and (not order or order[-1] != prov[0].page_no):
            order.append(prov[0].page_no)
    parts = doc.export_to_markdown(page_break_placeholder=_BREAK).split(_BREAK)
    if len(parts) == len(order) and len(set(order)) == len(order):
        return dict(zip(order, parts))
    print(f"  {name}: page split not certain, using slow per-page export", flush=True)
    keys = sorted(doc.pages.keys())
    out = {}
    for i, p in enumerate(keys, 1):
        out[p] = doc.export_to_markdown(page_no=p)
        if i % 100 == 0:
            print(f"  {name}: exported {i}/{len(keys)} pages", flush=True)
    return out


def _work(pdf_path: str, threads: int) -> tuple[str, int, float]:
    pdf = Path(pdf_path)
    t0 = time.time()
    chunks = parse_pdf(pdf, threads)
    out = PROCESSED_DIR / f"{pdf.stem}.jsonl"
    tmp = out.with_suffix(".jsonl.part")
    tmp.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")
    tmp.replace(out)  # atomic: a crash never leaves a half-written file that looks done
    return pdf.name, len(chunks), time.time() - t0


def ingest_all(only: list[str] | None = None, no_en: bool = False, workers: int = 1) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for pdf in sorted(RAW_DIR.glob("*.pdf")):
        if only and pdf.stem not in only:
            continue
        if no_en and pdf.stem.endswith("_en"):
            continue
        if (PROCESSED_DIR / f"{pdf.stem}.jsonl").exists():
            continue
        todo.append(pdf)
    # Small files first: regulations finish fast, and the huge annual reports (RAM hogs)
    # never run alongside each other at the end. Re-running skips finished files.
    todo.sort(key=lambda p: p.stat().st_size)

    threads = max(1, (os.cpu_count() or 4) // workers)
    print(f"{len(todo)} files, {workers} worker(s), {threads} threads each", flush=True)
    if workers <= 1:
        results = (_work(str(p), threads) for p in todo)
        for name, n, secs in results:
            print(f"{name}: {n} pages in {secs:.0f}s", flush=True)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_work, str(p), threads) for p in todo]
        for f in as_completed(futs):
            name, n, secs = f.result()
            print(f"{name}: {n} pages in {secs:.0f}s", flush=True)
