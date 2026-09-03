"""Text-to-speech output for the assistant."""

import threading

from .config import ASSISTANT_NAME, TTS_RATE, TTS_VOLUME, TTS_VOICE_HINT

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        import pyttsx3

        _engine = pyttsx3.init()
        _engine.setProperty("rate", TTS_RATE)
        _engine.setProperty("volume", TTS_VOLUME)
        for voice in _engine.getProperty("voices"):
            name = (voice.name or "").lower() + " " + (voice.id or "").lower()
            if TTS_VOICE_HINT in name:
                _engine.setProperty("voice", voice.id)
                break
    return _engine


def speak(text: str) -> None:
    """Speak *text* out loud (and echo it to the terminal)."""
    if not text:
        return
    print(f"{ASSISTANT_NAME}: {text}")
    try:
        with _lock:
            engine = _get_engine()
            engine.say(text)
            engine.runAndWait()
    except Exception as exc:  # never let audio failure kill the loop
        print(f"[tts error: {exc}]")


def shutdown() -> None:
    global _engine
    try:
        if _engine is not None:
            _engine.stop()
    except Exception:
        pass
    _engine = None
