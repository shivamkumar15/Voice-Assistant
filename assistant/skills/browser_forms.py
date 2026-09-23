"""Best-effort keyboard form filling for the focused browser page."""

from __future__ import annotations

import re

from . import input_control


def _pairs(spec: str) -> list[tuple[str, str]]:
    text = re.sub(r"^(?:the\s+)?form\s+with\s+", "", (spec or "").strip(), flags=re.I)
    pieces = re.split(r"\s+and\s+", text, flags=re.I)
    pairs = []
    for piece in pieces:
        match = re.match(r"^([a-z][a-z _-]{1,24})\s+(.+)$", piece.strip(), re.I)
        if match:
            pairs.append((match.group(1).strip(), match.group(2).strip()))
    return pairs


def fill_form(spec: str) -> tuple[bool, str]:
    pairs = _pairs(spec)
    if not pairs:
        return False, "Tell me fields like: name Aamina and email aamina@example.com"
    for _, value in pairs:
        ok, reply = input_control.type_text(value)
        if not ok:
            return False, reply
        ok, reply = input_control.press_key("tab")
        if not ok:
            return False, reply
    fields = ", ".join(name for name, _ in pairs)
    return True, f"Filled {fields} in the focused form; review it before submitting"
