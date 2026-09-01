"""Central configuration for the desktop assistant."""

import os
from pathlib import Path


def _load_dotenv():
    """Load key=value pairs from a .env file next to the project (no deps)."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


_load_dotenv()

ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Alexa")


WAKE_WORDS = [w.lower() for w in os.getenv(
    "WAKE_WORDS", "alexa,alex,lexa,lexi"
).split(",")]

EXIT_PHRASES = ["exit", "quit", "goodbye", "shut down", "shutdown", "bye bye"]

TTS_RATE = int(os.getenv("TTS_RATE", "175"))
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "1.0"))
TTS_VOICE_HINT = os.getenv("TTS_VOICE_HINT", "english")  # espeak voice filter

MIC_DEVICE_INDEX = None        
PHRASE_TIME_LIMIT = 8           
LISTEN_TIMEOUT = 6               
FOLLOWUP_TIMEOUT = 12            


BROWSER_CANDIDATES = {
    "linux": [
        "google-chrome-stable", "google-chrome", "chromium-browser",
        "chromium", "brave-browser", "microsoft-edge", "firefox",
    ],
    "darwin": ["Google Chrome", "Safari"],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
}

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "stealth/ox-alpha")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

WEATHER_CITY_DEFAULT = os.getenv("WEATHER_CITY", "")
