# Honey 🐝 — Voice Assistant

A Python desktop voice assistant with an emotion-driven personality, natural-language
desktop control, and speech in/out. Talk (or type) to your computer and Honey listens,
thinks, and acts.

> **Rust edition:** a full offline rewrite lives in [`honey-rs/`](honey-rs/README.md).

## Features

- 🧠 **AI brain** — Google Gemini (`google-generativeai`) with chat history
- 😊 **Emotion engine** — moods (happy, excited, tired, ...), energy level, relationship score; the AI's system prompt changes with Honey's current mood
- 💬 **Spontaneous thoughts** — Honey occasionally speaks up on its own when idle
- 🖥️ **Desktop control** — natural language commands via regex parsing
  - Apps & windows: open/close/launch apps, minimize/maximize/focus/list windows
  - Files: search, open, create folder
  - Keyboard/mouse automation: type text, press keys, copy/paste/save/undo, click/scroll
  - System info: CPU / memory / disk / battery
- ⏰ **Time service** — time/date queries, greetings by time of day
- 🌦️ **Weather** — OpenWeatherMap-backed weather queries (optional API key)
- 🎤 **Voice** — Google Speech Recognition for input, `pyttsx3` for output
- 🪟 **GUI** — CustomTkinter chat interface with live emotion sidebar and mic toggle

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Terminal loop: listen → think → speak |
| `gui.py` | CustomTkinter GUI app |
| `brain.py` | Gemini chat + command dispatch + sentiment detection |
| `command_parser.py` | Natural-language → action mapping |
| `desktop_controller.py` | App/window/file/system operations |
| `automation_controller.py` | Keyboard & mouse control |
| `emotion_engine.py` | Emotions, energy, relationship score |
| `personality.py` | Prompts, greetings, spontaneous messages |
| `time_service.py` | Time/date/reminders |
| `weather_service.py` | OpenWeatherMap integration |
| `voice_input.py` / `voice_output.py` | Speech recognition / TTS |

## Setup

```bash
pip install -r requirements.txt
```

Set your Gemini API key as an environment variable:

```bash
export GENAI_API_KEY="your-key-here"
```

Optional: set `OWM_API_KEY` for weather support (free key at
[openweathermap.org](https://openweathermap.org)).

> ⚠️ `config.py` currently contains a fallback API key — remove it before committing
> or sharing this repo, and rotate any key that was committed.

## Run

```bash
# GUI mode (chat window with mic toggle)
python gui.py

# Terminal voice mode
python main.py
```

Say "exit", "bye", or "quit" to leave terminal mode.

## Example commands

- "open chrome" · "close firefox" · "list windows"
- "search file report.pdf" · "create folder projects"
- "type hello world" · "press enter" · "copy" · "paste"
- "system info" · "what time is it" · "weather in london"

Anything else is handled as normal chat by Gemini through Honey's personality.
