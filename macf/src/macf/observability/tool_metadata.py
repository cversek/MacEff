"""Tool-invocation metadata formatters.

The PreToolUse hook fires for every tool invocation. Without metadata
the Telegram-routed observation reduces to "🎯 Skill" or "📄 Read" —
the *kind* of action but not its *target*. This module formats a
concise one-line summary per tool type so that remote observers see
"🎯 Skill: maceff-delegation" or "📄 Read: foo.py" instead of generic
labels.

Producers expected: PreToolUse hook in
``macf.hooks.handle_pre_tool_use``. Consumers: any code path that
constructs a Telegram-routed tool-invocation message.

Design notes:
- The formatter is data-only — it inspects ``tool_input`` dicts and
  returns strings. No I/O, no side effects.
- Each per-tool formatter uses ``.get(...)`` everywhere, never raising
  on missing fields. Tools evolve and add new input keys; missing
  fields produce sensible degraded output, not crashes.
- Unknown tools fall through to ``tool_name`` as the metadata, so the
  helper is safe to call indiscriminately.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse


# Maximum characters in the metadata payload before truncation. Picked
# to keep the full prefix + metadata under ~120 chars so Telegram messages
# stay scannable.
_MAX_METADATA_CHARS = 100


def _truncate(s: str, limit: int = _MAX_METADATA_CHARS) -> str:
    """Single-line truncation with ellipsis. Returns ``s`` unchanged if
    it fits, otherwise ``s[:limit-1] + "…"`` (Unicode single-char
    ellipsis to avoid the 3-byte cost of ``...``)."""
    if s is None:
        return ""
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _basename(path_str: str) -> str:
    """Best-effort filename extraction. Falls back to the original
    string if ``Path`` rejects it (rare but possible with weird inputs)."""
    if not path_str:
        return ""
    try:
        return Path(path_str).name or path_str
    except (TypeError, ValueError):
        return path_str


def _domain(url: str) -> str:
    """Best-effort hostname extraction from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or url
    except (TypeError, ValueError):
        return url


# Per-tool formatters. Each takes ``tool_input`` and returns the
# metadata segment (without the tool name — the dispatcher prepends it).
# Returning empty string means "no useful detail to add"; the
# dispatcher emits just the tool name in that case.

def _fmt_skill(tool_input: Dict[str, Any]) -> str:
    return tool_input.get("skill", "") or ""


def _fmt_bash(tool_input: Dict[str, Any]) -> str:
    cmd = tool_input.get("command", "")
    return _truncate(cmd, 80)


def _fmt_read(tool_input: Dict[str, Any]) -> str:
    return _basename(tool_input.get("file_path", ""))


def _fmt_edit_or_write(tool_input: Dict[str, Any]) -> str:
    return _basename(tool_input.get("file_path", ""))


def _fmt_task(tool_input: Dict[str, Any]) -> str:
    sa = tool_input.get("subagent_type", "?") or "?"
    desc = tool_input.get("description", "") or ""
    if desc:
        return f"[{sa}] {_truncate(desc, 60)}"
    return f"[{sa}]"


def _fmt_webfetch(tool_input: Dict[str, Any]) -> str:
    return _domain(tool_input.get("url", "") or "")


def _fmt_grep_or_glob(tool_input: Dict[str, Any]) -> str:
    pattern = tool_input.get("pattern", "") or tool_input.get("query", "")
    return _truncate(pattern, 60)


def _fmt_taskcreate(tool_input: Dict[str, Any]) -> str:
    return _truncate(tool_input.get("subject", "") or "", 60)


def _fmt_taskupdate(tool_input: Dict[str, Any]) -> str:
    task_id = tool_input.get("taskId", "?")
    status = tool_input.get("status", "")
    return f"#{task_id}" + (f" → {status}" if status else "")


def _fmt_taskget(tool_input: Dict[str, Any]) -> str:
    return f"#{tool_input.get('taskId', '?')}"


# Dispatch map. Keys are tool names exactly as Claude Code emits them.
_FORMATTERS = {
    "Skill": _fmt_skill,
    "Bash": _fmt_bash,
    "Read": _fmt_read,
    "Edit": _fmt_edit_or_write,
    "Write": _fmt_edit_or_write,
    "Task": _fmt_task,
    "WebFetch": _fmt_webfetch,
    "Grep": _fmt_grep_or_glob,
    "Glob": _fmt_grep_or_glob,
    "TaskCreate": _fmt_taskcreate,
    "TaskUpdate": _fmt_taskupdate,
    "TaskGet": _fmt_taskget,
}


def format_tool_metadata(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Return a concise one-line metadata summary for ``tool_name``.

    The output shape is ``"<tool_name>: <details>"`` when the tool has
    a per-tool formatter and produces non-empty details, otherwise
    just ``tool_name``.

    Args:
        tool_name: Tool identifier as emitted by Claude Code
            (e.g. ``"Skill"``, ``"Bash"``, ``"Read"``).
        tool_input: The tool's input dict. May be missing fields the
            formatter expects — formatters degrade gracefully.

    Returns:
        Metadata string suitable for a single-line Telegram message
        segment or terminal display. Bounded length: the formatter
        truncates long fields (commands, descriptions, patterns) so
        the result fits comfortably alongside a prefix tag.

    Examples:
        >>> format_tool_metadata("Skill", {"skill": "maceff-delegation"})
        'Skill: maceff-delegation'
        >>> format_tool_metadata("Read", {"file_path": "/abs/path/foo.py"})
        'Read: foo.py'
        >>> format_tool_metadata("UnknownTool", {"anything": 1})
        'UnknownTool'
    """
    if not isinstance(tool_input, dict):
        # Defensive: callers should pass a dict but typecheck just in case.
        tool_input = {}

    formatter = _FORMATTERS.get(tool_name)
    if formatter is None:
        return tool_name

    details = formatter(tool_input).strip()
    if not details:
        return tool_name
    return f"{tool_name}: {details}"
