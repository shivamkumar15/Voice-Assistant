"""Smart language layer: fuzzy matching, context resolution, small talk.

Used by Brain BEFORE the regex router so natural / sloppy phrasing still
lands on the right skill:

- typo repair ("opne youtub" -> "open youtube", "volum up" -> "volume up")
- natural phrasing normalisation ("could you please open github for me")
- pronoun / follow-up resolution ("turn it up", "louder", "again", "do that again")
- "my ..." defaults ("play my music" uses remembered favorite)
- name capture ("my name is Priya", "call me X", "weather in <city>" remembers city)
- daily briefing ("good morning" / "briefing" adds time+weather+system hint)

Pure functions + a thin SmartBrain wrapper around SmartMemory. No deps.
"""

from __future__ import annotations

import difflib
import re

# Canonical command vocabulary for fuzzy repair (first-word verbs + key nouns).
_VERBS = ["open", "close", "play", "search", "volume", "brightness", "take",
          "set", "turn", "switch", "type", "press", "click", "scroll", "move",
          "focus", "minimise", "minimize", "maximise", "maximize", "list",
          "show", "tell", "what", "remind", "timer", "message", "whatsapp",
          "lock", "sleep", "shutdown", "restart", "mute", "unmute", "pause",
          "resume", "skip", "next", "previous", "comment", "find", "run",
          "check", "cancel", "clear", "spark", "screenshot"]

_NOUNS = ["youtube", "google", "github", "gmail", "whatsapp", "telegram",
          "terminal", "vscode", "code", "chrome", "firefox", "volume",
          "brightness", "screenshot", "weather", "timer", "clipboard",
          "trash", "wifi", "bluetooth", "mouse", "window", "windows",
          "workspace", "music", "song", "video", "joke", "time", "date",
          "battery", "system", "status"]

_FILLER_PREFIX = re.compile(
    r"^(please\s+|could you(\s+please)?\s+|would you(\s+please)?\s+|can you(\s+please)?\s+|"
    r"hey\s+ninja[, ]*\s*|ok\s+ninja[, ]*\s*|ninja[, ]*\s*|kindly\s+)",
    re.IGNORECASE)
_FILLER_SUFFIX = re.compile(
    r"\s+(please|for me|right now|right away|thanks|thank you)[.!?]*\s*$",
    re.IGNORECASE)


def strip_politeness(text: str) -> str:
    """'Could you please open github for me' -> 'open github'."""
    t = (text or "").strip()
    for _ in range(3):  # nested fillers ("hey ninja, could you please ...")
        new = _FILLER_PREFIX.sub("", t).strip()
        if new == t:
            break
        t = new
    t = _FILLER_SUFFIX.sub("", t).strip()
    # "i want you to X" / "i'd like you to X" -> "X"
    t = re.sub(r"^i (want|would like|'d like) you to\s+", "", t, flags=re.IGNORECASE)
    return t.strip(" ,.!?") or text.strip()


def fuzzy_repair(text: str) -> str:
    """Fix small typos in the verb and key nouns. Conservative: only
    repairs when difflib is confident (>=0.78) so real queries aren't mangled."""
    t = (text or "").strip()
    if not t or len(t) > 160:
        return t
    words = t.split()
    if not words:
        return t
    # verb (first word)
    v = words[0].lower().strip(".,!?")
    if v not in _VERBS:
        hit = difflib.get_close_matches(v, _VERBS, n=1, cutoff=0.70)
        if hit:
            words[0] = hit[0] if words[0].islower() else hit[0]
    # nouns (remaining words, only short alphabetic tokens)
    for i in range(1, len(words)):
        w = words[i].lower().strip(".,!?")
        if not w or len(w) < 4 or not w.isalpha() or w in _NOUNS:
            continue
        hit = difflib.get_close_matches(w, _NOUNS, n=1, cutoff=0.82)
        if hit:
            words[i] = hit[0]
    out = " ".join(words)
    # common STT mangles
    out = re.sub(r"\byoutub\b", "youtube", out, flags=re.IGNORECASE)
    out = re.sub(r"\bvolum\b", "volume", out, flags=re.IGNORECASE)
    out = re.sub(r"\bbrigthness\b|\bbrightnes\b", "brightness", out, flags=re.IGNORECASE)
    out = re.sub(r"\bscreenshat\b|\bscreenshort\b", "screenshot", out, flags=re.IGNORECASE)
    return out


_FOLLOWUP_RE = re.compile(
    r"^(turn it (up|down)|louder|quieter|brighter|dimmer|darker|"
    r"a (bit|little) (louder|quieter|brighter|dimmer)|"
    r"a lot (louder|quieter)|more|less)$", re.IGNORECASE)
_REPEAT_RE = re.compile(
    r"^((do|play) (that|it) again|again|repeat( that)?|one more time|"
    r"run it again)$", re.IGNORECASE)


def resolve_context(text: str, last_cmd: str) -> str:
    """Expand pronouns / follow-ups using the previous command.

    'turn it up' after 'set volume to 40' -> 'volume up'
    'again' -> repeats last command verbatim.
    Returns *text* unchanged when no resolution applies.
    """
    t = (text or "").strip()
    if not t:
        return t
    low = t.lower().strip(" .!?")
    if _REPEAT_RE.fullmatch(low):
        return last_cmd or t
    if _FOLLOWUP_RE.fullmatch(low) and last_cmd:
        lc = last_cmd.lower()
        is_vol = "volume" in lc or "louder" in low or "quieter" in low or low in ("more", "less")
        is_bri = "brightness" in lc or "brighter" in low or "dimmer" in low or "darker" in low
        if "volume" in lc or (is_vol and not is_bri):
            if "down" in low or "quieter" in low or "less" in low or "dimmer" in low:
                return "volume down"
            return "volume up"
        if "brightness" in lc or is_bri:
            if "down" in low or "dimmer" in low or "darker" in low or "less" in low:
                return "brightness down"
            return "brightness up"
        # generic "more/less" after e.g. "scroll down" -> keep direction
        if low in ("more", "again"):
            return last_cmd
    # "it" -> last target, e.g. "close it" after "open youtube"
    m = re.fullmatch(r"(close|focus|minimise|minimize|maximise|maximize) it", low)
    if m and last_cmd:
        m2 = re.match(r"^(?:open|focus)\s+(.+)$", last_cmd.lower())
        if m2:
            return f"{m.group(1)} {m2.group(1)}"
    return t


def expand_my_defaults(text: str, favorites: dict) -> str:
    """'play my music' -> 'play <favorite>'; 'open my editor' etc."""
    t = (text or "").strip()
    low = t.lower()
    if re.fullmatch(r"play (my |favourite |favorite )?(music|song|songs|playlist)", low):
        fav = (favorites or {}).get("music", "")
        if fav:
            return f"play {fav}"
        return "play music"
    return t


# polite name / preference capture, checked before routing
_NAME_RE = re.compile(
    r"^(my name is|call me|i am|i'm)\s+([a-zA-Z][a-zA-Z' -]{1,30})\s*$", re.IGNORECASE)
_CITY_RE = re.compile(
    r"^(?:remember|set)?\s*(?:my|default|home)?\s*city(?: is)?\s*(?:is|to|:)?\s*([a-zA-Z][a-zA-Z .'-]{1,40})$",
    re.IGNORECASE)


def check_smart_setters(text: str, memory) -> str | None:
    """Handle 'my name is X' / 'my city is Y' directly. Returns reply or None."""
    t = (text or "").strip()
    m = _NAME_RE.match(t)
    if m and len(t.split()) <= 6:
        name = m.group(2).strip().title()
        # avoid hijacking "i am late" style phrases
        if m.group(1).lower() in ("i am", "i'm") and len(t.split()) > 4:
            return None
        memory.set("user_name", name)
        return f"Nice to meet you, {name}! I'll remember your name."
    m = _CITY_RE.match(t.lower())
    if m and ("city" in t.lower()):
        city = m.group(1).strip().title()
        if city and len(city.split()) <= 3:
            memory.set("default_city", city)
            return f"Got it — your default city is {city}."
    return None


def smart_greeting(memory) -> str:
    """Time-aware greeting with a proactive hint."""
    try:
        import datetime as _dt
        hour = _dt.datetime.now().hour
    except Exception:
        hour = 12
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    name = memory.user_name
    who = f", {name}" if name else ""
    hint = memory.suggestion()
    base = f"Good {part}{who}. I'm listening — chain tasks with 'and'."
    return f"{base} {hint}." if hint else base


def preprocess(text: str, memory) -> str:
    """Full smart pipeline: alias -> politeness -> fuzzy -> context -> defaults."""
    t = (text or "").strip()
    if not t:
        return t
    t = memory.resolve_alias(t)
    t = memory.corrected(t)
    t = strip_politeness(t)
    t = fuzzy_repair(t)
    t = resolve_context(t, memory.last_command())
    try:
        t = expand_my_defaults(t, memory.data.get("favorites", {}))
    except Exception:
        pass
    return t
