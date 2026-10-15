"""The session unit: an agent's Claude Code session as a unit its primal daemon parents.

MIS-0002-R12 (pd_MUST_start_units_itself): the daemon starts each unit as its own child.
The legacy harness cannot be that child. ``tmux new-session`` asks a tmux server to run
the session, and the server detaches from whoever started it, so the process the
daemon would start ends at once while the session lives on under the server, out of
the daemon's reach. Restarts there belong to MacEff's auto-restart loop inside the pane.

This wrapper keeps the chain primal daemon → wrapper → tmux server → ``claude``:
- it runs the agent's own tmux server in the foreground (``tmux -D``), as its child;
- the server lives on a socket of its own, under a private directory in the daemon's
  runtime directory, so no other login's sessions can keep it alive or share it;
- it creates the agent's session there, running the harness child script, which runs
  ``claude -c`` directly with no restart loop around it: restarts belong to the daemon
  alone, under the unit's declared policy;
- it turns the server's ``exit-empty`` on once the session exists, so the server, and
  then this wrapper, end when ``claude`` does. The daemon sees the unit exit.

Every tmux client reaches the server through ``TMUX_TMPDIR`` set to that directory,
with tmux's default socket name inside it: the attach helpers, and the mail clock by a
variable in its declared environment, with no change to the clock itself.

**Liveness** (MIS-0002-R14) comes from the session's transcript monitor, which the
operator chose on 2026-10-12: the monitor's loop reads the transcript and confirms the
client process each pass, so its beat means both run. The wrapper hands the monitor
the unit's identity through ``MACF_PD_SESSION_*`` variables naming this wrapper's pid,
the process the daemon started, and removes its own ``MACF_PD_UNIT`` and
``MACF_PD_LIVENESS_S`` from the session's environment, so no other process the session
starts can report liveness as this unit.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

from macf.notify.session import proc_start
from macf.pd.interface import check_socket_path, runtime_dir
from macf.pd.liveness import (ENV_HOME, ENV_INTERVAL, ENV_SESSION_INTERVAL, ENV_SESSION_PID,
                              ENV_SESSION_UNIT, ENV_UNIT)

#: What the agent's tmux directory is called inside the runtime directory, after the
#: agent's session identifier.
TMUX_DIR_SUFFIX = ".tmux"

#: How long the wrapper waits for its tmux server to answer before giving up.
READY_TIMEOUT_S = 10.0

#: Exit status when the session could not be created: the server is stopped, and the
#: daemon restarts the unit under its declared policy. Used for what a later start can
#: clear, such as a server that still serves an earlier session.
EXIT_NOT_STARTED = 1
#: Exit status when no restart can help: the project directory is missing, the socket
#: path is too long, or the tmux directory is not private. 78 is in a unit's default
#: ``no_restart``, so the daemon stops retrying and records why (Ira, on #652).
EXIT_REFUSED = 78

#: How long the session's own process group gets after SIGTERM before SIGKILL, once the
#: server has gone. A unit's declared ``stop_grace_s`` must exceed it, or the daemon's
#: SIGKILL reaches the wrapper first and nothing is left to stop the session.
PANE_GRACE_S = 10.0
#: How long a new pane has to call setsid() before its pid is taken as its group.
PANE_SETSID_WAIT_S = 2.0
#: Where a wrapper names its session's pane groups, in its private tmux directory, so the
#: next wrapper can end a session that a SIGKILL left running.
PANE_RECORD = "pane_groups.json"


def _group_alive(pgid: int) -> bool:
    """True while a member of process group *pgid* runs. A zombie does not count: it has
    exited, and only waits for a parent to reap it, which may be slow for a pane orphaned by
    its server. On Linux the members are read from /proc, elsewhere (macOS) from ``ps``; a
    signal 0, which also counts a zombie, is the probe only when neither can be read."""
    proc = Path("/proc")
    if proc.is_dir() and (proc / "self" / "stat").exists():
        for stat in proc.glob("[0-9]*/stat"):
            try:
                fields = stat.read_text().rpartition(")")[2].split()
            except OSError:
                continue
            if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
                return True
        return False
    try:
        out = subprocess.run(["ps", "-A", "-o", "pgid=,stat="], capture_output=True,
                             text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is not None:
        return any(len(f) == 2 and f[0] == str(pgid) and not f[1].startswith("Z")
                   for f in (line.split() for line in out.splitlines()))
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # a member we may not signal still lives


def pane_group(pane_pid: int, own: int, timeout: float = PANE_SETSID_WAIT_S) -> Optional[int]:
    """The process group of a pane's process, once it has one of its own; None if it is gone.

    tmux forks a pane and the child calls ``setsid()`` before it runs the pane's command. Read
    in between, the child still has the server's group, which is this unit's, and a stop would
    then have no group to reap. So wait for the group to differ from *own*. If it never does
    within *timeout*, the pane's pid is the answer: ``setsid()`` makes the group the pid's own.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            group = os.getpgid(pane_pid)
        except ProcessLookupError:
            return None  # noqa: MACEFF003 - a pane already gone has no group to reap; None is the documented answer
        if group != own:
            return group
        if time.monotonic() >= deadline:
            return pane_pid
        time.sleep(0.01)


def reap_group(pgid: int, grace: float = PANE_GRACE_S, poll: float = 0.1,
               leader_start: Optional[str] = None) -> bool:
    """Stop process group *pgid*: SIGTERM, then SIGKILL after *grace* seconds; True once it is
    gone. tmux runs each pane in a session, and so a process group, of its own, so the daemon's
    stop, which signals the unit's group, reaches the session only through the server's SIGHUP.
    A session that outlives that would run on after the unit ended, and a restart would start a
    second ``claude -c`` beside it (MIS-0002-R48 (outside_stop_MUST_override_gates)).

    *leader_start* is the start of the group's leader, the pane, read when the session was made.
    A group number is free again once all its members have gone, so before each signal the
    group is confirmed as the session's: a leader under that number with another start means
    the number now names someone else's group, which is left alone."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, grace)):
        if not _group_alive(pgid):
            return True
        if not _still_ours(pgid, leader_start):
            print(f"⚠️ MACF: session unit: process group {pgid} is no longer the session's: its "
                  f"number now leads another process; not signalling it", file=sys.stderr)
            return True
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and _group_alive(pgid):
            time.sleep(poll)
    return not _group_alive(pgid)


def _still_ours(pgid: int, leader_start: Optional[str]) -> bool:
    """Whether group *pgid* is still the one whose leader started at *leader_start*. A group
    whose leader has exited, members still running, keeps its number, which can't be reused
    while any member lives; so only a leader with a different start says the group is new."""
    if leader_start is None:
        return True
    from macf.pd.core import group_members
    return all(start == leader_start for pid, start in group_members(pgid) if pid == pgid)


def tmux_dir(agent: str, base: Optional[Path] = None) -> Path:
    """The private directory holding the agent's tmux socket, ``TMUX_TMPDIR`` for every
    client. ``agent`` is the session identifier (``TheHarborMaster_ee5cd8``)."""
    return (base or runtime_dir()) / f"{agent}{TMUX_DIR_SUFFIX}"


def tmux_socket(agent: str, base: Optional[Path] = None) -> Path:
    """Where tmux puts the server's socket under ``tmux_dir``: tmux's own layout."""
    return tmux_dir(agent, base) / f"tmux-{os.getuid()}" / "default"


def client_environment(agent: str, base: Optional[Path] = None,
                       environ: Optional[Mapping[str, str]] = None) -> Optional[Dict[str, str]]:
    """The environment a tmux client needs to reach the agent's session unit, or None when
    no session unit's server socket exists here (the legacy harness's default server)."""
    if not tmux_socket(agent, base).exists():
        return None
    env = {k: v for k, v in (os.environ if environ is None else environ).items() if k != "TMUX"}
    env["TMUX_TMPDIR"] = str(tmux_dir(agent, base))
    return env


def _private_dir(path: Path) -> Path:
    """Create *path* 0700, or refuse one that another user owns or others can open: a
    socket in it is a keyboard into the agent's session."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise PermissionError(f"{path} is not private to this user (mode {st.st_mode & 0o777:o})")
    return path


def session_environment(environ: Mapping[str, str], wrapper_pid: int, tmux_tmpdir: Path,
                        extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """The environment the tmux server starts with, which tmux copies into every session.

    The unit's own variables become the session's: ``MACF_PD_UNIT`` and its interval
    are removed, and ``MACF_PD_SESSION_*`` name the unit and this wrapper's pid for the
    transcript monitor. Without a declared unit there is no liveness to hand on."""
    env = {k: v for k, v in environ.items() if k not in (ENV_UNIT, ENV_INTERVAL, "TMUX", "TMUX_PANE")}
    unit, interval = environ.get(ENV_UNIT), environ.get(ENV_INTERVAL)
    if unit and interval and environ.get(ENV_HOME):
        env[ENV_SESSION_UNIT] = unit
        env[ENV_SESSION_INTERVAL] = interval
        env[ENV_SESSION_PID] = str(wrapper_pid)
    env["TMUX_TMPDIR"] = str(tmux_tmpdir)
    env.update(extra or {})
    return env


def proxy_environment(port: int, probe: Optional[Callable[[str], bool]] = None) -> Dict[str, str]:
    """The proxy attachment, probed as the legacy start script does: a proxy that does
    not answer leaves the session direct rather than down. The base URL and the
    first-party flag are one assignment, or the client silently falls back to a 200K
    window (``utils.harness.render_start``)."""
    url = f"http://127.0.0.1:{port}/"

    def _answers(u: str) -> bool:
        try:
            urllib.request.urlopen(u, timeout=2)
            return True
        except urllib.error.HTTPError:
            return True       # it answered, with an error status: it is up
        except (OSError, ValueError):
            return False

    if not (probe or _answers)(url):
        return {}
    return {"ANTHROPIC_BASE_URL": f"http://localhost:{port}",
            "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL": "1"}


def _tmux(tmux: str, env: Mapping[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([tmux, *args], env=dict(env), capture_output=True, text=True, timeout=15)


def run(agent: str, child: Path, *, project_dir: Optional[Path] = None,
        conf: Optional[Path] = None, extra_env: Optional[Mapping[str, str]] = None,
        environ: Optional[Mapping[str, str]] = None, tmux: str = "tmux",
        base: Optional[Path] = None, ready_timeout: float = READY_TIMEOUT_S) -> int:
    """Be the session unit until the session ends; return the tmux server's exit status.

    ``child`` is the command the session runs (the harness child script). A declared
    project directory that is missing is reported and the session is not started, since
    ``claude -c`` would resume a different conversation from anywhere else."""
    environ = os.environ if environ is None else environ
    if project_dir is not None and not Path(project_dir).is_dir():
        print(f"⚠️ MACF: session unit: the declared project directory {project_dir} does not exist; "
              f"not starting, because 'claude -c' would resume a different conversation",
              file=sys.stderr)
        return EXIT_REFUSED
    try:
        # MIS-0002-R129 (adapter_MUST_check_socket_path_length): tmux's own refusal names
        # only the path, after the wrapper has started a server that cannot listen.
        check_socket_path(tmux_socket(agent, base))
    except OSError as e:
        print(f"⚠️ MACF: session unit: {e}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        directory = _private_dir(tmux_dir(agent, base))
    except PermissionError as e:
        print(f"⚠️ MACF: session unit: {e}; not starting a server others could reach", file=sys.stderr)
        return EXIT_REFUSED
    env = session_environment(environ, os.getpid(), directory, extra_env)
    if tmux_socket(agent, base).exists() and _tmux(tmux, env, "has-session").returncode == 0:
        # The socket is private, so a server answering on it is this agent's, from an
        # earlier wrapper whose session still runs: a second would double the session.
        print(f"⚠️ MACF: session unit: a tmux server already serves {agent}; not starting a second",
              file=sys.stderr)
        return EXIT_NOT_STARTED
    # No server answers, so no wrapper serves this agent: a session a killed predecessor left
    # behind is ended before a second one starts beside it.
    _reap_predecessor(directory, agent)
    server_cmd = [tmux] + (["-f", str(conf)] if conf and Path(conf).is_file() else ["-f", "/dev/null"]) + ["-D"]
    server = subprocess.Popen(server_cmd, env=env, stdin=subprocess.DEVNULL)

    def _stop(signum, _frame):
        # The daemon's stop reaches the whole process group, the server included; this
        # covers a signal sent to the wrapper alone.
        if server.poll() is None:
            server.terminate()

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _stop)

    deadline = time.monotonic() + ready_timeout
    while _tmux(tmux, env, "show-options", "-s", "exit-empty").returncode != 0:
        if server.poll() is not None or time.monotonic() > deadline:
            print(f"⚠️ MACF: session unit: the tmux server did not answer within {ready_timeout:g} s",
                  file=sys.stderr)
            _stop(None, None)
            server.wait()
            return EXIT_NOT_STARTED
        time.sleep(0.1)

    # -P prints the new pane's pid in the reply that creates it, while the server is
    # certainly up. Asked for afterwards (list-panes), it was lost when a stop reached the
    # server in between, and the session was then never reaped: CI saw it twice.
    new = ["new-session", "-d", "-P", "-F", "#{pane_pid}", "-s", agent] + (["-c", str(project_dir)] if project_dir else []) + [str(child)]
    made = _tmux(tmux, env, *new)
    if made.returncode != 0:
        print(f"⚠️ MACF: session unit: could not create session {agent}: "
              f"{(made.stderr or made.stdout).strip()[:200]}", file=sys.stderr)
        _stop(None, None)
        server.wait()
        return EXIT_NOT_STARTED
    # The session's process group, read now while the pane exists: after the server has gone
    # it is the one thing that can still name the session's processes (reap_group).
    panes = made.stdout.split()
    pane_groups: Dict[int, Optional[str]] = {}       # the group, and its leader's start
    for pane in panes:
        try:
            group = pane_group(int(pane), os.getpgid(0))
        except ValueError:
            print(f"⚠️ MACF: session unit: tmux named a pane pid {pane!r} that is not a number; "
                  f"a stop will not reach that pane's group", file=sys.stderr)
            continue
        if group is not None:
            pane_groups[group] = proc_start(group)
    # Kept where the next wrapper looks, so a SIGKILL that ends this one before its reap
    # still leaves the session's group named to whoever starts next.
    _write_pane_record(directory, pane_groups)
    # Only now, with a session in it, may the server end when it is empty: from here on
    # the session's end is the server's, and the server's is this unit's.
    _tmux(tmux, env, "set-option", "-s", "exit-empty", "on")
    print(f"📡 MACF: session unit: session {agent} runs under tmux server {server.pid} "
          f"(TMUX_TMPDIR={directory})", file=sys.stderr)
    status = server.wait()
    # The unit ends only when the session has: a pane that outlived the server's hangup is
    # stopped here, so a restart never starts a second session beside it.
    for pgid, leader_start in pane_groups.items():
        if not reap_group(pgid, leader_start=leader_start):
            print(f"⚠️ MACF: session unit: process group {pgid} of session {agent} survived SIGKILL",
                  file=sys.stderr)
    _pane_record(directory).unlink(missing_ok=True)
    _remove_leftovers(tmux, env, directory)
    return status


def _pane_record(directory: Path) -> Path:
    return directory / PANE_RECORD


def _write_pane_record(directory: Path, pane_groups: Mapping[int, Optional[str]]) -> None:
    """Name the session's pane groups, with their leaders' starts, for the next wrapper."""
    path = _pane_record(directory)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps([[pgid, start] for pgid, start in pane_groups.items()]))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError as e:
        print(f"⚠️ MACF: session unit: could not record the pane groups ({e}); a wrapper killed "
              f"outright would leave this session for the next to find unnamed", file=sys.stderr)


def _reap_predecessor(directory: Path, agent: str) -> None:
    """End the session a wrapper killed outright left running, from the groups it recorded.

    A wrapper reaps its pane's group itself once its server has gone, but a SIGKILL, the
    daemon's after a stop's grace or the kernel's out-of-memory killer, ends it first, and a
    pane that ignores the hangup runs on. Each recorded group is reaped only while its
    leader's start still matches (reap_group), and one recorded with no start is left: its
    number can't be told from another's."""
    path = _pane_record(directory)
    try:
        recorded = json.loads(path.read_text())
    except FileNotFoundError:
        return  # noqa: MACEFF003 - no record is the normal case: no wrapper was killed before its reap
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: session unit: the previous pane record is unreadable ({e}); not reaping "
              f"from it", file=sys.stderr)
        path.unlink(missing_ok=True)
        return
    for entry in recorded if isinstance(recorded, list) else []:
        if not (isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], int) and entry[1]):
            continue
        pgid, start = entry
        if _group_alive(pgid):
            print(f"⚠️ MACF: session unit: a previous session of {agent} outlived its wrapper "
                  f"(process group {pgid}); ending it before starting another", file=sys.stderr)
            if not reap_group(pgid, leader_start=start):
                print(f"⚠️ MACF: session unit: process group {pgid} survived SIGKILL", file=sys.stderr)
    path.unlink(missing_ok=True)


def _remove_leftovers(tmux: str, env: Mapping[str, str], directory: Path) -> None:
    """Remove what the ended server left in its tmux directory: the socket tmux does not
    unlink on Linux, then the directories (Ira, on #652). Nothing goes while a server still
    answers on the socket, and a directory holding anything else stays."""
    socket = directory / f"tmux-{os.getuid()}" / "default"
    if socket.is_socket() and _tmux(tmux, env, "has-session").returncode != 0:
        try:
            socket.unlink()
        except OSError:
            pass
    for path in (socket.parent, directory):
        if not path.is_dir() or any(path.iterdir()):
            break                      # something else is in it: it stays
        try:
            path.rmdir()
        except OSError as e:
            print(f"⚠️ MACF: session unit: could not remove {path}: {e}", file=sys.stderr)
            break


def main(argv: Optional[List[str]] = None) -> int:
    """``macf_tools harness unit``: the session unit's command in a declaration."""
    import argparse
    from dataclasses import replace

    from macf.utils.harness import default_params, load_settings

    parser = argparse.ArgumentParser(prog="macf_tools harness unit")
    parser.add_argument("--agent", help="the session identifier (default: from the calling card)")
    parser.add_argument("--home", help="the agent home (default: MACEFF_AGENT_HOME_DIR)")
    parser.add_argument("--project-dir", help="where the session starts (default: the installed choice)")
    parser.add_argument("--no-proxy", action="store_true", help="never attach the API proxy")
    args = parser.parse_args(argv)
    p = load_settings(default_params(agent=args.agent, home=args.home))
    if args.project_dir:
        p = replace(p, project_dir=Path(args.project_dir))
    extra = {"MACF_CONTEXT_WINDOW": str(p.context_window), "TERM": p.term}
    if not args.no_proxy:
        extra.update(proxy_environment(p.proxy_port))
    conf = p.home / f".tmux-{p.agent}.conf"
    return run(p.agent, p.child_path, project_dir=p.project_dir, conf=conf, extra_env=extra)


if __name__ == "__main__":
    sys.exit(main())
