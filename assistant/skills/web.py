"""Web skill: open sites in Chrome and run searches."""

import shutil
import subprocess
import sys
from urllib.parse import quote_plus

from ..config import BROWSER_CANDIDATES

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


def youtube_search(query: str):
    """Play/search something on YouTube."""
    browser = _find_browser()
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    try:
        if browser is None:
            import webbrowser

            webbrowser.open(url)
        else:
            subprocess.Popen(browser + [url])
        return True, f"Playing {query} on YouTube"
    except Exception as exc:
        return False, f"YouTube failed: {exc}"
