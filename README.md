# Voice Assistant / Ninja

A Linux desktop voice assistant that listens for commands, opens apps, controls the desktop, browses the web, and speaks responses back to you.

This project is centered around `ninja.py`, which runs the assistant in GUI, terminal, or text mode. The logic is split into a lightweight command router and skill modules for browser, desktop, system, and input automation.

## Features

- Voice command processing with wake-word or continuous listening modes
- App launching and window management
- Browser automation for web pages and searches
- Mouse and keyboard control
- System actions like volume, brightness, screenshots, and shutdown confirmation
- Timers and reminders
- Weather, time, and general info queries
- Optional AI fallback for more natural language requests
- GTK-based HUD for desktop interaction

## Project Structure

```text
.
├── ninja.py                 # Main entry point
├── jarvis.py                # Compatibility alias
├── alexa.py                 # Compatibility alias
├── README.md                # Project documentation
├── requirements.txt         # Python dependencies
├── assistant/
│   ├── __init__.py
│   ├── brain.py             # Command routing and intent handling
│   ├── config.py            # Configuration and environment variables
│   ├── ear.py               # Microphone and speech input handling
│   ├── gui.py               # Desktop HUD interface
│   ├── mouth.py             # Text-to-speech support
│   ├── memory.py            # Memory helpers
│   ├── needle_brain.py      # Optional natural-language brain
│   ├── spark.py             # AI fallback integration
│   ├── worker.py            # Voice/task loop
│   ├── background.py        # Background job handling
│   └── skills/
│       ├── apps.py
│       ├── hypr.py
│       ├── info.py
│       ├── input_control.py
│       ├── reminders.py
│       ├── system_ctl.py
│       ├── web.py
│       └── windows.py
├── honey-rs/                # Legacy Rust prototype archive
└── .venv/                   # Local virtual environment (if created)
```

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

If your system is missing desktop utilities, install them with your package manager.

Example for Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3-pip python3-venv python3-gi xdotool pulseaudio-utils scrot
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
export WAKE_WORDS="ninja"
export WEATHER_CITY="Mumbai"
export SPARK_PROVIDER="auto"
export OPENROUTER_API_KEY="your-key"
```

You can also place these values into a `.env` file in the project root.

## Running the Assistant

Default GUI mode with continuous listening:

```bash
python ninja.py
```

Only respond after hearing the wake word:

```bash
python ninja.py --wake-word
```

Launch without the microphone:

```bash
python ninja.py --no-mic
```

Run voice mode without the GUI:

```bash
python ninja.py --no-gui
```

Terminal text mode:

```bash
python ninja.py --text
```

There are also compatibility aliases:

```bash
python jarvis.py
python alexa.py
```

## Example Commands

- "open youtube and play believer"
- "open whatsapp and text mom hello"
- "volume up"
- "take a screenshot"
- "search google for python tutorials"
- "focus vscode"
- "move mouse to the center"
- "set a timer for 10 minutes"
- "what is the weather in Mumbai"
- "lock screen"
- "shutdown the computer"

## Notes

- Commands are processed by a fast router in `assistant/brain.py` and can fall back to optional local or AI-based natural language systems.
- Destructive actions such as shutdown, restart, and logout require confirmation before execution.
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
