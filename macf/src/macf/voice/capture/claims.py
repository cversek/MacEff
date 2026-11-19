"""Keys and wake phrases claimed host-wide, for per-agent capture units on one host (MIS-0008 R26).

Until a system daemon runs the shared capture unit of R46, each agent on a host may run its own. Two
such units would both answer a key or phrase they both declare, so each claims its own in a registry in
the daemon runtime directory before it listens, and a clash with another live agent's claim refuses the
start with the same message R26 gives a shared unit. A claim whose process has died no longer counts.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterator, Optional

from macf.voice.capture.members import check_members

ROLES = ("wake_phrase", "hold_key", "toggle_key", "session_key", "send_key")


def default_path() -> Path:
    from macf.pd.names import runtime_dir
    return runtime_dir() / "voice-claims.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, under another account
    return True


class HostClaims:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    @contextmanager
    def _locked(self) -> Iterator[Dict[str, dict]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            table = json.loads(self.path.read_text()) if self.path.exists() else {}
            yield table
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(table, indent=1))
            tmp.replace(self.path)

    def claim(self, card: str, section, pid: int) -> None:
        """Claim ``card``'s keys and phrase, replacing its earlier claim; raises MembersRefused on a clash
        with another live agent, and then records nothing."""
        mine = {role: getattr(section, role, None) for role in ROLES}
        with self._locked() as table:
            for other in [c for c, e in table.items() if c == card or not _alive(int(e["pid"]))]:
                del table[other]
            sections = {c: SimpleNamespace(**e["section"]) for c, e in table.items()}
            sections[card] = SimpleNamespace(**mine)
            check_members(sections)
            table[card] = {"pid": pid, "section": mine}

    def release(self, card: str) -> None:
        with self._locked() as table:
            table.pop(card, None)

    def live(self) -> Dict[str, dict]:
        """The claims whose units are still running, by card."""
        if not self.path.exists():
            return {}
        table = json.loads(self.path.read_text())
        return {c: e for c, e in table.items() if _alive(int(e["pid"]))}
