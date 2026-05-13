"""recoverable_errors - Stop-hook auto-recovery for common tool-error friction.

When a tool call fails with an obviously-recoverable error (file not Read
before Edit, deferred tool not loaded, stale Read after file change, etc.)
the agent often stops with an apology rather than retrying. The Stop hook
imports `scan_last_tool_error` from this module to detect such errors in
the most recent tool result and emit `decision:'block' + reason:<directive>`
back to Claude Code, forcing the agent to apply the obvious recovery and
retry rather than stopping.

Registry shape:
    (name, regex, directive_template)

Templates may reference named regex groups via `{group_name}`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..utils.streaming import iter_lines_reverse

# --- Pattern registry ------------------------------------------------------
#
# Each entry: (name, compiled-regex, directive-template)
# `name` is a short stable identifier used in event logs.
# `regex` matches the tool_result content text (the <tool_use_error>...</...>
# wrapper is included so patterns are explicit about the surface they target).
# `template` is rendered with named-group substitution; missing optional groups
# are filled with empty strings.
#
# Patterns are evaluated in order; first match wins.

_PATTERN_SOURCES: List[Tuple[str, str, str]] = [
    (
        "file_not_read",
        r"<tool_use_error>File has not been read yet\.",
        "The Edit/Write tool requires a prior Read of the file in this turn. "
        "Read the target file again, then retry the original Edit/Write."
    ),
    (
        "file_modified_since_read",
        r"<tool_use_error>File has been modified since read",
        "The file changed since your last Read (linter, user, or sibling tool). "
        "Re-Read it to see current content, then retry the Edit with old_string "
        "matching the new contents."
    ),
    (
        "old_string_not_found",
        r"<tool_use_error>String to replace not found in file",
        "old_string did not match. The file likely changed since your last Read, "
        "or the literal contains characters that need escaping. Re-Read the file "
        "and retry with the exact current text."
    ),
    (
        "replace_all_mismatch",
        r"<tool_use_error>Found (?P<found>\d+) matches?.*?expected (?P<expected>\d+)",
        "Edit found {found} matches but expected {expected}. Either: (a) make "
        "old_string more specific by including surrounding context, OR (b) set "
        "replace_all=true to replace every occurrence."
    ),
    (
        "tool_not_in_registry",
        r"<tool_use_error>Error: No such tool available: (?P<tool>[\w_]+)</tool_use_error>",
        "Tool '{tool}' is not loaded. If it is a deferred tool, run "
        "ToolSearch with query='select:{tool}' to load its schema, then retry. "
        "If it was removed, choose a different approach."
    ),
    (
        "input_validation_error",
        r"<tool_use_error>InputValidationError: (?P<tool>\w+) failed due to the following issue:\s*(?P<details>[^<]+?)</tool_use_error>",
        "{tool} got bad parameters: {details}. Re-check the tool schema "
        "(parameter names, types, required vs optional) and retry."
    ),
    (
        "path_does_not_exist",
        r"<tool_use_error>Path does not exist:\s*(?P<path>[^<]+?)</tool_use_error>",
        "Path missing: {path}. Verify with `ls`, `Glob`, or `find` before "
        "retrying — the path may be in a different repo, a sibling submodule, "
        "or you may need to create parent directories first."
    ),
    (
        "file_does_not_exist",
        r"<tool_use_error>File does not exist\.(?:\s*Did you mean (?P<suggestion>[^?]+)\?)?</tool_use_error>",
        "File not found. {suggestion_hint}Verify the path with `ls` or `Glob` "
        "before retrying."
    ),
]


def _compile_pattern(name: str, regex: str, template: str):
    return (name, re.compile(regex, re.DOTALL), template)


PATTERNS = [_compile_pattern(*p) for p in _PATTERN_SOURCES]


def format_directive(template: str, groups: dict) -> str:
    """Render a directive template with named-group substitution.

    Optional groups that didn't match are passed through as empty strings.
    A `{name_hint}` reference renders as ``Did you mean: <value>. `` when the
    base group `{name}` matched, else empty — used by `path_does_not_exist`
    to fold the optional "Did you mean X?" CC suggestion into the directive.
    """
    safe_groups = {k: (v or "") for k, v in groups.items()}
    safe_groups.setdefault("suggestion", "")
    safe_groups["suggestion_hint"] = (
        f"Did you mean: {safe_groups['suggestion']}. "
        if safe_groups.get("suggestion") else ""
    )
    try:
        return template.format(**safe_groups)
    except KeyError as e:
        # Unknown placeholder — fall back to template raw rather than crash.
        return template + f"  [template-render-error: {e}]"


def match_error_text(text: str) -> Optional[Tuple[str, str]]:
    """Match a tool-error text against the registry.

    Args:
        text: The tool_result content string (typically wrapped in
              `<tool_use_error>...</tool_use_error>`).

    Returns:
        (pattern_name, formatted_directive) on first match, else None.
    """
    if not text:
        return None
    for name, regex, template in PATTERNS:
        m = regex.search(text)
        if not m:
            continue
        directive = format_directive(template, m.groupdict())
        return (name, directive)
    return None


def _extract_tool_result_text(content) -> Optional[str]:
    """Pull a string out of a tool_result `content` field.

    The CC transcript stores tool_result content as either a plain string
    OR a list of content blocks. Concatenate text blocks if list-shaped.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                t = b.get("text") or b.get("content") or ""
                parts.append(str(t))
        return " ".join(parts) if parts else None
    return None


def scan_last_tool_error(transcript_path: str) -> Optional[Tuple[str, str]]:
    """Scan the transcript JSONL for the most recent tool error.

    Reads the file backwards (memory-efficient via reversed line list);
    finds the most recent user message containing a `tool_result` with
    `is_error=True`; matches that error against the pattern registry.

    Args:
        transcript_path: Absolute path to the session JSONL transcript.

    Returns:
        (pattern_name, directive) if a recoverable error is found AND it
        is the most recent tool result. Returns None if:
          - transcript missing or unreadable
          - no tool errors found
          - the most recent tool result is NOT an error (agent already
            recovered — successful tool call after the error)
          - the error doesn't match any registered pattern
    """
    if not transcript_path:
        return None
    p = Path(transcript_path)
    if not p.exists() or not p.is_file():
        return None

    # JSONL transcripts can be >1 GB at high context use. Stream lines
    # from EOF instead of materializing the file (which OOM-killed the
    # Stop hook — closes GH cversek/MacEff#94). For the typical case we
    # find the answer in the last 1–3 lines, so this is also cheap.
    try:
        line_iter = iter_lines_reverse(p)
    except (OSError, IOError):
        return None

    for line in line_iter:
        if '"tool_result"' not in line:
            # Quick reject — not a tool result line. Avoids JSON parse cost.
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message") or {}
        if msg.get("role") != "user":
            continue
        content_blocks = msg.get("content")
        if not isinstance(content_blocks, list):
            continue
        # Walk the content blocks; first tool_result wins (a single user
        # message can contain multiple tool_results from parallel calls,
        # but the most recent stop is naturally tied to the last block).
        for block in reversed(content_blocks):
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            # Found the most recent tool_result. If it's not an error,
            # the agent already recovered — bail.
            if not block.get("is_error"):
                return None
            text = _extract_tool_result_text(block.get("content"))
            if text is None:
                return None
            return match_error_text(text)
    return None
