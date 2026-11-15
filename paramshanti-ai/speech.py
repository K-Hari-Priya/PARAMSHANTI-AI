"""
speech.py - play the spoken answer while it is still being made.

Gnani Timbre can stream: it sends the sound in small pieces as it produces them.
A Streamlit page cannot play pieces one by one, so this file runs a tiny web
server inside the app (reachable only from this computer). The page's audio
player is pointed at that server, which passes every piece on the moment it
arrives. Result: the voice starts after a second or two and plays as one
continuous recording, with no joins.

A long answer is voiced part after part (Gnani takes one request at a time, and
refuses a text that is too long). Every part is added to the same recording, so
the listener hears one unbroken voice from the first word to the last.

   job = speech.say(text, "en-IN")     start voicing in the background
   job.wait_ready()                    wait until the first second of sound is there
   speech.url(job)                     the address the audio player should play
"""
import contextlib
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import gnani

RATE = 24000                       # samples per second
BYTES_PER_SECOND = RATE * 2        # 16-bit mono sound

_lock = threading.Lock()
_jobs: dict = {}                   # job id -> Job (the last few answers)
_server = None
_port = None


class Job:
    """One spoken answer: the sound collected so far, and whether it is finished."""

    def __init__(self, text: str, language: str, voice: str | None = None, model: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.text, self.language, self.voice = text, language, voice
        self.model = model                 # None = the usual Timbre model
        self.pcm = bytearray()             # the sound received so far
        self.done = False
        self.error = ""
        self.how = ""                      # "streaming", "one request" or "mixed"
        self.parts = 0                     # how many parts the answer was voiced in
        self._ways = set()
        self.cancelled = False
        self.started = time.perf_counter()
        self.first_sound_after = None      # seconds until the first piece arrived
        self.finished_after = None
        self.changed = threading.Condition()
        self._response = None

    @property
    def seconds(self) -> float:
        return len(self.pcm) / BYTES_PER_SECOND

    def _add(self, piece: bytes) -> None:
        with self.changed:
            if self.first_sound_after is None:
                self.first_sound_after = time.perf_counter() - self.started
            self.pcm.extend(piece)
            self.changed.notify_all()

    def run(self) -> None:
        """Runs in a background thread: collect the sound from Gnani Timbre, part after part."""
        try:
            # Every language is voiced in small parts, joined into one recording (see gnani.small_parts).
            parts = gnani.small_parts(self.text) if gnani.PART_BYTES else gnani.speech_parts(self.text)
            self.parts = len(parts)
            for number, part in enumerate(parts):
                if self.cancelled:
                    break
                if number:
                    self._add(gnani.pause(RATE))
                self._voice(part)
        except Exception as problem:
            if not self.cancelled:         # sound that already arrived is kept
                self.error = f"the voice stopped early: {problem}" if self.pcm else str(problem)
        finally:
            self.how = "mixed" if len(self._ways) > 1 else "".join(self._ways)
            with self.changed:
                self.done = True
                self.finished_after = time.perf_counter() - self.started
                self.changed.notify_all()

    def _voice(self, part: str, depth: int = 0) -> None:
        """Voice one part and add its sound to the recording.

        First choice is streaming. If streaming gives no sound, the part is asked for in one
        ordinary request. If Gnani refuses that too in a way that can mean 'this text is too
        long', the part is cut in two and each half is voiced the same way."""
        before = len(self.pcm)
        stream_problem = "no sound arrived"
        try:
            pieces = gnani.stream_speech(part, self.language, RATE,
                                         on_response=self._remember, voice=self.voice, **self._other_model())
            with contextlib.closing(pieces):
                for piece in pieces:
                    if self.cancelled:
                        return
                    self._add(piece)
        except Exception as problem:
            if self.cancelled:
                return
            if len(self.pcm) > before:     # some of this part has been played already: stop here
                raise
            stream_problem = problem
        if len(self.pcm) > before:
            self._ways.add("streaming")
            return
        if self.cancelled:
            return
        try:
            wav = gnani.text_to_speech(part, language=self.language, voice=self.voice,
                                       sample_rate=RATE, **self._other_model())
        except Exception as plain_problem:
            maybe_too_long = any(getattr(p, "status", None) in (400, 413, 500)
                                 for p in (plain_problem, stream_problem))
            halves = gnani.shorter_parts(part) if depth < 2 and maybe_too_long else []
            if not halves:
                raise gnani.GnaniError(f"{plain_problem} (streaming also failed: {stream_problem})",
                                       getattr(plain_problem, "status", None))
            for number, half in enumerate(halves):
                if self.cancelled:
                    return
                if number:
                    self._add(gnani.pause(RATE))
                self._voice(half, depth + 1)
            return
        if not self.cancelled:
            self._add(gnani._wav_pieces(wav)[1])
            self._ways.add("one request")

    def _other_model(self) -> dict:
        """Names the Timbre model only when this language needs a different one."""
        return {"model": self.model} if self.model else {}

    def _remember(self, response) -> None:
        """Keep the open connection, so cancel() can close it."""
        self._response = response
        if self.cancelled:
            response.close()

    def cancel(self) -> None:
        """Stop voicing (a new question arrived), so Gnani is free for the next request."""
        self.cancelled = True
        try:
            if self._response is not None:
                self._response.close()
        except Exception:
            pass
        with self.changed:
            self.changed.notify_all()

    def wait_ready(self, min_seconds: float = 1.2, timeout: float = 60) -> bool:
        """Wait until about a second of sound has arrived, or all of it. True if there is sound."""
        deadline = time.time() + timeout
        with self.changed:
            while not self.done and len(self.pcm) < min_seconds * BYTES_PER_SECOND:
                left = deadline - time.time()
                if left <= 0:
                    break
                self.changed.wait(min(left, 0.5))
        return len(self.pcm) > 0


class _Handler(BaseHTTPRequestHandler):
    """Answers the audio player's request: GET /speech/<job id>.wav"""
    protocol_version = "HTTP/1.0"          # the reply ends when we close the connection

    def log_message(self, *args) -> None:  # keep the terminal quiet
        pass

    def do_GET(self) -> None:
        job_id = self.path.split("?")[0].rsplit("/", 1)[-1].split(".")[0]
        job = _jobs.get(job_id)
        if job is None:
            self.send_error(404)
            return
        try:
            if job.done:
                self._whole(job)
            else:
                self._live(job)
        except (BrokenPipeError, ConnectionError, OSError):
            pass                           # the player went away (new question, page closed)

    def _live(self, job: Job) -> None:
        """Still being voiced: send what we have, then each new piece as it arrives."""
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(gnani.wav_header(RATE, None))      # None = length not known yet
        sent = 0
        while True:
            with job.changed:
                while len(job.pcm) == sent and not job.done:
                    job.changed.wait(0.5)
                piece, finished = bytes(job.pcm[sent:]), job.done
            if piece:
                self.wfile.write(piece)
                self.wfile.flush()
                sent += len(piece)
            if finished and sent >= len(job.pcm):
                break

    def _whole(self, job: Job) -> None:
        """Finished: send it as a normal file, so the player can show its length and seek."""
        wav = gnani.pcm_to_wav(bytes(job.pcm), RATE)
        start, end = 0, len(wav) - 1
        wanted = self.headers.get("Range", "")
        partial = wanted.startswith("bytes=")
        if partial:
            first, _, last = wanted[6:].split(",")[0].partition("-")
            start = int(first) if first.strip().isdigit() else 0
            end = min(int(last), end) if last.strip().isdigit() else end
            if start > end:
                self.send_error(416)
                return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(wav)}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(wav[start:end + 1])


def _start_server() -> int:
    """Start the little web server once; later calls just return its port."""
    global _server, _port
    with _lock:
        if _server is None:
            for port in range(config.SPEECH_PORT, config.SPEECH_PORT + 10):
                try:
                    _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
                    break
                except OSError:
                    continue               # port busy: try the next one
            if _server is None:
                raise RuntimeError("no free local port for the voice player")
            _server.daemon_threads = True
            threading.Thread(target=_server.serve_forever, daemon=True).start()
            _port = port
        return _port


def stop_all() -> None:
    """Stop any answer that is still being voiced."""
    for job in list(_jobs.values()):
        if not job.done:
            job.cancel()


def say(text: str, language: str = "en-IN", voice: str | None = None, model: str | None = None) -> Job:
    """Start voicing text in the background and return its Job."""
    _start_server()
    stop_all()
    job = Job(text, language, voice, model)
    with _lock:
        _jobs[job.id] = job
        for old in list(_jobs)[:-8]:        # remember only the last few answers
            del _jobs[old]
    threading.Thread(target=job.run, daemon=True).start()
    return job


def get(job_id: str):
    return _jobs.get(job_id)


def url(job) -> str:
    """Address for the audio player. '?whole' marks the finished file, so the browser reloads it."""
    job_id = job if isinstance(job, str) else job.id
    known = _jobs.get(job_id)
    suffix = "?whole=1" if known is not None and known.done else ""
    return f"http://127.0.0.1:{_port}/speech/{job_id}.wav{suffix}"
