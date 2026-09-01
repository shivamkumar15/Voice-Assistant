#!/usr/bin/env python3
"""Alexa-style desktop assistant.

Always listens for a wake word ("Alexa"), then executes whatever command
follows: open YouTube in Chrome, play songs, control volume, take
screenshots, launch apps, and much more.

Usage:
    python alexa.py               # chat window + wake-word voice mode
    python alexa.py --no-wake     # treat every phrase as a command
    python alexa.py --no-mic      # chat window without the microphone
    python alexa.py --text        # terminal text mode (no window)
    python alexa.py --no-gui      # voice only, terminal output
"""

import argparse
import re
import threading

from assistant import ear, mouth
from assistant.brain import Brain
from assistant.config import ASSISTANT_NAME, EXIT_PHRASES, FOLLOWUP_TIMEOUT, WAKE_WORDS
from assistant.worker import strip_wake_word


def run_gui(no_wake: bool, voice: bool):
    """Full chat window: the worker thread runs voice + typed commands."""
    from assistant.gui import ChatWindow
    from assistant.worker import AssistantWorker

    worker = AssistantWorker(no_wake=no_wake, voice=voice)
    threading.Thread(target=worker.run, daemon=True).start()
    try:
        _install_sigint_handler()
        ChatWindow(worker).run()
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop()


def run_terminal(no_wake: bool):
    """Voice-only loop printing to the terminal (no window)."""
    brain = Brain()
    stop_event = threading.Event()

    print(f"{ASSISTANT_NAME} is awake. Say '{WAKE_WORDS[0]}' followed by a command.")
    print("Examples: 'alexa open youtube' · 'alexa play believer' · 'alexa volume up'")
    print(f"Say {' or '.join(EXIT_PHRASES[:2])} to quit.\n")
    try:
        mic = ear.get_ear()
        mic.start()
        while not stop_event.is_set():
            heard = mic.next_phrase(timeout=0.5)
            if not heard:
                continue

            if no_wake:
                command = heard
            else:
                had_wake, remainder = strip_wake_word(heard)
                if not had_wake:
                    continue  # ignore chatter that isn't addressed to us
                elif not remainder:
                    # Bare wake word -> short follow-up window.
                    mouth.speak("Yes?")
                    follow_up = mic.next_phrase(timeout=FOLLOWUP_TIMEOUT)
                    if not follow_up:
                        continue
                    command = follow_up
                else:
                    command = remainder

            normalized = re.sub(r"[.!?]+$", "", command.lower().strip())
            if normalized in EXIT_PHRASES:
                break

            reply = brain.handle(command)
            mouth.speak(reply)

        mouth.speak("Goodbye!")
    except Exception as exc:
        print(f"[assistant] stopped: {exc}")
    finally:
        stop_event.set()
        mouth.shutdown()


def _quit_on_signal():
    """GLib timer callback: quit the GUI when Ctrl+C arrives."""
    from gi.repository import Gtk

    Gtk.main_quit()
    return False


def _install_sigint_handler():
    from gi.repository import GLib

    try:
        from gi.repository import GLibUnix

        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, 2, _quit_on_signal)
    except (ImportError, AttributeError):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, _quit_on_signal)


def run_text_mode():
    brain = Brain()
    print(f"{ASSISTANT_NAME} text mode — type commands ('exit' to quit).\n")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if re.sub(r"[.!?]+$", "", line.lower().strip()) in EXIT_PHRASES:
            break
        reply = brain.handle(line)
        print(f"{ASSISTANT_NAME}: {reply}")


def main():
    parser = argparse.ArgumentParser(description=f"{ASSISTANT_NAME} desktop assistant")
    parser.add_argument("--no-wake", action="store_true",
                        help="treat every recognised phrase as a command")
    parser.add_argument("--no-mic", action="store_true",
                        help="start the chat window without the microphone")
    parser.add_argument("--text", action="store_true",
                        help="type commands in the terminal instead of using the microphone")
    parser.add_argument("--no-gui", action="store_true",
                        help="run without the chat window (terminal output only)")
    args = parser.parse_args()

    if args.text:
        run_text_mode()
        return

    use_gui = not args.no_gui
    if use_gui:
        try:
            from assistant import gui  # noqa: F401  (probes GTK availability)
        except ImportError:
            print("[gui] GTK unavailable — running voice-only mode")
            use_gui = False

    if use_gui:
        run_gui(no_wake=args.no_wake, voice=not args.no_mic)
    else:
        run_terminal(no_wake=args.no_wake)


if __name__ == "__main__":
    main()