"""Best-effort screenshot OCR for screen context questions."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import system_ctl


def _latest_screenshot(before: float = 0.0) -> Path | None:
    folder = Path.home() / "Pictures"
    if not folder.is_dir():
        return None
    candidates = []
    try:
        for path in folder.glob("screenshot_*.png"):
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= before - 1:
                candidates.append((modified, path))
    except OSError:
        return None
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def read_screen() -> tuple[bool, str]:
    started = time.time()
    ok, message = system_ctl.screenshot(False)
    if not ok:
        return False, message
    image = _latest_screenshot(started)
    if not image:
        return False, f"{message} I couldn't locate the image to read."
    if not shutil.which("tesseract"):
        return False, f"{message} Install tesseract-ocr if you want me to read the screen."
    try:
        result = subprocess.run(
            ["tesseract", str(image), "stdout"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"I captured the screen but couldn't read it: {exc}"
    text = " ".join((result.stdout or "").split())
    if result.returncode != 0 or not text:
        return False, f"I captured the screen, but no readable text was found. {message}"
    if len(text) > 1400:
        text = text[:1397].rstrip() + "…"
    return True, f"The screen says: {text}"
