#!/usr/bin/env python3
"""
Download the Indonesian banking corpus listed in manifest.csv.

Each file is saved as <doc_id>.pdf, so the filename doubles as the doc_id
used in citations (e.g. bri_2025.pdf -> doc_id "bri_2025").

Standard library only - no pip install needed.

Usage:
    python download_corpus.py                      # everything
    python download_corpus.py --check              # verify links only, no full download
    python download_corpus.py --category ojk bi    # regulations only
    python download_corpus.py --lang id            # Indonesian docs only
    python download_corpus.py --skip-aux           # skip FAQ / summary / explanatory files
    python download_corpus.py --with-extras        # also save every other PDF on scraped OJK/BI pages
    python download_corpus.py --only bri_2025 btn_2024

Results go to ./corpus/ and a log to ./corpus/download_log.csv.
"""

import argparse
import csv
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
import ssl

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}
AUX_TYPES = {"faq", "summary", "explanatory"}
MIN_PDF_BYTES = 10_000
CHUNK = 1 << 16

# Words that mark a PDF on an OJK/BI page as the main legal text vs. a side document.
MAIN_HINTS = ("salinan", "pojk", "seojk", "pbi", "padg", "peraturan")
SIDE_HINTS = ("abstrak", "faq", "ringkasan", "summary", "siaran", "sp ", "pers",
              "lampiran", "matriks", "pemetaan", "infografis", "tanya")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def make_ctx(insecure):
    if not insecure:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def safe_url(url):
    """Percent-encode spaces etc. without double-encoding existing escapes."""
    parts = urllib.parse.urlsplit(url.strip())
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~[]")
    query = urllib.parse.quote(parts.query, safe="=&%+/:?-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def open_url(url, ctx, timeout, extra_headers=None):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(safe_url(url), headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def with_retries(fn, tries=3):
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                raise
            last = e
        except Exception as e:  # network hiccups, timeouts
            last = e
        time.sleep(2 * (attempt + 1))
    raise last


def check_pdf(url, ctx, timeout):
    """Fetch only the first bytes and confirm the server returns a PDF."""
    def go():
        with open_url(url, ctx, timeout, {"Range": "bytes=0-1023"}) as r:
            head = r.read(1024)
            size = r.headers.get("Content-Range", "").split("/")[-1] or r.headers.get("Content-Length", "")
            return head, size, r.geturl()
    head, size, final = with_retries(go)
    if not head.startswith(b"%PDF"):
        raise ValueError("response is not a PDF")
    return final, size


def download_pdf(url, dest, ctx, timeout):
    tmp = dest + ".part"
    sha = hashlib.sha256()
    total = 0

    def go():
        nonlocal total
        total = 0
        with open_url(url, ctx, timeout) as r, open(tmp, "wb") as f:
            first = True
            while True:
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                if first:
                    if not chunk.startswith(b"%PDF"):
                        raise ValueError("response is not a PDF")
                    first = False
                f.write(chunk)
                sha.update(chunk)
                total += len(chunk)
            return r.geturl()

    try:
        final = with_retries(go)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    if total < MIN_PDF_BYTES:
        os.remove(tmp)
        raise ValueError(f"file too small ({total} bytes)")
    os.replace(tmp, dest)
    return final, total, sha.hexdigest()


def scrape_pdf_links(page_url, ctx, timeout):
    def go():
        with open_url(page_url, ctx, timeout, {"Accept": "text/html"}) as r:
            return r.read().decode("utf-8", errors="replace"), r.geturl()
    html, final = with_retries(go)
    parser = LinkParser()
    parser.feed(html)
    seen, out = set(), []
    for href in parser.links:
        if not re.search(r"\.pdf($|\?)", href, re.I):
            continue
        absu = urllib.parse.urljoin(final, href)
        if absu not in seen:
            seen.add(absu)
            out.append(absu)
    return out


def score_link(url):
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1]).lower()
    s = sum(2 for h in MAIN_HINTS if h in name)
    s -= sum(5 for h in SIDE_HINTS if h in name)
    return s


def side_slug(url):
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    name = re.sub(r"\.pdf.*$", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="manifest.csv")
    ap.add_argument("--out", default="corpus")
    ap.add_argument("--category", nargs="*", help="annual_report / ojk / bi")
    ap.add_argument("--lang", choices=["id", "en", "all"], default="all")
    ap.add_argument("--only", nargs="*", help="doc_ids to fetch")
    ap.add_argument("--skip-aux", action="store_true", help="skip FAQ/summary/explanatory files")
    ap.add_argument("--with-extras", action="store_true", help="save side PDFs found on scraped pages")
    ap.add_argument("--check", action="store_true", help="validate links without downloading")
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--insecure", action="store_true", help="skip TLS verification (some gov sites)")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    with open(args.manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.category:
        rows = [r for r in rows if r["category"] in args.category]
    if args.lang != "all":
        rows = [r for r in rows if r["lang"] == args.lang]
    if args.only:
        rows = [r for r in rows if r["doc_id"] in args.only]
    if args.skip_aux:
        rows = [r for r in rows if r["doc_type"] not in AUX_TYPES]

    os.makedirs(args.out, exist_ok=True)
    ctx = make_ctx(args.insecure)
    log_path = os.path.join(args.out, "check_log.csv" if args.check else "download_log.csv")
    log = []
    ok = fail = skipped = 0

    for i, r in enumerate(rows, 1):
        doc_id = r["doc_id"]
        dest = os.path.join(args.out, doc_id + ".pdf")
        print(f"[{i}/{len(rows)}] {doc_id}", end=" ... ", flush=True)

        if not args.check and os.path.exists(dest) and not args.force:
            print("exists, skipped")
            skipped += 1
            log.append({"doc_id": doc_id, "status": "skipped_exists", "url": "", "bytes": os.path.getsize(dest), "sha256": "", "error": ""})
            continue

        candidates = [u for u in [r["url"]] + r["fallback_urls"].split("|") if u.strip()]
        landing = [u for u in r["landing_page"].split("|") if u.strip()]
        errors, done = [], False

        # 1) direct URLs
        for u in candidates:
            try:
                if args.check:
                    final, size = check_pdf(u, ctx, args.timeout)
                    log.append({"doc_id": doc_id, "status": "ok", "url": final, "bytes": size, "sha256": "", "error": ""})
                else:
                    final, size, digest = download_pdf(u, dest, ctx, args.timeout)
                    log.append({"doc_id": doc_id, "status": "ok", "url": final, "bytes": size, "sha256": digest, "error": ""})
                print(f"ok ({size} bytes)" if size else "ok")
                done = True
                break
            except Exception as e:
                errors.append(f"{u} -> {e}")
            finally:
                time.sleep(args.delay)

        # 2) scrape the regulator page for the main PDF
        if not done and landing:
            for page in landing:
                try:
                    links = scrape_pdf_links(page, ctx, args.timeout)
                except Exception as e:
                    errors.append(f"{page} -> {e}")
                    continue
                if not links:
                    errors.append(f"{page} -> no PDF links found on page")
                    continue
                links.sort(key=score_link, reverse=True)
                main_link = links[0]
                try:
                    if args.check:
                        final, size = check_pdf(main_link, ctx, args.timeout)
                        log.append({"doc_id": doc_id, "status": "ok_scraped", "url": final, "bytes": size, "sha256": "", "error": ""})
                    else:
                        final, size, digest = download_pdf(main_link, dest, ctx, args.timeout)
                        log.append({"doc_id": doc_id, "status": "ok_scraped", "url": final, "bytes": size, "sha256": digest, "error": ""})
                    print(f"ok via page ({urllib.parse.unquote(main_link.rsplit('/', 1)[-1])})")
                    done = True
                except Exception as e:
                    errors.append(f"{main_link} -> {e}")
                if done and args.with_extras and not args.check:
                    for side in links[1:]:
                        side_dest = os.path.join(args.out, f"{doc_id}__{side_slug(side)}.pdf")
                        if os.path.exists(side_dest) and not args.force:
                            continue
                        try:
                            _, s, d = download_pdf(side, side_dest, ctx, args.timeout)
                            log.append({"doc_id": os.path.basename(side_dest)[:-4], "status": "ok_extra", "url": side, "bytes": s, "sha256": d, "error": ""})
                        except Exception as e:
                            log.append({"doc_id": os.path.basename(side_dest)[:-4], "status": "failed_extra", "url": side, "bytes": "", "sha256": "", "error": str(e)})
                        time.sleep(args.delay)
                if done:
                    break

        if done:
            ok += 1
        else:
            fail += 1
            print("FAILED")
            log.append({"doc_id": doc_id, "status": "failed", "url": "", "bytes": "", "sha256": "", "error": " || ".join(errors)})

    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "status", "url", "bytes", "sha256", "error"])
        w.writeheader()
        w.writerows(log)

    print(f"\nDone: {ok} ok, {skipped} skipped, {fail} failed. Log: {log_path}")
    if fail:
        print("For failures, open the landing_page in manifest.csv, download by hand, and save as <doc_id>.pdf.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
