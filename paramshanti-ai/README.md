# PARAMSHANTI AI

A voice assistant that answers from 131 books that present the teachings of
Bapuji Dashrathbhai Patel. Ask aloud or in writing, in ten Indian languages (English, Hindi,
Bengali, Gujarati, Marathi, Punjabi, Tamil, Telugu, Kannada, Malayalam) or in Hinglish.
You hear the answer, and under it you see the exact passage, its book and its page.

Built for the Great Indian AI Internship Challenge (Gnani AI), November 2026.

## What it does

- **Voice in, voice out.** Gnani Prisma hears the question; Gnani Timbre reads the answer aloud.
  The voice is streamed, so it starts while the rest of the answer is still being voiced.
- **Every answer shows its source.** Each passage appears word for word as a page of its book,
  with the book's name, the chapter and the page number, and a link that opens the book.
- **AI words and book words never mix.** The explanation is labelled as written by AI.
  Quotations are never written by the AI: the app copies them from its index.
- **It says when it does not know.** If no passage supports an answer, the app says so and
  labels the reply as general guidance.
- **Questions with several parts.** A long question is split into up to six parts and the
  books are searched for each one.
- **Ten languages.** The app opens on a welcome screen where the language is chosen. The
  question is translated for the search, the explanation comes back in the chosen language,
  and the passages are shown in their original English.
- **13 voices** (Gnani Timbre v3.0), chosen on the page.
- **The steps are timed on screen**: how long listening, searching, writing and the first
  sound took for each answer.

## How it works

| Step | What happens | Technology |
|---|---|---|
| 1 | The spoken question becomes text | Gnani Prisma v3.0 (speech-to-text) |
| 2 | The question is translated if needed and split into parts | Gemini 3.5 Flash-Lite |
| 3 | 15,219 passages from 131 books are searched by meaning | Chroma + MiniLM embeddings, on the laptop |
| 4 | A short explanation is written from the passages found | Gemini 3.5 Flash-Lite |
| 5 | The passages are shown word for word with book and page | Streamlit |
| 6 | The answer is read aloud, streamed | Gnani Timbre v3.0 (text-to-speech, SSE) |

## Problems solved

| Problem | What we changed |
|---|---|
| A passage that runs over two pages cannot have one page number | Passages never cross a page, so every passage has one exact page number |
| An LLM can alter or invent a quotation | The LLM only names the passage numbers it used; the app copies those passages from its index |
| A question with several parts got an answer to only one part | A planner splits the question into up to six searches, and the answer covers each part in order |
| Questions in Hindi, Hinglish and the other Indian languages found weak passages, because the books are in English | The question is translated into English before the search |
| The voice stopped part-way through a longer answer | The answer is voiced a sentence or two at a time and joined into one recording, with no length limit |
| The voice began only when the whole recording was ready | The voice is streamed, so it starts early |
| Sometimes no answer came, because the LLM or the voice service was slow or busy | Time limits, an automatic second try, and a clear message if it still fails |
| The same page (for example "About Bapuji") is in many books and crowded the results | Repeated passages are skipped in the search |

## Run it (Windows, Python 3.11 to 3.13)

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env                      (paste your Gnani key and your Gemini key)
python step1_test_gnani.py        (tests the Gnani key: text to speech and back)
python step2_get_books.py         (downloads the books and extracts their text)
python step3_build_index.py       (builds the searchable index)
python step4_ask.py               (tests the search)
python step5_test_llm.py          (tests the LLM and one full answer)
python step6_speed_test.py        (picks the fastest Gemini model for your key)
python step7_test_languages.py    (checks which languages Gnani hears and speaks with your key)
streamlit run app.py
```

## The files

| File | What it is |
|---|---|
| `app.py` | The page: settings, question box, answer, voice |
| `look.py` | How it looks: the night sky, the point of light, the paper pages |
| `rag.py` | Searching the books and writing the answer |
| `gnani.py` | The Gnani calls: Prisma (speech-to-text) and Timbre (text-to-speech) |
| `speech.py` | Streams the voice to the browser as one continuous recording |
| `llm.py` | The call to the LLM |
| `config.py` | Settings and keys (read from `.env`) |
| `books.csv` | The list of books and where each one is downloaded from |
| `step1` to `step7` | Set-up and test scripts, run once in order |
| `static/` | The typeface (EB Garamond) and the tab icon |

## What is not in this folder

- **Keys.** They live in `.env` on the laptop. `.env.example` shows the format.
- **The books, their extracted text and the index.** `step2_get_books.py` downloads the books
  from their public links, and `step3_build_index.py` builds the index, into a `data/` folder
  that stays on the laptop.

## Good to know

- The Gnani account used here handles one request at a time, and Timbre was heard to stop
  part-way through a longer text. So every answer is voiced a sentence or two at a time,
  and the parts are joined into a single recording with no limit on its length.
- The voice is served from the same laptop the app runs on. A public, hosted version needs
  a small change there, plus usage limits.
- This is a study and reflection aid. It quotes the books; it does not speak for
  Bapuji Dashrathbhai Patel and does not replace professional advice.

## Credits

Gnani AI (Prisma and Timbre), Google Gemini, Chroma, Streamlit, PyMuPDF.
The typeface is EB Garamond, used under the SIL Open Font License (see `static/fonts`).
