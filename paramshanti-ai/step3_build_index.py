"""
STEP 3 - build the searchable index from the text files made in step 2.

What it does:
  1. Cuts every book into passages of about 150 words (a passage never crosses a page,
     so its page number is always exact).
  2. Turns each passage into an "embedding": a list of numbers that captures its meaning.
  3. Stores passage + book title + chapter + page in a local vector database (Chroma).

Run:
   python step3_build_index.py            -> adds books that are not indexed yet
   python step3_build_index.py rebuild    -> wipes the index and builds it again

The first run downloads a small embedding model (about 80 MB), one time only.
"""
import json
import re
import sys
import time

import config
import rag

config.fix_console()

TARGET = 900      # aim for passages of about this many characters (~150 words)
HARD_MAX = 1200   # a single paragraph longer than this gets split by sentences
TOO_SHORT = 100   # shorter leftovers (titles, captions) are not worth indexing


def split_long(para: str) -> list[str]:
    """Split one very long paragraph into sentence groups of about TARGET characters."""
    if len(para) <= HARD_MAX:
        return [para]
    pieces, buf = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", para):
        if buf and len(buf) + len(sentence) + 1 > TARGET:
            pieces.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        pieces.append(buf)
    return pieces


def page_chunks(paras: list[str]) -> list[str]:
    """Join the paragraphs of ONE page into passages of about TARGET characters."""
    chunks, buf = [], ""
    for para in paras:
        for piece in split_long(para):
            if buf and len(buf) + len(piece) + 1 > TARGET:
                chunks.append(buf)
                buf = piece
            else:
                buf = f"{buf}\n{piece}".strip()     # keep paragraph breaks inside a passage
    if buf:
        if chunks and len(buf) < 200:       # tiny tail: attach it to the previous passage
            chunks[-1] = f"{chunks[-1]}\n{buf}"
        else:
            chunks.append(buf)
    return [c for c in chunks if len(c) >= TOO_SHORT]


def main() -> None:
    rebuild = "rebuild" in [a.lower() for a in sys.argv[1:]]
    files = sorted(config.TEXT_DIR.glob("*.json"))
    if not files:
        print("No books found in data\\text. Run  python step2_get_books.py  first.")
        sys.exit(1)

    if rebuild:
        try:
            rag.get_collection()                     # make sure the client exists
            rag._client.delete_collection(config.COLLECTION_NAME)
            print("Old index removed.")
        except Exception as e:
            print(f"(could not remove old index: {e})")
    col = rag.get_collection()

    print(f"{len(files)} book(s) to check. If this is the first run, the embedding model "
          f"(about 80 MB) downloads now; that part can take a few minutes.\n")
    started = time.time()
    added_total = 0
    for n, path in enumerate(files, start=1):
        book = json.loads(path.read_text(encoding="utf-8"))
        book_id = path.stem
        label = f"[{n}/{len(files)}] {book['title']}"
        if col.get(where={"book": book_id}, limit=1)["ids"]:
            print(f"{label} ... already indexed")
            continue

        ids, texts, metas = [], [], []
        for page in book["pages"]:
            for k, chunk in enumerate(page_chunks(page["paras"])):
                ids.append(f"{book_id}:{page['page']}:{k}")
                texts.append(chunk)
                metas.append({"book": book_id, "title": book["title"],
                              "chapter": page.get("chapter", ""), "page": page["page"],
                              "drive_id": book.get("drive_id", "")})
        for i in range(0, len(ids), 100):            # send in batches of 100
            col.add(ids=ids[i:i + 100], documents=texts[i:i + 100], metadatas=metas[i:i + 100])
            print(f"\r{label} ... {min(i + 100, len(ids))}/{len(ids)} passages", end="", flush=True)
        print(f"\r{label} ... {len(ids)} passages indexed" + " " * 12)
        added_total += len(ids)

    titles = [json.loads(p.read_text(encoding="utf-8"))["title"] for p in files]
    summary = {"books": titles, "passages": col.count()}
    rag.LIBRARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nAdded {added_total} passages in {time.time() - started:.0f} seconds.")
    print(f"The index now holds {col.count()} passages from {len(titles)} books.")
    print("\nSTEP 3 PASSED. Next:  python step4_ask.py")


if __name__ == "__main__":
    main()
