"""Desktop notifications and a small in-process notification inbox."""

from __future__ import annotations

import collections
import shutil
import subprocess
import threading
import time

_history: collections.deque[dict] = collections.deque(maxlen=50)
_lock = threading.Lock()


def _record(title: str, message: str) -> None:
    with _lock:
        _history.append({
            "title": (title or "Ninja").strip() or "Ninja",
            "message": (message or "").strip(),
            "timestamp": time.time(),
        })


def publish(title: str, message: str) -> tuple[bool, str]:
    title = (title or "Ninja").strip() or "Ninja"
    message = (message or "").strip()
    if not message:
        return False, "What should the notification say?"
    _record(title, message)
    if not shutil.which("notify-send"):
        return True, "I recorded that notification, but desktop alerts are unavailable"
    try:
        result = subprocess.run(
            ["notify-send", title, message],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, "Notification sent"
    except (OSError, subprocess.SubprocessError):
        pass
    return True, "I recorded the notification"


def recent(limit: int = 8) -> list[dict]:
    with _lock:
        items = list(_history)
    return items[-max(1, min(int(limit), len(items) or 1)):]


def read_recent(limit: int = 8) -> tuple[bool, str]:
    items = recent(limit)
    if not items:
        return True, "I have no recent assistant notifications"
    parts = []
    for item in items:
        message = item["message"]
        if len(message) > 100:
            message = message[:97].rstrip() + "…"
        parts.append(message)
    return True, "Recent notifications: " + "; ".join(parts)
