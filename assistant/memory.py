"""Smart persistent memory for Ninja.

Stores user preferences, aliases, command history and learned corrections
in a small JSON file so the assistant gets smarter over time:

- remembers your name, default city, favourite music, volume defaults
- keeps free-form facts that don't fit a preference ("I'm afraid of heights")
- learns contact/app nicknames ("mom" -> WhatsApp contact, "vscode" -> "code")
- recalls by ranked search, so "about my dentist appointment" still finds
  the stored "my dentist is Dr Rao"
- learns favourites from habit (most-played music, most-opened app/site)
- keeps last ~50 commands for context resolution ("turn it up", "again")
- tracks usage counts for proactive suggestions ("you usually 'open github'
  around now")

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


# "play music"-style requests must never be stored as the favorite — they
# say nothing about what the user actually likes.
_GENERIC_PLAYS = frozenset({
    "music", "song", "songs", "playlist", "something", "a song",
    "some music", "some songs", "something chill", "anything",
})


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
            "play_counts": {},      # "play <query>" request -> times asked
            "open_counts": {},      # "open <target>" request -> times asked
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
                                    "usage", "favorites", "play_counts",
                                    "open_counts"):
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
                # Habit counters are the last bulk worth biting into: keep the
                # most-used entries, drop the long tail of one-off requests.
                for key in ("play_counts", "open_counts"):
                    counts = self.data.get(key) or {}
                    if len(counts) > 40:
                        keep = sorted(counts, key=lambda k: -counts[k])[:20]
                        self.data[key] = {k: counts[k] for k in keep}
                        break
                else:
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
        # Sanitise exactly like set_preference, or "forget my sister's name"
        # would look for "sister's name" and never find "sisters name".
        key = re.sub(r"[^a-z0-9 _-]+", "", (key or "").lower()).strip()
        preferences = self.data.setdefault("preferences", {})
        if key not in preferences:
            for existing in list(preferences):
                if len(key) > 3 and (key in existing or existing in key):
                    key = existing
                    break
            else:
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

    @staticmethod
    def _query_words(query: str) -> list:
        """Content words of a recall query (short filler like "my" dropped).

        Apostrophes are folded away so "sister's" matches a stored
        "sisters name" preference rather than looking like an unknown token.
        """
        return [w.replace("'", "") for w in re.findall(r"[a-z0-9']+",
                                                       (query or "").lower())
                if len(w.replace("'", "")) > 2]

    def find_facts(self, query: str, limit: int = 0) -> list:
        """Facts relevant to *query*, best match first.

        Ranked instead of the old all-words-must-match filter: asking "what
        do you remember about my dentist appointment" used to miss the stored
        "my dentist is Dr Rao on Friday" purely because the word
        "appointment" was never in it. Facts that cover more of the query
        still sort first; a lone short-word overlap ("name", "the") is not
        treated as a match.
        """
        words = self._query_words(query)
        if not words:
            return []
        scored: list[tuple[float, int, str]] = []
        for fact in self.facts():
            # Fold apostrophes the same way the query words were folded, or
            # "sisters" would never match a stored "sister's".
            lowered = fact.lower().replace("'", "")
            matched = [w for w in words if w in lowered]
            if not matched:
                continue
            score = len(matched) / len(words)
            if score < 0.5:
                continue  # too little of the query is actually in this fact
            if len(matched) == 1 and len(matched[0]) < 5:
                continue  # a single vague word is noise, not recall
            scored.append((score, len(matched), fact))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        hits = [fact for _, _, fact in scored]
        return hits[:limit] if limit else hits

    def search(self, query: str, limit: int = 3) -> list:
        """Ranked recall across everything stored about the user.

        One place that answers "what's my X" / "what do you remember about
        X" from facts, preferences, favourites, name, city and aliases, so
        the assistant can't store something and then fail to recall it.
        Returns display-ready phrases ("your wifi password is hunter2"),
        best first; empty when nothing genuinely matches.
        """
        words = self._query_words(query)
        if not words:
            return []
        wset = set(words)
        qlow = (query or "").lower()
        ranked: list[tuple[float, str]] = []

        def add(score: float, phrase: str):
            if phrase:
                ranked.append((score, phrase))

        # Only treat these as the user's own name/city when nothing else is
        # being asked about — "what's my sister's name" must not answer with
        # the user's own name.
        name_q = {"name", "first", "last", "full", "called"}
        city_q = {"city", "home", "town", "live", "living", "based", "from"}
        if self.user_name and "name" in wset and wset <= name_q:
            add(1.0, f"your name is {self.user_name}")
        if self.default_city and (wset & {"city", "home"}) and wset <= city_q:
            add(1.0, f"your city is {self.default_city}")
        favorites = self.data.get("favorites", {}) or {}
        if (wset & {"music", "song", "songs", "playlist", "artist"}) \
                and str(favorites.get("music") or "").strip():
            add(0.9, f"your favorite music is {str(favorites['music']).strip()}")
        if (wset & {"app", "application", "editor"}) \
                and str(favorites.get("app") or "").strip():
            add(0.9, f"your favorite app is {str(favorites['app']).strip()}")
        if (wset & {"website", "site", "webpage"}) \
                and str(favorites.get("website") or "").strip():
            add(0.9, f"your favorite website is {str(favorites['website']).strip()}")
        # "name" and "city" are the words we answer from the dedicated
        # slots above; letting them also drive fuzzy preference matching made
        # "what's my name" drag in "your sister's name is Anya".
        overlap_words = [w for w in words if w not in {"name", "city"}]
        for key, value in self.preferences().items():
            klow = str(key).lower()
            if key in wset or (len(klow) > 3 and klow in qlow):
                add(1.0, f"your {key} is {value}")
                continue
            overlap = sum(1 for w in overlap_words
                          if w in klow or w in str(value).lower())
            if overlap:
                add(0.6 * overlap / len(words), f"your {key} is {value}")
        for fact in self.find_facts(query):
            add(0.8, fact)
        try:
            aliases = dict(self.data.get("aliases", {}) or {})
        except Exception:
            aliases = {}
        for nick, canonical in aliases.items():
            nwords = {w.replace("'", "") for w in
                      re.findall(r"[a-z0-9']+", str(nick).lower())}
            cwords = {w.replace("'", "") for w in
                      re.findall(r"[a-z0-9']+", str(canonical).lower())}
            if wset & (nwords | cwords):
                add(0.7, f"{nick} is {canonical}")

        ranked.sort(key=lambda item: -item[0])
        out: list[str] = []
        seen: set[str] = set()
        for _, phrase in ranked:
            if phrase in seen:
                continue
            seen.add(phrase)
            out.append(phrase)
            if len(out) >= limit:
                break
        return out

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

    def forget_alias(self, nick: str) -> bool:
        """Drop a learned nickname -> canonical mapping. True when found."""
        nick = (nick or "").lower().strip()
        aliases = self.data.setdefault("aliases", {})
        if nick not in aliases:
            # tolerate partial recall ("forget mom" for "mom's number")
            for key in list(aliases):
                if key == nick or (len(nick) > 3 and nick in key):
                    nick = key
                    break
            else:
                return False
        aliases.pop(nick, None)
        self.save()
        return True

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
        low = cmd.lower().strip()
        m = re.match(r"^play\s+(.+)$", low)
        if m:
            query = m.group(1).strip()
            if query and query not in _GENERIC_PLAYS:
                counts = self.data.setdefault("play_counts", {})
                counts[query] = int(counts.get(query, 0)) + 1
                # The most-played request becomes the favourite, so a one-off
                # ("play happy birthday") doesn't lock the slot forever the
                # way first-play-wins used to. Ties keep the earlier pick.
                best = max(counts, key=lambda k: counts[k])
                self.data.setdefault("favorites", {})["music"] = best
        m = re.match(r"^(?:open|go to|launch|visit|start)\s+(.+)$", low)
        if m:
            target = m.group(1).strip()
            # Skip one-off/parametrised targets ("go to workspace 2", "open
            # file notes.txt"): only a genuinely habitual name is worth
            # promoting to "open my app".
            if (target and "workspace" not in target and "my " not in target
                    and "file " not in target and len(target) <= 30
                    and not re.search(r"\d", target)):
                counts = self.data.setdefault("open_counts", {})
                counts[target] = int(counts.get(target, 0)) + 1
                if counts[target] >= 3:
                    self.data.setdefault("favorites", {})["app"] = target
        m = re.search(r"weather(?:.*?(?:in|at|for)\s+(.+))?$", low)
        if m and m.group(1):
            city = m.group(1).strip(" ?!.")
            if city and not self.default_city:
                self.data["default_city"] = city

    # ---------- proactive ----------
    def suggestion(self) -> str:
        """A short proactive hint, '' when nothing useful applies.

        Prefers a real pattern in the history — what this user tends to run
        around this hour and hasn't run yet today — over the hard-coded time
        rules, which are now only fallbacks.
        """
        try:
            import datetime as _dt

            now = _dt.datetime.now()
            hist = self.data.get("history", []) or []
            if len(hist) >= 5:
                def _ts(entry):
                    try:
                        return _dt.datetime.fromtimestamp(float(entry.get("ts")))
                    except Exception:
                        return None

                done_today = set()
                slot_counts: dict[str, int] = {}
                for entry in hist:
                    if not isinstance(entry, dict):
                        continue
                    when = _ts(entry)
                    if when is None:
                        continue
                    key = " ".join(str(entry.get("cmd", "")).lower().split()[:2]).strip()
                    if not key:
                        continue
                    if when.date() == now.date():
                        done_today.add(key)
                    if abs(when.hour - now.hour) <= 1:
                        slot_counts[key] = slot_counts.get(key, 0) + 1
                for key in ("good morning", "good evening", "daily briefing"):
                    done_today.add(key)
                candidates = {k: n for k, n in slot_counts.items()
                              if n >= 2 and k not in done_today}
                if candidates:
                    top = max(candidates, key=lambda k: candidates[k])
                    return f"You usually '{top}' around now"
            usage = self.data.get("usage", {}) or {}
            hour = now.hour
            if 5 <= hour < 12 and usage.get("play", 0) == 0 and len(hist) < 5:
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
