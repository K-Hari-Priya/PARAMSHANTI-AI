"""
app.py - the PARAMSHANTI AI screen.

Run:   streamlit run app.py      (then your browser opens at http://localhost:8501)

Flow for every question:
   voice --(Gnani Prisma)--> text --> search the books --> LLM explains from the passages
        --> screen shows explanation + exact quotations --(Gnani Timbre, streamed)--> spoken answer
"""
import html
import time

import streamlit as st

import config
import gnani
import look
import rag
import speech

ICON = config.ROOT / "static" / "light.png"       # the point of light, shown on the browser tab
st.set_page_config(page_title="PARAMSHANTI AI", page_icon=str(ICON) if ICON.exists() else "🕊️",
                   layout="centered", initial_sidebar_state="collapsed")
st.html(look.CSS)                  # the night sky, the point of light, the paper pages: see look.py

TAGLINE = "Ask by voice or text. Every answer shows the exact passage, the book and the page."
WELCOME = "Ask any question that is on your mind, aloud or in writing, in your own language."
EVERY_ANSWER = "Every answer shows the exact passage, the book and the page."
ABOUT = ("A study and reflection aid. It quotes books that present the teachings of "
         "Bapuji Dashrathbhai Patel. It does not speak for him and does not replace "
         "professional advice.")


VOICES = {                         # Gnani Timbre v3.0 voices (each speaks English and Hindi)
    "Shivani": "warm, patient", "Chetana": "gentle", "Tarika": "warm, reassuring",
    "Lakshmi": "expressive, warm", "Vasudha": "expressive, composed", "Kalpana": "composed",
    "Riyaa": "lively", "Yashraj": "male · warm, narrative", "Prakash": "male · steady",
    "Avinash": "male · firm", "Harshad": "male · firm", "Shubham": "male · energetic",
    "Devansh": "male · young, conversational",
}

PLAY_NOW = """
<script>
(function () {
  var tries = 0;
  var timer = setInterval(function () {
    var players = Array.prototype.slice.call(document.querySelectorAll("audio"));
    var player = players.filter(function (p) { return (p.currentSrc || p.src || "").indexOf("/speech/JOB_ID") >= 0; })[0];
    if (player && player.paused && !player.ended && player.currentTime === 0) {
      player.play().catch(function () {});
    }
    if ((player && !player.paused) || ++tries > 100) { clearInterval(timer); }
  }, 150);
})();
</script>
"""

# While the voice is speaking, the point of light pulses with it. This script only watches the
# audio player and marks the page as "speaking" or not; the pulse itself is in look.py.
LIGHT_FOLLOWS_VOICE = """
<script>
(function () {
  if (window.__psVoiceLight) { return; }
  window.__psVoiceLight = setInterval(function () {
    var player = document.querySelector("audio");
    var speaking = !!player && !player.paused && !player.ended && player.currentTime > 0;
    document.body.classList.toggle("ps-speaking", speaking);
  }, 250);
})();
</script>
"""

# A new answer is read from its beginning: this brings the page back to the top once.
SHOW_FROM_TOP = """
<script>
(function () {
  var node = document.querySelector(".ps-hero");
  while (node && node !== document.body) {              // find the part of the page that scrolls
    var how = getComputedStyle(node).overflowY;
    if ((how === "auto" || how === "scroll") && node.scrollHeight > node.clientHeight) { break; }
    node = node.parentElement;
  }
  if (node && node !== document.body && node.scrollTop > 0) { node.scrollTo({top: 0, behavior: "smooth"}); }
})();
</script>
"""


def tidy(text: str) -> str:
    """Join lines that belong to one sentence; keep real paragraph breaks and headings."""
    out = ""
    for line in (part.strip() for part in text.split("\n")):
        if not line:
            continue
        if not out:
            out = line
        elif out[-1] in '.!?:"”’)' and not line[0].islower():
            out += "\n" + line                  # the previous paragraph ended
        elif len(out.split("\n")[-1]) < 70 and line[0].isupper():
            out += "\n" + line                  # a short line with no full stop is a heading
        else:
            out += " " + line                   # the same sentence continues
    return out


def as_quote(text: str) -> str:
    """The stored passage, unchanged, with '…' where it starts or stops in mid-sentence."""
    t = tidy(text)
    if t and t[0].islower():
        t = "… " + t
    if t and t[-1] not in '.!?"”’)':
        t += " …"
    return t


def quote_card(p: dict) -> None:
    """Show one passage exactly as it is stored, as a page of its book: the book's name and
    chapter on top, the words, then the page number."""
    chapter = p.get("chapter") or ""
    if config.SHOW_AUTHORS and p.get("author"):
        chapter = f"{p['author']}, {chapter}" if chapter else p["author"]
    link = f"https://drive.google.com/file/d/{p['drive_id']}/view" if p.get("drive_id") else ""
    st.markdown(look.page(p["title"], chapter, as_quote(p["text"]).split("\n"), p["page"], link),
                unsafe_allow_html=True)


# ---------------- the language ----------------
# The language is chosen on the welcome screen. After that the same choice sits in the row
# at the top. Both write to st.session_state["language"].
LANGUAGES = list(rag.LANGS)


def choose_language(key: str) -> None:
    if st.session_state.get(key) in rag.LANGS:
        st.session_state["language"] = st.session_state[key]


language = st.session_state.setdefault("language", "English")

# ---------------- the welcome screen ----------------
# The app opens here: what it is, then the choice of language. Choosing one opens the
# screen where questions are asked.
def enter(name: str) -> None:
    st.session_state["language"] = name
    st.session_state["entered"] = True


stats = rag.library_stats()
books = f"{len(stats['books']):,} books that present the teachings of Bapuji Dashrathbhai Patel"
if not st.session_state.get("entered"):
    with st.container(key="welcome"):
        st.markdown(look.hero(False, WELCOME, f"Answers come from {books}. {EVERY_ANSWER}"),
                    unsafe_allow_html=True)
        st.markdown('<p class="ps-choose">Choose your language</p>', unsafe_allow_html=True)
        with st.container(horizontal=True, horizontal_alignment="center", key="languages"):
            for name in LANGUAGES:
                st.button(rag.LANGS[name]["label"], key=f"language_{name}", on_click=enter, args=(name,))
    st.stop()

# ---------------- asking: example questions and the question box ----------------
def pick(example: str) -> None:
    """An example question was tapped: remember it for the run that follows."""
    st.session_state["picked"] = example


def example_questions() -> None:
    """The example questions as a row of buttons."""
    with st.container(horizontal=True, horizontal_alignment="center", key="examples"):
        for number, example in enumerate(rag.LANGS[language]['examples']):
            st.button(example, key=f"example_{number}", on_click=pick, args=(example,))


# The question box stays at the bottom of the window. On the start screen the example
# questions sit just above it; once there is an answer they move to the end of the answer,
# so the answer has more room.
# (The box is created inside st.bottom on purpose. Left on its own, Streamlit treats a page
# with a question box as a chat and jumps to the end of the page whenever something new
# appears; here a new answer should be read from its beginning.)
with st.bottom:
    examples_slot = st.empty()
    sent = st.chat_input(rag.LANGS[language]['placeholder'], accept_audio=True, audio_sample_rate=16000)
question = st.session_state.pop("picked", None)
heard, listen_seconds = False, 0.0
if question or sent is not None:
    examples_slot.empty()          # a question is on its way: the examples step aside

started = bool(question or sent is not None or st.session_state.get("result"))

# ---------------- settings: a quiet row at the top ----------------
with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                  key="settings"):
    st.selectbox("Language", LANGUAGES, index=LANGUAGES.index(language), key="language_bar",
                 format_func=lambda name: rag.LANGS[name]["label"], label_visibility="collapsed",
                 on_change=choose_language, args=("language_bar",))
    speak = st.toggle("Read aloud", value=True)
    voice = config.TTS_VOICE
    if config.TTS_MODEL == "timbre-v3.0":          # the voice list below belongs to this model
        names = list(VOICES)
        with st.popover("Voice", icon=":material/record_voice_over:"):
            voice = st.selectbox("Voice (Gnani Timbre)", names,
                                 index=names.index(config.TTS_VOICE) if config.TTS_VOICE in names else 0,
                                 format_func=lambda name: f"{name}, {VOICES[name].replace(' · ', ', ')}")

# ---------------- sidebar: the library and how it works ----------------
with st.sidebar:
    st.markdown("### Library")
    left, right = st.columns(2)
    left.metric("Books", len(stats["books"]))
    right.metric("Passages", stats["passages"])
    with st.expander("Books in this library"):
        for title in stats["books"]:
            st.write("• " + title)
    st.divider()
    st.markdown(
        "**How it works**\n"
        "1. **Gnani Prisma** turns your voice into text\n"
        "2. The books are searched by meaning\n"
        "3. An LLM explains, using only the passages found\n"
        "4. **Gnani Timbre** reads the answer aloud"
    )
    st.caption(ABOUT)

# ---------------- the point of light and the title ----------------
answering = started
st.markdown(look.hero(answering, TAGLINE, f"Answers come from {books}."), unsafe_allow_html=True)

if not config.GNANI_API_KEY or not config.LLM_API_KEY:
    st.error("A key is missing. Open the .env file, paste GNANI_API_KEY and LLM_API_KEY, save, "
             "then stop the app (Ctrl+C) and start it again.")
    st.stop()
if stats["passages"] == 0:
    st.error("No books are indexed yet. Run step2_get_books.py and step3_build_index.py first.")
    st.stop()

@st.cache_resource(show_spinner="Getting the library ready...")
def warm_up() -> bool:
    """Run one search when the app starts: this loads the search model, so the first real
    question is as fast as the later ones."""
    rag.search("peace of mind", k=1)
    return True


warm_up()

# ---------------- what was asked ----------------
if question or sent is not None:
    speech.stop_all()              # a new question stops the voice of the previous answer
if sent is not None:
    if sent.audio is not None:                       # a voice question: Gnani Prisma -> text
        with st.spinner("Listening with Gnani Prisma..."):
            try:
                clock = time.perf_counter()
                question = gnani.speech_to_text(sent.audio.getvalue(),
                                                language=rag.LANGS[language]["stt"])
                listen_seconds = time.perf_counter() - clock
                heard = True
            except Exception as e:
                st.error(f"Speech-to-text failed: {e}")
        if heard and not question:
            st.warning("I could not hear any words. Please try again, a little closer to the microphone.")
    elif sent.text.strip():
        question = sent.text.strip()

# ---------------- answer ----------------
spinner_area = st.container()      # "searching..." appears here
answer_area = st.empty()           # the whole answer lives here, so a new question clears the old one

if question:
    answer_area.empty()            # remove the previous answer straight away
    result, problem = None, ""
    with spinner_area:
        with st.spinner("Searching the books and writing the explanation..."):
            try:
                result = rag.answer(question, language)
            except Exception as e:
                problem = str(e)
        if problem:
            st.error(f"Could not answer: {problem}")
    if result:
        result["heard"] = heard
        result["seconds"]["listen"] = listen_seconds
        result["audio_error"] = ""
        st.session_state["result"] = result
        st.session_state["voice_pending"] = bool(speak and result["spoken"])
        st.session_state["new_answer"] = True

# ---------------- show the latest answer ----------------
r = st.session_state.get("result")
if r:
    with answer_area.container():
        asked = "You asked (heard by Gnani Prisma)" if r.get("heard") else "You asked"
        st.markdown(f'<div class="ps-asked-by">{asked}</div>'
                    f'<div class="ps-asked">{html.escape(r["question"])}</div>', unsafe_allow_html=True)
        if r.get("search_query") and r["search_query"] != r["question"]:
            st.caption(f"Searched the books for: {r['search_query']}")

        audio_slot = st.empty()                      # the voice player appears here when it is ready

        if r["found"]:
            st.markdown('<div class="ps-h">Explanation<span class="ps-note">Written by AI from the '
                        'passages below. It is not text from the books.</span></div>',
                        unsafe_allow_html=True)
            with st.container(key="explanation"):
                st.write(r["answer"])
            original = " (original English)" if r.get("language") != "English" else ""
            st.markdown('<div class="ps-ornament" aria-hidden="true">·✶·</div>'
                        f'<div class="ps-h">From the books, word for word{original}</div>',
                        unsafe_allow_html=True)
            for passage in r["quotes"]:
                quote_card(passage)
        else:
            st.info("I could not find a passage about this in the books I have, "
                    "so nothing below comes from the books.")
            st.markdown('<div class="ps-h">General guidance<span class="ps-note">Written by AI. '
                        'This is not from the books.</span></div>', unsafe_allow_html=True)
            with st.container(key="explanation"):
                st.write(r["answer"])

        timing_slot = st.empty()

        with st.expander("All passages that were searched for this question"):
            for i, passage in enumerate(r["passages"], start=1):
                st.markdown(f"**{i}. {passage['title']}, page {passage['page']}** "
                            f"(distance {passage['distance']})")
                st.write(tidy(passage["text"]))
        st.markdown('<div class="ps-h ps-h--middle">Ask something else</div>', unsafe_allow_html=True)
        example_questions()
        st.markdown(f'<p class="ps-foot">{ABOUT}</p>', unsafe_allow_html=True)

    # The sky takes its colour from the subject of the question (see look.sky_for).
    st.html(look.sky_css(look.sky_for(f"{r['question']} {r.get('search_query', '')}")))
    if st.session_state.pop("new_answer", False):
        st.html(SHOW_FROM_TOP, unsafe_allow_javascript=True)

    def show_timing() -> None:
        """How this answer was made: each step, who did it, and how long it took."""
        took = r.get("seconds", {})
        stages = [("Question heard", "Gnani Prisma", "listen"), ("Question prepared", "", "translate"),
                  ("Books searched", "", "search"), ("Explanation written", "", "explain"),
                  ("Voice began", "Gnani Timbre", "voice")]
        shown = [(what, who, took[key]) for what, who, key in stages if took.get(key, 0) >= 0.05]
        if shown:
            timing_slot.markdown('<div class="ps-h">How this answer was made</div>' + look.steps(shown),
                                 unsafe_allow_html=True)

    # The text above is already on screen. Now the voice, once per answer. Gnani Timbre streams
    # the sound, and speech.py passes it to the player piece by piece, so it starts playing
    # after a second or two while the rest is still being voiced.
    if st.session_state.pop("voice_pending", False):
        show_timing()
        code = rag.LANGS[r["language"]]["tts"]
        how = rag.voice_for(r["language"])           # which Timbre model speaks this language
        try:
            if how is None:
                raise RuntimeError("no voice")
            job = speech.say(r["spoken"], code, how.get("voice") or voice, how.get("model"))
            with audio_slot:
                with st.spinner("Preparing the voice with Gnani Timbre..."):
                    has_sound = job.wait_ready()
            if has_sound:
                r["voice_id"] = job.id
                r["seconds"]["voice"] = job.first_sound_after or 0.0
                audio_slot.audio(speech.url(job), format="audio/wav", autoplay=True)
                # A browser's own "autoplay" waits for the whole download. This small script
                # presses play as soon as the first sound has arrived.
                st.html(PLAY_NOW.replace("JOB_ID", job.id), unsafe_allow_javascript=True)
            else:
                r["audio_error"] = job.error or "no sound arrived in time"
        except Exception as e:
            r["audio_error"] = str(e)
        if r.get("audio_error") and r["language"] not in ("English", "Hindi"):
            reason = "" if r["audio_error"] == "no voice" else f" ({r['audio_error']})"
            r["audio_error"] = f"Gnani Timbre does not read {r['language']} aloud yet, so this answer is shown as text.{reason}"
            audio_slot.info(r["audio_error"])
        elif r.get("audio_error"):
            audio_slot.warning(f"The voice could not be prepared: {r['audio_error']}")
        show_timing()
    else:
        if r.get("voice_id") and speech.get(r["voice_id"]):
            audio_slot.audio(speech.url(r["voice_id"]), format="audio/wav")
        elif r.get("audio_error") and r["language"] not in ("English", "Hindi"):
            audio_slot.info(r["audio_error"])
        elif r.get("audio_error"):
            audio_slot.warning(f"The voice could not be prepared: {r['audio_error']}")
        show_timing()

if not r:                          # the start screen: the examples sit just above the question box
    with examples_slot:
        example_questions()

st.html(LIGHT_FOLLOWS_VOICE, unsafe_allow_javascript=True)
