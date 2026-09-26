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


WAKE_WORDS = [
    word.strip().lower()
    for word in os.getenv("WAKE_WORDS", "ninja").split(",")
    if word.strip()
] or ["ninja"]

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

# Speech-to-text language (e.g. "en-US", "en-IN", "en-PH"). If the assistant
# constantly mishears accented words, set this to your English variant — it
# makes a big difference for words like "workspace". Google uses the full
# BCP-47 tag; Whisper only the "en" part, which ear.py derives from this.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-US")

# --- Local Whisper (faster-whisper / CTranslate2) ---------------------------
# OpenAI Whisper running fully on-device: no API key, no audio leaves the
# machine, and it hears accents, jargon and "workspace"-style words far more
# reliably than the keyless Google endpoint.
# "auto" (default): Whisper when faster-whisper is installed, else Google.
# "whisper": Whisper only. "google": Google Web Speech only.
STT_PROVIDER = os.getenv("STT_PROVIDER", "auto").strip().lower()
# Size name from faster-whisper: tiny.en / base.en / small.en / medium.en /
# large-v3, or an absolute path to a downloaded model. base.en is the
# accuracy/latency sweet spot; small.en is better on jargon, tiny.en is for
# slow CPUs.
STT_WHISPER_MODEL = os.getenv("STT_WHISPER_MODEL", "base.en")
# "auto" uses CUDA when a usable GPU is present and falls back to CPU.
STT_WHISPER_DEVICE = os.getenv("STT_WHISPER_DEVICE", "auto").strip().lower()
# "auto" picks float16 on GPU and int8 on CPU (int8 roughly doubles CPU
# speed for a barely noticeable accuracy loss on short commands).
STT_WHISPER_COMPUTE_TYPE = os.getenv("STT_WHISPER_COMPUTE_TYPE", "auto").strip().lower()
# Beam width. 1 is fastest, 5 (faster-whisper's default) is more accurate.
STT_WHISPER_BEAMS = max(1, int(os.getenv("STT_WHISPER_BEAMS", "5")))
# Vocabulary pre-priming: the words below are ones Whisper mangles in a
# desktop-assistant context ("works box" -> "workspace"). Measured against
# base.en this fixed "workspace", "vscode" and "haryana", all of which
# base.en got wrong unprimed.
# Keep it short. A long list biases the decoder toward saying those words at
# all, which is how a primed list turns "what is the weather" into
# "whatsapp weather" on a larger model.
# Blank to disable. Comma separated, so quote it in .env.
STT_WHISPER_HOTWORDS = os.getenv(
    "STT_WHISPER_HOTWORDS",
    "workspace, workspaces, vscode, bluetooth, brightness, screenshot, "
    "clipboard, notifications, timer, haryana",
)
# Where the Whisper model is downloaded and cached (fetched on first run).
STT_WHISPER_MODEL_DIR = Path(os.getenv(
    "STT_WHISPER_MODEL_DIR",
    str(Path.home() / ".cache" / "ninja-assistant" / "whisper"),
))


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
# --- Muse Spark 1.3 provider ----------------------------------------------
# "auto" (default): use the local OpenCode CLI's free Contributor tier when
# the `opencode` binary is installed, otherwise OpenRouter.
# "opencode": always the free tier via CLI. "openrouter": always OpenRouter.
SPARK_PROVIDER = os.getenv("SPARK_PROVIDER", "auto").strip().lower()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta/muse-spark-1.3")

# Free tier: Muse Spark 1.3 Contributor (Meta may use prompts/completions
# to train future models). It is locked to "within OpenCode" use, so Ninja
# shells out to the local `opencode run` CLI — no API key needed, just
# `opencode` installed + logged in (same setup this repo's opencode uses).
OPENCODE_MODEL = os.getenv(
    "OPENCODE_MODEL", "opencode/muse-spark-1.3-contributor-free")
OPENCODE_BIN = os.getenv("OPENCODE_BIN", "opencode")
OPENCODE_RUN_DIR = Path(os.getenv(
    "OPENCODE_RUN_DIR",
    str(Path.home() / ".local" / "share" / "ninja-assistant" / "opencode-run"),
))
OPENCODE_VARIANT = os.getenv("OPENCODE_VARIANT", "minimal")  # reasoning effort
OPENCODE_RUN_TIMEOUT = int(os.getenv("OPENCODE_RUN_TIMEOUT", "180"))
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

ASSISTANT_FILE_ROOTS = [
    Path(os.path.expandvars(value.strip())).expanduser()
    for value in os.getenv("ASSISTANT_FILE_ROOTS", str(Path.home())).split(os.pathsep)
    if value.strip()
]
FILE_SEARCH_MAX_DEPTH = max(1, int(os.getenv("FILE_SEARCH_MAX_DEPTH", "5")))
FILE_MAX_READ_BYTES = max(1024, int(os.getenv("FILE_MAX_READ_BYTES", "2000000")))
CODE_TIMEOUT = max(1, int(os.getenv("CODE_TIMEOUT", "15")))
CODE_MAX_OUTPUT = max(256, int(os.getenv("CODE_MAX_OUTPUT", "4000")))
ALLOW_PACKAGE_INSTALL = os.getenv("ALLOW_PACKAGE_INSTALL", "0").lower() in (
    "1", "true", "yes", "on",
)
