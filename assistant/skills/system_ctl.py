"""System control skill: volume, brightness, screenshots, media, power,
battery, mic mute. Uses whatever backend each desktop offers (PipeWire/pactl,
brightnessctl, playerctl, grim, systemctl) with X11 fallbacks."""

import os
import shutil
import subprocess
import time


def _run(cmd, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _spawn(cmd):
    """Start a long-lived command detached from the assistant."""
    subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# --- Volume -------------------------------------------------------------------

def volume_up(step: int = 10):
    if shutil.which("pactl"):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"])
        return True, f"Volume up {step} percent"
    if shutil.which("amixer"):
        _run(["amixer", "-q", "sset", "Master", f"{step}%+"])
        return True, f"Volume up {step} percent"
    return False, "No audio mixer found"


def volume_down(step: int = 10):
    if shutil.which("pactl"):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"])
        return True, f"Volume down {step} percent"
    if shutil.which("amixer"):
        _run(["amixer", "-q", "sset", "Master", f"{step}%-"])
        return True, f"Volume down {step} percent"
    return False, "No audio mixer found"


def volume_set(level: int):
    level = max(0, min(100, level))
    if shutil.which("pactl"):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
        return True, f"Volume set to {level} percent"
    if shutil.which("amixer"):
        _run(["amixer", "-q", "sset", "Master", f"{level}%"])
        return True, f"Volume set to {level} percent"
    return False, "No audio mixer found"


def volume_mute():
    if shutil.which("pactl"):
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        return True, "Toggled mute"
    if shutil.which("amixer"):
        _run(["amixer", "-q", "sset", "Master", "toggle"])
        return True, "Toggled mute"
    return False, "No audio mixer found"


def mic_mute():
    if not shutil.which("pactl"):
        return False, "I can't control the microphone here"
    _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])
    state = _run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"]).stdout.lower()
    if "yes" in state:
        return True, "Microphone muted"
    return True, "Microphone is live again"


# --- Brightness ---------------------------------------------------------------

def _brightness_pct() -> int:
    try:
        time.sleep(0.15)  # amdgpu backlight updates asynchronously after a set
        cur = int(_run(["brightnessctl", "get"]).stdout.strip() or 0)
        top = int(_run(["brightnessctl", "max"]).stdout.strip() or 1)
        return max(0, min(100, round(cur * 100 / top)))
    except (ValueError, OSError):
        return -1


def brightness_up(step: int = 10):
    if not shutil.which("brightnessctl"):
        return False, "brightnessctl is not installed"
    _run(["brightnessctl", "set", f"+{step}%"])
    pct = _brightness_pct()
    return True, f"Brightness at {pct} percent" if pct >= 0 else "Brightness up"


def brightness_down(step: int = 10):
    if not shutil.which("brightnessctl"):
        return False, "brightnessctl is not installed"
    _run(["brightnessctl", "set", f"{step}%-"])
    pct = _brightness_pct()
    return True, f"Brightness at {pct} percent" if pct >= 0 else "Brightness down"


def brightness_set(level: int):
    if not shutil.which("brightnessctl"):
        return False, "brightnessctl is not installed"
    level = max(0, min(100, level))
    _run(["brightnessctl", "set", f"{level}%"])
    return True, f"Brightness set to {level} percent"


# --- Media keys ---------------------------------------------------------------

def media_state() -> str:
    """Best-effort playback state across registered players: playing/paused/stopped."""
    if shutil.which("playerctl"):
        result = _run(["playerctl", "status"])
        out = (result.stdout or "").strip().lower()
        if "playing" in out:
            return "playing"
        if "paused" in out:
            return "paused"
    return "stopped"


def media_key(key: str):
    """key in: playpause, next, previous.

    Chromium exposes an MPRIS player only while media is loaded, so a
    Stopped/"no players" answer is normal when nothing is open. When no
    player responds, a raw XF86 media key (via ydotool uinput) is injected
    instead — the browser and most players act on it globally.
    """
    playerctl = {"playpause": "play-pause", "next": "next", "previous": "previous"}
    if key in playerctl and shutil.which("playerctl"):
        result = _run(["playerctl", "-a", playerctl[key]])
        if result.returncode == 0:
            replies = {"playpause": "Toggled playback", "next": "Skipped ahead",
                       "previous": "Went back a track"}
            return True, replies[key]
    mapping = {
        "playpause": ["XF86AudioPlay"],
        "next": ["XF86AudioNext"],
        "previous": ["XF86AudioPrev"],
    }
    keysyms = mapping.get(key)
    if not keysyms:
        return False, "Unknown media key"
    from . import input_control

    if input_control._ensure_daemon() and input_control._ydo("key", *keysyms):
        return True, "Done"
    if shutil.which("xdotool"):
        _run(["xdotool", "key", *keysyms])
        return True, "Done"
    return False, "Media keys unsupported here"


# --- Screenshot ---------------------------------------------------------------

def screenshot(area: bool = False):
    from datetime import datetime

    home = os.path.expanduser("~/Pictures")
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")

    if shutil.which("grim"):
        cmd = ["grim", path]
        if area and shutil.which("slurp"):
            region = _run(["slurp"]).stdout.strip()
            if region:
                cmd = ["grim", "-g", region, path]
        result = _run(cmd)
        if result.returncode == 0 and os.path.exists(path):
            if shutil.which("wl-copy"):
                try:
                    with open(path, "rb") as image:
                        subprocess.run(["wl-copy"], stdin=image, timeout=5)
                except (OSError, subprocess.SubprocessError):
                    pass
            return True, f"Screenshot saved in Pictures as {os.path.basename(path)}"

    candidates = [
        ["gnome-screenshot", "-f", path],
        ["spectacle", "-b", "-n", "-o", path],
        ["scrot", path],
        ["import", "-window", "root", path],
        ["maim", path],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            result = _run(cmd)
            if result.returncode == 0 and os.path.exists(path):
                return True, f"Screenshot saved in Pictures as {os.path.basename(path)}"
    try:
        import pyautogui

        pyautogui.screenshot(path)
        return True, "Screenshot saved in Pictures"
    except Exception:
        pass
    return False, "I couldn't take a screenshot"


# --- Power / session ----------------------------------------------------------

def lock_screen():
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("hyprlock"):
        try:
            _spawn(["hyprlock"])
            return True, "Locking the screen. See you!"
        except OSError:
            pass
    cmds = [
        ["swaylock"],
        ["loginctl", "lock-session"],
        ["gnome-screensaver-command", "-l"],
        ["xdg-screensaver", "lock"],
    ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            _run(cmd)
            return True, "Locking the screen. See you!"
    return False, "I couldn't lock the screen"


def log_out():
    from . import hypr

    if hypr.available() and hypr.dispatch("exit"):
        return True, "Logging out. Bye!"
    return False, "I can't log out of this session"


def suspend_computer():
    try:
        _run(["systemctl", "suspend"])
        return True, "Going to sleep. Wake me when you need me!"
    except Exception:
        return False, "I couldn't suspend the system"


def shutdown_computer():
    for cmd in (["systemctl", "poweroff"], ["shutdown", "-h", "now"]):
        try:
            if _run(cmd).returncode == 0:
                return True, "Shutting down. Goodbye!"
        except Exception:
            continue
    return False, "I don't have permission to shut down"


def restart_computer():
    for cmd in (["systemctl", "reboot"], ["shutdown", "-r", "now"]):
        try:
            if _run(cmd).returncode == 0:
                return True, "Restarting now"
        except Exception:
            continue
    return False, "I don't have permission to restart"


# --- Status -------------------------------------------------------------------

def system_status():
    import psutil

    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    parts = [f"CPU at {int(cpu)} percent", f"memory at {int(mem)} percent"]
    battery = None
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError):
        pass
    if battery is not None:
        state = "charging" if battery.power_plugged else "on battery"
        parts.append(f"battery at {int(battery.percent)} percent and {state}")
    disk = psutil.disk_usage("/").percent
    parts.append(f"disk at {int(disk)} percent")
    return True, ". ".join(parts)


def uptime_report():
    import psutil

    secs = int(time.time() - psutil.boot_time())
    hours, rem = divmod(secs, 3600)
    minutes = rem // 60
    return True, f"The system has been up for {hours} hours and {minutes} minutes"


# --- Radios / trash / clipboard -------------------------------------------------

def wifi(on: bool):
    if not shutil.which("nmcli"):
        return False, "WiFi control needs nmcli here"
    result = _run(["nmcli", "radio", "wifi", "on" if on else "off"])
    if result.returncode == 0:
        return True, f"WiFi turned {'on' if on else 'off'}"
    return False, "I couldn't switch the WiFi"


def wifi_connect(ssid: str = ""):
    """Join a network. With a name, connect to it; without one, bounce the
    radio so the machine rejoins its saved network."""
    if not shutil.which("nmcli"):
        return False, "WiFi control needs nmcli here"
    ssid = (ssid or "").strip()
    if ssid:
        result = _run(["nmcli", "dev", "wifi", "connect", ssid], check=False)
        if result.returncode == 0:
            return True, f"Connected to {ssid}"
        return False, f"I couldn't connect to {ssid}"
    _run(["nmcli", "radio", "wifi", "off"])
    time.sleep(1)
    result = _run(["nmcli", "radio", "wifi", "on"])
    if result.returncode == 0:
        return True, "Reconnecting to WiFi"
    return False, "I couldn't reconnect the WiFi"


def bluetooth(on: bool):
    if shutil.which("bluetoothctl"):
        result = _run(["bluetoothctl", "power", "on" if on else "off"])
        if result.returncode == 0:
            return True, f"Bluetooth turned {'on' if on else 'off'}"
    if shutil.which("rfkill"):
        kind = "bluetooth"
        result = _run(["rfkill", "unblock" if on else "block", kind])
        if result.returncode == 0:
            return True, f"Bluetooth turned {'on' if on else 'off'}"
    return False, "Bluetooth control isn't available here"


def empty_trash():
    if shutil.which("gio"):
        result = _run(["gio", "trash", "--empty"])
        if result.returncode == 0:
            return True, "Trash emptied"
    return False, "I couldn't empty the trash"


def read_clipboard():
    """Speak back the current clipboard text (truncated)."""
    text = ""
    if shutil.which("wl-paste"):
        text = _run(["wl-paste", "--no-newline"]).stdout
    elif shutil.which("xclip"):
        text = _run(["xclip", "-o", "-selection", "clipboard"]).stdout
    elif shutil.which("xsel"):
        text = _run(["xsel", "--clipboard", "--output"]).stdout
    else:
        return False, "No clipboard tool found here"
    text = (text or "").strip()
    if not text:
        return True, "The clipboard is empty"
    short = text if len(text) <= 140 else text[:140] + "…"
    return True, f"Clipboard says: {short}"
