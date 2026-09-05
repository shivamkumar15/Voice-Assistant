"""Brain: maps spoken phrases to skills and produces a spoken reply.

Routing order: regex fast-paths (exact commands, confirmations), then the
local Needle tool-calling model for natural phrasing the regexes can't
match, then the OpenRouter AI chat as the final fallback.
"""

import re
import time
from datetime import datetime

from .config import OPENROUTER_API_KEY
from .needle_brain import NeedleBrain
from .skills import apps, info, input_control, reminders, system_ctl, web, windows


class Brain:
    def __init__(self):
        self.pending_confirm = None  # "shutdown" | "restart" | "logout"
        self.needle = NeedleBrain()  # stays unavailable when disabled

    _CONFIRM_ACTIONS = {
        "shutdown": system_ctl.shutdown_computer,
        "restart": system_ctl.restart_computer,
        "logout": system_ctl.log_out,
    }

    def handle(self, text: str, use_needle: bool = True,
               strict: bool = False) -> str:
        """Return the spoken reply for a recognised *text* command.

        *strict* is True for phrases heard in the background without the
        wake word — Needle then needs a higher confidence to act.
        """
        command = text.lower().strip()

        if self.pending_confirm:
            action = self.pending_confirm
            if re.search(r"\b(yes|yeah|yep|sure|do it|confirm|go ahead)\b", command):
                self.pending_confirm = None
                _, reply = self._CONFIRM_ACTIONS[action]()
                return reply
            if re.search(r"\b(no|nope|cancel|stop|don'?t|never ?mind)\b", command):
                self.pending_confirm = None
                return "Cancelled."
            if not re.search(r"\b(shutdown|shut down|restart|reboot|log ?out|sign ?out)\b", command):
                self.pending_confirm = None

        if self._wants_shutdown(command):
            self.pending_confirm = "shutdown"
            return "Are you sure you want me to shut the computer down? Say yes or no."
        if self._wants_restart(command):
            self.pending_confirm = "restart"
            return "Are you sure you want me to restart the computer? Say yes or no."
        if self._wants_logout(command):
            self.pending_confirm = "logout"
            return "Do you want me to log you out? Open apps will be closed. Say yes or no."

        if re.search(
            r"\b(sleep|suspend|stand ?by)\b",
            command,
        ) and (
            re.match(r"^(go to |put .{0,25}to )?(sleep|suspend|stand ?by)$", command)
            or re.search(r"\b(computer|pc|system|machine|laptop)\b", command)
        ):
            _, reply = system_ctl.suspend_computer()
            return reply

        # --- Workspaces (must precede the generic open/go-to handler) ---
        m = re.match(r"^((?:go to|switch to|move to|jump to|open))\s+(?:the\s+|my\s+)?(.+)$", command)
        if m and "workspace" in command:
            rest = re.sub(r"\bworkspaces?\b", "", m.group(2)).strip()
            if re.fullmatch(r"(next|previous|prev)", rest):
                _, reply = windows.cycle_workspace("next" if rest == "next" else "prev")
                return reply
            n = windows.parse_workspace_number(rest)
            if n is not None:
                _, reply = windows.goto_workspace(n)
                return reply
            if m.group(1) != "open":
                return "Which workspace? Say: go to workspace 2"
            # else: not really a workspace command — fall through to open/etc.
        m = re.match(
            r"^(?:move|send)\s+(?:(.+?)\s+)?to\s+(?:the\s+|my\s+)?workspaces?\s+(.+)$",
            command,
        )
        if m:
            what = (m.group(1) or "").strip()
            n = windows.parse_workspace_number(m.group(2))
            if what in ("", "this window", "the window", "active window",
                        "this", "that", "it"):
                _, reply = windows.move_window_to_workspace(n)
            else:
                _, reply = windows.move_window_to_workspace(n, what)
            return reply
        m = re.match(r"^(next|previous|prev)\s+(?:the\s+)?workspaces?$", command)
        if m:
            _, reply = windows.cycle_workspace("next" if m.group(1) == "next" else "prev")
            return reply
        m = re.match(r"^(?:the\s+|my\s+)?workspaces?\s+(.+)$", command)
        if m:
            n = windows.parse_workspace_number(m.group(1))
            if n is not None:
                _, reply = windows.goto_workspace(n)
                return reply

        m = re.match(r"play\s+(.+?)\s+on\s+youtube$", command)
        if m:
            _, reply = web.youtube_search(m.group(1), autoplay=False)
            return reply
        m = re.match(r"search\s+(?:for\s+)?(.+?)\s+on\s+youtube$", command)
        if m:
            _, reply = web.youtube_search(m.group(1), autoplay=False)
            return reply

        m = re.match(
            r"^(?:google\s+search\s+(?:for\s+)?"
            r"|search\s+(?:(?:the\s+)?(?:web|internet)\s+)?(?:for\s+)?"
            r"|look\s+up\s+(?:for\s+)?)(.+)",
            command,
        )
        if m:
            query = re.sub(r"^google\s+(?:for\s+)?", "", m.group(1))
            _, reply = web.google_search(query)
            return reply

        if re.match(r"^next (song|track|video)$", command):
            _, reply = system_ctl.media_key("next")
            return reply
        m = re.match(r"^(?:go back|previous|rewind)(?: to)? (?:the )?"
                     r"(?:previous |last |prior )?(?:song|track|video)$",
                     command)
        if m:
            _, reply = system_ctl.media_key("previous")
            return reply
        if re.match(r"^(pause|resume|stop)\s*(the )?(music|video|song|playback)?$", command):
            _, reply = system_ctl.media_key("playpause")
            return reply
        if re.match(r"^skip( (this|the)? ?(song|track|video))?$", command):
            _, reply = system_ctl.media_key("next")
            return reply

        m = re.match(r"^play\s+(.+)$", command)
        if m:
            _, reply = web.play_query(m.group(1).strip())
            return reply

        m = re.match(r"^(?:open|go\s+to|launch|visit|start)\s+(.+?)$", command)
        if m and command not in ("start music",):
            target = re.sub(
                r"\s+(website|site|page|dot com|\.com|in browser|in chrome|app|application)$",
                "",
                m.group(1).strip(),
            ).strip()
            # A real installed desktop app always wins over a website with
            # a similar name ("open whatsapp" -> the app, not the web page).
            if apps.desktop_available(target):
                _, reply = apps.launch_app(target)
                return reply
            hit = web.find_site(target)
            if hit:
                _, reply = web.open_website(hit[0])
                return reply
            _, reply = apps.launch_app(target)
            return reply

        m = re.match(r"^open\s+(?:the\s+)?file\s+(.+)", command)
        if m:
            import os
            import subprocess

            path = os.path.expanduser(m.group(1))
            if os.path.exists(path):
                subprocess.Popen(["xdg-open", path])
                return f"Opening {m.group(1)}"
            return f"I can't find {m.group(1)}"

        m = re.match(r"^close\s+(?:the\s+)?(.+?)(?:\s+app(?:lication)?)?$", command)
        if m and "window" not in command and "tab" not in command:
            target = m.group(1).strip()
            if target in ("it", "this", "that"):
                _, reply = windows.close_window()
            elif target in ("browser", "chrome", "google chrome") or (
                web.find_site(target) and target not in apps.APPS
            ):
                # Closing a website means closing its browser.
                _, reply = apps.close_app("chrome")
            else:
                _, reply = apps.close_app(target)
            return reply

        if re.search(r"^(show|go to)\s+(the\s+)?desktop$|minimi[sz]e everything|minimi[sz]e all", command):
            _, reply = windows.minimize_all()
            return reply
        if re.search(
            r"restore (my |the )?windows?|bring (everything|all (my )?windows|them) back"
            r"|unminimi[sz]e (everything|all)",
            command,
        ):
            _, reply = windows.restore_all()
            return reply
        m = re.match(r"^(minimi[sz]e|maximi[sz]e|maximi[sz])\s*(?:the)?\s*(.*)$", command)
        if m:
            title = m.group(2).replace("window", "").strip()
            fn = windows.minimize_window if m.group(1).startswith("min") else windows.maximize_window
            _, reply = fn(title)
            return reply
        m = re.match(
            r"^(?:focus|switch to|bring up|activate)\s+(?:the\s+)?(.+?)(?:\s+window)?$",
            command,
        )
        if m and m.group(1) not in ("window",):
            ok, reply = windows.focus_window(m.group(1))
            if not ok and apps.can_launch(m.group(1)):
                # Not running — be a real assistant and start it instead.
                ok2, reply2 = apps.launch_app(m.group(1))
                if ok2:
                    return f"{m.group(1)} wasn't running. {reply2}"
            return reply
        if re.fullmatch(r"(focus|activate)( the)? window", command) or command == "switch window":
            _, reply = input_control.hotkey("switch window")
            return reply
        if re.match(r"^(list|what are|show me)\s+(?:the\s+)?(?:open\s+)?windows?", command):
            _, reply = windows.list_windows()
            return reply
        if re.fullmatch(r"(close|close the) window", command):
            _, reply = windows.close_window()
            return reply

        if re.search(r"\b(volume|sound)\b.*\b(up|increase|raise|louder)\b"
                     r"|^(go|come|turn|crank|pump)(?: the)? (?:volume|sound|music)? ?up$"
                     r"|^(increase|raise|crank|pump)(?: the)? (?:volume|sound)$"
                     r"|^(louder|up)$|^turn it up$|^crank it( up)?$|^ pump it$", command):
            _, reply = system_ctl.volume_up()
            return reply
        if re.search(r"\b(volume|sound)\b.*\b(down|decrease|lower|quieter)\b"
                     r"|^(go|come|turn)(?: the)? (?:volume|sound|music)? ?down$"
                     r"|^(decrease|lower)(?: the)? (?:volume|sound)$"
                     r"|^(quieter|down)$|^turn it down$", command):
            _, reply = system_ctl.volume_down()
            return reply
        if re.search(r"\bmic(rophone)?\b", command) and \
                re.fullmatch(
                    r"(?:un)?mute(?:\s+(?:the|my))?(?:\s+(?:mic|microphone))?"
                    r"|(?:mic|microphone)\s+(?:un)?mute",
                    command,
                ):
            _, reply = system_ctl.mic_mute()
            return reply
        if re.fullmatch(r"(mute|unmute|silence)( the| my)?( volume| sound| speakers?| audio)?", command):
            _, reply = system_ctl.volume_mute()
            return reply
        m = re.search(r"volume\s+(?:set\s+)?(?:to\s+)?(\d{1,3})\s*(?:percent|%)?", command)
        if m:
            _, reply = system_ctl.volume_set(int(m.group(1)))
            return reply

        if re.search(r"\bbrightness\b.*\b(up|increase|raise|brighter)\b"
                     r"|^(go|come|turn)(?: the)? (?:brightness|screen)? ?up$"
                     r"|^(increase|raise)(?: the)? (?:brightness|screen)$"
                     r"|^brighter$|^brighten( the)?( screen)?( it)?( up)?$|^light it up$", command):
            _, reply = system_ctl.brightness_up()
            return reply
        if re.search(r"\bbrightness\b.*\b(down|decrease|lower|dim)\b"
                     r"|^(go|come|turn)(?: the)? (?:brightness|screen)? ?down$"
                     r"|^(decrease|lower)(?: the)? (?:brightness|screen)$"
                     r"|^dimmer$|^dim( the)?( screen)?( it)?( down)?$"
                     r"|^darken( the)?( screen)?( it)?$", command):
            _, reply = system_ctl.brightness_down()
            return reply
        m = re.search(r"brightness\s+(?:to\s+)?(\d{1,3})\s*(?:percent|%)?", command)
        if m:
            _, reply = system_ctl.brightness_set(int(m.group(1)))
            return reply

        if re.search(r"(take|capture|grab)\s+(an?\s+)?(screen\s?shot|snapshot)|^screenshot( of (the )?(screen|desktop))?$", command):
            area = bool(re.search(r"\b(area|region|part|selection|section)\b", command))
            _, reply = system_ctl.screenshot(area)
            return reply

        if re.search(r"\bbattery\b|\bhow much (charge|battery)\b", command):
            ok, reply = system_ctl.system_status()
            battery_part = [p for p in reply.split(". ") if "battery" in p]
            return battery_part[0] if battery_part else "I couldn't read the battery"
        if re.search(r"\b(cpu|memory|ram|disk|system status|system info)\b", command) or \
                re.match(r"^how('?s| is) (my )?(computer|pc|system)( doing)?$", command):
            _, reply = system_ctl.system_status()
            return reply
        if re.search(r"\buptime\b|^how long .* been (on|running|up)", command):
            _, reply = system_ctl.uptime_report()
            return reply

        # --- Timers & reminders ---
        m = re.match(r"^(?:set )?(?:a |an )?timer for (.+)$", command)
        if m:
            secs, label = reminders.parse_duration(m.group(1))
            if secs is None:
                return "For how long? Say: set a timer for 10 minutes"
            _, reply = reminders.set_timer(secs, label)
            return reply
        m = re.match(r"^remind me to (.+?) in (.+)$", command)
        if m:
            secs, extra = reminders.parse_duration(m.group(2))
            if secs is None:
                return "In how long? Say: remind me to call mom in 20 minutes"
            label = (m.group(1) + (" " + extra if extra else "")).strip()
            _, reply = reminders.set_timer(secs, label)
            return reply
        m = re.match(r"^remind me in (.+)$", command)
        if m:
            secs, extra = reminders.parse_duration(m.group(1))
            if secs is None:
                return "In how long? Say: remind me in 10 minutes"
            _, reply = reminders.set_timer(secs, extra or "reminder")
            return reply
        if re.fullmatch(r"(list|show)( my)? (timers?|reminders?)", command):
            _, reply = reminders.list_timers()
            return reply
        m = re.fullmatch(r"cancel(?: my| the)? (timers?|reminders?)(?: #?(\d+))?", command)
        if m:
            _, reply = reminders.cancel_timer(int(m.group(2)) if m.group(2) else None)
            return reply

        # --- Radios, trash, clipboard ---
        m = re.match(r"^(turn|switch)\s+(wifi|wi-?fi|bluetooth)\s+(on|off)$", command)
        if m:
            kind, state = m.group(2), m.group(3) == "on"
            fn = system_ctl.wifi if "blue" not in kind else system_ctl.bluetooth
            _, reply = fn(state)
            return reply
        m = re.match(r"^(enable|disable)\s+(wifi|wi-?fi|bluetooth)$", command)
        if m:
            kind, state = m.group(2), m.group(1) == "enable"
            fn = system_ctl.wifi if "blue" not in kind else system_ctl.bluetooth
            _, reply = fn(state)
            return reply
        m = re.match(r"^turn\s+(on|off)\s+(?:the\s+)?(wifi|wi-?fi|bluetooth)$", command)
        if m:
            kind, state = m.group(2), m.group(1) == "on"
            fn = system_ctl.wifi if "blue" not in kind else system_ctl.bluetooth
            _, reply = fn(state)
            return reply
        if re.fullmatch(r"empty(?: the)? trash", command):
            _, reply = system_ctl.empty_trash()
            return reply
        if re.fullmatch(r"(read|show)( me)?( my| the)? clipboard", command) or \
                re.fullmatch(r"what('s| is)( in)?( my| the)? clipboard", command) or \
                command == "what did i copy":
            _, reply = system_ctl.read_clipboard()
            return reply

        if re.search(r"\block\b.*\b(screen|pc|computer)\b|^lock (the |my )?(screen|pc|computer)$", command):
            _, reply = system_ctl.lock_screen()
            return reply

        m = re.match(r"^(?:type|write)\s+(.+)$", command)
        if m:
            _, reply = input_control.type_text(m.group(1))
            return reply
        if command in input_control._COMBO_WORDS:
            _, reply = input_control.hotkey(command)
            return reply
        m = re.match(r"^press\s+(?:the\s+)?(.+?)(?:\s+key)?$", command)
        if m:
            _, reply = input_control.press_key(m.group(1))
            return reply
        if re.fullmatch(r"double\s*click", command):
            _, reply = input_control.double_click()
            return reply
        if re.fullmatch(r"(right\s*click|click right)", command):
            _, reply = input_control.click("right")
            return reply
        if re.fullmatch(r"(middle\s*click|click middle)", command):
            _, reply = input_control.click("middle")
            return reply
        if re.fullmatch(r"(click|left\s*click|click left)", command):
            _, reply = input_control.click()
            return reply
        m = re.match(r"^scroll\s+(up|down)(\s+a\s+(bit|lot))?$", command)
        if m:
            amount = 800 if m.group(3) == "lot" else 400
            _, reply = input_control.scroll(m.group(1), amount)
            return reply
        m = re.match(r"^drag\s+(?:the\s+)?mouse\s+(left|right|up|down)$", command)
        if m:
            _, reply = input_control.drag(m.group(1))
            return reply
        if re.fullmatch(r"(where(\'s| is) (the )?mouse|mouse position)", command):
            pos = input_control.mouse_position()
            if pos:
                return f"The mouse is at {pos[0]}, {pos[1]}"
            return "I can't read the mouse position here"

        m = re.match(
            r"^(?:move|push)\s+(?:the\s+)?mouse\s+(left|right|up|down)"
            r"(?:\s+a\s+(bit|little|lot|ton))?$",
            command,
        )
        if m:
            distance = {"bit": 120, "little": 120, "lot": 600, "ton": 600}.get(m.group(2), 300)
            _, reply = input_control.move_mouse(m.group(1), distance)
            return reply
        m = re.match(r"^(?:move|put)\s+(?:the\s+)?mouse\s+to\s+(\d{1,4})\s*[ ,]\s*(\d{1,4})$", command)
        if m:
            _, reply = input_control.move_mouse(x=int(m.group(1)), y=int(m.group(2)))
            return reply
        m = re.match(
            r"^(?:move|put)\s+(?:the\s+)?mouse\s+to\s+(?:the\s+)?"
            r"(center|middle|top|bottom|left|right|top left|top right|"
            r"bottom left|bottom right|top center|top centre|bottom center|"
            r"middle left|middle right)$",
            command,
        )
        if m:
            _, reply = input_control.move_mouse_named(m.group(1))
            return reply

        # --- Messaging & page interaction (chainable steps) ---
        m = re.match(
            r"^(?:send )?(?:a )?(?:whatsapp )?(?:message|text|msg)"
            r"(?: to)? ([a-z0-9 _.'+-]{1,30}?)(?: saying | that |, |: )?(.+)$",
            command,
        )
        if m:
            _, reply = web.whatsapp_send(m.group(1).strip(), m.group(2).strip())
            return reply
        m = re.match(
            r"^whatsapp ([a-z0-9 _.'+-]{1,30}?)(?: saying | that |, |: )?(.+)$",
            command,
        )
        if m:
            _, reply = web.whatsapp_send(m.group(1).strip(), m.group(2).strip())
            return reply
        m = re.match(r"^comment (.+) on (?:this|the|that) post$", command)
        if m:
            return self._comment_text(m.group(1).strip())
        m = re.match(r"^comment (.+)$", command)
        if m:
            return self._comment_text(m.group(1).strip())
        m = re.match(r"^find (.+?)(?: on (?:this |the )?page)?$", command)
        if m:
            query = m.group(1).strip()
            input_control.hotkey("find")  # Ctrl+F in the browser
            time.sleep(0.4)
            input_control.type_text(query)
            time.sleep(0.2)
            input_control.press_key("enter")
            return f"Finding {query} on this page"

        if re.search(
            r"(what(?:'s| is)? the time|what time is it|tell me the time|current time|time now|\btime\b.*\b(is it|kya)\b)",
            command,
        ):
            _, reply = info.get_time()
            return reply
        if re.search(r"\b(date|day is it today|today'?s date|what day)\b", command):
            _, reply = info.get_date()
            return reply
        if re.fullmatch(r"(what'?s|how'?s|check|tell me)\s+(the\s+)?weather(\s+(like\s+)?(today|now|outside))?", command):
            _, reply = info.get_weather()
            return reply
        m = re.search(r"weather(?:\s+(?:like\s+)?(?:today|now))?\s+(?:in|at|for)\s+(.+)", command)
        if m:
            _, reply = info.get_weather(m.group(1).rstrip("?"))
            return reply
        if re.search(r"\bjoke\b", command):
            _, reply = info.tell_joke()
            return reply
        if re.search(r"who are you|what are you|what can you do|your name|introduce yourself|^help$|^help me$", command):
            _, reply = info.who_are_you()
            return reply

        if re.match(r"^(hi|hello|hey|yo|good (morning|afternoon|evening)|namaste)\b", command):
            hour = datetime.now().hour
            part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
            return f"Hello! Good {part}. What can I do for you?"
        if re.search(r"\bthank(s| you)\b", command):
            return "You're welcome!"
        if re.search(r"\bhow are you\b", command):
            return "Running smooth and ready. How are you?"

        if use_needle:
            handled, reply = self.needle.handle(text, strict=strict)
            if handled:
                return reply

        _, reply = info.chat(text)
        return reply

    def _comment_text(self, text: str) -> str:
        """Type *text* into the focused box and submit (e.g. a post comment)."""
        ok, _ = input_control.type_text(text)
        if not ok:
            return "I couldn't type the comment"
        time.sleep(0.3)
        input_control.press_key("enter")
        return f"Commented: {text}"

    # --- chained multi-step commands -------------------------------------

    _CHAIN_SEP = re.compile(r"\s*(?:;|\band then\b|\bthen\b|\band\b)\s*")

    def handle_chain(self, text: str, addressed: bool = True,
                     from_voice: bool = False):
        """Run one or more chained commands ("A and B and C").

        Returns (handled, reply). A split only happens when *every* part
        looks like a real command — otherwise the whole phrase is handled
        as a single command exactly like before. *addressed*/*from_voice*
        come from the worker: background chatter needs a higher Needle
        confidence before any action is taken.
        """
        text = (text or "").strip()
        if not text:
            return False, ""
        strict = from_voice and not addressed
        if self.pending_confirm:
            return True, self.handle(text)
        parts = self._split_chain(text)
        if len(parts) == 1:
            if self._is_known_command(parts[0]):
                return True, self.handle(parts[0], strict=strict)
            # Unknown phrasing: Needle (the local tool-calling model) gets
            # first shot at natural language, then the regex + AI chat
            # fallback. use_needle is skipped in handle() to avoid double
            # execution.
            handled, reply = self.needle.handle(parts[0], strict=strict)
            if handled:
                return True, reply
            return False, self.handle(parts[0], use_needle=False)
        replies = []
        for i, part in enumerate(parts):
            replies.append(self.handle(part))
            if i < len(parts) - 1:
                time.sleep(2.0 if self._needs_settle(part) else 0.6)
        return True, ". ".join(replies)

    def _split_chain(self, text: str):
        """Split into command steps, or [text] when splitting is unsafe."""
        lowered = text.lower().strip()
        # Never split typed/dictated content — "and" may be literal text.
        if re.match(r"^(type|write)\s+.+$", lowered):
            return [text]
        # Never split questions: "what's my cpu and memory doing?" is one
        # status request, not "what's my cpu" + "memory doing?".
        if re.search(r"\b(what|where|when|who|why|how)\b", lowered):
            return [text]
        raw = [p.strip(" ,.!?") for p in self._CHAIN_SEP.split(text)]
        parts = [p for p in raw if p]
        if len(parts) < 2:
            return [text]
        if all(self._is_known_command(p) for p in parts):
            return parts
        return [text]

    @staticmethod
    def _needs_settle(part: str) -> bool:
        """Steps that load pages/apps need a pause before the next step."""
        return bool(re.match(
            r"^(open|go to|launch|visit|start|play|search|look up|"
            r"whatsapp|message|text|send|find)\b",
            part.lower().strip(),
        ))

    def _is_known_command(self, text: str) -> bool:
        """Pure check mirroring handle(): True when *text* parses as a command.

        No skills are executed here — used to validate chain splits and to
        silence background chatter in continuous-listening mode.
        """
        c = text.lower().strip()
        if not c:
            return False
        if self.pending_confirm:
            return True
        if OPENROUTER_API_KEY:
            return True  # AI fallback answers everything
        # NOTE: EXIT_PHRASES intentionally not listed — stray voice "quit"
        # must stay silent; real exits are caught by the caller first.
        if self._wants_shutdown(c) or self._wants_restart(c) or self._wants_logout(c):
            return True
        if re.search(r"\bsleep\b|\bsuspend\b|\bstand ?by\b", c):
            return True
        if re.match(r"play\s+.+\s+on\s+youtube$", c):
            return True
        if re.match(r"search\s+.+\s+on\s+youtube$", c):
            return True
        if re.match(
            r"^(?:google\s+search\s+(?:for\s+)?"
            r"|search\s+(?:(?:the\s+)?(?:web|internet)\s+)?(?:for\s+)?"
            r"|look\s+up\s+(?:for\s+)?)(.+)", c,
        ):
            return True
        if re.match(r"^next (song|track|video)$", c):
            return True
        if re.match(r"^(?:go back|previous|rewind)(?: to)? (?:the )?"
                    r"(?:previous |last |prior )?(?:song|track|video)$", c):
            return True
        if re.match(r"^(pause|resume|stop)\s*(the )?(music|video|song|playback)?$", c):
            return True
        if re.match(r"^skip( (this|the)? ?(song|track|video))?$", c):
            return True
        if re.match(r"^play\s+(.+)$", c):
            return True
        m = re.match(r"^(?:open|go\s+to|launch|visit|start)\s+(.+?)$", c)
        if m and c != "start music":
            import shutil as _shutil

            target = re.sub(
                r"\s+(website|site|page|dot com|\.com|in browser|in chrome|app|application)$",
                "", m.group(1).strip(),
            ).strip()
            if web.find_site(target) or target in apps.APPS:
                return True
            if _shutil.which(target.replace(" ", "-")):
                return True
            if "workspace" in c:
                pass  # maybe a workspace command — checked below
            else:
                return False
        if re.match(r"^open\s+(?:the\s+)?file\s+(.+)", c):
            return True
        if re.match(r"^close\s+(?:the\s+)?.+$", c):
            if re.fullmatch(r"(close|close the) window", c):
                return True
            return "tab" not in c
        if re.search(r"^(show|go to)\s+(the\s+)?desktop$|minimi[sz]e everything|minimi[sz]e all", c):
            return True
        if re.search(r"restore (my |the )?windows?|bring (everything|all (my )?windows|them) back"
                      r"|unminimi[sz]e (everything|all)", c):
            return True
        if re.match(r"^(minimi[sz]e|maximi[sz]e|maximi[sz])\s*(?:the)?\s*(.*)$", c):
            return True
        if re.match(r"^(?:focus|switch to|bring up|activate)\s+(?:the\s+)?.+$", c):
            return True
        if re.fullmatch(r"(focus|activate)( the)? window", c) or c == "switch window":
            return True
        if re.match(r"^(list|what are|show me)\s+(?:the\s+)?(?:open\s+)?windows?", c):
            return True
        if re.search(r"\b(volume|sound)\b.*\b(up|increase|raise|louder)\b"
                     r"|^(go|come|turn|crank|pump)(?: the)? (?:volume|sound|music)? ?up$"
                     r"|^(increase|raise|crank|pump)(?: the)? (?:volume|sound)$"
                     r"|^(louder|up)$|^turn it up$|^crank it( up)?$|^ pump it$", c):
            return True
        if re.search(r"\b(volume|sound)\b.*\b(down|decrease|lower|quieter)\b"
                     r"|^(go|come|turn)(?: the)? (?:volume|sound|music)? ?down$"
                     r"|^(decrease|lower)(?: the)? (?:volume|sound)$"
                     r"|^(quieter|down)$|^turn it down$", c):
            return True
        if re.search(r"\bmic(rophone)?\b", c):
            return True
        if re.fullmatch(r"(mute|unmute|silence)( the| my)?( volume| sound| speakers?| audio)?", c):
            return True
        if re.search(r"volume\s+(?:set\s+)?(?:to\s+)?(\d{1,3})\s*(?:percent|%)?", c):
            return True
        if re.search(r"\bbrightness\b.*\b(up|increase|raise|brighter)\b"
                     r"|^(go|come|turn)(?: the)? (?:brightness|screen)? ?up$"
                     r"|^(increase|raise)(?: the)? (?:brightness|screen)$"
                     r"|^brighter$|^brighten( the)?( screen)?( it)?( up)?$|^light it up$", c):
            return True
        if re.search(r"\bbrightness\b.*\b(down|decrease|lower|dim)\b"
                     r"|^(go|come|turn)(?: the)? (?:brightness|screen)? ?down$"
                     r"|^(decrease|lower)(?: the)? (?:brightness|screen)$"
                     r"|^dimmer$|^dim( the)?( screen)?( it)?( down)?$"
                     r"|^darken( the)?( screen)?( it)?$", c):
            return True
        if re.search(r"(take|capture|grab)\s+(an?\s+)?(screen\s?shot|snapshot)"
                      r"|^screenshot( of (the )?(screen|desktop))?$", c):
            return True
        if re.search(r"\bbattery\b|\bhow much (charge|battery)\b", c):
            return True
        if re.search(r"\b(cpu|memory|ram|disk|system status|system info)\b", c):
            return True
        if re.match(r"^how('?s| is) (my )?(computer|pc|system)( doing)?$", c):
            return True
        if re.search(r"\buptime\b|^how long .* been (on|running|up)", c):
            return True
        # Workspaces (mirrors the handlers above).
        m = re.match(r"^((?:go to|switch to|move to|jump to|open))\s+(?:the\s+|my\s+)?(.+)$", c)
        if m and "workspace" in c:
            rest = re.sub(r"\bworkspaces?\b", "", m.group(2)).strip()
            if re.fullmatch(r"(next|previous|prev)", rest):
                return True
            if windows.parse_workspace_number(rest) is not None:
                return True
            if m.group(1) != "open":
                return True  # handled as a "which workspace?" prompt
        if re.match(r"^(?:move|send)\s+(?:(.+?)\s+)?to\s+(?:the\s+|my\s+)?workspaces?\s+.+$", c):
            return True
        if re.match(r"^(next|previous|prev)\s+(?:the\s+)?workspaces?$", c):
            return True
        m = re.match(r"^(?:the\s+|my\s+)?workspaces?\s+(.+)$", c)
        if m and windows.parse_workspace_number(m.group(1)) is not None:
            return True
        if re.match(r"^(?:set )?(?:a |an )?timer for .+$", c):
            return True
        if re.match(r"^remind me (to .+ in .+|in .+)$", c):
            return True
        if re.fullmatch(r"(list|show)( my)? (timers?|reminders?)", c):
            return True
        if re.fullmatch(r"cancel(?: my| the)? (timers?|reminders?)(?: #?\d+)?", c):
            return True
        if re.match(r"^(turn|switch|enable|disable)\s+(wifi|wi-?fi|bluetooth)\b", c):
            return True
        if re.match(r"^turn\s+(on|off)\s+(?:the\s+)?(wifi|wi-?fi|bluetooth)$", c):
            return True
        if re.fullmatch(r"empty(?: the)? trash", c):
            return True
        if re.search(r"\bclipboard\b|what did i copy", c):
            return True
        if re.search(r"\block\b", c):
            return True
        if re.match(r"^(?:type|write)\s+(.+)$", c):
            return True
        if c in input_control._COMBO_WORDS:
            return True
        if re.match(r"^press\s+(?:the\s+)?.+$", c):
            return True
        if re.fullmatch(r"double\s*click", c):
            return True
        if re.fullmatch(r"(right\s*click|click right|middle\s*click|click middle"
                        r"|click|left\s*click|click left)", c):
            return True
        if re.match(r"^scroll\s+(up|down)", c):
            return True
        if re.match(r"^drag\s+(?:the\s+)?mouse\s+(left|right|up|down)$", c):
            return True
        if re.fullmatch(r"(where(\'s| is) (the )?mouse|mouse position)", c):
            return True
        if re.match(r"^(?:move|push)\s+(?:the\s+)?mouse\s+(left|right|up|down)", c):
            return True
        if re.match(r"^(?:move|put)\s+(?:the\s+)?mouse\s+to\s+", c):
            return True
        if re.match(r"^(?:send )?(?:a )?(?:whatsapp )?(?:message|text|msg)(?: to)? .+ .+$", c):
            return True
        if re.match(r"^whatsapp .+ .+$", c):
            return True
        if re.match(r"^comment .+$", c):
            return True
        if re.match(r"^find .+$", c):
            return True
        if re.search(r"(what(?:'s| is)? the time|what time is it|tell me the time"
                      r"|current time|time now)", c):
            return True
        if re.search(r"\b(date|day is it today|today'?s date|what day)\b", c):
            return True
        if re.search(r"\bweather\b", c):
            return True
        if re.search(r"\bjoke\b", c):
            return True
        if re.search(r"who are you|what are you|what can you do|your name"
                      r"|introduce yourself|^help$|^help me$", c):
            return True
        if re.match(r"^(hi|hello|hey|yo|good (morning|afternoon|evening)|namaste)\b", c):
            return True
        if re.search(r"\bthank(s| you)\b", c):
            return True
        if re.search(r"\bhow are you\b", c):
            return True
        return False

    @staticmethod
    def _wants_shutdown(c: str) -> bool:
        if re.match(r"^(shut ?down|shut ?off|power ?off|power ?down|switch off|turn off)\b", c):
            # Don't hijack "turn off bluetooth" style requests.
            return not re.search(
                r"\b(bluetooth|wi-?fi|lights?|notifications?|airplane|do not disturb)\b", c
            )
        return bool(re.search(r"\b(computer|pc|system|machine|laptop)\b", c)
                    and re.search(r"\b(shut ?down|shut ?off|power ?off|power ?down|turn off)\b", c))

    @staticmethod
    def _wants_restart(c: str) -> bool:
        if re.search(r"\b(restart|reboot)\b", c):
            return bool(re.match(r"^(restart|reboot)", c)) or \
                bool(re.search(r"\b(computer|pc|system|machine|laptop)\b", c))
        return False

    @staticmethod
    def _wants_logout(c: str) -> bool:
        return bool(re.match(r"^(log|sign)\s?out\b", c) or
                    re.search(r"\b(log|sign) (me )?out\b", c))
