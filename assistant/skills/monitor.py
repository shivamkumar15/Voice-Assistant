"""Short, bounded resource monitoring reports."""

from __future__ import annotations

import time

import psutil

from . import reminders


def monitor_system(duration: str = "60 seconds", interval: int = 5) -> tuple[bool, str]:
    seconds, _ = reminders.parse_duration(duration)
    if seconds is None:
        seconds = 60
    seconds = max(5, min(int(seconds), 3600))
    interval = max(1, min(int(interval), 30))
    samples: list[tuple[float, float, float]] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        samples.append((
            psutil.cpu_percent(interval=None),
            psutil.virtual_memory().percent,
            psutil.disk_usage("/").percent,
        ))
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    if not samples:
        return False, "I couldn't collect a system sample"
    averages = [sum(sample[index] for sample in samples) / len(samples)
                for index in range(3)]
    peaks = [max(sample[index] for sample in samples) for index in range(3)]
    return True, (
        f"Monitored {len(samples)} samples over {seconds} seconds. "
        f"Average CPU {averages[0]:.0f} percent, peak {peaks[0]:.0f}; "
        f"memory {averages[1]:.0f} percent, peak {peaks[1]:.0f}; "
        f"disk {averages[2]:.0f} percent."
    )
