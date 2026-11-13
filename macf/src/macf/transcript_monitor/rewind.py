"""Rewinds, told from the transcript's parent links (#1003).

A Claude Code rewind does not shorten the transcript. The abandoned turns stay in the
file, and the next prompt is appended with a ``parentUuid`` that points back past them.
So the only sign of a rewind is a typed prompt whose parent is not the latest turn:
assistant turns were written after that parent, and the prompt leaves them behind.

A rewind undoes the conversation, not what was done in it: a review posted or a commit
pushed in the dropped turns still happened. The event therefore carries the tools those
turns used, reduced to names (and Bash to its program), so an agent can see at a glance
whether anything left the session. It carries no text from the transcript.
"""
import json
import os
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

# Fewer dropped assistant entries than this is not reported: a single interrupted reply
# can leave one or two siblings behind without anyone rewinding.
MIN_DROPPED = 3
# Entries remembered. A rewind further back than this cannot be told from a gap.
CAPACITY = 50_000
# How much of the transcript's end is read at start, since the monitor starts there.
PRIME_BYTES = 8 * 1024 * 1024


@dataclass
class _Node:
    seq: int
    parent: Optional[str]
    assistant: bool
    timestamp: str
    tools: Counter = field(default_factory=Counter)


def _is_typed_prompt(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        kinds = {item.get("type") for item in content if isinstance(item, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


def _program(command: str) -> str:
    """The first program a Bash command runs: on its first line that isn't a comment, past
    subshell parentheses and VAR=value assignments. A compound command can run others, so
    this is a hint at what happened, not a list of it."""
    for line in command.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for word in line.replace("(", " ").split():
            if "=" in word and not word.startswith(("/", ".")):
                continue
            return os.path.basename(word)
        return ""
    return ""


def _tools(entry: dict) -> Counter:
    used: Counter = Counter()
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return used
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue
        name = str(item.get("name", ""))
        if name == "Bash":
            program = _program(str((item.get("input") or {}).get("command", "")))
            name = f"Bash:{program}" if program else name
        used[name] += 1
    return used


class RewindWatch:
    """A detector, so it sees each transcript line once, in order.

    Stateful: one per monitor, never shared, as its memory is of one transcript."""

    def __init__(self, capacity: int = CAPACITY, min_dropped: int = MIN_DROPPED) -> None:
        self._nodes: "OrderedDict[str, _Node]" = OrderedDict()
        self._reported: Set[str] = set()
        self._seq = 0
        self._capacity = capacity
        self._min_dropped = min_dropped

    def __call__(self, entry: dict):
        return self._observe(entry, emit=True)

    def prime(self, path: Path, max_bytes: int = PRIME_BYTES) -> int:
        """Remember the end of an existing transcript without reporting anything in it.
        Returns the number of entries read."""
        size = path.stat().st_size
        with open(path, "rb") as f:
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
        lines = data.split(b"\n")
        if start > 0:
            lines = lines[1:]  # the first line was cut by the seek
        read = 0
        for raw in lines:
            try:
                entry = json.loads(raw)
            except ValueError:  # noqa: S112 - priming only remembers history; the last line is
                continue        # often half-written, and the live monitor reports bad lines itself
            if isinstance(entry, dict):
                self._observe(entry, emit=False)
                read += 1
        return read

    def _observe(self, entry: dict, emit: bool):
        uuid = entry.get("uuid")
        if not uuid or entry.get("isSidechain"):
            return None
        self._seq += 1
        node = _Node(self._seq, entry.get("parentUuid"), entry.get("type") == "assistant",
                     str(entry.get("timestamp", "")),
                     _tools(entry) if entry.get("type") == "assistant" else Counter())
        found = self._dropped(node) if emit and _is_typed_prompt(entry) else None
        self._remember(uuid, node)
        if not found:
            return None
        from .daemon import Detection
        return Detection("context_rewind_detected", found)

    def _remember(self, uuid: str, node: _Node) -> None:
        self._nodes[uuid] = node
        while len(self._nodes) > self._capacity:
            old, _ = self._nodes.popitem(last=False)
            self._reported.discard(old)

    def _dropped(self, prompt: _Node) -> Optional[Dict]:
        parent = self._nodes.get(prompt.parent) if prompt.parent else None
        if parent is None:
            return None  # a root, or a parent older than memory: nothing to compare
        # Every ancestor of the prompt was written at or before its parent, so each
        # assistant entry written after the parent is off the prompt's line.
        dropped = []
        for uuid, node in reversed(self._nodes.items()):
            if node.seq <= parent.seq:
                break
            if node.assistant and uuid not in self._reported:
                dropped.append((uuid, node))
        if len(dropped) < self._min_dropped:
            return None
        dropped.reverse()
        tools: Counter = Counter()
        for uuid, node in dropped:
            tools.update(node.tools)
            self._reported.add(uuid)
        return {
            "branch_from": prompt.parent,
            "branch_from_time": parent.timestamp,
            "prompt_time": prompt.timestamp,
            "dropped_from": dropped[0][1].timestamp,
            "dropped_to": dropped[-1][1].timestamp,
            "dropped_assistant_entries": len(dropped),
            "tools": dict(sorted(tools.items())),
            "detector": "transcript_monitor",
        }
