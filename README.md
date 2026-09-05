# NINJA 🥷 — Your Personal Desktop Voice Assistant

An always-listening, HUD-style assistant that lives on your desktop.
It listens **continuously** — just speak, no wake word needed — and it
actually does the thing:

> *"open YouTube and play believer"* → Chrome opens YouTube and plays it
> *"open whatsapp and text mom hello"* → WhatsApp Web opens and sends it
> *"volume up" · "take a screenshot" · "what's the weather in Mumbai"*

Chain any tasks in one breath with **and** / **then**: *"visit github and
find ninjas and scroll down"*. Saying **"Ninja"** before a phrase guarantees
an answer; background chatter that isn't a command is silently ignored
(and in continuous mode, quit words only count with the wake word, so stray
chatter can't shut it down).

The window is a full N.I.N.J.A HUD: core-reactor status, live system monitor,
weather card, activity log, terminal, conversation panel, satellite/uplink
telemetry and a bottom command bar — like the reference mockup.

## How it works

```
 you speak ──► ear.py (mic + speech recognition)
                   │ wake word "ninja"
                   ▼
               brain.py ── routes the intent
                   │
                   ├─ regex fast-paths ──► exact commands ("volume up")
                   │
                   ├─ needle_brain.py ──► Needle 2, a local 45M tool-calling
                   │     model (offline, ~28MB RAM) that understands natural
                   │     phrasing and calls the same skills — confidence-gated
                   │     before anything executes
                   │
                   ├─ skills/
                   │   ├─ web.py          open sites / search / play songs
                   │   ├─ apps.py         launch & quit applications
                   │   ├─ windows.py      stash / maximise / focus / list windows
                   │   ├─ system_ctl.py   volume · brightness · screenshots · power · status
                   │   ├─ input_control.py type · press · click · scroll · mouse move/drag
                   │   ├─ reminders.py      timers & reminders with voice alerts
                   │   ├─ hypr.py         Hyprland (Wayland) compositor helpers
                   │   └─ info.py         time · date · weather · jokes · AI chat
                   │
                   └─ info.chat (OpenRouter) ── free-form questions, last resort
                   │
                   ▼
              mouth.py (text-to-speech reply)  +  NINJA HUD (gui.py)
```

## Features

- 🎙️ **Continuous listening** — no wake word needed; every phrase is heard,
  commands run instantly, chatter is ignored (use `--wake-word` for strict mode)
- 🔗 **Chained multi-step tasks** — "open youtube and play believer",
  "open whatsapp and text mom hello", "visit github then find ninjas"
- 💬 **WhatsApp messaging** — "message mom hello", "whatsapp dad call me back"
  (names via WhatsApp Web search, numbers go direct via wa.me)
- 🔍 **Page interaction** — "find cats" (Ctrl+F), "scroll down", "click",
  "comment nice video on this post"
- 🥷 **NINJA HUD** — core integrity reactor, acoustic-scan radar, CPU/disk/memory
  monitor, weather card, activity feed, terminal, conversation, net/uptime graphs
- 🖱️ **Full mouse control by voice** — "move mouse left/right/up/down",
  "move mouse to the center / top right / bottom left", "move mouse to 500, 300",
  "where's the mouse", "click", "right click", "double click", "scroll up/down",
  "drag mouse left"
- 🌐 **Websites in Chrome** — "open youtube", "open gmail", "search google for rust tutorials"
- ▶️ **Play anything** — "play lofi beats" opens YouTube results instantly
- 🚀 **Desktop apps** — "open whatsapp / telegram / terminal / vscode / files",
  with distro-aware fallbacks (kitty→gnome-terminal, telegram-desktop→telegram)
  plus flatpak support; "focus X" auto-launches X when it isn't running;
  desktop app preferred over the website when installed
- ⏲️ **Timers & reminders** — "set a timer for 10 minutes", "remind me to call
  mom in 20 minutes" (voice + desktop notification when they fire)
- 📻 **Radios & desktop bits** — "turn wifi off", "switch bluetooth on",
  "read my clipboard", "empty the trash"
- 🪟 **Windows & workspaces** — "focus / minimise / maximise <app>",
  "list windows", "show desktop", "go to workspace 2", "move this window to
  workspace 3", "next workspace" (Hyprland + X11)
- 🔊 **Volume, mic & media** — volume up/down/set 40%, mute, "mute mic", pause/next track (MPRIS)
- ☀️ **Brightness** — "brightness up", "dim the screen", "set brightness to 60"
- 📸 **Screenshots** — full screen or "screenshot of the area" (grim + slurp), saved to `~/Pictures` and copied to the clipboard
- 💻 **System control** — battery/CPU/memory reports, lock screen, sleep/suspend, log out, shutdown/restart (all destructive actions ask first)
- ⌨️ **Input automation** — "type hello world", "press enter", "copy", "scroll down", "click", "move mouse right"
- 🕒 **Info** — time, date, weather via wttr.in (no API key needed), jokes
- 🧠 **Natural-language brain (Needle 2, on-device)** — you don't have to say the
  magic words. "could you open github for me", "skip this song", "swap to
  workspace four", "message Priya saying I'll be late" all work:
  [Needle](https://github.com/cactus-compute/needle) is a 45M-parameter
  tool-calling model that runs fully offline (14MB engine, ~28MB RAM) and maps
  natural phrasing onto the skills above. Its 46 tools are split across 12 small
  domain agents (the shape the model is trained on) with a keyword router in
  front; every call is gated on a calibrated confidence score *before* it
  executes, and phrases heard in the background (no wake word) need a stricter
  score so overheard chatter can't drive the desktop. Anything below the gate —
  or refused as off-topic — falls back to the regex brain and AI chat. Mic mute
  and shutdown/restart/logout stay regex-only (with the spoken yes/no
  confirmation), so the model can never reach them.
- 🤖 **Optional AI brain** — set `OPENROUTER_API_KEY` and anything unmatched goes to your OpenRouter model (`stealth/ox-alpha` by default)
- 🌊 **Wayland-native** — on Hyprland everything (typing, clicking, mouse moves, window control, screenshots) works through `hyprctl` and `ydotool`, not just XWayland windows

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
export NEEDLE_ENABLED=0                        # disable the local NL brain (regex-only)
export NEEDLE_CONFIDENCE=0.5                   # min confidence before Needle acts (0..1)
export NEEDLE_CHATTER_CONFIDENCE=0.8           # stricter bar for background (no wake word) phrases
export NEEDLE_WEIGHTS="my_needle.cact"         # run a fine-tuned Needle archive
export NEEDLE_TELEMETRY=0                      # opt out of Needle's anonymous usage stats
export ASSISTANT_NAME="Ninja"        # rename the assistant (default: Ninja)
export WAKE_WORDS="ninja"            # custom wake words
export WEATHER_CITY_DEFAULT="Mumbai" # default city for "what's the weather"
```

## Run

```bash
# Full experience: NINJA HUD + continuous listening (default)
.venv/bin/python ninja.py

# Strict mode: only respond after hearing "Ninja"
.venv/bin/python ninja.py --wake-word

# HUD window without the microphone (typed commands only)
.venv/bin/python ninja.py --no-mic

# Every phrase is a command (explicit; same as default)
.venv/bin/python ninja.py --no-wake

# Voice without the HUD window (terminal output)
.venv/bin/python ninja.py --no-gui

# Terminal-only text mode (no window, no microphone)
.venv/bin/python ninja.py --text
```

(`jarvis.py` and `alexa.py` remain as compatibility aliases for `ninja.py`.)

Say **"exit"**, **"quit"**, or **"goodbye"** to stop.

## Example commands

| Say this | What happens |
|---|---|
| "open youtube and play shape of you" | YouTube opens and the song plays |
| "open whatsapp and text mom hello" | WhatsApp Web opens and sends the message |
| "message mom hello" / "whatsapp dad call me back" | Message someone on WhatsApp |
| "visit github then find ninjas" | Opens GitHub and finds text on the page |
| "comment nice video on this post" | Types the comment and submits it |
| "open terminal" / "open whatsapp" / "open telegram" | Real desktop apps launch (or web fallback) |
| "focus vscode" | Switches to it, launches it if closed |
| "go to 1st workspace" / "switch to workspace 2" | Jump between desktops |
| "move this window to workspace 3" / "next workspace" | Organize windows |
| "set a timer for 10 minutes" / "remind me to call mom in 20 minutes" | Voice + popup when due |
| "turn wifi off" / "switch bluetooth on" | Radio control |
| "read my clipboard" / "empty the trash" | Desktop bits |
| "ninja search google for python asyncio" | Google search results |
| "ninja open vscode" | VS Code launches |
| "ninja close chrome" | Chrome windows close gracefully |
| "ninja switch to chrome" / "focus firefox" | Focus a running window |
| "ninja minimise" / "maximise" / "show desktop" | Window management |
| "ninja restore my windows" | Bring stashed windows back (Hyprland) |
| "ninja list windows" | Speaks the open window titles |
| "ninja volume up" / "set volume to 30" | PipeWire/PulseAudio control |
| "ninja mute mic" | Toggle the microphone |
| "ninja brightness up" / "set brightness to 60" | Screen backlight control |
| "ninja take a screenshot" / "screenshot of the area" | Saved to ~/Pictures + clipboard |
| "ninja type hello world" / "press enter" | Real keystrokes into the focused window |
| "ninja move mouse right" / "move mouse to the center" / "move mouse to 500, 300" | Mouse movement |
| "ninja click" / "right click" / "double click" / "scroll down" / "drag mouse left" | Mouse buttons |
| "ninja where's the mouse" | Speaks cursor coordinates |
| "ninja what's the weather in delhi" | Live wttr.in report |
| "ninja system status" | CPU / memory / disk / battery |
| "ninja lock screen" / "sleep" / "log out" / "shutdown the computer" | Session control (confirm) |
| "ninja tell me a joke" | Programmer humour |

## Notes

- The Needle brain is **additive**: exact commands still hit the instant regex
  paths first, and anything Needle refuses or scores below the confidence gate
  falls through to the regex brain and the optional OpenRouter chat. Setting
  `NEEDLE_ENABLED=0` restores the pre-Needle behavior entirely.
- Needle's calibration depends on the CPU: on this machine its own validation
  suites pass with the production confidence gate but refuse less reliably than
  published, which is why the gates default conservative and destructive
  actions (shutdown/restart/logout, mic mute) are kept away from the model.
  If Needle ever acts on background chatter, raise `NEEDLE_CHATTER_CONFIDENCE`.

- Some laptops boot with the internal mic boost maxed out (+30dB), which makes the mic nothing but noise — the assistant tones it down automatically at every startup.
- Speech recognition uses Google's free web service, so an internet connection is required for voice input; TTS works offline via eSpeak.
- The HUD uses GTK3 (`python3-gi`, preinstalled on GNOME). Without it the assistant still runs voice-only in the terminal.
- On Hyprland the assistant controls the desktop through `hyprctl` and `ydotool` (uinput), so native Wayland windows are fully supported. On other Wayland desktops some tools (xdotool/pyautogui) only affect XWayland windows, and everything degrades to a spoken "couldn't do that" instead of crashing.
- "Minimise" on Hyprland stashes windows in a special workspace called `assistant` — "restore my windows" toggles it back.
- The old Python prototype and its Windows-only paths were removed — everything here runs natively on Linux (macOS/Windows app launching is supported where noted). A legacy Rust edition remains archived under [`honey-rs/`](honey-rs).
- ⚠️ An old commit of this repo once contained a hardcoded Gemini API key in `config.py`. That file is gone, but revoke/rotate that key in Google AI Studio if you ever used it. Keep your OpenRouter key out of the code — always export it as an environment variable.
