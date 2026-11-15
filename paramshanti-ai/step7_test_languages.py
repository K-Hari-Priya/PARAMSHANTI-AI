"""
STEP 7 - find out which languages Gnani can hear and speak with your key.

Run:   python step7_test_languages.py        (takes about two minutes)

For each of the ten languages it asks Gnani Timbre to say one sentence, then asks Gnani
Prisma to listen to that recording. The result is saved in data\\voices.json, and the app
uses it: a language Timbre cannot speak is still answered, as text.
"""
import io, json, wave

import config, gnani, rag

config.fix_console()
OTHER_MODEL, OTHER_VOICES = "timbre-v2.5", ["Nalini", "Karan", "Simran"]     # tried when the usual model cannot speak a language


def seconds(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


def try_voice(text, code, voice=None, model=None):
    try:
        wav = gnani.text_to_speech(text, language=code, voice=voice, model=model)
        return wav if seconds(wav) > 0.6 else None
    except Exception as problem:
        print(f"      ({model or config.TTS_MODEL}, {voice or config.TTS_VOICE}: {str(problem)[:110]})")
        return None


found = {}
print(f"Usual voice: {config.TTS_VOICE} on {config.TTS_MODEL}\n")
for name, lang in rag.LANGS.items():
    code, sentence = lang["tts"], lang["examples"][0]
    print(f"{name} ({code})")
    wav, how = try_voice(sentence, code), {}
    if wav is None:
        for voice in OTHER_VOICES:
            wav = try_voice(sentence, code, voice, OTHER_MODEL)
            if wav is not None:
                how = {"model": OTHER_MODEL, "voice": voice}
                break
    if wav is None:
        found[code] = None
        print("   SPEAK: no    (answers in this language will be shown as text)")
    else:
        found[code] = how
        print(f"   SPEAK: yes   ({how.get('model', config.TTS_MODEL)}, {how.get('voice', 'your chosen voice')}, {seconds(wav):.1f} s)")
    try:
        heard = gnani.speech_to_text(wav, language=lang["stt"]) if wav else ""
        print(f"   HEAR:  {'yes   ' + heard if heard else ('not tested' if not wav else 'nothing heard')}")
    except Exception as problem:
        print(f"   HEAR:  no    ({str(problem)[:110]})")
rag.VOICES_FILE.write_text(json.dumps(found, indent=1), encoding="utf-8")
print(f"\nSaved to {rag.VOICES_FILE}. Now start the app:  streamlit run app.py")
