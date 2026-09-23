"""Web skill: open sites in Chrome and run searches."""

import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote, quote_plus

import requests

from ..config import BROWSER_CANDIDATES
from . import apps

# Spoken name -> URL
SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "github": "https://github.com",
    "git hub": "https://github.com",
    "chat gpt": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "prime video": "https://www.primevideo.com",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "linkedin": "https://www.linkedin.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "wikipedia": "https://www.wikipedia.org",
    "spotify": "https://open.spotify.com",
    "hotstar": "https://www.hotstar.com",
    "twitch": "https://www.twitch.tv",
}

_browser_cmd = None


def _find_browser():
    global _browser_cmd
    if _browser_cmd is not None:
        return _browser_cmd

    key = sys.platform
    candidates = BROWSER_CANDIDATES.get("win32" if key.startswith("win") else key, [])
    if key == "darwin":
        for name in candidates:
            if shutil.which(f'/Applications/{name}.app/Contents/MacOS/{name}') or True:
                _browser_cmd = ["open", "-a", name]
                return _browser_cmd
    else:
        for candidate in candidates:
            path = shutil.which(candidate)
            if path:
                _browser_cmd = [path]
                return _browser_cmd
            # Windows-style absolute paths
            import os

            if os.path.isfile(candidate):
                _browser_cmd = [candidate]
                return _browser_cmd
    return None


def _launch_url(url: str) -> bool:
    """Open *url* detached from the assistant, trying each browser in turn.

    Previous code Popen'd a single cached browser binary with no
    detachment. If that binary was broken (e.g. Chrome renderer SIGILL on
    some hybrid-GPU setups) the song never played and repeated launches
    stacked heavy renderer processes until the session froze. Trying
    every candidate + a stdlib fallback, detached, avoids both failure
    modes.
    """
    candidates: list[list[str]] = []
    key = sys.platform
    raw = BROWSER_CANDIDATES.get("win32" if key.startswith("win") else key, [])
    for candidate in raw:
        path = shutil.which(candidate)
        if path:
            # --new-tab reuses a running Chrome instead of spawning a
            # whole new window/process tree for every song.
            if "chrome" in os.path.basename(path) or "chromium" in os.path.basename(path):
                candidates.append([path, "--new-tab", url])
            else:
                candidates.append([path, url])
        elif os.path.isfile(candidate):
            candidates.append([candidate, url])
    # Cached single-browser path kept as a last resort before webbrowser.
    browser = _find_browser()
    if browser is not None:
        candidates.append(browser + [url])
    for cmd in candidates:
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    try:
        import webbrowser

        webbrowser.open(url)
        return True
    except Exception:
        return False


_mpv_proc = None


def _stop_previous_audio():
    """Stop a previous mpv song so 'play X' never stacks audio processes.

    Stacked mpvs each decode + resample + hold a PipeWire stream; on a
    busy laptop that is how 'play a few songs' turns into 100% CPU,
    audio underruns and an apparent full-system freeze. Tracks our own
    mpv handle first (won't kill the user's own mpv), pkill only as a
    fallback for mpvs orphaned by older versions.
    """
    global _mpv_proc
    if _mpv_proc is not None:
        try:
            if _mpv_proc.poll() is None:
                _mpv_proc.terminate()
                try:
                    _mpv_proc.wait(timeout=3)
                except subprocess.SubprocessError:
                    _mpv_proc.kill()
        except OSError:
            pass
        _mpv_proc = None
    if shutil.which("pkill"):
        try:
            subprocess.run(
                ["pkill", "-f", "mpv --no-video --really-quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception:
            pass


def _play_audio_url(url: str) -> bool:
    """Play *url* audio-only via mpv (lightweight). False when unavailable."""
    global _mpv_proc
    mpv = shutil.which("mpv")
    if not mpv:
        return False
    _stop_previous_audio()
    try:
        _mpv_proc = subprocess.Popen(
            [mpv, "--no-video", "--really-quiet", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        _mpv_proc = None
        return False


def stop_playback() -> tuple[bool, str]:
    """Stop the current song (for 'pause'/'stop' handling)."""
    _stop_previous_audio()
    from . import system_ctl

    # Also pause any browser/MPRIS player so 'stop' silences everything.
    system_ctl.media_key("playpause")
    return True, "Stopped"


def find_site(query: str):
    """Match a spoken phrase to a known site. Returns (name, url) or None."""
    q = query.lower().strip()
    if not q:
        return None
    if q in SITES:
        return q, SITES[q]
    for name in sorted(SITES, key=len, reverse=True):
        if len(name) <= 2 and q != name:
            continue  # never fuzzy-match tiny names ("x" lives in "chrome")
        if name in q:
            return name, SITES[name]
    if q.endswith(".com") or q.endswith(".org") or q.endswith(".in"):
        url = q if q.startswith("http") else f"https://{q}"
        return q, url
    return None


def open_website(query: str):
    """Open a website by friendly name in the preferred browser."""
    hit = find_site(query)
    if not hit:
        return False, f"I don't know the site {query}"
    name, url = hit
    if _launch_url(url):
        return True, f"Opening {name}"
    return False, f"Could not open {name}"


def google_search(query: str):
    if not (query or "").strip():
        return False, "What should I search for?"
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    if _launch_url(url):
        return True, f"Searching Google for {query}"
    return False, "Search failed: no browser available"


def steam_search(query: str):
    query = (query or "").strip()
    if not query:
        return False, "Which game should I open?"
    url = f"https://store.steampowered.com/search/?term={quote_plus(query)}"
    if not _launch_url(url):
        return False, "I couldn't open Steam"
    return True, f"Searching Steam for {query}"


def youtube_search(query: str, autoplay: bool = True):
    """Play/search something on YouTube.

    With *autoplay*, the first result's video is played audio-only via mpv
    (lightweight: ~50MB, no GPU, no renderer to crash the session) instead
    of opening a full Chrome window per song. The browser is only a
    fallback when mpv is missing/fails, or when autoplay=False (the user
    asked to *search*, not play).
    """
    query = (query or "").strip()
    if not query:
        return False, "What should I play?"
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    watch_url = ""
    if autoplay:
        try:
            page = requests.get(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=8,
            )
            page.raise_for_status()
            first = re.search(r'"videoId":"([\w-]{11})"', page.text)
            if first:
                watch_url = f"https://www.youtube.com/watch?v={first.group(1)}"
        except requests.RequestException:
            pass  # no network / parse fail — fall back below
        if watch_url and _play_audio_url(watch_url):
            return True, f"Playing {query} on YouTube"
        # mpv missing or failed: fall back to the browser so *something*
        # still plays instead of silence.
        if _launch_url(watch_url or search_url):
            return True, f"Playing {query} on YouTube"
        return False, "YouTube failed: no player or browser available"
    if _launch_url(search_url):
        return True, f"Searching YouTube for {query}"
    return False, "YouTube failed: no browser available"


# Generic "play music" style requests — the user wants *music*, not a video
# literally called "song" or "music".
_GENERIC_PLAY = frozenset({
    "music", "some music", "a song", "the song", "song", "songs",
    "some songs", "that song", "something", "anything", "my playlist",
    "a playlist", "some tunes", "tunes", "a track", "tracks",
})


def play_query(query: str):
    """Handle a "play ..." request: named content plays on YouTube; a
    generic request resumes paused media or starts a default mix."""
    if (query or "").strip().lower() in _GENERIC_PLAY:
        from . import system_ctl

        state = system_ctl.media_state()
        if state == "paused":
            return system_ctl.media_key("playpause")
        if state == "playing":
            return True, "Already playing"
        return youtube_search("top hits mix")
    return youtube_search((query or "").strip())


def email_draft(recipient: str, message: str, subject: str = ""):
    """Open a connected email client with a prefilled draft for review."""
    recipient = (recipient or "").strip()
    message = (message or "").strip()
    if not recipient or not message:
        return False, "Tell me who to email and what to say"
    url = (
        f"mailto:{quote(recipient)}"
        f"?subject={quote_plus(subject.strip())}"
        f"&body={quote_plus(message)}"
    )
    if not _launch_url(url):
        return False, "I couldn't open an email client"
    return True, f"Opened an email draft to {recipient}; review it and press send"


def whatsapp_send(person: str, message: str):
    """Message someone on WhatsApp Web: open chat, type, send.

    Phone numbers go straight to the chat via wa.me; names are looked up
    through WhatsApp Web's chat search (Ctrl+K). Best effort throughout —
    the page needs a logged-in WhatsApp Web session.
    """
    from . import input_control

    person = (person or "").strip()
    message = (message or "").strip()
    if not person or not message:
        return False, "Tell me who to message and what to say"

    # Phone numbers skip the search step entirely.
    digits = re.sub(r"[^\d]", "", person)
    if digits and len(digits) >= 7 and len(re.sub(r"[\d+ ]", "", person)) == 0:
        url = f"https://wa.me/{digits}?text={quote_plus(message)}"
        if not _launch_url(url):
            return False, "Could not open WhatsApp"
        time.sleep(6)  # let the chat load
        input_control.press_key("enter")  # send the prefilled message
        return True, f"Sent to {person} on WhatsApp"

    if apps.desktop_available("whatsapp"):
        # Real desktop app installed — drive that instead of the browser.
        apps.launch_app("whatsapp")
        time.sleep(4)  # let the app come up
        try:
            from . import windows

            windows.focus_window("whatsapp")  # make sure keys land in it
            time.sleep(0.6)
        except Exception:
            pass
    else:
        ok, _ = open_website("whatsapp")
        if not ok:
            return False, "I couldn't open WhatsApp Web"
        time.sleep(6)  # let WhatsApp Web load
    input_control.press_key("escape")
    time.sleep(0.4)
    input_control.hotkey("control k")  # focus chat search
    time.sleep(0.6)
    input_control.type_text(person)
    time.sleep(1.5)
    input_control.press_key("enter")  # open the chat
    time.sleep(1.0)
    input_control.type_text(message)
    time.sleep(0.4)
    input_control.press_key("enter")  # send
    return True, f"Sent to {person} on WhatsApp"
