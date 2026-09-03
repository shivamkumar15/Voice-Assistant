"""Chat-style GTK window for the assistant.

Replaces the old always-on-top status pill with a proper chat interface:
a live transcript with message bubbles, a text input, quick-command
buttons, mic / voice-reply toggles and a Listening / Working / Speaking
status light.

The assistant itself runs on a worker thread (assistant.worker) and talks
to this window through two queues, so the GUI never blocks on the
microphone, the brain or the speech engine.
"""

import queue
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .config import ASSISTANT_NAME, WAKE_WORDS  # noqa: E402
from .worker import AssistantWorker  # noqa: E402

# state name -> css class for the status dot
STATE_DOT = {
    "idle": "dot-idle",
    "listening": "dot-listening",
    "working": "dot-working",
    "speaking": "dot-speaking",
}

STATE_TEXT = {
    "idle": 'Idle — type a command or say "{wake}"',
    "listening": "Listening…",
    "working": "Working…",
    "speaking": "Speaking…",
}

CSS = b"""
.dot { font-weight: 700; }
.dot-idle { color: #5f6b7a; }
.dot-listening { color: #4fc3f7; }
.dot-working { color: #ffb300; }
.dot-speaking { color: #66bb6a; }
.bubble-assistant { background: rgba(79, 195, 247, 0.16); border-radius: 12px; }
.bubble-user { background: rgba(129, 199, 132, 0.22); border-radius: 12px; }
"""

# (button label, command sent to the brain)
QUICK_ACTIONS = [
    ("🕐 Time", "what's the time"),
    ("📅 Date", "what's the date"),
    ("🌤 Weather", "what's the weather"),
    ("😄 Joke", "tell me a joke"),
    ("💻 System", "system status"),
    ("❓ Help", "what can you do"),
]


class ChatWindow:
    """GTK front-end for an AssistantWorker."""

    def __init__(self, worker: AssistantWorker):
        self.worker = worker
        self._worker_done = False
        self._build_css()
        self._build_window()
        GLib.timeout_add(100, self._poll_events)

    # --- construction --------------------------------------------------------

    def _build_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("no display available — cannot open the chat window")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            display.get_default_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_window(self):
        Gtk.Window.set_default_icon_name("audio-input-microphone")
        self.win = Gtk.Window(title=f"{ASSISTANT_NAME} — Voice Assistant")
        self.win.set_default_size(820, 620)
        self.win.connect("delete-event", self._on_delete)
        self.win.connect("destroy", self._on_destroy)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)
        self.win.add(root)

        # -- status bar ----------------------------------------------------
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.pack_start(top, False, False, 0)

        self.dot = Gtk.Label(label="●")
        dot_ctx = self.dot.get_style_context()
        dot_ctx.add_class("dot")
        dot_ctx.add_class(STATE_DOT["idle"])
        top.pack_start(self.dot, False, False, 0)

        self.state_label = Gtk.Label()
        self.state_label.set_halign(Gtk.Align.START)
        self.state_label.set_hexpand(True)
        top.pack_start(self.state_label, True, True, 0)

        self.mic_check = Gtk.CheckButton(label="🎤 Mic")
        self.mic_check.set_active(self.worker.voice and self.worker.mic_enabled)
        self.mic_check.set_tooltip_text("Pause or resume listening to the microphone")
        self.mic_check.connect("toggled", self._on_mic_toggled)
        top.pack_start(self.mic_check, False, False, 0)

        self.tts_check = Gtk.CheckButton(label="🔊 Voice replies")
        self.tts_check.set_active(self.worker.tts_enabled)
        self.tts_check.set_tooltip_text("Speak replies out loud")
        self.tts_check.connect("toggled", self._on_tts_toggled)
        top.pack_start(self.tts_check, False, False, 0)

        # -- transcript ------------------------------------------------------
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_vexpand(True)
        self.scroller.set_shadow_type(Gtk.ShadowType.IN)
        self.transcript = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.transcript.set_border_width(4)
        self.scroller.add(self.transcript)
        root.pack_start(self.scroller, True, True, 0)

        # -- quick commands --------------------------------------------------
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, command in QUICK_ACTIONS:
            btn = Gtk.Button.new_with_label(label)
            btn.set_tooltip_text(f"Send: {command}")
            btn.connect("clicked", lambda b, c=command: self._run_quick(c))
            chips.pack_start(btn, False, False, 0)
        root.pack_start(chips, False, False, 0)

        # -- input row ----------------------------------------------------
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(f"Type a command for {ASSISTANT_NAME}…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda w: self._submit())
        row.pack_start(self.entry, True, True, 0)

        self.send_btn = Gtk.Button.new_with_label("Send")
        self.send_btn.connect("clicked", lambda b: self._submit())
        row.pack_start(self.send_btn, False, False, 0)
        root.pack_start(row, False, False, 0)

        self._set_state("idle")

    # --- event flow ------------------------------------------------------------

    def _poll_events(self):
        """Drain worker events on the GTK thread (timer callback)."""
        while True:
            try:
                event = self.worker.events.get_nowait()
            except queue.Empty:
                break
            self._apply_event(event)
        if not self._worker_done:
            # The mic may have failed after startup — keep the toggle in sync.
            mic_ok = self.worker.voice and self.worker.mic is not None
            if not mic_ok and self.mic_check.get_active():
                self.mic_check.set_active(False)
            self.mic_check.set_sensitive(mic_ok)
        return True  # keep the timer running

    def _apply_event(self, event):
        kind = event[0]
        if kind == "state":
            self._set_state(event[1])
        elif kind == "user":
            self._add_message("user", event[1])
        elif kind == "assistant":
            self._add_message("assistant", event[1])
        elif kind == "notice":
            self._add_notice(event[1])
        elif kind == "quit":
            self._on_worker_quit()

    def _on_worker_quit(self):
        self._worker_done = True
        self._set_state("idle")
        self.state_label.set_text(f"{ASSISTANT_NAME} is offline")
        for widget in (self.entry, self.send_btn, self.mic_check, self.tts_check):
            widget.set_sensitive(False)
        self._add_notice(f"{ASSISTANT_NAME} has shut down — close the window to exit.")

    # --- widgets ----------------------------------------------------------------

    def _set_state(self, state):
        ctx = self.dot.get_style_context()
        for css_class in STATE_DOT.values():
            ctx.remove_class(css_class)
        ctx.add_class(STATE_DOT.get(state, STATE_DOT["idle"]))
        if state == "idle" and not self.worker.voice:
            text = "Type a command below"
        else:
            text = STATE_TEXT.get(state, STATE_TEXT["idle"]).format(wake=WAKE_WORDS[0])
        self.state_label.set_text(text)

    def _add_message(self, role, text):
        """Append a chat bubble; role is 'user' or 'assistant'."""
        ts = datetime.now().strftime("%H:%M")
        name = ASSISTANT_NAME if role == "assistant" else "You"

        header = Gtk.Label()
        header.set_markup(
            "<small><span alpha='30000'>%s · %s</span></small>"
            % (GLib.markup_escape_text(name), ts)
        )
        header.set_xalign(0)
        header.set_margin_start(10)
        header.set_margin_end(10)
        header.set_margin_top(6)

        body = Gtk.Label()
        body.set_text(text)
        body.set_xalign(0)
        body.set_line_wrap(True)
        body.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_max_width_chars(52)
        body.set_selectable(True)
        body.set_margin_start(10)
        body.set_margin_end(10)
        body.set_margin_bottom(6)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.pack_start(header, False, False, 0)
        inner.pack_start(body, False, False, 0)

        bubble = Gtk.EventBox()
        bubble.get_style_context().add_class("bubble-" + role)
        bubble.add(inner)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if role == "user":
            bubble.set_halign(Gtk.Align.END)
            row.pack_end(bubble, False, False, 0)
        else:
            bubble.set_halign(Gtk.Align.START)
            row.pack_start(bubble, False, False, 0)

        self.transcript.pack_start(row, False, False, 0)
        self.win.show_all()
        GLib.idle_add(self._scroll_bottom)

    def _add_notice(self, text):
        """Append a dim, centred system line (no bubble)."""
        label = Gtk.Label()
        label.set_markup(
            "<small><span alpha='30000'>%s</span></small>"
            % GLib.markup_escape_text(text)
        )
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_xalign(0.5)
        label.set_max_width_chars(72)
        label.set_justify(Gtk.Justification.CENTER)
        self.transcript.pack_start(label, False, False, 0)
        self.win.show_all()
        GLib.idle_add(self._scroll_bottom)

    def _scroll_bottom(self):
        adjustment = self.scroller.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return False  # run once

    # --- user actions -------------------------------------------------------------

    def _submit(self):
        if not self.entry.get_sensitive():
            return
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.worker.commands.put(("text", text))

    def _run_quick(self, command):
        self.worker.commands.put(("text", command))

    def _on_mic_toggled(self, check):
        self.worker.commands.put(("mic", check.get_active()))

    def _on_tts_toggled(self, check):
        self.worker.commands.put(("tts", check.get_active()))

    # --- window lifecycle ------------------------------------------------------------

    def _on_delete(self, widget, event):
        self.worker.stop()
        return False  # carry on with the destroy

    def _on_destroy(self, widget):
        self.worker.stop()
        Gtk.main_quit()

    def run(self):
        self.win.show_all()
        self.entry.grab_focus()
        Gtk.main()