"""Window management skill.

Backends, in order: Hyprland (Wayland), xdotool (X11), pygetwindow.

Hyprland has no real minimise — "minimise" stashes a window in a special
workspace (see hypr.STASH) and "restore my windows" brings the stash back.
"""

import re
import shutil
import subprocess

from . import hypr


def _xdotool(*args):
    if not shutil.which("xdotool"):
        return None
    return subprocess.run(
        ["xdotool", *args], capture_output=True, text=True
    ).stdout.strip()


def _pygetwindow():
    try:
        import pygetwindow as gw

        return gw
    except Exception:  # not installed or unsupported platform (Linux)
        return None


# --- listing -----------------------------------------------------------------

def list_windows():
    if hypr.available():
        titles = [
            c.get("title") or c.get("class") or ""
            for c in hypr.clients()
            if c.get("mapped") and c.get("workspace", {}).get("id", 0) >= 0
        ]
        titles = [t for t in titles if t]
        if titles:
            shown = ", ".join(titles[:10])
            extra = f" and {len(titles) - 10} more" if len(titles) > 10 else ""
            return True, f"Open windows: {shown}{extra}"
        return False, "There are no open windows right now"

    out = _xdotool("search", "--onlyvisible", "--name", ".")
    if out:
        titles = []
        for wid in out.splitlines()[:15]:
            name = _xdotool("getwindowname", wid)
            if name and name not in titles:
                titles.append(name)
        if titles:
            return True, "Open windows: " + ", ".join(titles)
    gw = _pygetwindow()
    if gw:
        titles = [t for t in gw.getAllTitles() if t]
        if titles:
            return True, "Open windows: " + ", ".join(titles[:10])
    return False, "I couldn't list the windows"


# --- focus --------------------------------------------------------------------

def focus_window(title: str):
    if hypr.available():
        client = hypr.find_client_wait(title)
        if client and hypr.focus_client(client):
            name = client.get("title") or client.get("class") or title
            return True, f"Switched to {name}"
        return False, f"No window matching {title}"

    wid = _window_id(title)
    if wid:
        _xdotool("windowactivate", wid)
        return True, f"Switched to {title}"
    return False, f"No window matching {title}"


# --- close --------------------------------------------------------------------

def close_window(title: str = ""):
    if hypr.available():
        if title:
            client = hypr.find_client_wait(title)
            if client and hypr.dispatch("closewindow",
                                        f"address:{client.get('address')}"):
                return True, "Closed it"
            return False, f"Couldn't find a window called {title}"
        if hypr.dispatch("killactive"):
            return True, "Closed it"
        return False, "Couldn't close the window"

    target = _window_id(title) if title else _xdotool("getactivewindow")
    if target:
        _xdotool("windowclose", target)
        return True, "Closed it"
    return False, "Couldn't find that window"


# --- minimise / maximise --------------------------------------------------------

def minimize_window(title: str = ""):
    if hypr.available():
        client = hypr.find_client_wait(title) if title else hypr.active_client()
        if client and hypr.stash_client(client):
            name = client.get("title") or client.get("class") or "it"
            return True, f"Stashed {name} away"
        return False, f"Couldn't minimise {title or 'the window'}"

    if title:
        wid = _window_id(title)
        if wid and _xdotool("windowminimize", "sync", wid) is not None:
            return True, f"Minimised {title}"
        return False, f"Couldn't find a window called {title}"
    active = _xdotool("getactivewindow")
    if active:
        _xdotool("windowminimize", "sync", active)
        return True, "Minimised"
    return False, "Couldn't minimise"


def maximize_window(title: str = ""):
    if hypr.available():
        client = hypr.find_client_wait(title) if title else hypr.active_client()
        if not client:
            return False, f"Couldn't find a window called {title}" if title \
                else "Couldn't maximise"
        # `fullscreen 2` is Hyprland's "maximise without true fullscreen";
        # it toggles, so check the current state first.
        already = client.get("fullscreen") == 2
        if hypr.focus_client(client) and hypr.dispatch("fullscreen", "2"):
            return True, "Back to normal size" if already else "Maximised"
        return False, "Couldn't maximise"

    target = _window_id(title) if title else _xdotool("getactivewindow")
    if target:
        _xdotool("windowsize", target, "100%", "100%")
        _xdotool("windowactivate", target)
        return True, "Maximised"
    return False, "Couldn't maximise"


def minimize_all():
    """Show the desktop: stash every window on the current workspace."""
    if hypr.available():
        ws = hypr.active_workspace_id()
        if ws is None:
            return False, "I couldn't read your workspaces"
        moved = 0
        for client in hypr.clients():
            if client.get("mapped") and client.get("workspace", {}).get("id") == ws:
                if hypr.stash_client(client):
                    moved += 1
        if moved:
            return True, "Showing the desktop"
        return False, "No windows to minimise on this workspace"

    out = _xdotool("key", "super+d")
    if out is None:
        gw = _pygetwindow()
        if gw:
            for win in gw.getAllWindows():
                try:
                    win.minimize()
                except Exception:
                    pass
            return True, "Minimised everything"
        return False, "No window manager tool available"
    return True, "Showing the desktop"


def restore_all():
    """Bring back everything stashed by minimize_all / minimize_window."""
    if hypr.available():
        if not hypr.stashed_clients():
            return False, "Nothing is minimised"
        if hypr.show_stash():
            return True, "Your windows are back"
        return False, "Couldn't restore the windows"

    gw = _pygetwindow()
    if gw:
        restored = 0
        for win in gw.getAllWindows():
            try:
                if win.isMinimized:
                    win.restore()
                    restored += 1
            except Exception:
                pass
        if restored:
            return True, "Your windows are back"
    return False, "Nothing is minimised"


# --- workspaces ---------------------------------------------------------------

_WORKSPACE_WORDS = {
    "first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3,
    "fourth": 4, "four": 4, "fifth": 5, "five": 5, "sixth": 6, "six": 6,
    "seventh": 7, "seven": 7, "eighth": 8, "eight": 8, "ninth": 9, "nine": 9,
    "tenth": 10, "ten": 10,
}


def parse_workspace_number(text):
    """'1st' / 'first' / 'workspace 2' -> int, else None. Accepts 1..20."""
    t = (text or "").lower().strip()
    m = re.search(r"(\d+)\s*(?:st|nd|rd|th)?\b", t)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 20 else None
    for word, n in _WORKSPACE_WORDS.items():
        if re.search(rf"\b{word}\b", t):
            return n
    return None


def goto_workspace(number: int):
    """Switch to workspace *number*."""
    if number is None:
        return False, "Which workspace? Say: go to workspace 2"
    if hypr.available():
        if hypr.dispatch("workspace", str(number)):
            return True, f"Switched to workspace {number}"
        return False, f"Couldn't switch to workspace {number}"
    if shutil.which("xdotool"):
        if _xdotool("set_desktop", str(number - 1)) is not None:
            return True, f"Switched to workspace {number}"
    return False, "Workspace switching isn't available here"


def cycle_workspace(direction: str):
    """Switch to the next / previous workspace."""
    if hypr.available():
        delta = "e+1" if direction == "next" else "e-1"
        if hypr.dispatch("workspace", delta):
            return True, f"Switched to the {direction} workspace"
        return False, "Couldn't switch workspaces"
    if shutil.which("xdotool"):
        try:
            cur = int(_xdotool("get_desktop") or 0)
            total = int(_xdotool("get_num_desktops") or 1)
            nxt = (cur + (1 if direction == "next" else -1)) % max(1, total)
        except (TypeError, ValueError):
            return False, "Couldn't switch workspaces"
        if _xdotool("set_desktop", str(nxt)) is not None:
            return True, f"Switched to the {direction} workspace"
    return False, "Workspace switching isn't available here"


def move_window_to_workspace(number: int, title: str = ""):
    """Send the active (or named) window to a workspace and follow it."""
    if number is None:
        return False, "Which workspace? Say: move this window to workspace 2"
    if hypr.available():
        if title:
            client = hypr.find_client_wait(title)
            if not client:
                return False, f"No window matching {title}"
            addr = client.get("address")
            if hypr.dispatch("movetoworkspace", f"{number},address:{addr}") \
                    and hypr.dispatch("workspace", str(number)):
                return True, f"Moved {title} to workspace {number}"
            return False, f"Couldn't move {title} to workspace {number}"
        if hypr.dispatch("movetoworkspace", str(number)):
            return True, f"Moved the window to workspace {number}"
        return False, "Couldn't move the window"
    wid = _window_id(title) if title else _xdotool("getactivewindow")
    if wid and _xdotool("set_desktop_for_window", wid, str(number - 1)) is not None:
        _xdotool("set_desktop", str(number - 1))
        return True, f"Moved the window to workspace {number}"
    return False, "Couldn't move the window"


# --- lookup helpers (X11) -------------------------------------------------------

def _window_id(title: str):
    """Find a window id whose title contains *title* (case-insensitive)."""
    out = _xdotool("search", "--name", title)
    if not out:
        lowered = title.lower()
        for wid in (_xdotool("search", "--name", "") or "").splitlines():
            name = (_xdotool("getwindowname", wid) or "").lower()
            if lowered in name:
                return wid
        return None
    return out.splitlines()[0]
