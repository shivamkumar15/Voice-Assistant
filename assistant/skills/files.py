"""Safe local file, document, and study-plan operations."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from ..config import (
    ASSISTANT_FILE_ROOTS,
    FILE_MAX_READ_BYTES,
    FILE_SEARCH_MAX_DEPTH,
)

_SKIP_DIRS = {
    ".cache", ".git", ".local", ".mozilla", ".npm", ".venv", "venv",
    "node_modules", "__pycache__", "target",
}
_PROTECTED_NAMES = {
    ".aws", ".azure", ".config", ".gnupg", ".kde", ".ssh", ".kube",
}
_PROTECTED_PREFIXES = ((".local", "share", "ninja-assistant"),)
_TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".json", ".jsonl", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".csv", ".tsv", ".py", ".js", ".ts",
    ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".hpp", ".rs", ".go",
    ".sh", ".html", ".htm", ".xml", ".css", ".sql",
}
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been",
    "before", "being", "between", "both", "but", "can", "could", "does",
    "for", "from", "had", "has", "have", "how", "into", "its", "more",
    "most", "not", "only", "other", "our", "should", "than", "that", "the",
    "their", "then", "there", "these", "they", "this", "those", "through",
    "under", "using", "was", "were", "what", "when", "where", "which", "will",
    "with", "would", "you", "your",
}


class FileOperationError(ValueError):
    """Raised when a requested path is outside the assistant workspace."""


def _roots() -> list[Path]:
    roots = []
    for root in ASSISTANT_FILE_ROOTS:
        try:
            roots.append(Path(root).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
    return roots or [Path.home().resolve()]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_protected(path: Path) -> bool:
    home = Path.home().resolve()
    if not _is_within(path, home):
        return False
    try:
        relative = path.relative_to(home)
    except ValueError:
        return False
    parts = {part.lower() for part in relative.parts}
    if any(item in parts for item in _PROTECTED_NAMES):
        return True
    normalized_parts = tuple(part.lower() for part in relative.parts)
    return any(normalized_parts[:len(prefix)] == prefix for prefix in _PROTECTED_PREFIXES)


def resolve_path(value: str | Path, *, must_exist: bool = False,
                 allow_root: bool = False) -> Path:
    """Resolve a spoken path and reject traversal or sensitive locations."""
    raw = str(value or "").strip().strip("'\"")
    if not raw:
        raise FileOperationError("I need a file or folder name")
    if raw.startswith("file://"):
        raw = raw[7:]
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    roots = _roots()
    if not path.is_absolute():
        path = roots[0] / path
    try:
        path = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise FileOperationError(f"I couldn't resolve that path: {exc}") from exc
    if not any(_is_within(path, root) for root in roots):
        raise FileOperationError(
            "That location is outside my allowed workspace. "
            "Set ASSISTANT_FILE_ROOTS to add a trusted folder."
        )
    if not allow_root and any(path == root for root in roots):
        raise FileOperationError("I won't modify the workspace root itself")
    if _is_protected(path):
        raise FileOperationError("I won't access private credential folders")
    if must_exist and not path.exists():
        raise FileOperationError(f"I couldn't find {raw}")
    return path


def _display(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _query_words(value: str) -> str:
    value = re.sub(r"\b(?:my|the|folder|directory|file|document)\b", " ", value.lower())
    return re.sub(r"[^a-z0-9._ -]+", " ", value).strip(" .")


def _walk(root: Path, max_depth: int | None = None):
    max_depth = FILE_SEARCH_MAX_DEPTH if max_depth is None else max_depth
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        dirs[:] = [
            name for name in dirs
            if name not in _SKIP_DIRS
            and not name.startswith(".")
            and not _is_protected(current_path / name)
        ]
        yield current_path, dirs, files
        if depth >= max_depth:
            dirs[:] = []


def find_directories(query: str, limit: int = 12) -> list[Path]:
    query = _query_words(query)
    if not query:
        return []
    try:
        direct = resolve_path(query, must_exist=True)
        if direct.is_dir():
            return [direct]
    except FileOperationError:
        pass
    normalized = re.sub(r"[^a-z0-9]", "", query)
    matches: list[tuple[int, int, Path]] = []
    for root in _roots():
        if not root.is_dir():
            continue
        for current, dirs, _ in _walk(root):
            for name in dirs:
                candidate = current / name
                compact = re.sub(r"[^a-z0-9]", "", name.lower())
                if compact == normalized:
                    score = 0
                elif normalized and normalized in compact:
                    score = 1
                elif normalized and compact in normalized:
                    score = 2
                else:
                    continue
                matches.append((score, len(candidate.parts), candidate))
    matches.sort(key=lambda item: (item[0], item[1], str(item[2])))
    return [item[2] for item in matches[:limit]]


def _matches_name(path: Path, query: str) -> bool:
    query = query.strip().lower()
    if not query:
        return True
    if any(char in query for char in "*?["):
        from fnmatch import fnmatch

        return fnmatch(path.name.lower(), query)
    stem = path.stem.lower().replace("_", " ").replace("-", " ")
    target = query.removesuffix(path.suffix.lower()).replace("_", " ").replace("-", " ")
    return query in path.name.lower() or target in stem


def find_files(query: str = "", folder: str | Path | None = None,
               latest: bool = False, limit: int = 100) -> list[Path]:
    """Find files under an allowed directory, optionally newest first."""
    roots: list[Path]
    if folder:
        try:
            root = resolve_path(folder, must_exist=True, allow_root=True)
        except FileOperationError:
            return []
        if not root.is_dir():
            return []
        roots = [root]
    else:
        roots = [root for root in _roots() if root.is_dir()]
    query = (query or "").strip()
    suffix = ""
    suffix_match = re.search(r"(\.[a-z0-9]{1,8})$", query.lower())
    if suffix_match:
        suffix = suffix_match.group(1)
        query = query[:-len(suffix)]
    found: list[Path] = []
    for root in roots:
        for current, _, files in _walk(root, max(FILE_SEARCH_MAX_DEPTH, 4)):
            for name in files:
                if name.startswith("."):
                    continue
                path = current / name
                if suffix and not name.lower().endswith(suffix):
                    continue
                if query and not _matches_name(path, query):
                    continue
                found.append(path)
                if len(found) >= max(limit * 4, 400):
                    break
            if len(found) >= max(limit * 4, 400):
                break
    if latest:
        found.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0,
                   reverse=True)
    else:
        found.sort(key=lambda item: str(item).lower())
    return found[:limit]


def latest_file(folder: str | Path, pattern: str = "*") -> Path | None:
    files = find_files(pattern, folder=folder, latest=True, limit=1)
    return files[0] if files else None


def open_path(path: str | Path) -> tuple[bool, str]:
    try:
        target = resolve_path(path, must_exist=True, allow_root=True)
    except FileOperationError as exc:
        return False, str(exc)
    if shutil.which("xdg-open"):
        command = ["xdg-open", str(target)]
    elif shutil.which("gio"):
        command = ["gio", "open", str(target)]
    else:
        return False, "I couldn't find a desktop opener"
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True, f"Opening {_display(target)}"
    except OSError as exc:
        return False, f"I couldn't open that: {exc}"


def _atomic_write(path: Path, content: str, overwrite: bool) -> tuple[bool, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite and path.exists():
            return False, f"{_display(path)} already exists"
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        if not overwrite and path.exists():
            temporary.unlink(missing_ok=True)
            return False, f"{_display(path)} already exists"
        os.replace(temporary, path)
        return True, f"Saved {_display(path)}"
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        return False, f"I couldn't save that file: {exc}"


def create_file(path: str | Path, content: str = "", overwrite: bool = False):
    try:
        target = resolve_path(path)
    except FileOperationError as exc:
        return False, str(exc)
    return _atomic_write(target, content, overwrite)


def write_file(path: str | Path, content: str, append: bool = False):
    try:
        target = resolve_path(path)
    except FileOperationError as exc:
        return False, str(exc)
    if append and target.exists():
        try:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(content)
            return True, f"Updated {_display(target)}"
        except OSError as exc:
            return False, f"I couldn't update that file: {exc}"
    return _atomic_write(target, content, overwrite=True)


def move_file(source: str | Path, destination: str | Path, overwrite: bool = False):
    try:
        src = resolve_path(source, must_exist=True)
        dst = resolve_path(destination)
    except FileOperationError as exc:
        return False, str(exc)
    if src == dst:
        return False, "The source and destination are the same"
    if dst.exists() and not overwrite:
        return False, f"{_display(dst)} already exists"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return True, f"Moved {_display(src)} to {_display(dst)}"
    except OSError as exc:
        return False, f"I couldn't move that file: {exc}"


def rename_file(source: str | Path, new_name: str):
    new_name = str(new_name or "").strip().strip("'\"")
    if not new_name or "/" in new_name or "\\" in new_name:
        return False, "Tell me a new file name without slashes"
    try:
        src = resolve_path(source, must_exist=True)
    except FileOperationError as exc:
        return False, str(exc)
    return move_file(src, src.parent / new_name)


def _trash(path: Path) -> tuple[bool, str]:
    if shutil.which("gio"):
        try:
            result = subprocess.run(
                ["gio", "trash", "--", str(path)],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                return True, f"Moved {_display(path)} to the trash"
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, f"Deleted {_display(path)}"
    except OSError as exc:
        return False, f"I couldn't delete that: {exc}"


def delete_path(path: str | Path):
    try:
        target = resolve_path(path, must_exist=True)
    except FileOperationError as exc:
        return False, str(exc)
    return _trash(target)


def list_directory(folder: str | Path) -> tuple[bool, str]:
    try:
        target = resolve_path(folder, must_exist=True, allow_root=True)
    except FileOperationError as exc:
        return False, str(exc)
    if not target.is_dir():
        return False, f"{_display(target)} is not a folder"
    try:
        entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as exc:
        return False, f"I couldn't read that folder: {exc}"
    if not entries:
        return True, f"{_display(target)} is empty"
    shown = []
    for entry in entries[:30]:
        suffix = "/" if entry.is_dir() else ""
        shown.append(entry.name + suffix)
    extra = f", and {len(entries) - 30} more" if len(entries) > 30 else ""
    return True, f"{_display(target)} contains " + ", ".join(shown) + extra


def _read_text_file(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(FILE_MAX_READ_BYTES + 1)
    if len(data) > FILE_MAX_READ_BYTES:
        data = data[:FILE_MAX_READ_BYTES]
    return data.decode("utf-8", errors="replace")


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        return " ".join(node.text or "" for node in root.iter()
                        if node.tag.endswith("}t"))
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""


def _odt_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("content.xml")
        root = ElementTree.fromstring(xml)
        return " ".join(
            "".join(node.itertext()) for node in root.iter()
            if node.tag.endswith("}p")
        )
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""


def _html_text(path: Path) -> str:
    raw = _read_text_file(path)
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    return re.sub(r"(?s)<[^>]+>", " ", html.unescape(raw))


def extract_text(path: str | Path) -> tuple[bool, str]:
    """Extract readable text from common document formats."""
    try:
        target = resolve_path(path, must_exist=True)
    except FileOperationError as exc:
        return False, str(exc)
    suffix = target.suffix.lower()
    try:
        if suffix == ".pdf":
            if shutil.which("pdftotext"):
                result = subprocess.run(
                    ["pdftotext", "-layout", str(target), "-"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return True, result.stdout[:FILE_MAX_READ_BYTES]
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(target))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                if text.strip():
                    return True, text[:FILE_MAX_READ_BYTES]
            except Exception:
                pass
            return False, "I couldn't read that PDF. Install pdftotext or pypdf."
        if suffix == ".docx":
            text = _docx_text(target)
            return (True, text[:FILE_MAX_READ_BYTES]) if text.strip() else (
                False, "I couldn't find readable text in that Word document."
            )
        if suffix == ".odt":
            text = _odt_text(target)
            return (True, text[:FILE_MAX_READ_BYTES]) if text.strip() else (
                False, "I couldn't find readable text in that document."
            )
        if suffix in (".html", ".htm"):
            text = _html_text(target)
            return (True, text[:FILE_MAX_READ_BYTES]) if text.strip() else (
                False, "That document is empty."
            )
        if suffix in _TEXT_SUFFIXES or not suffix:
            text = _read_text_file(target)
            if "\x00" in text[:1024]:
                return False, "That looks like a binary file, not readable text."
            return (True, text) if text.strip() else (False, "That file is empty.")
        return False, f"I don't know how to read {suffix or 'that file type'} yet."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"I couldn't read that document: {exc}"


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
    result = [part.strip() for part in parts if part.strip()]
    if len(result) <= 1 and len(compact) > 320:
        result = [compact[index:index + 300].strip()
                  for index in range(0, len(compact), 300)]
    return [part for part in result if part]


def summarize_text(text: str, max_sentences: int = 5) -> str:
    sentences = _sentences(text)
    if not sentences:
        return ""
    words = re.findall(r"[a-z][a-z0-9'-]{2,}", text.lower())
    frequency = Counter(word for word in words if word not in _STOP_WORDS)
    if not frequency:
        return " ".join(sentences[:max_sentences])
    ranked = []
    for index, sentence in enumerate(sentences):
        sentence_words = re.findall(r"[a-z][a-z0-9'-]{2,}", sentence.lower())
        useful = [word for word in sentence_words if word in frequency]
        score = sum(frequency[word] for word in useful) / max(1, len(sentence_words) ** 0.5)
        if index == 0:
            score += 1.5
        if index < 3:
            score += 0.25
        ranked.append((score, index, sentence))
    selected = sorted(sorted(ranked, reverse=True)[:max(1, max_sentences)],
                      key=lambda item: item[1])
    return " ".join(item[2] for item in selected)


def summarize_file(path: str | Path, max_sentences: int = 5) -> tuple[bool, str]:
    ok, text = extract_text(path)
    if not ok:
        return False, text
    summary = summarize_text(text, max_sentences=max_sentences)
    if not summary:
        return False, "I couldn't find enough readable text to summarize."
    if len(summary) > 1600:
        summary = summary[:1597].rstrip() + "…"
    return True, summary


def read_file(path: str | Path, max_chars: int = 1600) -> tuple[bool, str]:
    ok, text = extract_text(path)
    if not ok:
        return False, text
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) > max_chars:
        clean = clean[:max_chars - 1].rstrip() + "…"
    return True, clean or "That file is empty."


def _topics(text: str, count: int = 6) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9'-]{3,}", (text or "").lower())
    frequency = Counter(word for word in words if word not in _STOP_WORDS)
    return [word.title() for word, _ in frequency.most_common(count)]


def build_study_plan(title: str, summary: str) -> str:
    topics = _topics(summary)
    topic_text = ", ".join(topics) if topics else "the main ideas"
    return (
        f"Study plan: {title}\n\n"
        f"Focus topics: {topic_text}\n\n"
        "1. Read the source once and write down the central question.\n"
        "2. Review the summary and explain each key idea in your own words.\n"
        "3. Turn the focus topics into questions and answer them from memory.\n"
        "4. Apply the ideas to one practical example or small exercise.\n"
        "5. Review again tomorrow, then again after three days and one week.\n\n"
        f"Summary:\n{summary or 'No readable summary was available.'}\n"
    )


def save_study_plan(source: str | Path, summary: str) -> tuple[bool, str]:
    try:
        source_path = resolve_path(source, must_exist=True)
    except FileOperationError as exc:
        return False, str(exc)
    target = source_path.with_name(f"{source_path.stem}_study_plan.txt")
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = source_path.with_name(f"{source_path.stem}_study_plan_{stamp}.txt")
    plan = build_study_plan(source_path.stem, summary)
    ok, reply = create_file(target, plan, overwrite=False)
    if ok:
        return True, f"{reply}. Open it with: open {_display(target)}"
    return False, reply
