"""N.I.N.J.A HUD window — desktop assistant console.

Full-screen-style HUD inspired by the reference mockup:
top status bar, left telemetry rail, central core-reactor, right terminal +
conversation stack, bottom command nav. All desktop control (mouse move /
click / scroll / drag, typing, windows, apps, volume, brightness,
screenshots, power) is driven by voice via assistant.brain — this window is
the visual front-end and also accepts typed commands.

Talks to AssistantWorker through its command/event queues so the GUI never
blocks on the mic, brain or TTS.
"""

import math
import platform
import queue
import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .config import ASSISTANT_NAME, WAKE_WORDS  # noqa: E402
from .worker import AssistantWorker  # noqa: E402

DISPLAY_NAME = "N.I.N.J.A"
CITY_DEFAULT = "Quezon City"

CSS = b"""
window { background-color: #030710; }
label { color: #d8e4ef; font-family: Monospace; }
scrolledwindow { background-color: transparent; border: none; }
textview { background-color: #060d16; color: #9fd8e8; font-family: Monospace; }
textview text { background-color: #060d16; }
entry { background-color: #0a1622; color: #e8f1f9; border: 1px solid #1e3a4f;
        border-radius: 6px; padding: 6px; font-family: Monospace; }
button { background-color: #0a1622; color: #9fb3c8; border: 1px solid #1a2f42;
         border-radius: 8px; font-family: Monospace; }
button:hover { border-color: #22d3ee; color: #e8f1f9; }
.nav-active { border-color: #22d3ee; color: #22d3ee; }
.hud-panel { background-color: #060d16; border: 1px solid #14293b; border-radius: 10px; }
.hud-title { color: #7d93a8; font-size: 9px; letter-spacing: 2px; }
.hud-value { color: #e8f1f9; font-size: 13px; }
.hud-dim { color: #5b7286; font-size: 10px; }
.hud-cyan { color: #22d3ee; }
.hud-green { color: #34d399; }
.hud-red { color: #f87171; }
.hud-gold { color: #fbbf24; }
.hud-big { font-size: 26px; color: #ffffff; }
.online-pill { background-color: rgba(52,211,153,0.12); border: 1px solid #34d399;
               border-radius: 12px; color: #34d399; padding: 2px 10px; font-size: 10px; }
.warn-pill { background-color: rgba(248,113,113,0.10); border: 1px solid #f87171;
             border-radius: 12px; color: #f87171; padding: 3px 12px; font-size: 10px; }
.bubble-user { background: rgba(251,191,36,0.10); border: 1px solid #3a3220; border-radius: 10px; }
.bubble-ninja { background: rgba(34,211,238,0.08); border: 1px solid #14394a; border-radius: 10px; }
progressbar trough { background-color: #0a1622; border-radius: 4px; min-height: 6px; }
progressbar progress { background-color: #22d3ee; border-radius: 4px; }
"""

NAV_ITEMS = [
    ("SYSTEM", "system status"),
    ("WEATHER", "what's the weather"),
    ("CAMERA", "take a screenshot"),
    ("UPTIME", "uptime"),
    ("NEWS", "search for latest tech news"),
    ("NOTES", "open text editor"),
    ("FOCUS", "list windows"),
    ("TELEGRAM", "open telegram"),
    ("LOG", "__focus_log__"),
    ("CHAT", "__focus_chat__"),
]

VOICE_HELP = (
    "NINJA listens continuously — just speak, no wake word needed "
    "(say 'Ninja' before a phrase to make sure it answers).\n"
    "Chain tasks in one breath with 'and' / 'then': "
    "'open youtube and play believer'.\n"
    "• Mouse: move mouse left/right/up/down · move mouse to the center / top right · "
    "move mouse to 500, 300 · click · right click · double click · scroll up/down · drag left\n"
    "• Type: type hello world · press enter · copy · paste · save\n"
    "• Apps/web: open youtube · play believer · open vscode · open terminal · "
    "open whatsapp · open telegram · close chrome\n"
    "• Message: message mom hello · whatsapp dad call me back · send a message to john i am late\n"
    "• Page: find cats · scroll down · click · comment nice video on this post\n"
    "• Reminders: set a timer for 10 minutes · remind me to call mom in 20 minutes · "
    "list timers · cancel timers\n"
    "• Radios/clipboard: turn wifi off · switch bluetooth on · read my clipboard · empty the trash\n"
    "• Windows: focus chrome · minimise · maximise · list windows · show desktop · "
    "go to workspace 2 · move this window to workspace 3 · next workspace\n"
    "• System: volume up · set volume to 40 · brightness up · take a screenshot · "
    "system status · lock screen · sleep\n"
    "• Info: what time is it · weather in Delhi · tell me a joke"
)


def _stats():
    """Return dict with cpu/mem/disk/battery/uptime/net; never raises."""
    out = {"cpu": 0, "mem": 0, "disk": 0, "batt": 100, "charging": True,
           "uptime": "00:00:00", "net_up": 0, "net_down": 0}
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
        try:
            n = psutil.net_io_counters()
            out["net_up"] = n.bytes_sent
            out["net_down"] = n.bytes_recv
        except Exception:
            pass
    except Exception:
        pass
    return out


def _neofetch_text():
    s = _stats()
    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_s = f"{mem.used/1e9:.2f}GiB / {mem.total/1e9:.2f}GiB"
    except Exception:
        mem_s = "—"
    try:
        from .skills import hypr as _hypr
        size = _hypr.screen_size()
        res = f"{size[0]}x{size[1]}" if size else "1920x1080"
    except Exception:
        res = "1920x1080"
    lines = [
        "ninja@system:~$ neofetch",
        f"OS: N.I.N.J.A OS 2.0 {platform.machine()}",
        "Host: Ninja Desktop System",
        f"Kernel: {platform.release()}-ninja",
        f"Uptime: {s['uptime']}",
        "Packages: 1287 (core)",
        "Shell: zsh 5.9",
        f"Resolution: {res}",
        "Terminal: ninja-hud",
        f"CPU: {platform.processor() or 'Generic x86_64'}",
        "GPU: Desktop GPU",
        f"Memory: {mem_s}",
        "",
        "ninja@system:~$ ",
    ]
    return "\n".join(lines)


class ChatWindow:
    """NINJA HUD front-end for an AssistantWorker (same API as before)."""

    def __init__(self, worker: AssistantWorker):
        self.worker = worker
        self._worker_done = False
        self._angle = 0.0
        self._radar = 0.0
        self._wave_phase = 0.0
        self._state = "idle"
        self._cpu_hist = [10] * 60
        self._net_hist = [0.0] * 60
        self._last_net = None
        self._last_cmd_time = None
        self._latency_ms = 24
        self._weather = {"temp": "--", "city": CITY_DEFAULT.upper(),
                         "desc": "—", "hum": "—", "wind": "—", "feels": "—"}
        self._build_css()
        self._build_window()
        GLib.timeout_add(100, self._poll_events)
        GLib.timeout_add(1000, self._tick_clock)
        GLib.timeout_add(2000, self._tick_stats)
        GLib.timeout_add(50, self._tick_anim)
        threading.Thread(target=self._fetch_weather, daemon=True).start()
        self._term_append(_neofetch_text())

    # ---------- css / window skeleton ----------

    def _build_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no display available — cannot open the HUD window")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            display.get_default_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _panel(self, title, extra=""):
        frame = Gtk.EventBox()
        frame.get_style_context().add_class("hud-panel")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(10)
        frame.add(box)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        t = Gtk.Label(label=f"⬢  {title}  {extra}")
        t.get_style_context().add_class("hud-title")
        t.set_xalign(0)
        t.set_hexpand(True)
        head.pack_start(t, True, True, 0)
        box.pack_start(head, False, False, 0)
        return frame, box

    def _small(self, text, cls="hud-dim"):
        lb = Gtk.Label(label=text)
        lb.get_style_context().add_class(cls)
        lb.set_xalign(0)
        return lb

    def _build_window(self):
        Gtk.Window.set_default_icon_name("audio-input-microphone")
        self.win = Gtk.Window(title=f"{DISPLAY_NAME} — Desktop Assistant")
        self.win.set_default_size(1380, 830)
        self.win.connect("delete-event", self._on_delete)
        self.win.connect("destroy", self._on_destroy)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        # ===== top bar =====
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top.set_border_width(8)
        root.pack_start(top, False, False, 0)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bname = Gtk.Label(label="N.I.N.J.A")
        bname.get_style_context().add_class("hud-value")
        brand.pack_start(bname, False, False, 0)
        self.online_pill = Gtk.Label(label="● ONLINE")
        self.online_pill.get_style_context().add_class("online-pill")
        brand.pack_start(self.online_pill, False, False, 0)
        top.pack_start(brand, True, True, 0)

        center = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.clock_label = Gtk.Label(label="--:--:--")
        self.clock_label.get_style_context().add_class("hud-value")
        center.pack_start(self.clock_label, False, False, 0)
        self.date_label = Gtk.Label(label="")
        self.date_label.get_style_context().add_class("hud-dim")
        center.pack_start(self.date_label, False, False, 0)
        top.pack_start(center, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.top_weather = Gtk.Label(label=f"☁ --°C  {CITY_DEFAULT.upper()}")
        self.top_weather.get_style_context().add_class("hud-dim")
        right.pack_start(self.top_weather, False, False, 0)
        help_btn = Gtk.Button.new_with_label("⚙")
        help_btn.set_tooltip_text("Voice command help")
        help_btn.connect("clicked", lambda b: self._show_help())
        right.pack_start(help_btn, False, False, 0)
        top.pack_start(right, True, True, 0)

        # ===== main 3 columns =====
        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main.set_border_width(8)
        root.pack_start(main, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.set_size_request(215, -1)
        main.pack_start(left, False, False, 0)

        center_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center_col.set_hexpand(True)
        main.pack_start(center_col, True, True, 0)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_col.set_size_request(400, -1)
        main.pack_start(right_col, False, False, 0)

        self._build_left(left)
        self._build_center(center_col)
        self._build_right(right_col)

        # ===== bottom nav =====
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav.set_border_width(8)
        nav.set_halign(Gtk.Align.CENTER)
        root.pack_start(nav, False, False, 0)
        self.nav_buttons = {}
        for name, cmd in NAV_ITEMS:
            btn = Gtk.Button.new_with_label(f"{name}")
            btn.set_tooltip_text(f"Send: {cmd}" if not cmd.startswith("__") else name)
            btn.connect("clicked", lambda b, c=cmd: self._run_nav(c))
            if name in ("WEATHER", "CHAT"):
                btn.get_style_context().add_class("nav-active")
            nav.pack_start(btn, True, True, 0)
            self.nav_buttons[name] = btn

        ver = Gtk.Label(label="V2.0 - PERSONAL AI  •  say 'Ninja' + command  •  mouse: move/click/scroll/drag")
        ver.get_style_context().add_class("hud-dim")
        root.pack_start(ver, False, False, 2)


    def _build_left(self, left):
        link_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        link_box.set_border_width(4)
        left.pack_start(link_box, False, False, 0)
        link_box.pack_start(self._small("LINK"), False, False, 0)
        self.link_label = Gtk.Label(label="● Online")
        self.link_label.get_style_context().add_class("hud-green")
        self.link_label.set_xalign(0)
        link_box.pack_start(self.link_label, False, False, 0)
        link_box.pack_start(self._small("LATENCY"), False, False, 0)
        self.latency_label = Gtk.Label(label="24 ms")
        self.latency_label.set_xalign(0)
        link_box.pack_start(self.latency_label, False, False, 0)
        link_box.pack_start(self._small("THREAT"), False, False, 0)
        self.threat_label = Gtk.Label(label="NOMINAL")
        self.threat_label.get_style_context().add_class("hud-green")
        self.threat_label.set_xalign(0)
        link_box.pack_start(self.threat_label, False, False, 0)
        self.threat_bar = Gtk.Label(label="━━━━━━━━")
        self.threat_bar.get_style_context().add_class("hud-green")
        self.threat_bar.set_xalign(0)
        link_box.pack_start(self.threat_bar, False, False, 0)

        radar_panel, radar_box = self._panel("ACOUSTIC SCAN", "SCANNING")
        left.pack_start(radar_panel, False, False, 0)
        self.radar_draw = Gtk.DrawingArea()
        self.radar_draw.set_size_request(180, 150)
        self.radar_draw.connect("draw", self._draw_radar)
        radar_box.pack_start(self.radar_draw, False, False, 0)
        stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.contacts_label = Gtk.Label(label="CONTACTS\n19")
        self.peak_label = Gtk.Label(label="PEAK\n1500 Hz")
        for w in (self.contacts_label, self.peak_label):
            w.get_style_context().add_class("hud-dim")
            stats.pack_start(w, True, True, 0)
        radar_box.pack_start(stats, False, False, 0)

        mon_panel, mon_box = self._panel("SYSTEM MONITOR")
        left.pack_start(mon_panel, True, True, 0)
        self.cpu_label = self._small("CPU 0%", "hud-value")
        mon_box.pack_start(self.cpu_label, False, False, 0)
        self.cpu_wave = Gtk.DrawingArea()
        self.cpu_wave.set_size_request(180, 30)
        self.cpu_wave.connect("draw", self._draw_cpu_wave)
        mon_box.pack_start(self.cpu_wave, False, False, 0)
        self.disk_label = self._small("DISK — / —%", "hud-value")
        mon_box.pack_start(self.disk_label, False, False, 0)
        self.disk_bar = Gtk.ProgressBar()
        mon_box.pack_start(self.disk_bar, False, False, 0)
        self.mem_label = self._small("MEMORY 0%", "hud-value")
        mon_box.pack_start(self.mem_label, False, False, 0)
        self.mem_bar = Gtk.ProgressBar()
        mon_box.pack_start(self.mem_bar, False, False, 0)
        mon_box.pack_start(self._small("voice: move mouse · click · scroll · type"), False, False, 4)

    # ---------- center ----------

    def _build_center(self, col):
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        col.pack_start(top_row, False, False, 0)

        w_panel, w_box = self._panel("WEATHER")
        w_panel.set_hexpand(True)
        top_row.pack_start(w_panel, True, True, 0)
        self.w_temp = Gtk.Label(label="--°C")
        self.w_temp.get_style_context().add_class("hud-big")
        self.w_temp.set_xalign(0)
        w_box.pack_start(self.w_temp, False, False, 0)
        self.w_city = Gtk.Label(label=CITY_DEFAULT.upper() + ", PH")
        self.w_city.get_style_context().add_class("hud-cyan")
        self.w_city.set_xalign(0)
        w_box.pack_start(self.w_city, False, False, 0)
        self.w_desc = self._small("—")
        w_box.pack_start(self.w_desc, False, False, 0)
        w_sub = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.w_hum = Gtk.Label(label="HUM —")
        self.w_wind = Gtk.Label(label="WIND —")
        self.w_feels = Gtk.Label(label="FEELS —")
        for w in (self.w_hum, self.w_wind, self.w_feels):
            w.get_style_context().add_class("hud-dim")
            w_sub.pack_start(w, True, True, 0)
        w_box.pack_start(w_sub, False, False, 0)

        mid_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        mid_info.set_hexpand(True)
        top_row.pack_start(mid_info, True, True, 0)
        self.mem_badge = Gtk.Label(label="⚠ MEMORY PRESSURE")
        self.mem_badge.get_style_context().add_class("warn-pill")
        self.mem_badge.set_halign(Gtk.Align.CENTER)
        mid_info.pack_start(self.mem_badge, False, False, 0)
        self.logline_label = Gtk.Label(label="LOG --:--:-- ready")
        self.logline_label.get_style_context().add_class("hud-dim")
        self.logline_label.set_line_wrap(True)
        mid_info.pack_start(self.logline_label, False, False, 0)

        # core reactor
        core_panel, core_box = self._panel("")
        col.pack_start(core_panel, True, True, 0)
        self.core_pct = Gtk.Label(label="CORE INTEGRITY\n--%")
        self.core_pct.set_justify(Gtk.Justification.CENTER)
        self.core_pct.get_style_context().add_class("hud-dim")
        core_box.pack_start(self.core_pct, False, False, 0)
        overlay = Gtk.Overlay()
        overlay.set_vexpand(True)
        core_box.pack_start(overlay, True, True, 0)
        self.core_draw = Gtk.DrawingArea()
        self.core_draw.set_size_request(380, 320)
        self.core_draw.set_hexpand(True)
        self.core_draw.set_vexpand(True)
        self.core_draw.connect("draw", self._draw_core)
        overlay.add(self.core_draw)
        center_labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        center_labels.set_halign(Gtk.Align.CENTER)
        center_labels.set_valign(Gtk.Align.CENTER)
        self.core_name = Gtk.Label(label=DISPLAY_NAME.replace(".", ""))
        self.core_name.get_style_context().add_class("hud-cyan")
        center_labels.pack_start(self.core_name, False, False, 0)
        self.core_status = Gtk.Label(label="Listening… just speak")
        self.core_status.get_style_context().add_class("hud-dim")
        center_labels.pack_start(self.core_status, False, False, 0)
        self.core_wave = Gtk.DrawingArea()
        self.core_wave.set_size_request(180, 18)
        self.core_wave.connect("draw", self._draw_core_wave)
        center_labels.pack_start(self.core_wave, False, False, 0)
        overlay.add_overlay(center_labels)

        side = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.cpu_side = Gtk.Label(label="CPU 0%")
        self.cpu_side.get_style_context().add_class("hud-cyan")
        self.ram_side = Gtk.Label(label="RAM 0%")
        self.ram_side.get_style_context().add_class("hud-cyan")
        side.pack_start(self.cpu_side, True, True, 0)
        side.pack_start(self.ram_side, True, True, 0)
        core_box.pack_start(side, False, False, 0)

        # hardware buttons
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btns.set_halign(Gtk.Align.CENTER)
        col.pack_start(btns, False, False, 0)
        self.cam_btn = Gtk.Button.new_with_label("📷")
        self.cam_btn.set_tooltip_text("Take a screenshot (voice: take a screenshot)")
        self.cam_btn.connect("clicked", lambda b: self._send_text("take a screenshot"))
        btns.pack_start(self.cam_btn, False, False, 0)
        self.mic_btn = Gtk.Button.new_with_label("🎤")
        self.mic_btn.set_tooltip_text("Toggle microphone listening")
        self.mic_btn.connect("clicked", lambda b: self._toggle_mic())
        btns.pack_start(self.mic_btn, False, False, 0)
        self.kbd_btn = Gtk.Button.new_with_label("⌨")
        self.kbd_btn.set_tooltip_text("Focus text input (type commands)")
        self.kbd_btn.connect("clicked", lambda b: self.entry.grab_focus())
        btns.pack_start(self.kbd_btn, False, False, 0)

        # activity
        act_panel, act_box = self._panel("ACTIVITY")
        col.pack_start(act_panel, False, False, 0)
        self.act_scroller = Gtk.ScrolledWindow()
        self.act_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.act_scroller.set_min_content_height(130)
        try:
            self.act_scroller.set_max_content_height(170)
        except AttributeError:
            self.act_scroller.set_size_request(-1, 160)
        self.act_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.act_scroller.add(self.act_box)
        act_box.pack_start(self.act_scroller, True, True, 0)

    # ---------- right stack ----------

    def _build_right(self, col):
        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        status.set_border_width(2)
        col.pack_start(status, False, False, 0)
        self.mic_state = Gtk.Label(label="MIC   ● Listening")
        self.mic_state.get_style_context().add_class("hud-green")
        self.mic_state.set_xalign(1)
        status.pack_start(self.mic_state, False, False, 0)
        self.mode_label = Gtk.Label(label=self._mode_text())
        self.mode_label.get_style_context().add_class("hud-dim")
        self.mode_label.set_xalign(1)
        status.pack_start(self.mode_label, False, False, 0)
        self.batt_label = Gtk.Label(label="BATTERY ● CHG   100%")
        self.batt_label.get_style_context().add_class("hud-dim")
        self.batt_label.set_xalign(1)
        status.pack_start(self.batt_label, False, False, 0)

        term_panel, term_box = self._panel("TERMINAL")
        col.pack_start(term_panel, False, False, 0)
        self.term_scroller = Gtk.ScrolledWindow()
        self.term_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.term_scroller.set_min_content_height(190)
        self.term_view = Gtk.TextView()
        self.term_view.set_editable(False)
        self.term_view.set_cursor_visible(False)
        self.term_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.term_view.override_font(Pango.FontDescription("Monospace 8"))
        self.term_scroller.add(self.term_view)
        term_box.pack_start(self.term_scroller, True, True, 0)

        conv_panel, conv_box = self._panel("CONVERSATION")
        col.pack_start(conv_panel, True, True, 0)
        self.conv_scroller = Gtk.ScrolledWindow()
        self.conv_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.conv_scroller.set_min_content_height(150)
        self.conv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.conv_scroller.add(self.conv_box)
        conv_box.pack_start(self.conv_scroller, True, True, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ask anything… or just speak")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda w: self._submit())
        row.pack_start(self.entry, True, True, 0)
        send = Gtk.Button.new_with_label("➤")
        send.connect("clicked", lambda b: self._submit())
        row.pack_start(send, False, False, 0)
        conv_box.pack_start(row, False, False, 0)

        geo = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        col.pack_start(geo, False, False, 0)
        uplink = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        uplink.pack_start(self._small("SATELLITE UPLINK"), False, False, 0)
        lk = Gtk.Label(label="LOCKED - NIGHT")
        lk.get_style_context().add_class("hud-cyan")
        lk.set_xalign(0)
        uplink.pack_start(lk, False, False, 0)
        self.globe_draw = Gtk.DrawingArea()
        self.globe_draw.set_size_request(120, 90)
        self.globe_draw.connect("draw", self._draw_globe)
        uplink.pack_start(self.globe_draw, False, False, 0)
        geo.pack_start(uplink, False, False, 0)
        side2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        side2.set_hexpand(True)
        geo.pack_start(side2, True, True, 0)
        self.latlon_label = Gtk.Label(label="LAT 14.63° N      LON 121.03° E")
        self.latlon_label.get_style_context().add_class("hud-dim")
        side2.pack_start(self.latlon_label, False, False, 0)
        side2.pack_start(self._small("NET 606"), False, False, 0)
        self.net_draw = Gtk.DrawingArea()
        self.net_draw.set_size_request(180, 34)
        self.net_draw.connect("draw", self._draw_net)
        side2.pack_start(self.net_draw, False, False, 0)
        self.uptime_label = Gtk.Label(label="UPTIME   00:00:00")
        self.uptime_label.get_style_context().add_class("hud-dim")
        self.uptime_label.set_xalign(1)
        side2.pack_start(self.uptime_label, False, False, 0)

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
        R = min(w, h) / 2 - 14
        s = _stats()
        cpu_f = max(0.02, min(1.0, s["cpu"] / 100.0))
        mem_f = max(0.02, min(1.0, s["mem"] / 100.0))
        # bg
        cr.set_source_rgb(0.012, 0.03, 0.06)
        cr.paint()
        # grid
        cr.set_source_rgba(0.13, 0.35, 0.5, 0.15)
        cr.set_line_width(1)
        for gx in range(0, w, 28):
            cr.move_to(gx, 0)
            cr.line_to(gx, h)
            cr.stroke()
        for gy in range(0, h, 28):
            cr.move_to(0, gy)
            cr.line_to(w, gy)
            cr.stroke()
        # outer tick ring (rotating)
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(self._angle * 0.25)
        for i in range(72):
            a = 2 * math.pi * i / 72
            long_tick = (i % 6 == 0)
            r1 = R
            r0 = R - (12 if long_tick else 6)
            cr.set_source_rgba(0.13, 0.83, 0.93, 0.9 if long_tick else 0.35)
            cr.set_line_width(2 if long_tick else 1)
            cr.move_to(r0 * math.cos(a), r0 * math.sin(a))
            cr.line_to(r1 * math.cos(a), r1 * math.sin(a))
            cr.stroke()
        cr.restore()
        # static thin rings
        for frac, alpha in ((0.88, 0.5), (0.72, 0.35), (0.55, 0.6)):
            cr.set_source_rgba(0.13, 0.5, 0.7, alpha)
            cr.set_line_width(1.2)
            cr.arc(cx, cy, R * frac, 0, 2 * math.pi)
            cr.stroke()
        # CPU arc (cyan, left)
        cr.set_source_rgb(0.13, 0.83, 0.93)
        cr.set_line_width(5)
        cr.arc(cx, cy, R * 0.80, math.pi * 0.55, math.pi * 0.55 + math.pi * 1.15 * cpu_f + 0.05)
        cr.stroke()
        # RAM arc (blue, right)
        cr.set_source_rgb(0.25, 0.45, 1.0)
        cr.set_line_width(5)
        cr.arc(cx, cy, R * 0.80, -math.pi * 0.42, -math.pi * 0.42 + math.pi * 1.1 * mem_f + 0.05)
        cr.stroke()
        # glow pulse follows the live intake level + a gentle idle breath
        mic_level, _ = self._get_mic_visual()
        pulse = 1.0 + mic_level * 0.06 + 0.008 * math.sin(self._wave_phase * 2)
        if self._state == "speaking":
            pulse += 0.01 * math.sin(self._wave_phase * 3)
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.85)
        cr.set_line_width(2 + mic_level * 2.5)
        cr.arc(cx, cy, R * 0.55 * pulse, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.12 + mic_level * 0.25)
        cr.set_line_width(10 + mic_level * 10)
        cr.arc(cx, cy, R * 0.55 * pulse, 0, 2 * math.pi)
        cr.stroke()
        return False

    def _draw_core_wave(self, area, cr):
        """Audio-intake visualiser: pill bars driven by the live mic meter."""
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(0.02, 0.06, 0.1)
        cr.paint()
        level, hist = self._get_mic_visual()
        live = level > 0.02
        n_bars = 22
        gap = 4.0
        bar_w = min(9.0, (w - gap * (n_bars + 1)) / n_bars)
        total = n_bars * bar_w + (n_bars - 1) * gap
        x0 = (w - total) / 2 + bar_w / 2
        mid = h / 2
        try:
            cr.set_line_cap(1)  # cairo LINE_CAP_ROUND -> pill-shaped bars
        except Exception:
            pass
        for i in range(n_bars):
            # Time flows left (old) -> right (new); newest sample at the right.
            if hist:
                idx = int(i * (len(hist) - 1) / max(1, n_bars - 1))
                v = hist[idx]
            else:
                v = 0.0
            if live:
                # Centre bars dance hardest with the instantaneous level.
                centre = 1.0 - abs(i - (n_bars - 1) / 2) / ((n_bars - 1) / 2)
                v = max(v, level * (0.35 + 0.65 * centre))
            else:
                # Idle: gentle breathing shimmer so it never looks dead.
                v = 0.06 + 0.05 * abs(math.sin(i * 0.55 + self._wave_phase * 1.6))
            bar_h = max(3.0, v * (h - 6))
            alpha = 0.55 + 0.45 * min(1.0, v * 1.6)
            cr.set_source_rgba(0.13, 0.83, 0.93, alpha)
            cr.set_line_width(bar_w)
            cr.move_to(x0 + i * (bar_w + gap), mid - bar_h / 2)
            cr.line_to(x0 + i * (bar_w + gap), mid + bar_h / 2)
            cr.stroke()
        return False

    def _draw_radar(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 6
        cr.set_source_rgb(0.02, 0.06, 0.1)
        cr.paint()
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.5)
        cr.set_line_width(1)
        for f in (1.0, 0.66, 0.33):
            cr.arc(cx, cy, R * f, 0, 2 * math.pi)
            cr.stroke()
        cr.move_to(cx - R, cy)
        cr.line_to(cx + R, cy)
        cr.move_to(cx, cy - R)
        cr.line_to(cx, cy + R)
        cr.stroke()
        # sweep
        a = self._radar
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.9)
        cr.set_line_width(2)
        cr.move_to(cx, cy)
        cr.line_to(cx + R * math.cos(a), cy + R * math.sin(a))
        cr.stroke()
        # blips
        for i, (ba, bf) in enumerate(((0.7, 0.6), (2.4, 0.4), (4.2, 0.75))):
            bx = cx + R * bf * math.cos(ba)
            by = cy + R * bf * math.sin(ba)
            cr.set_source_rgba(0.13, 0.83, 0.93, 0.9)
            cr.arc(bx, by, 3, 0, 2 * math.pi)
            cr.fill()
        return False

    def _draw_cpu_wave(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(0.02, 0.06, 0.1)
        cr.paint()
        cr.set_source_rgb(0.13, 0.83, 0.93)
        cr.set_line_width(1.2)
        n = len(self._cpu_hist)
        for i, v in enumerate(self._cpu_hist):
            x = w * i / max(1, n - 1)
            y = h - (v / 100.0) * (h - 4) - 2
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        return False

    def _draw_net(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(0.02, 0.06, 0.1)
        cr.paint()
        cr.set_source_rgb(0.13, 0.83, 0.93)
        cr.set_line_width(1.2)
        mx = max(self._net_hist) if max(self._net_hist) > 0 else 1.0
        for i, v in enumerate(self._net_hist):
            x = w * i / max(1, len(self._net_hist) - 1)
            y = h - (v / mx) * (h - 4) - 2
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        return False

    def _draw_globe(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 4
        cr.set_source_rgb(0.02, 0.06, 0.1)
        cr.paint()
        cr.set_source_rgb(0.13, 0.83, 0.93)
        cr.set_line_width(1.2)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(0.13, 0.83, 0.93, 0.6)
        for k in (-0.5, 0.0, 0.5):
            cr.save()
            cr.translate(cx, cy)
            cr.scale(1.0, 1.0)
            cr.arc(0, 0, R * abs(math.cos(k)) if k else R, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
            cr.move_to(cx - R * math.cos(k * 0.8), cy - R)
            cr.line_to(cx - R * math.cos(k * 0.8), cy + R)
            cr.stroke()
        # trajectory
        cr.set_source_rgb(1.0, 0.55, 0.2)
        cr.set_line_width(1.6)
        cr.arc(cx, cy, R * 0.92, 0.4, 2.2)
        cr.stroke()
        return False

    # ---------- live ticks ----------

    def _tick_clock(self):
        now = datetime.now()
        self.clock_label.set_text(now.strftime("%I:%M:%S %p").lstrip("0"))
        self.date_label.set_text(now.strftime("%B %d, %Y").upper())
        return True

    def _tick_stats(self):
        s = _stats()
        self._cpu_hist.append(s["cpu"])
        self._cpu_hist = self._cpu_hist[-60:]
        if self._last_net is None:
            self._last_net = (s["net_up"], s["net_down"])
            rate = 0.0
        else:
            du = s["net_up"] - self._last_net[0]
            dd = s["net_down"] - self._last_net[1]
            self._last_net = (s["net_up"], s["net_down"])
            rate = max(0.0, (du + dd) / 1024.0 / 2.0)
        self._net_hist.append(rate)
        self._net_hist = self._net_hist[-60:]

        integrity = 100 - int((s["cpu"] + s["mem"]) / 4)
        self.core_pct.set_text(f"CORE INTEGRITY\n{integrity}%")
        self.cpu_side.set_text(f"CPU\n{s['cpu']}%")
        self.ram_side.set_text(f"RAM\n{s['mem']}%")
        self.cpu_label.set_text(f"CPU {s['cpu']}%")
        self.disk_label.set_text(f"DISK {s['disk']}% used")
        try:
            self.disk_bar.set_fraction(s["disk"] / 100.0)
            self.mem_bar.set_fraction(s["mem"] / 100.0)
        except Exception:
            pass
        self.mem_label.set_text(f"MEMORY {s['mem']}%")
        self.latency_label.set_text(f"{self._latency_ms} ms")
        # threat
        peak = max(s["cpu"], s["mem"])
        if peak >= 85:
            level, cls = "CRITICAL", "hud-red"
        elif peak >= 65:
            level, cls = "HIGH", "hud-gold"
        else:
            level, cls = "NOMINAL", "hud-green"
        self.threat_label.set_text(level)
        for c in ("hud-red", "hud-gold", "hud-green"):
            self.threat_label.get_style_context().remove_class(c)
        self.threat_label.get_style_context().add_class(cls)
        self.threat_bar.get_style_context().remove_class("hud-red")
        self.threat_bar.get_style_context().remove_class("hud-gold")
        self.threat_bar.get_style_context().remove_class("hud-green")
        self.threat_bar.get_style_context().add_class(cls)
        # memory badge + log line
        self.mem_badge.set_visible(s["mem"] >= 70)
        if peak >= 85:
            msg = "Threat critical - CPU saturated" if s["cpu"] >= s["mem"] else "Threat critical - Memory"
            self.logline_label.set_text(f"LOG {datetime.now():%H:%M:%S}  {msg}")
            self._activity(f"Threat critical - {'CPU saturated' if s['cpu'] >= s['mem'] else 'Memory'}", "red")
        elif peak >= 65:
            self.logline_label.set_text(f"LOG {datetime.now():%H:%M:%S}  Threat high - load elevated")
        # battery / uptime / mic
        chg = "CHG" if s["charging"] else "BAT"
        self.batt_label.set_text(f"BATTERY ● {chg}   {s['batt']}%")
        self.uptime_label.set_text(f"UPTIME   {s['uptime']}")
        listening = self._state == "listening" or (
            self.worker.voice and self.worker.mic_enabled and self.worker.mic is not None)
        if not self._worker_done:
            self.mic_state.set_text("MIC   ● Listening" if listening else "MIC   ○ Muted")
        # redraw small graphs
        try:
            self.cpu_wave.queue_draw()
            self.net_draw.queue_draw()
        except Exception:
            pass
        return True

    def _tick_anim(self):
        self._angle += 0.06
        self._radar += 0.09
        self._wave_phase += 0.12
        for w in (self.core_draw, self.core_wave, self.radar_draw, self.globe_draw):
            try:
                w.queue_draw()
            except Exception:
                pass
        # PEAK follows the live intake level (falls back to idle jitter).
        try:
            import random
            mic_level, _ = self._get_mic_visual()
            if mic_level > 0.02:
                hz = int(1400 + mic_level * 900 + random.randint(-40, 40))
            else:
                hz = 1400 + random.randint(0, 300)
            self.peak_label.set_text(f"PEAK\n{hz} Hz")
        except Exception:
            pass
        return True

    def _fetch_weather(self):
        try:
            import requests
            r = requests.get(f"https://wttr.in/{CITY_DEFAULT}?format=j1", timeout=10)
            if not r.ok:
                return
            data = r.json()
            cur = (data.get("current_condition") or [{}])[0]
            temp = cur.get("temp_C", "--")
            desc = (cur.get("weatherDesc") or [{}])[0].get("value", "—")
            hum = cur.get("humidity", "—")
            wind = cur.get("windspeedKmph", "—")
            feels = cur.get("FeelsLikeC", "—")
            GLib.idle_add(self._apply_weather, str(temp), str(desc), str(hum), str(wind), str(feels))
        except Exception:
            return

    def _apply_weather(self, temp, desc, hum, wind, feels):
        self._weather.update({"temp": temp, "desc": desc, "hum": hum, "wind": wind, "feels": feels})
        self.w_temp.set_text(f"{temp}°C")
        self.w_city.set_text(f"{CITY_DEFAULT.upper()}, PH")
        self.w_desc.set_text(desc.lower())
        self.w_hum.set_text(f"HUMIDITY\n{hum}%")
        self.w_wind.set_text(f"WIND\n{wind} m/s" if wind == "—" else f"WIND\n{float(wind)/3.6:.1f} m/s")
        self.w_feels.set_text(f"FEELS\n{feels}°C")
        self.top_weather.set_text(f"☁ {temp}°C  {CITY_DEFAULT.upper()}")
        return False

    # ---------- worker events ----------

    def _poll_events(self):
        while True:
            try:
                event = self.worker.events.get_nowait()
            except queue.Empty:
                break
            self._apply_event(event)
        if not self._worker_done:
            mic_ok = self.worker.voice and self.worker.mic is not None
            try:
                self.mic_btn.set_sensitive(mic_ok)
            except Exception:
                pass
        return True

    def _apply_event(self, event):
        kind = event[0]
        if kind == "state":
            self._set_state(event[1])
        elif kind == "user":
            self._add_message("user", event[1])
            self._activity(f"Command: {event[1]}", "cyan")
            self._term_append(f"ninja@system:~$ {event[1]}")
            import time as _t
            self._last_cmd_time = _t.monotonic()
        elif kind == "assistant":
            self._add_message("ninja", event[1])
            if self._last_cmd_time is not None:
                import time as _t
                self._latency_ms = int((_t.monotonic() - self._last_cmd_time) * 1000)
                self._last_cmd_time = None
            self._term_append(str(event[1]))
        elif kind == "notice":
            self._add_notice(event[1])
            self._activity(str(event[1]), "dim")
        elif kind == "quit":
            self._on_worker_quit()

    def _mode_text(self):
        if getattr(self.worker, "no_wake", True):
            return "MODE   ● Continuous"
        return f"MODE   ● Wake word ('{WAKE_WORDS[0]}')"

    def _set_state(self, state):
        self._state = state
        continuous = getattr(self.worker, "no_wake", True)
        texts = {
            "idle": "Ready — just speak" if continuous else "Ready — type or say 'Ninja'",
            "listening": "Listening… just speak" if continuous else "Listening for wake word…",
            "working": "Working…",
            "speaking": "Speaking…",
        }
        if state == "idle" and not self.worker.voice:
            self.core_status.set_text("Type a command below")
        else:
            self.core_status.set_text(texts.get(state, texts["idle"]))
        if state == "listening":
            self.mic_state.set_text("MIC   ● Listening")
        elif state == "idle" and not (self.worker.voice and self.worker.mic_enabled):
            self.mic_state.set_text("MIC   ○ Muted")

    # ---------- widgets: conversation / activity / terminal ----------

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
        if color == "red":
            m.get_style_context().add_class("hud-red")
        elif color == "cyan":
            m.get_style_context().add_class("hud-cyan")
        elif color == "gold":
            m.get_style_context().add_class("hud-gold")
        else:
            m.get_style_context().add_class("hud-dim")
        row.pack_start(t, False, False, 0)
        row.pack_start(m, True, True, 0)
        self.act_box.pack_start(row, False, False, 0)
        # keep last ~40 lines
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
        self.worker.commands.put(("text", text.strip()))

    def _submit(self):
        if not self.entry.get_sensitive():
            return
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self._send_text(text)

    def _run_nav(self, cmd):
        if cmd == "__focus_chat__":
            self.entry.grab_focus()
            return
        if cmd == "__focus_log__":
            try:
                self.act_scroller.grab_focus()
            except Exception:
                pass
            return
        self._send_text(cmd)

    def _toggle_mic(self):
        new_state = not (self.worker.mic_enabled)
        self.worker.commands.put(("mic", new_state))
        self.mic_state.set_text("MIC   ● Listening" if new_state else "MIC   ○ Muted")

    def _show_help(self):
        dlg = Gtk.MessageDialog(
            transient_for=self.win, modal=True,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE,
            text="N.I.N.J.A — voice + desktop control")
        dlg.format_secondary_text(VOICE_HELP)
        dlg.run()
        dlg.destroy()

    # ---------- lifecycle ----------

    def _on_worker_quit(self):
        self._worker_done = True
        self._set_state("idle")
        self.core_status.set_text("NINJA is offline")
        self.online_pill.set_text("● OFFLINE")
        for w in (self.entry, self.cam_btn, self.mic_btn, self.kbd_btn):
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

    def run(self):
        self._activity("NINJA HUD online — listening continuously, just speak", "cyan")
        self._activity("Chain tasks: 'open youtube and play believer'", "dim")
        self._activity("Voice mouse ready: move / click / scroll / drag", "dim")
        self._add_message("ninja", "NINJA online and listening to everything you say — "
                                   "no wake word needed. Chain tasks with 'and', e.g. "
                                   "'open youtube and play believer', or 'open whatsapp "
                                   "and text mom hello'. I can move and click the mouse, "
                                   "type, manage windows, apps, volume, screenshots and more.")
        self.win.show_all()
        self.mem_badge.set_visible(False)
        self.entry.grab_focus()
        Gtk.main()
