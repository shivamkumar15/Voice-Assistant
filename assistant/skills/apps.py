"""App skill: launch and quit desktop applications (Linux / macOS / Windows)."""

import shutil
import subprocess
import sys

import psutil

from . import hypr

# Spoken name -> launch command per platform.
# "linux" may be a single binary or a list of candidates tried in order,
# so distro renames (kitty vs gnome-terminal, telegram-desktop vs telegram)
# just work.
APPS = {
    "chrome": {"linux": ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"],
               "darwin": "Google Chrome", "win32": "chrome"},
    "google chrome": {"linux": ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"],
                      "darwin": "Google Chrome", "win32": "chrome"},
    "browser": {"linux": ["google-chrome-stable", "firefox", "chromium"],
                "darwin": "Google Chrome", "win32": "chrome"},
    "firefox": {"linux": "firefox", "darwin": "Firefox", "win32": "firefox"},
    "edge": {"linux": ["microsoft-edge", "microsoft-edge-stable"], "darwin": "Microsoft Edge",
             "win32": "msedge"},
    "code": {"linux": ["code", "codium", "vscodium"], "darwin": "Visual Studio Code", "win32": "code"},
    "vs code": {"linux": ["code", "codium", "vscodium"], "darwin": "Visual Studio Code", "win32": "code"},
    "vscode": {"linux": ["code", "codium", "vscodium"], "darwin": "Visual Studio Code", "win32": "code"},
    "visual studio code": {"linux": ["code", "codium", "vscodium"], "darwin": "Visual Studio Code",
                           "win32": "code"},
    "text editor": {"linux": ["gedit", "kate", "mousepad", "xed"], "darwin": "TextEdit",
                    "win32": "notepad"},
    "notepad": {"linux": ["gedit", "kate", "mousepad", "xed"], "darwin": "TextEdit",
                "win32": "notepad"},
    "editor": {"linux": ["gedit", "kate", "mousepad", "xed"], "darwin": "TextEdit",
               "win32": "notepad"},
    "calculator": {"linux": ["gnome-calculator", "kcalc", "mate-calc"], "darwin": "Calculator",
                   "win32": "calc"},
    "files": {"linux": ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"], "darwin": "Finder",
              "win32": "explorer"},
    "file manager": {"linux": ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"],
                     "darwin": "Finder", "win32": "explorer"},
    "terminal": {"linux": ["kitty", "gnome-terminal", "konsole", "xfce4-terminal",
                           "alacritty", "xterm"],
                 "darwin": "Terminal", "win32": "cmd"},
    "settings": {"linux": "gnome-control-center", "darwin": "System Settings",
                 "win32": "ms-settings:"},
    "system monitor": {"linux": ["gnome-system-monitor", "mate-system-monitor", "htop"],
                       "darwin": None, "win32": "taskmgr"},
    "task manager": {"linux": ["gnome-system-monitor", "mate-system-monitor", "htop"],
                     "darwin": None, "win32": "taskmgr"},
    "spotify": {"linux": "spotify", "darwin": "Spotify", "win32": "spotify"},
    "spotify desktop": {"linux": "spotify", "darwin": "Spotify", "win32": "spotify"},
    "music": {"linux": ["spotify", "rhythmbox", "vlc", "audacious"], "darwin": "Music",
              "win32": "spotify"},
    "vlc": {"linux": "vlc", "darwin": "VLC", "win32": "vlc"},
    "discord": {"linux": "discord", "darwin": "Discord", "win32": "discord"},
    "telegram": {"linux": ["telegram-desktop", "telegram"], "darwin": "Telegram",
                 "win32": None},
    "whatsapp": {"linux": ["whatsapp-for-linux", "whatsapp-desktop", "wasistlos"],
                 "darwin": "WhatsApp", "win32": None},
    "slack": {"linux": "slack", "darwin": "Slack", "win32": None},
    "zoom": {"linux": ["zoom", "zoom-client"], "darwin": "zoom.us", "win32": None},
    "teams": {"linux": "teams", "darwin": "Microsoft Teams", "win32": None},
    "steam": {"linux": "steam", "darwin": "Steam", "win32": None},
    "obs": {"linux": "obs", "darwin": "OBS", "win32": None},
    "mail": {"linux": ["thunderbird", "geary", "evolution"], "darwin": "Mail", "win32": None},
    "email": {"linux": ["thunderbird", "geary", "evolution"], "darwin": "Mail", "win32": None},
    "thunderbird": {"linux": "thunderbird", "darwin": "Thunderbird", "win32": None},
    "libreoffice writer": {"linux": "lowriter", "darwin": None, "win32": None},
    "writer": {"linux": "lowriter", "darwin": None, "win32": None},
    "word": {"linux": "lowriter", "darwin": "Microsoft Word", "win32": "winword"},
    "excel": {"linux": "localc", "darwin": "Microsoft Excel", "win32": "excel"},
    "paint": {"linux": ["gimp", "pinta", "kolourpaint"], "darwin": "Preview", "win32": "mspaint"},
    "camera": {"linux": ["cheese", "guvcview"], "darwin": "Photo Booth", "win32": None},
}

# Spoken name -> flatpak app IDs tried when no native binary is found.
FLATPAK_IDS = {
    "whatsapp": ["com.github.eneshecan.WhatsappForLinux", "io.github.mimbrero.WhatsAppDesktop"],
    "telegram": ["org.telegram.desktop"],
    "discord": ["com.discordapp.Discord"],
    "spotify": ["com.spotify.Client"],
    "slack": ["com.slack.Slack"],
    "zoom": ["us.zoom.Zoom"],
    "steam": ["com.valvesoftware.Steam"],
    "vlc": ["org.videolan.VLC"],
    "code": ["com.visualstudio.code"],
    "vs code": ["com.visualstudio.code"],
    "vscode": ["com.visualstudio.code"],
    "firefox": ["org.mozilla.firefox"],
    "chrome": ["com.google.Chrome"],
    "google chrome": ["com.google.Chrome"],
    "obs": ["com.obsproject.Studio"],
    "thunderbird": ["org.mozilla.Thunderbird"],
}

# Process names used when killing an app
_PROCESS_NAMES = {
    "chrome": ["chrome"],
    "google chrome": ["chrome"],
    "browser": ["chrome", "firefox", "chromium"],
    "firefox": ["firefox"],
    "code": ["code"],
    "vs code": ["code"],
    "vscode": ["code"],
    "visual studio code": ["code"],
    "vlc": ["vlc"],
    "discord": ["discord"],
    "telegram": ["telegram"],
    "whatsapp": ["whatsapp", "wasistlos"],
    "slack": ["slack"],
    "zoom": ["zoom"],
    "teams": ["teams"],
    "steam": ["steam"],
    "spotify": ["spotify"],
    "spotify desktop": ["spotify"],
    "music": ["spotify", "rhythmbox", "vlc"],
    "calculator": ["gnome-calculator", "kcalc"],
    "text editor": ["gedit", "kate"],
    "notepad": ["gedit", "notepad.exe"],
    "terminal": ["kitty", "gnome-terminal", "konsole", "alacritty", "xterm"],
    "files": ["nautilus", "dolphin", "thunar", "nemo"],
    "file manager": ["nautilus", "dolphin", "thunar", "nemo"],
    "obs": ["obs"],
    "thunderbird": ["thunderbird"],
    "mail": ["thunderbird", "geary", "evolution"],
}

# Spoken name -> substring of the Wayland window class, so "close <app>" can
# close windows gracefully through the compositor instead of killing processes.
_WINDOW_CLASSES = {
    "chrome": "chrome", "google chrome": "chrome", "browser": "chrome",
    "firefox": "firefox", "edge": "edge", "code": "code", "vs code": "code",
    "vscode": "code", "visual studio code": "code", "vlc": "vlc",
    "discord": "discord", "telegram": "telegram", "whatsapp": "whatsapp",
    "slack": "slack", "zoom": "zoom", "teams": "teams", "steam": "steam",
    "spotify": "spotify", "spotify desktop": "spotify", "music": "spotify",
    "calculator": "calculator", "text editor": "gedit", "notepad": "gedit",
    "editor": "gedit", "terminal": "kitty", "files": "nautilus",
    "file manager": "nautilus", "settings": "settings",
    "paint": "gimp", "camera": "cheese", "mail": "thunderbird",
    "email": "thunderbird", "thunderbird": "thunderbird", "obs": "obs",
}


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _candidates(spoken_name: str) -> list:
    """Native binaries for *spoken_name* on this platform, in order."""
    entry = APPS.get(spoken_name.lower().strip())
    if not entry:
        return []
    target = entry.get(_platform_key())
    if not target:
        return []
    return [target] if isinstance(target, str) else list(target)


def _flatpak_ids(spoken_name: str) -> list:
    return FLATPAK_IDS.get(spoken_name.lower().strip(), [])


def _flatpak_available(app_id: str) -> bool:
    if not shutil.which("flatpak"):
        return False
    try:
        result = subprocess.run(
            ["flatpak", "info", app_id],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def desktop_available(spoken_name: str) -> bool:
    """True when *spoken_name* can be launched as a real desktop app here."""
    key = spoken_name.lower().strip()
    if _platform_key() == "darwin":
        entry = APPS.get(key, {})
        name = entry.get("darwin")
        if isinstance(name, str):
            import os

            if os.path.isdir(f"/Applications/{name}.app"):
                return True
        return False
    if any(shutil.which(c) for c in _candidates(key)):
        return True
    return any(_flatpak_available(i) for i in _flatpak_ids(key))


def can_launch(spoken_name: str) -> bool:
    """True when we have any way to open *spoken_name* (app or raw binary)."""
    key = spoken_name.lower().strip()
    if desktop_available(key):
        return True
    return bool(shutil.which(key.replace(" ", "-")))


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


def _launch_flatpak(app_id: str) -> bool:
    if not shutil.which("flatpak"):
        return False
    try:
        subprocess.Popen(["flatpak", "run", app_id],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def launch_app(spoken_name: str):
    key = spoken_name.lower().strip()
    entry = APPS.get(key)
    if entry:
        targets = _candidates(key)
        if _platform_key() == "darwin" and entry.get("darwin"):
            try:
                # Prefer the compositor's exec: the app inherits a guaranteed
                # session environment (Wayland display, audio, portals).
                if _launch_raw(entry["darwin"]):
                    return True, f"Opening {spoken_name}"
            except Exception as exc:
                return False, f"Could not open {spoken_name}: {exc}"
            return False, f"{spoken_name} is not installed"
        if targets:
            try:
                for target in targets:
                    if not shutil.which(target):
                        continue
                    if hypr.available() and hypr.dispatch("exec", target):
                        return True, f"Opening {spoken_name}"
                    if _launch_raw(target):
                        return True, f"Opening {spoken_name}"
                for app_id in _flatpak_ids(key):
                    if _flatpak_available(app_id) and _launch_flatpak(app_id):
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
