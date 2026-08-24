"""Addressing a live session from the filesystem alone.

An out-of-process observer cannot inherit anything from the session it wants to
reach -- not an environment variable, not a file descriptor. It discovers the
session the way a daemon has to: by reading files.

  1. the per-session credential  ~/.claude/sessions/<pid>.<hash>.key
  2. the per-session socket      $XDG_RUNTIME_DIR/cc-socks/<pid>.sock

WHO OWNS THE CREDENTIAL, and what that means. It is mode 0600 owned by the
AGENT'S OWN uid, inside a 0700 directory also agent-owned, and whoever wakes the
session must be able to read it. This is not fixable by permissions. The
disposition on record is to DISCARD wake attribution rather than defend it: no
component reasons over any field of a wake, so what a wake claims is irrelevant
because every fact comes from the store. Read
`macf_tools policy navigate notification_delivery` before changing that -- the
requirement it removes REACTIVATES the moment any field is trusted.

Consequence, stated plainly: a leaked credential permits CAUSING TURNS, not
FORGING MAIL. The residual risk is attention hijack, and it is bounded by rate.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SESSIONS_DIRNAME = ".claude/sessions"
SOCKET_DIRNAME = "cc-socks"


def sessions_dir() -> Path:
    return Path(os.path.expanduser("~")) / SESSIONS_DIRNAME


def socket_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / SOCKET_DIRNAME


@dataclass(frozen=True)
class PeerCredential:
    """A session credential. The token is NEVER logged, echoed or returned.

    `__repr__` is overridden rather than left to the dataclass default, because
    the default would render the token into any traceback, log line or debugger
    frame that touches this object -- which is the ordinary way a secret escapes.
    """

    token: str = field(repr=False)
    declared_start: Optional[str] = None
    path: Optional[Path] = None

    def __repr__(self) -> str:
        return f"PeerCredential(token=<redacted {len(self.token)} chars>, declared_start={self.declared_start!r})"

    def __str__(self) -> str:
        return self.__repr__()


def find_credential_path(pid: int) -> Optional[Path]:
    """Locate the credential file for a pid, or None with a stated reason."""
    directory = sessions_dir()
    try:
        names = os.listdir(directory)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: session dir unreadable (no wake possible): {e}", file=sys.stderr)
        return None
    for name in names:
        if name.startswith(f"{pid}.") and name.endswith(".key"):
            return directory / name
    return None


def read_credential(path: Path) -> Optional[PeerCredential]:
    """Read a credential. Returns None -- never a partial or empty credential."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: credential unreadable (no wake): {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: credential malformed (no wake): {e}", file=sys.stderr)
        return None
    token = data.get("peerToken")
    if not token:
        print("⚠️ MACF: credential carries no peerToken (no wake)", file=sys.stderr)
        return None
    return PeerCredential(token=token, declared_start=data.get("procStart"), path=path)


def proc_start_ticks(pid: int) -> Optional[int]:
    """Field 22 of /proc/<pid>/stat -- process start, in clock ticks since boot.

    `comm` may contain spaces and parentheses, so everything is parsed relative to
    the LAST ')' rather than by splitting the whole line.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except (FileNotFoundError, ProcessLookupError) as e:
        print(f"⚠️ MACF: pid {pid} is not running (no wake): {e}", file=sys.stderr)
        return None
    except (PermissionError, OSError) as e:
        print(f"⚠️ MACF: /proc unreadable for pid {pid} (no wake): {e}", file=sys.stderr)
        return None
    try:
        tail = data[data.rfind(")") + 2:].split()
        return int(tail[19])
    except (IndexError, ValueError) as e:
        print(f"⚠️ MACF: /proc stat unparseable for pid {pid} (no wake): {e}", file=sys.stderr)
        return None


def verify_incarnation(pid: int, declared_start) -> bool:
    """Bind the credential to a process INCARNATION rather than to a number.

    Without this the design addresses a pid, and a recycled pid becomes
    addressable with a stale credential.

    THE TYPES DIFFER AND THIS IS THE WHOLE REASON THE CHECK GOES UNWRITTEN.
    The credential stores the value as a STRING; /proc yields an INT. Both are
    clock ticks since boot -- same unit, measured -- so a naive `==` is False for
    every well-formed credential, the check refuses every legitimate wake, and
    the obvious remedy is to delete it. Normalise, then compare.

    A credential with NO declared start fails CLOSED. It is an authorization
    check, not an advisory one, so absence is not permission.
    """
    if declared_start is None:
        print(
            f"⚠️ MACF: credential for pid {pid} declares no procStart (refusing: "
            "an incarnation check cannot fail open)",
            file=sys.stderr,
        )
        return False
    actual = proc_start_ticks(pid)
    if actual is None:
        return False
    try:
        declared = int(str(declared_start).strip())
    except (TypeError, ValueError) as e:
        print(f"⚠️ MACF: procStart not an integer for pid {pid} (refusing): {e}", file=sys.stderr)
        return False
    if declared != actual:
        print(
            f"⚠️ MACF: incarnation mismatch for pid {pid} (refusing: stale credential "
            f"against a recycled pid) declared={declared} actual={actual}",
            file=sys.stderr,
        )
        return False
    return True


def find_socket(pid: int) -> Optional[Path]:
    path = socket_dir() / f"{pid}.sock"
    if not path.exists():
        print(f"⚠️ MACF: no session socket for pid {pid} (no wake): {path}", file=sys.stderr)
        return None
    return path


def addressable_sessions() -> list:
    """Every pid that currently has BOTH a credential and a live socket.

    Answers "which agents can actually be woken?" -- a question the mechanism
    this replaces could not answer at all, because it silently did nothing for
    any agent not running under tmux.
    """
    found = []
    directory = sessions_dir()
    try:
        names = os.listdir(directory)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: session dir unreadable (cannot enumerate): {e}", file=sys.stderr)
        return found
    for name in names:
        if not name.endswith(".key"):
            continue
        try:
            pid = int(name.split(".")[0])
        except ValueError:
            continue
        if (socket_dir() / f"{pid}.sock").exists() and proc_start_ticks(pid) is not None:
            found.append(pid)
    return sorted(found)
