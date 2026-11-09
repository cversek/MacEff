"""The feedback drafts the client holds unsent, read and never changed (cversek/MacEff#903).

A draft makes the client answer ``/exit`` with a review-or-discard dialog, so ``inject exit``
refuses while one waits (#812). Sending or discarding it is the operator's decision. These
readers let a status line or a refusal say how many there are, how old and what about, so the
operator can decide at a calm moment instead of when a restart is blocked.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Draft:
    path: Path
    title: str
    created: Optional[datetime]


def drafts_dir() -> Path:
    """Where the client keeps its unsent feedback drafts."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "feedback" / "drafts"


def _created(data: dict, path: Path) -> datetime:
    """When the draft was made: its own ``created_at``, else the file's modification time.
    Raises OSError when the file is gone."""
    raw = data.get("created_at")
    if isinstance(raw, str):
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        except ValueError:
            pass  # noqa: MACEFF003 - an unreadable stamp falls back to the file's own time below
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def unsent_drafts() -> List[Draft]:
    """The drafts waiting, oldest first. A draft whose text can't be read is still listed,
    untitled, since it blocks an exit all the same."""
    found = []
    for path in sorted(drafts_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        title = data.get("title") if isinstance(data.get("title"), str) else ""
        try:
            created = _created(data, path)
        except OSError:
            continue   # sent or discarded since the listing, so it no longer blocks an exit
        found.append(Draft(path, title.strip(), created))
    return sorted(found, key=lambda d: d.created or datetime.max.replace(tzinfo=timezone.utc))


def age(draft: Draft, now: Optional[datetime] = None) -> str:
    """How old the draft is, in the largest whole unit: "18 days old", "5 hours old", "under an hour old"."""
    if draft.created is None:
        return "of unknown age"
    seconds = ((now or datetime.now(timezone.utc)) - draft.created).total_seconds()
    for unit, size in (("day", 86400), ("hour", 3600)):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'s' if n != 1 else ''} old"
    return "under an hour old"


def describe(draft: Draft, now: Optional[datetime] = None) -> str:
    """One draft as a person would name it: its title and age, then its file."""
    title = f'"{draft.title}"' if draft.title else "an untitled draft"
    return f"{title}, {age(draft, now)} ({draft.path})"
