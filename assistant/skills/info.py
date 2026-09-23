"""Info skill: time, date, weather, jokes, identity, AI chat fallback."""

import random
from datetime import datetime

import requests

from ..config import (
    ASSISTANT_NAME,
    OPENROUTER_API_KEY,
    WEATHER_CITY_DEFAULT,
)

_JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "There are only 10 kinds of people: those who understand binary and those who don't.",
    "I told my computer I needed a break, and it said 'no problem, I'll go to sleep'.",
    "Why did the developer go broke? Because he used up all his cache.",
    "A SQL query walks into a bar, goes up to two tables and asks: can I join you?",
]


def get_time():
    now = datetime.now()
    return True, f"It's {now.strftime('%I:%M %p').lstrip('0')}"


def get_date():
    now = datetime.now()
    return True, f"Today is {now.strftime('%A, %d %B %Y')}"


def get_weather(city: str = ""):
    city = city.strip() or WEATHER_CITY_DEFAULT
    if not city:
        return False, "Which city? Say: weather in Mumbai"
    try:
        response = requests.get(
            f"https://wttr.in/{city}?format=%C,+%t,+feels+like+%f,+humidity+%h,+wind+%w",
            timeout=8,
        )
        if response.ok:
            return True, f"Weather in {city.title()}: {response.text.strip()}"
    except requests.RequestException:
        pass
    return False, "I couldn't reach the weather service"


def tell_joke():
    return True, random.choice(_JOKES)


def who_are_you():
    return True, (
        f"I'm {ASSISTANT_NAME}, your desktop assistant. I listen continuously, "
        "so just speak — no wake word needed. Chain tasks with and, like open "
        "YouTube and play a song, or open WhatsApp and text mom hello. I can "
        "open apps and websites, message people on WhatsApp, find text on a "
        "page, comment on posts, set timers and reminders, switch wifi and "
        "bluetooth, read the clipboard, type and click for you, move the mouse by "
        "voice, scroll, drag, manage windows, change volume and brightness, "
        "take screenshots, read local documents, create study plans, manage files "
        "and Git repositories, read recent notifications, fill focused browser forms, "
        "monitor system resources, "
        "control music, lock or sleep the computer, and answer questions, switch "
        "workspaces, and move windows between them."
    )


def chat(prompt: str):
    """Muse Spark 1.3 fallback for anything that isn't a known command.

    Uses the Spark client (free OpenCode CLI tier preferred, OpenRouter
    fallback) with history + speech-cleaned output.
    """
    try:
        from ..spark import get_spark, legacy_chat, spark_available

        if not spark_available():
            return False, (
                "That's not a command I know yet. Try: open youtube, play song , "
                "volume up,"
            )
        spark = get_spark()
        ok, reply = spark.ask(prompt)
        if ok:
            return True, reply
        # spark.ask returns (False, '') on refusal — try legacy once so
        # plain questions still get answered even when tools refuse.
        if not reply:
            return legacy_chat(prompt)
        return False, reply
    except Exception as exc:
        return False, f"My AI brain hit a snag. ({exc})"


def spark_status():
    """Short diagnostics line for 'ai status' / 'spark status' commands."""
    try:
        from ..spark import get_spark

        return True, get_spark().status()
    except Exception as exc:
        return False, f"Spark status unavailable: {exc}"
