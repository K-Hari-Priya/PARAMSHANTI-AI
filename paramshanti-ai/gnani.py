"""
gnani.py - the Gnani AI calls this project uses.

  speech_to_text(audio_bytes)  -> text       (Gnani "Prisma" model)
  text_to_speech(text)         -> WAV bytes  (Gnani "Timbre" model, sound returned when it is all ready)
  stream_speech(text)          -> pieces of sound as Timbre produces them (streaming)
  speech_parts(text)           -> a long answer cut into parts, each ending at the end of a sentence

All are plain HTTPS requests, as described at https://docs.gnani.ai

The app uses stream_speech so the voice can start after a second or two instead of
waiting for the whole answer (see speech.py). The account allows ONE request at a time,
and Gnani refuses a text that is too long, so a long answer is voiced part after part.
"""
import base64
import json
import math
import re
import struct
import time

import requests

import config

BASE_URL = "https://api.vachana.ai"

PART_CHARS = 900            # the most text sent to Timbre in ONE request (Gnani refuses a text
                            # that is too long). The answer itself has no limit: a longer answer
                            # simply becomes more parts, and all of it is read aloud.
PAUSE_SECONDS = 0.2         # silence between two parts, like a breath between sentences


class GnaniError(Exception):
    """Raised when Gnani returns an error, with a readable explanation."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status           # the HTTP status code, when there was one


def _explain(resp: requests.Response) -> str:
    """Turn any Gnani error reply into one readable line."""
    try:
        data = resp.json()
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:300]}"
    msg = ""
    if isinstance(data, dict):
        err = data.get("error")
        det = data.get("detail")
        if isinstance(err, dict):
            msg = f"{err.get('type', '')} {err.get('message', '')}"
        elif isinstance(det, dict):
            msg = f"{det.get('error_code', '')} {det.get('message', '')}"
        elif det:
            msg = str(det)
        elif err:
            msg = f"{err} {data.get('message', '')}"
    msg = msg.strip() or str(data)[:300]
    hint = {
        401: "The API key is missing or wrong. Check GNANI_API_KEY in .env.",
        402: "Credits finished. Check your balance at app.gnani.ai/voice.",
        403: "Key, account status or credits problem. Check app.gnani.ai/voice.",
        429: "Too many requests. Wait a minute and try again.",
    }.get(resp.status_code, "")
    return f"HTTP {resp.status_code}: {msg} {hint}".strip()


def _send(make_request, tries: int = 8, wait: float = 1.2) -> requests.Response:
    """Send a request. If Gnani says 'one request at a time' (HTTP 429) because an
    earlier request is still finishing, wait a moment and try again."""
    resp = make_request()
    for _ in range(tries - 1):
        if resp.status_code != 429:
            break
        time.sleep(wait)
        resp = make_request()
    if resp.status_code != 200:
        raise GnaniError(_explain(resp), resp.status_code)
    return resp


def speech_to_text(audio_bytes: bytes, filename: str = "question.wav",
                   language: str = "en-IN", model: str | None = None) -> str:
    """Send a recording (max 30 seconds) to Gnani Prisma and return the text."""
    key = config.need(config.GNANI_API_KEY, "GNANI_API_KEY")
    model = config.STT_MODEL if model is None else model
    form = {"language_code": language}
    if model:                      # leaving it out means Gnani's default (Prisma v2.5)
        form["model"] = model
    resp = _send(lambda: requests.post(
        f"{BASE_URL}/stt/v3",
        headers={"X-API-Key-ID": key},
        files={"audio_file": (filename, audio_bytes, "audio/wav")},
        data=form,
        timeout=90,
    ))
    return (resp.json().get("transcript") or "").strip()


def clean_for_speech(text: str) -> str:
    """Remove things that sound wrong when read aloud. No words are removed."""
    text = re.sub(r"\[\d+\]", "", text)            # passage numbers like [1]
    text = re.sub(r"[*_#>`]", "", text)            # markdown symbols
    return re.sub(r"\s+", " ", text).strip()


# A sentence ends at . ! ? or । (Hindi), possibly followed by a closing quote or bracket.
_SENTENCE_GAP = re.compile(r"(?<=[.!?।])\s+|(?<=[.!?।][\"'”’)\]])\s+")
_NOT_AN_END = ("Dr.", "Mr.", "Mrs.", "Ms.", "Shri.", "Smt.", "Sri.", "St.", "vs.", "e.g.", "i.e.")


def _sentences(text: str) -> list[str]:
    """Cut text into sentences."""
    found: list[str] = []
    for piece in _SENTENCE_GAP.split(text):
        if not piece:
            continue
        last = found[-1] if found else ""
        if last.endswith(_NOT_AN_END) or re.search(r"(^|\s)\d{1,2}\.$", last):
            found[-1] = f"{last} {piece}"          # "Dr. Rao" and "2. Next point" stay together
        else:
            found.append(piece)
    return found


def _cut_long(sentence: str, limit: int) -> list[str]:
    """A single sentence longer than the limit is cut at a comma, or else at a space."""
    pieces = []
    while len(sentence) > limit:
        cut = sentence[:limit]
        at = max(cut.rfind(", "), cut.rfind("; "), cut.rfind(": "))
        if at < limit // 2:
            at = cut.rfind(" ")
        if at <= 0:
            at = limit - 1                         # no space anywhere: cut at the limit
        pieces.append(sentence[:at + 1].strip())
        sentence = sentence[at + 1:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


PART_BYTES = 300      # the size of one request to Timbre (see small_parts); 0 = the older, larger parts


def _size(text: str) -> int:
    """How big a text is for Timbre: its UTF-8 bytes (a Hindi or Telugu letter counts as three)."""
    return len(text.encode("utf-8"))


def small_parts(text: str, max_bytes: int | None = None) -> list[str]:
    """Cut an answer into small parts for Timbre, a sentence or two each.

    Timbre has been heard to stop part-way through a longer text, at the end of a sentence,
    after roughly 400 bytes. So no request is larger than max_bytes: whole sentences are
    kept together while they fit, and a sentence that is too long by itself is cut at a
    comma. The parts are voiced one after another and joined, so nothing is left out,
    however long the answer is."""
    max_bytes = max_bytes or PART_BYTES or 300
    pieces = []
    for sentence in _sentences(clean_for_speech(text)):
        if _size(sentence) <= max_bytes:
            pieces.append(sentence)
        else:                                       # the same limit, counted in this sentence's letters
            letters = max(30, int(len(sentence) * max_bytes / _size(sentence)))
            pieces.extend(piece for piece in _cut_long(sentence, letters) if piece.strip())
    parts: list[str] = []
    for piece in pieces:
        if parts and _size(parts[-1]) + 1 + _size(piece) <= max_bytes:
            parts[-1] = f"{parts[-1]} {piece}"
        else:
            parts.append(piece)
    return parts


def sentence_parts(text: str, part_chars: int = PART_CHARS) -> list[str]:
    """Cut an answer into its sentences, one part for each.

    Used for the languages other than English and Hindi: there Timbre has been heard to stop
    after the first sentence of a longer text, so every sentence is sent on its own and the
    recordings are joined. Nothing is left out."""
    parts = []
    for sentence in _sentences(clean_for_speech(text)):
        parts.extend(piece for piece in _cut_long(sentence, part_chars) if piece.strip())
    return parts


def speech_parts(text: str, part_chars: int = PART_CHARS) -> list[str]:
    """Cut an answer into parts that Timbre voices one after another.

    A short answer stays in one part. A longer one is cut at the ends of sentences into
    parts of about equal length, none longer than part_chars. Nothing is left out,
    however long the answer is."""
    text = clean_for_speech(text)
    if len(text) <= part_chars:
        return [text] if text else []
    units: list[str] = []                          # the sentences; a very short one joins the next
    for sentence in _sentences(text):
        for piece in _cut_long(sentence, part_chars):
            if units and len(units[-1]) < 40 and len(units[-1]) + 1 + len(piece) <= part_chars:
                units[-1] = f"{units[-1]} {piece}"
            else:
                units.append(piece)
    # A very long text is worked through a stretch at a time (about 8 parts each), so this
    # stays quick whatever the length.
    total = sum(len(unit) + 1 for unit in units)
    stretches = math.ceil(total / (part_chars * 8))
    parts, stretch, seen, finished = [], [], 0, 0
    for unit in units:
        stretch.append(unit)
        seen += len(unit) + 1
        if finished < stretches - 1 and seen >= total / stretches * (finished + 1):
            parts += _fill(stretch, part_chars)
            stretch, finished = [], finished + 1
    return parts + (_fill(stretch, part_chars) if stretch else [])


def _fill(sentences: list[str], part_chars: int) -> list[str]:
    """Put the sentences, in order, into as few parts as possible (none over part_chars),
    and of all the ways to do that, choose the one whose parts are most equal in length."""
    n = len(sentences)
    before = [0] * (n + 1)                         # before[i] = characters ahead of sentence i
    for i, sentence in enumerate(sentences):
        before[i + 1] = before[i] + len(sentence) + 1

    def size(i: int, j: int) -> int:               # sentences i to j-1, joined by spaces
        return before[j] - before[i] - 1

    count, i = 0, 0                                # fewest parts: fill each one as far as it goes
    while i < n:
        j = i + 1
        while j < n and size(i, j + 1) <= part_chars:
            j += 1
        count, i = count + 1, j

    # Most equal: try every way to make `count` parts and keep the smallest total of squared
    # lengths. best[k][j] is the best total for the first j sentences in k parts.
    best = [[float("inf")] * (n + 1) for _ in range(count + 1)]
    cut_at = [[0] * (n + 1) for _ in range(count + 1)]
    best[0][0] = 0
    for k in range(1, count + 1):
        for j in range(k, n + 1):
            for i in range(j - 1, k - 2, -1):      # the last part holds sentences i to j-1
                if size(i, j) > part_chars:
                    break
                total = best[k - 1][i] + size(i, j) ** 2
                if total < best[k][j]:
                    best[k][j], cut_at[k][j] = total, i
    parts, j = [], n
    for k in range(count, 0, -1):
        i = cut_at[k][j]
        parts.append(" ".join(sentences[i:j]))
        j = i
    return parts[::-1]


def shorter_parts(text: str) -> list[str]:
    """Cut one part into two shorter ones (used if Gnani refuses a part as too long).
    Returns an empty list when the text is already too short to be worth cutting."""
    parts = speech_parts(text, part_chars=max(100, math.ceil(len(text) * 0.6)))
    return parts if len(parts) > 1 else []


def pause(sample_rate: int = 24000, seconds: float = PAUSE_SECONDS) -> bytes:
    """A moment of silence, as raw 16-bit mono sound."""
    return b"\x00\x00" * int(sample_rate * seconds)


def text_to_speech(text: str, language: str = "en-IN", voice: str | None = None,
                   model: str | None = None, sample_rate: int = 24000) -> bytes:
    """Send text to Gnani Timbre and return the spoken audio as WAV bytes.

    A long text goes as several requests, one after another, joined into one recording."""
    parts = speech_parts(text)
    if len(parts) <= 1:
        return _speech_request(parts[0] if parts else "", language, voice, model, sample_rate)
    replies = [_wav_pieces(_speech_request(part, language, voice, model, sample_rate)) for part in parts]
    rate = struct.unpack("<I", replies[0][0][4:8])[0]          # the sample rate Gnani actually used
    return pcm_to_wav(pause(rate).join(sound for _, sound in replies), rate)


def _speech_request(text: str, language: str, voice: str | None, model: str | None,
                    sample_rate: int) -> bytes:
    """One ordinary text-to-speech request: the reply is a complete WAV file."""
    key = config.need(config.GNANI_API_KEY, "GNANI_API_KEY")
    body = {
        "text": clean_for_speech(text),
        "voice": voice or config.TTS_VOICE,
        "model": model or config.TTS_MODEL,
        "language": language,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    resp = _send(lambda: requests.post(
        f"{BASE_URL}/api/v1/tts/inference",
        headers={"X-API-Key-ID": key, "Content-Type": "application/json"},
        json=body,
        timeout=120,
    ))
    if not resp.content.startswith(b"RIFF"):       # a real WAV file starts with RIFF
        raise GnaniError(f"Expected audio but got: {resp.content[:200]!r}")
    return resp.content


def stream_speech(text: str, language: str = "en-IN", sample_rate: int = 24000,
                  on_response=None, voice: str | None = None, model: str | None = None):
    """Streaming text-to-speech: yield pieces of raw sound as Timbre produces them.

    This uses Gnani's SSE endpoint ("Server-Sent Events"): one request stays open and the
    server keeps sending small chunks of audio, so the first words can be played while the
    rest of the answer is still being voiced. Each piece is raw 16-bit mono PCM.

    A long text is voiced part after part: when one request finishes the next one starts,
    and the pieces simply keep coming.
    """
    for number, part in enumerate(speech_parts(text) or [""]):
        if number:
            yield pause(sample_rate)
        if model:
            yield from _stream_request(part, language, sample_rate, on_response, voice, model)
        else:
            yield from _stream_request(part, language, sample_rate, on_response, voice)


def _stream_request(text: str, language: str, sample_rate: int, on_response, voice: str | None,
                    model: str | None = None):
    """One streaming request: yield its pieces of sound as they arrive."""
    key = config.need(config.GNANI_API_KEY, "GNANI_API_KEY")
    body = {
        "text": clean_for_speech(text),
        "voice": voice or config.TTS_VOICE,
        "model": model or config.TTS_MODEL,
        "language": language,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",            # raw = just the sound, no file header
        },
    }
    resp = _send(lambda: requests.post(
        f"{BASE_URL}/api/v1/tts/sse",
        headers={"X-API-Key-ID": key, "Content-Type": "application/json"},
        json=body,
        stream=True,
        timeout=(15, 60),
    ))
    if on_response:
        on_response(resp)                  # lets the caller close the connection to stop early
    event = ""
    try:
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", "replace")
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except ValueError:
                continue
            if event == "error":
                raise GnaniError(f"{data.get('type', '')} {data.get('message', '')}".strip() or "streaming error")
            sound = data.get("audio")
            if sound:
                piece = base64.b64decode(sound)
                if piece[:4] == b"RIFF":   # just in case a piece arrives as a small WAV file
                    piece = _wav_pieces(piece)[1]
                yield piece
            if data.get("is_final") or event == "complete":
                break
    finally:
        resp.close()


def wav_header(sample_rate: int, sound_bytes: int | None) -> bytes:
    """The 44 bytes that start a WAV file of 16-bit mono sound.
    sound_bytes=None means 'length not known yet' (used while the sound is still streaming)."""
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    riff_size = 0xFFFFFFFF if sound_bytes is None else 36 + sound_bytes
    data_size = 0xFFFFFFFF if sound_bytes is None else sound_bytes
    return (b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
            + b"fmt " + struct.pack("<I", 16) + fmt
            + b"data" + struct.pack("<I", data_size))


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Put a WAV file header in front of raw 16-bit mono sound."""
    return wav_header(sample_rate, len(pcm)) + pcm


def _wav_pieces(data: bytes) -> tuple[bytes, bytes]:
    """Take a WAV file apart: (its format description, its raw sound)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt = 12, None
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        start = pos + 8
        if tag == b"fmt ":
            fmt = data[start:start + size]
        elif tag == b"data":
            if fmt is None:
                break
            end = start + size
            if size in (0, 0xFFFFFFFF) or end > len(data):   # some servers leave the size blank
                end = len(data)
            return fmt, data[start:end]
        pos = start + size + (size & 1)
    raise ValueError("WAV file has no sound in it")


def wav_seconds(wav: bytes) -> float:
    """How long a WAV file plays."""
    fmt, sound = _wav_pieces(wav)
    return len(sound) / struct.unpack("<I", fmt[8:12])[0]       # bytes / bytes-per-second
