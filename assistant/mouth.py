"""Text-to-speech output for the assistant.

Prefers Piper neural TTS (natural voice — sounds like Jarvis, not a 90s
robot) and falls back to pyttsx3/eSpeak when Piper or a voice model isn't
available. The Piper voice is downloaded once, on first use, into
~/.local/share/piper/voices.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading

from .config import (
    ASSISTANT_NAME,
    PIPER_VOICE_DIR,
    TTS_PIPER_LENGTH_SCALE,
    TTS_PIPER_VOICE,
    TTS_PIPER_VOICE_NAME,
    TTS_RATE,
    TTS_VOICE_HINT,
    TTS_VOLUME,
)

_engine = None
_lock = threading.Lock()

# Default voice: British male — the Jarvis sound. Keep the list ordered by
# preference; the first one present (or downloadable) wins.
_PIPER_VOICE_PREFS = [
    ("en_GB", "alan", "medium"),
    ("en_GB", "northern_english_male", "medium"),
    ("en_US", "ryan", "high"),
    ("en_US", "lessac", "medium"),
]


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


def _piper_binary() -> str | None:
    for path in (
        shutil.which("piper"),
        shutil.which("piper-bin"),
        # The venv's pip-installed piper, found even when not activated.
        os.path.join(sys.prefix, "bin", "piper"),
    ):
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _player_binary() -> str | None:
    for name in ("paplay", "pw-play", "aplay", "ffplay"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _download_piper_voice(locale: str, speaker: str, quality: str) -> str | None:
    """Fetch a voice model once from rhasspy/piper-voices; returns its path."""
    import requests

    base = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{locale.split('_')[0]}/{locale}/{speaker}/{quality}")
    PIPER_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    stem = os.path.join(PIPER_VOICE_DIR, f"{locale}-{speaker}-{quality}")
    try:
        for suffix in (".onnx", ".onnx.json"):
            target = stem + suffix
            if os.path.exists(target):
                continue
            print(f"[tts] downloading Piper voice {os.path.basename(target)} ...")
            with requests.get(f"{base}/{locale}-{speaker}-{quality}{suffix}",
                              stream=True, timeout=(10, 120)) as resp:
                resp.raise_for_status()
                tmp = target + ".part"
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(1 << 16):
                        fh.write(chunk)
                os.replace(tmp, target)
        return stem + ".onnx"
    except Exception as exc:
        print(f"[tts] Piper voice download failed ({exc}) — using eSpeak")
        return None


def _resolve_piper_voice() -> str | None:
    """Explicit path > named voice in the voice dir > preferred download."""
    if TTS_PIPER_VOICE and os.path.exists(TTS_PIPER_VOICE):
        return TTS_PIPER_VOICE
    if os.path.isdir(PIPER_VOICE_DIR):
        present = [n for n in sorted(os.listdir(PIPER_VOICE_DIR))
                   if n.endswith(".onnx")]
        if TTS_PIPER_VOICE_NAME:
            for n in present:
                if TTS_PIPER_VOICE_NAME.lower() in n.lower():
                    return os.path.join(PIPER_VOICE_DIR, n)
        if present:
            present.sort(key=lambda n: (not n.startswith(("en_GB", "en_US")), n))
            return os.path.join(PIPER_VOICE_DIR, present[0])
    if TTS_PIPER_VOICE_NAME:
        # "en_US-ryan-high" or "alan" — best-effort parse into parts.
        parts = TTS_PIPER_VOICE_NAME.split("-")
        if len(parts) == 3:
            return _download_piper_voice(*parts)
    for locale, speaker, quality in _PIPER_VOICE_PREFS:
        path = _download_piper_voice(locale, speaker, quality)
        if path:
            return path
    return None


def _speak_piper(text: str) -> bool:
    """Speak through Piper; False when Piper can't be used (fall back)."""
    binary = _piper_binary()
    player = _player_binary()
    if not (binary and player):
        return False
    voice = _resolve_piper_voice()
    if not voice:
        return False
    wav_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav:
            wav_path = wav.name
        cmd = [binary, "-m", voice, "-f", wav_path]
        if TTS_VOLUME and TTS_VOLUME != 1.0:
            cmd += ["--volume", str(TTS_VOLUME)]
        if TTS_PIPER_LENGTH_SCALE:
            cmd += ["-l", TTS_PIPER_LENGTH_SCALE]
        # 20s is plenty for a short reply; 60s let a wedged piper wedge
        # the whole assistant (held _lock) and look like a full freeze.
        result = subprocess.run(cmd, input=text.encode(), timeout=20,
                                capture_output=True)
        if result.returncode != 0 or not os.path.exists(wav_path):
            return False
        try:
            if not os.path.getsize(wav_path):
                return False
        except OSError:
            return False
        play = [player]
        if os.path.basename(player) == "ffplay":
            play += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
        # TTS wavs are seconds long; 30s cap means a hung paplay/PipeWire
        # fails fast instead of freezing speech (and the worker) for 2 min.
        subprocess.run(play + [wav_path], timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        try:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
        except OSError:
            pass


def speak(text: str) -> None:
    """Speak *text* out loud (and echo it to the terminal)."""
    if not text:
        return
    print(f"{ASSISTANT_NAME}: {text}")
    try:
        with _lock:
            if _speak_piper(text):
                return
            # eSpeak fallback: never let a hung audio backend wedge the
            # worker. runAndWait has no timeout, so bound it.
            import concurrent.futures

            engine = _get_engine()
            engine.say(text)

            def _wait():
                engine.runAndWait()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_wait)
                try:
                    fut.result(timeout=15)
                except concurrent.futures.TimeoutError:
                    try:
                        engine.stop()
                    except Exception:
                        pass
                    print("[tts] eSpeak playback timed out — skipping audio")
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
