"""Microphone input: one persistent capture stream feeding recognised phrases
into a queue. Keeping the stream open avoids per-phrase reopen latency and the
ALSA device-probe noise.

Phrases are gated on a median-based noise floor rather than the stock
SpeechRecognition dynamic threshold: laptop mics produce short loud bursts
(fan spin-up, EMI) that the stock threshold chases upward, leaving the
assistant deaf. A median floor over recent history ignores bursts.
"""

import audioop
import collections
import contextlib
import os
import queue
import re
import statistics
import subprocess
import sys
import threading
import time

from .config import MIC_DEVICE_INDEX, PHRASE_TIME_LIMIT, STT_LANGUAGE

# Words the assistant can act on. When Google returns several guesses for
# one utterance, the guess containing one of these wins over the top
# hypothesis — e.g. "go to box 2" loses to "go to workspace 2", so a
# mangled keyword doesn't eat the whole command.
_COMMAND_KEYWORDS = (
    "workspace", "volume", "brightness", "screenshot", "youtube", "whatsapp",
    "telegram", "terminal", "vscode", "chrome", "firefox", "timer", "reminder",
    "bluetooth", "wifi", "clipboard", "trash", "mouse", "click", "scroll",
    "type", "press", "open", "close", "focus", "minimise", "minimize",
    "maximise", "maximize", "play", "pause", "weather", "joke", "lock",
    "sleep", "shutdown", "restart",
)


def _pick_transcript(result) -> str:
    """Pick the best guess from a show_all recognition result.

    Prefers an alternative containing a known command keyword; otherwise
    the top hypothesis. Returns '' when nothing usable came back.
    """
    if isinstance(result, str):
        return result.strip()
    if not isinstance(result, dict):
        return ""
    alternatives = result.get("alternative") or []
    if not alternatives:
        return ""
    texts = [str(a.get("transcript") or "").strip()
             for a in alternatives if isinstance(a, dict)]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    for text in texts:
        lowered = text.lower()
        if any(k in lowered for k in _COMMAND_KEYWORDS):
            return text
    return texts[0]


@contextlib.contextmanager
def _silence_c_stderr():
    """Silence C-level stderr (ALSA probe chatter) during device setup."""
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stderr.flush()
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)


def _ensure_sane_mic_gain():
    """Tone down a maxed 'Internal Mic Boost' on any capture card.

    Many laptops boot with the boost at +30dB on top of +30dB capture gain,
    which drowns the microphone in electrical noise and makes speech
    recognition impossible. Driver defaults tend to reset this on every
    reboot, so we enforce it at each startup (best effort, silent).
    """
    for card in range(6):
        try:
            probe = subprocess.run(
                ["amixer", "-c", str(card), "sget", "Internal Mic Boost"],
                capture_output=True, text=True, timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if probe.returncode != 0 or "30.00dB" not in probe.stdout:
            continue
        subprocess.run(
            ["amixer", "-c", str(card), "sset", "Internal Mic Boost", "0"],
            capture_output=True, timeout=3,
        )
        print("[ear] internal mic boost was maxed — toned it down for clean audio")


def _ensure_capture_volume():
    """Raise a near-muted default source.

    PipeWire may restore stale device volumes when capture streams reopen,
    leaving the microphone effectively deaf. Recognition needs a usable
    level, so bring anything below 60% back up (best effort, silent).
    """
    try:
        probe = subprocess.run(
            ["pactl", "get-source-volume", "@DEFAULT_SOURCE@"],
            capture_output=True, text=True, timeout=3,
        )
        match = re.search(r"/\s*(\d+)%", probe.stdout)
        if match and int(match.group(1)) < 60:
            subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "100%"],
                capture_output=True, timeout=3,
            )
            print("[ear] microphone capture volume was low — raised it")
    except (OSError, subprocess.SubprocessError):
        pass


class Ear:
    def __init__(self):
        self.phrases = queue.Queue()
        self._started = False
        self._service_error_reported = False
        # Live intake meter for the HUD visualiser (updated per audio chunk).
        self.raw_level = 0
        self.audio_level = 0.0  # smoothed 0.0..1.0
        self.level_history = collections.deque(maxlen=32)
        self._level_time = 0.0

    def _push_audio_level(self, rms: int):
        """Feed one RMS reading into the live meter + short history."""
        now = time.monotonic()
        self.raw_level = rms
        # Normalise: quiet room ~<500, loud speech ~7500+. Sqrt curve lifts whispers.
        norm = (rms - 500) / 7000.0
        norm = min(1.0, max(0.0, norm))
        norm = norm ** 0.6
        # Fast attack, slow release so bars jump with speech and fall smoothly.
        if norm > self.audio_level:
            self.audio_level = self.audio_level * 0.4 + norm * 0.6
        else:
            self.audio_level = self.audio_level * 0.85 + norm * 0.15
        self.level_history.append(self.audio_level)
        self._level_time = now

    def audio_snapshot(self):
        """Return (level 0..1, [history], age_seconds) for visualisers."""
        age = time.monotonic() - self._level_time if self._level_time else 999.0
        level = self.audio_level
        if age > 0.25:
            # No fresh chunks — decay toward silence instead of freezing.
            level *= max(0.0, 1.0 - (age - 0.25) * 4.0)
        return level, list(self.level_history), age

    def start(self):
        if self._started:
            return
        import speech_recognition as sr

        _ensure_sane_mic_gain()
        _ensure_capture_volume()
        self.recognizer = sr.Recognizer()
        microphone = sr.Microphone(device_index=MIC_DEVICE_INDEX)

        with _silence_c_stderr():
            source = microphone.__enter__()

        worker = threading.Thread(
            target=self._listen_loop,
            args=(self.recognizer, source),
            daemon=True,
        )
        worker.start()
        self._started = True
        print("[ear] microphone ready")

    def _listen_loop(self, recognizer, source):
        import speech_recognition as sr

        chunk = source.CHUNK
        width = source.SAMPLE_WIDTH
        rate = source.SAMPLE_RATE
        seconds_per_chunk = chunk / rate
        # Recent noise-floor history (~8 s). Median, so bursts don't count.
        history = collections.deque(maxlen=max(60, int(8 / seconds_per_chunk)))
        # Pre-roll: keep the last ~0.4 s of audio so the first syllable
        # ("work-" in "workspace") isn't clipped when the gate triggers late.
        preroll = collections.deque(maxlen=max(1, int(0.4 / seconds_per_chunk)))
        quiet_chunks_needed = max(1, int(0.6 / seconds_per_chunk))
        min_speech_chunks = max(1, int(0.3 / seconds_per_chunk))
        min_gate = 700  # never react to anything quieter than this
        last_gain_check = time.monotonic()

        while True:
            # PipeWire keeps re-restoring the ALSA boost on stream events;
            # re-check periodically so the mic stays usable mid-session.
            if time.monotonic() - last_gain_check > 30:
                last_gain_check = time.monotonic()
                _ensure_sane_mic_gain()
            try:
                data = source.stream.read(chunk)
            except Exception as exc:
                print(f"[ear] capture error: {exc}")
                time.sleep(0.1)
                continue
            if not data:
                continue
            level = audioop.rms(data, width)
            self._push_audio_level(level)
            history.append(level)
            preroll.append(data)
            gate = max(statistics.median(history) * 2.5, min_gate)
            if level < gate:
                continue

            # Speech started — record until ~0.6 s of quiet or the phrase cap.
            # Prepend the pre-roll so clipped first syllables survive.
            frames = list(preroll) + [data]
            quiet_run = 0
            deadline = time.monotonic() + PHRASE_TIME_LIMIT
            while time.monotonic() < deadline:
                try:
                    data = source.stream.read(chunk)
                except Exception as exc:
                    print(f"[ear] capture error: {exc}")
                    break
                if not data:
                    break
                frames.append(data)
                level = audioop.rms(data, width)
                self._push_audio_level(level)
                history.append(level)
                quiet_run = quiet_run + 1 if level < gate else 0
                if quiet_run >= quiet_chunks_needed:
                    break
            if len(frames) < min_speech_chunks:
                continue  # a click or burst, not speech

            audio = sr.AudioData(b"".join(frames), rate, width)
            try:
                # show_all=True returns every guess; _pick_transcript keeps
                # the one that looks most like a real command.
                result = recognizer.recognize_google(
                    audio, language=STT_LANGUAGE, show_all=True)
                text = _pick_transcript(result)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                if not self._service_error_reported:
                    print(f"[ear] speech service unreachable ({exc}); retrying...")
                    self._service_error_reported = True
                continue
            except Exception as exc:
                print(f"[ear] recognition error: {exc}")
                continue
            self._service_error_reported = False
            text = text.strip()
            if text:
                print(f"You: {text}")
                self.phrases.put(text)

    def next_phrase(self, timeout: float = 0.5) -> str:
        """Wait up to *timeout* seconds for a phrase; '' if silent."""
        try:
            return self.phrases.get(timeout=timeout)
        except queue.Empty:
            return ""

    def drain(self):
        """Discard any buffered phrases (e.g. while the mic is muted)."""
        while True:
            try:
                self.phrases.get_nowait()
            except queue.Empty:
                return


# Module-level convenience instance used by the app.
_default = None


def get_ear() -> Ear:
    global _default
    if _default is None:
        _default = Ear()
    return _default


def listen(timeout: int = 6) -> str:
    """Blocking single-shot listen (used by tests / simple scripts)."""
    ear = get_ear()
    ear.start()
    return ear.next_phrase(timeout=timeout)
