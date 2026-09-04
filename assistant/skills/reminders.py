"""Timers & reminders skill: "set a timer for 10 minutes",
"remind me to call mom in 20 minutes". Fires with voice + desktop alert."""

import re
import shutil
import subprocess
import threading
import time

_timers = {}  # id -> {"label": str, "fires_at": float, "timer": Timer}
_next_id = 1
_lock = threading.Lock()

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
}


def parse_duration(text: str):
    """Parse "10 minutes tea" -> (600 seconds, "tea"). Returns (None, '') if none."""
    text = (text or "").strip().lower()
    m = re.match(r"^(half an hour|half hour|an hour|a hour)\b\s*(.*)$", text)
    if m:
        return 1800, m.group(2).strip()
    m = re.match(
        r"^(\d+(?:\.\d+)?|[a-z]+)?\s*"
        r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b\s*(.*)$",
        text,
    )
    if not m:
        return None, ""
    amount, unit, rest = m.group(1), m.group(2), m.group(3).strip()
    if not amount:
        amount = 1
    elif re.fullmatch(r"\d+(?:\.\d+)?", amount):
        amount = float(amount)
    else:
        amount = _NUMBER_WORDS.get(amount)
        if amount is None:
            return None, ""
    unit = unit[0]
    seconds = amount * {"s": 1, "m": 60, "h": 3600}[unit]
    return int(seconds), rest


def _fire(timer_id: int):
    with _lock:
        entry = _timers.pop(timer_id, None)
    if not entry:
        return
    label = entry["label"]
    message = f"Timer done: {label}" if label != "timer" else "Time is up!"
    try:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "Ninja", message], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        from .. import mouth

        mouth.speak(message)
    except Exception:
        pass


def set_timer(seconds: int, label: str = "timer"):
    global _next_id
    seconds = max(1, int(seconds))
    label = (label or "timer").strip() or "timer"
    with _lock:
        timer_id = _next_id
        _next_id += 1
        t = threading.Timer(seconds, _fire, args=(timer_id,))
        t.daemon = True
        _timers[timer_id] = {"label": label, "fires_at": time.time() + seconds,
                             "timer": t}
        t.start()
    spoken = _speak_duration(seconds)
    if label == "timer":
        return True, f"Timer set for {spoken}"
    return True, f"Reminder set for {spoken}: {label}"


def _speak_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        text = f"{minutes} minute{'s' if minutes != 1 else ''}"
        return text if not secs else f"{text} and {secs} seconds"
    hours, minutes = divmod(minutes, 60)
    text = f"{hours} hour{'s' if hours != 1 else ''}"
    return text if not minutes else f"{text} and {minutes} minutes"


def list_timers():
    with _lock:
        items = [(i, e) for i, e in sorted(_timers.items())]
    if not items:
        return True, "No timers running"
    parts = []
    for i, entry in items:
        left = max(0, int(entry["fires_at"] - time.time()))
        parts.append(f"#{i} {entry['label']} in {_speak_duration(left)}")
    return True, "Timers: " + "; ".join(parts)


def cancel_timer(timer_id=None):
    """Cancel one timer by id, or all when *timer_id* is None."""
    with _lock:
        if timer_id is None:
            ids = list(_timers)
        else:
            ids = [timer_id] if timer_id in _timers else []
        for i in ids:
            try:
                _timers[i]["timer"].cancel()
            except Exception:
                pass
            _timers.pop(i, None)
    if not ids:
        return False, "No such timer"
    if timer_id is None:
        return True, f"Cancelled {len(ids)} timer{'s' if len(ids) != 1 else ''}"
    return True, f"Cancelled timer #{timer_id}"
