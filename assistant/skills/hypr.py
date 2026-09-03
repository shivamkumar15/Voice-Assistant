"""Hyprland helpers: hyprctl wrappers and window lookup (Wayland).

Used by the window / input / app skills as the preferred backend whenever
the assistant runs inside a Hyprland session. The instance signature is
normally inherited from the session environment; when it is missing (e.g.
the assistant was started by a systemd unit or a launcher that scrubs env)
we fall back to the newest session listed in /tmp/hypr.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

# Special workspace used as the "minimised" stash. Hyprland has no real
# minimise; stashing a window there and toggling it back is the idiomatic
# equivalent (and what "restore my windows" undoes).
STASH = "assistant"

_sig = None


def _instance_sig() -> str | None:
    global _sig
    if _sig is None:
        _sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        if not _sig:
            sessions = Path("/tmp/hypr")
            if sessions.is_dir():
                newest = max(sessions.iterdir(), key=lambda p: p.stat().st_mtime,
                             default=None)
                _sig = newest.name if newest else ""
    return _sig or None


def available() -> bool:
    return bool(shutil.which("hyprctl")) and _instance_sig() is not None


def _run(*args, timeout: float = 5) -> str | None:
    if not available():
        return None
    env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE=_instance_sig())
    try:
        result = subprocess.run(
            ["hyprctl", *args], capture_output=True, text=True,
            env=env, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def dispatch(*args) -> bool:
    """Run `hyprctl dispatch ...`; True when Hyprland accepted it."""
    out = _run("dispatch", *args)
    return out is not None and out.strip().startswith("ok")


def clients() -> list:
    out = _run("-j", "clients")
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def active_client() -> dict:
    out = _run("-j", "activewindow")
    if not out:
        return {}
    try:
        return json.loads(out) or {}
    except json.JSONDecodeError:
        return {}


def active_workspace_id() -> int | None:
    out = _run("-j", "activeworkspace")
    if not out:
        return None
    try:
        return (json.loads(out) or {}).get("id")
    except json.JSONDecodeError:
        return None


def find_client(query: str) -> dict | None:
    """Find a mapped window whose class or title contains *query*.

    Matches across spacing variants so spoken names like "google chrome"
    hit the class "google-chrome".
    """
    q = query.lower().strip()
    if not q:
        return None
    variants = {q, q.replace(" ", "-"), q.replace(" ", "")}
    for client in clients():
        if not client.get("mapped"):
            continue
        haystack = (
            (client.get("class") or "") + "\n" + (client.get("title") or "")
        ).lower()
        if any(v in haystack for v in variants if v):
            return client
    return None


def find_client_wait(query: str, timeout: float = 2.5) -> dict | None:
    """find_client with a short retry — freshly launched windows take a
    moment to appear, and spoken commands shouldn't race them."""
    deadline = time.monotonic() + timeout
    while True:
        client = find_client(query)
        if client is not None or time.monotonic() >= deadline:
            return client
        time.sleep(0.25)


def cursor_pos() -> tuple[int, int] | None:
    out = _run("cursorpos")
    if not out or "," not in out:
        return None
    try:
        x, y = out.strip().split(",")
        return int(x), int(y)
    except ValueError:
        return None


def screen_size() -> tuple[int, int] | None:
    out = _run("-j", "monitors")
    if not out:
        return None
    try:
        monitors = json.loads(out)
    except json.JSONDecodeError:
        return None
    width = height = 0
    for monitor in monitors:
        width = max(width, monitor.get("x", 0) + monitor.get("width", 0))
        height = max(height, monitor.get("y", 0) + monitor.get("height", 0))
    return (width, height) or None


def move_cursor(x: int, y: int) -> bool:
    return dispatch("movecursor", str(x), str(y))


def focus_client(client: dict | None) -> bool:
    """Focus a client, un-stashing it first when it lives in the stash."""
    if not client:
        return False
    if client.get("workspace", {}).get("id", 0) < 0 and dispatch(
        "togglespecialworkspace", STASH
    ):
        pass
    return dispatch("focuswindow", f"address:{client.get('address')}")


def stash_client(client: dict) -> bool:
    return dispatch(
        "movetoworkspacesilent",
        f"special:{STASH}",
        f"address:{client.get('address')}",
    )


def stashed_clients() -> list:
    return [c for c in clients() if c.get("mapped")
            and c.get("workspace", {}).get("id", 0) < 0]


def show_stash() -> bool:
    return dispatch("togglespecialworkspace", STASH)
