# Alexa 🗣️ — Your Personal Desktop Voice Assistant

An always-listening, Alexa-style assistant that lives on your desktop.
Say **"Alexa"** followed by a command and it actually does the thing:

> *"Alexa, open YouTube"* → Google Chrome launches straight to youtube.com
> *"Alexa, play believer"* → YouTube plays it
> *"Alexa, volume up" · "Alexa, take a screenshot" · "Alexa, what's the weather in Mumbai"*

## How it works

```
 you speak ──► ear.py (mic + speech recognition)
                   │ wake word "alexa"
                   ▼
               brain.py ── routes the intent ──► skills/
                                                  ├─ web.py          open sites / search / play songs
                                                  ├─ apps.py         launch & quit applications
                                                  ├─ windows.py      minimise / maximise / focus windows
                                                  ├─ system_ctl.py   volume · screenshots · power · status
                                                  ├─ input_control.py type · press · click · scroll
                                                  └─ info.py         time · date · weather · jokes · AI chat
                   │
                   ▼
              mouth.py (text-to-speech reply)  +  chat window GUI (gui.py)
```

## Features

- 🎙️ **Wake-word activation** — stays quiet until it hears "Alexa" (customisable)
- 🌐 **Websites in Chrome** — "open youtube", "open gmail", "search google for rust tutorials"
- ▶️ **Play anything** — "play lofi beats" opens YouTube results instantly
- 🚀 **Apps** — "open chrome / vscode / terminal / calculator", "close firefox"
- 🪟 **Windows** — minimise, maximise, focus, list, show desktop
- 🔊 **Volume & media** — volume up/down/set 40%, mute, pause/next track
- 📸 **Screenshots** — saved to `~/Pictures`
- 💻 **System control** — battery/CPU/memory reports, lock screen, shutdown/restart (with confirmation)
- ⌨️ **Input automation** — "type hello world", "press enter", "copy", "scroll down", "click"
- 🕒 **Info** — time, date, weather via wttr.in (no API key needed), jokes
- 🤖 **Optional AI brain** — set `OPENROUTER_API_KEY` and anything unmatched goes to your OpenRouter model (`stealth/ox-alpha` by default)
- 🖥️ **Proper chat GUI** — a full chat window: live transcript with bubbles, text input, quick-command buttons, mic & voice-reply toggles, and a Listening / Working / Speaking status light

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Linux system packages used automatically when present: `xdotool`, `pactl`/`amixer`,
`gnome-screenshot`/`scrot`. On Debian/Ubuntu: `sudo apt install xdotool pulseaudio-utils`.

Optional environment variables:

```bash
export OPENROUTER_API_KEY="sk-or-..."          # enables AI chat fallback
export OPENROUTER_MODEL="stealth/ox-alpha"     # any OpenRouter model id
export ASSISTANT_NAME="Jarvis"       # rename the assistant
export WAKE_WORDS="jarvis,jarves"    # custom wake words
export WEATHER_CITY_DEFAULT="Mumbai" # default city for "what's the weather"
```

## Run

```bash
# Full experience: chat window + wake-word voice
.venv/bin/python alexa.py

# Chat window without the microphone (typed commands only)
.venv/bin/python alexa.py --no-mic

# Every phrase is a command (no wake word needed)
.venv/bin/python alexa.py --no-wake

# Voice without the chat window (terminal output)
.venv/bin/python alexa.py --no-gui

# Terminal-only text mode (no window, no microphone)
.venv/bin/python alexa.py --text
```

Say **"exit"**, **"quit"**, or **"goodbye"** to stop.

## Example commands

| Say this | What happens |
|---|---|
| "alexa open youtube" | Chrome opens youtube.com |
| "alexa play shape of you" | YouTube search for the song |
| "alexa search google for python asyncio" | Google search results |
| "alexa open vscode" | VS Code launches |
| "alexa close chrome" | All Chrome processes quit |
| "alexa minimize" / "show desktop" | Window management |
| "alexa volume up" / "set volume to 30" | PulseAudio/ALSA control |
| "alexa take a screenshot" | Saved to ~/Pictures |
| "alexa what's the weather in delhi" | Live wttr.in report |
| "alexa system status" | CPU / memory / disk / battery |
| "alexa lock screen" / "shutdown the computer" | Session control (confirm) |
| "alexa tell me a joke" | Programmer humour |

## Notes

- Speech recognition uses Google's free web service, so an internet connection is required for voice input; TTS works offline via eSpeak.
- The chat window uses GTK3 (`python3-gi`, preinstalled on GNOME). Without it the assistant still runs voice-only in the terminal.
- On GNOME-Wayland sessions some window tools (xdotool/pyautogui) only affect XWayland windows, and silent screenshots may be sandboxed — everything degrades to a spoken "couldn't do that" instead of crashing.
- The old Python prototype and its Windows-only paths were removed — everything here runs natively on Linux (macOS/Windows app launching is supported where noted). A legacy Rust edition remains archived under [`honey-rs/`](honey-rs).
- ⚠️ An old commit of this repo once contained a hardcoded Gemini API key in `config.py`. That file is gone, but revoke/rotate that key in Google AI Studio if you ever used it. Keep your OpenRouter key out of the code — always export it as an environment variable.
