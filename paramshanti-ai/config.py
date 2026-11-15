"""
config.py - shared settings for PARAMSHANTI AI.

Every other file imports from here, so paths and keys live in ONE place.
You normally never need to edit this file. Keys go in the .env file.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------- folders ----------
ROOT = Path(__file__).resolve().parent      # the project folder (C:\paramshanti-ai)
DATA = ROOT / "data"
PDF_DIR = DATA / "pdfs"        # downloaded books (PDF)
TEXT_DIR = DATA / "text"       # text pulled out of each book, page by page
CHROMA_DIR = DATA / "chroma"   # the searchable index (vector database)
AUDIO_DIR = DATA / "audio"     # test recordings

for _d in (PDF_DIR, TEXT_DIR, CHROMA_DIR, AUDIO_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------- keys and options (read from the .env file) ----------
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    """Read a setting from .env. Placeholder text counts as 'not set'."""
    value = (os.getenv(name) or "").strip().strip('"').strip("'")
    if not value or value.upper().startswith("PASTE_"):
        return default
    return value


GNANI_API_KEY = env("GNANI_API_KEY")
STT_MODEL = env("STT_MODEL", "prisma-v3.0")      # Gnani speech-to-text model
if STT_MODEL.lower() in ("default", "prisma-v2.5"):
    STT_MODEL = ""                               # empty = Gnani's default (Prisma v2.5)
TTS_MODEL = env("TTS_MODEL", "timbre-v3.0")      # Gnani text-to-speech model
TTS_VOICE = env("TTS_VOICE", "Shivani")          # a voice that belongs to TTS_MODEL
SPEECH_PORT = int(env("SPEECH_PORT", "8502"))    # local port the voice player reads from

LLM_PROVIDER = env("LLM_PROVIDER", "gemini").lower()   # "gemini" or "openai" (Groq etc.)
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL = env("LLM_MODEL")                     # empty = pick automatically (see llm.py)
LLM_BASE_URL = env("LLM_BASE_URL", "https://api.groq.com/openai/v1")  # only for "openai"

KEEP_PDFS = env("KEEP_PDFS", "no").lower() in ("yes", "true", "1")   # keep PDFs after reading them?
SHOW_AUTHORS = env("SHOW_AUTHORS", "no").lower() in ("yes", "true", "1")   # print each book's author?

COLLECTION_NAME = "bapuji_books"
TOP_K = 6          # how many passages we fetch for each question
MAX_QUOTES = 3     # how many passages we show as quotations


def fix_console() -> None:
    """Stop Windows from crashing when we print characters like the long dash."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def need(value: str, name: str) -> str:
    """Stop with a clear message when a key is missing from .env."""
    if not value:
        print(f"\nMISSING: {name} is not set.")
        print("Fix: type   notepad .env   then paste your key after the = sign, save, and run again.")
        sys.exit(1)
    return value
