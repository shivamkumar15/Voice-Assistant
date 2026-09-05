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

ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Ninja")


WAKE_WORDS = [w.lower() for w in os.getenv(
    "WAKE_WORDS", "ninja"
).split(",")]

# Note: "shut down" is deliberately NOT an exit phrase — it routes to the
# brain's power commands (which ask for confirmation) instead of quitting.
EXIT_PHRASES = ["exit", "quit", "goodbye", "bye bye"]

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

# Needle (github.com/cactus-compute/needle): a 45M-parameter local
# tool-calling model that maps natural phrases onto the skills the regex
# brain can't match. Inference is fully offline; the 14MB engine is fetched
# once from Hugging Face and cached under ~/.cache/cactus-needle/.
NEEDLE_ENABLED = os.getenv("NEEDLE_ENABLED", "1").lower() not in ("0", "false", "no", "off")
# Minimum calibrated confidence for executing a tool call; weaker matches are
# refused and handed back to the regex brain / AI chat. (Cactus's own
# production contract uses 0.4; we default slightly higher because desktop
# actions can be disruptive.) Raise it if Needle ever acts on background
# chatter, lower it if it feels deaf.
NEEDLE_CONFIDENCE = float(os.getenv("NEEDLE_CONFIDENCE", "0.5"))
# Phrases heard in the background (no wake word, continuous listening) can be
# the TV, a call, or a housemate — Needle only acts on them at this stricter
# confidence, so overheard chatter can't drive the desktop.
NEEDLE_CHATTER_CONFIDENCE = float(os.getenv("NEEDLE_CHATTER_CONFIDENCE", "0.8"))
# Optional tuned .cact archive (needle finetune + build) to run instead of
# the base model.
NEEDLE_WEIGHTS = os.getenv("NEEDLE_WEIGHTS", "")

WEATHER_CITY_DEFAULT = os.getenv("WEATHER_CITY", "")
