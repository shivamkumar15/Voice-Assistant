# Voice Assistant / Ninja

A terminalo based voice assistant that listens for commands, opens apps, controls the desktop, browses the web, and speaks responses back to you.

This project is centered around `ninja.py`, which runs the assistant in GUI, terminal, or text mode. The logic is split into a lightweight command router and skill modules for browser, desktop, system, and input automation.

## Features

- Voice command processing with wake-word or continuous listening modes
- Local offline speech recognition with OpenAI Whisper (`faster-whisper`), no API key
- App launching and window management
- Browser automation for web pages and searches
- Mouse and keyboard control
- System actions like volume, brightness, screenshots, and shutdown confirmation
- Timers, reminders, and bounded resource monitoring
- Weather, time, notifications, and general info queries
- Safe local file and document workflows: find, read, summarize, create, move, rename, and delete
- Multi-step study workflows such as finding the latest PDF and creating a study plan
- Git status/history/diff, confirmed commits and sync, and bounded code execution
- Best-effort screen OCR, browser form filling, email drafts, and game search
- Persistent preferences, aliases, and multi-step command memory
- Optional AI fallback for more natural language requests
- GTK-based HUD for desktop interaction

## Requirements

- Python 3.10+
- Linux desktop environment
- Microphone and speakers
- Optional: GTK for the GUI dashboard
- Optional: system utilities such as `hyprctl`, `ydotool`, `grim`, `slurp`, `playerctl`, `brightnessctl`, and `nmcli` depending on the commands you use

## Installation

Create and activate a virtual environment:

```bash
cd /home/dranzer/Voice-Assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The first run downloads the Whisper model (~150MB for `base.en`) to
`~/.cache/ninja-assistant/whisper`, then caches it for later runs. It is
loaded in the background at startup, so the first phrase you speak is not
delayed by it.

If your system is missing desktop utilities, install them with your package manager.

Example for Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3-pip python3-venv python3-gi xdotool pulseaudio-utils scrot poppler-utils tesseract-ocr
```

For Wayland/Hyprland users, common tools include:

```bash
sudo pacman -S ydotool grim slurp wl-clipboard brightnessctl playerctl libpulse
```

## Configuration

The project reads environment variables from a `.env` file if present, or from the shell environment.

Example:

```bash
export ASSISTANT_NAME="Ninja"
export WAKE_WORDS="ninja,aamina"
export WEATHER_CITY="Mumbai"
export ASSISTANT_FILE_ROOTS="$HOME"
export FILE_SEARCH_MAX_DEPTH="5"
export ALLOW_PACKAGE_INSTALL="0"
export SPARK_PROVIDER="auto"
```

You can also place these values into a `.env` file in the project root. `WAKE_WORDS` accepts a comma-separated list; the spoken greeting `Hey Ninja` is recognized automatically.

### Speech recognition

Voice input uses OpenAI Whisper running locally through `faster-whisper`
(CTranslate2). Audio never leaves the machine, no API key is needed, and it
handles accents and jargon better than a keyless cloud endpoint.

| Variable | Default | Purpose |
| --- | --- | --- |
| `STT_PROVIDER` | `auto` | `whisper` (local), `google` (cloud fallback), or `auto` to use Whisper when installed |
| `STT_WHISPER_MODEL` | `base.en` | `tiny.en` / `base.en` / `small.en` / `medium.en` / `large-v3`, or a path to a downloaded model |
| `STT_WHISPER_DEVICE` | `auto` | `auto` uses a GPU when one works, else CPU. Force `cpu` to skip the probe |
| `STT_WHISPER_BEAMS` | `5` | Beam width. `1` is fastest, `5` is more accurate |
| `STT_WHISPER_HOTWORDS` | assistant vocabulary | Words pre-primed into the decoder, which is what fixes "works box" → "workspace". Blank to disable |
| `STT_LANGUAGE` | `en-US` | Accent hint, e.g. `en-IN` |

Notes:

- `base.en` is the default for a reason: on short commands it matched `small.en` while running about 3x faster, and the larger model occasionally spoke a primed hotword that was never said. Raise to `small.en` only if you use long or unusual vocabulary.
- GPU use needs `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` on some setups. The startup line says which device it actually chose; if the GPU probe fails it silently falls back to CPU `int8`, which is still faster than real time for short commands.
- If `faster-whisper` is not installed, or the model cannot be loaded, the assistant falls back to the keyless Google endpoint and says so in the terminal.

## Running the Assistant

Default GUI mode with continuous listening:

```bash
python ninja.py
```

Only respond after hearing the wake word:

```bash
python ninja.py --wake-word
```


Run voice mode without the GUI:

```bash
python ninja.py --no-gui
```

Terminal text mode:

```bash
python ninja.py --text
```

## Example Commands

- "open youtube and play believer"
- "open whatsapp and text mom hello"
- "volume up"
- "take a screenshot"
- "search google for python tutorials"
- "focus vscode"
- "got this navbar and to about us page"
- "set a timer for 10 minutes"
- "what is the weather in Haryana"
- "lock screen"
- "shutdown the computer"
- "open my CS folder, find the latest PDF, summarize it and create a study plan"
- "find the latest assignment in Documents and read it"
- "create a file named notes.txt"
- "git status", "git diff", "git commit with message update parser"
- "monitor system for 5 minutes"
- "read notifications"
- "what's on my screen"
- "fill the form with name Aamina and email aamina@example.com"

## Notes

- Commands are processed by a fast router in `assistant/brain.py` and can fall back to optional local or AI-based natural language systems.
- Destructive actions such as shutdown, restart, and logout require confirmation before execution.
- Local file access is restricted to `ASSISTANT_FILE_ROOTS` and sensitive credential folders are blocked. Deleting files, replacing files, installing packages, running code, and Git commit/push/pull require confirmation.
- PDF extraction uses `pdftotext` when available and falls back to `pypdf` if installed. Screen reading uses `tesseract` when available.
- Form filling is keyboard-based and expects the browser form to already be focused; review the form before submitting.
- The project is designed primarily for Linux desktop use, with Hyprland/Wayland support and X11 fallbacks.
- The `honey-rs` directory contains an older Rust prototype and is not the main runtime path.

## Development Notes

This codebase is best treated as a personal desktop automation platform rather than a generic library. It contains command routing, desktop automation, browser interaction, speech I/O, and optional AI enhancements.

If you want to extend the assistant, the most likely extension points are:

- `assistant/skills/` for new commands and actions
- `assistant/brain.py` for new routing logic
- `assistant/config.py` for environment-driven behavior
- `assistant/gui.py` for the visual HUD

## License

This project does not currently include a license file. If you are using or distributing it, add a license explicitly before sharing it publicly.
