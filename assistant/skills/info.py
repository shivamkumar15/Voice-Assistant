"""Info skill: time, date, weather, jokes, identity, AI chat fallback."""

import random
from datetime import datetime

import requests

from ..config import (
    ASSISTANT_NAME,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
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
        f"I'm {ASSISTANT_NAME}, your desktop assistant. I can open apps and "
        "websites, type and click for you, move and close windows, change "
        "volume and brightness, take screenshots, control music, lock or "
        "sleep the computer, and answer questions. Just say my name followed "
        "by a command."
    )


def chat(prompt: str):
    """OpenRouter fallback for anything that isn't a known command (optional)."""
    if not OPENROUTER_API_KEY:
        return False, (
            "That's not a command I know yet. Try: open youtube, play song , "
            "volume up,"
        )
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
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
                "max_tokens": 120,
            },
            timeout=20,
        )
        data = response.json()
        if response.ok:
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if text:
                return True, text
            return False, "I have nothing to say about that."
        message = data.get("error", {}).get("message") or f"HTTP {response.status_code}"
        return False, f"The AI service said: {message}"
    except requests.RequestException as exc:
        return False, f"My AI brain is unreachable right now. ({exc})"
