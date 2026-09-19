"""Central configuration for the desktop assistant."""

import os
from pathlib import Path


def _load_dotenv():
    """Load key=value pairs from .env files (no deps).

    Checks the project root first, then assistant/.env (legacy location) —
    existing installs keep working either way. Real environment variables
    always win (setdefault).
    """
    here = Path(__file__).resolve()
    for env_file in (here.parent.parent / ".env", here.parent / ".env"):
        if not env_file.exists():
            continue
        try:
            text = env_file.read_text()
        except OSError:
            continue
        for line in text.splitlines():
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

# Piper neural TTS (sounds like Jarvis, not a 90s robot). Download a voice
# .onnx(+.json) from huggingface.co/rhasspy/piper-voices and point
# TTS_PIPER_VOICE at it, or `pacman -S piper-bin` / paru -S piper and set
# TTS_PIPER_VOICE_NAME (e.g. "en_US-ryan-high" or "en_GB-alan-medium").
TTS_PIPER_VOICE = os.getenv("TTS_PIPER_VOICE", "")       # path to .onnx
TTS_PIPER_VOICE_NAME = os.getenv("TTS_PIPER_VOICE_NAME", "")
TTS_PIPER_LENGTH_SCALE = os.getenv("TTS_PIPER_LENGTH_SCALE", "")  # <1 = faster

# Where the assistant downloads/looks for Piper voices.
PIPER_VOICE_DIR = Path(os.getenv(
    "PIPER_VOICE_DIR", str(Path.home() / ".local" / "share" / "piper" / "voices")
))

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
# Muse Spark 1.3 — Meta's agentic reasoning model (1M context, tool
# calling). Served on OpenRouter as meta/muse-spark-1.3 and on
# OpenCode-compatible gateways behind the same chat-completions API, so
# OPENROUTER_BASE_URL can point at either. Overrides via OPENROUTER_MODEL.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta/muse-spark-1.3")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# --- Muse Spark 1.3 tuning -------------------------------------------------
# Reasoning effort for Spark ("minimal"/"low"/"medium"/"high"/"max" or "");
# "minimal" is the default because Spark spends the token budget on
# reasoning first — with the default effort even a 150-token budget comes
# back empty (all reasoning, no answer). Higher = smarter but slower and
# hungrier; raise it together with SPARK_MAX_TOKENS when you have credits.
SPARK_REASONING_EFFORT = os.getenv("SPARK_REASONING_EFFORT", "minimal")
SPARK_TEMPERATURE = float(os.getenv("SPARK_TEMPERATURE", "0.4"))
# Completion budget. 200 fits small/free OpenRouter balances and still
# answers (old fallback used 120 and often cut off). Raise to 400+ with
# credits for richer answers; the client auto-retries smaller when the
# balance can't cover the request.
SPARK_MAX_TOKENS = int(os.getenv("SPARK_MAX_TOKENS", "200"))
# Conversation turns remembered (user+assistant pairs) for follow-ups.
SPARK_HISTORY = int(os.getenv("SPARK_HISTORY", "12"))
# When 0, Spark answers chat-only (no tool calls); when 1 (default) it can
# act via tools (open apps, timers, volume, ...).
SPARK_TOOLS_ENABLED = os.getenv("SPARK_TOOLS_ENABLED", "1").lower() not in (
    "0", "false", "no", "off",
)

# --- Background execution --------------------------------------------------
BACKGROUND_MAX_WORKERS = int(os.getenv("BACKGROUND_MAX_WORKERS", "4"))
BACKGROUND_SHELL_TIMEOUT = int(os.getenv("BACKGROUND_SHELL_TIMEOUT", "120"))

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
