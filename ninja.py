#!/usr/bin/env python3
"""Ninja — your desktop voice assistant.

Listens continuously and executes whatever you say: open YouTube in Chrome
and play songs, message people on WhatsApp, control volume and brightness,
take screenshots, launch apps, type and click for you, move the mouse, manage
windows, and much more. Chain tasks in one breath: "open youtube and play
believer".

Usage:
    python ninja.py               # HUD window + continuous listening (default)
    python ninja.py --wake-word   # only respond after hearing "Ninja"
    python ninja.py --no-mic      # HUD window without the microphone
    python ninja.py --text        # terminal text mode (no window)
    python ninja.py --no-gui      # voice only, terminal output
"""

import argparse
import re
import threading

from assistant import ear, mouth
from assistant.brain import Brain
from assistant.config import ASSISTANT_NAME, EXIT_PHRASES, FOLLOWUP_TIMEOUT, WAKE_WORDS
from assistant.worker import strip_wake_word


def run_gui(no_wake: bool, voice: bool):
    """Full HUD window: the worker thread runs voice + typed commands."""
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

    if no_wake:
        print(f"{ASSISTANT_NAME} is awake and listening continuously — just speak commands.")
        print("Examples: 'open youtube and play believer' · 'volume up' · 'message mom hello'")
        print("Say 'Ninja exit' to quit.\n")
    else:
        print(f"{ASSISTANT_NAME} is awake. Say '{WAKE_WORDS[0]}' followed by a command.")
        print("Examples: 'ninja open youtube' · 'ninja play believer' · 'ninja volume up'")
        print(f"Say {' or '.join(EXIT_PHRASES[:2])} to quit.\n")
    try:
        mic = ear.get_ear()
        mic.start()
        while not stop_event.is_set():
            heard = mic.next_phrase(timeout=0.5)
            if not heard:
                continue

            if no_wake:
                addressed, remainder = strip_wake_word(heard)
                if addressed and not remainder:
                    mouth.speak("Yes?")
                    follow_up = mic.next_phrase(timeout=FOLLOWUP_TIMEOUT)
                    if not follow_up:
                        continue
                    command, addressed = follow_up, True
                else:
                    command = remainder if addressed else heard
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
                addressed = True

            normalized = re.sub(r"[.!?]+$", "", command.lower().strip())
            if normalized in EXIT_PHRASES and (addressed or not no_wake):
                break

            handled, reply = brain.handle_chain(command)
            if handled or addressed:
                mouth.speak(reply)
            else:
                print(f"(heard, not a command: {command})")

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
    print(f"{ASSISTANT_NAME} text mode — type commands ('exit' to quit).")
    print("Chain tasks with 'and': open youtube and play believer\n")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if re.sub(r"[.!?]+$", "", line.lower().strip()) in EXIT_PHRASES:
            break
        _, reply = brain.handle_chain(line)
        print(f"{ASSISTANT_NAME}: {reply}")


def main():
    parser = argparse.ArgumentParser(description=f"{ASSISTANT_NAME} desktop assistant")
    parser.add_argument("--no-wake", dest="no_wake", action="store_true",
                        help="listen continuously, treat every phrase as a command (default)")
    parser.add_argument("--wake-word", dest="no_wake", action="store_false",
                        help="only respond after hearing the wake word")
    parser.set_defaults(no_wake=True)
    parser.add_argument("--no-mic", action="store_true",
                        help="start the HUD window without the microphone")
    parser.add_argument("--text", action="store_true",
                        help="type commands in the terminal instead of using the microphone")
    parser.add_argument("--no-gui", action="store_true",
                        help="run without the HUD window (terminal output only)")
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
