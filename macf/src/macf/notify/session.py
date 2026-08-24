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


@dataclass(frozen=True)
class SessionInfo:
    """What the client publishes about a session, beside the credential.

    MEASURED: the sidecar `<pid>.json` is world-readable (0664) while the
    credential is 0600. It carries the CONVERSATION identity, which is what makes
    the ambiguous-target problem tractable at all -- two processes serving one
    conversation share a `sessionId` and are otherwise indistinguishable from two
    unrelated agents.

    `status` is TURN STATE, not liveness. It is stamped at transitions, so a
    session that died mid-turn leaves `busy` behind forever. Never age it as a
    heartbeat; pair it with /proc.
    """

    pid: int
    session_id: str
    status: str
    kind: str
    cwd: str
    socket_path: str
    proc_start: str
    updated_at: float
    tmux: Optional[str] = None


def read_session_info(pid: int) -> Optional[SessionInfo]:
    """Read the sidecar. Returns None with a stated reason, never a partial."""
    path = sessions_dir() / f"{pid}.json"
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: session sidecar unreadable for pid {pid}: {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: session sidecar malformed for pid {pid}: {e}", file=sys.stderr)
        return None
    session_id = data.get("sessionId")
    if not session_id:
        print(f"⚠️ MACF: session sidecar for pid {pid} names no sessionId", file=sys.stderr)
        return None
    return SessionInfo(
        pid=pid,
        session_id=session_id,
        status=str(data.get("status") or "unknown"),
        kind=str(data.get("kind") or "unknown"),
        cwd=str(data.get("cwd") or ""),
        # Prefer the path the client PUBLISHED over one we construct. Constructing
        # it duplicates the client's layout decision in our code, where it drifts.
        socket_path=str(data.get("messagingSocketPath") or (socket_dir() / f"{pid}.sock")),
        proc_start=str(data.get("procStart") or ""),
        updated_at=float(data.get("updatedAt") or 0) / 1000.0,
        tmux=data.get("tmux"),
    )


def live_sessions() -> list:
    """Every session with a sidecar whose process is still alive."""
    out = []
    try:
        names = os.listdir(sessions_dir())
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: session dir unreadable (cannot enumerate): {e}", file=sys.stderr)
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            pid = int(name[: -len(".json")])
        except ValueError:
            continue
        if proc_start_ticks(pid) is None:
            continue
        info = read_session_info(pid)
        if info is not None:
            out.append(info)
    return sorted(out, key=lambda i: i.pid)


def resolve_target(session_id: str):
    """Choose ONE process for a conversation, and report any ambiguity.

    THE AMBIGUOUS TARGET IS REAL AND WAS OBSERVED, NOT IMAGINED. Interrupting and
    restarting a supervised session can leave a background twin that resumes the
    same conversation and inherits the same subscriptions. Both processes are
    legitimate and live, so the incarnation check does not help: it guards a
    RECYCLED pid, not a DELIBERATE fork.

    Returns (chosen_or_None, all_candidates). The caller MUST surface a
    len(candidates) > 1 result rather than resolving it invisibly -- an agent may
    decline to be told about the WORLD but never about ITSELF, and "there are two
    of you" is about itself.

    THE CHOICE RULE IS A HEURISTIC AND IS LABELLED AS ONE. Newest process start
    wins, on the reasoning that a restart creates the new process while the twin
    is the one that failed to die -- so the newest is the one a human is looking
    at. NOT YET MEASURED. What would confirm it: induce a fork, then check which
    pid owns the foreground terminal. Until then this is a stated assumption, not
    a finding, and it is written here so the next reader can attack it.
    """
    candidates = [s for s in live_sessions() if s.session_id == session_id]
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], candidates

    def start_key(info):
        try:
            return int(info.proc_start)
        except (TypeError, ValueError):
            return -1

    ranked = sorted(candidates, key=start_key, reverse=True)
    print(
        f"⚠️ MACF: {len(candidates)} live processes serve conversation "
        f"{session_id[:8]} (pids {[c.pid for c in candidates]}) -- delivering to "
        f"{ranked[0].pid} by newest-start heuristic, and recording the ambiguity",
        file=sys.stderr,
    )
    return ranked[0], candidates


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
