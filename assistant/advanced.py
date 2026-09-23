"""Deterministic multi-step workflows for advanced assistant commands."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .skills import browser_forms, code, files, git, monitor, notifications, screen, software, web


@dataclass
class PendingAction:
    kind: str
    args: dict
    prompt: str
    prefix_steps: list[tuple[str, dict]] = field(default_factory=list)


@dataclass
class AdvancedTask:
    steps: list[tuple[str, dict]]
    pending: PendingAction | None = None
    blocked: bool = False


@dataclass
class _Context:
    folder: Path | None = None
    file: Path | None = None
    summary: str = ""


class AdvancedAgent:
    """Turn explicit local workflows into bounded, reversible operations."""

    def __init__(self):
        self.pending: PendingAction | None = None
        self.last_folder: Path | None = None
        self.last_file: Path | None = None
        self.last_summary: str = ""

    _INTENT_RE = re.compile(
        r"\b(?:folder|directory|pdf|docx|document|study plan|file|files|"
        r"summari[sz]e|notification|notifications|screen|git|code|email|mail|form|game|monitor|"
        r"install|delete|rename)\b",
        re.IGNORECASE,
    )

    def is_advanced(self, text: str) -> bool:
        return bool(self._INTENT_RE.search(text or ""))

    def prepare(self, text: str, strict: bool = False) -> AdvancedTask | None:
        value = (text or "").strip()
        if not value:
            return None
        if strict:
            return AdvancedTask(steps=[], blocked=True)
        steps = self._parse_steps(value)
        if not steps:
            return None
        for index, (kind, args) in enumerate(steps):
            pending = self._pending_for(kind, args)
            if pending is not None:
                pending.prefix_steps = steps[:index]
                return AdvancedTask(steps=[], pending=pending)
        return AdvancedTask(steps=steps)

    def execute(self, task: AdvancedTask) -> tuple[bool, str]:
        if task.blocked:
            return False, ""
        if task.pending is not None:
            return self.execute_pending(task.pending)
        context = _Context(
            folder=self.last_folder,
            file=self.last_file,
            summary=self.last_summary,
        )
        replies: list[str] = []
        ok, message = self._run_steps(task.steps, context, replies)
        if not ok:
            return False, message
        self._remember_context(context)
        return True, self._final_reply(context, replies, task.steps)

    def execute_pending(self, action: PendingAction) -> tuple[bool, str]:
        if self.pending is action:
            self.pending = None
        context = _Context(
            folder=self.last_folder,
            file=self.last_file,
            summary=self.last_summary,
        )
        replies: list[str] = []
        ok, message = self._run_steps(action.prefix_steps, context, replies)
        if not ok:
            return False, message
        try:
            if action.kind == "delete":
                ok, message = files.delete_path(
                    self._existing_path(action.args["path"], context)
                )
            elif action.kind == "code":
                ok, message = code.run_snippet(
                    action.args.get("language", "python"),
                    action.args.get("code", ""),
                )
            elif action.kind == "run_code_file":
                ok, message = code.run_file(
                    action.args.get("path", ""), action.args.get("language", "")
                )
            elif action.kind == "git_commit":
                ok, message = git.commit(
                    action.args.get("path"), action.args.get("message", "")
                )
            elif action.kind == "git_sync":
                ok, message = git.sync(
                    action.args.get("path"), bool(action.args.get("pull"))
                )
            elif action.kind == "install":
                ok, message = software.install(action.args.get("package", ""))
            elif action.kind == "email":
                ok, message = web.email_draft(
                    action.args.get("recipient", ""),
                    action.args.get("message", ""),
                    action.args.get("subject", ""),
                )
            elif action.kind == "overwrite":
                ok, message = files.write_file(
                    action.args["path"], action.args.get("content", ""), append=False
                )
            else:
                ok, message = False, "That action is no longer available."
        except Exception as exc:
            ok, message = False, f"That action failed: {exc}"
        if not ok:
            return False, message
        replies.append(message)
        self._remember_context(context)
        return True, self._final_reply(context, replies, [])

    def _existing_path(self, value: str, context: _Context | None = None):
        raw = str(value or "").strip()
        if raw.lower() in ("it", "that", "this", "the file", "the document"):
            candidate = context.file if context is not None else self.last_file
            if candidate is not None and candidate.exists():
                return candidate
            return raw
        return files.resolve_path(raw, must_exist=True)

    def _pending_for(self, kind: str, args: dict) -> PendingAction | None:
        if kind == "delete":
            try:
                path = self._existing_path(args.get("path", ""))
            except files.FileOperationError:
                path = args.get("path", "")
            args["path"] = str(path)
            return PendingAction(
                "delete", args,
                f"This will move {path} to the trash. Say yes to continue or no to cancel.",
            )
        if kind == "code":
            language = str(args.get("language", "python"))
            return PendingAction(
                "code", args,
                f"Run the supplied {language} code? Say yes to continue or no to cancel.",
            )
        if kind == "run_code_file":
            path = str(args.get("path", ""))
            return PendingAction(
                "run_code_file", args,
                f"Run the code file {path}? Say yes to continue or no to cancel.",
            )
        if kind == "git_commit":
            message = str(args.get("message", ""))
            return PendingAction(
                "git_commit", args,
                f"Create a Git commit with this message: {message}. Say yes to continue or no to cancel.",
            )
        if kind == "git_sync":
            action = "pull" if args.get("pull") else "push"
            return PendingAction(
                "git_sync", args,
                f"Git {action} can change remote files. Say yes to continue or no to cancel.",
            )
        if kind == "install":
            package = str(args.get("package", ""))
            return PendingAction(
                "install", args,
                f"Install {package}? Say yes to continue or no to cancel.",
            )
        if kind == "email":
            recipient = str(args.get("recipient", ""))
            return PendingAction(
                "email", args,
                f"Open an email draft to {recipient}? Say yes to continue or no to cancel.",
            )
        if kind == "write":
            try:
                target = files.resolve_path(args.get("path", ""))
                if target.exists():
                    return PendingAction(
                        "overwrite", args,
                        f"{target} already exists. Replace it? Say yes to continue or no to cancel.",
                    )
            except files.FileOperationError:
                return None
        return None

    def _parse_steps(self, text: str) -> list[tuple[str, dict]]:
        value = text.strip()
        lowered = value.lower()
        first = re.search(
            r"\b(?:open|show|find|search|list|read|summari[sz]e|create|write|"
            r"fill|complete|monitor|"
            r"delete|remove|move|rename|run|execute|git|send|install|"
            r"what(?:'s| is) on)\b",
            lowered,
        )
        if first and first.start() > 0:
            value = value[first.start():]
        form = re.match(
            r"^(?:fill|complete)(?:\s+out)?\s+(?:the\s+)?form\s+with\s+(.+)$",
            value, re.I,
        )
        value = re.sub(
            r"\s+and\s+save\s+(?:it|that)\s*$", "", value, flags=re.I
        )
        if form:
            return [("form", {"spec": form.group(1)})]
        direct = self._parse_clause(value)
        if direct and (
            not self._contains_separator(value)
            or any(kind in ("write", "write_code", "code", "form") for kind, _ in direct)
        ):
            return direct
        pieces = self._split_clauses(value)
        parsed: list[tuple[str, dict]] = []
        for piece in pieces:
            part = self._parse_clause(piece)
            if not part:
                return self._parse_clause(value) or []
            parsed.extend(part)
        return parsed

    @staticmethod
    def _contains_separator(value: str) -> bool:
        return bool(re.search(r"\s*(?:,|;|\bthen\b|\band\b)\s*", value, re.IGNORECASE))

    @staticmethod
    def _split_clauses(value: str) -> list[str]:
        pieces = re.split(
            r"\s*(?:,|;|\bthen\b|\band\b)\s*",
            value,
            flags=re.IGNORECASE,
        )
        return [piece.strip(" .!?") for piece in pieces if piece.strip(" .!?" )]

    def _parse_clause(self, clause: str) -> list[tuple[str, dict]]:
        text = re.sub(r"^(?:please|can you|could you|would you)\s+", "", clause.strip(), flags=re.I)
        text = re.sub(r"\b(?:for me|right now|okay|ok)\b\s*$", "", text, flags=re.I).strip(" .!?")
        if not text:
            return []

        match = re.match(
            r"^(?:run|execute)\s+(?:the\s+)?(python(?:3)?|javascript|js|node|bash|shell)\s+"
            r"(?:code|program)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("code", {"language": match.group(1), "code": match.group(2).strip()})]
        match = re.match(
            r"^(?:run|execute)\s+(python(?:3)?|javascript|js|node|bash|shell)\s+"
            r"(?:file|script)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("run_code_file", {
                "path": self._path_text(match.group(2)),
                "language": match.group(1),
            })]
        match = re.match(r"^(?:run|execute)\s+(?:the\s+)?(?:file|script)\s+(.+)$", text, re.I)
        if match:
            return [("run_code_file", {"path": self._path_text(match.group(1))})]
        match = re.match(
            r"^(?:write|create)\s+(?:a\s+)?(python(?:3)?|javascript|js|node|bash|shell)\s+"
            r"(?:code|program|script)\s+(?:named|called)\s+(.+?)\s+"
            r"(?:with|containing)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("write_code", {
                "language": match.group(1),
                "name": self._path_text(match.group(2)),
                "code": match.group(3).strip(),
            })]
        match = re.match(
            r"^(?:write|create)\s+(?:a\s+)?(python(?:3)?|javascript|js|node|bash|shell)\s+"
            r"(?:code|program|script)\s+(?:named|called)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("write_code", {
                "language": match.group(1),
                "name": self._path_text(match.group(2)),
                "code": "",
            })]
        match = re.match(
            r"^(?:write|create)\s+(?:a\s+)?(python(?:3)?|javascript|js|node|bash|shell)\s+"
            r"(?:code|program|script)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("write_code", {
                "language": match.group(1),
                "name": "snippet",
                "code": match.group(2).strip(),
            })]

        match = re.match(r"^(?:open|show|go to)\s+(?:the\s+|my\s+)?(.+?)\s+(?:folder|directory)$", text, re.I)
        if match:
            return [("open_folder", {"query": self._path_text(match.group(1))})]
        match = re.match(r"^(?:open|show|go to)\s+(?:the\s+)?(?:folder|directory)\s+(.+)$", text, re.I)
        if match:
            return [("open_folder", {"query": self._path_text(match.group(1))})]
        match = re.match(r"^open\s+(?:the\s+)?(?:document|pdf|docx)\s+(.+)$", text, re.I)
        if match:
            return [("open_document", {"query": self._path_text(match.group(1))})]
        match = re.match(r"^(?:show|read)\s+(?:the\s+)?(?:file|document|pdf|docx)\s+(.+)$", text, re.I)
        if match:
            return [("read", {"query": self._path_text(match.group(1))})]

        match = re.match(
            r"^find\s+(?:the\s+)?(?:(latest|newest|most recent)\s+)?(.+?)(?:\s+(?:in|from)\s+(.+))?$",
            text, re.I,
        )
        if match:
            query = self._path_text(match.group(2))
            folder = self._folder_text(match.group(3)) if match.group(3) else ""
            return [("find", {
                "query": query,
                "folder": folder,
                "latest": bool(match.group(1)),
            })]
        match = re.match(
            r"^(?:search|find)\s+(?:my\s+)?files?\s+(?:for|named|called|matching)\s+(.+?)"
            r"(?:\s+(?:in|from)\s+(.+))?$",
            text, re.I,
        )
        if match:
            return [("find", {
                "query": self._path_text(match.group(1)),
                "folder": self._folder_text(match.group(2)) if match.group(2) else "",
                "latest": False,
            })]

        match = re.match(
            r"^monitor\s+(?:system\s+resources|resources|system|computer)"
            r"(?:\s+for\s+(.+))?$",
            text, re.I,
        )
        if match:
            return [("monitor", {"duration": match.group(1) or "60 seconds"})]

        match = re.match(r"^(?:launch|open|play)\s+(?:the\s+)?game\s+(.+)$", text, re.I)
        if match:
            return [("game", {"query": self._path_text(match.group(1))})]

        match = re.match(
            r"^(read|summari[sz]e)\s+(?:the\s+)?(latest|newest|most recent)\s+"
            r"(.+?)(?:\s+(?:in|from)\s+(.+))?$",
            text, re.I,
        )
        if match:
            return [("summarize" if match.group(1).lower().startswith("summari") else "read", {
                "query": self._path_text(match.group(3)),
                "folder": self._folder_text(match.group(4)) if match.group(4) else "",
                "latest": True,
            })]
        match = re.match(
            r"^(?:read|summari[sz]e)\s+(?:the\s+)?(?:file|document|pdf|docx)?\s*(.+)$", text, re.I,
        )

        if match and not re.match(r"^(?:notifications?|screen)$", match.group(1), re.I):
            return [("summarize" if re.match(r"^summari", text, re.I) else "read", {
                "query": self._path_text(match.group(1)),
            })]
        match = re.match(r"^(?:create|make|generate)\s+(?:a\s+)?study plan(?:\s+for\s+(.+))?$", text, re.I)
        if match:
            return [("study_plan", {"query": self._path_text(match.group(1)) if match.group(1) else ""})]
        match = re.match(r"^(?:list|show)\s+(?:the\s+)?(?:files|contents)(?:\s+in\s+(.+))?$", text, re.I)
        if match:
            return [("list", {"query": self._folder_text(match.group(1)) if match.group(1) else ""})]

        match = re.match(r"^(?:create|make)\s+(?:a\s+)?(?:new\s+)?file\s+(?:named|called)?\s*(.+)$", text, re.I)
        if match:
            return [("write", {"path": self._path_text(match.group(1)), "content": ""})]
        match = re.match(r"^(?:write|save)\s+(.+?)\s+(?:to|in)\s+(?:the\s+)?file\s+(.+)$", text, re.I)
        if match:
            return [("write", {
                "path": self._path_text(match.group(2)),
                "content": match.group(1).strip(),
            })]
        match = re.match(r"^(?:write|save)\s+(?:the\s+)?(?:text|content)\s+(.+?)\s+(?:to|in)\s+(.+)$", text, re.I)
        if match:
            return [("write", {
                "path": self._path_text(match.group(2)),
                "content": match.group(1).strip(),
            })]

        match = re.match(r"^(?:move)\s+(.+?)\s+(?:to|into)\s+(.+)$", text, re.I)
        if match:
            return [("move", {
                "source": self._path_text(match.group(1)),
                "destination": self._path_text(match.group(2)),
            })]
        match = re.match(r"^rename\s+(.+?)\s+(?:to|as)\s+(.+)$", text, re.I)
        if match:
            return [("rename", {
                "source": self._path_text(match.group(1)),
                "name": self._path_text(match.group(2)),
            })]
        match = re.match(r"^(?:delete|remove|trash)\s+(?:the\s+)?(?:file|folder|directory|document)?\s*(.+)$", text, re.I)
        if match:
            return [("delete", {"path": self._path_text(match.group(1))})]

        match = re.match(
            r"^(?:send\s+)?(?:an?\s+)?email\s+(?:to\s+)?(.+?)\s+"
            r"(?:saying|with message|that)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("email", {
                "recipient": self._path_text(match.group(1)),
                "message": match.group(2).strip(),
                "subject": "",
            })]
        match = re.match(
            r"^(?:send\s+)?(?:an?\s+)?email\s+(?:to\s+)?(.+?)\s+"
            r"with subject\s+(.+?)\s+(?:saying|with message|and say|and saying)\s+(.+)$",
            text, re.I,
        )
        if match:
            return [("email", {
                "recipient": self._path_text(match.group(1)),
                "subject": match.group(2).strip(),
                "message": match.group(3).strip(),
            })]

        match = re.match(r"^git\s+(status|log|history|branch|branches|diff|stage|commit|push|pull)\b(.*)$", text, re.I)
        if match:
            action = match.group(1).lower()
            rest = match.group(2).strip()
            if action == "stage":
                stage_match = re.match(
                    r"(.+?)\s+(?:in|inside|from)\s+(.+)$", rest, re.I
                )
                if stage_match:
                    value = stage_match.group(1).strip()
                    repo = self._path_text(stage_match.group(2))
                else:
                    repo, value = self._split_git_rest(rest)
                return [("git_stage", {"path": repo, "value": value or "."})]
            repo, value = self._split_git_rest(rest)
            if action in ("commit",):
                message_match = re.match(
                    r"^(?:with\s+message\s+|message\s+|message\s*:\s*)(.+?)"
                    r"(?:\s+(?:in|inside|from)\s+(.+))?$",
                    rest, re.I,
                )
                if message_match:
                    value = message_match.group(1).strip()
                    repo = self._path_text(message_match.group(2) or repo)
                else:
                    value = re.sub(r"^(?:with\s+message\s+|message\s+|message\s*:\s*)", "", value, flags=re.I)
                return [("git_commit", {"path": repo, "message": value})]
            if action in ("push", "pull"):
                return [("git_sync", {"path": repo, "pull": action == "pull"})]
            return [("git", {"action": action, "path": repo, "value": value})]

        match = re.match(r"^(?:send|show|create)\s+(?:a\s+)?notification(?:\s+(?:saying|with|that)\s+(.+))?$", text, re.I)
        if match:
            return [("notification", {"message": match.group(1) or ""})]
        match = re.match(
            r"^(?:read|show|list|what are)\s+(?:my\s+)?notifications?$", text, re.I
        )
        if match:
            return [("read_notifications", {})]
        if re.match(r"^(?:what(?:'s| is)|read|describe|understand)\s+(?:on\s+)?(?:my\s+)?screen$", text, re.I):
            return [("screen", {})]
        match = re.match(
            r"^install\s+(?:software\s+|package\s+|app\s+)?(.+)$", text, re.I
        )
        if match:
            return [("install", {"package": self._path_text(match.group(1))})]
        return []

    @staticmethod
    def _path_text(value: str) -> str:
        value = (value or "").strip().strip("'\"")
        value = re.sub(r"^(?:the|my|a|an)\s+", "", value, flags=re.I)
        value = re.sub(r"^(?:file|document|folder|directory)\s+", "", value, flags=re.I)
        value = re.sub(r"\s+(?:folder|directory|file|document)$", "", value, flags=re.I)
        return value.strip(" .!?")

    @classmethod
    def _folder_text(cls, value: str) -> str:
        return cls._path_text(value)

    @classmethod
    def _split_git_rest(cls, rest: str) -> tuple[str, str]:
        match = re.match(r"(?:in|inside|from)\s+(.+?)(?:\s+(?:with|message|using)\s+(.*))?$", rest, re.I)
        if not match:
            return "", rest.strip()
        return cls._path_text(match.group(1)), (match.group(2) or "").strip()

    def _resolve_folder(self, query: str, context: _Context) -> Path | None:
        if not query:
            return context.folder
        try:
            path = files.resolve_path(query, must_exist=True, allow_root=True)
            if path.is_dir():
                context.folder = path
                return path
        except files.FileOperationError:
            pass
        matches = files.find_directories(query, limit=1)
        if matches:
            context.folder = matches[0]
            return matches[0]
        return None

    def _resolve_file(self, query: str, context: _Context, latest: bool = False) -> Path | None:
        value = self._path_text(query)
        requested_latest = latest or bool(re.search(
            r"^(?:the\s+)?(?:latest|newest|most recent)\b", value, re.I
        ))
        value = re.sub(r"^(?:the\s+)?(?:latest|newest|most recent)\s+", "", value, flags=re.I)
        if value.lower() in ("file", "document"):
            value = ""
        if not value or value.lower() in ("it", "that", "the latest", "latest"):
            if context.file and context.file.exists():
                return context.file
            folder = context.folder
            target = files.latest_file(folder) if folder else files.latest_file(
                files._roots()[0]
            )
            if target is not None:
                context.file = target
            return target
        try:
            path = files.resolve_path(value, must_exist=True)
            if path.is_file():
                context.file = path
                return path
        except files.FileOperationError:
            pass
        folder = context.folder
        matches = files.find_files(value, folder=folder, latest=requested_latest, limit=1)
        if matches:
            context.file = matches[0]
            return matches[0]
        return None

    def _remember_context(self, context: _Context):
        if context.folder is not None:
            self.last_folder = context.folder
        if context.file is not None and context.file.exists():
            self.last_file = context.file
        if context.summary:
            self.last_summary = context.summary

    def _run_steps(self, steps: list[tuple[str, dict]], context: _Context,
                   replies: list[str]) -> tuple[bool, str]:
        for kind, args in steps:
            try:
                ok, message = self._run_step(kind, args, context)
            except Exception as exc:
                return False, f"That task stopped: {exc}"
            replies.append(message)
            if not ok:
                return False, message
        return True, ""

    def _run_step(self, kind: str, args: dict, context: _Context) -> tuple[bool, str]:
        if kind == "open_folder":
            folder = self._resolve_folder(str(args.get("query", "")), context)
            if not folder:
                return False, f"I couldn't find the folder {args.get('query', '')}"
            ok, message = files.open_path(folder)
            return True, message if ok else f"I found {files._display(folder)}, but {message}"
        if kind == "find":
            folder = self._resolve_folder(str(args.get("folder", "")), context)
            query = str(args.get("query", ""))
            target = self._resolve_file(query, context, bool(args.get("latest")))
            if not target:
                where = folder or "the allowed workspace"
                return False, f"I couldn't find {query or 'a matching file'} in {where}"
            return True, f"Found {files._display(target)}"
        if kind == "list":
            folder = self._resolve_folder(str(args.get("query", "")), context)
            if not folder and not args.get("query"):
                folder = files._roots()[0]
                context.folder = folder
            if not folder:
                return False, "Tell me which folder to list"
            return files.list_directory(folder)
        if kind == "open_document":
            target = self._resolve_file(str(args.get("query", "")), context)
            if not target:
                return False, f"I couldn't find {args.get('query', 'that document')}"
            return files.open_path(target)
        if kind == "read":
            if args.get("folder") and not self._resolve_folder(
                    str(args.get("folder", "")), context):
                return False, f"I couldn't find the folder {args.get('folder')}"
            target = self._resolve_file(
                str(args.get("query", "")), context, bool(args.get("latest"))
            )
            if not target:
                return False, f"I couldn't find {args.get('query', 'that file')}"
            return files.read_file(target)
        if kind == "summarize":
            if args.get("folder") and not self._resolve_folder(
                    str(args.get("folder", "")), context):
                return False, f"I couldn't find the folder {args.get('folder')}"
            target = self._resolve_file(
                str(args.get("query", "")), context, bool(args.get("latest"))
            )
            if not target:
                return False, f"I couldn't find {args.get('query', 'that document')}"
            ok, summary = files.summarize_file(target)
            if ok:
                context.summary = summary
            return ok, f"Summary of {files._display(target)}: {summary}" if ok else summary
        if kind == "study_plan":
            query = str(args.get("query", "")).strip()
            target = self._resolve_file(query, context) if query else context.file
            if target:
                if not context.summary:
                    ok, summary = files.summarize_file(target)
                    if not ok:
                        return False, summary
                    context.summary = summary
                return files.save_study_plan(target, context.summary)
            if not context.summary:
                return False, "Tell me which document the study plan is for"
            target = Path.home() / "Documents" / "Ninja" / "study_plan.txt"
            ok, message = files.create_file(target, files.build_study_plan("study plan", context.summary))
            return ok, message if ok else f"I saved the study plan: {message}"
        if kind == "write":
            ok, message = files.write_file(
                args.get("path", ""), args.get("content", ""), append=False
            )
            return ok, message
        if kind == "move":
            source = self._existing_path(args.get("source", ""), context)
            return files.move_file(source, args.get("destination", ""))
        if kind == "rename":
            source = self._existing_path(args.get("source", ""), context)
            return files.rename_file(source, args.get("name", ""))
        if kind == "delete":
            return files.delete_path(self._existing_path(args.get("path", ""), context))
        if kind == "form":
            return browser_forms.fill_form(args.get("spec", ""))
        if kind == "monitor":
            return monitor.monitor_system(args.get("duration", "60 seconds"))
        if kind == "game":
            return web.steam_search(args.get("query", ""))
        if kind == "code":
            return code.run_snippet(args.get("language", "python"), args.get("code", ""))
        if kind == "run_code_file":
            return code.run_file(args.get("path", ""), args.get("language", ""))
        if kind == "write_code":
            return code.write_snippet(
                args.get("language", "python"),
                args.get("code", ""),
                args.get("name", "snippet"),
            )
        if kind == "git":
            return git.action(args.get("action", "status"), args.get("path"), args.get("value", ""))
        if kind == "git_stage":
            return git.stage(args.get("path"), args.get("value", "."))
        if kind == "git_commit":
            return git.commit(args.get("path"), args.get("message", ""))
        if kind == "git_sync":
            return git.sync(args.get("path"), bool(args.get("pull")))
        if kind == "notification":
            return notifications.publish("Ninja", args.get("message", ""))
        if kind == "read_notifications":
            return notifications.read_recent()
        if kind == "screen":
            return screen.read_screen()
        if kind == "install":
            return software.install(args.get("package", ""))
        return False, f"I don't know how to perform {kind}."

    def _final_reply(self, context: _Context, replies: list[str],
                     steps: list[tuple[str, dict]]) -> str:
        unique: list[str] = []
        for reply in replies:
            if reply and reply not in unique:
                unique.append(reply)
        if context.file and any(kind == "study_plan" for kind, _ in steps):
            summary = context.summary or "the document was read"
            plan_reply = next(
                (item for item in reversed(unique)
                 if "study" in item.lower() and "plan" in item.lower()),
                "",
            )
            if plan_reply:
                spoken_summary = context.summary[:700].rstrip()
                if len(context.summary) > 700:
                    spoken_summary += "…"
                return (
                    f"I finished the task using {files._display(context.file)}. "
                    f"Summary: {spoken_summary.rstrip('.')}. {plan_reply}"
                )
            return f"I finished the task using {files._display(context.file)}. {summary}"
        if not unique:
            return "I finished that task."
        result = " ".join(unique)
        if len(result) > 1800:
            result = result[:1797].rstrip() + "…"
        return result


_shared: AdvancedAgent | None = None


def get_advanced() -> AdvancedAgent:
    global _shared
    if _shared is None:
        _shared = AdvancedAgent()
    return _shared
