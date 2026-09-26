"""NINJA console — clean professional desktop assistant window.

Three-column layout:

    left    system, sound & display, weather
    center  assistant status, quick actions, activity, jobs & timers
    right   conversation, console transcript

Talks to AssistantWorker through its command/event queues so the GUI never
blocks on the mic, brain or TTS.
"""

import math
import queue
import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .config import ASSISTANT_NAME, WAKE_WORDS  # noqa: E402
from .worker import AssistantWorker  # noqa: E402

DISPLAY_NAME = "NINJA"
CITY_DEFAULT = "Quezon City"

ACCENT = (0.35, 0.65, 1.00)   # #58a6ff
GREEN = (0.25, 0.73, 0.35)    # #3fb950

CSS = b"""
window { background-color: #0d1117; }
label, button, entry { font-family: Sans; }
label { color: #e6edf3; }
scrolledwindow { background-color: transparent; border: none; }
textview { background-color: #0d1117; color: #8b949e; }
textview text { background-color: #0d1117; font-family: Monospace; }
entry { background-color: #0d1117; color: #e6edf3; border: 1px solid #30363d;
        border-radius: 6px; padding: 7px 9px; }
entry:focus { border-color: #58a6ff; }
button { background-color: #21262d; color: #e6edf3; border: 1px solid #30363d;
         border-radius: 6px; padding: 4px 10px; }
button:hover { border-color: #58a6ff; }
button:disabled { color: #6e7681; }
.hud-panel { background-color: #151b23; border: 1px solid #2b333d; border-radius: 8px; }
.hud-title { color: #8b949e; font-size: 9px; letter-spacing: 2px; }
.hud-value { color: #e6edf3; font-size: 12px; }
.hud-dim { color: #8b949e; font-size: 10px; }
.hud-accent { color: #58a6ff; }
.hud-green { color: #3fb950; }
.hud-red { color: #f85149; }
.hud-amber { color: #d29922; }
.hud-big { font-size: 24px; color: #ffffff; }

.bubble-user { background: rgba(210,153,34,0.07); border: 1px solid #4a3f1e; border-radius: 8px; }
.bubble-ninja { background: rgba(56,139,253,0.08); border: 1px solid #2a4a6b; border-radius: 8px; }
.chip { background-color: #21262d; border: 1px solid #30363d; border-radius: 13px;
        padding: 2px 10px; font-size: 10px; }
.chip:hover { border-color: #58a6ff; color: #58a6ff; }
.suggest-bar { background-color: rgba(56,139,253,0.06); border: 1px solid #2a4a6b;
               border-radius: 8px; }
progressbar trough { background-color: #21262d; border-radius: 4px; min-height: 6px; }
progressbar progress { background-color: #58a6ff; border-radius: 4px; }
scale trough { background-color: #21262d; border-radius: 4px; min-height: 6px; }
scale highlight { background-color: #58a6ff; border-radius: 4px; }
scale slider { background-color: #e6edf3; border-radius: 8px; min-width: 12px; min-height: 12px; }
.msg-action { border: none; background: transparent; color: #6e7681; font-size: 10px; padding: 0 6px 0 0; }
.msg-action:hover { color: #58a6ff; border-color: transparent; }
.job-row { background-color: #0d1117; border: 1px solid #2b333d; border-radius: 6px; }
"""

QUICK_ACTIONS = [
    ("Lofi", "play lofi beats"),
    ("Weather", "what's the weather"),
    ("Screenshot", "take a screenshot"),
    ("Status", "system status"),
    ("Timer 5 min", "set a timer for 5 minutes"),
    ("Joke", "tell me a joke"),
    ("Briefing", "briefing"),
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
    "lock screen", "briefing", "what do you remember", "my name is ",
    "my city is ", "remember that I prefer concise answers", "spark status",
    "clear chat history", "find the latest PDF in my CS folder", "read notifications",
    "git status", "create a study plan",
]

VOICE_HELP = (
    "NINJA listens continuously — just speak, no wake word needed "
    "(say 'Ninja' before a phrase to make sure it answers).\n"
    "Chain tasks in one breath with 'and' / 'then': "
    "'open youtube and play believer'.\n"
    "• Apps & web: open youtube · play believer · open vscode · open terminal · "
    "open whatsapp · open telegram · close chrome\n"
    "• Message: message mom hello · whatsapp dad call me back\n"
    "• Page: find cats · scroll down · click · comment nice video on this post\n"
    "• Mouse: move mouse to the center · move mouse to 500, 300 · click · "
    "right click · scroll up/down · drag left\n"
    "• Type: type hello world · press enter · copy · paste\n"
    "• Timers: set a timer for 10 minutes · remind me to call mom in 20 minutes\n"
    "• System: volume up · set volume to 40 · brightness up · take a screenshot · "
    "system status · lock screen\n"
    "• Radios: turn wifi off · switch bluetooth on · read my clipboard\n"
    "• Windows: focus chrome · minimise · maximise · list windows · "
    "go to workspace 2 · move this window to workspace 3\n"
    "• Files & study: open my CS folder · find the latest PDF · summarize it · "
    "create a study plan · read notifications\n"
    "• Developer: git status · git diff · run python code (confirmation required)\n"
    "• Smart memory: my name is Priya · my city is Mumbai · what do you remember · "
    "remember that I prefer concise answers · turn it up · again · briefing"
)


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


def _console_header():
    return "ninja console — commands and replies are logged here"


class ChatWindow:
    """NINJA console front-end for an AssistantWorker (same API as before)."""

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
        self._weather = {"temp": "--", "city": CITY_DEFAULT.upper(), "desc": "—"}
        self._build_css()
        self._build_window()
        GLib.timeout_add(100, self._poll_events)
        GLib.timeout_add(1000, self._tick_clock)
        GLib.timeout_add(2000, self._tick_stats)
        GLib.timeout_add(50, self._tick_anim)
        threading.Thread(target=self._fetch_weather, daemon=True).start()
        threading.Thread(target=self._init_levels, daemon=True).start()
        self._term_append(_console_header())

    def _build_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no display available — cannot open the window")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            display.get_default_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _panel(self, title):
        frame = Gtk.EventBox()
        frame.get_style_context().add_class("hud-panel")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)
        frame.add(box)
        t = Gtk.Label(label=title)
        t.get_style_context().add_class("hud-title")
        t.set_xalign(0)
        box.pack_start(t, False, False, 0)
        return frame, box

    def _small(self, text, cls="hud-dim"):
        lb = Gtk.Label(label=text)
        lb.get_style_context().add_class(cls)
        lb.set_xalign(0)
        return lb

    def _meter_row(self, box, name):
        """Labelled progress row; returns (value_label, progressbar)."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        key = Gtk.Label(label=name)
        key.get_style_context().add_class("hud-dim")
        key.set_size_request(72, -1)
        key.set_xalign(0)
        row.pack_start(key, False, False, 0)
        bar = Gtk.ProgressBar()
        bar.set_hexpand(True)
        bar.set_valign(Gtk.Align.CENTER)
        row.pack_start(bar, True, True, 0)
        val = Gtk.Label(label="—")
        val.get_style_context().add_class("hud-value")
        val.set_size_request(44, -1)
        val.set_xalign(1)
        row.pack_start(val, False, False, 0)
        box.pack_start(row, False, False, 0)
        return val, bar

    def _build_window(self):
        Gtk.Window.set_default_icon_name("audio-input-microphone")
        self.win = Gtk.Window(title=f"{DISPLAY_NAME} — Desktop Assistant")
        self.win.set_default_size(1280, 800)
        self.win.connect("delete-event", self._on_delete)
        self.win.connect("destroy", self._on_destroy)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        # ===== top bar =====
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top.set_border_width(10)
        root.pack_start(top, False, False, 0)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bname = Gtk.Label(label=DISPLAY_NAME)
        bname.get_style_context().add_class("hud-value")
        brand.pack_start(bname, False, False, 0)
        self.online_pill = Gtk.Label(label="● ONLINE")
        self.online_pill.get_style_context().add_class("online-pill")
        brand.pack_start(self.online_pill, False, False, 0)
        top.pack_start(brand, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top.pack_start(spacer, True, True, 0)

        self.clock_label = Gtk.Label(label="--:--")
        self.clock_label.get_style_context().add_class("hud-value")
        top.pack_start(self.clock_label, False, False, 0)
        self.date_label = Gtk.Label(label="")
        self.date_label.get_style_context().add_class("hud-dim")
        top.pack_start(self.date_label, False, False, 0)
        self.top_weather = Gtk.Label(label="")
        self.top_weather.get_style_context().add_class("hud-dim")
        top.pack_start(self.top_weather, False, False, 0)
        help_btn = Gtk.Button.new_with_label("Help")
        help_btn.set_tooltip_text("Voice command help")
        help_btn.connect("clicked", lambda b: self._show_help())
        top.pack_start(help_btn, False, False, 0)

        # ===== main columns =====
        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main.set_border_width(10)
        root.pack_start(main, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left.set_size_request(248, -1)
        main.pack_start(left, False, False, 0)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        center.set_hexpand(True)
        main.pack_start(center, True, True, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right.set_size_request(392, -1)
        main.pack_start(right, False, False, 0)

        self._build_left(left)
        self._build_center(center)
        self._build_right(right)

        # ===== footer =====
        foot = Gtk.Label(
            label="Just speak, or type below  ·  ↑↓ history  ·  Ctrl+M mutes the mic")
        foot.get_style_context().add_class("hud-dim")
        root.pack_start(foot, False, False, 4)

    # ---------- left: system / sound / weather ----------

    def _build_left(self, left):
        sys_panel, sys_box = self._panel("SYSTEM")
        left.pack_start(sys_panel, False, False, 0)
        self.cpu_val, self.cpu_bar = self._meter_row(sys_box, "CPU")
        self.mem_val, self.mem_bar = self._meter_row(sys_box, "Memory")
        self.disk_val, self.disk_bar = self._meter_row(sys_box, "Disk")
        batt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        batt_key = Gtk.Label(label="Battery")
        batt_key.get_style_context().add_class("hud-dim")
        batt_key.set_size_request(72, -1)
        batt_key.set_xalign(0)
        batt_row.pack_start(batt_key, False, False, 0)
        self.batt_val = Gtk.Label(label="—")
        self.batt_val.get_style_context().add_class("hud-value")
        self.batt_val.set_hexpand(True)
        self.batt_val.set_xalign(1)
        batt_row.pack_start(self.batt_val, True, True, 0)
        sys_box.pack_start(batt_row, False, False, 0)
        upt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        upt_key = Gtk.Label(label="Uptime")
        upt_key.get_style_context().add_class("hud-dim")
        upt_key.set_size_request(72, -1)
        upt_key.set_xalign(0)
        upt_row.pack_start(upt_key, False, False, 0)
        self.uptime_val = Gtk.Label(label="—")
        self.uptime_val.get_style_context().add_class("hud-value")
        self.uptime_val.set_hexpand(True)
        self.uptime_val.set_xalign(1)
        upt_row.pack_start(self.uptime_val, True, True, 0)
        sys_box.pack_start(upt_row, False, False, 0)

        snd_panel, snd_box = self._panel("SOUND & DISPLAY")
        left.pack_start(snd_panel, False, False, 0)
        snd_box.pack_start(self._small("Volume"), False, False, 0)
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vol_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol_scale.set_value(50)
        self.vol_scale.set_hexpand(True)
        self.vol_scale.set_tooltip_text("Speaker volume")
        self.vol_scale.connect("value-changed", self._on_vol_slider)
        vol_row.pack_start(self.vol_scale, True, True, 0)
        self.vol_val = Gtk.Label(label="50%")
        self.vol_val.get_style_context().add_class("hud-dim")
        self.vol_val.set_size_request(40, -1)
        vol_row.pack_start(self.vol_val, False, False, 0)
        mute_btn = Gtk.Button.new_with_label("Mute")
        mute_btn.set_tooltip_text("Toggle mute (voice: mute)")
        mute_btn.connect("clicked", lambda b: self._send_text("mute"))
        vol_row.pack_start(mute_btn, False, False, 0)
        snd_box.pack_start(vol_row, False, False, 0)
        snd_box.pack_start(self._small("Brightness"), False, False, 0)
        bri_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bri_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 5, 100, 1)
        self.bri_scale.set_value(80)
        self.bri_scale.set_hexpand(True)
        self.bri_scale.set_tooltip_text("Screen brightness")
        self.bri_scale.connect("value-changed", self._on_bri_slider)
        bri_row.pack_start(self.bri_scale, True, True, 0)
        self.bri_val = Gtk.Label(label="80%")
        self.bri_val.get_style_context().add_class("hud-dim")
        self.bri_val.set_size_request(40, -1)
        bri_row.pack_start(self.bri_val, False, False, 0)
        snd_box.pack_start(bri_row, False, False, 0)
        media_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for icon, tip, key in (("⏮", "Previous track", "previous"),
                               ("⏯", "Play / pause", "playpause"),
                               ("⏭", "Next track", "next")):
            btn = Gtk.Button.new_with_label(icon)
            btn.set_tooltip_text(f"{tip} (voice: {key})")
            btn.connect("clicked", lambda b, k=key: self._media_key(k))
            media_row.pack_start(btn, True, True, 0)
        snd_box.pack_start(media_row, False, False, 2)

        w_panel, w_box = self._panel("WEATHER")
        left.pack_start(w_panel, False, False, 0)
        w_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.w_temp = Gtk.Label(label="--°")
        self.w_temp.get_style_context().add_class("hud-big")
        w_top.pack_start(self.w_temp, False, False, 0)
        w_meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.w_city = Gtk.Label(label=CITY_DEFAULT.upper())
        self.w_city.get_style_context().add_class("hud-accent")
        self.w_city.set_xalign(0)
        w_meta.pack_start(self.w_city, False, False, 0)
        self.w_desc = self._small("—")
        w_meta.pack_start(self.w_desc, False, False, 0)
        w_top.pack_start(w_meta, True, True, 0)
        w_box.pack_start(w_top, False, False, 0)
        self.w_sub = self._small("—")
        w_box.pack_start(self.w_sub, False, False, 0)
        city_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.city_entry = Gtk.Entry()
        self.city_entry.set_placeholder_text("Change city…")
        self.city_entry.set_hexpand(True)
        self.city_entry.connect("activate", lambda w: self._set_city())
        city_row.pack_start(self.city_entry, True, True, 0)
        city_set = Gtk.Button.new_with_label("Set")
        city_set.set_tooltip_text("Remember this city and refresh")
        city_set.connect("clicked", lambda b: self._set_city())
        city_row.pack_start(city_set, False, False, 0)
        city_go = Gtk.Button.new_with_label("⟳")
        city_go.set_tooltip_text("Refresh weather now")
        city_go.connect("clicked", lambda b: self._refresh_weather())
        city_row.pack_start(city_go, False, False, 0)
        w_box.pack_start(city_row, False, False, 0)

    # ---------- center: assistant / actions / activity / jobs ----------

    def _build_center(self, col):
        as_panel, as_box = self._panel("ASSISTANT")
        col.pack_start(as_panel, False, False, 0)
        self.core_draw = Gtk.DrawingArea()
        self.core_draw.set_size_request(-1, 210)
        self.core_draw.connect("draw", self._draw_core)
        as_box.pack_start(self.core_draw, False, False, 0)
        self.core_status = Gtk.Label(label="Starting…")
        self.core_status.get_style_context().add_class("hud-value")
        as_box.pack_start(self.core_status, False, False, 0)
        self.core_wave = Gtk.DrawingArea()
        self.core_wave.set_size_request(-1, 22)
        self.core_wave.connect("draw", self._draw_core_wave)
        as_box.pack_start(self.core_wave, False, False, 0)

        chips = Gtk.FlowBox()
        chips.set_selection_mode(Gtk.SelectionMode.NONE)
        chips.set_max_children_per_line(7)
        chips.set_column_spacing(6)
        for label, cmd in QUICK_ACTIONS:
            btn = Gtk.Button.new_with_label(label)
            btn.get_style_context().add_class("chip")
            btn.set_tooltip_text(f"Send: {cmd}")
            btn.connect("clicked", lambda b, c=cmd: self._send_text(c))
            chips.add(btn)
        col.pack_start(chips, False, False, 0)

        sugg_box = Gtk.EventBox()
        sugg_box.get_style_context().add_class("suggest-bar")
        sugg_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sugg_inner.set_border_width(8)
        sugg_box.add(sugg_inner)
        self.suggest_label = Gtk.Label(
            label="Try 'briefing' for your daily overview")
        self.suggest_label.get_style_context().add_class("hud-dim")
        self.suggest_label.set_xalign(0)
        self.suggest_label.set_hexpand(True)
        self.suggest_label.set_line_wrap(True)
        sugg_inner.pack_start(self.suggest_label, True, True, 0)
        self.suggest_btn = Gtk.Button.new_with_label("Run")
        self.suggest_btn.set_tooltip_text("Run the suggested command")
        self.suggest_btn.connect("clicked", lambda b: self._run_suggestion())
        sugg_inner.pack_start(self.suggest_btn, False, False, 0)
        col.pack_start(sugg_box, False, False, 0)

        act_panel, act_box = self._panel("ACTIVITY")
        col.pack_start(act_panel, False, False, 0)
        self.act_scroller = Gtk.ScrolledWindow()
        self.act_scroller.set_policy(Gtk.PolicyType.NEVER,
                                     Gtk.PolicyType.AUTOMATIC)
        self.act_scroller.set_min_content_height(96)
        try:
            self.act_scroller.set_max_content_height(130)
        except AttributeError:
            self.act_scroller.set_size_request(-1, 115)
        self.act_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.act_scroller.add(self.act_box)
        act_box.pack_start(self.act_scroller, True, True, 0)

        job_panel, job_box = self._panel("JOBS & TIMERS")
        col.pack_start(job_panel, False, False, 0)
        job_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.jobs_count = Gtk.Label(label="Idle")
        self.jobs_count.get_style_context().add_class("hud-dim")
        self.jobs_count.set_hexpand(True)
        self.jobs_count.set_xalign(0)
        job_head.pack_start(self.jobs_count, True, True, 0)
        for label, tip, fn in (("Refresh", "Refresh the list", self._refresh_jobs),
                               ("List", "Ask: list jobs",
                                lambda b: self._send_text("list jobs")),
                               ("Clear", "Clear finished jobs", self._clear_jobs)):
            btn = Gtk.Button.new_with_label(label)
            btn.set_tooltip_text(tip)
            btn.connect("clicked", fn)
            job_head.pack_start(btn, False, False, 0)
        job_box.pack_start(job_head, False, False, 0)
        self.jobs_scroller = Gtk.ScrolledWindow()
        self.jobs_scroller.set_policy(Gtk.PolicyType.NEVER,
                                      Gtk.PolicyType.AUTOMATIC)
        self.jobs_scroller.set_min_content_height(72)
        try:
            self.jobs_scroller.set_max_content_height(120)
        except AttributeError:
            self.jobs_scroller.set_size_request(-1, 100)
        self.jobs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.jobs_scroller.add(self.jobs_box)
        job_box.pack_start(self.jobs_scroller, True, True, 0)

    # ---------- right: status / conversation / console ----------

    def _build_right(self, col):
        status_panel, status_box = self._panel("STATUS")
        col.pack_start(status_panel, False, False, 0)
        state_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.state_dot = Gtk.Label(label="●")
        self.state_dot.get_style_context().add_class("hud-green")
        state_row.pack_start(self.state_dot, False, False, 0)
        self.mic_state = Gtk.Label(label="Listening")
        self.mic_state.get_style_context().add_class("hud-value")
        self.mic_state.set_hexpand(True)
        self.mic_state.set_xalign(0)
        state_row.pack_start(self.mic_state, True, True, 0)
        self.mode_label = Gtk.Label(label=self._mode_text())
        self.mode_label.get_style_context().add_class("hud-dim")
        state_row.pack_start(self.mode_label, False, False, 0)
        status_box.pack_start(state_row, False, False, 0)
        tog_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mic_lbl = Gtk.Label(label="Microphone")
        mic_lbl.get_style_context().add_class("hud-dim")
        tog_row.pack_start(mic_lbl, False, False, 0)
        self.mic_switch = Gtk.Switch()
        self.mic_switch.set_active(True)
        self.mic_switch.set_tooltip_text("Microphone on/off (Ctrl+M)")
        self.mic_switch.connect(
            "notify::active", lambda s, p: self._toggle_mic(s.get_active()))
        tog_row.pack_start(self.mic_switch, False, False, 0)
        tts_lbl = Gtk.Label(label="Voice replies")
        tts_lbl.get_style_context().add_class("hud-dim")
        tog_row.pack_start(tts_lbl, False, False, 0)
        self.tts_switch = Gtk.Switch()
        self.tts_switch.set_active(True)
        self.tts_switch.set_tooltip_text("Spoken replies on/off")
        self.tts_switch.connect(
            "notify::active", lambda s, p: self._toggle_tts(s.get_active()))
        tog_row.pack_start(self.tts_switch, False, False, 0)
        status_box.pack_start(tog_row, False, False, 0)

        conv_panel, conv_box = self._panel("CONVERSATION")
        col.pack_start(conv_panel, True, True, 0)
        self.conv_scroller = Gtk.ScrolledWindow()
        self.conv_scroller.set_policy(Gtk.PolicyType.NEVER,
                                      Gtk.PolicyType.AUTOMATIC)
        self.conv_scroller.set_min_content_height(220)
        self.conv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.conv_scroller.add(self.conv_box)
        conv_box.pack_start(self.conv_scroller, True, True, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ask anything, or just speak…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda w: self._submit())
        self.entry.connect("key-press-event", self._on_entry_key)
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
        row.pack_start(self.entry, True, True, 0)
        send = Gtk.Button.new_with_label("Send")
        send.connect("clicked", lambda b: self._submit())
        row.pack_start(send, False, False, 0)
        conv_box.pack_start(row, False, False, 0)

        term_panel, term_box = self._panel("CONSOLE")
        col.pack_start(term_panel, False, False, 0)
        self.term_scroller = Gtk.ScrolledWindow()
        self.term_scroller.set_policy(Gtk.PolicyType.AUTOMATIC,
                                      Gtk.PolicyType.AUTOMATIC)
        self.term_scroller.set_min_content_height(104)
        self.term_view = Gtk.TextView()
        self.term_view.set_editable(False)
        self.term_view.set_cursor_visible(False)
        self.term_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.term_view.override_font(Pango.FontDescription("Monospace 8"))
        self.term_scroller.add(self.term_view)
        term_box.pack_start(self.term_scroller, True, True, 0)

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

    def _draw_core(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 10
        if R <= 0:
            return False
        s = _stats()
        cpu_f = max(0.03, min(1.0, s["cpu"] / 100.0))
        mem_f = max(0.03, min(1.0, s["mem"] / 100.0))
        cr.set_source_rgb(0.05, 0.07, 0.09)
        cr.paint()
        # faint tick ring, slowly rotating
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(self._angle * 0.2)
        for i in range(48):
            a = 2 * math.pi * i / 48
            long_tick = (i % 4 == 0)
            r1 = R
            r0 = R - (9 if long_tick else 5)
            cr.set_source_rgba(*ACCENT, 0.55 if long_tick else 0.22)
            cr.set_line_width(2 if long_tick else 1)
            cr.move_to(r0 * math.cos(a), r0 * math.sin(a))
            cr.line_to(r1 * math.cos(a), r1 * math.sin(a))
            cr.stroke()
        cr.restore()
        # CPU + memory arcs
        cr.set_source_rgb(*ACCENT)
        cr.set_line_width(4)
        cr.arc(cx, cy, R * 0.78, math.pi * 0.6,
               math.pi * 0.6 + math.pi * 1.1 * cpu_f + 0.04)
        cr.stroke()
        cr.set_source_rgb(*GREEN)
        cr.set_line_width(4)
        cr.arc(cx, cy, R * 0.78, -math.pi * 0.38,
               -math.pi * 0.38 + math.pi * 1.05 * mem_f + 0.04)
        cr.stroke()
        # breathing core ring follows the live mic level
        mic_level, _ = self._get_mic_visual()
        pulse = 1.0 + mic_level * 0.06 + 0.008 * math.sin(self._wave_phase * 2)
        cr.set_source_rgba(*ACCENT, 0.85)
        cr.set_line_width(2 + mic_level * 2)
        cr.arc(cx, cy, R * 0.52 * pulse, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(*ACCENT, 0.10 + mic_level * 0.22)
        cr.set_line_width(9 + mic_level * 9)
        cr.arc(cx, cy, R * 0.52 * pulse, 0, 2 * math.pi)
        cr.stroke()
        return False

    def _draw_core_wave(self, area, cr):
        """Audio-intake visualiser: bars driven by the live mic meter."""
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(0.05, 0.07, 0.09)
        cr.paint()
        level, hist = self._get_mic_visual()
        live = level > 0.02
        n_bars = 28
        gap = 4.0
        bar_w = min(8.0, (w - gap * (n_bars + 1)) / n_bars)
        total = n_bars * bar_w + (n_bars - 1) * gap
        x0 = (w - total) / 2 + bar_w / 2
        mid = h / 2
        try:
            cr.set_line_cap(1)  # pill-shaped bars
        except Exception:
            pass
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
                v = 0.06 + 0.05 * abs(math.sin(i * 0.55 + self._wave_phase * 1.6))
            bar_h = max(3.0, v * (h - 6))
            alpha = 0.5 + 0.45 * min(1.0, v * 1.6)
            cr.set_source_rgba(*ACCENT, alpha)
            cr.set_line_width(bar_w)
            cr.move_to(x0 + i * (bar_w + gap), mid - bar_h / 2)
            cr.line_to(x0 + i * (bar_w + gap), mid + bar_h / 2)
            cr.stroke()
        return False

    # ---------- live ticks ----------

    def _tick_clock(self):
        now = datetime.now()
        self.clock_label.set_text(now.strftime("%I:%M %p").lstrip("0"))
        self.date_label.set_text(now.strftime("%a, %b %d").upper())
        return True

    def _tick_stats(self):
        s = _stats()
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
        listening = (self._state == "listening" or (
            self.worker.voice and self.worker.mic_enabled
            and self.worker.mic is not None))
        if not self._worker_done:
            try:
                self.mic_state.set_text(
                    "Listening" if listening else "Muted")
            except Exception:
                pass
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
        self._angle += 0.05
        self._wave_phase += 0.12
        for w in (self.core_draw, self.core_wave):
            try:
                w.queue_draw()
            except Exception:
                pass
        return True

    # ---------- levels / weather ----------

    def _init_levels(self):
        """Read current volume/brightness once so sliders start truthful."""
        vol, bri = None, None
        try:
            import shutil
            import subprocess
            if shutil.which("pactl"):
                out = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=4).stdout
                import re as _re
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
        """Remembered city wins, then the typed box, then the default."""
        try:
            from .memory import get_memory
            saved = get_memory().default_city
            if saved:
                return saved
        except Exception:
            pass
        try:
            typed = self.city_entry.get_text().strip()
            if typed:
                return typed
        except Exception:
            pass
        return CITY_DEFAULT

    def _fetch_weather(self, city: str | None = None):
        try:
            import requests
            target = city or self._weather_city()
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
        city = city or self._weather_city()
        self._weather.update({"temp": temp, "desc": desc, "city": city.upper()})
        try:
            self.w_temp.set_text(f"{temp}°")
            self.w_city.set_text(city.upper())
            self.w_desc.set_text(str(desc).lower())
            try:
                wind_ms = f"{float(wind) / 3.6:.1f} m/s"
            except Exception:
                wind_ms = str(wind)
            self.w_sub.set_text(
                f"Feels {feels}° · Hum {hum}% · Wind {wind_ms}")
            self.top_weather.set_text(f"{temp}°  {city.upper()}")
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
        elif kind == "notice":
            self._add_notice(event[1])
            self._activity(str(event[1]), "dim")
        elif kind == "quit":
            self._on_worker_quit()

    def _mode_text(self):
        if getattr(self.worker, "no_wake", True):
            return "Continuous"
        return f"Wake word"

    def _set_state(self, state):
        self._state = state
        continuous = getattr(self.worker, "no_wake", True)
        texts = {
            "idle": "Ready — just speak" if continuous else "Ready — say 'Ninja'",
            "listening": "Listening…" if continuous else "Listening for wake word…",
            "working": "Working…",
            "speaking": "Speaking…",
        }
        if state == "idle" and not self.worker.voice:
            self.core_status.set_text("Type a command below")
        else:
            self.core_status.set_text(texts.get(state, texts["idle"]))
        dot_cls = {"listening": "hud-green", "working": "hud-amber",
                   "speaking": "hud-accent"}.get(state, "hud-dim")
        try:
            for c in ("hud-green", "hud-amber", "hud-accent", "hud-dim"):
                self.state_dot.get_style_context().remove_class(c)
            self.state_dot.get_style_context().add_class(dot_cls)
            if state == "listening":
                self.mic_state.set_text("Listening")
            elif state in ("working", "speaking"):
                self.mic_state.set_text(texts[state])
            elif not (self.worker.voice and self.worker.mic_enabled):
                self.mic_state.set_text("Muted")
        except Exception:
            pass

    # ---------- widgets: conversation / activity / console ----------

    def _add_message(self, role, text):
        ts = datetime.now().strftime("%H:%M")
        who = "NINJA" if role == "ninja" else "YOU"
        cls = "bubble-ninja" if role == "ninja" else "bubble-user"
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bubble = Gtk.EventBox()
        bubble.get_style_context().add_class(cls)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_border_width(8)
        head = Gtk.Label(label=f"{who} · {ts}")
        head.get_style_context().add_class("hud-dim")
        head.set_xalign(0)
        body = Gtk.Label(label=text)
        body.set_xalign(0)
        body.set_line_wrap(True)
        body.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_max_width_chars(44)
        body.set_selectable(True)
        inner.pack_start(head, False, False, 0)
        inner.pack_start(body, False, False, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        copy_btn = Gtk.Button.new_with_label("Copy")
        copy_btn.get_style_context().add_class("msg-action")
        copy_btn.set_tooltip_text("Copy message to clipboard")
        copy_btn.connect("clicked", lambda b, t=text: self._copy_text(t))
        actions.pack_start(copy_btn, False, False, 0)
        if role == "user":
            rerun = Gtk.Button.new_with_label("Re-run")
            rerun.get_style_context().add_class("msg-action")
            rerun.set_tooltip_text("Send this command again")
            rerun.connect("clicked", lambda b, t=text: self._send_text(t))
            actions.pack_start(rerun, False, False, 0)
        else:
            speak_btn = Gtk.Button.new_with_label("Speak")
            speak_btn.get_style_context().add_class("msg-action")
            speak_btn.set_tooltip_text("Speak this reply again")
            speak_btn.connect("clicked", lambda b, t=text: self._speak_text(t))
            actions.pack_start(speak_btn, False, False, 0)
        inner.pack_start(actions, False, False, 0)
        bubble.add(inner)
        bubble.set_halign(Gtk.Align.START if role == "ninja" else Gtk.Align.END)
        if role == "ninja":
            outer.pack_start(bubble, False, False, 0)
        else:
            outer.pack_end(bubble, False, False, 0)
        self.conv_box.pack_start(outer, False, False, 0)
        self.win.show_all()
        GLib.idle_add(self._scroll_bottom, self.conv_scroller)

    def _add_notice(self, text):
        lb = Gtk.Label(label=text)
        lb.get_style_context().add_class("hud-dim")
        lb.set_line_wrap(True)
        lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lb.set_max_width_chars(44)
        lb.set_xalign(0.5)
        self.conv_box.pack_start(lb, False, False, 0)
        self.win.show_all()
        GLib.idle_add(self._scroll_bottom, self.conv_scroller)

    def _activity(self, text, color="dim"):
        ts = datetime.now().strftime("%H:%M:%S")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        t = Gtk.Label(label=ts)
        t.get_style_context().add_class("hud-dim")
        m = Gtk.Label(label=text)
        m.set_xalign(0)
        m.set_line_wrap(True)
        m.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        m.set_max_width_chars(52)
        m.set_ellipsize(Pango.EllipsizeMode.END)
        m.get_style_context().add_class(
            {"accent": "hud-accent", "red": "hud-red",
             "amber": "hud-amber"}.get(color, "hud-dim"))
        row.pack_start(t, False, False, 0)
        row.pack_start(m, True, True, 0)
        self.act_box.pack_start(row, False, False, 0)
        kids = self.act_box.get_children()
        if len(kids) > 40:
            self.act_box.remove(kids[0])
        self.win.show_all()
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
        try:
            adj = scroller.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
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

    def _toggle_mic(self, want: bool | None = None):
        new_state = bool(want) if want is not None else not self.worker.mic_enabled
        self.worker.commands.put(("mic", new_state))
        try:
            if self.mic_switch.get_active() != new_state:
                self.mic_switch.set_active(new_state)
        except Exception:
            pass
        self._activity(f"Microphone {'on' if new_state else 'muted'}", "dim")

    def _toggle_tts(self, want: bool | None = None):
        if want is None:
            want = not self.worker.tts_enabled
        else:
            want = bool(want)
        self.worker.commands.put(("tts", want))
        try:
            if self.tts_switch.get_active() != want:
                self.tts_switch.set_active(want)
        except Exception:
            pass
        self._activity(f"Voice replies {'on' if want else 'off'}", "dim")

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

    # ----- jobs & timers -----
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
        if not rows:
            lb = Gtk.Label(label="No jobs or timers")
            lb.get_style_context().add_class("hud-dim")
            lb.set_xalign(0)
            self.jobs_box.pack_start(lb, False, False, 0)
        for kind, jid, label, status in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.get_style_context().add_class("job-row")
            row.set_border_width(5)
            dot = Gtk.Label(label="●")
            dot.get_style_context().add_class(
                "hud-accent" if status == "running"
                else ("hud-green" if status == "done" else "hud-dim"))
            row.pack_start(dot, False, False, 0)
            name = Gtk.Label(label=f"{kind} #{jid} · {label[:42]}")
            name.set_xalign(0)
            name.set_hexpand(True)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.get_style_context().add_class("hud-dim")
            row.pack_start(name, True, True, 0)
            if status == "running":
                cancel = Gtk.Button.new_with_label("Cancel")
                cancel.set_tooltip_text(f"Cancel {kind} #{jid}")
                cancel.connect("clicked", lambda b, k=kind, i=jid:
                               self._cancel_row(k, i))
                row.pack_start(cancel, False, False, 0)
            else:
                st = Gtk.Label(label=status)
                st.get_style_context().add_class("hud-dim")
                row.pack_start(st, False, False, 0)
            self.jobs_box.pack_start(row, False, False, 0)
        self.win.show_all()

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

    # ----- smart suggestion -----
    def _update_suggestion(self):
        hint = ""
        try:
            from .memory import get_memory
            hint = get_memory().suggestion()
        except Exception:
            hint = ""
        if hint:
            import re as _re
            m = _re.search(r"'([^']+)'", hint)
            cmd = m.group(1) if m else ""
            self.suggest_label.set_text(hint)
            self._suggest_cmd = cmd
            try:
                self.suggest_btn.set_sensitive(bool(cmd))
            except Exception:
                pass
        else:
            self.suggest_label.set_text("Try 'briefing' for your daily overview")
            self._suggest_cmd = "briefing"
            try:
                self.suggest_btn.set_sensitive(True)
            except Exception:
                pass

    def _run_suggestion(self):
        if self._suggest_cmd:
            self._send_text(self._suggest_cmd)
        else:
            self.entry.grab_focus()

    def _show_help(self):
        dlg = Gtk.MessageDialog(
            transient_for=self.win, modal=True,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE,
            text="NINJA — voice + desktop control")
        dlg.format_secondary_text(VOICE_HELP)
        dlg.run()
        dlg.destroy()

    # ---------- lifecycle ----------

    def _on_worker_quit(self):
        self._worker_done = True
        self._set_state("idle")
        self.core_status.set_text("NINJA is offline")
        self.online_pill.set_text("● OFFLINE")
        for w in (self.entry, getattr(self, "suggest_btn", None)):
            try:
                if w is not None:
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

    def run(self):
        self._activity("NINJA online — listening continuously", "accent")
        try:
            from .memory import get_memory
            name = get_memory().user_name
            hello = f"Welcome back, {name}. " if name else ""
        except Exception:
            hello = ""
        self._add_message(
            "ninja",
            f"{hello}I'm listening — just speak, or type below. "
            "Try 'briefing' for your daily overview, 'my city is …' to set "
            "weather, or use the quick actions.")
        self.win.show_all()
        try:
            self._refresh_jobs()
            self._update_suggestion()
        except Exception:
            pass
        self.entry.grab_focus()
        Gtk.main()
