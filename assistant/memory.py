"""Smart persistent memory for Ninja.

Stores user preferences, aliases, command history and learned corrections
in a small JSON file so the assistant gets smarter over time:

- remembers your name, default city, favourite music, volume defaults
- keeps free-form facts that don't fit a preference ("I'm afraid of heights")
- learns contact/app nicknames ("mom" -> WhatsApp contact, "vscode" -> "code")
- keeps last ~50 commands for context resolution ("turn it up", "again")
- tracks usage counts for proactive suggestions ("you often check weather...")

File: ~/.local/share/ninja-assistant/memory.json
No third-party deps, never raises on load/save.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path


def _default_path() -> Path:
    return Path.home() / ".local" / "share" / "ninja-assistant" / "memory.json"


class SmartMemory:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _default_path()
        self._lock = threading.RLock()
        self.data: dict = {
            "user_name": "",
            "default_city": "",
            "favorites": {"music": "", "app": "", "website": ""},
            "preferences": {},
            "facts": [],            # free-form facts that fit no preference slot
            "aliases": {},          # nickname -> canonical ("mom" -> contact)
            "corrections": {},      # misheard -> intended ("oprn youtube" -> "open youtube")
            "history": [],          # [{cmd, reply_ok, ts}]
            "usage": {},            # intent-key -> count
            "last": {"cmd": "", "reply": "", "ts": 0.0},
        }
        self.load()

    # ---------- persistence ----------
    # History/usage/corrections are trimmed aggressively; facts are capped
    # at MAX_FACTS, so the profile itself stays small. Command history is
    # the only bulky part and is trimmed to keep the JSON far under this.
    MAX_JSON_BYTES = 100_000

    def load(self):
        with self._lock:
            try:
                if self.path.exists():
                    loaded = json.loads(self.path.read_text())
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if k in self.data:
                                self.data[k] = v
                        # Repair legacy shapes: a facts list that is not a
                        # list (or a string) previously crashed recall.
                        if not isinstance(self.data.get("facts"), list):
                            self.data["facts"] = []
                        if not isinstance(self.data.get("history"), list):
                            self.data["history"] = []
                        for key in ("preferences", "aliases", "corrections",
                                    "usage", "favorites"):
                            if not isinstance(self.data.get(key), dict):
                                self.data[key] = {}
            except Exception as exc:
                # A corrupted file used to be swallowed silently, so the
                # assistant quietly "forgot" everything. Keep the broken
                # file so the cause is visible, and say so in the terminal.
                print(f"[memory] couldn't read {self.path} ({exc}) — "
                      "starting with a fresh memory")
                try:
                    broken = self.path.with_suffix(".broken.json")
                    if self.path.exists():
                        broken.write_bytes(self.path.read_bytes())
                except Exception:
                    pass

    def save(self):
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                # Trim the bulk before writing, not after: slicing the JSON
                # string to a byte cap used to write TRUNCATED JSON to disk,
                # which then failed to load on the next start — the whole
                # memory silently reset every time it grew past 20KB.
                self._trim_for_disk()
                payload = self._serialized()
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(payload)
                tmp.replace(self.path)
            except Exception as exc:
                print(f"[memory] save failed: {exc}")

    def _trim_for_disk(self):
        """Keep the JSON under MAX_JSON_BYTES by dropping oldest history."""
        try:
            # Measure exactly what save() writes (indented), or the cap
            # silently drifts and the file keeps growing past it.
            while len(self._serialized()) > self.MAX_JSON_BYTES:
                hist = self.data.get("history") or []
                if len(hist) > 5:
                    del hist[: max(1, len(hist) // 2)]
                    continue
                corr = self.data.get("corrections") or {}
                if len(corr) > 10:
                    for k in list(corr)[: len(corr) // 2]:
                        corr.pop(k, None)
                    continue
                if (self.data.get("facts") or []) and self.MAX_FACTS > 20:
                    self.MAX_FACTS = 20
                    del (self.data["facts"] or [])[: len(self.data["facts"]) // 2]
                    continue
                break  # nothing left worth dropping
        except Exception:
            pass

    def _serialized(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    # ---------- simple accessors ----------
    @property
    def user_name(self) -> str:
        return (self.data.get("user_name") or "").strip()

    @property
    def default_city(self) -> str:
        return (self.data.get("default_city") or "").strip()

    def set(self, key: str, value: str):
        with self._lock:
            if key in ("user_name", "default_city"):
                self.data[key] = (value or "").strip()
                self.save()
            elif key in ("music", "app", "website"):
                self.data.setdefault("favorites", {})[key] = (value or "").strip()
                self.save()

    def favorite(self, key: str) -> str:
        try:
            return (self.data.get("favorites", {}).get(key) or "").strip()
        except Exception:
            return ""

    def set_preference(self, key: str, value: str):
        key = re.sub(r"[^a-z0-9 _-]+", "", (key or "").lower()).strip()
        value = str(value or "").strip()[:300]
        if not key or not value:
            return False
        preferences = self.data.setdefault("preferences", {})
        preferences[key] = value
        self.save()
        return True

    def get_preference(self, key: str) -> str:
        try:
            return (self.data.get("preferences", {}).get(
                (key or "").lower().strip(), ""
            ) or "").strip()
        except Exception:
            return ""

    def preferences(self) -> dict:
        try:
            return dict(self.data.get("preferences", {}) or {})
        except Exception:
            return {}

    def forget_preference(self, key: str) -> bool:
        key = (key or "").lower().strip()
        preferences = self.data.setdefault("preferences", {})
        if key not in preferences:
            return False
        preferences.pop(key, None)
        self.save()
        return True

    # ---------- free-form facts ----------
    # "remember that I am afraid of heights" is not a preference, not a name,
    # not a city, and not a favourite anything. It used to be answered with
    # "I'll remember that" and then thrown away, so the assistant lied. These
    # store the sentence as said, and are what that reply now promises.
    MAX_FACTS = 100

    def _fact_list(self) -> list:
        """The facts list, repaired if the stored shape is not a list.

        memory.json is a hand-editable file, so a bad edit ("facts": "oops")
        must not take remembering down with an AttributeError.
        """
        facts = self.data.get("facts")
        if not isinstance(facts, list):
            facts = []
            self.data["facts"] = facts
        return facts

    def add_fact(self, fact: str) -> bool:
        """Remember a free-form fact. True if it was new (not a duplicate)."""
        fact = (fact or "").strip()[:300]
        if not fact:
            return False
        facts = self._fact_list()
        # Case-insensitive dedup, but keep the original spelling of the fact
        # the user actually said ("Dr Rao", not "dr rao").
        if any(str(existing).lower() == fact.lower() for existing in facts):
            return False
        facts.append(fact)
        del facts[:-self.MAX_FACTS]
        self.save()
        return True

    def facts(self) -> list:
        try:
            return [str(f).strip() for f in self._fact_list() if str(f or "").strip()]
        except Exception:
            return []

    def find_facts(self, query: str) -> list:
        """Facts containing any word of *query* (all words must match)."""
        words = [w for w in re.findall(r"[a-z0-9']+", (query or "").lower()) if len(w) > 2]
        if not words:
            return []
        hits = []
        for fact in self.facts():
            lowered = fact.lower()
            if all(word in lowered for word in words):
                hits.append(fact)
        return hits

    def forget_fact(self, query: str) -> int:
        """Drop every fact matching *query*. Returns how many were removed."""
        words = [w for w in re.findall(r"[a-z0-9']+", (query or "").lower()) if len(w) > 2]
        if not words:
            return 0
        facts = self._fact_list()
        kept = [f for f in facts
                if not all(w in str(f).lower() for w in words)]
        removed = len(facts) - len(kept)
        if removed:
            self.data["facts"] = kept
            self.save()
        return removed

    def add_alias(self, nick: str, canonical: str):
        nick = (nick or "").lower().strip()
        canonical = (canonical or "").strip()
        if nick and canonical and nick != canonical.lower():
            self.data.setdefault("aliases", {})[nick] = canonical
            self.save()

    def resolve_alias(self, text: str) -> str:
        """Replace known nicknames inside *text* (word-boundary safe)."""
        try:
            aliases = self.data.get("aliases", {}) or {}
        except Exception:
            return text
        out = text
        for nick, canonical in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
            if not nick:
                continue
            out = re.sub(rf"\b{re.escape(nick)}\b", canonical, out,
                         flags=re.IGNORECASE)
        return out

    def learn_correction(self, heard: str, intended: str):
        heard = (heard or "").lower().strip()
        intended = (intended or "").strip()
        if heard and intended and heard != intended.lower():
            corr = self.data.setdefault("corrections", {})
            corr[heard] = intended
            # cap size
            while len(corr) > 200:
                corr.pop(next(iter(corr)))
            self.save()

    def corrected(self, text: str) -> str:
        try:
            return self.data.get("corrections", {}).get((text or "").lower().strip(), text)
        except Exception:
            return text

    # ---------- history / context ----------
    def remember(self, cmd: str, reply: str = "", ok: bool = True):
        cmd = (cmd or "").strip()
        if not cmd:
            return
        with self._lock:
            entry = {"cmd": cmd[:200], "ok": bool(ok), "ts": time.time()}
            hist = self.data.setdefault("history", [])
            hist.append(entry)
            del hist[:-50]
            self.data["last"] = {"cmd": cmd[:200], "reply": (reply or "")[:500],
                                 "ts": time.time()}
        # usage counting by first two words (cheap intent key)
        key = " ".join(cmd.lower().split()[:2])
        usage = self.data.setdefault("usage", {})
        usage[key] = int(usage.get(key, 0)) + 1
        # auto-learn favorites from repeated patterns
        self._auto_learn(cmd)
        self.save()

    def last_command(self) -> str:
        try:
            return self.data.get("last", {}).get("cmd", "") or ""
        except Exception:
            return ""

    def recent(self, n: int = 8) -> list[str]:
        try:
            return [e.get("cmd", "") for e in self.data.get("history", [])[-n:]]
        except Exception:
            return []

    def _auto_learn(self, cmd: str):
        low = cmd.lower()
        m = re.match(r"^play\s+(.+)$", low)
        if m and m.group(1).strip() not in ("music", "song", "songs", "something", "a song", "some music"):
            # most-played query becomes the music favorite (skip the generic
            # "play music" request, which used to be saved as the favorite)
            fav = self.favorite("music")
            if not fav:
                self.data.setdefault("favorites", {})["music"] = m.group(1).strip()
        m = re.search(r"weather(?:.*?(?:in|at|for)\s+(.+))?$", low)
        if m and m.group(1):
            city = m.group(1).strip(" ?!.")
            if city and not self.default_city:
                self.data["default_city"] = city

    # ---------- proactive ----------
    def suggestion(self) -> str:
        """A short proactive hint based on time + usage. '' when nothing useful."""
        try:
            import datetime as _dt
            hour = _dt.datetime.now().hour
            usage = self.data.get("usage", {}) or {}
            if 5 <= hour < 12 and usage.get("play", 0) == 0 and len(self.data.get("history", [])) < 5:
                return "Try 'play lofi beats' to start your morning"
            if hour >= 18 and "weather" not in usage:
                city = self.default_city or "your city"
                return f"Ask 'what's the weather in {city}' before heading out"
            # most-used intent nudge
            if usage:
                top = max(usage, key=lambda k: usage[k])
                if usage[top] >= 5 and top.startswith("open "):
                    return f"You often run '{top}' — pin it as a quick-action chip"
            return ""
        except Exception:
            return ""


_memory: SmartMemory | None = None


def get_memory() -> SmartMemory:
    global _memory
    if _memory is None:
        _memory = SmartMemory()
    return _memory
