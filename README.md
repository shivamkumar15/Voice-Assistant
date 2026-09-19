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
                   │
                   ▼
           worker.py ── voice/text loop, wake-word + exit handling
                   │
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
                    └─ info.chat (Muse Spark 1.3) ── agentic fallback: history,
                       tool calls (acts, doesn't just talk), speech-cleaned
                       replies; auto-retries smaller budgets on low credits
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
- 🔊 **Real playback** — "play believer" opens the video itself (autoplays),
  "play song" / "play music" resumes what's paused or starts a top-hits mix,
  "search lofi on youtube" still gives the results page; pause/next/previous
  target every registered player, with a global media-key fallback when none
  are open
- 📡 **WiFi & radios** — "turn wifi off", "switch bluetooth on" (via
  `nmcli` / `bluetoothctl` / `rfkill` when available)
- 📻 **Desktop bits** — "read my clipboard", "empty the trash"
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
- 🤖 **Muse Spark 1.3 brain (agentic)** — set `OPENROUTER_API_KEY` and anything
  unmatched goes to `meta/muse-spark-1.3` (1M context, reasoning + tool calls).
  Unlike a plain chatbot it keeps conversation history (follow-ups work:
  *"what did I just ask you?"*), can *act* via 16 tools (open apps, play
  music, volume, timers, screenshots, …) over multiple steps, and replies are
  cleaned for speech (no markdown read aloud). Same API shape as
  OpenCode-compatible gateways, so `OPENROUTER_BASE_URL` can point at either.
  It auto-retries smaller token budgets on low-credit accounts and tells you
  plainly when credits run out. `spark status` shows model/tools/history;
  `clear chat history` resets it.
- 🏃 **Background commands** — append *"in background"* / *"in parallel"* to any
  command and it runs on a thread pool without blocking voice or the HUD:
  *"check weather in background"*, *"run ls -la in background"* (raw shell
  works too: `run <shell command> in background`). Manage with *"list jobs"*,
  *"check job 1"*, *"cancel job 2"*, *"clear jobs"* — completion is spoken and
  shown in the HUD.
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

Optional environment variables (or put them in a `.env` file in the
project root — `assistant/config.py` loads it automatically):

```bash
export OPENROUTER_API_KEY="sk-or-..."          # enables the Muse Spark 1.3 brain
export OPENROUTER_MODEL="meta/muse-spark-1.3"  # default; any OpenRouter model id
export SPARK_REASONING_EFFORT="minimal"        # minimal/low/medium/high/max (default: minimal)
export SPARK_MAX_TOKENS="200"                  # completion budget (auto-retries smaller)
export SPARK_TEMPERATURE="0.4"                 # answer randomness
export SPARK_HISTORY="12"                      # conversation turns remembered
export SPARK_TOOLS_ENABLED="1"                 # 0 = chat-only, 1 = Spark can act via tools
export BACKGROUND_MAX_WORKERS="4"              # background job threads
export BACKGROUND_SHELL_TIMEOUT="120"          # seconds per background shell command
export NEEDLE_ENABLED=0                        # disable the local NL brain (regex-only)
export NEEDLE_CONFIDENCE=0.5                   # min confidence before Needle acts (0..1)
export NEEDLE_CHATTER_CONFIDENCE=0.8           # stricter bar for background (no wake word) phrases
export NEEDLE_WEIGHTS="my_needle.cact"         # run a fine-tuned Needle archive
export ASSISTANT_NAME="Ninja"        # rename the assistant (default: Ninja)
export WAKE_WORDS="ninja"            # custom wake words, comma-separated
export WEATHER_CITY="Mumbai"         # default city for "what's the weather"
export TTS_PIPER_VOICE_NAME="en_GB-alan-medium"  # Piper voice (see rhasspy/piper-voices)
export TTS_PIPER_VOICE="/path/to/voice.onnx"    # ...or an explicit voice file
export TTS_PIPER_LENGTH_SCALE="0.95"            # <1 = faster speech
export PIPER_VOICE_DIR="~/.local/share/piper/voices"  # where voices are cached
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

Say **"exit"**, **"quit"**, **"goodbye"**, or **"bye bye"** to stop
(in continuous voice mode, address it — e.g. *"ninja exit"* — so stray
chatter can't shut it down).

## Project structure

```
ninja.py               entry point (HUD + voice / terminal / text modes)
jarvis.py / alexa.py   compatibility aliases for ninja.py
assistant/
  ear.py               microphone capture + speech recognition
  worker.py            voice/text loop, wake-word + exit handling
  brain.py             regex command router + chained commands
  needle_brain.py      local Needle 2 NL brain (12 domain agents, 46 tools)
  mouth.py             Piper neural TTS (eSpeak fallback)
  gui.py               N.I.N.J.A HUD window (GTK3)
  config.py            env vars + .env loading
  skills/              web · apps · windows · system_ctl · input_control
                       reminders · hypr (Hyprland) · info
honey-rs/              archived legacy Rust edition
```

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
| "list timers" / "cancel timers" / "cancel timer 2" | Manage running timers & reminders |
| "open the file ~/notes/todo.txt" | Open a file with its default app |
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
| "check weather in background" / "run ls -la in background" | Runs without blocking; reports when done |
| "list jobs" / "check job 1" / "cancel job 2" | Manage background jobs |
| "spark status" / "clear chat history" | Muse Spark model, tools & memory diagnostics |
| "ninja lock screen" / "sleep" / "log out" / "shutdown the computer" | Session control (confirm) |
| "ninja tell me a joke" | Programmer humour |

## Notes

- The Needle brain is **additive**: exact commands still hit the instant regex
  paths first, and anything Needle refuses or scores below the confidence gate
  falls through to the regex brain and the Muse Spark 1.3 agent. Setting
  `NEEDLE_ENABLED=0` restores the pre-Needle behavior entirely (regex → Spark).
- Needle's calibration depends on the CPU: on this machine its own validation
  suites pass with the production confidence gate but refuse less reliably than
  published, which is why the gates default conservative and destructive
  actions (shutdown/restart/logout, mic mute) are kept away from the model.
  If Needle ever acts on background chatter, raise `NEEDLE_CHATTER_CONFIDENCE`.

- The HUD weather card defaults to Quezon City (`CITY_DEFAULT` in
  `assistant/gui.py`); the spoken "what's the weather" reply without a city
  uses `WEATHER_CITY` (and otherwise asks which city).
- Some laptops boot with the internal mic boost maxed out (+30dB), which makes the mic nothing but noise — the assistant tones it down automatically at every startup (and re-checks periodically, since PipeWire can restore it mid-session). It also raises a near-muted capture source back to a usable level.
- Speech recognition uses Google's free web service, so an internet connection is required for voice input. Replies speak through **Piper** neural TTS (a natural British voice, downloaded once on first use into `~/.local/share/piper/voices`; set `TTS_PIPER_VOICE_NAME` or `TTS_PIPER_VOICE` to choose another from rhasspy/piper-voices) and fall back to eSpeak if Piper is unavailable.
- The HUD uses GTK3 (`python3-gi`, preinstalled on GNOME). Without it the assistant still runs voice-only in the terminal.
- On Hyprland the assistant controls the desktop through `hyprctl` and `ydotool` (uinput), so native Wayland windows are fully supported. On other Wayland desktops some tools (xdotool/pyautogui) only affect XWayland windows, and everything degrades to a spoken "couldn't do that" instead of crashing.
- "Minimise" on Hyprland stashes windows in a special workspace called `assistant` — "restore my windows" toggles it back.
- The old Python prototype and its Windows-only paths were removed — everything here runs natively on Linux (macOS/Windows app launching is supported where noted). A legacy Rust edition remains archived under [`honey-rs/`](honey-rs).
- ⚠️ An old commit of this repo once contained a hardcoded Gemini API key in `config.py`. That file is gone, but revoke/rotate that key in Google AI Studio if you ever used it. Keep your OpenRouter key out of the code — always export it as an environment variable.
