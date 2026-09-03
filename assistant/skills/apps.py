"""App skill: launch and quit desktop applications (Linux / macOS / Windows)."""

import shutil
import subprocess
import sys

import psutil

from . import hypr

# Spoken name -> launch command per platform
APPS = {
    "chrome": {"linux": "google-chrome-stable", "darwin": "Google Chrome", "win32": "chrome"},
    "google chrome": {"linux": "google-chrome-stable", "darwin": "Google Chrome", "win32": "chrome"},
    "firefox": {"linux": "firefox", "darwin": "Firefox", "win32": "firefox"},
    "code": {"linux": "code", "darwin": "Visual Studio Code", "win32": "code"},
    "vs code": {"linux": "code", "darwin": "Visual Studio Code", "win32": "code"},
    "vscode": {"linux": "code", "darwin": "Visual Studio Code", "win32": "code"},
    "visual studio code": {"linux": "code", "darwin": "Visual Studio Code", "win32": "code"},
    "text editor": {"linux": "gedit", "darwin": "TextEdit", "win32": "notepad"},
    "notepad": {"linux": "gedit", "darwin": "TextEdit", "win32": "notepad"},
    "editor": {"linux": "gedit", "darwin": "TextEdit", "win32": "notepad"},
    "calculator": {"linux": "gnome-calculator", "darwin": "Calculator", "win32": "calc"},
    "files": {"linux": "nautilus", "darwin": "Finder", "win32": "explorer"},
    "file manager": {"linux": "nautilus", "darwin": "Finder", "win32": "explorer"},
    "terminal": {"linux": "gnome-terminal", "darwin": "Terminal", "win32": "cmd"},
    "settings": {"linux": "gnome-control-center", "darwin": "System Settings", "win32": "ms-settings:"},
    "system monitor": {"linux": "gnome-system-monitor", "darwin": None, "win32": "taskmgr"},
    "spotify desktop": {"linux": "spotify", "darwin": "Spotify", "win32": "spotify"},
    "vlc": {"linux": "vlc", "darwin": "VLC", "win32": "vlc"},
    "discord": {"linux": "discord", "darwin": "Discord", "win32": "discord"},
    "libreoffice writer": {"linux": "lowriter", "darwin": None, "win32": None},
    "writer": {"linux": "lowriter", "darwin": None, "win32": None},
    "word": {"linux": "lowriter", "darwin": "Microsoft Word", "win32": "winword"},
    "excel": {"linux": "localc", "darwin": "Microsoft Excel", "win32": "excel"},
    "paint": {"linux": "gimp", "darwin": "Preview", "win32": "mspaint"},
}

# Process names used when killing an app
_PROCESS_NAMES = {
    "chrome": ["chrome"],
    "google chrome": ["chrome"],
    "firefox": ["firefox"],
    "code": ["code"],
    "vs code": ["code"],
    "vscode": ["code"],
    "vlc": ["vlc"],
    "discord": ["discord"],
    "spotify": ["spotify"],
    "calculator": ["gnome-calculator"],
    "text editor": ["gedit"],
    "notepad": ["gedit", "notepad.exe"],
}

# Spoken name -> substring of the Wayland window class, so "close <app>" can
# close windows gracefully through the compositor instead of killing processes.
_WINDOW_CLASSES = {
    "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "code": "code", "vs code": "code",
    "vscode": "code", "visual studio code": "code", "vlc": "vlc",
    "discord": "discord", "spotify": "spotify", "spotify desktop": "spotify",
    "calculator": "calculator", "text editor": "gedit", "notepad": "gedit",
    "editor": "gedit", "terminal": "kitty", "files": "nautilus",
    "file manager": "nautilus", "settings": "settings",
    "paint": "gimp",
}


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _launch_raw(name: str) -> bool:
    """Best-effort launch of an arbitrary command name."""
    path = shutil.which(name)
    if path:
        subprocess.Popen([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    if _platform_key() == "darwin":
        try:
            subprocess.run(["open", "-a", name], check=True)
            return True
        except Exception:
            return False
    return False


def launch_app(spoken_name: str):
    key = spoken_name.lower().strip()
    entry = APPS.get(key)
    if entry:
        target = entry.get(_platform_key())
        if target:
            try:
                # Prefer the compositor's exec: the app inherits a guaranteed
                # session environment (Wayland display, audio, portals).
                if hypr.available() and hypr.dispatch("exec", target):
                    return True, f"Opening {spoken_name}"
                if _launch_raw(target):
                    return True, f"Opening {spoken_name}"
                return False, f"{spoken_name} is not installed"
            except Exception as exc:
                return False, f"Could not open {spoken_name}: {exc}"
        return False, f"{spoken_name} is not supported on this platform"
    # Unknown app: try to run it directly.
    if hypr.available() and shutil.which(key.replace(" ", "-")):
        if hypr.dispatch("exec", key.replace(" ", "-")):
            return True, f"Trying to open {spoken_name}"
    if _launch_raw(key.replace(" ", "-")):
        return True, f"Trying to open {spoken_name}"
    return False, f"I don't know how to open {spoken_name}"


def close_app(spoken_name: str):
    key = spoken_name.lower().strip()

    # Graceful first: ask the compositor to close the app's windows.
    if hypr.available():
        needle = _WINDOW_CLASSES.get(key, key.replace(" ", "-"))
        closed = 0
        for client in hypr.clients():
            if not client.get("mapped"):
                continue
            wclass = (client.get("class") or "").lower()
            tokens = {needle, needle.replace("-", ""), needle.split()[0]}
            if any(t and t in wclass for t in tokens):
                if hypr.dispatch("closewindow", f"address:{client.get('address')}"):
                    closed += 1
        if closed:
            return True, f"Closed {spoken_name}"

    needles = _PROCESS_NAMES.get(key, [key.replace(" ", "")])
    killed = 0
    me = psutil.Process().pid
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if any(n in pname for n in needles) and proc.info["pid"] != me:
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        return True, f"Closed {spoken_name}"
    return False, f"{spoken_name} is not running"
