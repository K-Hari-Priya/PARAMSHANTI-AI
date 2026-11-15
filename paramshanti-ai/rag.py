"""
rag.py - "Retrieval-Augmented Generation" in three small functions.

   get_collection()   opens the searchable index of book passages
   search(question)   finds the passages closest in MEANING to the question
   answer(question)   asks the LLM to explain, using ONLY those passages

The golden rule of this project lives here: a quotation shown to the user is
always a passage copied from the index, never text written by the LLM.
"""
import csv
import json
import re
import time

import chromadb

import config
import llm

_client = None
LIBRARY_FILE = config.DATA / "library.json"

# ---------------------------------------------------------------------------
# Who wrote which book. Every book in the library presents the teachings of
# Bapuji Dashrathbhai Patel, and that is how the app describes them. A few titles
# carry another author's name on the cover; authors.csv lists those. The names are
# only printed if you set SHOW_AUTHORS=yes in .env (off by default).
# ---------------------------------------------------------------------------
AUTHORS_FILE = config.ROOT / "authors.csv"
DEFAULT_AUTHOR = "Bapuji Dashrathbhai Patel"
_authors = None


def title_key(title: str) -> str:
    """Compare titles without being fooled by dashes, apostrophes or capitals."""
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def other_authors() -> dict:
    """The contents of authors.csv as {title key: author}."""
    global _authors
    if _authors is None:
        _authors = {}
        if AUTHORS_FILE.exists():
            with open(AUTHORS_FILE, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    title, author = (row.get("title") or "").strip(), (row.get("author") or "").strip()
                    if title and author:
                        _authors[title_key(title)] = author
    return _authors


def author_of(title: str) -> str:
    return other_authors().get(title_key(title), DEFAULT_AUTHOR)


# Everything that changes with the language the user picks.
#   stt / tts : language codes for Gnani Prisma and Gnani Timbre
#   style     : how the LLM should write the explanation
#   not_found : spoken before a general answer, so a listener knows it is not from the books
LANGS = {
    "English": {
        "label": "English", "stt": "en-IN", "tts": "en-IN",
        "style": "simple, warm English",
        "not_found": "I could not find this in the books I have. Here is some general guidance. ",
        "placeholder": "Type your question, or press the microphone and speak",
        "examples": ["How do I control anger?", "What happens after death?", "How do I stop overthinking?"],
    },
    "Hindi": {
        "label": "हिंदी", "stt": "hi-IN", "tts": "hi-IN",
        "style": ("simple, warm, everyday Hindi, entirely in Devanagari script. Write the books' own "
                  "terms in Devanagari too (for example आत्मा, मन, बुद्धि, साक्षी भाव, पुरुषार्थ, परमशांति)"),
        "not_found": "मुझे यह बात इन पुस्तकों में नहीं मिली। यह एक सामान्य सुझाव है। ",
        "placeholder": "अपना प्रश्न लिखें, या माइक दबाकर बोलें (Hindi or Hinglish)",
        "examples": ["गुस्से में शांत कैसे रहें?", "मृत्यु के बाद क्या होता है?", "ज़्यादा सोचना कैसे रोकें?"],
    },
    "Bengali": {
        "label": "বাংলা", "stt": "bn-IN", "tts": "bn-IN",
        "style": "simple, warm, everyday Bengali, entirely in Bengali script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "এই বিষয়টি আমি এই বইগুলিতে পাইনি। এটি একটি সাধারণ পরামর্শ। ",
        "placeholder": "আপনার প্রশ্ন লিখুন, অথবা মাইক টিপে বলুন",
        "examples": ["রাগ কীভাবে নিয়ন্ত্রণ করব?", "মৃত্যুর পরে কী হয়?", "অতিরিক্ত চিন্তা কীভাবে থামাব?"],
    },
    "Gujarati": {
        "label": "ગુજરાતી", "stt": "gu-IN", "tts": "gu-IN",
        "style": "simple, warm, everyday Gujarati, entirely in Gujarati script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "આ વાત મને આ પુસ્તકોમાં મળી નથી. આ એક સામાન્ય સૂચન છે. ",
        "placeholder": "તમારો પ્રશ્ન લખો, અથવા માઇક દબાવીને બોલો",
        "examples": ["ગુસ્સા પર કાબૂ કેવી રીતે રાખવો?", "મૃત્યુ પછી શું થાય છે?", "વધારે વિચારવાનું કેવી રીતે બંધ કરવું?"],
    },
    "Marathi": {
        "label": "मराठी", "stt": "mr-IN", "tts": "mr-IN",
        "style": "simple, warm, everyday Marathi, entirely in Devanagari script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "ही गोष्ट मला या पुस्तकांमध्ये सापडली नाही. ही एक सामान्य सूचना आहे. ",
        "placeholder": "तुमचा प्रश्न लिहा, किंवा माइक दाबून बोला",
        "examples": ["रागावर नियंत्रण कसे ठेवावे?", "मृत्यूनंतर काय होते?", "जास्त विचार करणे कसे थांबवावे?"],
    },
    "Punjabi": {
        "label": "ਪੰਜਾਬੀ", "stt": "pa-IN", "tts": "pa-IN",
        "style": "simple, warm, everyday Punjabi, entirely in Gurmukhi script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "ਇਹ ਗੱਲ ਮੈਨੂੰ ਇਨ੍ਹਾਂ ਕਿਤਾਬਾਂ ਵਿੱਚ ਨਹੀਂ ਮਿਲੀ। ਇਹ ਇੱਕ ਆਮ ਸੁਝਾਅ ਹੈ। ",
        "placeholder": "ਆਪਣਾ ਸਵਾਲ ਲਿਖੋ, ਜਾਂ ਮਾਈਕ ਦਬਾ ਕੇ ਬੋਲੋ",
        "examples": ["ਗੁੱਸੇ 'ਤੇ ਕਾਬੂ ਕਿਵੇਂ ਪਾਈਏ?", "ਮੌਤ ਤੋਂ ਬਾਅਦ ਕੀ ਹੁੰਦਾ ਹੈ?", "ਜ਼ਿਆਦਾ ਸੋਚਣਾ ਕਿਵੇਂ ਬੰਦ ਕਰੀਏ?"],
    },
    "Tamil": {
        "label": "தமிழ்", "stt": "ta-IN", "tts": "ta-IN",
        "style": "simple, warm, everyday Tamil, entirely in Tamil script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "இந்த விஷயம் இந்தப் புத்தகங்களில் எனக்குக் கிடைக்கவில்லை. இது ஒரு பொதுவான ஆலோசனை. ",
        "placeholder": "உங்கள் கேள்வியை எழுதுங்கள், அல்லது மைக்கை அழுத்தி பேசுங்கள்",
        "examples": ["கோபத்தை எப்படி கட்டுப்படுத்துவது?", "இறப்புக்குப் பிறகு என்ன நடக்கிறது?", "அதிகமாக யோசிப்பதை எப்படி நிறுத்துவது?"],
    },
    "Telugu": {
        "label": "తెలుగు", "stt": "te-IN", "tts": "te-IN",
        "style": "simple, warm, everyday Telugu, entirely in Telugu script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "ఈ విషయం నాకు ఈ పుస్తకాలలో దొరకలేదు. ఇది ఒక సాధారణ సూచన. ",
        "placeholder": "మీ ప్రశ్నను రాయండి, లేదా మైక్ నొక్కి మాట్లాడండి",
        "examples": ["కోపాన్ని ఎలా నియంత్రించాలి?", "మరణం తర్వాత ఏమి జరుగుతుంది?", "అతిగా ఆలోచించడం ఎలా ఆపాలి?"],
    },
    "Kannada": {
        "label": "ಕನ್ನಡ", "stt": "kn-IN", "tts": "kn-IN",
        "style": "simple, warm, everyday Kannada, entirely in Kannada script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "ಈ ವಿಷಯ ನನಗೆ ಈ ಪುಸ್ತಕಗಳಲ್ಲಿ ಸಿಗಲಿಲ್ಲ. ಇದು ಒಂದು ಸಾಮಾನ್ಯ ಸಲಹೆ. ",
        "placeholder": "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಬರೆಯಿರಿ, ಅಥವಾ ಮೈಕ್ ಒತ್ತಿ ಮಾತನಾಡಿ",
        "examples": ["ಕೋಪವನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?", "ಸಾವಿನ ನಂತರ ಏನಾಗುತ್ತದೆ?", "ಅತಿಯಾಗಿ ಯೋಚಿಸುವುದನ್ನು ಹೇಗೆ ನಿಲ್ಲಿಸುವುದು?"],
    },
    "Malayalam": {
        "label": "മലയാളം", "stt": "ml-IN", "tts": "ml-IN",
        "style": "simple, warm, everyday Malayalam, entirely in Malayalam script, with no English words (also translate 'the teachings' and 'the books')",
        "not_found": "ഈ വിഷയം എനിക്ക് ഈ പുസ്തകങ്ങളിൽ കണ്ടെത്താനായില്ല. ഇത് ഒരു പൊതുവായ നിർദ്ദേശമാണ്. ",
        "placeholder": "നിങ്ങളുടെ ചോദ്യം എഴുതുക, അല്ലെങ്കിൽ മൈക്ക് അമർത്തി സംസാരിക്കുക",
        "examples": ["കോപം എങ്ങനെ നിയന്ത്രിക്കാം?", "മരണശേഷം എന്ത് സംഭവിക്കുന്നു?", "അമിതമായ ചിന്ത എങ്ങനെ നിർത്താം?"],
    },
}
VOICES_FILE = config.DATA / "voices.json"      # written by step7_test_languages.py


def voice_for(language: str) -> dict | None:
    """How to voice this language: {} = the usual model and the chosen voice,
    {"model": ..., "voice": ...} = another Timbre model speaks it, None = no voice for it.
    Before step7_test_languages.py has been run, every language is simply tried."""
    if language in ("English", "Hindi"):           # always the usual model and the chosen voice
        return {}
    try:
        found = json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return found.get(LANGS[language]["tts"], {})


def get_collection():
    """Open (or create) the vector database stored in data\\chroma."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    # No embedding function is named, so Chroma uses its default one
    # (the small "all-MiniLM-L6-v2" model, which runs on your laptop for free).
    return _client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
    )


def library_stats() -> dict:
    """How many books and passages are indexed (written by step 3)."""
    if LIBRARY_FILE.exists():
        return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    return {"books": [], "passages": 0}


def _same_text_key(text: str) -> str:
    """Two passages with the same opening words count as the same passage."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:160]


def search(question: str, k: int = config.TOP_K) -> list[dict]:
    """Return the k passages whose meaning is closest to the question.

    Many books contain the same page (for example "About Bapuji"), so repeats are skipped.
    """
    col = get_collection()
    total = col.count()
    if total == 0:
        return []
    res = col.query(query_texts=[question], n_results=min(k * 4, total))
    seen, passages = set(), []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        key = _same_text_key(text)
        if key in seen:
            continue
        seen.add(key)
        title = meta.get("title", "")
        passages.append({
            "text": text,
            "title": title,
            "author": author_of(title),
            "chapter": meta.get("chapter", ""),
            "page": meta.get("page", ""),
            "drive_id": meta.get("drive_id", ""),
            "distance": round(float(dist), 3),      # smaller = closer in meaning
        })
        if len(passages) == k:
            break
    return passages


def search_many(queries: list[str]) -> list[dict]:
    """Search once per query and mix the results, so every part of the question gets passages."""
    if len(queries) == 1:
        return search(queries[0])
    found = [search(q, k=3) for q in queries]
    mixed, seen = [], set()
    for rank in range(3):                       # best passage of each query first, then second best...
        for passages in found:
            if rank < len(passages) and len(mixed) < 12:
                key = _same_text_key(passages[rank]["text"])
                if key not in seen:
                    seen.add(key)
                    mixed.append(passages[rank])
    return mixed


PLAN_PROMPT = """You prepare search queries for a library of English books that present the teachings
of Bapuji Dashrathbhai Patel. Rewrite the person's question as short, standalone English search
queries, one per line, at most 6 lines.
- One query for each separate thing the person asks about. A single question gives a single line.
- The question may be in any Indian language, in its own script or typed with English letters, or mixed
  with English. Write the queries in English.
- Keep the meaning exactly. Do not add a name, a topic or any word the person did not say.
- Only if the person names Bapuji: write the name as "Bapuji" (one word), however they spelled it.
- No numbering, no bullets, no explanations."""


def plan_queries(question: str) -> list[str]:
    """Turn the question into the search queries to run.

    A plain single English question is searched as it is (no LLM call, so it stays fast).
    A Hindi/Hinglish question, or one that asks several things at once, goes to the LLM first:
    it is translated and split, so each part gets its own search.
    """
    if not (needs_translation(question) or asks_several_things(question)):
        return [question]
    reply = llm.chat(PLAN_PROMPT, question, temperature=0.0)    # 0 = the same split every time
    lines = [re.sub(r"^[\s\-\*\u2022\d\.\)]+", "", line).strip().strip('"') for line in reply.splitlines()]
    lines = [line for line in lines if len(line) > 2][:6]
    return lines or [question]


def asks_several_things(question: str) -> bool:
    """True for questions like 'Who is X? What is Y? And why Z?'"""
    marks = question.count("?")
    words = re.findall(r"[a-z']+", question.lower())
    askers = sum(w in ("who", "what", "why", "when", "where", "which", "how") for w in words)
    return marks >= 3 or (marks >= 2 and len(words) >= 16) or askers >= 3


# Very common English words, and words that only appear in Hindi typed with English letters.
_ENGLISH = set("""a about after am an and are be because can could did do does feel feeling for from get
have how i if in is it me my of on or should so stay stop that the this to was what when where which
who why will with would you your""".split())
_HINGLISH = set("""kya hai hain kaise kaisa kaisi kyu kyun kyon ka ki ke ko mein nahi nahin aur kab kahan
kaun kis tha thi hota hoti hote hona hoga hogi karna kare karu karun karein karo raha rahi rahe mujhe
mera meri mere tum aap yeh woh bhi toh agar lekin kyunki chahiye sakta sakti sakte batao bataye
bataiye batayein samjhao samjhaiye matlab kuch bahut jab liye hoon hun gaya gayi kitna kitni apna
apni apne hamara unka iska uska phir abhi kabhi sab koi kisi wala wali kijiye dijiye""".split())


def needs_translation(question: str) -> bool:
    """True when the question is not plain English (Hindi script, or Hindi in English letters).

    Plain English questions skip the translation step, which saves one LLM call and a few seconds.
    """
    if re.search(r"[\u0900-\u0D7F]", question):      # any letter of an Indian script
        return True
    words = re.findall(r"[a-z']+", question.lower())
    if len(words) < 2:
        return False
    hindi = sum(w in _HINGLISH for w in words)
    english = sum(w in _ENGLISH for w in words) / len(words)
    return hindi >= 2 or (hindi >= 1 and english < 0.3) or english == 0


SYSTEM_PROMPT = """You are PARAMSHANTI AI, a study assistant for the Paramshanti library: books that present
the teachings of Bapuji Dashrathbhai Patel. You receive a QUESTION and numbered PASSAGES copied word
for word from those books.

Rules you must follow:
1. Decide which passages really help to answer the question. Some or all may be irrelevant.
2. If at least one passage helps: explain the answer using only what those passages say. Match
   the length to the question: when the person shares a personal difficulty or asks how to do
   something, write 4 or 5 warm, practical sentences; for a simple factual question 2 or 3
   sentences are enough. If the question has several parts, answer each part in one or two
   sentences, in the same order, and say in a few words which parts the passages do not cover.
   Every sentence you write must be supported by the passages: do not add teachings, advice,
   claims or quotations that are not in them. Never invent a book name or page number.
3. If no passage helps: write USED: NONE. Then give 2 or 3 sentences of general, common-sense
   guidance. In that case do not mention Bapuji and claim nothing about the books or teachings.
4. Your text is a paraphrase, so never write "Bapuji says" or put words in his mouth. Write
   "the teachings explain" or "the book explains" instead. The exact passage is shown on screen.
5. Do not give medical, legal or financial instructions; suggest a qualified professional instead.
6. Write plain sentences only: no bullet points, no markdown, no passage numbers in the text.
7. Language of the ANSWER text: {STYLE}. The labels USED and ANSWER stay in English.

Reply in exactly this format and nothing else:
USED: <passage numbers separated by commas, or NONE>
ANSWER: <your text>"""


def build_prompt(question: str, queries: list[str], passages: list[dict], language: str) -> tuple[str, str]:
    """The two texts sent to the LLM: (system instruction, user message)."""
    lang = LANGS.get(language, LANGS["English"])
    listing = "\n\n".join(
        f"[{i}] (Book: {p['title']}, page {p['page']})\n{p['text']}"
        for i, p in enumerate(passages, start=1)
    )
    asked = f"QUESTION: {question}"
    if queries != [question]:
        asked += "\nTHE QUESTION AS ENGLISH SEARCH QUERIES: " + " | ".join(queries)
    return SYSTEM_PROMPT.replace("{STYLE}", lang["style"]), f"{asked}\n\nPASSAGES:\n{listing}"


def parse_reply(raw: str, how_many: int) -> tuple[list[int], str]:
    """Split the LLM reply into (passage numbers it used, the answer text)."""
    used = []
    m_used = re.search(r"USED\s*:\s*(.*)", raw, flags=re.I)
    if m_used:
        for num in re.findall(r"\d+", m_used.group(1)):
            i = int(num)
            if 1 <= i <= how_many and i not in used:   # ignore numbers that do not exist
                used.append(i)
    m_ans = re.search(r"ANSWER\s*:\s*(.*)", raw, flags=re.I | re.S)
    text = (m_ans.group(1) if m_ans else re.sub(r"USED\s*:.*", "", raw, flags=re.I)).strip()
    return used, text


def answer(question: str, language: str = "English") -> dict:
    """Full pipeline for one question. Returns everything the screen needs."""
    lang = LANGS.get(language, LANGS["English"])
    seconds = {}                                   # how long each stage took, shown on screen

    clock = time.perf_counter()
    queries = plan_queries(question)               # translate / split the question if needed
    seconds["translate"] = time.perf_counter() - clock

    clock = time.perf_counter()
    passages = search_many(queries)
    seconds["search"] = time.perf_counter() - clock

    result = {"question": question, "language": language, "queries": queries,
              "search_query": " · ".join(queries),
              "found": False, "quotes": [], "passages": passages, "answer": "", "spoken": "",
              "seconds": seconds}
    if not passages:
        result["answer"] = "No books are indexed yet. Run step2_get_books.py and step3_build_index.py first."
        return result

    system, user = build_prompt(question, queries, passages, language)
    clock = time.perf_counter()
    raw = llm.chat(system, user)
    seconds["explain"] = time.perf_counter() - clock
    used, text = parse_reply(raw, len(passages))

    # Quotations come straight from the index, picked by number. The LLM cannot alter them.
    limit = max(config.MAX_QUOTES, min(6, len(queries)))      # several parts: a quotation for each
    result["quotes"] = [passages[i - 1] for i in used][:limit]
    result["found"] = bool(result["quotes"])
    result["answer"] = text
    result["spoken"] = text if result["found"] else lang["not_found"] + text
    return result
