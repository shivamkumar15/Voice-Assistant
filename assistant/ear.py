"""Microphone input: one persistent capture stream feeding recognised phrases
into a queue. Keeping the stream open avoids per-phrase reopen latency and the
ALSA device-probe noise.

Phrases are gated on a median-based noise floor rather than the stock
SpeechRecognition dynamic threshold: laptop mics produce short loud bursts
(fan spin-up, EMI) that the stock threshold chases upward, leaving the
assistant deaf. A median floor over recent history ignores bursts.

Transcription itself is pluggable. The default runs OpenAI Whisper locally via
faster-whisper (STT_PROVIDER=auto): it is fully offline, needs no API key, and
beats the keyless Google endpoint on accents and jargon. Google Web Speech
stays wired in as a fallback so a missing package or a failed model load
degrades to "still listens" rather than "no mic".
"""

try:
    import audioop
except ModuleNotFoundError:
    audioop = None

import collections
import contextlib
import io
import math
import os
import queue
import re
import statistics
import wave
from array import array
import subprocess
import sys
import threading
import time

from .config import (
    MIC_DEVICE_INDEX,
    PHRASE_TIME_LIMIT,
    STT_LANGUAGE,
    STT_PROVIDER,
    STT_WHISPER_BEAMS,
    STT_WHISPER_COMPUTE_TYPE,
    STT_WHISPER_DEVICE,
    STT_WHISPER_HOTWORDS,
    STT_WHISPER_MODEL,
    STT_WHISPER_MODEL_DIR,
)


_COMMAND_KEYWORDS = (
    "workspace", "volume", "brightness", "screenshot", "youtube", "whatsapp",
    "telegram", "terminal", "vscode", "chrome", "firefox", "timer", "reminder",
    "bluetooth", "wifi", "clipboard", "trash", "mouse", "click", "scroll",
    "type", "press", "open", "close", "focus", "minimise", "minimize",
    "maximise", "maximize", "play", "pause", "weather", "joke", "lock",
    "sleep", "shutdown", "restart", "notification", "notifications", "file",
    "files", "folder", "directory", "pdf", "document", "summarize", "summary",
    "study", "plan", "git", "code", "monitor", "screen", "email", "form",
)


def _rms(data: bytes, width: int) -> int:
    if audioop is not None:
        return audioop.rms(data, width)
    if not data:
        return 0
    if width == 1:
        samples = [abs(value - 128) for value in data]
    elif width == 2:
        sample_array = array("h")
        sample_array.frombytes(data[:len(data) - len(data) % 2])
        samples = [value * value for value in sample_array]
    elif width == 4:
        sample_array = array("i")
        sample_array.frombytes(data[:len(data) - len(data) % 4])
        samples = [value * value for value in sample_array]
    else:
        samples = [value * value for value in data]
    return int(math.sqrt(sum(samples) / max(1, len(samples))))


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


# --- Speech-to-text provider ------------------------------------------------

_whisper_importable = None


def whisper_available() -> bool:
    """True when the faster-whisper package is importable."""
    global _whisper_importable
    if _whisper_importable is None:
        try:
            import faster_whisper  # noqa: F401
            _whisper_importable = True
        except ImportError:
            _whisper_importable = False
    return _whisper_importable


def resolve_stt_provider() -> str:
    """'whisper' or 'google' per STT_PROVIDER (auto prefers local Whisper)."""
    want = (STT_PROVIDER or "auto").strip().lower()
    if want == "whisper":
        return "whisper"
    if want == "google":
        return "google"
    return "whisper" if whisper_available() else "google"


def _whisper_language():
    """Our BCP-47 STT_LANGUAGE ('en-US') as Whisper's ISO-639-1 ('en').

    None lets Whisper detect the language itself.
    """
    code = (STT_LANGUAGE or "en").strip().lower()
    if not code or code == "auto":
        return None
    return code.split("-", 1)[0].strip() or "en"


def _wav_bytes(frames, rate: int, width: int) -> bytes:
    """Wrap captured PCM chunks in a WAV header, entirely in memory.

    Feeding Whisper a WAV (rather than a raw array) lets faster-whisper do the
    48kHz -> 16kHz resample with PyAV's proper polyphase filter, instead of the
    naive decimation that turns chipmunk speech into garbage.
    """
    return _wrap_wav(b"".join(frames), rate, width)


def _wrap_wav(payload: bytes, rate: int, width: int) -> bytes:
    """Put a WAV header in front of raw PCM, in memory (no temp file)."""
    if width not in (1, 2, 4):
        raise ValueError(f"unsupported sample width: {width}")
    if width != 2:
        # sr.Microphone can be configured for 1- or 4-byte samples, and
        # decode_audio only takes the WAV container. Convert rather than let
        # it fail deep inside PyAV, where the message would be unhelpful.
        # "B" not "b": 8-bit WAV samples are unsigned, centred on 128.
        samples = array({1: "B", 4: "i"}[width])
        samples.frombytes(payload[:len(payload) - len(payload) % width])
        if width == 1:  # unsigned 8-bit is centred on 128, not 0
            values = [min(32767, max(-32768, (value - 128) * 256))
                      for value in samples]
        else:
            values = [value >> 16 for value in samples]
        payload = array("h", values).tobytes()
        width = 2
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(payload)
    return buffer.getvalue()


def _probe_tone_wav(rate: int = 16000, seconds: float = 0.4) -> bytes:
    """A short 440Hz tone, used to prove a device can actually run Whisper.

    Deliberately not silence: with vad_filter on, a silent clip is dropped
    before the encoder is ever touched, so probing with it would happily pass
    on a device that cannot run anything.
    """
    import numpy as np

    t = np.arange(int(rate * seconds), dtype=np.float32) / rate
    tone = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
    return _wrap_wav(tone.tobytes(), rate, 2)


def _cuda_present() -> bool:
    """True when a CUDA device is visible at all (not yet proven usable)."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() >= 1
    except Exception:
        return False


class WhisperEngine:
    """Local speech-to-text with OpenAI Whisper (via faster-whisper).

    Fully offline: the model is fetched from Hugging Face on first use, cached
    under STT_WHISPER_MODEL_DIR, then held in memory for the session. The
    engine is only ever touched from the single listen thread, so the model
    handle needs no locking.
    """

    def __init__(self, model=None, device=None, compute_type=None):
        self.model_name = model or STT_WHISPER_MODEL
        self.requested_device = (device or STT_WHISPER_DEVICE or "auto").lower()
        self.requested_compute = (compute_type or STT_WHISPER_COMPUTE_TYPE
                                  or "auto").lower()
        self._model = None
        self.device = None

    def _build(self, device: str, compute_type: str):
        """Load the model on *device* and prove it can run an encode.

        The smoke test is not paranoia. CTranslate2 happily reports a CUDA
        device and accepts the model, then fails on the *first inference* when
        cuBLAS/cuDNN are missing (a bare driver install with no
        nvidia-cublas-cu12). Probing with real audio is the only way to know
        before the user's first spoken phrase dies on a raw RuntimeError.
        """
        from faster_whisper import WhisperModel

        model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(STT_WHISPER_MODEL_DIR),
        )
        segments, _info = model.transcribe(
            io.BytesIO(_probe_tone_wav()), language="en", beam_size=1,
            without_timestamps=True,
        )
        list(segments)  # the generator is lazy: this is what runs the encoder
        return model

    def load(self):
        """Build the model, downloading it on first run. Idempotent."""
        if self._model is not None:
            return self._model

        started = time.monotonic()
        attempts = []
        if self.requested_device == "auto":
            if _cuda_present():
                attempts.append(("cuda", "float16"))
            # int8 on CPU is roughly twice the speed of float32 for a loss you
            # cannot hear on short commands.
            attempts.append(("cpu", "int8"))
        else:
            compute = self.requested_compute
            if compute == "auto":
                compute = "float16" if self.requested_device == "cuda" else "int8"
            attempts.append((self.requested_device, compute))

        errors = []
        for device, compute in attempts:
            try:
                self._model = self._build(device, compute)
            except Exception as exc:
                errors.append(f"{device}: {exc}")
                print(f"[ear] whisper unusable on {device} ({exc})")
                continue
            self.device = device
            print(f"[ear] whisper ready — {self.model_name} on "
                  f"{device}/{compute} ({time.monotonic() - started:.1f}s, "
                  "local speech-to-text)")
            return self._model

        self._model = None
        raise RuntimeError(f"could not load whisper model "
                           f"'{self.model_name}' ({'; '.join(errors)})")

    def transcribe(self, wav: bytes) -> str:
        """Transcribe a mono WAV blob to text. '' means nothing intelligible.

        The knobs below are what make this usable as a live command recogniser
        rather than a batch transcriber, and each one is a guard against a
        specific Whisper failure that is normally invisible: silence becoming
        words, or one word repeating until the time limit runs out.
        """
        model = self.load()
        segments, _info = model.transcribe(
            io.BytesIO(wav),
            language=_whisper_language(),
            beam_size=STT_WHISPER_BEAMS,
            # Silero VAD inside Whisper trims the leading/trailing silence our
            # own gate left in, and is the main defence against Whisper
            # hallucinating a sentence out of a cough.
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            # Whisper's classic failure mode is looping one phrase forever
            # ("thank you. thank you. thank you."). Every phrase here is
            # independent, so never carry text over from the previous one, and
            # treat trailing silence as the end of the utterance.
            condition_on_previous_text=False,
            hallucination_silence_threshold=2,
            # Prime the decoder with the assistant's vocabulary. This is what
            # turns "works box" into "workspace" and "harry armor" into
            # "haryana". Kept short on purpose: a long list biases the decoder
            # toward saying those words at all, so a bigger model with the same
            # list turned "what is the weather" into "whatsapp weather".
            hotwords=STT_WHISPER_HOTWORDS.strip() or None,
            without_timestamps=True,
        )
        # transcribe() is a lazy generator: iterating here (not at the call) is
        # what actually runs inference, so exceptions surface inside the caller's
        # try/except rather than at an unrelated point later.
        return " ".join(segment.text.strip() for segment in segments).strip()


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
        self.provider = resolve_stt_provider()
        self.whisper = WhisperEngine() if self.provider == "whisper" else None
        # Serialises the single recogniser, and is held while the listener is
        # paused so a phrase never records over the assistant's own voice.
        self._stt_lock = threading.RLock()
        self._paused = threading.Event()
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

        # Warm the model up off-thread: the first load downloads and
        # initialises weights, which would otherwise be charged to whichever
        # phrase happens to arrive first.
        if self.whisper is not None:
            threading.Thread(target=self._warm_whisper, daemon=True).start()

        worker = threading.Thread(
            target=self._listen_loop,
            args=(self.recognizer, source),
            daemon=True,
        )
        worker.start()
        self._started = True
        print(f"[ear] microphone ready (speech-to-text: {self.provider})")

    def pause(self):
        """Stop accepting phrases until resume() (used while the assistant speaks).

        Without this the microphone hears the reply through the speakers and
        transcribes it, so the assistant talks to itself. Cheap and safe to
        call from any thread; the resume costs one dropped phrase at worst.
        """
        self._paused.set()

    def resume(self):
        """Undo pause() and throw away anything captured while paused."""
        if self._paused.is_set():
            self._paused.clear()
            self.drain()

    def _warm_whisper(self):
        """Load the model in the background; fall back to Google on failure."""
        try:
            self.whisper.load()
        except Exception as exc:
            print(f"[ear] whisper unavailable ({exc}) — using Google instead")
            self.provider = "google"
            self.whisper = None

    def _transcribe_serialised(self, recognizer, frames, rate, width) -> str:
        """Run _transcribe under a lock shared with self-pausing.

        Local Whisper holds the GIL through a multi-hundred-millisecond C++
        decode, which would otherwise stall the main worker thread between
        phrases (frozen HUD, sluggish wake-word stripping).
        """
        with self._stt_lock:
            return self._transcribe(recognizer, frames, rate, width)

    def _transcribe(self, recognizer, frames, rate, width) -> str:
        """Transcribe one captured phrase with the active provider.

        Returns '' for silence or unintelligible audio. Whichever provider is
        in use, an error here is reported once and then swallowed: a failed
        phrase must never take the listener down.
        """
        import speech_recognition as sr

        if self.provider == "whisper":
            return self.whisper.transcribe(_wav_bytes(frames, rate, width))

        # show_all=True returns every guess; _pick_transcript keeps the one
        # that looks most like a real command.
        audio = sr.AudioData(b"".join(frames), rate, width)
        result = recognizer.recognize_google(
            audio, language=STT_LANGUAGE, show_all=True)
        return _pick_transcript(result)

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
            if self._paused.is_set():
                time.sleep(0.05)
                continue
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
            level = _rms(data, width)
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
                level = _rms(data, width)
                self._push_audio_level(level)
                history.append(level)
                quiet_run = quiet_run + 1 if level < gate else 0
                if quiet_run >= quiet_chunks_needed:
                    break
            if len(frames) < min_speech_chunks:
                continue  # a click or burst, not speech

            try:
                text = self._transcribe_serialised(recognizer, frames, rate, width)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                if not self._service_error_reported:
                    print(f"[ear] speech service unreachable ({exc}); retrying...")
                    self._service_error_reported = True
                continue
            except Exception as exc:
                if not self._service_error_reported:
                    print(f"[ear] {self.provider} recognition error: {exc}")
                    self._service_error_reported = True
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
