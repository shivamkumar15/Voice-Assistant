# Honey (Rust edition) 🐝

A full Rust rewrite of the original Python Voice-Assistant: talk to your laptop
and it listens, thinks, and controls your desktop.

- **Speech-to-text**: local Whisper (whisper.cpp) — fully offline, no cloud STT
- **Text-to-speech**: `espeak-ng`
- **Chat brain**: [ox-alpha](https://openrouter.ai) via OpenRouter
- **Desktop control**: Hyprland (`hyprctl` + `ydotool`), xdotool fallback on X11
- **Personality**: emotion engine with moods, energy and relationship score

## Build

```bash
cd ~/Voice-Assistant/honey-rs
cargo build --release
```

Requirements: Rust 1.75+, `alsa-utils` (arecord), `espeak-ng`, `hyprctl`
(Hyprland) or `xdotool` (X11), and `ydotool` for keyboard/mouse automation.

## Run

```bash
./target/release/honey            # voice mode
./target/release/honey --text     # type instead of talking
./target/release/honey --no-tts   # silent mode
```

First voice run downloads the Whisper model (~78 MB) to `~/.cache/honey/`.
Set `HONEY_WHISPER_MODEL=/path/to/ggml-*.bin` to use a different model
(e.g. `ggml-base.en.bin` for better accuracy).

## API keys

Keys are read from the environment or auto-loaded from a `.env` file in the
project directory (never commit yours):

```bash
echo 'OPENROUTER_API_KEY=sk-or-v1-...' > .env
chmod 600 .env
```

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key (chat). Without it, desktop commands still work. |
| `OPENROUTER_MODEL` | Model override (default `stealth/ox-alpha`) |
| `OWM_API_KEY` | OpenWeatherMap key (weather) |
| `OWM_CITY` | Default city (default New York) |
| `HONEY_USER_NAME` | Your name (default Shivam) |
| `HONEY_VAD_THRESHOLD` | Mic silence threshold (default 350) |
| `HONEY_WHISPER_MODEL` | Path to an alternative Whisper model |

## One-time setup

```bash
# keyboard/mouse automation needs the ydotool daemon:
sudo systemctl enable --now ydotoold
```

Make sure your user has permission on `/dev/uinput` (udev rule or `input`
group), otherwise ydotool can't inject keys.

## What you can say

- **Apps**: "open firefox", "launch spotify", "close calculator"
- **Windows**: "list windows", "switch to spotify", "close window chrome", "maximize window kitty"
- **Files**: "find lecture notes", "open file report.pdf", "create folder stuff"
- **Keyboard/mouse**: "copy", "paste", "save", "press enter", "type hello world", "click", "double click", "do copy shortcut"
- **Info**: "system info", "what time is it", "what's the date", "is it the weekend"
- **Weather**: "what's the weather", "weather in london"
- **Chat**: anything else goes to ox-alpha (with Honey's emotion engine)
- **Exit**: "bye" / "goodbye" / "exit" / "quit" / "see you"

## Layout (mirrors the Python original)

| Python | Rust |
|---|---|
| main.py | src/main.rs |
| brain.py | src/brain.rs |
| command_parser.py | src/command_parser.rs |
| desktop_controller.py | src/desktop_controller.rs |
| automation_controller.py | src/automation_controller.rs |
| time_service.py | src/time_service.rs |
| weather_service.py | src/weather_service.rs |
| personality.py / emotion_engine.py | src/personality.rs / src/emotion_engine.rs |
| voice_input.py (Google STT) | src/voice_input.rs (local Whisper) |
| voice_output.py (pyttsx3) | src/voice_output.rs (espeak-ng) |

Not ported: gui.py (customtkinter GUI) and memory.py (unused by the main loop).
