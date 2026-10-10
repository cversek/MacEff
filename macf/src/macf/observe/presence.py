"""Presence: who can see the session, and how, as one record the call line reads.

MIS-0002-R91 (call_line_MUST_show_presence): the observed agent's per-call line shows each
onlooker that watches and each operator surface that is present.
MIS-0002-R98 (presence_MUST_say_enabled_when_undetectable): a surface that cannot detect
its viewer says it is enabled, never that someone is attached.
MIS-0002-R102 (presence_SHOULD_show_reachable): an operator reachable through a channel is
told apart from an operator attached at a keyboard.
MIS-0002-R97 (keyboard_surface_MUST_set_presence) is the head maintainer's judgment per
surface; ``surface_state`` is where a surface declares what it can know.

The primal daemon writes the record; hooks only read it. A record that cannot be read is
said on the line as unknown, never shown as nobody there.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .acts import ENDED, PAUSED, Observation

ATTACHED = "attached"
ENABLED = "enabled"
REACHABLE = "reachable"


@dataclass(frozen=True)
class Surface:
    """An operator surface: how the operator can reach the session.

    ``keyboard`` surfaces can type (a terminal, a remote-control viewer); a channel can
    only carry messages. ``detects_viewer`` says whether the surface can tell that someone
    is looking, and ``viewer_seen`` what it saw.
    """

    name: str
    keyboard: bool
    detects_viewer: bool = True
    viewer_seen: bool = False


def surface_state(s: Surface) -> Optional[str]:
    """What a surface may claim, or None when it is not present at all."""
    if not s.keyboard:
        return REACHABLE
    if not s.detects_viewer:
        return ENABLED
    return ATTACHED if s.viewer_seen else None


def build(surfaces: Iterable[Surface], observations: Dict[str, Observation]) -> dict:
    """The presence record: surfaces present, with their state, and onlookers watching."""
    present = []
    for s in surfaces:
        st = surface_state(s)
        if st is not None:
            present.append({"surface": s.name, "state": st})
    watching = [{"onlooker": o.onlooker, "paused": o.status == PAUSED}
                for o in sorted(observations.values(), key=lambda o: o.onlooker) if o.status != ENDED]
    return {"version": 1, "surfaces": present, "onlookers": watching}


def write(path: Path, record: dict) -> None:
    """Replace the record whole, owner-only, so a reader never sees half of one."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(record, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read(path: Path) -> Optional[dict]:
    """The record, or None when there is none or it cannot be read (said, never guessed)."""
    try:
        record = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {"version": 1, "surfaces": [], "onlookers": []}
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: presence record unreadable at {path}: {e}", file=sys.stderr)
        return None
    if not isinstance(record, dict) or record.get("version") != 1:
        print(f"⚠️ MACF: presence record at {path} has an unknown shape", file=sys.stderr)
        return None
    return record


def call_line(record: Optional[dict]) -> str:
    """The presence segment of the per-call line (R91), or '' when nobody can see the session."""
    if record is None:
        return "presence: unknown"
    parts: List[str] = []
    onlookers = record.get("onlookers") or []
    if onlookers:
        names = [o["onlooker"] + (" (paused)" if o.get("paused") else "") for o in onlookers]
        parts.append("onlookers: " + ", ".join(names))
    surfaces = record.get("surfaces") or []
    if surfaces:
        parts.append("operator: " + ", ".join(f"{s['surface']} {s['state']}" for s in surfaces))
    return " · ".join(parts)
