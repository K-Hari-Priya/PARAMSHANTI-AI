"""
STEP 1 - test your Gnani AI key, with no microphone needed.

What it does:
  1. Timbre (text-to-speech) turns one sentence into data\\audio\\test.wav
  2. Prisma (speech-to-text) listens to that same file and writes the text back
If both lines say OK, your key, credits and both Gnani models work.

Run:   python step1_test_gnani.py
"""
import sys

import config
import gnani

config.fix_console()
config.need(config.GNANI_API_KEY, "GNANI_API_KEY")

SENTENCE = "Peace of mind is the first step towards a happy life."
out_file = config.AUDIO_DIR / "test.wav"

# ---- 1. text to speech ---------------------------------------------------
# Try your configured voice first; fall back to the older model if it is refused.
attempts = [(config.TTS_MODEL, config.TTS_VOICE), ("timbre-v2.5", "Kaveri")]
audio, used_tts = None, None
for model, voice in attempts:
    try:
        audio = gnani.text_to_speech(SENTENCE, model=model, voice=voice, sample_rate=16000)
        used_tts = (model, voice)
        break
    except gnani.GnaniError as e:
        print(f"TTS with {model} / {voice} failed -> {e}")
    except Exception as e:
        print(f"TTS could not reach Gnani -> {e}")

if audio is None:
    print("\nFAIL: text-to-speech did not work. Copy everything above and send it to Claude.")
    sys.exit(1)

out_file.write_bytes(audio)
print(f"OK  text-to-speech  model={used_tts[0]} voice={used_tts[1]}  -> {out_file} ({len(audio)//1024} KB)")

# ---- 2. speech to text ---------------------------------------------------
text, used_stt = None, None
for model in dict.fromkeys([config.STT_MODEL, ""]):   # "" = Gnani's default model (Prisma v2.5)
    try:
        text = gnani.speech_to_text(audio, filename="test.wav", model=model)
        used_stt = model
        break
    except gnani.GnaniError as e:
        print(f"STT with {model or 'default model'} failed -> {e}")
    except Exception as e:
        print(f"STT could not reach Gnani -> {e}")

if text is None:
    print("\nFAIL: speech-to-text did not work. Copy everything above and send it to Claude.")
    sys.exit(1)

print(f"OK  speech-to-text  model={used_stt or 'prisma-v2.5 (default)'}")
print(f"\n    We said : {SENTENCE}")
print(f"    It heard: {text}")

# ---- what to put in .env if a fallback was needed --------------------------
if used_tts != (config.TTS_MODEL, config.TTS_VOICE):
    print(f"\nNOTE: add these two lines to .env:  TTS_MODEL={used_tts[0]}   and   TTS_VOICE={used_tts[1]}")
if used_stt != config.STT_MODEL:
    print("\nNOTE: add this line to .env:  STT_MODEL=default")
print("\nSTEP 1 PASSED. You can double-click data\\audio\\test.wav to hear the voice.")
