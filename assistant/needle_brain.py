"""Needle brain: natural-language command understanding, fully on-device.

The regex brain in brain.py matches exact command patterns instantly, but
free-form phrasing ("could you put on some lofi", "make the screen a bit
dimmer", "swap to workspace four") used to fall straight through to the
cloud AI chat. Needle 2 (github.com/cactus-compute/needle) is a 45M-parameter
tool-calling model — a single 14MB engine using ~28MB of RAM — that maps
those phrases onto the very same skills: text in, a structured tool call
out, no network during inference.

Needle is trained and validated on tool surfaces of at most ~5 tools per
agent (see needle.environments); with more, its retrieval and confidence
heads drift out of distribution and start confidently calling the wrong
tool. So the skills are partitioned into small domain agents (apps, media,
sound, screen, windows, workspace, system, status, info, keys, mouse,
timers) and a cheap keyword router picks the domain for each phrase; a
misroute is safe because the wrong domain's agent refuses with an empty
call and the phrase falls back to the regex brain / AI chat.

Tool declarations follow the conventions of needle.environments: one-
sentence imperative descriptions with explicit disambiguation cues, closed
value sets as Literals, bounded numbers, and human time phrases copied
verbatim for the host to resolve. Every call is gated on Needle's
calibrated confidence *before* it touches the desktop: below
NEEDLE_CONFIDENCE — or NEEDLE_CHATTER_CONFIDENCE for phrases heard in the
background without the wake word — the phrase is handed back instead. The
loop is driven manually with agent.complete() for exactly that reason —
agent.run() would execute tools before we could veto them.
"""

import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal

from .config import (
    NEEDLE_CHATTER_CONFIDENCE,
    NEEDLE_CONFIDENCE,
    NEEDLE_ENABLED,
    NEEDLE_WEIGHTS,
)

# Safety cap on agentic steps per phrase (open X, then do Y, then Z...).
MAX_STEPS = 5

_TOOL_INDEX_DIR = Path.home() / ".cache" / "ninja-assistant"

# Keyword router: first bucket whose pattern matches takes the phrase.
# Domain-level buckets are far more forgiving than intent-level patterns —
# and a wrong bucket just means the domain's agent refuses. Order matters.
_ROUTES = [
    ("apps", r"^(?:please |could you |would you |will you )*(?:open|launch|visit)\b"),
    ("workspace", r"\bworkspaces?\b"),
    ("timers", r"\btimers?\b|\bremind"),
    ("mouse", r"\bmouse\b|\bcursor\b|\bclick\b|\bscroll\b|\bdrag\b"),
    ("keys", r"\btype\b|\bwrite\b|\bpress\b|\bkeys?\b|\bshortcut\b|\bcopy\b"
             r"|\bpaste\b|\bcut\b|\bundo\b|\bredo\b|\bselect all\b"),
    ("system", r"\bwi-?fi\b|\bbluetooth\b|\block\b|\bsleep\b|\bsuspend\b"
               r"|\btrash\b|\bclipboard\b|\bscreenshot\b"),
    ("screen", r"\bbright|\bdim\b|\bscreen\b|\bbacklight\b|\bdisplay\b"),
    ("sound", r"\bvolume\b|\blouder\b|\bquieter\b|\bmute\b|\bsound\b"
              r"|\bspeakers?\b|\bmics?\b|\bmicrophone\b"),
    ("media", r"\bplay\b|\bsongs?\b|\bmusic\b|\bvideos?\b|\bpause\b"
              r"|\btracks?\b|\bskip\b|\bput on\b"),
    ("status", r"\bbattery\b|\bcpu\b|\bmemory\b|\bram\b|\bdisk\b|\bstatus\b"
               r"|\buptime\b|how long"),
    ("info", r"\btime\b|\bdate\b|\bweather\b|\bjoke\b|what day"),
    ("windows", r"\bwindows?\b|\bminimi|\bmaximi|\bfocus\b|\bstash\w*\b"
                r"|\brestore\b|\bdesktop\b|\byoutube\b"),
]
DEFAULT_DOMAIN = "apps"

# Tools whose string arguments must be copied from the phrase. The engine
# occasionally hallucinates arguments on some CPUs (e.g. query="welcome" for
# "play believer by imagine dragons"); a song name or message that appears
# nowhere in what was said must never be typed, sent, or searched for, so
# verify the overlap before executing.
_VERBATIM_ARGS = {
    "play_on_youtube": ("query",),
    "search_web": ("query",),
    "type_text": ("text",),
    "send_whatsapp_message": ("contact", "message"),
    "create_reminder": ("message",),
}

# Which tools belong to which domain agent. Every agent stays at <=6 tools.
DOMAINS = {
    "apps": ["open_app_or_site", "close_app", "search_web", "send_whatsapp_message"],
    "media": ["play_on_youtube", "play_pause_media", "next_track", "previous_track"],
    "sound": ["set_volume", "change_volume", "mute_volume"],
    "screen": ["set_brightness", "change_brightness"],
    "windows": ["focus_window", "close_window", "minimize_window",
                "maximize_window", "show_desktop", "restore_windows"],
    "workspace": ["go_to_workspace", "cycle_workspace", "move_window_to_workspace"],
    "system": ["set_radio", "lock_screen", "sleep_computer", "empty_trash",
               "read_clipboard", "take_screenshot"],
    "status": ["system_status", "battery_status", "uptime"],
    "info": ["get_time", "get_date", "check_weather", "tell_joke"],
    "keys": ["type_text", "press_key", "keyboard_shortcut"],
    "mouse": ["mouse_click", "double_click", "scroll", "move_mouse"],
    "timers": ["set_timer", "create_reminder", "list_timers", "cancel_timer"],
}


def route_domain(text: str) -> str:
    """Pick the domain agent for a phrase (cheap keyword buckets)."""
    lowered = (text or "").lower()
    for domain, pattern in _ROUTES:
        if re.search(pattern, lowered):
            return domain
    return DEFAULT_DOMAIN


def _system_facts() -> str:
    """Response contract, in the exact style of the shipped
    needle.environments (pure instructions — fact-style system turns made
    the model ignore the contract and re-call tools after their result)."""
    return (
        "Map each explicit supported desktop action to exactly one declared "
        "call; never duplicate an action. Do not guess missing values. Copy "
        "typed text, messages, and time phrases verbatim. Unsupported, "
        "invalid, ambiguous, and negated requests return no call."
    )


def _build_tools(needle):
    """Declare every assistant skill as a Needle tool; returns (tools, fns).

    Needle reads these descriptions to decide what to call and how to fill
    arguments, so each mirrors the phrasing a person would actually use and
    says how it differs from its neighbours, in the style of the shipped
    environments.
    """
    from .skills import apps, info, input_control, reminders, system_ctl, web, windows

    tools = []
    fns = {}

    def tool(fn):
        decorated = needle.tool(fn)
        schema = getattr(decorated, "_needle_tool", None) or {}
        fns[schema.get("name") or fn.__name__] = fn
        tools.append(decorated)
        return decorated


    @tool
    def open_app_or_site(target: str):
        """Open a desktop app or a website by name. Use play_on_youtube for playing songs.

        Args:
            target: The app or site name, e.g. chrome, whatsapp, youtube, github.
        """
        if apps.desktop_available(target):
            return apps.launch_app(target)
        if web.find_site(target):
            return web.open_website(target)
        return apps.launch_app(target)

    @tool
    def close_app(target: str):
        """Close a running desktop app by name. For just the focused window use close_window.

        Args:
            target: The app to close, e.g. chrome, spotify.
        """
        return apps.close_app(target)

    @tool
    def search_web(query: str):
        """Search the web on Google and open the results.

        Args:
            query: What to search for, copied word for word.
        """
        return web.google_search(query)

    @tool
    def play_on_youtube(query: str):
        """Play a song, artist, or video on YouTube. Copy the request word for word. Use the playback tools for pausing, resuming, or skipping.

        Args:
            query: The song, artist, or video, copied word for word.
        """
        return web.youtube_search(query)

    @tool
    def send_whatsapp_message(contact: str, message: str):
        """Send a WhatsApp message to a person. Needs a logged-in WhatsApp Web.

        Args:
            contact: The person's name or phone number.
            message: The message text, copied word for word.
        """
        return web.whatsapp_send(contact, message)

    # --- windows & workspaces -----------------------------------------------

    @tool
    def focus_window(title: str):
        """Bring a window to the front by its app or title.

        Args:
            title: The app name or part of the window title.
        """
        return windows.focus_window(title)

    @tool
    def close_window():
        """Close the currently focused window. Takes no arguments. Closing a whole app is close_app."""
        return windows.close_window()

    @tool
    def minimize_window(title: str = ""):
        """Minimise a window, stashing it out of the way.

        Args:
            title: The window to minimise; include only when stated, else the focused one.
        """
        return windows.minimize_window(title)

    @tool
    def maximize_window(title: str = ""):
        """Maximise a window to fill the screen (toggles back if already maximised).

        Args:
            title: The window; include only when stated, else the focused one.
        """
        return windows.maximize_window(title)

    @tool
    def show_desktop():
        """Minimise every window on the current workspace. Takes no arguments."""
        return windows.minimize_all()

    @tool
    def restore_windows():
        """Bring back all minimised windows. Takes no arguments."""
        return windows.restore_all()

    @tool
    def go_to_workspace(number: Annotated[int, needle.Field(ge=1, le=20)]):
        """Switch to a workspace by number.

        Args:
            number: The workspace number, 1-20.
        """
        return windows.goto_workspace(number)

    @tool
    def cycle_workspace(direction: Literal["next", "previous"]):
        """Move to the adjacent workspace.

        Args:
            direction: next or previous.
        """
        return windows.cycle_workspace(direction)

    @tool
    def move_window_to_workspace(
        number: Annotated[int, needle.Field(ge=1, le=20)],
        title: str = "",
    ):
        """Send a window to another workspace and follow it there.

        Args:
            number: The workspace number to move it to.
            title: Which window; include only when stated, else the focused one.
        """
        return windows.move_window_to_workspace(number, title)

    # --- volume & brightness --------------------------------------------------

    @tool
    def set_volume(level: Annotated[int, needle.Field(ge=0, le=100)]):
        """Set the speaker volume to the exact percent the user states. Only when a number is stated; for 'louder' or 'quieter' use change_volume.

        Args:
            level: Volume level from 0 to 100.
        """
        return system_ctl.volume_set(level)

    @tool
    def change_volume(
        direction: Literal["up", "down"],
        step: Annotated[int, needle.Field(gt=0, le=50)] = 10,
    ):
        """Turn the speaker volume up or down a little, e.g. 'turn the volume down', 'a little louder'. This never mutes and never skips.

        Args:
            direction: up or down.
            step: Percent to change by; include only when stated.
        """
        if direction == "up":
            return system_ctl.volume_up(step)
        return system_ctl.volume_down(step)

    @tool
    def mute_volume():
        """Mute or unmute the speaker sound. This never changes the volume level. Takes no arguments."""
        return system_ctl.volume_mute()

    # NOTE: no microphone tool here on purpose. The engine persistently
    # mapped "mute the speakers" to a mic-mute tool (their own validation
    # suite fails refusal cases on some CPUs), and the regex brain already
    # covers mic mute phrasings exactly — so the mic stays out of reach of
    # the model.

    @tool
    def set_brightness(level: Annotated[int, needle.Field(ge=0, le=100)]):
        """Set the screen brightness to an exact percent.

        Args:
            level: Brightness from 0 to 100.
        """
        return system_ctl.brightness_set(level)

    @tool
    def change_brightness(
        direction: Literal["up", "down"],
        step: Annotated[int, needle.Field(gt=0, le=50)] = 10,
    ):
        """Make the screen brighter or dimmer, e.g. 'dim the screen', 'brighten it a bit'.

        Args:
            direction: up or down.
            step: Percent to change by; include only when stated.
        """
        if direction == "up":
            return system_ctl.brightness_up(step)
        return system_ctl.brightness_down(step)

    # --- media playback ---------------------------------------------------------

    @tool
    def play_pause_media():
        """Pause or resume the currently playing media. Takes no arguments. Starting something new is play_on_youtube."""
        return system_ctl.media_key("playpause")

    @tool
    def next_track():
        """Skip to the next track. Takes no arguments."""
        return system_ctl.media_key("next")

    @tool
    def previous_track():
        """Go back to the previous track. Takes no arguments."""
        return system_ctl.media_key("previous")

    # --- radios, session & status -------------------------------------------------

    @tool
    def set_radio(radio: Literal["wifi", "bluetooth"], enabled: bool):
        """Turn WiFi or Bluetooth on or off.

        Args:
            radio: Which radio.
            enabled: true turns it on, false turns it off.
        """
        if radio == "wifi":
            return system_ctl.wifi(enabled)
        return system_ctl.bluetooth(enabled)

    @tool
    def lock_screen():
        """Lock the screen. Takes no arguments."""
        return system_ctl.lock_screen()

    @tool
    def sleep_computer():
        """Put the computer to sleep (suspend). Takes no arguments. Never for shutdown or restart."""
        return system_ctl.suspend_computer()

    @tool
    def empty_trash():
        """Empty the trash. Takes no arguments."""
        return system_ctl.empty_trash()

    @tool
    def read_clipboard():
        """Read the clipboard text out loud. Takes no arguments."""
        return system_ctl.read_clipboard()

    @tool
    def take_screenshot(area: bool = False):
        """Take a screenshot, saved to Pictures and copied to the clipboard.

        Args:
            area: true when the user wants to select a region first.
        """
        return system_ctl.screenshot(area)

    @tool
    def system_status():
        """Report the computer's status: CPU, memory, disk, and battery. For battery alone use battery_status."""
        return system_ctl.system_status()

    @tool
    def battery_status():
        """Report the battery charge percent and whether it is plugged in and charging. Read-only. Takes no arguments."""
        try:
            import psutil

            battery = psutil.sensors_battery()
        except Exception:
            battery = None
        if battery is None:
            return False, "I couldn't read the battery"
        state = "charging" if battery.power_plugged else "on battery"
        return True, f"Battery is at {int(battery.percent)} percent and {state}"

    @tool
    def uptime():
        """Say how long the computer has been on since its last boot. Takes no arguments."""
        return system_ctl.uptime_report()

    # --- keyboard & mouse -------------------------------------------------------

    @tool
    def type_text(text: str):
        """Type text into the focused window as keystrokes. Only for explicit dictation requests like 'type' or 'write'.

        Args:
            text: The exact text to type, copied word for word.
        """
        return input_control.type_text(text)

    @tool
    def press_key(
        key: Literal[
            "enter", "tab", "space", "escape", "backspace", "delete", "up",
            "down", "left", "right", "home", "end", "page up", "page down",
            "print screen", "caps lock", "insert",
        ],
    ):
        """Press a single keyboard key.

        Args:
            key: The key to press.
        """
        return input_control.press_key(key)

    @tool
    def keyboard_shortcut(
        combo: Literal[
            "copy", "paste", "cut", "select all", "save", "undo", "redo",
            "find", "new tab", "close tab", "switch window",
        ],
    ):
        """Press a common Ctrl keyboard shortcut.

        Args:
            combo: Which shortcut to press.
        """
        return input_control.hotkey(combo)

    @tool
    def mouse_click(button: Literal["left", "right", "middle"] = "left"):
        """Click a mouse button at the cursor position.

        Args:
            button: Which button; left unless stated.
        """
        return input_control.click(button)

    @tool
    def double_click():
        """Double-click at the cursor position. Takes no arguments."""
        return input_control.double_click()

    @tool
    def scroll(
        direction: Literal["up", "down"],
        amount: Literal["a bit", "a lot"] = "a bit",
    ):
        """Scroll the page under the cursor up or down.

        Args:
            direction: up or down.
            amount: How far; a bit unless stated.
        """
        return input_control.scroll(direction, 900 if amount == "a lot" else 400)

    @tool
    def move_mouse(
        direction: Literal["left", "right", "up", "down"],
        distance: Literal["a bit", "a lot"] = "a bit",
    ):
        """Nudge the mouse cursor in a direction without clicking.

        Args:
            direction: Which way.
            distance: How far; a bit unless stated.
        """
        return input_control.move_mouse(direction, 550 if distance == "a lot" else 150)

    # --- info -----------------------------------------------------------------

    @tool
    def get_time():
        """Say the current clock time. Takes no arguments."""
        return info.get_time()

    @tool
    def get_date():
        """Say today's date. Takes no arguments."""
        return info.get_date()

    @tool
    def check_weather(city: str = ""):
        """Report the current weather, for a stated city or the default one.

        Args:
            city: The city; include only when stated.
        """
        return info.get_weather(city)

    @tool
    def tell_joke():
        """Tell a short joke. Takes no arguments."""
        return info.tell_joke()

    # --- timers & reminders ------------------------------------------------------

    @tool
    def set_timer(time_human: str):
        """Set a countdown timer for a stated duration.

        Args:
            time_human: The duration copied word for word, e.g. '10 minutes'.
        """
        text = re.sub(r"^\s*(?:for|in)\s+", "", (time_human or "").strip(),
                      flags=re.IGNORECASE)
        secs, extra = reminders.parse_duration(text)
        if secs is None:
            return False, f"I couldn't read the duration '{time_human}'"
        return reminders.set_timer(secs, extra or "timer")

    @tool
    def create_reminder(message: str, date_time_human: str):
        """Create a reminder that fires after a stated time. Needs both a message and a time phrase.

        Args:
            message: What to remind the user about, copied word for word.
            date_time_human: The time phrase copied word for word, e.g. 'in 20 minutes'.
        """
        text = re.sub(r"^\s*(?:for|in)\s+", "", (date_time_human or "").strip(),
                      flags=re.IGNORECASE)
        secs, extra = reminders.parse_duration(text)
        if secs is None:
            return False, f"I couldn't read the time '{date_time_human}'"
        label = message + ((" " + extra) if extra else "")
        return reminders.set_timer(secs, label)

    @tool
    def list_timers():
        """List the running timers and reminders. Takes no arguments."""
        return reminders.list_timers()

    @tool
    def cancel_timer(number: Annotated[int, needle.Field(ge=0, le=999)] = 0):
        """Cancel one timer by number, or all timers.

        Args:
            number: The timer number; 0 means all timers.
        """
        return reminders.cancel_timer(number or None)

    return tools, fns


class NeedleBrain:
    """Natural-language router: phrase -> domain agent -> skill calls.

    Each domain is its own small Needle agent (the shape the model is
    trained on); a keyword router picks the domain. Every tool call is
    confidence-gated before execution; refusals and weak matches return
    handled=False so the caller falls back to the regex brain / AI chat.
    """

    def __init__(self):
        self.available = False
        self._agents = {}
        self._fns = {}
        if not NEEDLE_ENABLED:
            print("[needle] disabled (NEEDLE_ENABLED=0)")
            return
        try:
            import needle
        except ImportError as exc:
            print(f"[needle] package missing ({exc}) — regex brain only")
            return
        try:
            # Same validation the shipped environments use: out-of-bounds
            # calls are suppressed to refusals instead of reaching a skill.
            os.environ.setdefault("NEEDLE_STRICT_VALIDATE", "1")
            self._needle = needle
            all_tools, self._fns = _build_tools(needle)
            by_name = {}
            for t in all_tools:
                schema = getattr(t, "_needle_tool", None) or {}
                by_name[schema.get("name") or ""] = t
            self._domain_tools = {
                domain: [by_name[n] for n in members if n in by_name]
                for domain, members in DOMAINS.items()
            }
            missing = [n for members in DOMAINS.values() for n in members
                       if n not in by_name]
            if missing:
                raise RuntimeError(f"tools missing from DOMAINS: {missing}")
            self.available = True
            print(f"[needle] ready — {len(all_tools)} skills across "
                  f"{len(self._domain_tools)} domain agents (local "
                  "natural-language brain)")
        except Exception as exc:
            self._needle = None
            print(f"[needle] init failed ({exc}) — regex brain only")

    def _agent_for(self, domain: str):
        """Build (or fetch) the Needle agent for one domain. Agents are
        lazily created; the shared engine re-binds on domain switches."""
        agent = self._agents.get(domain)
        if agent is None:
            index = _TOOL_INDEX_DIR / f"needle_tool_index_{domain}"
            kwargs = {
                "tools": self._domain_tools[domain],
                "system": _system_facts(),
            }
            if NEEDLE_WEIGHTS:
                kwargs["weights"] = NEEDLE_WEIGHTS
            try:
                index.parent.mkdir(parents=True, exist_ok=True)
                agent = self._needle.Needle(tool_index_path=str(index), **kwargs)
            except Exception:
                agent = self._needle.Needle(**kwargs)
            self._agents[domain] = agent
        return agent

    def handle(self, text: str, strict: bool = False):
        """Run *text* through Needle. Returns (handled, spoken_reply).

        handled is True only when a tool actually executed; router misses,
        refusals (off-topic empty calls), weak confidence and errors all
        return False so the caller can fall back to the regex brain / chat.
        *strict* raises the confidence bar for phrases heard in the
        background (no wake word) so overheard chatter can't act.
        """
        if not self.available:
            return False, ""
        min_confidence = NEEDLE_CHATTER_CONFIDENCE if strict else NEEDLE_CONFIDENCE
        agent = self._agent_for(route_domain(text))
        says = []
        done = set()
        try:
            response = agent.complete(text)
            for _ in range(MAX_STEPS):
                calls = response.get("function_calls") or []
                if response.get("type") != "call" or not calls:
                    break  # loop done, or the phrase was refused (empty call)
                confidence = response.get("confidence")
                if confidence is not None and confidence < min_confidence:
                    agent.reset()  # drop the half-matched exchange
                    return False, ""
                if any(not self._args_verbatim(text, call) for call in calls):
                    agent.reset()  # hallucinated argument — refuse the phrase
                    return False, ""
                outs, seen = [], set()
                repeat = True
                for call in calls:
                    # The engine sometimes duplicates a call, within a turn
                    # or after its result came back; run each action once.
                    key = (call.get("name"),
                           json.dumps(call.get("arguments"), sort_keys=True))
                    if key in seen or key in done:
                        continue
                    seen.add(key)
                    done.add(key)
                    outs.append(self._execute(call))
                    repeat = False
                says.extend(o["say"] for o in outs if o["ok"] and o["say"])
                if repeat or not outs:
                    break  # nothing new to do — the loop is finished
                response = agent.complete(json.dumps(outs))
        except Exception as exc:
            print(f"[needle] error: {exc}")
            try:
                agent.reset()
            except Exception:
                pass
            return False, ""
        if not says:
            return False, ""
        return True, ". ".join(says)

    @staticmethod
    def _args_verbatim(phrase: str, call: dict) -> bool:
        """True when the call's copy-verbatim arguments appear in the phrase."""
        for arg in _VERBATIM_ARGS.get(call.get("name") or "", ()):
            value = (call.get("arguments") or {}).get(arg)
            if value is None:
                continue
            spoken = set(re.findall(r"[a-z0-9']+", phrase.lower()))
            words = re.findall(r"[a-z0-9']+", str(value).lower())
            if not words or not all(w in spoken for w in words):
                return False
        return True

    def _execute(self, call: dict) -> dict:
        """Run one Needle call against the matching skill function."""
        fn = self._fns.get(call.get("name") or "")
        args = call.get("arguments") or {}
        if fn is None:
            return {"ok": False, "say": "That action isn't available here"}
        try:
            ok, say = fn(**args)
            return {"ok": bool(ok), "say": say}
        except Exception as exc:
            return {"ok": False, "say": f"That didn't work: {exc}"}
