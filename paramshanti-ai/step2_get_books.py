"""
STEP 2 - download the books and pull the text out of them, page by page.

Run one of these:
   python step2_get_books.py          -> 8 starter books (takes a minute or two)
   python step2_get_books.py all      -> all 131 English books (run this later)
   python step2_get_books.py karma    -> every book with "karma" in its title

The list of books and their Google Drive IDs is in books.csv.
For each book we save a small text file in data\\text. The PDF itself is deleted
afterwards to save disk space (set KEEP_PDFS=yes in .env to keep the PDFs).

If a download fails, download that PDF by hand from the website, drop it into
data\\pdfs and run this file again: it reads every PDF it finds in that folder.
"""
import csv
import json
import re
import sys
import time
import unicodedata
from collections import Counter

import pymupdf
import requests

import config

config.fix_console()

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def slug(title: str) -> str:
    """A safe file name made from a book title."""
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:80] or "book"


def sniff(first: bytes) -> str:
    """Guess what kind of file we received from its first bytes."""
    head = first[:1024]
    low = head.lower()
    if b"%PDF" in head:
        return "pdf"
    if b"<html" in low or b"<!doctype" in low:
        return "web page"
    if head.startswith(b"ID3") or head[4:8] == b"ftyp" or head.startswith((b"RIFF", b"OggS")) \
            or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio file"
    if head.startswith(b"PK"):
        return "zip/epub file"
    return "unknown file type"


def download(drive_id: str, dest) -> tuple[bool, str]:
    """Download one public Google Drive file. Returns (worked, reason_if_not)."""
    urls = [
        f"https://drive.usercontent.google.com/download?id={drive_id}&export=download&confirm=t",
        f"https://drive.google.com/uc?export=download&confirm=t&id={drive_id}",
    ]
    reason = "unknown problem"
    tmp = dest.with_suffix(".part")
    for url in urls:
        try:
            with requests.get(url, stream=True, timeout=60, headers=BROWSER) as resp:
                if resp.status_code != 200:
                    reason = f"Google answered HTTP {resp.status_code}"
                    continue
                chunks = resp.iter_content(chunk_size=65536)
                first = next(chunks, b"")
                kind = sniff(first)
                if kind == "web page":          # Google showed a page instead of the file
                    reason = "Google showed a web page instead of the file (limit reached or not public)"
                    continue
                if kind != "pdf":               # an audio book etc: nothing to read
                    return False, f"not a PDF ({kind})"
                with open(tmp, "wb") as f:
                    f.write(first)
                    for chunk in chunks:
                        f.write(chunk)
            tmp.replace(dest)
            return True, ""
        except requests.RequestException as e:
            reason = f"network problem: {e.__class__.__name__}"
    if tmp.exists():
        tmp.unlink()
    return False, reason


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)      # joined letters such as "fi" become two normal letters
    text = text.replace("­", "")               # invisible soft hyphens
    text = re.sub(r"-\n(?=[a-z])", "", text)        # words split across two lines
    return re.sub(r"\s+", " ", text).strip()


def mostly_words(text: str) -> bool:
    """False for page numbers, dotted contents lines and other non-sentences."""
    letters = sum(ch.isalpha() for ch in text)
    return len(text) >= 3 and letters / len(text) >= 0.6


def extract(pdf_path, title: str, drive_id: str = "") -> dict | None:
    """Read a PDF and return its paragraphs with the page number of each."""
    doc = pymupdf.open(pdf_path)
    try:
        toc = [(lvl, clean(name), pg) for lvl, name, pg in doc.get_toc(simple=True)]
    except Exception:
        toc = []
    if toc:
        top = min(lvl for lvl, _, _ in toc)
        toc = [(name, pg) for lvl, name, pg in toc if lvl == top and name]

    raw_pages, seen = [], Counter()
    for page in doc:
        paras = [clean(b[4]) for b in page.get_text("blocks") if b[6] == 0]
        paras = [p for p in paras if p]
        raw_pages.append(paras)
        for p in set(paras):
            if len(p) < 80:                           # short lines may be headers/footers
                seen[re.sub(r"\d+", "#", p.lower())] += 1
    page_count = len(raw_pages)
    doc.close()

    # A short line that repeats on many pages is a running header or footer: drop it.
    limit = max(4, page_count // 5)
    repeated = {key for key, n in seen.items() if n >= limit}

    pages, total_chars = [], 0
    for number, paras in enumerate(raw_pages, start=1):
        keep = [p for p in paras
                if mostly_words(p) and re.sub(r"\d+", "#", p.lower()) not in repeated]
        if not keep:
            continue
        chapter = ""
        for name, start in toc:                       # last chapter that starts on or before this page
            if start <= number:
                chapter = name
        pages.append({"page": number, "chapter": chapter, "paras": keep})
        total_chars += sum(len(p) for p in keep)

    if total_chars < 500:                             # scanned images have no text layer
        return None
    return {"title": title, "drive_id": drive_id, "page_count": page_count, "pages": pages}


def process(pdf_path, title: str, drive_id: str) -> str:
    """Extract one PDF and save the result. Returns a short status line."""
    info = extract(pdf_path, title, drive_id)
    if info is None:
        return "NO TEXT (the PDF is probably scanned images)"
    out = config.TEXT_DIR / f"{slug(title)}.json"
    out.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    paras = sum(len(p["paras"]) for p in info["pages"])
    return f"ok: {info['page_count']} pages, {paras} paragraphs"


def main() -> None:
    with open(config.ROOT / "books.csv", encoding="utf-8", newline="") as f:
        catalogue = list(csv.DictReader(f))

    words = [w.lower() for w in sys.argv[1:]]
    if not words:
        chosen = [b for b in catalogue if b["starter"]]
        print(f"Getting the {len(chosen)} starter books. (Use 'all' for all {len(catalogue)}.)\n")
    elif words == ["all"]:
        chosen = catalogue
        print(f"Getting all {len(chosen)} books. This can take a while; you can stop with Ctrl+C "
              f"and run it again later, finished books are skipped.\n")
    else:
        chosen = [b for b in catalogue if all(w in b["title"].lower() for w in words)]
        print(f"{len(chosen)} book(s) match {' '.join(words)!r}.\n")

    ready, problems = 0, []
    for i, book in enumerate(chosen, start=1):
        title, drive_id = book["title"], book["drive_id"]
        name = slug(title)
        label = f"[{i}/{len(chosen)}] {title}"
        if (config.TEXT_DIR / f"{name}.json").exists():
            print(f"{label} ... already done")
            ready += 1
            continue
        pdf_path = config.PDF_DIR / f"{name}.pdf"
        downloaded_now = False
        if not pdf_path.exists():
            ok, why = download(drive_id, pdf_path)
            if not ok:
                print(f"{label} ... SKIPPED: {why}")
                problems.append((title, why))
                continue
            downloaded_now = True
            time.sleep(1)                              # be polite to Google Drive
        size = pdf_path.stat().st_size / 1_048_576
        try:
            status = process(pdf_path, title, drive_id)
        except Exception as e:
            status = f"COULD NOT READ ({e.__class__.__name__}: {e})"
        print(f"{label} ... {size:.1f} MB ... {status}")
        if status.startswith("ok"):
            ready += 1
        else:
            problems.append((title, status))
        if downloaded_now and not config.KEEP_PDFS:
            pdf_path.unlink(missing_ok=True)

    # Any PDF you put into data\pdfs by hand is read too.
    for pdf_path in sorted(config.PDF_DIR.glob("*.pdf")):
        if (config.TEXT_DIR / f"{slug(pdf_path.stem)}.json").exists():
            continue
        title = pdf_path.stem.replace("_", " ").strip()
        try:
            status = process(pdf_path, title, "")
        except Exception as e:
            status = f"COULD NOT READ ({e.__class__.__name__}: {e})"
        print(f"[your own PDF] {title} ... {status}")

    total = len(list(config.TEXT_DIR.glob("*.json")))
    print(f"\nDone. {ready} of {len(chosen)} chosen books are ready. "
          f"Books ready in total: {total} (in {config.TEXT_DIR}).")
    if problems:
        print(f"\n{len(problems)} book(s) were skipped:")
        for title, why in problems:
            print(f"   - {title}: {why}")
        print("\n'not a PDF (audio file)' is normal: some entries on the site are audio books.")
    if total == 0:
        print("\nSTEP 2 FAILED: no book could be read. Copy everything above and send it to Claude.")
        sys.exit(1)
    print("\nSTEP 2 PASSED. Next:  python step3_build_index.py")


if __name__ == "__main__":
    main()
