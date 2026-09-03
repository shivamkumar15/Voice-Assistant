"""Microphone input: one persistent capture stream feeding recognised phrases
into a queue. Keeping the stream open avoids per-phrase reopen latency and the
ALSA device-probe noise."""

import contextlib
import os
import queue

import sys
import threading

from .config import LISTEN_TIMEOUT, MIC_DEVICE_INDEX, PHRASE_TIME_LIMIT


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


class Ear:
    def __init__(self):
        self.phrases = queue.Queue()
        self._started = False
        self._service_error_reported = False

    def start(self):
        if self._started:
            return
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        microphone = sr.Microphone(device_index=MIC_DEVICE_INDEX)

        with _silence_c_stderr():
            source = microphone.__enter__()
            recognizer.adjust_for_ambient_noise(source, duration=1)

        worker = threading.Thread(
            target=self._listen_loop,
            args=(recognizer, source),
            daemon=True,
        )
        worker.start()
        self._started = True
        print("[ear] microphone ready")

    def _listen_loop(self, recognizer, source):
        import speech_recognition as sr

        while True:
            try:
                audio = recognizer.listen(
                    source, timeout=None, phrase_time_limit=PHRASE_TIME_LIMIT
                )
            except Exception as exc:
                print(f"[ear] capture error: {exc}")
                continue
            try:
                text = recognizer.recognize_google(audio)
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


def listen(timeout: int = LISTEN_TIMEOUT) -> str:
    """Blocking single-shot listen (used by tests / simple scripts)."""
    ear = get_ear()
    ear.start()
    return ear.next_phrase(timeout=timeout)
