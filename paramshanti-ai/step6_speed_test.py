"""
STEP 6 - make the answers faster.

Part A (LLM):   times several Gemini models on a real question from your books and keeps
                the fastest one that still follows the answer format.
Part B (voice): times Gnani Timbre's streaming for a five-sentence answer: how soon the
                first sound arrives and whether the rest arrives faster than it plays.

Run:   python step6_speed_test.py
It does not use the index, so it can run in a second window while step 3 is building.
"""
import json
import sys
import time

import config
import gnani
import llm
import rag

config.fix_console()
config.need(config.LLM_API_KEY, "LLM_API_KEY")
config.need(config.GNANI_API_KEY, "GNANI_API_KEY")

QUESTION = "I am feeling so angry. What do I do? How do I stay calm?"


def sample_passages() -> list[dict]:
    """Six real paragraphs about anger from your books (read from data\\text, not from the index)."""
    found, spare = [], []
    for path in sorted(config.TEXT_DIR.glob("*.json")):
        book = json.loads(path.read_text(encoding="utf-8"))
        for page in book["pages"]:
            for para in page["paras"]:
                if not 250 <= len(para) <= 1100:
                    continue
                item = {"title": book["title"], "author": rag.author_of(book["title"]),
                        "page": page["page"], "text": para}
                if "anger" in para.lower() or "angry" in para.lower():
                    found.append(item)
                    break
                if len(spare) < 6:
                    spare.append(item)
            if len(found) >= 6:
                return found
    return (found + spare)[:6]          # too few about anger: fill up with other paragraphs


# ------------------------------- Part A: the LLM -------------------------------
print("PART A - which LLM model answers fastest?\n")
passages = sample_passages()
if len(passages) < 2:
    print("Could not find sample paragraphs in data\\text. Run step2_get_books.py first.")
    sys.exit(1)
system, user = rag.build_prompt(QUESTION, [QUESTION], passages, "English")

current = llm.current_model()
if config.LLM_PROVIDER == "openai":
    candidates = [current]
else:
    try:
        names = llm.list_models()
    except Exception as e:
        print(f"Could not list models ({e}). Testing only the current model.")
        names = [current]
    ordered = llm.best_gemini_candidates(names)
    lite = [n for n in ordered if "lite" in n.lower()]
    full = [n for n in ordered if "lite" not in n.lower()]
    candidates = list(dict.fromkeys(lite[:4] + [current] + full[:3]))[:7]

print(f"Current model: {current}")
print(f"Testing: {', '.join(candidates)}\n")

rows = []          # (seconds, model, thinking setting, reply text)
for name in candidates:
    for setting in ("level:minimal", "level:low", "budget:0", ""):
        label = f"{name} [{setting or 'default thinking'}]"
        started = time.perf_counter()
        try:
            raw = llm.chat(system, user, model=name, thinking=setting, timeout=20, attempts=1)
        except llm.LLMError as e:
            message = str(e)
            if "HTTP 400" in message and setting:       # this model does not accept that setting
                continue
            print(f"   {label:58s} failed: {message[:70]}")
            break
        except Exception as e:
            print(f"   {label:58s} failed: {e.__class__.__name__}")
            break
        took = time.perf_counter() - started
        used, text = rag.parse_reply(raw, len(passages))
        good = "ANSWER" in raw.upper() and len(text) >= 60
        print(f"   {label:58s} {took:5.1f}s   {'format ok' if good else 'FORMAT NOT FOLLOWED'}")
        if good:
            rows.append((took, name, setting, text))
        break
    if rows and min(rows)[0] < 2.5:                      # fast enough: stop testing
        break

if rows:
    took, name, setting, text = min(rows)
    llm.MODEL_FILE.write_text(f"{name}|{setting}" if setting else name, encoding="utf-8")
    print(f"\nFASTEST: {name} [{setting or 'default thinking'}] in {took:.1f}s. Saved; the app will use it.")
    print("Its answer, so you can judge the quality:\n")
    print("   " + text.replace("\n", " "))
    if config.LLM_MODEL:
        print("\nNOTE: .env has LLM_MODEL set, which overrides this choice. Remove that line to use it.")
else:
    print("\nNo model gave a usable answer just now. Nothing was changed. Try again in a few minutes.")

# ------------------------------- Part B: the voice -------------------------------
print("\n" + "=" * 78 + "\nPART B - streamed voice (Gnani Timbre): how soon does it start, and does it keep up?\n")
ANSWER = ("When anger arises, do not suppress it, but step back and observe what is happening within "
          "your mind. Recognize that you are the observer of the anger rather than the anger itself. "
          "You can break this old pattern by reminding yourself that you are free and peaceful. "
          "A helpful rule is to not let any negative thought stay longer than five minutes. "
          "By not identifying with the emotion, you will respond to life with greater clarity.")
def stall_seconds(arrivals: list, buffer: float = 1.2) -> float:
    """Pretend a player starts once `buffer` seconds of speech have arrived and plays without
    stopping. Return how long it would sit waiting for sound that has not arrived yet."""
    start_at = next((t for t, got in arrivals if got >= buffer), arrivals[-1][0])
    played, waited, clock = 0.0, 0.0, start_at
    for (t, got), (next_t, _) in zip(arrivals, arrivals[1:]):
        if next_t <= clock:
            continue
        span = next_t - clock                  # time until the next piece arrives
        can_play = max(0.0, got - played)      # speech we hold but have not played yet
        played += min(can_play, span)
        waited += max(0.0, span - can_play)
        clock = next_t
    return waited


RATE = 24000
arrivals = []          # (seconds since the request, seconds of speech received so far)
sound = bytearray()
started = time.perf_counter()
try:
    for piece in gnani.stream_speech(ANSWER, sample_rate=RATE):
        sound.extend(piece)
        arrivals.append((time.perf_counter() - started, len(sound) / (RATE * 2)))
except Exception as e:
    print(f"   streaming failed -> {e}")

if arrivals:
    first, total_time, speech = arrivals[0][0], arrivals[-1][0], arrivals[-1][1]
    print(f"   first sound after : {first:5.1f}s")
    print(f"   all sound after   : {total_time:5.1f}s, for {speech:.1f}s of speech in {len(arrivals)} pieces")
    waited = stall_seconds(arrivals)
    if waited < 0.3:
        print("   verdict           : the sound arrives faster than it plays, so playback is smooth")
    else:
        print(f"   verdict           : the player would pause for about {waited:.1f}s in total while waiting for sound")
    out = config.AUDIO_DIR / "speed_test.wav"
    out.write_bytes(gnani.pcm_to_wav(bytes(sound), RATE))
    print(f"\n   Saved {out} if you want to listen.")

print("\nSTEP 6 DONE. Copy everything above and send it to Claude.")
