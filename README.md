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
                                                  ├─ windows.py      stash / maximise / focus / list windows
                                                  ├─ system_ctl.py   volume · brightness · screenshots · power · status
                                                  ├─ input_control.py type · press · click · scroll · mouse
                                                  ├─ hypr.py         Hyprland (Wayland) compositor helpers
                                                  └─ info.py         time · date · weather · jokes · AI chat
                   │
                   ▼
              mouth.py (text-to-speech reply)  +  chat window GUI (gui.py)
```

## Features

- 🎙️ **Wake-word activation** — stays quiet until it hears "Alexa" (customisable)
- 🌐 **Websites in Chrome** — "open youtube", "open gmail", "search google for rust tutorials"
- ▶️ **Play anything** — "play lofi beats" opens YouTube results instantly
- 🚀 **Apps** — "open chrome / vscode / terminal / calculator", "close firefox" (graceful window close)
- 🪟 **Windows** — "focus / maximise / minimise <app>", "list windows", "show desktop", "restore my windows"
- 🔊 **Volume, mic & media** — volume up/down/set 40%, mute, "mute mic", pause/next track (MPRIS)
- ☀️ **Brightness** — "brightness up", "dim the screen", "set brightness to 60"
- 📸 **Screenshots** — full screen or "screenshot of the area" (grim + slurp), saved to `~/Pictures` and copied to the clipboard
- 💻 **System control** — battery/CPU/memory reports, lock screen, sleep/suspend, log out, shutdown/restart (all destructive actions ask first)
- ⌨️ **Input automation** — "type hello world", "press enter", "copy", "scroll down", "click", "move mouse right"
- 🕒 **Info** — time, date, weather via wttr.in (no API key needed), jokes
- 🤖 **Optional AI brain** — set `OPENROUTER_API_KEY` and anything unmatched goes to your OpenRouter model (`stealth/ox-alpha` by default)
- 🖥️ **Proper chat GUI** — a full chat window: live transcript with bubbles, text input, quick-command buttons, mic & voice-reply toggles, and a Listening / Working / Speaking status light
- 🌊 **Wayland-native** — on Hyprland everything (typing, clicking, window control, screenshots) works through `hyprctl` and `ydotool`, not just XWayland windows

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Linux system packages used automatically when present:

- **Hyprland / Wayland (recommended):** `hyprctl` (ships with Hyprland), `ydotool`
  (typing/clicking — the assistant starts `ydotoold` for you; be in the `input`
  group so `/dev/uinput` is writable), `grim` + `slurp` (screenshots),
  `wl-copy`, `brightnessctl`, `playerctl`, `pactl` (PipeWire/PulseAudio)
  - Arch: `sudo pacman -S ydotool grim slurp wl-clipboard brightnessctl playerctl libpulse`
- **Other desktops (fallbacks):** `xdotool`, `amixer`, `gnome-screenshot`/`scrot`
  - Debian/Ubuntu: `sudo apt install xdotool pulseaudio-utils scrot`

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
| "alexa close chrome" | Chrome windows close gracefully |
| "alexa switch to chrome" / "focus firefox" | Focus a running window |
| "alexa minimise" / "maximise" / "show desktop" | Window management |
| "alexa restore my windows" | Bring stashed windows back (Hyprland) |
| "alexa list windows" | Speaks the open window titles |
| "alexa volume up" / "set volume to 30" | PipeWire/PulseAudio control |
| "alexa mute mic" | Toggle the microphone |
| "alexa brightness up" / "set brightness to 60" | Screen backlight control |
| "alexa take a screenshot" / "screenshot of the area" | Saved to ~/Pictures + clipboard |
| "alexa type hello world" / "press enter" | Real keystrokes into the focused window |
| "alexa move mouse right" / "click" | Mouse control |
| "alexa what's the weather in delhi" | Live wttr.in report |
| "alexa system status" | CPU / memory / disk / battery |
| "alexa lock screen" / "sleep" / "log out" / "shutdown the computer" | Session control (confirm) |
| "alexa tell me a joke" | Programmer humour |

## Notes

- Speech recognition uses Google's free web service, so an internet connection is required for voice input; TTS works offline via eSpeak.
- The chat window uses GTK3 (`python3-gi`, preinstalled on GNOME). Without it the assistant still runs voice-only in the terminal.
- On Hyprland the assistant controls the desktop through `hyprctl` and `ydotool` (uinput), so native Wayland windows are fully supported. On other Wayland desktops some tools (xdotool/pyautogui) only affect XWayland windows, and everything degrades to a spoken "couldn't do that" instead of crashing.
- "Minimise" on Hyprland stashes windows in a special workspace called `assistant` — "restore my windows" toggles it back.
- The old Python prototype and its Windows-only paths were removed — everything here runs natively on Linux (macOS/Windows app launching is supported where noted). A legacy Rust edition remains archived under [`honey-rs/`](honey-rs).
- ⚠️ An old commit of this repo once contained a hardcoded Gemini API key in `config.py`. That file is gone, but revoke/rotate that key in Google AI Studio if you ever used it. Keep your OpenRouter key out of the code — always export it as an environment variable.
