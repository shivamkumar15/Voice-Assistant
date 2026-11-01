"""NINJA — Aurora desktop interface.

A chat-first layout for a voice assistant:

    left     slim navigation rail (home, system, memory, jobs, console)
    center   live voice stage, conversation, quick actions, composer
    right    contextual insight pages (weather, performance, memory, jobs)

The window talks to AssistantWorker through its command/event queues, so the
interface never blocks on the microphone, the brain or speech output.
"""

import math
import queue
import threading
from datetime import datetime

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .config import WAKE_WORDS, WEATHER_CITY_DEFAULT  # noqa: E402
from .worker import AssistantWorker  # noqa: E402

DISPLAY_NAME = "NINJA"
CITY_DEFAULT = ""  # resolved from memory / config at fetch time

# Aurora palette, also used by the Cairo voice visualiser.
VIOLET = (0.486, 0.361, 1.000)   # #7c5cff
CYAN = (0.133, 0.827, 0.933)     # #22d3ee
MINT = (0.204, 0.827, 0.600)     # #34d399

NAV_ITEMS = [
    ("overview", "⌂", "HOME"),
    ("system", "▤", "SYSTEM"),
    ("memory", "◈", "MEMORY"),
    ("jobs", "◷", "JOBS"),
    ("console", "⌘", "CONSOLE"),
]

PAGE_TITLES = {
    "overview": "OVERVIEW",
    "system": "SYSTEM",
    "memory": "MEMORY",
    "jobs": "JOBS & TIMERS",
    "console": "CONSOLE",
}

CSS = b"""
window {
    background-color: #060a12;
    background-image: linear-gradient(to bottom right, #060a12, #08101d 55%, #05080f);
    color: #e8eefc;
    font-family: "Inter", "Cantarell", Sans;
    font-size: 13px;
}
label { color: #e8eefc; }
.muted { color: #8798b5; font-size: 11px; }
.dim { color: #5f6f8c; font-size: 10px; }
.accent { color: #a78bfa; }
.cyan { color: #22d3ee; }
.green { color: #34d399; }
.amber { color: #fbbf24; }
.red { color: #fb7185; }

.section-title {
    color: #8798b5; font-size: 9px; font-weight: bold; letter-spacing: 1.8px;
}
.page-title { color: #a78bfa; font-size: 9px; font-weight: bold; letter-spacing: 1.8px; }
.greeting { color: #f3f7ff; font-size: 19px; font-weight: bold; }
.subtle { color: #8798b5; font-size: 11px; }
.clock { color: #f3f7ff; font-size: 22px; font-weight: bold; letter-spacing: 0.5px; }
.line { background-color: rgba(148,163,184,0.12); min-height: 1px; }

/* ---------- surfaces ---------- */
.card {
    background-color: rgba(13,20,34,0.74);
    border: 1px solid rgba(148,163,184,0.12);
    border-radius: 18px;
}
.card-soft {
    background-color: rgba(15,23,40,0.55);
    border: 1px solid rgba(148,163,184,0.09);
    border-radius: 14px;
}
.rail {
    background-color: rgba(10,16,28,0.74);
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 20px;
}
.top-accent {
    background-image: linear-gradient(to right, #7c5cff, #22d3ee, #34d399);
    min-height: 2px;
}
.logo {
    background-image: linear-gradient(to bottom right, #7c5cff, #22d3ee);
    border-radius: 15px;
    box-shadow: 0 8px 20px rgba(124,92,255,0.35);
}
.logo label { color: #ffffff; font-size: 22px; font-weight: bold; }
.rail-brand {
    color: #8798b5; font-size: 8px; font-weight: bold; letter-spacing: 2px;
}

/* ---------- buttons ---------- */
button {
    background-image: none;
    background-color: rgba(255,255,255,0.04);
    color: #dbe6fa;
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 10px;
    padding: 7px 12px;
    box-shadow: none;
    text-shadow: none;
}
button:hover {
    background-color: rgba(255,255,255,0.08);
    border-color: rgba(148,163,184,0.30);
}
button:active { background-color: rgba(255,255,255,0.12); }
button:disabled {
    color: #4b5a75;
    border-color: rgba(148,163,184,0.08);
    background-color: rgba(255,255,255,0.02);
}
button.primary {
    background-image: linear-gradient(to bottom right, #7c5cff, #5b8cff 55%, #22d3ee);
    color: #ffffff;
    border: 1px solid rgba(124,92,255,0.55);
    font-weight: bold;
    box-shadow: 0 6px 18px rgba(92,92,255,0.30);
}
button.primary:hover {
    background-image: linear-gradient(to bottom right, #8b6dff, #6d9aff 55%, #38ddf0);
}
button.ghost {
    background-color: transparent;
    border-color: rgba(148,163,184,0.14);
    color: #8798b5;
}
button.ghost:hover { color: #e8eefc; border-color: rgba(148,163,184,0.30); }
button.danger {
    color: #fb7185;
    border-color: rgba(251,113,133,0.28);
    background-color: rgba(251,113,133,0.06);
}
button.danger:hover { background-color: rgba(251,113,133,0.12); }
button.chip {
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    color: #a9b8d4;
    background-color: rgba(255,255,255,0.035);
    border-color: rgba(148,163,184,0.14);
}
button.chip:hover {
    color: #ffffff;
    border-color: rgba(124,92,255,0.55);
    background-color: rgba(124,92,255,0.12);
}
button.icon-btn {
    border-radius: 999px;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    color: #8798b5;
}
button.icon-btn:hover { color: #ffffff; border-color: rgba(124,92,255,0.50); }
button.send-btn {
    border-radius: 999px;
    min-width: 46px;
    min-height: 46px;
    padding: 0;
    font-size: 18px;
}
button.media-btn { min-height: 40px; border-radius: 12px; font-size: 15px; }
button.msg-action {
    background: transparent;
    border: none;
    padding: 0 8px 0 0;
    font-size: 9px;
    color: #5f6f8c;
    box-shadow: none;
}
button.msg-action:hover { color: #a78bfa; border: none; background: transparent; }

/* ---------- rail navigation ---------- */
button.rail-btn {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 7px 4px;
}
button.rail-btn:hover { background-color: rgba(255,255,255,0.05); }
button.rail-btn.active {
    background-color: rgba(124,92,255,0.16);
    border-color: rgba(124,92,255,0.30);
}
button.rail-btn.active label { color: #f5f3ff; }
.rail-icon { font-size: 15px; color: #7f91ae; }
.rail-label { font-size: 8px; letter-spacing: 1px; color: #7f91ae; font-weight: bold; }
button.rail-toggle {
    border-radius: 14px;
    padding: 8px 4px;
    background-color: transparent;
    border: 1px solid rgba(148,163,184,0.10);
}
button.rail-toggle:hover { background-color: rgba(255,255,255,0.05); }
button.rail-toggle.on {
    background-color: rgba(52,211,153,0.08);
    border-color: rgba(52,211,153,0.28);
}
.toggle-dot { font-size: 10px; }
.toggle-dot.dot-on { color: #34d399; }
.toggle-dot.dot-off { color: #4b5a75; }
.toggle-text { font-size: 8px; letter-spacing: 1px; color: #8798b5; font-weight: bold; }

/* ---------- header pills ---------- */
.pill {
    border-radius: 999px;
    padding: 6px 12px;
    background-color: rgba(255,255,255,0.04);
    border: 1px solid rgba(148,163,184,0.14);
}
.pill label { font-size: 10px; color: #a9b8d4; }
.pill.online {
    border-color: rgba(52,211,153,0.30);
    background-color: rgba(52,211,153,0.07);
}
.pill.online label { color: #6ee7b7; }
.pill.offline {
    border-color: rgba(251,113,133,0.30);
    background-color: rgba(251,113,133,0.07);
}
.pill.offline label { color: #fda4af; }

/* ---------- hero / voice stage ---------- */
.hero {
    background-image: linear-gradient(to bottom right,
        rgba(124,92,255,0.16), rgba(34,211,238,0.07) 48%, rgba(13,20,34,0.65));
    border: 1px solid rgba(124,92,255,0.24);
    border-radius: 20px;
}
.hero-state { color: #f8fafc; font-size: 22px; font-weight: bold; }
.hero-kicker {
    color: #a78bfa; font-size: 9px; font-weight: bold; letter-spacing: 2px;
}
.hero-mode { color: #8798b5; font-size: 8px; font-weight: bold; letter-spacing: 1.5px; }
.hero-sub { color: #8798b5; font-size: 11px; }
.empty-icon { color: #a78bfa; font-size: 30px; }
.empty-title { color: #e2e8f0; font-size: 14px; font-weight: bold; }
.suggest {
    background-color: rgba(6,10,18,0.45);
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 12px;
}
.suggest label { font-size: 11px; color: #a9b8d4; }
.state-green { color: #34d399; }
.state-amber { color: #fbbf24; }
.state-cyan { color: #22d3ee; }
.state-dim { color: #8798b5; }

/* ---------- conversation ---------- */
.chat-card {
    background-color: rgba(10,16,28,0.68);
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 20px;
}
.bubble-ninja {
    background-color: rgba(124,92,255,0.10);
    border: 1px solid rgba(124,92,255,0.22);
    border-radius: 16px;
}
.bubble-user {
    background-color: rgba(34,211,238,0.07);
    border: 1px solid rgba(34,211,238,0.18);
    border-radius: 16px;
}
.avatar-ninja {
    background-image: linear-gradient(to bottom right, #7c5cff, #22d3ee);
    border-radius: 999px;
}
.avatar-user {
    background-color: rgba(148,163,184,0.16);
    border: 1px solid rgba(148,163,184,0.18);
    border-radius: 999px;
}
.avatar-ninja label { color: #ffffff; font-size: 11px; font-weight: bold; }
.avatar-user label { color: #cbd5e1; font-size: 10px; font-weight: bold; }
.msg-who { color: #a78bfa; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
.msg-who.user { color: #67e8f9; }
.msg-time { color: #5f6f8c; font-size: 9px; }
.msg-body { color: #e2e8f0; font-size: 13px; }
.notice { color: #5f6f8c; font-size: 10px; }
.entry-placeholder { color: #5f6f8c; font-size: 13px; }

/* ---------- context pages ---------- */
.weather-temp { color: #ffffff; font-size: 38px; font-weight: bold; }
.weather-city { color: #67e8f9; font-size: 11px; font-weight: bold; letter-spacing: 1px; }
.weather-desc { color: #8798b5; font-size: 11px; }
.weather-glyph { color: #fbbf24; font-size: 26px; }
.meter-key { color: #8798b5; font-size: 10px; }
.meter-val { color: #e2e8f0; font-size: 10px; font-weight: bold; }
.mem-chip {
    background-color: rgba(124,92,255,0.09);
    border: 1px solid rgba(124,92,255,0.18);
    border-radius: 8px;
}
.mem-chip label { color: #c4b5fd; font-size: 10px; }
.mem-empty { color: #5f6f8c; font-size: 11px; }
.job-row {
    background-color: rgba(255,255,255,0.025);
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 10px;
}
.job-name { color: #cbd5e1; font-size: 11px; }
.activity-time {
    color: #4b5a75; font-size: 9px;
    font-family: "JetBrains Mono", Monospace;
}
.activity-text { color: #a9b8d4; font-size: 11px; }
.help-shell {
    background-color: #0a1120;
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 18px;
}
.help-title { color: #f8fafc; font-size: 24px; font-weight: bold; }
.help-sub { color: #8798b5; font-size: 11px; }
.help-section {
    color: #a78bfa; font-size: 10px; font-weight: bold; letter-spacing: 1.4px;
}
.help-body { color: #b7c4dc; font-size: 11px; }

/* ---------- entry / scroll / meters ---------- */
entry {
    background-image: none;
    background-color: rgba(10,16,28,0.90);
    color: #e8eefc;
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 12px;
    padding: 10px 14px;
    box-shadow: none;
}
entry:focus {
    border-color: rgba(124,92,255,0.65);
    background-color: rgba(12,19,33,0.95);
    box-shadow: 0 0 0 3px rgba(124,92,255,0.10);
}
entry.chat-entry { border-radius: 14px; padding: 13px 16px; font-size: 13px; }
scrolledwindow, viewport { background-color: transparent; border: none; }
scrollbar { background-color: transparent; border: none; }
scrollbar slider {
    background-color: rgba(148,163,184,0.20);
    border-radius: 999px;
    min-width: 6px;
    min-height: 30px;
}
scrollbar slider:hover { background-color: rgba(148,163,184,0.38); }
progressbar trough {
    background-color: rgba(148,163,184,0.12);
    border: none;
    border-radius: 999px;
    min-height: 6px;
}
progressbar progress {
    background-image: linear-gradient(to right, #7c5cff, #22d3ee);
    border: none;
    border-radius: 999px;
    min-height: 6px;
}
scale { background-color: transparent; }
scale trough {
    background-color: rgba(148,163,184,0.14);
    border: none;
    border-radius: 999px;
    min-height: 6px;
}
scale highlight {
    background-image: linear-gradient(to right, #7c5cff, #22d3ee);
    border-radius: 999px;
}
scale slider {
    background-color: #f8fafc;
    border: 2px solid #7c5cff;
    border-radius: 999px;
    min-width: 10px;
    min-height: 10px;
    margin: -4px;
}
textview.console-view { background-color: #060a12; color: #8fa3c4; }
textview.console-view text {
    background-color: #060a12;
    color: #8fa3c4;
    font-family: "JetBrains Mono", Monospace;
    font-size: 9px;
}
tooltip {
    background-color: #131d30;
    color: #e8eefc;
    border: 1px solid rgba(148,163,184,0.18);
    border-radius: 8px;
}
dialog, messagedialog { background-color: #0a1120; }
treeview.view {
    background-color: #0b1220;
    color: #e8eefc;
    border: 1px solid rgba(148,163,184,0.16);
}
treeview.view:selected {
    background-color: rgba(124,92,255,0.35);
    color: #ffffff;
}
"""

QUICK_ACTIONS = [
    ("Lofi", "play lofi beats"),
    ("Weather", "what's the weather"),
    ("Screenshot", "take a screenshot"),
    ("Status", "system status"),
    ("Timer 5 min", "set a timer for 5 minutes"),
    ("Joke", "tell me a joke"),
    ("Briefing", "briefing"),
    ("Memory", "what do you remember"),
]

COMPLETIONS = [
    "open youtube", "open github", "open gmail", "open whatsapp", "open telegram",
    "open terminal", "open vscode", "open files",
    "play lofi beats", "search google for ",
    "volume up", "volume down", "set volume to 40", "mute", "brightness up",
    "brightness down", "set brightness to 60", "take a screenshot",
    "system status", "uptime", "what's the weather", "what's the weather in ",
    "what time is it", "tell me a joke", "set a timer for 5 minutes",
    "remind me to call mom in 20 minutes", "list timers", "list jobs",
    "check job 1", "focus chrome", "list windows", "go to workspace 2",
    "move mouse to the center", "click", "scroll down", "type hello world",
    "turn wifi off", "turn wifi on", "read my clipboard", "empty the trash",
    "lock screen", "briefing", "what do you remember", "what do you remember about ",
    "my name is ", "my city is ", "remember that I prefer concise answers",
    "remember that ", "forget that ", "spark status",
    "clear chat history", "find the latest PDF in my CS folder", "read notifications",
    "git status", "create a study plan",
]

HELP_SECTIONS = [
    ("Getting started",
     "NINJA listens continuously — just speak, no wake word needed. Say "
     "'Ninja' before a phrase when you want to be certain it answers. Chain "
     "tasks in one breath with 'and' / 'then': 'open youtube and play believer'."),
    ("Apps & web",
     "open youtube · play believer · open vscode · open terminal · "
     "open whatsapp · open telegram · close chrome"),
    ("Messages",
     "message mom hello · whatsapp dad call me back"),
    ("Pages",
     "find cats · scroll down · click · comment nice video on this post"),
    ("Mouse & typing",
     "move mouse to the center · move mouse to 500, 300 · click · right click · "
     "scroll up/down · drag left · type hello world · press enter · copy · paste"),
    ("Timers & reminders",
     "set a timer for 10 minutes · remind me to call mom in 20 minutes · list timers"),
    ("System",
     "volume up · set volume to 40 · brightness up · take a screenshot · "
     "system status · lock screen"),
    ("Radios",
     "turn wifi off · switch bluetooth on · read my clipboard"),
    ("Windows",
     "focus chrome · minimise · maximise · list windows · go to workspace 2 · "
     "move this window to workspace 3"),
    ("Files & study",
     "open my CS folder · find the latest PDF · summarize it · create a study "
     "plan · read notifications"),
    ("Developer",
     "git status · git diff · run python code (confirmation required)"),
    ("Smart memory",
     "my name is Priya · my city is Mumbai · remember that I am afraid of "
     "heights · what do you remember about heights · forget that I am afraid "
     "of heights · turn it up · again · briefing"),
]


def _stats():
    """Return dict with cpu/mem/disk/battery/uptime; never raises."""
    out = {"cpu": 0, "mem": 0, "disk": 0, "batt": 100, "charging": True,
           "uptime": "00:00:00"}
    try:
        import time as _t
        import psutil
        out["cpu"] = int(psutil.cpu_percent(interval=None))
        out["mem"] = int(psutil.virtual_memory().percent)
        out["disk"] = int(psutil.disk_usage("/").percent)
        try:
            b = psutil.sensors_battery()
            if b is not None:
                out["batt"] = int(b.percent)
                out["charging"] = bool(b.power_plugged)
        except Exception:
            pass
        secs = int(_t.time() - psutil.boot_time())
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        out["uptime"] = f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        pass
    return out


def _greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Working late"


def _weather_glyph(desc):
    d = (desc or "").lower()
    if any(word in d for word in ("thunder", "storm", "lightning")):
        return "⚡"
    if any(word in d for word in ("snow", "sleet", "blizzard")):
        return "❄"
    if any(word in d for word in ("rain", "drizzle", "shower")):
        return "☂"
    if any(word in d for word in ("fog", "mist", "haze")):
        return "≋"
    if any(word in d for word in ("cloud", "overcast")):
        return "☁"
    if desc:
        return "☀"
    return "◌"


def _console_header():
    return "NINJA console · session log"


class ChatWindow:
    """Aurora front-end for an AssistantWorker."""

    def __init__(self, worker: AssistantWorker):
        self.worker = worker
        self._worker_done = False
        self._angle = 0.0
        self._wave_phase = 0.0
        self._state = "idle"
        self._cmd_history: list[str] = []
        self._hist_idx: int = -1
        self._vol_timer = None
        self._bri_timer = None
        self._quiet_sliders = False
        self._stat_ticks = 0
        self._suggest_cmd = "briefing"
        self._user_name = ""
        self._msg_count = 0
        self._active_page = "overview"
        self._nav_buttons: dict[str, Gtk.Button] = {}
        self._mic_on = bool(getattr(worker, "mic_enabled", False))
        self._tts_on = bool(getattr(worker, "tts_enabled", True))
        self._stats_cache = {"cpu": 0, "mem": 0, "disk": 0, "batt": 100,
                             "charging": True, "uptime": "00:00:00"}
        self._weather = {"temp": "--", "city": CITY_DEFAULT.upper(), "desc": "—"}
        self._build_css()
        self._build_window()
        self._refresh_memory()
        self._refresh_jobs()
        self._update_suggestion()
        self._sync_toggles()
        GLib.timeout_add(100, self._poll_events)
        GLib.timeout_add(1000, self._tick_clock)
        GLib.timeout_add(2000, self._tick_stats)
        GLib.timeout_add(50, self._tick_anim)
        threading.Thread(target=self._fetch_weather, daemon=True).start()
        threading.Thread(target=self._init_levels, daemon=True).start()
        self._term_append(_console_header())

    # ---------- construction helpers ----------

    def _build_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no display available — cannot open the window")
        try:
            settings = Gtk.Settings.get_default()
            if settings is not None:
                settings.set_property("gtk-application-prefer-dark-theme", True)
        except Exception:
            pass
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            display.get_default_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _label(self, text, cls=None, xalign=0, wrap=False, max_chars=0,
               selectable=False):
        lb = Gtk.Label(label=text)
        if cls:
            lb.get_style_context().add_class(cls)
        lb.set_xalign(xalign)
        if wrap:
            lb.set_line_wrap(True)
            lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if max_chars:
            lb.set_max_width_chars(max_chars)
        if selectable:
            lb.set_selectable(True)
        return lb

    def _pill(self, text, cls=""):
        box = Gtk.EventBox()
        box.get_style_context().add_class("pill")
        if cls:
            box.get_style_context().add_class(cls)
        lb = Gtk.Label(label=text)
        lb.get_style_context().add_class("pill-text")
        box.add(lb)
        return box, lb

    def _icon_button(self, glyph, tooltip, callback, cls="icon-btn"):
        btn = Gtk.Button.new_with_label(glyph)
        btn.get_style_context().add_class(cls)
        btn.set_tooltip_text(tooltip)
        btn.connect("clicked", callback)
        return btn

    def _card(self, title, subtitle=None):
        frame = Gtk.EventBox()
        frame.get_style_context().add_class("card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(16)
        frame.add(box)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        t = self._label(title.upper(), "section-title")
        head.pack_start(t, False, False, 0)
        if subtitle:
            s = self._label(subtitle, "muted")
            head.pack_start(s, False, False, 0)
        box.pack_start(head, False, False, 0)
        return frame, box, head

    def _meter_row(self, box, name):
        """Labelled progress row; returns (value_label, progressbar)."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        key = self._label(name, "meter-key")
        key.set_size_request(64, -1)
        row.pack_start(key, False, False, 0)
        bar = Gtk.ProgressBar()
        bar.set_hexpand(True)
        bar.set_valign(Gtk.Align.CENTER)
        row.pack_start(bar, True, True, 0)
        val = self._label("—", "meter-val", xalign=1)
        val.set_size_request(42, -1)
        row.pack_start(val, False, False, 0)
        box.pack_start(row, False, False, 0)
        return val, bar

    def _value_row(self, box, name):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        key = self._label(name, "meter-key")
        key.set_size_request(64, -1)
        row.pack_start(key, False, False, 0)
        val = self._label("—", "meter-val", xalign=1)
        val.set_hexpand(True)
        row.pack_start(val, True, True, 0)
        box.pack_start(row, False, False, 0)
        return val

    def _toggle_button(self, text, tooltip, callback):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.get_style_context().add_class("rail-toggle")
        btn.set_tooltip_text(tooltip)
        child = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        dot = self._label("●", "toggle-dot", xalign=0.5)
        lbl = self._label(text, "toggle-text", xalign=0.5)
        child.pack_start(dot, False, False, 0)
        child.pack_start(lbl, False, False, 0)
        btn.add(child)
        btn.connect("clicked", lambda b: callback())
        return btn, dot

    def _scroller(self, box):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_hexpand(True)
        sw.set_vexpand(True)
        sw.add(box)
        return sw

    # ---------- window shell ----------

    def _build_window(self):
        Gtk.Window.set_default_icon_name("audio-input-microphone")
        self.win = Gtk.Window(title=f"{DISPLAY_NAME} — Voice Assistant")
        self.win.set_default_size(1380, 880)
        self.win.set_size_request(1120, 720)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("delete-event", self._on_delete)
        self.win.connect("destroy", self._on_destroy)
        self.win.connect("key-press-event", self._on_window_key)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        accent = Gtk.EventBox()
        accent.get_style_context().add_class("top-accent")
        accent.set_size_request(-1, 2)
        root.pack_start(accent, False, False, 0)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main.set_border_width(20)
        root.pack_start(main, True, True, 0)

        main.pack_start(self._build_header(), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        body.pack_start(self._build_rail(), False, True, 0)
        body.pack_start(self._build_center(), True, True, 0)
        body.pack_start(self._build_context(), False, True, 0)
        main.pack_start(body, True, True, 0)

    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.greeting_label = self._label(_greeting(), "greeting")
        self.date_label = self._label("", "subtle")
        left.pack_start(self.greeting_label, False, False, 0)
        left.pack_start(self.date_label, False, False, 0)
        header.pack_start(left, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.pack_start(spacer, True, True, 0)

        self.weather_pill_box, self.top_weather = self._pill("Set city")
        self.weather_pill_box.set_tooltip_text("Open the weather panel")
        self.weather_pill_box.connect(
            "button-press-event",
            lambda w, e: self._show_page("overview") or True)
        header.pack_start(self.weather_pill_box, False, False, 0)

        self.online_pill_box, self.online_pill = self._pill("● Online", "online")
        self.online_pill_box.set_tooltip_text("Assistant connection status")
        header.pack_start(self.online_pill_box, False, False, 0)

        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.clock_label = self._label("--:--", "clock", xalign=1)
        clock_box.pack_start(self.clock_label, False, False, 0)
        header.pack_start(clock_box, False, False, 0)

        help_btn = self._icon_button(
            "?", "Command guide (F1)", lambda b: self._show_help())
        help_btn.set_valign(Gtk.Align.CENTER)
        header.pack_start(help_btn, False, False, 0)
        return header

    def _build_rail(self):
        shell = Gtk.EventBox()
        shell.get_style_context().add_class("rail")
        shell.set_size_request(92, -1)
        shell.set_vexpand(True)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_border_width(10)
        inner.set_vexpand(True)
        shell.add(inner)

        logo = Gtk.EventBox()
        logo.get_style_context().add_class("logo")
        logo.set_size_request(48, 48)
        logo.set_halign(Gtk.Align.CENTER)
        logo_lbl = self._label("N", xalign=0.5)
        logo_lbl.set_halign(Gtk.Align.CENTER)
        logo_lbl.set_valign(Gtk.Align.CENTER)
        logo.add(logo_lbl)
        inner.pack_start(logo, False, False, 0)

        brand = self._label("NINJA", "rail-brand", xalign=0.5)
        brand.set_halign(Gtk.Align.CENTER)
        inner.pack_start(brand, False, False, 0)

        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for key, icon, text in NAV_ITEMS:
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("rail-btn")
            btn.set_tooltip_text(f"{PAGE_TITLES[key]} panel")
            child = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            child.pack_start(self._label(icon, "rail-icon", xalign=0.5),
                             False, False, 0)
            child.pack_start(self._label(text, "rail-label", xalign=0.5),
                             False, False, 0)
            btn.add(child)
            btn.connect("clicked", lambda b, n=key: self._show_page(n))
            nav.pack_start(btn, False, False, 0)
            self._nav_buttons[key] = btn
        inner.pack_start(nav, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        inner.pack_start(spacer, True, True, 0)

        self.mic_btn, self.mic_dot = self._toggle_button(
            "MIC", "Microphone on/off (Ctrl+M)", self._toggle_mic)
        if not getattr(self.worker, "voice", False):
            self.mic_btn.set_sensitive(False)
            self.mic_btn.set_tooltip_text(
                "Microphone unavailable — start without --no-mic")
        inner.pack_start(self.mic_btn, False, False, 0)
        self.tts_btn, self.tts_dot = self._toggle_button(
            "VOICE", "Spoken replies on/off", self._toggle_tts)
        inner.pack_start(self.tts_btn, False, False, 0)
        return shell

    # ---------- center column ----------

    def _build_center(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        col.set_hexpand(True)
        col.set_size_request(620, -1)

        col.pack_start(self._build_hero(), False, False, 0)
        col.pack_start(self._build_chat(), True, True, 0)
        col.pack_start(self._build_quick_actions(), False, False, 0)
        col.pack_start(self._build_composer(), False, False, 0)

        hint = self._label(
            "Enter to send  ·  ↑↓ history  ·  Ctrl+M mute  ·  Ctrl+1–5 panels",
            "muted", xalign=1)
        col.pack_start(hint, False, False, 0)
        return col

    def _build_hero(self):
        hero = Gtk.EventBox()
        hero.get_style_context().add_class("hero")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        inner.set_border_width(16)
        hero.add(inner)

        self.orb = Gtk.DrawingArea()
        self.orb.set_size_request(138, 138)
        self.orb.connect("draw", self._draw_orb)
        inner.pack_start(self.orb, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_hexpand(True)
        right.set_valign(Gtk.Align.CENTER)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.state_dot = self._label("●", "state-dim")
        top.pack_start(self.state_dot, False, False, 0)
        top.pack_start(self._label("NINJA · VOICE", "hero-kicker"),
                       False, False, 0)
        top_spacer = Gtk.Box()
        top_spacer.set_hexpand(True)
        top.pack_start(top_spacer, True, True, 0)
        self.mode_label = self._label(self._mode_text(), "hero-mode", xalign=1)
        top.pack_start(self.mode_label, False, False, 0)
        right.pack_start(top, False, False, 0)

        self.hero_state = self._label("Starting…", "hero-state")
        right.pack_start(self.hero_state, False, False, 0)
        self.hero_sub = self._label("Getting the microphone ready…", "hero-sub",
                                    wrap=True)
        right.pack_start(self.hero_sub, False, False, 0)

        self.hero_wave = Gtk.DrawingArea()
        self.hero_wave.set_size_request(-1, 34)
        self.hero_wave.set_hexpand(True)
        self.hero_wave.connect("draw", self._draw_wave)
        right.pack_start(self.hero_wave, False, False, 2)

        suggest = Gtk.EventBox()
        suggest.get_style_context().add_class("suggest")
        suggest_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=10)
        suggest_inner.set_border_width(9)
        suggest.add(suggest_inner)
        self.suggest_label = self._label(
            "Try 'briefing' for your daily overview", "suggest-text", wrap=True,
            max_chars=58)
        self.suggest_label.set_hexpand(True)
        suggest_inner.pack_start(self.suggest_label, True, True, 0)
        self.suggest_btn = Gtk.Button.new_with_label("Run")
        self.suggest_btn.get_style_context().add_class("primary")
        self.suggest_btn.set_tooltip_text("Run the suggested command")
        self.suggest_btn.connect("clicked", lambda b: self._run_suggestion())
        suggest_inner.pack_start(self.suggest_btn, False, False, 0)
        right.pack_start(suggest, False, False, 0)

        inner.pack_start(right, True, True, 0)
        return hero

    def _build_chat(self):
        shell = Gtk.EventBox()
        shell.get_style_context().add_class("chat-card")
        shell.set_vexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_border_width(16)
        inner.set_vexpand(True)
        shell.add(inner)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.pack_start(self._label("CONVERSATION", "section-title"),
                        False, False, 0)
        self.msg_count = self._label("0 messages", "muted")
        head.pack_start(self.msg_count, False, False, 0)
        head_spacer = Gtk.Box()
        head_spacer.set_hexpand(True)
        head.pack_start(head_spacer, True, True, 0)
        clear_btn = Gtk.Button.new_with_label("Clear")
        clear_btn.get_style_context().add_class("ghost")
        clear_btn.set_tooltip_text(
            "Clear the on-screen conversation (saved history is kept)")
        clear_btn.connect("clicked", lambda b: self._clear_chat())
        head.pack_start(clear_btn, False, False, 0)
        inner.pack_start(head, False, False, 0)

        self.conv_scroller = Gtk.ScrolledWindow()
        self.conv_scroller.set_policy(Gtk.PolicyType.NEVER,
                                      Gtk.PolicyType.AUTOMATIC)
        self.conv_scroller.set_vexpand(True)
        self.conv_scroller.set_min_content_height(240)
        self.conv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.conv_scroller.add(self.conv_box)
        inner.pack_start(self.conv_scroller, True, True, 0)
        return shell

    def _build_quick_actions(self):
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(8)
        flow.set_min_children_per_line(1)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)
        flow.set_homogeneous(False)
        for label, cmd in QUICK_ACTIONS:
            btn = Gtk.Button.new_with_label(label)
            btn.get_style_context().add_class("chip")
            btn.set_tooltip_text(f"Send: {cmd}")
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", lambda b, c=cmd: self._send_text(c))
            flow.add(btn)
        return flow

    def _build_composer(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("chat-entry")
        self.entry.set_hexpand(True)
        self.entry.set_size_request(-1, 46)
        self.entry.connect("activate", lambda w: self._submit())
        self.entry.connect("key-press-event", self._on_entry_key)
        self.entry.connect("changed", self._update_placeholder)
        try:
            completion = Gtk.EntryCompletion()
            store = Gtk.ListStore(str)
            for c in COMPLETIONS:
                store.append([c])
            completion.set_model(store)
            completion.set_text_column(0)
            completion.set_minimum_key_length(2)
            completion.set_popup_completion(True)
            self.entry.set_completion(completion)
        except Exception:
            pass

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.add(self.entry)
        self.entry_placeholder = self._label(
            "Ask Ninja anything, or just speak…", "entry-placeholder")
        self.entry_placeholder.set_halign(Gtk.Align.START)
        self.entry_placeholder.set_valign(Gtk.Align.CENTER)
        self.entry_placeholder.set_margin_start(16)
        self.entry_placeholder.set_can_focus(False)
        overlay.add_overlay(self.entry_placeholder)
        try:
            overlay.set_overlay_pass_through(self.entry_placeholder, True)
        except Exception:
            pass
        row.pack_start(overlay, True, True, 0)

        self.send_btn = Gtk.Button.new_with_label("→")
        self.send_btn.get_style_context().add_class("primary")
        self.send_btn.get_style_context().add_class("send-btn")
        self.send_btn.set_tooltip_text("Send (Enter)")
        self.send_btn.connect("clicked", lambda b: self._submit())
        row.pack_start(self.send_btn, False, False, 0)
        self._update_placeholder()
        return row

    # ---------- right column: contextual pages ----------

    def _build_context(self):
        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        shell.set_size_request(340, -1)
        shell.set_vexpand(True)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.pack_start(self._label("INSIGHTS", "section-title"), False, False, 0)
        self.page_title = self._label("OVERVIEW", "page-title", xalign=1)
        self.page_title.set_hexpand(True)
        head.pack_start(self.page_title, True, True, 0)
        shell.pack_start(head, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.add_named(self._page_overview(), "overview")
        self.stack.add_named(self._page_system(), "system")
        self.stack.add_named(self._page_memory(), "memory")
        self.stack.add_named(self._page_jobs(), "jobs")
        self.stack.add_named(self._page_console(), "console")
        shell.pack_start(self.stack, True, True, 0)
        self._show_page("overview")
        return shell

    def _show_page(self, name):
        if name not in self._nav_buttons:
            return
        self._active_page = name
        try:
            self.stack.set_visible_child_name(name)
        except Exception:
            pass
        for key, btn in self._nav_buttons.items():
            ctx = btn.get_style_context()
            if key == name:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        try:
            self.page_title.set_text(PAGE_TITLES.get(name, name.upper()))
        except Exception:
            pass

    def _page_overview(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        w_card, w_box, w_head = self._card("Weather")
        w_head.pack_end(self._icon_button(
            "⟳", "Refresh weather", lambda b: self._refresh_weather()),
            False, False, 0)

        w_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.w_glyph = self._label("◌", "weather-glyph", xalign=0.5)
        self.w_glyph.set_size_request(34, -1)
        w_row.pack_start(self.w_glyph, False, False, 0)
        self.w_temp = self._label("--°", "weather-temp")
        w_row.pack_start(self.w_temp, False, False, 0)
        w_meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        w_meta.set_valign(Gtk.Align.CENTER)
        self.w_city = self._label(CITY_DEFAULT.upper() or "SET A CITY",
                                  "weather-city")
        self.w_desc = self._label("for live weather", "weather-desc")
        w_meta.pack_start(self.w_city, False, False, 0)
        w_meta.pack_start(self.w_desc, False, False, 0)
        w_row.pack_start(w_meta, True, True, 0)
        w_box.pack_start(w_row, False, False, 0)

        self.w_sub = self._label("—", "subtle", wrap=True)
        w_box.pack_start(self.w_sub, False, False, 0)

        city_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.city_entry = Gtk.Entry()
        self.city_entry.set_placeholder_text("Change city…")
        self.city_entry.set_hexpand(True)
        self.city_entry.connect("activate", lambda w: self._set_city())
        city_row.pack_start(self.city_entry, True, True, 0)
        city_set = Gtk.Button.new_with_label("Set")
        city_set.get_style_context().add_class("ghost")
        city_set.set_tooltip_text("Remember this city and refresh")
        city_set.connect("clicked", lambda b: self._set_city())
        city_row.pack_start(city_set, False, False, 0)
        w_box.pack_start(city_row, False, False, 0)
        box.pack_start(w_card, False, False, 0)

        g_card, g_box, _ = self._card("At a glance")
        for name, attr, page in (("Jobs", "overview_jobs", "jobs"),
                                 ("Memory", "overview_memory", "memory"),
                                 ("Microphone", "overview_mic", None)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            key = self._label(name, "meter-key")
            key.set_size_request(78, -1)
            row.pack_start(key, False, False, 0)
            val = self._label("—", "meter-val")
            val.set_hexpand(True)
            row.pack_start(val, True, True, 0)
            setattr(self, attr, val)
            if page:
                btn = Gtk.Button.new_with_label("Open")
                btn.get_style_context().add_class("ghost")
                btn.set_tooltip_text(f"Open the {PAGE_TITLES[page]} panel")
                btn.connect("clicked", lambda b, p=page: self._show_page(p))
                row.pack_start(btn, False, False, 0)
            g_box.pack_start(row, False, False, 0)
        box.pack_start(g_card, False, False, 0)

        t_card, t_box, _ = self._card("Voice tips")
        t_box.pack_start(self._label(
            "Speak naturally — no wake word needed. Say 'Ninja' before a "
            "command to be certain it answers, or chain tasks with 'and'.",
            "subtle", wrap=True, max_chars=42), False, False, 0)
        tip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        guide = Gtk.Button.new_with_label("Command guide")
        guide.get_style_context().add_class("ghost")
        guide.connect("clicked", lambda b: self._show_help())
        tip_row.pack_start(guide, True, True, 0)
        brief = Gtk.Button.new_with_label("Briefing")
        brief.get_style_context().add_class("ghost")
        brief.connect("clicked", lambda b: self._send_text("briefing"))
        tip_row.pack_start(brief, True, True, 0)
        t_box.pack_start(tip_row, False, False, 0)
        box.pack_start(t_card, False, False, 0)

        return self._scroller(box)

    def _page_system(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        p_card, p_box, _ = self._card("Performance")
        self.cpu_val, self.cpu_bar = self._meter_row(p_box, "CPU")
        self.mem_val, self.mem_bar = self._meter_row(p_box, "Memory")
        self.disk_val, self.disk_bar = self._meter_row(p_box, "Disk")
        self.batt_val = self._value_row(p_box, "Battery")
        self.uptime_val = self._value_row(p_box, "Uptime")
        self.mic_state = self._value_row(p_box, "Microphone")
        box.pack_start(p_card, False, False, 0)

        s_card, s_box, _ = self._card("Sound & display")
        s_box.pack_start(self._label("Volume", "meter-key"), False, False, 0)
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vol_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol_scale.set_value(50)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.set_hexpand(True)
        self.vol_scale.set_tooltip_text("Speaker volume")
        self.vol_scale.connect("value-changed", self._on_vol_slider)
        vol_row.pack_start(self.vol_scale, True, True, 0)
        self.vol_val = self._label("50%", "meter-val", xalign=1)
        self.vol_val.set_size_request(38, -1)
        vol_row.pack_start(self.vol_val, False, False, 0)
        mute_btn = Gtk.Button.new_with_label("Mute")
        mute_btn.get_style_context().add_class("ghost")
        mute_btn.set_tooltip_text("Toggle mute (voice: mute)")
        mute_btn.connect("clicked", lambda b: self._send_text("mute"))
        vol_row.pack_start(mute_btn, False, False, 0)
        s_box.pack_start(vol_row, False, False, 0)

        s_box.pack_start(self._label("Brightness", "meter-key"), False, False, 0)
        bri_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bri_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 5, 100, 1)
        self.bri_scale.set_value(80)
        self.bri_scale.set_draw_value(False)
        self.bri_scale.set_hexpand(True)
        self.bri_scale.set_tooltip_text("Screen brightness")
        self.bri_scale.connect("value-changed", self._on_bri_slider)
        bri_row.pack_start(self.bri_scale, True, True, 0)
        self.bri_val = self._label("80%", "meter-val", xalign=1)
        self.bri_val.set_size_request(38, -1)
        bri_row.pack_start(self.bri_val, False, False, 0)
        s_box.pack_start(bri_row, False, False, 0)
        box.pack_start(s_card, False, False, 0)

        m_card, m_box, _ = self._card("Media")
        media_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for icon, tip, key in (("⏮", "Previous track", "previous"),
                               ("⏯", "Play / pause", "playpause"),
                               ("⏭", "Next track", "next")):
            btn = Gtk.Button.new_with_label(icon)
            btn.get_style_context().add_class("media-btn")
            btn.set_hexpand(True)
            btn.set_tooltip_text(f"{tip} (voice: {key})")
            btn.connect("clicked", lambda b, k=key: self._media_key(k))
            media_row.pack_start(btn, True, True, 0)
        m_box.pack_start(media_row, False, False, 0)
        box.pack_start(m_card, False, False, 0)

        q_card, q_box, _ = self._card("Quick controls")
        q_flow = Gtk.FlowBox()
        q_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        q_flow.set_max_children_per_line(2)
        q_flow.set_column_spacing(8)
        q_flow.set_row_spacing(8)
        q_flow.set_homogeneous(True)
        for label, cmd in (("Screenshot", "take a screenshot"),
                           ("Lock screen", "lock screen"),
                           ("Status", "system status"),
                           ("Clipboard", "read my clipboard")):
            btn = Gtk.Button.new_with_label(label)
            btn.get_style_context().add_class("ghost")
            btn.set_tooltip_text(f"Send: {cmd}")
            btn.connect("clicked", lambda b, c=cmd: self._send_text(c))
            q_flow.add(btn)
        q_box.pack_start(q_flow, False, False, 0)
        box.pack_start(q_card, False, False, 0)

        return self._scroller(box)

    def _page_memory(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        m_card, m_box, m_head = self._card("Memory", "what I know")
        m_head.pack_end(self._icon_button(
            "⟳", "Refresh what the assistant remembers",
            lambda b: self._refresh_memory()), False, False, 0)

        self.mem_summary = self._label(
            "Nothing yet — tell me about yourself.", "mem-empty", wrap=True,
            max_chars=38)
        m_box.pack_start(self.mem_summary, False, False, 0)

        self.mem_chips = Gtk.FlowBox()
        self.mem_chips.set_selection_mode(Gtk.SelectionMode.NONE)
        self.mem_chips.set_max_children_per_line(2)
        self.mem_chips.set_column_spacing(6)
        self.mem_chips.set_row_spacing(6)
        m_box.pack_start(self.mem_chips, False, False, 0)

        mem_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mem_ask = Gtk.Button.new_with_label("Recall")
        mem_ask.get_style_context().add_class("ghost")
        mem_ask.set_tooltip_text("Ask: what do you remember")
        mem_ask.connect("clicked", lambda b: self._send_text(
            "what do you remember"))
        mem_row.pack_start(mem_ask, True, True, 0)
        self.mem_forget = Gtk.Button.new_with_label("Forget all")
        self.mem_forget.get_style_context().add_class("danger")
        self.mem_forget.set_tooltip_text(
            "Wipe every remembered name, fact and preference")
        self.mem_forget.connect("clicked", lambda b: self._forget_all())
        mem_row.pack_start(self.mem_forget, False, False, 0)
        m_box.pack_start(mem_row, False, False, 0)
        box.pack_start(m_card, False, False, 0)

        teach_card, teach_box, _ = self._card("Teach Ninja")
        teach_box.pack_start(self._label(
            "Type a starter and finish it in the composer:",
            "subtle", wrap=True, max_chars=38), False, False, 0)
        for prefix in ("My name is ", "My city is ", "Remember that "):
            btn = Gtk.Button.new_with_label(f"{prefix.strip()}…")
            btn.get_style_context().add_class("ghost")
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", lambda b, p=prefix: self._prefill(p))
            teach_box.pack_start(btn, False, False, 0)
        box.pack_start(teach_card, False, False, 0)

        p_card, p_box, _ = self._card("Privacy")
        p_box.pack_start(self._label(
            "Memory is stored locally in ~/.local/share/ninja-assistant/"
            "memory.json. NINJA reads it only when a command needs context "
            "and never uploads it.", "subtle", wrap=True, max_chars=40),
            False, False, 0)
        box.pack_start(p_card, False, False, 0)

        return self._scroller(box)

    def _page_jobs(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_vexpand(True)

        j_card, j_box, j_head = self._card("Jobs & timers")
        j_card.set_vexpand(True)
        j_box.set_vexpand(True)
        self.jobs_card_box = j_box
        self.jobs_count = self._label("Nothing running", "muted", xalign=1)
        j_head.pack_end(self.jobs_count, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, tip, fn in (("Refresh", "Refresh the list",
                                self._refresh_jobs),
                               ("List", "Ask: list jobs",
                                lambda b: self._send_text("list jobs")),
                               ("Clear", "Clear finished jobs",
                                self._clear_jobs)):
            btn = Gtk.Button.new_with_label(label)
            btn.get_style_context().add_class("ghost")
            btn.set_tooltip_text(tip)
            btn.connect("clicked", fn)
            controls.pack_start(btn, True, True, 0)
        j_box.pack_start(controls, False, False, 0)

        self.jobs_scroller = Gtk.ScrolledWindow()
        self.jobs_scroller.set_policy(Gtk.PolicyType.NEVER,
                                      Gtk.PolicyType.AUTOMATIC)
        self.jobs_scroller.set_min_content_height(220)
        self.jobs_scroller.set_vexpand(True)
        self.jobs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.jobs_scroller.add(self.jobs_box)
        j_box.pack_start(self.jobs_scroller, True, True, 0)

        self.jobs_empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.jobs_empty.set_vexpand(True)
        self.jobs_empty.set_valign(Gtk.Align.CENTER)
        self.jobs_empty.set_halign(Gtk.Align.CENTER)
        self.jobs_empty.pack_start(
            self._label("◷", "empty-icon", xalign=0.5), False, False, 0)
        self.jobs_empty.pack_start(
            self._label("No jobs or timers", "empty-title", xalign=0.5),
            False, False, 0)
        self.jobs_empty.pack_start(
            self._label("Ask NINJA to set a timer or start a background task.",
                        "muted", xalign=0.5, wrap=True, max_chars=32),
            False, False, 0)
        j_box.pack_start(self.jobs_empty, True, True, 0)
        box.pack_start(j_card, True, True, 0)

        hint_card, hint_box, _ = self._card("Try a timer")
        hint_box.pack_start(self._label(
            "Ask for a countdown and keep working — NINJA will speak up "
            "when it fires.", "subtle", wrap=True, max_chars=40),
            False, False, 0)
        hint_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        timer_btn = Gtk.Button.new_with_label("Timer 10 min")
        timer_btn.get_style_context().add_class("ghost")
        timer_btn.connect("clicked", lambda b: self._send_text(
            "set a timer for 10 minutes"))
        hint_row.pack_start(timer_btn, True, True, 0)
        list_btn = Gtk.Button.new_with_label("List timers")
        list_btn.get_style_context().add_class("ghost")
        list_btn.connect("clicked", lambda b: self._send_text("list timers"))
        hint_row.pack_start(list_btn, True, True, 0)
        hint_box.pack_start(hint_row, False, False, 0)
        box.pack_start(hint_card, False, False, 0)
        return box

    def _page_console(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_vexpand(True)

        a_card, a_box, a_head = self._card("Activity")
        a_card.set_vexpand(True)
        a_box.set_vexpand(True)
        clear_a = Gtk.Button.new_with_label("Clear")
        clear_a.get_style_context().add_class("ghost")
        clear_a.set_tooltip_text("Clear the activity feed")
        clear_a.connect("clicked", lambda b: self._clear_activity())
        a_head.pack_end(clear_a, False, False, 0)
        self.act_scroller = Gtk.ScrolledWindow()
        self.act_scroller.set_policy(Gtk.PolicyType.NEVER,
                                     Gtk.PolicyType.AUTOMATIC)
        self.act_scroller.set_min_content_height(200)
        self.act_scroller.set_vexpand(True)
        self.act_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.act_scroller.add(self.act_box)
        a_box.pack_start(self.act_scroller, True, True, 0)
        box.pack_start(a_card, True, True, 0)

        c_card, c_box, c_head = self._card("Console")
        c_card.set_vexpand(True)
        c_box.set_vexpand(True)
        clear_c = Gtk.Button.new_with_label("Clear")
        clear_c.get_style_context().add_class("ghost")
        clear_c.set_tooltip_text("Clear the console transcript")
        clear_c.connect("clicked", lambda b: self._clear_console())
        c_head.pack_end(clear_c, False, False, 0)
        self.term_scroller = Gtk.ScrolledWindow()
        self.term_scroller.set_policy(Gtk.PolicyType.AUTOMATIC,
                                      Gtk.PolicyType.AUTOMATIC)
        self.term_scroller.set_min_content_height(200)
        self.term_scroller.set_vexpand(True)
        self.term_view = Gtk.TextView()
        self.term_view.get_style_context().add_class("console-view")
        self.term_view.set_editable(False)
        self.term_view.set_cursor_visible(False)
        self.term_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.term_view.set_left_margin(10)
        self.term_view.set_right_margin(10)
        self.term_view.set_top_margin(8)
        self.term_view.set_bottom_margin(8)
        self.term_scroller.add(self.term_view)
        c_box.pack_start(self.term_scroller, True, True, 0)
        box.pack_start(c_card, True, True, 0)
        return box

    # ---------- drawing ----------

    def _get_mic_visual(self):
        """Return (level 0..1, history list) for the intake visualiser.

        0 when the mic is muted / unavailable / stale; otherwise the live
        smoothed RMS meter from ear.py. Never raises (draw path must not die).
        """
        try:
            mic = getattr(self.worker, "mic", None)
            if (mic is None or not getattr(self.worker, "voice", False)
                    or not getattr(self.worker, "mic_enabled", False)):
                return 0.0, []
            snap = getattr(mic, "audio_snapshot", None)
            if snap is None:
                return 0.0, []
            level, hist, _age = snap()
            return max(0.0, min(1.0, float(level))), hist
        except Exception:
            return 0.0, []

    def _draw_orb(self, area, cr):
        """A layered, breathing voice orb; the card behind it shows through."""
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 6
        if R <= 0:
            return False

        s = self._stats_cache
        cpu = max(0.02, min(1.0, s["cpu"] / 100.0))
        mem = max(0.02, min(1.0, s["mem"] / 100.0))
        mic_level, _ = self._get_mic_visual()
        breathe = 0.5 + 0.5 * math.sin(self._wave_phase * 1.35)
        pulse = max(mic_level, 0.06 + 0.035 * breathe)

        # Soft outer glow.
        glow = cairo.RadialGradient(cx, cy, R * 0.10, cx, cy, R)
        glow.add_color_stop_rgba(0.0, *VIOLET, 0.20)
        glow.add_color_stop_rgba(0.55, *CYAN, 0.07)
        glow.add_color_stop_rgba(1.0, 0, 0, 0, 0.0)
        cr.set_source(glow)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.fill()

        # Slow tick ring.
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(self._angle * 0.16)
        for i in range(56):
            a = 2 * math.pi * i / 56
            long_tick = (i % 7 == 0)
            r1 = R
            r0 = R - (9 if long_tick else 4)
            cr.set_source_rgba(*(CYAN if long_tick else VIOLET),
                               0.45 if long_tick else 0.16)
            cr.set_line_width(1.6 if long_tick else 0.9)
            cr.move_to(r0 * math.cos(a), r0 * math.sin(a))
            cr.line_to(r1 * math.cos(a), r1 * math.sin(a))
            cr.stroke()
        cr.restore()

        # Rotating dashed halo.
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(-self._angle * 0.42)
        cr.set_dash([1.5, 9.0])
        cr.set_source_rgba(*CYAN, 0.20 + mic_level * 0.35)
        cr.set_line_width(1.4)
        cr.arc(0, 0, R * 0.93, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])
        cr.restore()

        # CPU + memory arcs, in the Aurora gradient.
        grad = cairo.LinearGradient(cx - R, cy - R, cx + R, cy + R)
        grad.add_color_stop_rgba(0.0, *VIOLET, 0.95)
        grad.add_color_stop_rgba(1.0, *CYAN, 0.95)
        cr.set_source(grad)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(3.2)
        cr.arc(cx, cy, R * 0.84, -math.pi * 0.5,
               -math.pi * 0.5 + 2 * math.pi * cpu + 0.03)
        cr.stroke()

        mem_grad = cairo.LinearGradient(cx + R, cy - R, cx - R, cy + R)
        mem_grad.add_color_stop_rgba(0.0, *MINT, 0.90)
        mem_grad.add_color_stop_rgba(1.0, *CYAN, 0.75)
        cr.set_source(mem_grad)
        cr.set_line_width(2.4)
        cr.arc(cx, cy, R * 0.75, math.pi * 0.5,
               math.pi * 0.5 + 2 * math.pi * mem + 0.03)
        cr.stroke()

        # Breathing ring driven by the live microphone level.
        ring_r = R * 0.55 * (1.0 + mic_level * 0.05 + 0.008 * breathe)
        cr.set_source_rgba(*CYAN, 0.25 + mic_level * 0.55)
        cr.set_line_width(1.4 + mic_level * 2.0)
        cr.arc(cx, cy, ring_r, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(*VIOLET, 0.06 + mic_level * 0.18)
        cr.set_line_width(10 + mic_level * 12)
        cr.arc(cx, cy, ring_r, 0, 2 * math.pi)
        cr.stroke()

        # Glass sphere.
        sphere = cairo.RadialGradient(
            cx - R * 0.12, cy - R * 0.14, R * 0.02,
            cx, cy, R * 0.52)
        sphere.add_color_stop_rgba(0.0, 1, 1, 1, 0.92)
        sphere.add_color_stop_rgba(0.20, *VIOLET, 0.78)
        sphere.add_color_stop_rgba(0.58, *CYAN, 0.24)
        sphere.add_color_stop_rgba(1.0, *CYAN, 0.0)
        cr.set_source(sphere)
        cr.arc(cx, cy, R * 0.52, 0, 2 * math.pi)
        cr.fill()

        # Core light.
        core = cairo.RadialGradient(cx, cy, 0, cx, cy, R * 0.22)
        core.add_color_stop_rgba(0.0, 1, 1, 1, 0.85)
        core.add_color_stop_rgba(0.45, *CYAN, 0.25)
        core.add_color_stop_rgba(1.0, *CYAN, 0.0)
        cr.set_source(core)
        cr.arc(cx, cy, R * 0.22, 0, 2 * math.pi)
        cr.fill()

        # Orbiting sparks.
        for i in range(3):
            a = self._angle * (0.55 + i * 0.22) + i * 2.1
            r = R * (0.66 + i * 0.055)
            px, py = cx + r * math.cos(a), cy + r * math.sin(a)
            cr.set_source_rgba(*(CYAN if i % 2 else VIOLET), 0.75)
            cr.arc(px, py, 1.6, 0, 2 * math.pi)
            cr.fill()

        # Bright centre point.
        cr.set_source_rgba(1, 1, 1, 0.92)
        cr.arc(cx, cy, 2.2 + pulse * 2.2, 0, 2 * math.pi)
        cr.fill()
        return False

    @staticmethod
    def _mix(a, b, t):
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))

    def _draw_wave(self, area, cr):
        """Audio-intake bars driven by the live microphone meter."""
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        level, hist = self._get_mic_visual()
        live = level > 0.02
        n_bars = 34
        gap = 4.0
        bar_w = min(6.0, (w - gap * (n_bars + 1)) / n_bars)
        total = n_bars * bar_w + (n_bars - 1) * gap
        x0 = (w - total) / 2 + bar_w / 2
        mid = h / 2
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for i in range(n_bars):
            if hist:
                idx = int(i * (len(hist) - 1) / max(1, n_bars - 1))
                v = hist[idx]
            else:
                v = 0.0
            if live:
                centre = 1.0 - abs(i - (n_bars - 1) / 2) / ((n_bars - 1) / 2)
                v = max(v, level * (0.35 + 0.65 * centre))
            else:
                v = 0.18 + 0.16 * abs(
                    math.sin(i * 0.52 + self._wave_phase * 1.5))
            bar_h = max(3.0, v * (h - 4))
            colour = self._mix(VIOLET, CYAN, i / max(1, n_bars - 1))
            cr.set_source_rgba(*colour, 0.35 + 0.55 * min(1.0, v * 1.8))
            cr.set_line_width(bar_w)
            cr.move_to(x0 + i * (bar_w + gap), mid - bar_h / 2)
            cr.line_to(x0 + i * (bar_w + gap), mid + bar_h / 2)
            cr.stroke()
        return False

    # ---------- live ticks ----------

    def _tick_clock(self):
        now = datetime.now()
        self.clock_label.set_text(now.strftime("%I:%M %p").lstrip("0"))
        self.date_label.set_text(f"{now:%A, %B} {now.day}")
        self._update_greeting()
        return True

    def _tick_stats(self):
        s = _stats()
        self._stats_cache = s
        for val, bar, pct in ((self.cpu_val, self.cpu_bar, s["cpu"]),
                              (self.mem_val, self.mem_bar, s["mem"]),
                              (self.disk_val, self.disk_bar, s["disk"])):
            try:
                val.set_text(f"{pct}%")
                bar.set_fraction(pct / 100.0)
            except Exception:
                pass
        chg = "Charging" if s["charging"] else "On battery"
        try:
            self.batt_val.set_text(f"{s['batt']}% · {chg}")
            self.uptime_val.set_text(s["uptime"])
        except Exception:
            pass
        try:
            if not self.worker.voice:
                mic_text = "No microphone"
            elif getattr(self.worker, "mic", None) is None \
                    and getattr(self.worker, "mic_enabled", False):
                mic_text = "Starting…"
            elif getattr(self.worker, "mic_enabled", False):
                mic_text = "Listening"
            else:
                mic_text = "Muted"
            self.mic_state.set_text(mic_text)
        except Exception:
            pass
        self._sync_toggles()
        self._stat_ticks += 1
        if self._stat_ticks % 3 == 0:
            try:
                self._refresh_jobs()
            except Exception:
                pass
        if self._stat_ticks % 15 == 0:
            try:
                self._update_suggestion()
            except Exception:
                pass
        return True

    def _tick_anim(self):
        self._angle += 0.025
        self._wave_phase += 0.10
        for w in (getattr(self, "orb", None), getattr(self, "hero_wave", None)):
            try:
                if w is not None:
                    w.queue_draw()
            except Exception:
                pass
        return True

    # ---------- levels / weather ----------

    def _init_levels(self):
        """Read current volume/brightness once so sliders start truthful."""
        vol, bri = None, None
        try:
            import re as _re
            import shutil
            import subprocess
            if shutil.which("pactl"):
                out = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=4).stdout
                m = _re.search(r"/\s*(\d+)%", out)
                if m:
                    vol = max(0, min(100, int(m.group(1))))
            if shutil.which("brightnessctl"):
                cur = subprocess.run(
                    ["brightnessctl", "get"],
                    capture_output=True, text=True, timeout=4).stdout.strip()
                top = subprocess.run(
                    ["brightnessctl", "max"],
                    capture_output=True, text=True, timeout=4).stdout.strip()
                vol_cur, vol_top = int(cur or 0), int(top or 1)
                if vol_top > 0:
                    bri = max(5, min(100, round(vol_cur * 100 / vol_top)))
        except Exception:
            pass
        if vol is not None or bri is not None:
            GLib.idle_add(self._apply_init_levels, vol, bri)

    def _apply_init_levels(self, vol, bri):
        try:
            self._quiet_sliders = True
            if vol is not None:
                self.vol_scale.set_value(vol)
                self.vol_val.set_text(f"{vol}%")
            if bri is not None:
                self.bri_scale.set_value(bri)
                self.bri_val.set_text(f"{bri}%")
        except Exception:
            pass
        finally:
            self._quiet_sliders = False
        return False

    def _weather_city(self) -> str:
        """Remembered city wins, then config, then the typed box, then none."""
        try:
            from .memory import get_memory
            saved = get_memory().default_city
            if saved:
                return saved
        except Exception:
            pass
        if WEATHER_CITY_DEFAULT:
            return WEATHER_CITY_DEFAULT
        try:
            typed = self.city_entry.get_text().strip()
            if typed:
                return typed
        except Exception:
            pass
        return ""

    def _fetch_weather(self, city: str | None = None):
        """Fetch weather off-thread; only GLib.idle_add may touch widgets."""
        try:
            import requests
            target = (city or self._weather_city()).strip()
            if not target:
                GLib.idle_add(self._apply_weather, "", "", "", "", "", "")
                return
            r = requests.get(f"https://wttr.in/{target}?format=j1", timeout=10)
            if not r.ok:
                return
            data = r.json()
            cur = (data.get("current_condition") or [{}])[0]
            temp = cur.get("temp_C", "--")
            desc = (cur.get("weatherDesc") or [{}])[0].get("value", "—")
            hum = cur.get("humidity", "—")
            wind = cur.get("windspeedKmph", "—")
            feels = cur.get("FeelsLikeC", "—")
            GLib.idle_add(self._apply_weather, str(temp), str(desc), str(hum),
                          str(wind), str(feels), target)
        except Exception:
            return

    def _apply_weather(self, temp, desc, hum, wind, feels, city: str | None = None):
        if not city:
            # No city known yet — a calm empty state instead of a fake city.
            self._weather.update({"temp": "--", "desc": "", "city": ""})
            try:
                self.w_temp.set_text("--°")
                self.w_glyph.set_text("◌")
                self.w_city.set_text("SET A CITY")
                self.w_desc.set_text("for live weather")
                self.w_sub.set_text("—")
                self.top_weather.set_text("Set city")
            except Exception:
                pass
            return False
        self._weather.update({"temp": temp, "desc": desc, "city": city.upper()})
        try:
            glyph = _weather_glyph(desc)
            self.w_temp.set_text(f"{temp}°")
            self.w_glyph.set_text(glyph)
            self.w_city.set_text(city.upper())
            self.w_desc.set_text(str(desc).lower())
            try:
                wind_ms = f"{float(wind) / 3.6:.1f} m/s"
            except Exception:
                wind_ms = str(wind)
            self.w_sub.set_text(
                f"Feels {feels}° · Humidity {hum}% · Wind {wind_ms}")
            self.top_weather.set_text(f"{glyph}  {temp}°  {city.upper()}")
        except Exception:
            pass
        return False

    def _set_city(self):
        try:
            city = self.city_entry.get_text().strip()
        except Exception:
            return
        if not city:
            return
        try:
            from .memory import get_memory
            get_memory().set("default_city", city)
        except Exception:
            pass
        self._activity(f"Default city set to {city}", "accent")
        threading.Thread(target=self._fetch_weather, args=(city,),
                         daemon=True).start()

    def _refresh_weather(self):
        threading.Thread(target=self._fetch_weather, daemon=True).start()
        self._activity("Weather refreshing…", "dim")

    # ---------- worker events ----------

    def _poll_events(self):
        while True:
            try:
                event = self.worker.events.get_nowait()
            except queue.Empty:
                break
            self._apply_event(event)
        return True

    def _apply_event(self, event):
        kind = event[0]
        if kind == "state":
            self._set_state(event[1])
        elif kind == "user":
            self._add_message("user", event[1])
            self._activity(f"Command: {event[1]}", "accent")
            self._term_append(f"$ {event[1]}")
        elif kind == "assistant":
            self._add_message("ninja", event[1])
            self._term_append(str(event[1]))
            # A reply may have learned something ("my name is …", city set,
            # alias learned) — keep the memory panel truthful.
            GLib.idle_add(self._refresh_memory)
            GLib.idle_add(self._update_suggestion)
        elif kind == "notice":
            self._add_notice(event[1])
            self._activity(str(event[1]), "dim")
        elif kind == "quit":
            self._on_worker_quit()

    def _mode_text(self):
        return "CONTINUOUS" if getattr(self.worker, "no_wake", True) else "WAKE WORD"

    def _set_state(self, state):
        self._state = state
        continuous = getattr(self.worker, "no_wake", True)
        titles = {
            "idle": "Ready",
            "listening": "Listening",
            "working": "Working",
            "speaking": "Speaking",
        }
        if state == "idle":
            if not getattr(self.worker, "voice", False):
                sub = "Type a command below — the microphone is off."
            elif not getattr(self.worker, "mic_enabled", False):
                sub = "Microphone muted — type below or press Ctrl+M."
            elif continuous:
                sub = "Speak naturally — no wake word needed."
            else:
                sub = f"Say '{WAKE_WORDS[0]}' to get my attention."
        elif state == "listening":
            sub = ("Speak naturally — no wake word needed." if continuous
                   else f"Say '{WAKE_WORDS[0]}' to get my attention.")
        elif state == "working":
            sub = "Processing your request…"
        else:
            sub = "Replying aloud…"
        try:
            self.hero_state.set_text(titles.get(state, "Ready"))
            self.hero_sub.set_text(sub)
        except Exception:
            pass
        dot_cls = {"listening": "state-green", "working": "state-amber",
                   "speaking": "state-cyan"}.get(state, "state-dim")
        try:
            for c in ("state-green", "state-amber", "state-cyan", "state-dim"):
                self.state_dot.get_style_context().remove_class(c)
            self.state_dot.get_style_context().add_class(dot_cls)
        except Exception:
            pass

    # ---------- widgets: conversation / activity / console ----------

    def _avatar(self, text, cls):
        box = Gtk.EventBox()
        box.get_style_context().add_class(cls)
        box.set_size_request(30, 30)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.START)
        lbl = self._label(text, xalign=0.5)
        lbl.set_halign(Gtk.Align.CENTER)
        lbl.set_valign(Gtk.Align.CENTER)
        box.add(lbl)
        return box

    def _add_message(self, role, text):
        ts = datetime.now().strftime("%H:%M")
        is_ninja = role == "ninja"
        who = "NINJA" if is_ninja else "YOU"
        bubble = Gtk.EventBox()
        bubble.get_style_context().add_class(
            "bubble-ninja" if is_ninja else "bubble-user")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_border_width(12)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        head.pack_start(self._label(who, "msg-who" if is_ninja else "msg-who user"),
                        False, False, 0)
        head.pack_start(self._label(f"· {ts}", "msg-time"), False, False, 0)
        inner.pack_start(head, False, False, 0)

        body = self._label(text, "msg-body", wrap=True, max_chars=58,
                           selectable=True)
        inner.pack_start(body, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        copy_btn = Gtk.Button.new_with_label("Copy")
        copy_btn.get_style_context().add_class("msg-action")
        copy_btn.set_tooltip_text("Copy message to clipboard")
        copy_btn.connect("clicked", lambda b, t=text: self._copy_text(t))
        actions.pack_start(copy_btn, False, False, 0)
        if is_ninja:
            speak_btn = Gtk.Button.new_with_label("Speak")
            speak_btn.get_style_context().add_class("msg-action")
            speak_btn.set_tooltip_text("Speak this reply again")
            speak_btn.connect("clicked", lambda b, t=text: self._speak_text(t))
            actions.pack_start(speak_btn, False, False, 0)
        else:
            rerun = Gtk.Button.new_with_label("Re-run")
            rerun.get_style_context().add_class("msg-action")
            rerun.set_tooltip_text("Send this command again")
            rerun.connect("clicked", lambda b, t=text: self._send_text(t))
            actions.pack_start(rerun, False, False, 0)
        inner.pack_start(actions, False, False, 0)

        bubble.add(inner)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        avatar = self._avatar("N" if is_ninja else "Y",
                              "avatar-ninja" if is_ninja else "avatar-user")
        if is_ninja:
            row.pack_start(avatar, False, False, 0)
            row.pack_start(bubble, False, False, 0)
        else:
            row.pack_end(avatar, False, False, 0)
            row.pack_end(bubble, False, False, 0)
        self.conv_box.pack_start(row, False, False, 0)
        row.show_all()
        self._msg_count += 1
        self._update_msg_count()
        GLib.idle_add(self._scroll_bottom, self.conv_scroller)

    def _add_notice(self, text):
        lb = self._label(text, "notice", xalign=0.5, wrap=True, max_chars=60)
        lb.set_halign(Gtk.Align.CENTER)
        self.conv_box.pack_start(lb, False, False, 0)
        lb.show_all()
        GLib.idle_add(self._scroll_bottom, self.conv_scroller)

    def _update_msg_count(self):
        try:
            self.msg_count.set_text(
                f"{self._msg_count} message{'s' if self._msg_count != 1 else ''}")
        except Exception:
            pass

    def _clear_chat(self):
        for child in list(self.conv_box.get_children()):
            self.conv_box.remove(child)
        self._msg_count = 0
        self._update_msg_count()
        self._add_notice("Conversation view cleared — saved history is kept.")
        self._activity("Conversation view cleared", "dim")

    def _clear_activity(self):
        for child in list(self.act_box.get_children()):
            self.act_box.remove(child)
        self._activity("Activity cleared", "dim")

    def _clear_console(self):
        try:
            self.term_view.get_buffer().set_text(_console_header() + "\n")
        except Exception:
            pass

    def _activity(self, text, color="dim"):
        ts = datetime.now().strftime("%H:%M:%S")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        t = self._label(ts, "activity-time")
        t.set_size_request(52, -1)
        row.pack_start(t, False, False, 0)
        m = self._label(text, "activity-text", wrap=True, max_chars=36)
        m.set_ellipsize(Pango.EllipsizeMode.END)
        m.set_hexpand(True)
        cls = {"accent": "accent", "red": "red",
               "amber": "amber"}.get(color, "muted")
        m.get_style_context().add_class(cls)
        row.pack_start(m, True, True, 0)
        self.act_box.pack_start(row, False, False, 0)
        kids = self.act_box.get_children()
        if len(kids) > 80:
            self.act_box.remove(kids[0])
        row.show_all()
        GLib.idle_add(self._scroll_bottom, self.act_scroller)

    def _term_append(self, text):
        try:
            buf = self.term_view.get_buffer()
            end = buf.get_end_iter()
            buf.insert(end, (text if text.endswith("\n") else text + "\n"))
            mark = buf.create_mark(None, buf.get_end_iter(), False)
            self.term_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        except Exception:
            pass

    def _scroll_bottom(self, scroller):
        self._scroll_bottom_once(scroller)
        # Layout often settles a frame after the child is added; a second
        # pass makes sure the newest message is actually visible.
        GLib.timeout_add(60, self._scroll_bottom_once, scroller)
        return False

    def _scroll_bottom_once(self, scroller):
        try:
            adj = scroller.get_vadjustment()
            adj.set_value(max(adj.get_lower(),
                              adj.get_upper() - adj.get_page_size()))
        except Exception:
            pass
        return False

    # ---------- user actions ----------

    def _send_text(self, text):
        if self._worker_done or not (text or "").strip():
            return
        text = text.strip()
        if not self._cmd_history or self._cmd_history[-1] != text:
            self._cmd_history.append(text)
            del self._cmd_history[:-50]
        self._hist_idx = len(self._cmd_history)
        self.worker.commands.put(("text", text))

    def _update_placeholder(self, *args):
        try:
            self.entry_placeholder.set_visible(not bool(self.entry.get_text()))
        except Exception:
            pass

    def _submit(self):
        if not self.entry.get_sensitive():
            return
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self._send_text(text)

    def _on_entry_key(self, widget, event):
        """Up/Down = history, Ctrl+M = mic toggle, Esc = clear."""
        try:
            key = event.keyval
            if key in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
                if self._cmd_history:
                    self._hist_idx = max(0, self._hist_idx - 1)
                    self.entry.set_text(self._cmd_history[self._hist_idx])
                    self.entry.set_position(-1)
                return True
            if key in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
                if self._cmd_history:
                    self._hist_idx = min(len(self._cmd_history),
                                         self._hist_idx + 1)
                    txt = (self._cmd_history[self._hist_idx]
                           if self._hist_idx < len(self._cmd_history) else "")
                    self.entry.set_text(txt)
                    self.entry.set_position(-1)
                return True
            if key == Gdk.KEY_Escape:
                self.entry.set_text("")
                return True
            if (event.state & Gdk.ModifierType.CONTROL_MASK) and key in (
                    ord("m"), ord("M")):
                self._toggle_mic()
                return True
        except Exception:
            pass
        return False

    def _on_window_key(self, widget, event):
        try:
            key = event.keyval
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            if key == Gdk.KEY_F1:
                self._show_help()
                return True
            if ctrl and key in (ord("m"), ord("M")):
                self._toggle_mic()
                return True
            if ctrl and Gdk.KEY_1 <= key <= Gdk.KEY_5:
                names = [item[0] for item in NAV_ITEMS]
                self._show_page(names[key - Gdk.KEY_1])
                return True
        except Exception:
            pass
        return False

    def _toggle_mic(self, want: bool | None = None):
        if not getattr(self.worker, "voice", False):
            self._activity(
                "Microphone unavailable — start without --no-mic", "amber")
            return
        new_state = (bool(want) if want is not None
                     else not bool(getattr(self.worker, "mic_enabled", False)))
        self.worker.commands.put(("mic", new_state))
        self._mic_on = new_state
        self._style_toggle(self.mic_btn, self.mic_dot, new_state)
        self._activity(f"Microphone {'on' if new_state else 'muted'}", "dim")

    def _toggle_tts(self, want: bool | None = None):
        new_state = (bool(want) if want is not None
                     else not bool(getattr(self.worker, "tts_enabled", True)))
        self.worker.commands.put(("tts", new_state))
        self._tts_on = new_state
        self._style_toggle(self.tts_btn, self.tts_dot, new_state)
        self._activity(f"Voice replies {'on' if new_state else 'off'}", "dim")

    def _style_toggle(self, btn, dot, on):
        dot.set_text("●" if on else "○")
        ctx = dot.get_style_context()
        for cls in ("dot-on", "dot-off"):
            ctx.remove_class(cls)
        ctx.add_class("dot-on" if on else "dot-off")
        bctx = btn.get_style_context()
        for cls in ("on", "off"):
            bctx.remove_class(cls)
        bctx.add_class("on" if on else "off")

    def _sync_toggles(self):
        mic_on = bool(getattr(self.worker, "mic_enabled", False))
        tts_on = bool(getattr(self.worker, "tts_enabled", True))
        self._mic_on = mic_on
        self._tts_on = tts_on
        try:
            self._style_toggle(self.mic_btn, self.mic_dot, mic_on)
            self._style_toggle(self.tts_btn, self.tts_dot, tts_on)
        except Exception:
            pass
        try:
            self.overview_mic.set_text("On" if mic_on else "Off")
        except Exception:
            pass

    # ----- sliders / media (direct skill calls, no TTS spam) -----

    def _on_vol_slider(self, scale):
        if self._quiet_sliders:
            return
        try:
            val = int(scale.get_value())
            self.vol_val.set_text(f"{val}%")
            if self._vol_timer is not None:
                GLib.source_remove(self._vol_timer)
            self._vol_timer = GLib.timeout_add(350, self._apply_volume, val)
        except Exception:
            pass

    def _apply_volume(self, val: int):
        self._vol_timer = None

        def _do():
            try:
                from .skills import system_ctl
                ok, reply = system_ctl.volume_set(int(val))
                GLib.idle_add(self._activity, reply,
                              "accent" if ok else "dim")
            except Exception as exc:
                GLib.idle_add(self._activity, f"Volume failed: {exc}", "dim")
        threading.Thread(target=_do, daemon=True).start()
        return False

    def _on_bri_slider(self, scale):
        if self._quiet_sliders:
            return
        try:
            val = int(scale.get_value())
            self.bri_val.set_text(f"{val}%")
            if self._bri_timer is not None:
                GLib.source_remove(self._bri_timer)
            self._bri_timer = GLib.timeout_add(350, self._apply_brightness, val)
        except Exception:
            pass

    def _apply_brightness(self, val: int):
        self._bri_timer = None

        def _do():
            try:
                from .skills import system_ctl
                ok, reply = system_ctl.brightness_set(int(val))
                GLib.idle_add(self._activity, reply,
                              "accent" if ok else "dim")
            except Exception as exc:
                GLib.idle_add(self._activity, f"Brightness failed: {exc}",
                              "dim")
        threading.Thread(target=_do, daemon=True).start()
        return False

    def _media_key(self, key: str):
        def _do():
            try:
                from .skills import system_ctl
                ok, reply = system_ctl.media_key(key)
                GLib.idle_add(self._activity, f"Media {key}: {reply}",
                              "accent" if ok else "dim")
            except Exception as exc:
                GLib.idle_add(self._activity, f"Media failed: {exc}", "dim")
        threading.Thread(target=_do, daemon=True).start()

    # ----- message helpers -----

    def _copy_text(self, text: str):
        try:
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clip.set_text(text or "", -1)
            self._activity("Copied to clipboard", "dim")
        except Exception:
            pass

    def _speak_text(self, text: str):
        def _do():
            from . import ear, mouth
            mic = ear.get_ear()
            # Pause the ear so speaking from the HUD does not get transcribed
            # as a fresh command.
            try:
                mic.pause()
            except Exception:
                mic = None
            try:
                mouth.speak(text or "")
            except Exception:
                pass
            finally:
                if mic is not None:
                    try:
                        mic.resume()
                    except Exception:
                        pass
        threading.Thread(target=_do, daemon=True).start()

    def _prefill(self, text: str):
        try:
            self.entry.grab_focus()
            self.entry.set_text(text)
            self.entry.set_position(-1)
        except Exception:
            pass

    # ---------- memory panel ----------

    def _update_greeting(self):
        try:
            greeting = _greeting()
            if self._user_name:
                self.greeting_label.set_text(f"{greeting}, {self._user_name}")
            else:
                self.greeting_label.set_text(greeting)
        except Exception:
            pass

    def _refresh_memory(self):
        """Show the SmartMemory profile as small chips (name, city, facts…)."""
        try:
            for child in list(self.mem_chips.get_children()):
                self.mem_chips.remove(child)
        except Exception:
            pass
        try:
            from .memory import get_memory
            mem = get_memory()
            items: list[tuple[str, str]] = []
            if mem.user_name:
                items.append(("name", mem.user_name))
            if mem.default_city:
                items.append(("city", mem.default_city))
            for key in ("music", "app", "website"):
                fav = mem.favorite(key)
                if fav:
                    items.append((f"fav {key}", fav))
            for key, value in list(mem.preferences().items())[:6]:
                items.append((key[:18], value[:28]))
            for fact in mem.facts()[-6:]:
                items.append(("fact", fact[:32]))
            try:
                aliases = dict(mem.data.get("aliases", {}) or {})
            except Exception:
                aliases = {}
            for nick, canonical in list(aliases.items())[:4]:
                items.append((nick, str(canonical)[:24]))
            self._user_name = mem.user_name or ""
        except Exception:
            items = []
            self._user_name = ""
        if not items:
            self.mem_summary.set_text("Nothing yet — try 'my name is …' or "
                                      "'remember that …'.")
            self.overview_memory.set_text("Nothing yet")
        else:
            self.mem_summary.set_text(
                f"{len(items)} thing{'s' if len(items) != 1 else ''} remembered:")
            self.overview_memory.set_text(
                f"{len(items)} thing{'s' if len(items) != 1 else ''}")
            for key, value in items:
                chip = Gtk.EventBox()
                chip.get_style_context().add_class("mem-chip")
                chip.set_halign(Gtk.Align.START)
                chip.set_valign(Gtk.Align.START)
                lbl = self._label(f"{key}: {value}", xalign=0)
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                chip.add(lbl)
                chip.set_tooltip_text(f"{key}: {value}")
                self.mem_chips.add(chip)
                chip.show_all()
        try:
            self.mem_forget.set_sensitive(bool(items))
        except Exception:
            pass
        try:
            self.mem_chips.show_all()
        except Exception:
            pass
        self._update_greeting()

    def _forget_all(self):
        dlg = Gtk.Dialog(title="Forget everything?", transient_for=self.win,
                         modal=True)
        dlg.set_default_size(500, 230)
        content = dlg.get_content_area()
        content.set_border_width(0)
        shell = Gtk.EventBox()
        shell.get_style_context().add_class("help-shell")
        content.pack_start(shell, True, True, 0)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(22)
        shell.add(outer)
        outer.pack_start(self._label("Forget everything?", "help-title"),
                         False, False, 0)
        outer.pack_start(self._label(
            "Your name, city, favorites, preferences and facts are wiped. "
            "This cannot be undone.", "help-sub", wrap=True, max_chars=54),
            False, False, 0)
        gap = Gtk.Box()
        gap.set_vexpand(True)
        outer.pack_start(gap, True, True, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        actions.pack_start(spacer, True, True, 0)
        cancel = Gtk.Button.new_with_label("Keep memory")
        cancel.get_style_context().add_class("ghost")
        cancel.connect("clicked", lambda b: dlg.response(Gtk.ResponseType.CANCEL))
        actions.pack_start(cancel, False, False, 0)
        forget = Gtk.Button.new_with_label("Forget all")
        forget.get_style_context().add_class("danger")
        forget.connect("clicked", lambda b: dlg.response(Gtk.ResponseType.YES))
        actions.pack_start(forget, False, False, 0)
        outer.pack_start(actions, False, False, 0)
        dlg.connect("key-press-event", self._help_key)
        dlg.show_all()
        answer = dlg.run()
        dlg.destroy()
        if answer != Gtk.ResponseType.YES:
            return
        try:
            from .memory import get_memory
            mem = get_memory()
            mem.data.update({"user_name": "", "default_city": "",
                             "favorites": {"music": "", "app": "", "website": ""},
                             "preferences": {}, "facts": [], "aliases": {},
                             "corrections": {}})
            mem.save()
        except Exception:
            pass
        self._refresh_memory()
        self._activity("Memory wiped — I know nothing about you now", "amber")

    # ---------- jobs & timers ----------

    def _job_rows(self):
        """Return [(kind, id, label, status)] for jobs + timers."""
        rows: list[tuple] = []
        try:
            from . import background
            with background._lock:
                for jid, job in sorted(background._jobs.items()):
                    rows.append(("job", jid, job.get("label", "task"),
                                 job.get("status", "?")))
        except Exception:
            pass
        try:
            from .skills import reminders
            import time as _t
            with reminders._lock:
                for tid, entry in sorted(reminders._timers.items()):
                    left = max(0, int(entry["fires_at"] - _t.time()))
                    rows.append(("timer", tid,
                                 f"{entry.get('label', 'timer')} · {left}s left",
                                 "running"))
        except Exception:
            pass
        return rows[-8:]

    def _refresh_jobs(self, *args):
        for child in list(self.jobs_box.get_children()):
            self.jobs_box.remove(child)
        rows = self._job_rows()
        running = sum(1 for r in rows if r[3] == "running")
        try:
            self.jobs_count.set_text(
                f"{running} running · {len(rows)} total" if rows
                else "Nothing running")
        except Exception:
            pass
        try:
            self.overview_jobs.set_text(
                f"{running} running" if rows else "Idle")
        except Exception:
            pass
        if not rows:
            try:
                self.jobs_scroller.hide()
                self.jobs_empty.show_all()
            except Exception:
                pass
        else:
            try:
                self.jobs_empty.hide()
                self.jobs_scroller.show_all()
            except Exception:
                pass
        for kind, jid, label, status in rows:
            row = Gtk.EventBox()
            row.get_style_context().add_class("job-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            inner.set_border_width(9)
            row.add(inner)
            dot = self._label("●")
            dot.get_style_context().add_class(
                "accent" if status == "running"
                else ("green" if status == "done" else "muted"))
            inner.pack_start(dot, False, False, 0)
            name = self._label(f"{kind} #{jid} · {label[:40]}", "job-name")
            name.set_hexpand(True)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            inner.pack_start(name, True, True, 0)
            if status == "running":
                cancel = Gtk.Button.new_with_label("Cancel")
                cancel.get_style_context().add_class("ghost")
                cancel.set_tooltip_text(f"Cancel {kind} #{jid}")
                cancel.connect("clicked", lambda b, k=kind, i=jid:
                               self._cancel_row(k, i))
                inner.pack_start(cancel, False, False, 0)
            else:
                st = self._label(status, "muted")
                inner.pack_start(st, False, False, 0)
            self.jobs_box.pack_start(row, False, False, 0)
            row.show_all()

    def _cancel_row(self, kind: str, jid: int):
        def _do():
            try:
                if kind == "job":
                    from . import background
                    _, reply = background.cancel_job(jid)
                else:
                    from .skills import reminders
                    _, reply = reminders.cancel_timer(jid)
                GLib.idle_add(self._activity, reply, "accent")
                GLib.idle_add(self._refresh_jobs)
            except Exception as exc:
                GLib.idle_add(self._activity, f"Cancel failed: {exc}", "dim")
        threading.Thread(target=_do, daemon=True).start()

    def _clear_jobs(self, *args):
        def _do():
            try:
                from . import background
                _, reply = background.clear_finished()
                GLib.idle_add(self._activity, reply, "dim")
                GLib.idle_add(self._refresh_jobs)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    # ---------- smart suggestion ----------

    def _update_suggestion(self):
        """Chat-aware hint: memory nudge first, then usage habits, then time."""
        hint, cmd = "", "briefing"
        try:
            from .memory import get_memory
            mem = get_memory()
            hint = mem.suggestion()
            import re as _re
            m = _re.search(r"'([^']+)'", hint or "")
            if m:
                cmd = m.group(1)
        except Exception:
            hint = ""
        if not hint:
            # Habit: the most-repeated two-word command this session.
            try:
                from .memory import get_memory
                usage = dict(get_memory().data.get("usage", {}) or {})
                usage.pop("briefing", None)
                if usage:
                    top = max(usage, key=lambda k: usage[k])
                    if usage.get(top, 0) >= 2:
                        hint = f"Say '{top}' again?"
                        cmd = top
            except Exception:
                pass
        if not hint:
            hour = datetime.now().hour
            if hour >= 18:
                city = ""
                try:
                    from .memory import get_memory
                    city = get_memory().default_city
                except Exception:
                    city = ""
                if city:
                    hint = f"Evening check — 'what is the weather in {city}'?"
                    cmd = f"what's the weather in {city}"
        if not hint:
            hour = datetime.now().hour
            hint = ("Start your day — try 'briefing' for your overview"
                    if 5 <= hour < 12
                    else "Try 'briefing' for your daily overview")
            cmd = "briefing"
        self.suggest_label.set_text(hint)
        self._suggest_cmd = cmd
        try:
            self.suggest_btn.set_sensitive(bool(cmd))
        except Exception:
            pass

    def _run_suggestion(self):
        if self._suggest_cmd:
            self._send_text(self._suggest_cmd)
        else:
            self.entry.grab_focus()

    # ---------- help ----------

    def _show_help(self):
        dlg = Gtk.Dialog(title=f"{DISPLAY_NAME} · Command guide",
                         transient_for=self.win, modal=True)
        dlg.set_default_size(740, 680)
        dlg.get_style_context().add_class("help-dialog")
        content = dlg.get_content_area()
        content.set_border_width(0)

        shell = Gtk.EventBox()
        shell.get_style_context().add_class("help-shell")
        content.pack_start(shell, True, True, 0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_border_width(22)
        shell.add(outer)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.pack_start(self._label("Command guide", "help-title"),
                             False, False, 0)
        title_box.pack_start(self._label(
            "Everything you can say or type. Voice commands work without the "
            "wake word unless noted.", "help-sub", wrap=True, max_chars=76),
            False, False, 0)
        head.pack_start(title_box, True, True, 0)
        close_btn = self._icon_button(
            "✕", "Close (Esc)", lambda b: dlg.response(Gtk.ResponseType.CLOSE))
        close_btn.set_valign(Gtk.Align.START)
        head.pack_start(close_btn, False, False, 0)
        outer.pack_start(head, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(480)
        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for title, body in HELP_SECTIONS:
            sec = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            sec.pack_start(self._label(title.upper(), "help-section"),
                           False, False, 0)
            body_lb = self._label(body, "help-body", wrap=True,
                                  max_chars=76, selectable=True)
            body_lb.set_can_focus(False)
            sec.pack_start(body_lb, False, False, 0)
            sections.pack_start(sec, False, False, 0)
        scroller.add(sections)
        outer.pack_start(scroller, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.pack_start(self._label(
            "Tip: chain tasks with 'and' or 'then'.", "muted"),
            True, True, 0)
        got_it = Gtk.Button.new_with_label("Got it")
        got_it.get_style_context().add_class("primary")
        got_it.connect("clicked", lambda b: dlg.response(Gtk.ResponseType.CLOSE))
        footer.pack_start(got_it, False, False, 0)
        outer.pack_start(footer, False, False, 0)

        dlg.connect("key-press-event", self._help_key)
        dlg.show_all()
        GLib.idle_add(self._reset_scroll, scroller)
        close_btn.grab_focus()
        dlg.run()
        dlg.destroy()

    @staticmethod
    def _help_key(dialog, event):
        if event.keyval == Gdk.KEY_Escape:
            dialog.response(Gtk.ResponseType.CLOSE)
            return True
        return False

    @staticmethod
    def _reset_scroll(scroller):
        try:
            scroller.get_vadjustment().set_value(0)
        except Exception:
            pass
        return False

    # ---------- lifecycle ----------

    def _on_worker_quit(self):
        self._worker_done = True
        self._set_state("idle")
        try:
            self.hero_state.set_text("Offline")
            self.hero_sub.set_text("NINJA has shut down — close the window to exit.")
        except Exception:
            pass
        try:
            self.online_pill.set_text("OFFLINE")
            ctx = self.online_pill_box.get_style_context()
            ctx.remove_class("online")
            ctx.add_class("offline")
        except Exception:
            pass
        for w in (self.entry, self.send_btn, self.suggest_btn):
            try:
                w.set_sensitive(False)
            except Exception:
                pass
        self._add_notice("NINJA has shut down — close the window to exit.")

    def _on_delete(self, widget, event):
        self.worker.stop()
        return False

    def _on_destroy(self, widget):
        self.worker.stop()
        Gtk.main_quit()

    def _restore_conversation(self, tail: int = 6):
        """Show the tail of the previous conversation as read-only history.

        Uses the same persisted store the AI brain reads, so the chat
        survives restarts. Called from run(); safe to call anytime.
        """
        try:
            from .config import SPARK_HISTORY_PATH
            import json as _json
            data = _json.loads(SPARK_HISTORY_PATH.read_text())
        except Exception:
            return
        if not isinstance(data, list):
            return
        shown = 0
        for msg in data[-tail:]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = str(msg.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                self._add_message("user" if role == "user" else "ninja",
                                  content)
                shown += 1
        if shown:
            self._add_notice("— previous conversation restored —")

    def run(self):
        continuous = getattr(self.worker, "no_wake", True)
        self._activity(
            f"NINJA online — {'continuous listening' if continuous else 'wake word mode'}",
            "accent")
        try:
            from .memory import get_memory
            name = get_memory().user_name
            hello = f"Welcome back, {name}. " if name else ""
        except Exception:
            hello = ""
        if not getattr(self.worker, "voice", False):
            intro = ("The microphone is off, but I'm ready for typed commands. "
                     "Try 'briefing' for a quick overview.")
        elif continuous:
            intro = ("I'm listening — speak naturally, or type below. "
                     "Try 'briefing' for a quick overview.")
        else:
            intro = (f"I'm listening for '{WAKE_WORDS[0]}' — or type below. "
                     "Try 'briefing' for a quick overview.")
        self._add_message("ninja", f"{hello}{intro}")
        self._restore_conversation()
        self.win.show_all()
        try:
            self._refresh_jobs()
            self._update_suggestion()
            self._refresh_memory()
            self._sync_toggles()
        except Exception:
            pass
        self.entry.grab_focus()
        Gtk.main()
