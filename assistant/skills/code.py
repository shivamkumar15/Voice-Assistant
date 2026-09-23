"""Bounded code writing and execution helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..config import CODE_MAX_OUTPUT, CODE_TIMEOUT
from . import files

_LANGUAGE_SUFFIXES = {
    "python": ".py",
    "python3": ".py",
    "javascript": ".js",
    "js": ".js",
    "node": ".js",
    "bash": ".sh",
    "shell": ".sh",
}


def _workspace() -> Path:
    path = Path.home() / ".local" / "share" / "ninja-assistant" / "code"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _language_name(language: str) -> str:
    value = (language or "python").lower().strip()
    if value in ("python3", "py"):
        return "python"
    if value in ("js", "node"):
        return "javascript"
    if value in ("shell", "sh"):
        return "bash"
    return value if value in ("python", "javascript", "bash") else "python"


def _safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "snippet").strip())
    value = value.strip("._") or "snippet"
    return value[:80]


def write_snippet(language: str, code: str, name: str = ""):
    language_name = _language_name(language)
    suffix = _LANGUAGE_SUFFIXES.get(language_name, ".txt")
    target = _workspace() / f"{_safe_name(name)}{suffix}"
    if target.exists():
        target = _workspace() / (
            f"{target.stem}_{int(time.time())}{target.suffix}"
        )
    try:
        target.write_text(code or "", encoding="utf-8")
        return True, f"Saved code to {target}"
    except OSError as exc:
        return False, f"I couldn't save the code: {exc}"


def _command(language_name: str, path: Path) -> list[str] | None:
    if language_name == "python":
        return [sys.executable, "-I", str(path)]
    if language_name == "javascript":
        node = shutil.which("node")
        return [node, str(path)] if node else None
    if language_name == "bash":
        shell = shutil.which("bash")
        return [shell, str(path)] if shell else None
    return None


def _execute(command: list[str], cwd: Path, timeout: int) -> tuple[bool, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(Path.home()),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
        )
    except subprocess.TimeoutExpired:
        return False, f"Code execution timed out after {timeout} seconds"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"I couldn't run the code: {exc}"
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if len(output) > CODE_MAX_OUTPUT:
        output = output[:CODE_MAX_OUTPUT].rstrip() + "…"
    if result.returncode != 0:
        return False, output or f"Code exited with status {result.returncode}"
    return True, output or "Code finished with no output"


def run_snippet(language: str, code: str, timeout: int = CODE_TIMEOUT):
    language_name = _language_name(language)
    if _command(language_name, Path("snippet")) is None:
        return False, f"{language_name.title()} is not installed"
    suffix = _LANGUAGE_SUFFIXES.get(language_name, ".txt")
    with tempfile.TemporaryDirectory(prefix="ninja-code-") as directory:
        path = Path(directory) / f"snippet{suffix}"
        try:
            path.write_text(code or "", encoding="utf-8")
        except OSError as exc:
            return False, f"I couldn't prepare the code: {exc}"
        command = _command(language_name, path)
        if command is None:
            return False, f"{language_name.title()} is not installed"
        return _execute(command, Path(directory), timeout)


def run_file(path: str, language: str = "", timeout: int = CODE_TIMEOUT):
    try:
        target = files.resolve_path(path, must_exist=True)
    except files.FileOperationError as exc:
        return False, str(exc)
    language_name = _language_name(language or target.suffix.lstrip("."))
    command = _command(language_name, target)
    if command is None:
        return False, f"I don't know how to run {target.suffix or 'that file'}"
    return _execute(command, target.parent, timeout)
