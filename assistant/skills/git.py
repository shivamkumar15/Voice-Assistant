"""Safe Git repository inspection and explicit write operations."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import files


def _run(repo: Path, args: list[str], timeout: int = 10) -> tuple[bool, str]:
    if not shutil.which("git"):
        return False, "Git is not installed"
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "The Git command timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Git failed: {exc}"
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if len(output) > 3500:
        output = output[:3497].rstrip() + "…"
    if result.returncode != 0:
        return False, output or "The Git command failed"
    return True, output or "Done"


def find_repo(path: str | Path | None = None) -> tuple[bool, str]:
    try:
        target = files.resolve_path(path or Path.cwd(), must_exist=True, allow_root=True)
    except files.FileOperationError as exc:
        return False, str(exc)
    if target.is_file():
        target = target.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=5,
        )
    except subprocess.TimeoutExpired:
        return False, "The Git repository check timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Git failed: {exc}"
    if result.returncode != 0:
        return False, f"{target} is not inside a Git repository"
    return True, result.stdout.strip()


def _repo(path: str | Path | None) -> tuple[bool, str | Path]:
    ok, value = find_repo(path)
    return ok, value


def status(path: str | Path | None = None) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    success, output = _run(repo, ["status", "--short", "--branch", "--untracked-files=no"])
    if not success:
        return False, output
    return True, output or "The working tree is clean."


def log(path: str | Path | None = None, count: int = 5) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    count = max(1, min(int(count), 20))
    success, output = _run(repo, ["log", f"-{count}", "--oneline", "--decorate"])
    return success, output or "This repository has no commits yet."


def branch(path: str | Path | None = None) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    success, output = _run(repo, ["branch", "--show-current"])
    current = output.strip() if success else "unknown"
    success, all_branches = _run(repo, ["branch", "--format=%(refname:short)"])
    if not success:
        return False, all_branches
    names = [line.strip() for line in all_branches.splitlines() if line.strip()]
    return True, f"Current branch: {current or 'detached'}. Branches: " + ", ".join(names[:12])


def diff(path: str | Path | None = None, staged: bool = False) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    args = ["diff", "--stat"] if not staged else ["diff", "--cached", "--stat"]
    success, output = _run(repo, args)
    return success, output or "No changes."


def stage(path: str | Path | None, target: str = ".") -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    target = (target or ".").strip()
    if target.startswith("-"):
        return False, "Tell me which repository file to stage"
    success, output = _run(repo, ["add", "--", target])
    return success, output or f"Staged {target}."


def commit(path: str | Path | None, message: str) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    message = (message or "").strip()
    if not message:
        return False, "What commit message should I use?"
    success, output = _run(repo, ["commit", "-m", message])
    return success, output or "Commit created."


def sync(path: str | Path | None, pull: bool = False) -> tuple[bool, str]:
    ok, repo = _repo(path)
    if not ok:
        return False, str(repo)
    command = "pull" if pull else "push"
    success, output = _run(repo, [command], timeout=60)
    return success, output or f"Git {command} completed."


def action(name: str, path: str | Path | None = None, value: str = "") -> tuple[bool, str]:
    name = (name or "").lower().strip()
    if name in ("state", "status"):
        return status(path)
    if name in ("log", "history"):
        return log(path)
    if name in ("branch", "branches"):
        return branch(path)
    if name == "diff":
        return diff(path)
    if name == "stage":
        return stage(path, value)
    if name == "commit":
        return commit(path, value)
    if name in ("push", "pull"):
        return sync(path, pull=name == "pull")
    return False, f"I don't know the Git action {name}."
