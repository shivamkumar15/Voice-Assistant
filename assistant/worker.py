"""Assistant worker: the voice/text loop that powers every front-end.

Front-ends (the GTK chat window or a plain terminal) talk to the worker
through two thread-safe queues:

    worker.commands   front-end -> worker
        ("text", str)   process a typed command
        ("mic", bool)   enable/disable consuming microphone phrases
        ("tts", bool)   enable/disable spoken replies
        ("quit", None)  stop the worker

    worker.events     worker -> front-end
        ("state", s)         s in {"idle", "listening", "working", "speaking"}
        ("user", text)       what the user said or typed
        ("assistant", text)  the assistant's reply
        ("notice", text)     informational system message
        ("quit", None)       the worker has stopped
"""

import queue
import re
import threading
import time

from . import ear, mouth
from .brain import Brain
from .config import ASSISTANT_NAME, EXIT_PHRASES, FOLLOWUP_TIMEOUT, WAKE_WORDS


def strip_wake_word(text: str):
    """Return (had_wake_word, remaining_command)."""
    lowered = text.lower().strip()
    for wake in WAKE_WORDS:
        if lowered == wake:
            return True, ""
        # "alexa open youtube" / "hey alexa, open youtube"
        m = re.match(rf"^(?:hey |hi |ok |okay )?{wake}[,!.]?\s+(.+)$", lowered)
        if m:
            return True, m.group(1).strip()
    return False, ""


class AssistantWorker:
    """Runs the assistant loop on its own thread.

    The GUI (or any other front-end) stays responsive: it sends commands and
    receives events through the queues documented in the module docstring.
    """

    def __init__(self, no_wake: bool = False, voice: bool = True, tts: bool = True):
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.brain = Brain()
        self.no_wake = no_wake
        self.voice = voice
        self.mic_enabled = voice
        self.tts_enabled = tts
        self.mic = None

    # --- front-end API -------------------------------------------------------

    def emit(self, event):
        self.events.put(event)

    def stop(self):
        """Ask the worker to shut down (safe to call from any thread)."""
        self.stop_event.set()
        self.commands.put(("quit", None))

    # --- main loop -----------------------------------------------------------

    def run(self):
        try:
            if self.voice:
                try:
                    self.mic = ear.get_ear()
                    self.mic.start()
                except Exception as exc:
                    print(f"[ear] microphone unavailable: {exc}")
                    self.emit(("notice",
                               "Microphone unavailable — you can still type commands."))
                    self.mic = None
                    self.mic_enabled = False
            self.emit((
                "notice",
                f"{ASSISTANT_NAME} is awake. Say '{WAKE_WORDS[0]}' followed by a "
                "command, or type one below. Say 'exit' to quit.",
            ))
            self.emit(("state", self._idle_state()))
            while not self.stop_event.is_set():
                if self._drain_commands():
                    break
                if self.mic is not None and self.mic_enabled:
                    heard = self.mic.next_phrase(timeout=0.2)
                    if heard:
                        self.handle_voice(heard)
                elif self.mic is not None:
                    self.mic.drain()  # keep dropping phrases while muted
                    time.sleep(0.1)
                else:
                    time.sleep(0.1)
        except Exception as exc:
            print(f"[assistant] stopped: {exc}")
            self.emit(("notice", f"Assistant stopped: {exc}"))
        finally:
            self.stop_event.set()
            mouth.shutdown()
            self.emit(("quit", None))

    def _drain_commands(self) -> bool:
        """Handle pending front-end commands; True when a quit was requested."""
        while True:
            try:
                kind, payload = self.commands.get_nowait()
            except queue.Empty:
                return False
            if kind == "quit":
                return True
            if kind == "text":
                self.handle_command(payload)
            elif kind == "mic":
                self.mic_enabled = bool(payload)
                if self.mic_enabled and self.mic is not None:
                    self.mic.drain()  # drop anything captured while muted
                self.emit(("state", self._idle_state()))
            elif kind == "tts":
                self.tts_enabled = bool(payload)

    # --- processing ----------------------------------------------------------

    def handle_voice(self, heard: str):
        self.emit(("user", heard))
        if self.no_wake:
            command = heard
        else:
            had_wake, remainder = strip_wake_word(heard)
            if not had_wake:
                return  # ignore chatter that isn't addressed to us
            if not remainder:
                # Bare wake word -> short follow-up window.
                self.emit(("state", "speaking"))
                self.emit(("assistant", "Yes?"))
                self._speak("Yes?")
                follow_up = self._wait_follow_up()
                if not follow_up:
                    self.emit(("state", self._idle_state()))
                    return
                self.emit(("user", follow_up))
                command = follow_up
            else:
                command = remainder
        self.handle_command(command, echo=False)

    def _wait_follow_up(self) -> str:
        """Wait for a follow-up phrase, staying responsive to front-end commands."""
        deadline = time.monotonic() + FOLLOWUP_TIMEOUT
        while not self.stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ""
            if self._drain_commands():
                self.stop_event.set()
                return ""
            heard = self.mic.next_phrase(timeout=min(0.3, remaining))
            if heard:
                return heard
        return ""

    def handle_command(self, text: str, echo: bool = True):
        text = (text or "").strip()
        if not text:
            return
        if echo:
            print(f"You: {text}")
            self.emit(("user", text))

        normalized = re.sub(r"[.!?]+$", "", text.lower().strip())
        if normalized in EXIT_PHRASES:
            self.emit(("assistant", "Goodbye!"))
            self._speak("Goodbye!")
            self.stop_event.set()
            return

        self.emit(("state", "working"))
        try:
            reply = self.brain.handle(text)
        except Exception as exc:
            reply = f"Something went wrong handling that: {exc}"
        self.emit(("assistant", reply))
        self.emit(("state", "speaking"))
        self._speak(reply)
        self.emit(("state", self._idle_state()))

    # --- helpers -------------------------------------------------------------

    def _speak(self, text: str):
        if not text:
            return
        if self.tts_enabled:
            mouth.speak(text)  # also echoes to the terminal
        else:
            print(f"{ASSISTANT_NAME}: {text}")

    def _idle_state(self) -> str:
        listening = self.voice and self.mic_enabled and self.mic is not None
        return "listening" if listening else "idle"