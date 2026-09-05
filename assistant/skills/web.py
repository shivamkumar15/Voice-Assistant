"""Web skill: open sites in Chrome and run searches."""

import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote_plus

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
    browser = _find_browser()
    try:
        if browser is None:
            import webbrowser

            webbrowser.open(url)
        else:
            subprocess.Popen(browser + [url])
        return True, f"Opening {name}"
    except Exception as exc:
        return False, f"Could not open {name}: {exc}"


def google_search(query: str):
    browser = _find_browser()
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        if browser is None:
            import webbrowser

            webbrowser.open(url)
        else:
            subprocess.Popen(browser + [url])
        return True, f"Searching Google for {query}"
    except Exception as exc:
        return False, f"Search failed: {exc}"


def youtube_search(query: str, autoplay: bool = True):
    """Play/search something on YouTube.

    With *autoplay*, the first result's video is opened directly (the watch
    page starts playing on its own) instead of dropping the user on the
    search results — "play X" should mean play, not browse.
    """
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    playing = False
    if autoplay:
        try:
            page = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=8,
            )
            first = re.search(r'"videoId":"([\w-]{11})"', page.text)
            if first:
                url = f"https://www.youtube.com/watch?v={first.group(1)}"
                playing = True
        except requests.RequestException:
            pass  # no network / parse fail — fall back to the results page
    browser = _find_browser()
    try:
        if browser is None:
            import webbrowser

            webbrowser.open(url)
        else:
            subprocess.Popen(browser + [url])
        if playing:
            return True, f"Playing {query} on YouTube"
        return True, f"Searching YouTube for {query}"
    except Exception as exc:
        return False, f"YouTube failed: {exc}"


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
        browser = _find_browser()
        try:
            if browser is None:
                import webbrowser

                webbrowser.open(url)
            else:
                subprocess.Popen(browser + [url])
        except Exception as exc:
            return False, f"Could not open WhatsApp: {exc}"
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
