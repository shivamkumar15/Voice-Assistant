"""Muse Spark 1.3 brain: advanced agentic fallback via OpenRouter.

Meta's Muse Spark 1.3 (meta/muse-spark-1.3) is a 1M-context multimodal
reasoning model tuned for long-running agentic / multi-step assistant
workflows. It improves instruction following and coding efficiency over
1.2 and supports OpenAI-style tool calling, reasoning effort control,
structured output and temperature — all through the OpenRouter
chat-completions API (OpenCode Zen serves the same model behind the
same API shape, so pointing OPENROUTER_BASE_URL at an OpenCode-compatible
gateway just works).

Routing order in brain.py is now:

    regex fast-paths -> local Needle (offline NL) -> Spark agent -> plain chat

Spark is the "advanced" layer: unlike the old single-shot chat fallback
it keeps conversation history, knows every skill, and can *act* — calling
tools (open apps, play music, set timers, check weather, ...) over up to
MAX_STEPS rounds before answering. Replies are cleaned for speech (no
markdown) and kept concise so TTS sounds natural, while still being more
complete than the old 120-token fallback.
"""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime

import requests

from .config import (
    ASSISTANT_NAME,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    SPARK_HISTORY,
    SPARK_MAX_TOKENS,
    SPARK_REASONING_EFFORT,
    SPARK_TEMPERATURE,
    SPARK_TOOLS_ENABLED,
)

MAX_STEPS = 3
_REQUEST_TIMEOUT = 30


class _CreditError(RuntimeError):
    """Raised when OpenRouter says the max_tokens budget exceeds credits."""


def _system_prompt() -> str:
    now = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    return (
        f"You are {ASSISTANT_NAME}, a concise desktop voice assistant running on Linux. "
        f"Current time: {now}. "
        "You control the user's desktop through tools: open apps/websites, play YouTube, "
        "web search, WhatsApp messages, volume/brightness, screenshots, system status, "
        "time/weather/jokes, timers, windows, typing and media keys. "
        "Rules: when the user asks to DO something, call the matching tool instead of "
        "describing it. Never claim an action succeeded without a tool result. "
        "For questions, answer in one or two short spoken-style sentences. "
        "No markdown, no bullet lists, no code fences, no emojis — plain speech. "
        "If a request is destructive (shutdown/restart/logout) or unclear, ask for "
        "clarification instead of acting."
    )


def _tool_defs() -> list:
    """OpenAI-format tool schemas for the skills Spark may call."""
    return [
        {
            "type": "function",
            "function": {
                "name": "open_app_or_site",
                "description": "Open a desktop app or website by name (youtube, github, terminal, vscode, whatsapp).",
                "parameters": {
                    "type": "object",
                    "properties": {"target": {"type": "string", "description": "App or site name"}},
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_on_youtube",
                "description": "Play a song, artist or video on YouTube.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Song/artist/video, verbatim"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search Google and open results.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "whatsapp_send",
                "description": "Send a WhatsApp message (needs logged-in WhatsApp Web).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "contact": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["contact", "message"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_volume",
                "description": "Set speaker volume to an exact percent.",
                "parameters": {
                    "type": "object",
                    "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "change_volume",
                "description": "Turn volume up or down a little.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"]},
                        "step": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    },
                    "required": ["direction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_brightness",
                "description": "Set screen brightness to an exact percent.",
                "parameters": {
                    "type": "object",
                    "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "system_status",
                "description": "Report CPU, memory, disk and battery status.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Say the current clock time.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_weather",
                "description": "Report current weather for a city (or the default).",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "City, if stated"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tell_joke",
                "description": "Tell a short programmer joke.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_timer",
                "description": "Set a countdown timer / reminder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "duration": {"type": "string", "description": "Duration verbatim, e.g. '10 minutes'"},
                        "label": {"type": "string", "description": "Reminder label, if any"},
                    },
                    "required": ["duration"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Take a screenshot (saved to Pictures + clipboard).",
                "parameters": {
                    "type": "object",
                    "properties": {"area": {"type": "boolean", "description": "True to select a region first"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "focus_window",
                "description": "Bring a window to the front by app/title.",
                "parameters": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "Type text into the focused window (explicit dictation only).",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "media_control",
                "description": "Pause/resume, next or previous track.",
                "parameters": {
                    "type": "object",
                    "properties": {"action": {"type": "string", "enum": ["playpause", "next", "previous"]}},
                    "required": ["action"],
                },
            },
        },
    ]


def clean_for_speech(text: str) -> str:
    """Strip markdown/formatting so TTS reads naturally; keep it tight."""
    t = (text or "").strip()
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)  # code fences
    t = re.sub(r"`([^`]*)`", r"\1", t)  # inline code
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)  # bold
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?m)^\s*#{1,6}\s*", "", t)  # headings
    t = re.sub(r"(?m)^\s*[-*•]\s+", "", t)  # bullets
    t = re.sub(r"(?m)^\s*\d+[.)]\s+", "", t)  # numbered lists
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # links
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    # Spoken replies should stay short; GUI still shows the full text via
    # the same string, so cap generously (better output, still speakable).
    if len(t) > 1200:
        cut = t[:1200]
        dot = cut.rfind(". ")
        t = (cut[: dot + 1] if dot > 600 else cut.rstrip() + "…")
    return t or "I have nothing to say about that."


class SparkBrain:
    """Muse Spark 1.3 agentic client with history + tool loop."""

    def __init__(self):
        self.available = bool(OPENROUTER_API_KEY)
        self.model = OPENROUTER_MODEL
        self.history: deque = deque(maxlen=max(2, SPARK_HISTORY))
        if not self.available:
            print("[spark] no OPENROUTER_API_KEY — Spark brain disabled (regex + Needle only)")

    # -- public API ------------------------------------------------------

    def handle(self, text: str) -> tuple[bool, str]:
        """Try Spark; (False, '') when unavailable/error so callers fall back."""
        ok, reply = self.ask(text)
        if not ok:
            return False, ""
        return True, reply

    def ask(self, prompt: str) -> tuple[bool, str]:
        if not self.available:
            return False, ""
        prompt = (prompt or "").strip()
        if not prompt:
            return False, ""
        messages: list = [{"role": "system", "content": _system_prompt()}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": prompt})
        # (budget, use_tools) attempts: full agentic first, then smaller,
        # then chat-only for low-credit / prompt-limit accounts where the
        # ~1k tool schemas don't fit the free-tier prompt allowance.
        # Each budget is tried with tools AND chat-only: tools can blow the
        # prompt allowance while chat-only at the same budget fits.
        attempts: list[tuple[int, bool]] = []
        for budget in [SPARK_MAX_TOKENS, 250, 200, 150, 80]:
            if budget > SPARK_MAX_TOKENS or budget < 40:
                continue
            attempts.append((budget, True))
            attempts.append((budget, False))
        # de-dup while keeping order
        seen, ordered = set(), []
        for item in attempts:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        last_error = ""
        for budget, use_tools in ordered:
            if use_tools and not SPARK_TOOLS_ENABLED:
                continue
            try:
                ok, reply = self._ask_with_budget(prompt, list(messages), budget,
                                                  use_tools=use_tools)
                if ok:
                    return True, reply
                if reply:  # actionable error (e.g. truncated) — remember it
                    last_error = reply
                continue
            except _CreditError as exc:
                last_error = str(exc)
                mode = "tools" if use_tools else "chat"
                print(f"[spark] {mode} budget {budget} rejected ({exc}) — retrying")
                continue
            except requests.RequestException as exc:
                return False, f"My AI brain is unreachable right now. ({exc})"
            except Exception as exc:
                print(f"[spark] error: {exc}")
                return False, ""
        return False, (
            f"The AI service said: {last_error}" if last_error
            else "My AI brain is unreachable right now."
        )

    def _ask_with_budget(self, prompt: str, messages: list, budget: int,
                         use_tools: bool | None = None) -> tuple[bool, str]:
        tool_results: list[str] = []
        if use_tools is None:
            use_tools = SPARK_TOOLS_ENABLED and budget >= 150
        for _ in range(MAX_STEPS + 1):
            data = self._call(messages, tools=use_tools, max_tokens=budget)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            finish = choice.get("finish_reason") or choice.get("native_finish_reason")
            content = ((msg.get("content") or "") or "").strip()
            calls = msg.get("tool_calls") or []
            if not calls:
                if content:
                    reply = clean_for_speech(content)
                    self._remember(prompt, reply)
                    return True, reply
                if tool_results:
                    reply = clean_for_speech(". ".join(tool_results))
                    self._remember(prompt, reply)
                    return True, reply
                if (finish or "") == "length":
                    # Reasoning ate the whole budget — no room left to answer.
                    return False, (
                        "My answer got cut off by the token budget. "
                        "Try raising SPARK_MAX_TOKENS or lowering "
                        "SPARK_REASONING_EFFORT."
                    )
                return False, ""
            # Execute tool calls, feed results back for a grounded reply.
            messages.append(msg)
            for call in calls:
                fn = (call.get("function") or {})
                name = fn.get("name") or ""
                args = self._parse_args(fn.get("arguments"))
                result = self._execute_tool(name, args)
                tool_results.append(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or name,
                    "name": name,
                    "content": result[:2000],
                })
        final = ". ".join(tool_results) if tool_results else ""
        if not final:
            return False, ""
        reply = clean_for_speech(final)
        self._remember(prompt, reply)
        return True, reply

    def reset(self):
        self.history.clear()

    # -- internals -------------------------------------------------------

    def _remember(self, prompt: str, reply: str):
        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": reply})

    @staticmethod
    def _parse_args(raw) -> dict:
        import json as _json

        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = _json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _call(self, messages: list, tools: bool, max_tokens: int | None = None) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": SPARK_TEMPERATURE,
            "max_tokens": max_tokens or SPARK_MAX_TOKENS,
        }
        if tools:
            payload["tools"] = _tool_defs()
            payload["tool_choice"] = "auto"
        if SPARK_REASONING_EFFORT:
            # OpenRouter reasoning control for reasoning models like Spark.
            payload["reasoning"] = {"effort": SPARK_REASONING_EFFORT}
        resp = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/ninja-assistant",
                "X-Title": f"{ASSISTANT_NAME} desktop assistant",
            },
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        try:
            data = resp.json()
        except Exception:
            data = {}
        if not resp.ok:
            msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
            msg = (msg or f"HTTP {resp.status_code}") or ""
            lowered = msg.lower()
            if "insufficient credits" in lowered or "never purchased" in lowered:
                raise RuntimeError(msg)  # fail fast — no budget will cover this
            if ("more credits" in lowered or "fewer max_tokens" in lowered
                    or "prompt tokens limit" in lowered or "token limit" in lowered
                    or "context length" in lowered or "max_tokens" in lowered
                    and "afford" in lowered):
                raise _CreditError(msg)
            raise RuntimeError(msg)
        return data

    def _execute_tool(self, name: str, args: dict) -> str:
        """Run one model-requested tool against local skills."""
        try:
            from .skills import apps, info, input_control, reminders, system_ctl, web, windows

            if name == "open_app_or_site":
                target = str(args.get("target") or "").strip()
                if apps.desktop_available(target):
                    _, reply = apps.launch_app(target)
                elif web.find_site(target):
                    _, reply = web.open_website(target)
                else:
                    _, reply = apps.launch_app(target)
                return reply
            if name == "play_on_youtube":
                _, reply = web.play_query(str(args.get("query") or ""))
                return reply
            if name == "web_search":
                _, reply = web.google_search(str(args.get("query") or ""))
                return reply
            if name == "whatsapp_send":
                _, reply = web.whatsapp_send(
                    str(args.get("contact") or ""), str(args.get("message") or ""))
                return reply
            if name == "set_volume":
                _, reply = system_ctl.volume_set(int(args.get("level", 50)))
                return reply
            if name == "change_volume":
                direction = "up" if str(args.get("direction")) == "up" else "down"
                step = int(args.get("step") or 10)
                _, reply = system_ctl.volume_up(step) if direction == "up" else system_ctl.volume_down(step)
                return reply
            if name == "set_brightness":
                _, reply = system_ctl.brightness_set(int(args.get("level", 50)))
                return reply
            if name == "system_status":
                _, reply = system_ctl.system_status()
                return reply
            if name == "get_time":
                _, reply = info.get_time()
                return reply
            if name == "check_weather":
                _, reply = info.get_weather(str(args.get("city") or ""))
                return reply
            if name == "tell_joke":
                _, reply = info.tell_joke()
                return reply
            if name == "set_timer":
                secs, extra = reminders.parse_duration(str(args.get("duration") or ""))
                if secs is None:
                    return f"I couldn't read the duration '{args.get('duration')}'"
                label = str(args.get("label") or "") or extra or "timer"
                _, reply = reminders.set_timer(secs, label)
                return reply
            if name == "take_screenshot":
                _, reply = system_ctl.screenshot(bool(args.get("area")))
                return reply
            if name == "focus_window":
                _, reply = windows.focus_window(str(args.get("title") or ""))
                return reply
            if name == "type_text":
                _, reply = input_control.type_text(str(args.get("text") or ""))
                return reply
            if name == "media_control":
                action = str(args.get("action") or "playpause")
                if action not in ("playpause", "next", "previous"):
                    action = "playpause"
                _, reply = system_ctl.media_key(action)
                return reply
            return f"Unknown tool {name}"
        except Exception as exc:
            return f"That didn't work: {exc}"

    # -- diagnostics -----------------------------------------------------

    def status(self) -> str:
        if not self.available:
            return "Spark brain is disabled (set OPENROUTER_API_KEY to enable it)"
        tools = "with tools" if SPARK_TOOLS_ENABLED else "chat only"
        hist = f"{len(self.history)//2} exchanges remembered"
        return (
            f"Muse Spark 1.3 ({self.model}, {tools}, {hist}). "
            f"Reasoning effort: {SPARK_REASONING_EFFORT or 'default'}."
        )


# Shared singleton so history persists across Brain instances.
_shared: SparkBrain | None = None


def get_spark() -> SparkBrain:
    global _shared
    if _shared is None:
        _shared = SparkBrain()
    # Re-check availability in case env was set after first import.
    if not _shared.available and OPENROUTER_API_KEY:
        _shared.available = True
    return _shared


def wait_ready(timeout: float = 0.0) -> bool:
    """Trivial readiness probe (API is remote; returns availability)."""
    _ = timeout
    return bool(OPENROUTER_API_KEY)


def legacy_chat(prompt: str) -> tuple[bool, str]:
    """Original single-shot chat (used when Spark tools are disabled/fail)."""
    if not OPENROUTER_API_KEY:
        return False, (
            "That's not a command I know yet. Try: open youtube, play song, "
            "volume up,"
        )
    budgets = []
    for cand in (SPARK_MAX_TOKENS, 250, 200, 150, 80):
        if cand <= SPARK_MAX_TOKENS and cand >= 40 and cand not in budgets:
            budgets.append(cand)
    last_msg = ""
    for budget in budgets:
        try:
            t0 = time.monotonic()
            payload: dict = {
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"You are {ASSISTANT_NAME}, a concise desktop voice "
                            "assistant. Answer in one or two short spoken-style "
                            "sentences. No markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": budget,
                "temperature": SPARK_TEMPERATURE,
            }
            if SPARK_REASONING_EFFORT:
                payload["reasoning"] = {"effort": SPARK_REASONING_EFFORT}
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/ninja-assistant",
                    "X-Title": f"{ASSISTANT_NAME} desktop assistant",
                },
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            data = response.json()
            if response.ok:
                choice = (data.get("choices") or [{}])[0]
                choice_msg = (choice.get("message") or {})
                text = ((choice_msg.get("content") or "") or "").strip()
                if text:
                    ms = int((time.monotonic() - t0) * 1000)
                    print(f"[spark] chat answered in {ms}ms (budget {budget})")
                    return True, clean_for_speech(text)
                finish = choice.get("finish_reason") or ""
                if finish == "length":
                    last_msg = ("My answer got cut off by the token budget. "
                                "Try raising SPARK_MAX_TOKENS.")
                    continue
                return False, "I have nothing to say about that."
            message = data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            last_msg = message
            lowered = message.lower()
            if "insufficient credits" in lowered or "never purchased" in lowered:
                return False, f"The AI service said: {message}"
            retryable = ("more credits" in lowered or "fewer max_tokens" in lowered
                         or "prompt tokens limit" in lowered or "token limit" in lowered)
            if not retryable:
                return False, f"The AI service said: {message}"
            print(f"[spark] budget {budget} too high — retrying smaller")
        except requests.RequestException as exc:
            return False, f"My AI brain is unreachable right now. ({exc})"
    return False, f"The AI service said: {last_msg}"
