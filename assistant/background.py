"""Background command execution: run slow work without blocking voice/HUD.

Say "open youtube and play believer in background", "check weather in
background", or "run <shell command> in background" and the assistant
acknowledges immediately ("Running ... as job #1") while the real work
runs on a small thread pool. Say "list jobs", "check job 1" or
"cancel job 2" to manage them; completion is spoken + shown in the HUD
via the worker's job listener.

Also handles raw shell: "run ls -la in background" or "run pip install
foo in background" executes the shell string with a timeout and keeps
truncated output for "check job N".
"""

from __future__ import annotations

import re
import shlex
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from .config import BACKGROUND_MAX_WORKERS, BACKGROUND_SHELL_TIMEOUT

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
_jobs: dict[int, dict] = {}
_futures: dict[int, Future] = {}
_next_id = 1
_listener = None  # fn(job_id, label, ok, reply)


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, BACKGROUND_MAX_WORKERS),
                thread_name_prefix="ninja-bg",
            )
    return _executor


def set_listener(fn) -> None:
    """Worker sets this so job completion speaks + posts to the HUD."""
    global _listener
    _listener = fn


def submit(label: str, func, *args, **kwargs) -> int:
    """Run func(*args, **kwargs) in background; returns job id."""
    global _next_id
    label = (label or "task").strip() or "task"
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "label": label,
            "status": "running",
            "created_at": time.time(),
            "finished_at": None,
            "reply": "",
        }
    fut = _pool().submit(_run_job, job_id, label, func, args, kwargs)
    with _lock:
        _futures[job_id] = fut
    return job_id


def _run_job(job_id: int, label: str, func, args, kwargs):
    ok, reply = False, "Job failed with no output"
    try:
        out = func(*args, **kwargs)
        if isinstance(out, tuple) and len(out) == 2:
            ok, reply = bool(out[0]), str(out[1])
        elif isinstance(out, str):
            ok, reply = True, out
        else:
            ok, reply = True, str(out)
    except Exception as exc:  # never let a job die silently
        ok, reply = False, f"Job {job_id} ({label}) failed: {exc}"
    with _lock:
        job = _jobs.get(job_id, {})
        job["status"] = "done" if ok else "failed"
        job["finished_at"] = time.time()
        job["reply"] = reply
    listener = _listener
    if listener is not None:
        try:
            listener(job_id, label, ok, reply)
        except Exception:
            pass
    return ok, reply


def run_shell(cmd: str, timeout: int = BACKGROUND_SHELL_TIMEOUT) -> tuple[bool, str]:
    """Execute a shell string, capturing truncated output."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False, "Nothing to run"
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        if len(out) > 1500:
            out = out[:1500].rstrip() + "…"
        if proc.returncode == 0:
            return True, f"Finished: {cmd}" + (f". Output: {out}" if out else "")
        return False, f"Command failed ({proc.returncode}): {cmd}" + (f". {out}" if out else "")
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s: {cmd}"
    except Exception as exc:
        return False, f"Couldn't run that: {exc}"


def looks_like_shell(text: str) -> bool:
    """Heuristic: 'run ls /tmp' / 'run pip install x' is shell, not a skill."""
    t = (text or "").strip().lower()
    if not t.startswith("run "):
        return False
    rest = t[4:].strip()
    if not rest:
        return False
    shells = (
        "ls ", "cat ", "echo ", "pip ", "python ", "git ", "npm ", "sudo ",
        "systemctl ", "docker ", "apt ", "pacman ", "./", "/", "sleep ",
    )
    if rest.startswith(shells) or re.match(r"^[a-z0-9_.-]+( +[a-z0-9_./-]+)+$", rest):
        return True
    # 'run <shell word>' with flags looks like shell too.
    return bool(re.match(r"^[a-z][a-z0-9_.-]*\s+(-{1,2}\w|\w)", rest))


def strip_background_marker(text: str) -> tuple[str, bool]:
    """Return (command_without_marker, wanted_background)."""
    t = (text or "").strip()
    m = re.search(r"\s*\bin (the )?background\s*$", t, re.IGNORECASE)
    m2 = re.search(r"\s*\bin parallel\s*$", t, re.IGNORECASE)
    if m or m2:
        cut = (m or m2).start()
        return t[:cut].strip(" ,.!?"), True
    return t, False


def list_jobs() -> tuple[bool, str]:
    with _lock:
        items = sorted(_jobs.items())
    if not items:
        return True, "No background jobs yet"
    parts = []
    for jid, job in items[-8:]:  # keep the spoken reply short
        st = job["status"]
        if st == "running":
            age = int(time.time() - job["created_at"])
            parts.append(f"#{jid} {job['label']} (running {age}s)")
        else:
            reply = (job.get("reply") or "")[:120]
            parts.append(f"#{jid} {job['label']} ({st}: {reply})")
    return True, "Background jobs: " + "; ".join(parts)


def job_status(job_id: int) -> tuple[bool, str]:
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return False, f"No job #{job_id}"
    if job["status"] == "running":
        age = int(time.time() - job["created_at"])
        return True, f"Job #{job_id} ({job['label']}) is still running ({age}s)"
    reply = (job.get("reply") or "")[:500]
    return True, f"Job #{job_id} ({job['label']}) {job['status']}: {reply}"


def cancel_job(job_id: int) -> tuple[bool, str]:
    with _lock:
        fut = _futures.get(job_id)
        job = _jobs.get(job_id)
    if not job:
        return False, f"No job #{job_id}"
    if job["status"] != "running":
        return True, f"Job #{job_id} already {job['status']}"
    cancelled = bool(fut.cancel()) if fut is not None else False
    if cancelled:
        with _lock:
            job["status"] = "cancelled"
            job["finished_at"] = time.time()
        return True, f"Cancelled job #{job_id} ({job['label']})"
    return False, (
        f"Job #{job_id} is already executing — I can't interrupt it, "
        "but it will report when done"
    )


def clear_finished() -> tuple[bool, str]:
    with _lock:
        done = [jid for jid, j in _jobs.items() if j["status"] != "running"]
        for jid in done:
            _jobs.pop(jid, None)
            _futures.pop(jid, None)
    if not done:
        return True, "No finished jobs to clear"
    return True, f"Cleared {len(done)} finished job{'s' if len(done) != 1 else ''}"


def parse_job_number(text: str) -> int | None:
    m = re.search(r"job\s*#?\s*(\d+)", (text or "").lower())
    return int(m.group(1)) if m else None
