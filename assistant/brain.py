"""Brain: maps spoken phrases to skills and produces a spoken reply."""

import re
from datetime import datetime

from .skills import apps, info, input_control, system_ctl, web, windows


class Brain:
    def __init__(self):
        self.pending_confirm = None  # "shutdown" | "restart" | "logout"

    _CONFIRM_ACTIONS = {
        "shutdown": system_ctl.shutdown_computer,
        "restart": system_ctl.restart_computer,
        "logout": system_ctl.log_out,
    }

    def handle(self, text: str) -> str:
        """Return the spoken reply for a recognised *text* command."""
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

        m = re.match(r"play\s+(.+?)\s+on\s+youtube$", command)
        if m:
            _, reply = web.youtube_search(m.group(1))
            return reply
        m = re.match(r"search\s+(?:for\s+)?(.+?)\s+on\s+youtube$", command)
        if m:
            _, reply = web.youtube_search(m.group(1))
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
        if re.match(r"^(pause|resume|stop)\s*(the )?(music|video|song|playback)?$", command):
            _, reply = system_ctl.media_key("playpause")
            return reply

        m = re.match(r"^play\s+(.+)$", command)
        if m:
            query = m.group(1).strip()
            if query in ("music", "some music", "a song", "something", "my playlist"):
                _, reply = system_ctl.media_key("playpause")
            else:
                _, reply = web.youtube_search(query)
            return reply

        m = re.match(r"^(?:open|go\s+to|launch|visit|start)\s+(.+?)$", command)
        if m and command not in ("start music",):
            target = re.sub(
                r"\s+(website|site|page|dot com|\.com|in browser|in chrome|app|application)$",
                "",
                m.group(1).strip(),
            ).strip()
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
            _, reply = windows.focus_window(m.group(1))
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

        if re.search(r"\b(volume|sound)\b.*\b(up|increase|raise|louder)\b|^louder$|^turn it up$", command):
            _, reply = system_ctl.volume_up()
            return reply
        if re.search(r"\b(volume|sound)\b.*\b(down|decrease|lower|quieter)\b|^quieter$|^turn it down$", command):
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
        if re.fullmatch(r"(mute|unmute|silence)( the)?( volume| sound)?", command):
            _, reply = system_ctl.volume_mute()
            return reply
        m = re.search(r"volume\s+(?:set\s+)?(?:to\s+)?(\d{1,3})\s*(?:percent|%)?", command)
        if m:
            _, reply = system_ctl.volume_set(int(m.group(1)))
            return reply

        if re.search(r"\bbrightness\b.*\b(up|increase|raise|brighter)\b|^brighten( the)?( screen)?( it)?$", command):
            _, reply = system_ctl.brightness_up()
            return reply
        if re.search(r"\bbrightness\b.*\b(down|decrease|lower|dim)\b|^dim( the)?( screen)?( it)?$|^darken( the)?( screen)?$", command):
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
        if re.fullmatch(r"right\s*click", command):
            _, reply = input_control.click("right")
            return reply
        if re.fullmatch(r"click", command):
            _, reply = input_control.click()
            return reply
        m = re.match(r"^scroll\s+(up|down)(\s+a\s+(bit|lot))?$", command)
        if m:
            amount = 800 if m.group(3) == "lot" else 400
            _, reply = input_control.scroll(m.group(1), amount)
            return reply

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

        _, reply = info.chat(text)
        return reply

    @staticmethod
    def _wants_shutdown(c: str) -> bool:
        if re.match(r"^(shut ?down|power ?off|switch off|turn off)\b", c):
            # Don't hijack "turn off bluetooth" style requests.
            return not re.search(
                r"\b(bluetooth|wi-?fi|lights?|notifications?|airplane|do not disturb)\b", c
            )
        return bool(re.search(r"\b(computer|pc|system|machine|laptop)\b", c)
                    and re.search(r"\b(shut ?down|power ?off|turn off)\b", c))

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
