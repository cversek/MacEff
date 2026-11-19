"""Keys and wake phrases claimed across one login's agents, for per-agent capture units (MIS-0008 R26).

Until a system daemon runs the shared capture unit of R46, each agent may run its own. Two such units
would both answer a key or phrase they both declare, so each claims its own in a registry before it
listens, and a clash with another live agent's claim refuses the start with the same message R26 gives a
shared unit. A claim counts only while the process that made it is still running: it is bound to that
process's start time, so a pid that comes back as another process doesn't keep a dead unit's keys.

PER LOGIN, NOT PER HOST. The registry is in the daemon runtime directory, which is per account. Where
every agent shares the operator's login, as on a Mac, that is every agent on the host. Where agents run
as accounts of their own, each account has its own registry and a clash between accounts is not seen;
the shared unit of R46 is the answer there.
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


class ClaimsUnreadable(RuntimeError):
    """The registry isn't readable JSON, so no claim can be checked against it."""


def default_path() -> Path:
    from macf.pd.names import runtime_dir
    return runtime_dir() / "voice-claims.json"


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, under another account
    return True


def _live(entry: dict) -> bool:
    """Whether the process that made a claim is still the one running under its pid."""
    from macf.notify.session import verify_incarnation
    pid = int(entry["pid"])
    if entry.get("start") is None:
        # this platform has no process-start source, so the claim was made without one: the pid is all there is
        return _pid_exists(pid)
    return verify_incarnation(pid, entry["start"])


class HostClaims:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    def _read(self) -> Dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except ValueError as e:
            raise ClaimsUnreadable(
                f"the voice claims registry {self.path} isn't readable JSON ({e}); remove it, then restart "
                "every agent's capture unit so each claims its keys again") from e

    @contextmanager
    def _locked(self) -> Iterator[Dict[str, dict]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            table = self._read()
            yield table
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(table, indent=1))
            tmp.replace(self.path)

    def claim(self, card: str, section, pid: int) -> None:
        """Claim ``card``'s keys and phrase, replacing its earlier claim; raises MembersRefused on a clash
        with another live agent, and then records nothing."""
        from macf.notify.session import proc_start
        mine = {role: getattr(section, role, None) for role in ROLES}
        with self._locked() as table:
            for other in [c for c, e in table.items() if c == card or not _live(e)]:
                del table[other]
            sections = {c: SimpleNamespace(**e["section"]) for c, e in table.items()}
            sections[card] = SimpleNamespace(**mine)
            check_members(sections)
            table[card] = {"pid": pid, "start": proc_start(pid), "section": mine}

    def release(self, card: str, pid: Optional[int] = None) -> None:
        """Drop ``card``'s claim; with ``pid``, only if that process made it, so a unit stopping late
        never drops the claim of the unit that replaced it."""
        if not self.path.exists():
            return
        with self._locked() as table:
            if card in table and (pid is None or int(table[card]["pid"]) == pid):
                del table[card]

    def live(self) -> Dict[str, dict]:
        """The claims whose units are still running, by card."""
        return {c: e for c, e in self._read().items() if _live(e)}
