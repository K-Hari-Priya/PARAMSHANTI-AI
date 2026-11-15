"""
STEP 5 - test the LLM key, then run one full question end to end in the terminal.

  Part A: asks the model to reply READY. If the model name is wrong for your key,
          it lists the models your key can use, tries them, and remembers one that works.
  Part B: search + LLM for a real question, showing which passages the AI used.

Run:
   python step5_test_llm.py
   python step5_test_llm.py "What is the soul?"
"""
import sys
import textwrap

import config
import llm
import rag

config.fix_console()
config.need(config.LLM_API_KEY, "LLM_API_KEY")


def try_model(name: str) -> bool:
    try:
        reply = llm.chat("You are a test. Follow the instruction exactly.", "Reply with the single word READY.",
                         model=name)
        print(f"OK  model '{name}' replied: {reply[:40]!r}")
        return True
    except llm.LLMError as e:
        print(f"    model '{name}' failed -> {e}")
    except Exception as e:
        print(f"    could not reach the LLM provider -> {e}")
    return False


# ---------------- Part A: find a working model ----------------
print(f"Provider: {config.LLM_PROVIDER}\n")
model = llm.current_model()
if not try_model(model):
    print("\nLooking up the models your key can use...")
    try:
        names = llm.list_models()
    except Exception as e:
        print(f"\nFAIL: could not list models -> {e}\nCopy everything above and send it to Claude.")
        sys.exit(1)
    candidates = llm.best_gemini_candidates(names) if config.LLM_PROVIDER != "openai" else names
    print(f"{len(names)} models found. Trying: {', '.join(candidates[:6]) or '(none suitable)'}\n")
    model = next((c for c in candidates[:6] if try_model(c)), None)
    if model is None:
        print("\nFAIL: no model worked. Copy everything above and send it to Claude.")
        print("All models seen:", ", ".join(names))
        sys.exit(1)
    llm.MODEL_FILE.write_text(model, encoding="utf-8")
    print(f"\nSaved '{model}' as the model to use (in data\\llm_model.txt).")

# ---------------- Part B: one real question ----------------
question = " ".join(sys.argv[1:]) or "How can I stay calm when I feel angry?"
print("\n" + "=" * 78 + f"\nQUESTION: {question}\n")
try:
    result = rag.answer(question)
except Exception as e:
    print(f"FAIL: {e}\nCopy everything above and send it to Claude.")
    sys.exit(1)

if result["found"]:
    print("FROM THE BOOKS (exact text):")
    for q in result["quotes"]:
        print(textwrap.fill(f'"{q["text"]}"', width=78, initial_indent="  ", subsequent_indent="  "))
        print(f"      -- {q['title']}, page {q['page']}\n")
    print("EXPLANATION (written by AI from the passages above):")
else:
    print("NOT FOUND in the indexed books.\n\nGENERAL GUIDANCE (AI, not from the books):")
print(textwrap.fill(result["answer"], width=78, initial_indent="  ", subsequent_indent="  "))
print("\nSTEP 5 PASSED. Next:  streamlit run app.py")
