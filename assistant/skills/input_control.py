"""Keyboard & mouse control skill.

Backends: ydotool (Wayland) -> wtype (Wayland, typing only) -> pyautogui (X11).

ydotool injects events straight into the kernel input layer, so it works on
Wayland (Hyprland etc.) for every window, native or XWayland. It needs the
`ydotoold` daemon; we start it on demand, which requires the user to be in
the `input` group (access to /dev/uinput).
"""

import os
import shutil
import subprocess
import sys
import time
import types

from . import hypr

# --- key tables ---------------------------------------------------------------

_KEY_ALIASES = {
    "enter": "enter", "return": "enter", "tab": "tab", "space": "space",
    "escape": "escape", "esc": "escape", "backspace": "backspace",
    "delete": "delete", "up": "up", "down": "down", "left": "left",
    "right": "right", "home": "home", "end": "end",
    "page up": "pageup", "pageup": "pageup", "page down": "pagedown",
    "pagedown": "pagedown", "print screen": "printscreen",
    "printscreen": "printscreen", "caps lock": "capslock",
    "capslock": "capslock", "insert": "insert",
}

_COMBO_WORDS = {
    "copy": ["ctrl", "c"], "paste": ["ctrl", "v"], "cut": ["ctrl", "x"],
    "select all": ["ctrl", "a"], "save": ["ctrl", "s"],
    "undo": ["ctrl", "z"], "redo": ["ctrl", "y"], "find": ["ctrl", "f"],
    "new tab": ["ctrl", "t"], "close tab": ["ctrl", "w"],
    "switch window": ["alt", "tab"], "minimise": ["super", "h"],
}

# Linux input event codes, needed because ydotool speaks raw keycodes.
_YDO_KEYS = {
    "enter": 28, "tab": 15, "space": 57, "backspace": 14,
    "escape": 1, "delete": 111, "insert": 110, "home": 102, "end": 107,
    "pageup": 104, "pagedown": 109, "up": 103, "down": 108,
    "left": 105, "right": 106, "printscreen": 99, "capslock": 58,
    "ctrl": 29, "control": 29, "alt": 56, "shift": 42,
    "super": 125, "meta": 125, "cmd": 125, "command": 125, "win": 125,
    "volumeup": 115, "volumedown": 114, "mute": 113,
    "playpause": 164, "next": 171, "previous": 165,
}
# QWERTY rows and the keycode each row starts at.
for _offset, _row in ((16, "qwertyuiop"), (30, "asdfghjkl"), (44, "zxcvbnm")):
    for _i, _ch in enumerate(_row):
        _YDO_KEYS[_ch] = _offset + _i
for _i in range(10):  # digit row: 1=2 ... 9=10, 0=11
    _YDO_KEYS[str((_i + 1) % 10)] = _i + 2
for _i in range(12):  # F1..F12
    _YDO_KEYS[f"f{_i + 1}"] = (59 + _i) if _i < 10 else (87 + _i - 10)

_MOUSE_BUTTONS = {"left": 0xC0, "right": 0xC1, "middle": 0xC2}

# --- ydotool daemon -------------------------------------------------------------

_daemon_ready: bool | None = None


def _ydotool_socket() -> str:
    return os.environ.get(
        "YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket"
    )


def _ensure_daemon() -> bool:
    """Make sure ydotoold is up; returns True when the client can talk to it."""
    global _daemon_ready
    if _daemon_ready is not None:
        return _daemon_ready
    if not shutil.which("ydotool"):
        _daemon_ready = False
        return False
    sock = _ydotool_socket()
    if not os.path.exists(sock):
        try:
            subprocess.Popen(
                ["ydotoold"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            _daemon_ready = False
            return False
        for _ in range(30):  # ~1.5 s for the socket to appear
            if os.path.exists(sock):
                break
            time.sleep(0.05)
    _daemon_ready = os.path.exists(sock)
    if not _daemon_ready:
        print("[input] ydotoold unavailable — keyboard/mouse control limited "
              "to X11 windows (add yourself to the `input` group for Wayland)")
    return _daemon_ready


def _ydo(*args) -> bool:
    if not _ensure_daemon():
        return False
    try:
        result = subprocess.run(
            ["ydotool", *args], capture_output=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _ydo_key_sequence(parts) -> bool:
    """Send a press/release sequence like ['ctrl', 'c'] as a chord."""
    codes = []
    for part in parts:
        code = _YDO_KEYS.get(part.lower())
        if code is None:
            return False
        codes.append(code)
    events = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    return _ydo("key", *events)


# --- pyautogui fallback (X11 only) ----------------------------------------------

def _pyautogui():
    # mouseinfo (pyautogui dep) calls sys.exit() at import when tkinter is
    # missing; stub it out since we never use its GUI.
    if "mouseinfo" not in sys.modules:
        stub = types.ModuleType("mouseinfo")
        stub.mouseInfo = lambda *args, **kwargs: None
        sys.modules["mouseinfo"] = stub

    # Help Xlib find credentials: sessions usually set XAUTHORITY, but when
    # they don't, point at the standard file (or /dev/null for open servers).
    if not os.environ.get("XAUTHORITY"):
        from pathlib import Path

        home_auth = Path.home() / ".Xauthority"
        os.environ["XAUTHORITY"] = str(home_auth) if home_auth.exists() else "/dev/null"

    import pyautogui

    pyautogui.FAILSAFE = False
    return pyautogui


# --- public API -----------------------------------------------------------------

def type_text(text: str):
    if _ydo("type", "--", text):
        return True, "Typed it"
    if shutil.which("wtype"):
        try:
            subprocess.run(["wtype", text], check=True, timeout=5)
            return True, "Typed it"
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        _pyautogui().typewrite(text, interval=0.02)
        return True, "Typed it"
    except Exception as exc:
        return False, f"Typing failed: {exc}"


def press_key(spoken: str):
    key = _KEY_ALIASES.get(spoken.lower().strip(), spoken.lower().strip().replace(" ", ""))
    if _ydo_key_sequence([key]):
        return True, f"Pressed {key}"
    try:
        _pyautogui().press(key)
        return True, f"Pressed {key}"
    except Exception as exc:
        return False, f"Couldn't press {spoken}: {exc}"


def hotkey(spoken: str):
    keys = _COMBO_WORDS.get(spoken.lower().strip())
    if not keys:
        mapping = {"control": "ctrl", "command": "cmd", "option": "alt", "esc": "esc"}
        keys = [mapping.get(p, p) for p in spoken.lower().replace("+", " ").split()]
    if _ydo_key_sequence(keys):
        return True, "Done"
    try:
        _pyautogui().hotkey(*keys)
        return True, "Done"
    except Exception as exc:
        return False, f"Shortcut failed: {exc}"


def move_mouse(direction: str = "", distance: int = 300, x: int | None = None,
               y: int | None = None):
    """Relative move by direction, or absolute move when x/y are given.

    Hyprland's movecursor dispatcher is used first — ydotool's uinput
    absolute positioning is unreliable under compositors.
    """
    deltas = {"left": (-distance, 0), "right": (distance, 0),
              "up": (0, -distance), "down": (0, distance)}
    if hypr.available():
        if x is not None and y is not None:
            if hypr.move_cursor(x, y):
                return True, f"Mouse at {x}, {y}"
        elif direction in deltas:
            pos = hypr.cursor_pos()
            size = hypr.screen_size()
            if pos:
                dx, dy = deltas[direction]
                nx, ny = pos[0] + dx, pos[1] + dy
                if size:
                    nx = max(0, min(nx, size[0] - 1))
                    ny = max(0, min(ny, size[1] - 1))
                if hypr.move_cursor(nx, ny):
                    return True, "Moved it"
        else:
            return False, "Where should the mouse go?"
    if x is not None and y is not None:
        ok = _ydo("mousemove", "-a", str(x), str(y))
    elif direction in deltas:
        dx, dy = deltas[direction]
        ok = _ydo("mousemove", str(dx), str(dy))
    else:
        return False, "Where should the mouse go?"
    if ok:
        return True, "Moved it" if (x is None) else f"Mouse at {x}, {y}"
    try:
        pag = _pyautogui()
        if x is not None and y is not None:
            pag.moveTo(x, y)
        else:
            dx, dy = deltas[direction]
            pag.moveRel(dx, dy)
        return True, "Moved it"
    except Exception as exc:
        return False, f"Mouse move failed: {exc}"


def click(button: str = "left"):
    if _ydo("click", str(_MOUSE_BUTTONS.get(button, _MOUSE_BUTTONS["left"]))):
        return True, f"{button.capitalize()} clicked"
    try:
        pag = _pyautogui()
        if button == "right":
            pag.rightClick()
        else:
            pag.click()
        return True, f"{button.capitalize()} clicked"
    except Exception as exc:
        return False, f"Click failed: {exc}"


def double_click():
    if _ydo("click", "-r", "2", str(_MOUSE_BUTTONS["left"])):
        return True, "Double clicked"
    try:
        _pyautogui().doubleClick()
        return True, "Double clicked"
    except Exception as exc:
        return False, f"Click failed: {exc}"


def scroll(direction: str, amount: int = 400):
    # ydotool wheel: value is amount / 120 wheel steps; positive = up.
    if _ydo("mousemove", "-w", "-x", "0", "-y", str(amount if direction == "up" else -amount)):
        return True, f"Scrolled {direction}"
    try:
        _pyautogui().scroll(amount if direction == "up" else -amount)
        return True, f"Scrolled {direction}"
    except Exception as exc:
        return False, f"Scroll failed: {exc}"
