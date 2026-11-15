"""
STEP 4 - test the search on its own (no AI answer yet, no keys needed).

Type a question; you get the passages whose MEANING is closest, each with its
book and page. If these look relevant, retrieval works.

Run:
   python step4_ask.py
   python step4_ask.py "How do I control my anger?"
"""
import sys
import textwrap

import config
import rag

config.fix_console()


def show(question: str) -> None:
    passages = rag.search(question, k=5)
    if not passages:
        print("The index is empty. Run step2_get_books.py and step3_build_index.py first.")
        return
    print(f"\nQUESTION: {question}\n" + "=" * 78)
    for i, p in enumerate(passages, start=1):
        where = f"{p['title']}, page {p['page']}"
        if p["chapter"]:
            where += f" ({p['chapter']})"
        print(f"\n[{i}] {where}   distance={p['distance']} (smaller is closer)")
        print(textwrap.fill(p["text"], width=78, initial_indent="    ", subsequent_indent="    "))
    print()


if len(sys.argv) > 1:
    show(" ".join(sys.argv[1:]))
else:
    print("Type a question and press Enter. Press Enter on an empty line to stop.")
    while True:
        try:
            q = input("\nYour question: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        show(q)
print("If the passages matched your question, STEP 4 PASSED. Next:  python step5_test_llm.py")
