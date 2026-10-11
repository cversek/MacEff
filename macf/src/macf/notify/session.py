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
import calendar
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from macf.supervisor import ancestor_pids

SESSIONS_DIRNAME = ".claude/sessions"
SOCKET_DIRNAME = "cc-socks"


def sessions_dir() -> Path:
    return Path(os.path.expanduser("~")) / SESSIONS_DIRNAME


def jobs_dir() -> Path:
    """Where the client's background daemon keeps one ``<short>/state.json`` per job."""
    return Path(os.path.expanduser("~")) / ".claude" / "jobs"


def socket_dir() -> Path:
    """Where the client puts ``<pid>.sock``. ``$XDG_RUNTIME_DIR/cc-socks`` when the
    variable is set; otherwise ``/run/user/<uid>`` on Linux and ``/tmp`` on macOS,
    which has no runtime dir (MEASURED: the macOS client publishes
    ``messagingSocketPath: /tmp/cc-socks/<pid>.sock`` in its sidecar)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        runtime = "/tmp" if sys.platform == "darwin" else f"/run/user/{os.getuid()}"
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

    Linux only. On a host without procfs this returns None for every pid, so
    callers must go through ``proc_start``, which dispatches on the platform.

    `comm` may contain spaces and parentheses, so everything is parsed relative to
    the LAST ')' rather than by splitting the whole line.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except (FileNotFoundError, ProcessLookupError):
        return None  # noqa: MACEFF003 - not running is this function's answer, not a failure
    except (PermissionError, OSError) as e:
        print(f"⚠️ MACF: /proc unreadable for pid {pid}: {e}", file=sys.stderr)
        return None
    try:
        tail = data[data.rfind(")") + 2:].split()
        return int(tail[19])
    except (IndexError, ValueError) as e:
        print(f"⚠️ MACF: /proc stat unparseable for pid {pid}: {e}", file=sys.stderr)
        return None


_ASCTIME = "%a %b %d %H:%M:%S %Y"


def _proc_start_darwin(pid: int) -> Optional[str]:
    """Process start as the client records it on macOS: ``asctime`` of the start
    instant in UTC. MEASURED against the client's own sidecar and credential:
    ``ps -o lstart=`` gives the same instant in local time to the second, and
    ``time.asctime(time.gmtime(...))`` of it reproduces the stored string exactly.
    """
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: ps unavailable for pid {pid}: {e}", file=sys.stderr)
        return None
    raw = out.stdout.strip()
    if out.returncode != 0 or not raw:
        return None  # not running: an ordinary answer for every caller, so nothing to warn about
    try:
        local = time.strptime(raw, _ASCTIME)
        return time.asctime(time.gmtime(time.mktime(local)))
    except (ValueError, OverflowError) as e:
        print(f"⚠️ MACF: ps lstart unparseable for pid {pid}: {e!r} {raw!r}", file=sys.stderr)
        return None


def proc_start(pid: int) -> Optional[str]:
    """The process-start fingerprint in the form the client STORES on this platform.

    Linux: clock ticks since boot, as a decimal string (``/proc/<pid>/stat``).
    macOS: ``asctime`` of the start instant in UTC (see ``_proc_start_darwin``).
    None when the pid is not running or the platform has no known source --
    which every caller treats as "not live", so an unknown platform fails closed.
    The wake, the readout, the MacEff channel's peer check and the transcript monitor
    all ask through here, so a pid that is not running is an answer, not a warning.
    """
    if sys.platform.startswith("linux"):
        ticks = proc_start_ticks(pid)
        return None if ticks is None else str(ticks)
    if sys.platform == "darwin":
        return _proc_start_darwin(pid)
    print(f"⚠️ MACF: no process-start source on {sys.platform}", file=sys.stderr)
    return None


def proc_start_key(value) -> Optional[int]:
    """Canonical integer for a stored ``procStart`` in either platform form, for
    equality and for newest-start ordering. None when it is neither form."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return calendar.timegm(time.strptime(text, _ASCTIME))
    except (ValueError, OverflowError) as e:
        print(f"⚠️ MACF: procStart is neither ticks nor UTC asctime: {text!r} ({e})", file=sys.stderr)
        return None


def proc_start_from_key(key: int) -> str:
    """Inverse of ``proc_start_key`` in this platform's stored form; lets a test
    say "one incarnation later" without knowing which platform it is on."""
    if sys.platform == "darwin":
        return time.asctime(time.gmtime(key))
    return str(key)


def verify_incarnation(pid: int, declared_start) -> bool:
    """Bind the credential to a process INCARNATION rather than to a number.

    Without this the design addresses a pid, and a recycled pid becomes
    addressable with a stale credential.

    THE TYPES DIFFER AND THIS IS THE WHOLE REASON THE CHECK GOES UNWRITTEN.
    The credential stores the value as a STRING; /proc yields an INT. On Linux
    both are clock ticks since boot -- same unit, measured -- so a naive `==` is
    False for every well-formed credential, the check refuses every legitimate
    wake, and the obvious remedy is to delete it. On macOS the client stores a
    UTC asctime string instead, and there is no /proc at all. Both sides go
    through ``proc_start_key`` so the comparison is between canonical integers
    whatever the platform wrote.

    A credential with NO declared start fails CLOSED. It is an authorization
    check, not an advisory one, so absence is not permission.
    """
    if declared_start is None:
        print(
            f"⚠️ MACF: no recorded start time for pid {pid} (refusing: "
            "an incarnation check cannot fail open)",
            file=sys.stderr,
        )
        return False
    actual = proc_start_key(proc_start(pid))
    if actual is None:
        return False
    declared = proc_start_key(declared_start)
    if declared is None:
        print(f"⚠️ MACF: recorded start time unusable for pid {pid} (refusing): {declared_start!r}", file=sys.stderr)
        return False
    if declared != actual:
        print(
            f"⚠️ MACF: incarnation mismatch for pid {pid} (refusing: the recorded start "
            f"is stale against a recycled pid) declared={declared} actual={actual}",
            file=sys.stderr,
        )
        return False
    return True


def descends_from(pid: int, ancestor_pid: int, ancestor_start) -> bool:
    """True when *pid* is *ancestor_pid* or below it, and the ancestor is the same
    INCARNATION it declared.

    For a peer check on a local socket (MIS-0002-R122
    (pd_MUST_check_channel_peer_lineage)): the kernel names the peer's pid and uid,
    but every command an agent runs has the same uid and descends from the same
    session, so the uid alone cannot tell the agent's channel from anything else
    the agent runs. Lineage under the live session narrows it to that session's
    process tree. The incarnation check stops a recycled session pid from passing,
    and a channel left running after its session ended fails because its old
    session is no longer its ancestor.
    """
    if not verify_incarnation(ancestor_pid, ancestor_start):
        return False
    if ancestor_pid not in ancestor_pids(pid):
        print(f"⚠️ MACF: pid {pid} does not descend from pid {ancestor_pid} (refusing)", file=sys.stderr)
        return False
    return True


def published_socket(pid: int) -> Optional[Path]:
    """The socket path the client published in ``<pid>.json``, or None if it gave none.

    A missing sidecar is not reported here: the caller falls back to the derived
    path, and ``read_session_info`` is where a bad sidecar is diagnosed.
    """
    try:
        with open(sessions_dir() / f"{pid}.json") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None  # noqa: MACEFF003 - no sidecar means nothing was published; the caller derives the path
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: session sidecar unreadable for pid {pid}; deriving its socket path: {e}",
              file=sys.stderr)
        return None
    value = data.get("messagingSocketPath") if isinstance(data, dict) else None
    return Path(value) if isinstance(value, str) and value else None


def socket_path_for(pid: int) -> Path:
    """Where ``pid``'s socket is: the published path when the client gave one.

    Deriving the path duplicates the client's layout decision in our code, where
    it drifts, and it has: without ``XDG_RUNTIME_DIR``, sessions of different
    client versions in one container published both ``/tmp/cc-socks/`` and
    ``/tmp/cc-socks-<uid>/``, while the derivation looks under
    ``/run/user/<uid>``, which a container usually lacks. The derived path
    remains the fallback for a client that publishes none.
    """
    return published_socket(pid) or socket_dir() / f"{pid}.sock"


def find_socket(pid: int) -> Optional[Path]:
    path = socket_path_for(pid)
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


@dataclass
class HostedSession:
    """A live session hosted by Claude Code's own background daemon.

    MEASURED on 2.1.296: a worker started cold carries its flags in argv, but a
    respawned one runs in a pre-started spare whose argv is generic, so the job
    record is the one place the launch flags always are. ``channels`` is None
    when that record is missing or unreadable: unknown, never "none".
    """
    pid: int
    session_id: str
    status: str
    cwd: str
    channels: Optional[list]


def _respawn_flags(session_id: str) -> Optional[list]:
    path = jobs_dir() / session_id[:8] / "state.json"
    try:
        with open(path) as fh:
            flags = json.load(fh).get("respawnFlags")
    except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: job record unreadable for session {session_id[:8]}: {e}", file=sys.stderr)
        return None
    return flags if isinstance(flags, list) else None


def _channels_from_flags(flags: list) -> list:
    """The channel entries in a job's launch flags.

    MEASURED on 2.1.296: ``--channels=X`` is kept as one token, and ``--channels`` takes
    every value up to the next flag.
    """
    channels = []
    taking = False
    for f in flags:
        if not isinstance(f, str):
            taking = False
        elif f.startswith("--channels="):
            channels.append(f.split("=", 1)[1])
            taking = False
        elif f == "--channels":
            taking = True
        elif f.startswith("-"):
            taking = False
        elif taking:
            channels.append(f)
    return channels


def harness_hosted_sessions() -> list:
    """Live sessions the client's background daemon hosts, with their channels.

    The first thing MIS-0002-R66 (pd_MUST_adopt_harness_supervisor) needs: a readout
    that sees what the harness's own supervisor runs instead of reporting nothing.
    """
    hosted = []
    for info in live_sessions():
        if info.kind != "bg":
            continue
        flags = _respawn_flags(info.session_id)
        channels = None if flags is None else _channels_from_flags(flags)
        hosted.append(HostedSession(pid=info.pid, session_id=info.session_id,
                                    status=info.status, cwd=info.cwd, channels=channels))
    return hosted


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
        if proc_start(pid) is None:
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

    THE MECHANISM IS NOW MEASURED, so the rule is no longer only a heuristic.

    A supervised session's process tree is:

        tmux pane -> supervisor -> client        (client in its OWN session)

    The client is spawned with a new session id, which detaches it from the
    pane's controlling terminal. So an interrupt typed in the pane goes to the
    SUPERVISOR's foreground process group and NOT to the client. If the
    supervisor dies there, the client is orphaned and keeps running; the next
    supervisor spawns a fresh client with a continue flag, and two processes then
    serve one conversation. The setsid that causes this was introduced to fix a
    terminal file-descriptor leak -- one fix's remedy is the other's cause, which
    is why it reads as mysterious from either end alone.

    The twin is therefore the OLDER process (the orphan) and the current one is
    NEWER, which is what newest-start selects. But an ORDERING is a weaker answer
    than an IDENTITY, and an authoritative one exists:

    **THE SUPERVISOR REGISTRY NAMES ITS OWN CURRENT CHILD.** A live supervisor
    records the pid it spawned. Asking it is not a guess -- it is the answer from
    the party that made the decision. So: prefer the live supervisor's registered
    child, and fall back to newest-start only when no supervisor claims any
    candidate (an unsupervised session, or a registry we cannot read).

    Fallback rather than requirement, deliberately: an unsupervised session is
    ordinary, not an error, and a notifier that refuses to address one would fail
    closed on an advisory path.
    """
    candidates = [s for s in live_sessions() if s.session_id == session_id]
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], candidates

    def start_key(info):
        key = proc_start_key(info.proc_start)
        return -1 if key is None else key

    ranked = sorted(candidates, key=start_key, reverse=True)
    supervised = supervised_child_pids()
    claimed = [c for c in ranked if c.pid in supervised]
    if claimed:
        chosen, rule = claimed[0], "live supervisor's registered child (authoritative)"
    else:
        chosen, rule = ranked[0], "newest process start (fallback -- no supervisor claims one)"
    print(
        f"⚠️ MACF: {len(candidates)} live processes serve conversation "
        f"{session_id[:8]} (pids {[c.pid for c in candidates]}) -- delivering to "
        f"{chosen.pid} by {rule}, and recording the ambiguity",
        file=sys.stderr,
    )
    return chosen, candidates


def supervised_child_pids() -> set:
    """Pids that a LIVE supervisor currently claims as its own child.

    Authoritative where it answers, and silent where it does not. Import is
    deferred and failure is swallowed to a warning because this is an ADVISORY
    refinement: a notifier must not fail to deliver because a supervision
    registry could not be read.
    """
    try:
        from ..supervisor import _iter_live_supervisors
    except ImportError as e:
        print(f"⚠️ MACF: supervisor registry unavailable (falling back to newest-start): {e}", file=sys.stderr)
        return set()
    pids = set()
    try:
        for data in _iter_live_supervisors():
            child = data.get("child_pid")
            if isinstance(child, int):
                pids.add(child)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"⚠️ MACF: supervisor registry unreadable (falling back to newest-start): {e}", file=sys.stderr)
        return set()
    return pids


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
        if socket_path_for(pid).exists() and proc_start(pid) is not None:
            found.append(pid)
    return sorted(found)
