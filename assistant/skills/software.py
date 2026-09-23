"""Explicit, bounded software installation helpers."""

from __future__ import annotations

import re
import shutil
import subprocess

from ..config import ALLOW_PACKAGE_INSTALL

_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]{0,80}$")


def _run(command: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "The installation timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Installation failed: {exc}"
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if len(output) > 1800:
        output = output[:1797].rstrip() + "…"
    if result.returncode != 0:
        return False, output or f"Installation exited with status {result.returncode}"
    return True, output or "Installation completed."


def install(package: str) -> tuple[bool, str]:
    package = (package or "").strip()
    if not _PACKAGE_RE.fullmatch(package):
        return False, "Tell me one valid software package name"
    if not ALLOW_PACKAGE_INSTALL:
        return False, (
            "Package installation is disabled. Set ALLOW_PACKAGE_INSTALL=1 "
            "and confirm the installation if you want me to do it."
        )
    if shutil.which("flatpak"):
        return _run(["flatpak", "install", "-y", package])
    if shutil.which("pacman"):
        return _run(["pacman", "-S", "--needed", package])
    if shutil.which("dnf"):
        return _run(["dnf", "install", "-y", package])
    if shutil.which("apt-get"):
        if not shutil.which("sudo"):
            return False, "Installing this package needs sudo, which is unavailable"
        return _run(["sudo", "-n", "apt-get", "install", "-y", package])
    if shutil.which("brew"):
        return _run(["brew", "install", package])
    return False, "I couldn't find a supported package manager"
