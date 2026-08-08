"""Auto-restarting process supervisor with multi-process management.

Manages multiple supervised processes, each in its own terminal window.
Provides pm2-style process listing with stats.

Usage:
    macf_tools auto-restart launch -- claude -c
    macf_tools auto-restart launch --name manny -- ssh pa_manny@localhost
    macf_tools auto-restart list                 # ps-style listing
    macf_tools auto-restart restart <pid>        # trigger restart
    macf_tools auto-restart disable <pid>        # stop auto-restart
    macf_tools auto-restart status <pid>         # detailed status

Architecture:
    launch → opens new terminal → runs supervisor loop in that terminal
    supervisor loop → spawns command as child, restarts on exit
    registry → /tmp/macf/auto-restart/*.json (one per supervised process)
    signals → SIGUSR1 (restart child), SIGUSR2 (disable loop)
"""

import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

def _resolve_registry_dir() -> Path:
    """Per-user supervisor registry directory.

    A single global `/tmp/macf/auto-restart` is owned by whichever uid creates
    it first, so the *second* agent user on a shared host or container dies with
    PermissionError the moment its supervisor starts — and the symptom ("the
    tmux session vanished instantly") reads as anything but a permissions
    problem. A shared directory is also a shared namespace: `auto-restart list`
    would show other users' supervisors, and lookup-by-name could match them.

    Resolution order:
    1. `$XDG_RUNTIME_DIR/macf/auto-restart` — per-user by construction, and the
       same base the proxy already uses for its pid/log files.
    2. `/tmp/macf-{uid}/auto-restart` — uid-qualified fallback, created 0700.
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "macf" / "auto-restart"
    return Path(f"/tmp/macf-{os.getuid()}") / "auto-restart"


REGISTRY_DIR = _resolve_registry_dir()


def _registry_file(pid: int) -> Path:
    return REGISTRY_DIR / f"{pid}.json"


def _ensure_registry_dir() -> None:
    """Create the registry dir owner-only, so it can never be hijacked."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def _write_registry(pid: int, data: dict):
    """Write process stats to registry."""
    _ensure_registry_dir()
    _registry_file(pid).write_text(json.dumps(data, indent=2))


def _read_registry(pid: int) -> dict:
    f = _registry_file(pid)
    if not f.exists():
        return {}
    return json.loads(f.read_text())


def _update_registry(pid: int, **kwargs):
    data = _read_registry(pid)
    data.update(kwargs)
    _write_registry(pid, data)


def _cleanup_registry(pid: int):
    f = _registry_file(pid)
    if f.exists():
        f.unlink()


def _notify_telegram(message: str, prefix: str = ""):
    try:
        from macf.channels.telegram import send_telegram_notification
        send_telegram_notification(message, prefix=prefix)
    except (ImportError, OSError, ConnectionError) as e:
        print(f"⚠️ MACF: supervisor telegram notification failed: {e}", file=sys.stderr)


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining = minutes % 60
    if hours < 24:
        return f"{hours}h{remaining}m"
    days = hours // 24
    remaining_h = hours % 24
    return f"{days}d{remaining_h}h"


# Linux terminal emulators we know how to drive, in preference order.
# x-terminal-emulator (the Debian "alternatives" symlink) is tried LAST as a
# generic fallback and is resolved to its concrete target before dispatch.
_LINUX_TERMINALS = [
    "gnome-terminal", "ptyxis", "kgx", "tilix", "konsole",
    "lxterminal", "foot", "xterm", "x-terminal-emulator",
]


def _shell_command_string(cmd: list) -> str:
    """Render *cmd* (an argv list) as a single POSIX-shell-safe string.

    For the consumers that re-parse their command argument through a shell
    (macOS AppleScript ``do script`` / iTerm2 ``command``, and legacy
    ``lxterminal -e``). ``shlex.quote`` keeps arguments that contain spaces or
    metacharacters intact, which the previous naive backslash/quote escaping
    did not.
    """
    return " ".join(shlex.quote(arg) for arg in cmd)


def _applescript_quote(s: str) -> str:
    """Escape *s* for embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _terminal_command_form(base: str, term_path: str, cmd: list) -> list:
    """Pure dispatch: given a terminal's *base* name and the *term_path* to
    invoke, return the launch argv for *cmd* (an argv list). No filesystem or
    PATH access, so this is deterministically unit-testable.

    Cardinal rule: pass *cmd* as SEPARATE argv elements for any terminal that
    execs its command argument directly. Collapsing the command into one
    ``" ".join(...)`` token makes argv-respecting terminals (gnome-terminal,
    ptyxis, konsole) try to exec the whole line as a single filename, e.g.
    ``Failed to find executable 'python3 -m macf.supervisor ...': No such
    file or directory``. Only legacy terminals whose flag genuinely takes one
    shell-reparsed string (lxterminal) get a quoted join.
    """
    if base.endswith(".wrapper"):
        base = base[: -len(".wrapper")]

    # `--` separator camp: program + args follow a literal `--`.
    if base in ("gnome-terminal", "ptyxis", "kgx", "tilix"):
        return [term_path, "--", *cmd]
    # `-e` + separate-argv camp: -e consumes the remaining argv tokens.
    if base in ("konsole", "xterm"):
        return [term_path, "-e", *cmd]
    # foot takes the command directly, with no separator flag.
    if base == "foot":
        return [term_path, *cmd]
    # Legacy single-string camp: -e wants one shell-reparsed string.
    if base == "lxterminal":
        return [term_path, "-e", _shell_command_string(cmd)]
    # Unknown terminal: the `--` convention is the most widely supported
    # argv-safe form among modern emulators.
    return [term_path, "--", *cmd]


def _terminal_argv(term: str, cmd: list) -> list:
    """Build the argv to launch *cmd* in Linux terminal *term* (a bare command
    name or a path).

    *term* is resolved through PATH (``shutil.which``) and then symlinks
    (``os.path.realpath``) so that (a) a bare name like ``"ptyxis"`` becomes a
    real executable path rather than a bogus cwd-relative one, and (b)
    ``x-terminal-emulator`` -- the Debian "alternatives" symlink, which on
    GNOME hosts points at ptyxis -- resolves to the concrete terminal, so its
    native invocation is used instead of the lossy ``-e <string>``
    compatibility interface that caused the original bug.
    """
    resolved = shutil.which(term) or term
    real = os.path.realpath(resolved)
    base = os.path.basename(real)
    return _terminal_command_form(base, real, cmd)


def _tmux_available() -> bool:
    """True if a tmux binary is on PATH (Linux and macOS alike)."""
    return shutil.which("tmux") is not None


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _new_session_id() -> str:
    """A fresh CC-compatible session UUID. Its first 8 hex chars become the
    breadcrumb short id (s_xxxxxxxx) and the tmux session-name suffix, so a
    command that passes this through to `claude --session-id` lands a session
    whose breadcrumb matches the tmux name by construction."""
    return str(uuid.uuid4())


def _latest_session_id() -> str:
    """The session id of the most recently modified CC transcript under
    ~/.claude/projects/ - i.e. the conversation `claude -c` would resume.
    Returns None if there are no transcripts. Lets the supervisor pin (and
    name the tmux session after) the session the user is actually continuing,
    instead of minting a fresh empty one."""
    projects = Path.home() / ".claude" / "projects"
    if not projects.exists():
        return None
    latest, latest_mtime = None, -1.0
    for jf in projects.glob("*/*.jsonl"):
        if not _UUID_RE.match(jf.stem):
            continue
        try:
            m = jf.stat().st_mtime
        except OSError:
            continue
        if m > latest_mtime:
            latest_mtime, latest = m, jf.stem
    return latest


def _resolve_session_spec(spec: str) -> str:
    """Map a launch-time --session-id spec to a concrete session id (or None).

    None/""  -> None      (do not pin; the command runs as-is, e.g. its own -c)
    "new"    -> a fresh UUID
    "latest" -> the most recent CC transcript's id (resume it), or a fresh UUID
                if none exists - this restores `claude -c` continuity while
                still yielding an id to name the tmux session after.
    <uuid>   -> that explicit id
    """
    if spec in (None, ""):
        return None
    if spec == "new":
        return _new_session_id()
    if spec == "latest":
        return _latest_session_id() or _new_session_id()
    return spec


def _sanitize_tmux_name(name: str) -> str:
    """tmux forbids '.' and ':' in session names (they are window/pane
    separators) and chokes on whitespace. Map those to '_'."""
    cleaned = "".join("_" if ch in ".: \t\n" else ch for ch in name)
    return cleaned or "session"


def _tmux_wrap(tmux_session: str, cmd: list) -> list:
    """Wrap *cmd* (an argv list) so it runs inside a named tmux session.

    tmux's [shell-command] is a SINGLE argument re-parsed by `/bin/sh -c`, so
    the command is passed as one shell-safe string. `-A` attaches to an
    existing session of that name instead of erroring, which is the right
    behaviour for a long-lived supervisor pane.
    """
    return ["tmux", "new-session", "-A", "-s", tmux_session,
            _shell_command_string(cmd)]


def _is_supervisor_process(pid: int) -> bool:
    """Is this pid still a supervisor, or something that inherited the number?

    Separate and module-level for the same reason ``_is_alive`` is: the process
    table is not a thing a test should have to own. Both are the seam where
    "what the registry says" meets "what is actually true".
    """
    try:
        args = subprocess.run(["ps", "-o", "args=", "-p", str(pid)],
                              capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "macf.supervisor" in args


def is_live_supervisor(data: dict) -> bool:
    """Does this registry entry describe a supervisor that is actually running?

    Three conditions, and each excludes a state that has been observed on a
    live host:

    * ``status == "running"`` — entries persist after the process ends, so the
      file existing proves nothing. Seven stale entries sat in one registry,
      one of them still claiming a supervisor that had exited nine days earlier.
    * the pid is alive — an entry can outlive its process by any amount.
    * the pid is still a supervisor — pids are recycled, and an entry pointing
      at whatever inherited the number is worse than no entry at all.

    Deliberately NOT ``pgrep -f 'macf.supervisor --name X'``: when tmux starts a
    server it keeps the command it was asked to run in its own argv, so that
    matches the tmux server and reports a live supervisor for as long as the
    server lives. The registry is keyed by the supervisor's own pid, which is
    what makes the process check meaningful.
    """
    if data.get("status") != "running":
        return False
    pid = data.get("supervisor_pid", 0)
    if not pid or not _is_alive(pid):
        return False
    return _is_supervisor_process(pid)


def _iter_live_supervisors():
    """Yield the registry data of every supervisor that is actually running now.

    The single registry scan that every "who is live?" question routes through,
    so ``is_live_supervisor`` — the process-liveness predicate, never the state
    file alone — is applied in exactly one place and cannot come to mean two
    different things in two callers.
    """
    if not REGISTRY_DIR.exists():
        return
    for entry in REGISTRY_DIR.glob("*.json"):
        if entry.name == "supervisor_crash.log":
            continue
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if is_live_supervisor(data):
            yield data


def _find_supervisor(target: str) -> dict | None:
    """Find a RUNNING supervisor registry entry by supervisor PID or by name.
    On multiple name matches, returns the most recently created."""
    matches = [
        data for data in _iter_live_supervisors()
        if target == str(data.get("supervisor_pid", 0)) or target == data.get("name")
    ]
    if not matches:
        return None
    return max(matches, key=lambda d: d.get("created", 0))


def find_live_supervisor_by_name(name: str, exclude_pid: int = 0) -> dict | None:
    """The live supervisor already owning this calling card, or None.

    The singleton guard's eyes (task #113 / GH#210). "Owning" is keyed on the
    supervisor *name* — the calling card — because the fork the FORK INCIDENT
    documented was three ``claude -c`` clients under one name, and two live
    supervisors sharing a name is precisely the state in which two clients write
    one task store. Distinct names are distinct services (``claude`` vs
    ``manny``) and never collide here.

    ``exclude_pid`` skips the caller's own entry so a supervisor calling this to
    check for a *pre-existing* twin never matches itself. Liveness is decided by
    ``is_live_supervisor`` (status running + pid alive + pid still a supervisor),
    never by the state file alone: the same evening produced ``running`` entries
    for dead pids and dead entries for live ones. On multiple matches returns the
    most recently created.
    """
    matches = [
        data for data in _iter_live_supervisors()
        if data.get("name") == name and data.get("supervisor_pid", 0) != exclude_pid
    ]
    if not matches:
        return None
    return max(matches, key=lambda d: d.get("created", 0))


def _find_own_supervisor() -> dict | None:
    """Find the RUNNING supervisor whose child is *this* session.

    tmux sessions are named with the CC session id as a suffix
    (see ``launch_in_terminal``), so an agent can locate its own supervisor by
    matching the current session id against each registry entry's
    ``tmux_session``. Returns the most recently created match, or None when the
    session is unsupervised / not tmux-backed.
    """
    import os
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or _latest_session_id()
    if not sid or not REGISTRY_DIR.exists():
        return None
    short = sid.split("-")[0]
    matches = []
    for entry in REGISTRY_DIR.glob("*.json"):
        if entry.name == "supervisor_crash.log":
            continue
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not _is_alive(data.get("supervisor_pid", 0)):
            continue
        ts = data.get("tmux_session") or ""
        if sid in ts or (short and short in ts):
            matches.append(data)
    if not matches:
        return None
    return max(matches, key=lambda d: d.get("created", 0))


def send_slash_to_self(command: str, target: str = "") -> int:
    """Queue a slash command (e.g. ``/compact``) into this agent's own live CC
    pane via the tmux side channel.

    The client parses slash commands only from its own TTY input, so there is
    no in-process way to invoke ``/compact``; the supported path is to type it
    into the pane. Typed mid-turn it simply queues and fires when the current
    turn yields — which is exactly the intended use (an operator, away from the
    keyboard, directing the agent to compact itself).

    *command* is given without the leading slash (``"compact"`` → ``/compact``);
    a leading slash is tolerated. *target* optionally names the supervisor
    directly (``auto-restart`` name/pid) when self-resolution is not wanted.
    Returns 0 on success; non-zero with a diagnostic on any failure, and never
    raises into the caller.
    """
    cmd = "/" + command.lstrip("/")
    if target:
        return send_keys(target, [cmd], enter=True)
    data = _find_own_supervisor()
    if not data:
        print("[inject] Could not find a running supervisor for this session. "
              "This session may be unsupervised or not tmux-backed. "
              "Pass an explicit --target <name|pid> (see `auto-restart list`).",
              file=sys.stderr)
        return 1
    return send_keys(data.get("name") or str(data.get("supervisor_pid")),
                     [cmd], enter=True)


def send_keys(target: str, keys: list, enter: bool = True) -> int:
    """Inject literal text (plus an optional Enter) into a supervised session's
    tmux pane - the side channel for driving the live CC client (e.g. a real
    `/compact`, which the client parses only from its own TTY input).

    *target* is a supervisor name or PID. The text is sent with `-l` (literal,
    no key-name interpretation) and the Enter is a separate key press, so text
    that happens to contain 'Enter' or 'C-c' is not reinterpreted.
    """
    if not _tmux_available():
        print("[auto-restart] tmux not found; send-keys requires a tmux-backed session.",
              file=sys.stderr)
        return 1
    data = _find_supervisor(target)
    if not data:
        print(f"[auto-restart] No running supervised process matching '{target}'.",
              file=sys.stderr)
        return 1
    tmux_session = data.get("tmux_session")
    if not tmux_session:
        print(f"[auto-restart] '{data.get('name')}' was launched without a tmux session; "
              f"send-keys is unavailable.\n"
              f"  Relaunch (with tmux on PATH) to enable the input side channel.",
              file=sys.stderr)
        return 1
    text = " ".join(keys)
    # `-t <session>` targets that session's active pane. `--` guards text that
    # starts with '-'. CC's stdin reader receives the bytes as if typed.
    rc = subprocess.run(
        ["tmux", "send-keys", "-t", tmux_session, "-l", "--", text]
    ).returncode
    if rc == 0 and enter:
        rc = subprocess.run(["tmux", "send-keys", "-t", tmux_session, "Enter"]).returncode
    if rc == 0:
        suffix = " + Enter" if enter else ""
        print(f"[auto-restart] Sent to tmux session '{tmux_session}': {text!r}{suffix}")
    else:
        print(f"[auto-restart] tmux send-keys failed (rc={rc}). "
              f"Is the session alive?  tmux ls", file=sys.stderr)
    return rc


def launch_in_terminal(cmd_args: list, name: str = "",
                       restart_delay: int = 5,
                       terminal: str = "auto",
                       use_tmux: bool = True,
                       session_spec: str = None,
                       post_start_keys: str = None,
                       post_start_delay: int = 18,
                       force: bool = False) -> int:
    """Launch a supervised process in a new terminal window.

    Args:
        cmd_args: Command and arguments to supervise
        name: Optional display name (defaults to command basename)
        restart_delay: Seconds between restarts
        terminal: Terminal app to use: "auto", "terminal", "iterm2",
            "gnome-terminal", "ptyxis", "kgx", "tilix", "lxterminal", "foot",
            "xterm", "konsole", "x-terminal-emulator"
        use_tmux: If True (default) and tmux is on PATH, run the supervisor
            inside a named tmux session ("<name>_<short-session-id>") so the
            live child can be driven via `auto-restart send-keys`. Degrades
            gracefully (direct launch, no send-keys) when tmux is absent.
        session_spec: Session id to pin: None (default - do not pin; the
            command resumes on its own, e.g. its own `-c`), "latest" (the most
            recent CC transcript id), "new" (a fresh session), or an explicit
            UUID. When set it is exported as MACF_SESSION_ID for the command to
            forward via `claude --session-id`. CAVEAT: CC refuses `--session-id`
            for a session that is currently LIVE ("already in use"), so do not
            pin the conversation you are still in - use None (the command's own
            `-c`) for that case.

    Returns:
        Supervisor PID
    """
    if not cmd_args:
        print("Error: no command specified", file=sys.stderr)
        return 1

    if not name:
        name = os.path.basename(cmd_args[0])

    # Singleton pre-flight, early copy (task #113 / GH#210). run_loop holds the
    # authoritative guard — it is the confluence a systemd-launched supervisor
    # also passes through — but refusing HERE too, before a terminal window is
    # ever opened, spares the interactive user an orphaned terminal that would
    # only flash the same refusal and vanish. Same predicate, friendlier moment.
    if not force:
        existing = find_live_supervisor_by_name(name)
        if existing:
            _refuse_duplicate(name, existing, where="launch_in_terminal")
            return 1

    # Optionally pin a session id. When set, the supervised command (e.g. a
    # wrapper around `claude`) forwards it via `claude --session-id
    # "$MACF_SESSION_ID"`, so the CC breadcrumb (s_<first8>) matches the tmux
    # session name below. "latest" resumes the user's current conversation.
    session_id = _resolve_session_spec(session_spec)
    short_id = session_id[:8] if session_id else None

    # Optionally back the session with a named tmux session so the live child
    # is reachable by `auto-restart send-keys`. The id suffix is added only
    # when an id is pinned; otherwise the bare name is used.
    tmuxify = use_tmux and _tmux_available()
    if tmuxify:
        tmux_session = _sanitize_tmux_name(f"{name}_{short_id}" if short_id else name)
    else:
        tmux_session = None
    if use_tmux and not tmuxify:
        print("[auto-restart] tmux not found - launching without the send-keys "
              "side channel (install tmux to enable it).", file=sys.stderr)

    # Build the supervisor command that runs in the new terminal. --session-id
    # and --tmux-session are recorded by the supervisor in its registry entry.
    supervisor_cmd = [
        sys.executable, "-m", "macf.supervisor",
        "_run_loop",
        "--name", name,
        "--delay", str(restart_delay),
    ]
    if session_id:
        supervisor_cmd += ["--session-id", session_id]
    if tmux_session:
        supervisor_cmd += ["--tmux-session", tmux_session]
    if post_start_keys:
        supervisor_cmd += ["--post-start-keys", post_start_keys,
                           "--post-start-delay", str(post_start_delay)]
    # Propagate the override: without it the terminal-hosted supervisor would
    # re-run the pre-flight and refuse, so a --force that stopped at this layer
    # would be silently ineffective.
    if force:
        supervisor_cmd += ["--force"]
    supervisor_cmd += ["--"] + cmd_args

    # When tmux-backed, the terminal hosts `tmux new-session` which runs the
    # supervisor in its pane (-A: attach if a session of that name already
    # exists). tmux's [shell-command] is a single shell-reparsed argument, so
    # pass the supervisor command as one shell-safe string.
    if tmux_session:
        launch_cmd = _tmux_wrap(tmux_session, supervisor_cmd)
    else:
        launch_cmd = supervisor_cmd

    # macOS terminals run their command argument through a shell, so build a
    # shell-safe string and then escape it for the AppleScript literal.
    escaped_cmd = _applescript_quote(_shell_command_string(launch_cmd))

    system = platform.system()
    if system == "Darwin":
        # Resolve terminal choice
        if terminal == "auto":
            # Prefer iTerm2 if running, else Terminal.app
            try:
                result = subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "iTerm2"'],
                    capture_output=True, text=True, timeout=3
                )
                terminal = "iterm2" if "true" in result.stdout.lower() else "terminal"
            except (OSError, subprocess.SubprocessError) as e:
                print(f"⚠️ MACF: terminal detection failed: {e}", file=sys.stderr)
                terminal = "terminal"

        if terminal == "iterm2":
            osascript = f'''
                tell application "iTerm2"
                    activate
                    create window with default profile command "{escaped_cmd}"
                end tell
            '''
        else:
            osascript = f'''
                tell application "Terminal"
                    activate
                    do script "{escaped_cmd}"
                end tell
            '''

        subprocess.Popen(["osascript", "-e", osascript])
        time.sleep(1.5)

    elif system == "Linux":
        # Linux: find the first available terminal emulator and launch the
        # supervisor in it, passing the command as separate argv tokens (see
        # _terminal_argv) so argv-respecting terminals do not mis-exec the
        # whole command line as a single filename.
        candidates = [terminal] if terminal not in ("auto", "") else _LINUX_TERMINALS
        for term in candidates:
            if subprocess.run(["which", term], capture_output=True).returncode == 0:
                subprocess.Popen(_terminal_argv(term, launch_cmd))
                time.sleep(1.5)
                break
        else:
            print("No terminal emulator found. Run directly:", file=sys.stderr)
            print(f"  {_shell_command_string(launch_cmd)}", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1

    # Find the newly created registry entry
    if REGISTRY_DIR.exists():
        entries = sorted(REGISTRY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if entries:
            data = json.loads(entries[0].read_text())
            pid = data.get("supervisor_pid", "?")
            print(f"[auto-restart] Launched '{name}' in new terminal (supervisor PID: {pid})")
            print(f"[auto-restart] Command: {' '.join(cmd_args)}")
            if session_id:
                print(f"[auto-restart] Session id: {session_id} (breadcrumb s_{short_id})")
            if tmux_session:
                print(f"[auto-restart] tmux session: {tmux_session}")
                print(f"[auto-restart] Send input: macf_tools auto-restart send-keys {name} -- <text>")
            print(f"[auto-restart] Manage: macf_tools auto-restart list")
            return pid

    print(f"[auto-restart] Launched '{name}' in new terminal")
    return 0


# Shell exit codes that mean the command was never launched. POSIX shells use
# 127 for "not found" and 126 for "found but not executable". Neither describes
# a process that ran and failed, so neither is a reason to try again.
_NEVER_LAUNCHED_EXITS = (126, 127)

# A child that exits this fast did not do any work. Pairing the exit code with
# the lifetime matters: a long-running child is entitled to exit 127 as its own
# considered result, and killing supervision for that would be wrong.
_NEVER_LAUNCHED_WINDOW_SECONDS = 3


def _unlaunchable_reason(cmd_args: list) -> "str | None":
    """Why this command can never run, or None if it might.

    Only a path is checked, and only when it is one: a bare word may be an
    alias or a shell function, and the child is deliberately run through an
    interactive shell so that those resolve. Refusing them here would break the
    very indirection that invocation exists to support. An absolute or relative
    PATH-bearing target, by contrast, is a claim about the filesystem that can
    be checked cheaply and answered definitively.
    """
    if not cmd_args:
        return "no command was given"
    target = cmd_args[0]
    if os.sep not in target:
        return None
    if not os.path.exists(target):
        return f"{target} does not exist"
    if not os.access(target, os.X_OK):
        return f"{target} exists but is not executable"
    return None


def _send_post_start_keys(tmux_session: str, keys: str, delay: int) -> None:
    """Send `keys` to the child's tmux pane `delay` seconds after it spawns.

    Runs on a daemon thread: the wait must not delay supervision, and a failure
    here must never take down the supervisor — the child is fine either way.
    """
    time.sleep(max(0, delay))
    try:
        subprocess.run(["tmux", "send-keys", "-t", tmux_session, keys],
                       capture_output=True, timeout=10)
        print(f"[auto-restart] Sent post-start keys to '{tmux_session}': {keys!r}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[auto-restart] post-start keys failed (non-fatal): {e}", file=sys.stderr)


def _refuse_duplicate(name: str, existing: dict, *, where: str) -> None:
    """Print the singleton refusal and fire the Telegram notice.

    Shared by both guard sites so the refusal — which names the live instance
    and the sanctioned rejoin path — reads identically whether it fires early in
    ``launch_in_terminal`` or authoritatively in ``run_loop``.
    """
    other_pid = existing.get("supervisor_pid")
    other_restarts = existing.get("restart_count", 0)
    other_session = existing.get("tmux_session") or "n/a"
    print(f"\n[auto-restart] REFUSING TO START: a live supervisor for "
          f"'{name}' already exists (pid {other_pid}, {other_restarts} restart(s), "
          f"tmux session {other_session}).", file=sys.stderr)
    print("[auto-restart] Starting another would MINT A FORK — two clients "
          "writing one calling card, the failure GH#210 exists to prevent.",
          file=sys.stderr)
    print(f"[auto-restart] To restart that instance IN PLACE (rejoin, not fork):"
          f"\n                 macf_tools auto-restart restart {other_pid}",
          file=sys.stderr)
    print("[auto-restart] To run a genuinely separate service, give it a distinct "
          "--name. To override this guard deliberately, pass --force.",
          file=sys.stderr)
    _notify_telegram(
        f"Name: {name}\nLive instance: pid {other_pid}\n"
        f"Rejoin: auto-restart restart {other_pid}",
        prefix="\U0001f6d1 Supervisor Refused (would fork)")


def run_loop(cmd_args: list, name: str = "", restart_delay: int = 5,
             tmux_session: str = None, session_id: str = None,
             post_start_keys: str = None, post_start_delay: int = 18,
             force: bool = False):
    """Run the supervisor loop (called inside the new terminal).

    This is the actual supervisor process — manages the child.

    tmux_session / session_id are recorded in the registry (for `send-keys`
    resolution and breadcrumb correlation). When session_id is set it is also
    exported as MACF_SESSION_ID so the supervised command can forward it (e.g.
    `claude --session-id "$MACF_SESSION_ID"`).

    post_start_keys / post_start_delay drive the post-spawn keystroke hook,
    which fires after *every* spawn — initial and each restart — so a relaunch
    that re-presents the workspace-trust dialog does not strand an unattended
    agent at a prompt. Requires a tmux-backed session.
    """
    pid = os.getpid()
    created = time.time()

    # Refuse to supervise a command that cannot ever run. Restarting is a
    # response to a process that FAILED; a command that does not exist has not
    # failed, it was never launchable, and no number of retries changes that.
    #
    # Measured before this existed: with the child binary removed, the loop
    # reached three restarts in eight seconds, kept its registry entry marked
    # "running", and surfaced nothing — the shell's "command not found" went to
    # a pane that had already gone. An agent's harness silently spinning is
    # indistinguishable, from every status surface, from one that is simply up.
    problem = _unlaunchable_reason(cmd_args)
    if problem:
        print(f"[auto-restart] REFUSING TO START: {problem}", file=sys.stderr)
        print("[auto-restart] This is not a transient failure and restarting "
              "cannot fix it, so no supervisor is registered.", file=sys.stderr)
        _notify_telegram(f"Name: {name}\n{problem}",
                         prefix="\U0001f6d1 Supervisor Refused")
        return 1

    # Singleton pre-flight (task #113 / GH#210). Refuse to become a SECOND live
    # supervisor for a calling card that already has one. This guard lives HERE,
    # in run_loop, because run_loop is the confluence every supervisor birth
    # passes through — `launch_in_terminal`, a systemd unit invoking this module
    # directly, a manual launch. A guard placed only at `launch_in_terminal`
    # would leave the systemd door open, and the fork the FORK INCIDENT
    # documented (three `claude -c` clients under one name) mints through
    # whichever door is unguarded. Checked by process liveness, never by state
    # file: this same evening produced 'running' entries for dead pids and dead
    # entries for live ones. --force is the deliberate override for a human who
    # genuinely wants a second instance.
    if not force:
        existing = find_live_supervisor_by_name(name, exclude_pid=pid)
        if existing:
            _refuse_duplicate(name, existing, where="run_loop")
            return 1

    # Export the pinned session id so the child (run via $SHELL -ic, which
    # inherits this environment) can pass it to `claude --session-id`.
    if session_id:
        os.environ["MACF_SESSION_ID"] = session_id

    _write_registry(pid, {
        "supervisor_pid": pid,
        "name": name,
        "command": cmd_args,
        "created": created,
        "created_iso": datetime.fromtimestamp(created).isoformat(),
        "restart_count": 0,
        "status": "running",
        "last_restart": None,
        "child_pid": None,
        "tmux_session": tmux_session,
        "session_id": session_id,
    })

    child = None
    restart_count = 0
    stop_requested = False  # Flag for Ctrl-C during countdown
    # Mutable so the `finally` block can set it without a nonlocal dance.
    _exit_status = [0]

    def handle_restart(signum, frame):
        nonlocal child
        if child and child.poll() is None:
            _notify_telegram(
                f"Process: {name}\nRestart #{restart_count + 1}",
                prefix="\U0001f504 \u03bcC Triggered"
            )
            child.send_signal(signal.SIGINT)

    def handle_disable(signum, frame):
        _update_registry(pid, status="disabled")
        nonlocal child
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT)

    def handle_sigint_countdown(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGUSR1, handle_restart)
    signal.signal(signal.SIGUSR2, handle_disable)

    print(f"[auto-restart] Supervisor PID: {pid}")
    print(f"[auto-restart] Name: {name}")
    print(f"[auto-restart] Command: {' '.join(cmd_args)}")
    print(f"[auto-restart] Restart delay: {restart_delay}s")
    print(f"[auto-restart] Remote restart: macf_tools auto-restart restart {pid}")
    print(f"[auto-restart] Disable: macf_tools auto-restart disable {pid}")
    print()

    _notify_telegram(
        f"Name: {name}\nCommand: {' '.join(cmd_args)}\nPID: {pid}",
        prefix="\U0001f680 Supervisor Started"
    )

    try:
        while True:
            reg = _read_registry(pid)
            if reg.get("status") == "disabled":
                print("[auto-restart] Disabled. Exiting.")
                break

            # Use shell=True to resolve aliases (e.g., claude_autoupdating)
            # Interactive shell (-i) needed to source alias definitions from rc files
            cmd_string = " ".join(cmd_args)
            user_shell = os.environ.get("SHELL", "")
            if not user_shell:
                # Cross-platform default: zsh on macOS, bash on Linux
                user_shell = "/bin/zsh" if platform.system() == "Darwin" else "/bin/bash"
            # start_new_session=True puts each child in its own session/process
            # group via setsid(2). Without this, lxterminal (and similar PTY-based
            # terminals) leak partially-torn-down file descriptors into the
            # supervisor's environment after the first child exits — subsequent
            # respawns then fail with "initialize_job_control: no job control in
            # background: Bad file descriptor" and the supervisor enters an
            # infinite crash loop. Closes GH issue #27.
            child = subprocess.Popen(
                [user_shell, "-ic", cmd_string],
                start_new_session=True,
            )
            _update_registry(pid, child_pid=child.pid, status="running")

            # Post-start keys: some deployments re-present the workspace-trust
            # dialog on every relaunch, which parks the child at an interactive
            # prompt. Attended, that's a keystroke; unattended, it's an
            # indefinite hang the supervisor reads as "healthy" (#164). Fire in
            # a background thread so the delay never blocks supervision, and
            # only for tmux-backed sessions (there is no pane to type into
            # otherwise). Harmless when no prompt is showing.
            if post_start_keys and tmux_session:
                threading.Thread(
                    target=_send_post_start_keys,
                    args=(tmux_session, post_start_keys, post_start_delay),
                    daemon=True,
                ).start()

            spawned_at = time.time()
            exit_code = child.wait()
            lifetime = time.time() - spawned_at
            child = None
            restart_count += 1

            _update_registry(pid,
                             restart_count=restart_count,
                             last_restart=time.time(),
                             child_pid=None,
                             last_exit_code=exit_code)

            # Check if disabled during child run
            reg = _read_registry(pid)
            if reg.get("status") == "disabled":
                print(f"[auto-restart] Disabled. Not restarting.")
                break

            # The pre-flight check cannot see through an alias, a shell
            # function or a PATH lookup, so the same "never launched" case can
            # still arrive here — as a shell exit code instead of a missing
            # file. Stop, rather than spin: the shell has already decided this
            # command does not resolve, and it will decide the same thing every
            # five seconds forever.
            if exit_code in _NEVER_LAUNCHED_EXITS and lifetime < _NEVER_LAUNCHED_WINDOW_SECONDS:
                reason = ("not found" if exit_code == 127 else "not executable")
                print(f"\n[auto-restart] FATAL: the shell reports the command is "
                      f"{reason} (exit {exit_code}, after {lifetime:.1f}s).",
                      file=sys.stderr)
                print("[auto-restart] Not restarting — retrying cannot resolve a "
                      "command that does not resolve.", file=sys.stderr)
                _update_registry(pid, status="failed", last_exit_code=exit_code,
                                 failure_reason=f"command {reason}")
                _notify_telegram(
                    f"Process: {name}\nCommand {reason} (exit {exit_code})\n"
                    f"Supervision stopped after {restart_count} attempt(s).",
                    prefix="\U0001f6d1 Supervisor Failed")
                break

            # Install countdown SIGINT handler (interactive shell corrupts default handler)
            stop_requested = False
            signal.signal(signal.SIGINT, handle_sigint_countdown)

            print(f"\n[auto-restart] Exited (code {exit_code}). Restart #{restart_count}.")
            print(f"[auto-restart] Ctrl-C during countdown to stop (will NOT restart).\n")
            _notify_telegram(
                f"Process: {name}\nExit code: {exit_code}\nRestart #{restart_count}",
                prefix="\U0001f504 Auto-Restart"
            )

            # Countdown with visual trail (polling flag instead of catching KeyboardInterrupt)
            for remaining in range(restart_delay, 0, -1):
                if stop_requested:
                    break
                print(f"[auto-restart] Restarting in {remaining}s...", flush=True)
                # Poll in short intervals so flag is checked promptly
                for _ in range(10):
                    if stop_requested:
                        break
                    time.sleep(0.1)

            if stop_requested:
                print(f"\n[auto-restart] Ctrl-C caught. Stopping auto-restart.")
                _notify_telegram(
                    f"Process: {name}\nStopped by Ctrl-C during countdown",
                    prefix="\U0001f6d1 Supervisor Stopped"
                )
                break

    except KeyboardInterrupt:
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait()
    finally:
        # "stopped" means someone asked it to stop. "failed" means it gave up.
        # Overwriting the second with the first erases the only signal that
        # distinguishes a clean shutdown from a supervisor that could not run
        # what it was given — and that distinction is the entire point of
        # recording a failure.
        final_status = "stopped"
        if _read_registry(pid).get("status") == "failed":
            final_status = "failed"
        _update_registry(pid, status=final_status,
                         stopped=time.time(),
                         total_restarts=restart_count)
        # Carried out of `finally` so the caller — and therefore the service
        # manager — sees a failure as a failure. A supervisor that gave up and
        # exited 0 leaves the unit reporting active with nothing supervised.
        _exit_status[0] = 1 if final_status == "failed" else 0
        _notify_telegram(
            f"Process: {name}\nRestarts: {restart_count}\nUptime: {_format_duration(time.time() - created)}",
            prefix="\U0001f6d1 Supervisor Stopped"
        )
    return _exit_status[0]


def list_processes(show_all: bool = False):
    """List managed processes with stats.

    Default: show only running processes.
    --all: show all including stopped/dead (history).
    Auto-cleans stale entries that are not running.
    """
    if not REGISTRY_DIR.exists():
        print("No managed processes.")
        return

    entries = sorted(REGISTRY_DIR.glob("*.json"))
    if not entries:
        print("No managed processes.")
        return

    # Categorize entries. "Active" means an entry that is genuinely a live
    # supervisor — status running AND pid alive AND the pid still a supervisor
    # (is_live_supervisor), not merely an alive pid. The weaker os.kill check
    # marked a recycled pid — now running something unrelated — as a live
    # supervisor, so a dead supervisor's number could show as "running" once the
    # OS handed it out again (task #113 / GH#210 registry hygiene). _alive is
    # still recorded for the status-line normalization below.
    active = []
    stale = []
    for entry in entries:
        if entry.name == "supervisor_crash.log":
            continue
        data = json.loads(entry.read_text())
        pid = data.get("supervisor_pid", 0)
        data["_alive"] = _is_alive(pid)
        data["_path"] = entry
        if is_live_supervisor(data):
            active.append(data)
        else:
            stale.append(data)

    # Auto-clean stale entries (unless --all requested)
    if not show_all:
        for data in stale:
            data["_path"].unlink(missing_ok=True)
        if not active:
            cleaned = len(stale)
            msg = f"No running processes."
            if cleaned:
                msg += f" (cleaned {cleaned} stale entries)"
            print(msg)
            return
        display = active
    else:
        display = active + stale

    # Header
    print(f"{'PID':>8}  {'NAME':<20}  {'STATUS':<10}  {'RESTARTS':>8}  {'UPTIME':>8}  {'COMMAND'}")
    print("-" * 90)

    for data in display:
        pid = data.get("supervisor_pid", 0)
        name = data.get("name", "?")
        status = data.get("status", "?")
        alive = data.get("_alive", False)
        restarts = data.get("restart_count", 0)
        created = data.get("created", 0)
        cmd = " ".join(data.get("command", []))

        # Normalize: dead and stopped both mean "not running"
        if not alive and status in ("running", "dead"):
            status = "stopped"

        uptime = _format_duration(time.time() - created) if created else "?"

        # Color status
        if status == "running" and alive:
            status_display = f"\033[32m{status}\033[0m"
        elif status == "disabled":
            status_display = f"\033[33m{status}\033[0m"
        elif status == "killed":
            status_display = f"\033[31m{status}\033[0m"
        else:
            status_display = f"\033[2m{status}\033[0m"  # dim for stopped

        print(f"{pid:>8}  {name:<20}  {status_display:<21}  {restarts:>8}  {uptime:>8}  {cmd[:40]}")


def restart(pid: int):
    """Send restart signal to a supervised process."""
    if not _is_alive(pid):
        print(f"[auto-restart] Process {pid} is not running")
        return
    os.kill(pid, signal.SIGUSR1)
    print(f"[auto-restart] Restart signal sent to {pid}")


def disable(pid: int):
    """Disable auto-restart for a supervised process."""
    if not _is_alive(pid):
        print(f"[auto-restart] Process {pid} is not running")
        _update_registry(pid, status="disabled")
        return
    os.kill(pid, signal.SIGUSR2)
    print(f"[auto-restart] Disable signal sent to {pid}")


def kill_process(pid: int):
    """Nuclear option: kill supervisor and child processes."""
    data = _read_registry(pid)
    if not data:
        print(f"[auto-restart] No registry entry for PID {pid}")
        return

    child_pid = data.get("child_pid")
    killed = []

    # Kill child first
    if child_pid and _is_alive(child_pid):
        os.kill(child_pid, signal.SIGKILL)
        killed.append(f"child {child_pid}")

    # Kill supervisor
    if _is_alive(pid):
        os.kill(pid, signal.SIGKILL)
        killed.append(f"supervisor {pid}")

    # Clean up registry
    _update_registry(pid, status="killed")

    if killed:
        print(f"[auto-restart] Killed: {', '.join(killed)}")
        _notify_telegram(
            f"Process: {data.get('name', '?')}\nKilled: {', '.join(killed)}",
            prefix="\U0001f480 Process Killed"
        )
    else:
        print(f"[auto-restart] Process {pid} already dead")


def status(pid: int):
    """Show detailed status for a supervised process."""
    data = _read_registry(pid)
    if not data:
        print(f"[auto-restart] No registry entry for PID {pid}")
        return

    alive = _is_alive(pid)
    print(f"Supervisor PID:  {pid} ({'alive' if alive else 'dead'})")
    print(f"Name:            {data.get('name', '?')}")
    print(f"Command:         {' '.join(data.get('command', []))}")
    print(f"Status:          {data.get('status', '?')}")
    print(f"Child PID:       {data.get('child_pid', 'none')}")
    print(f"tmux session:    {data.get('tmux_session') or 'none (send-keys unavailable)'}")
    print(f"Session id:      {data.get('session_id') or 'N/A'}")
    print(f"Created:         {data.get('created_iso', '?')}")
    print(f"Restarts:        {data.get('restart_count', 0)}")
    print(f"Last exit code:  {data.get('last_exit_code', 'N/A')}")
    created = data.get("created", 0)
    if created:
        print(f"Uptime:          {_format_duration(time.time() - created)}")


# Entry point for running inside new terminal
if __name__ == "__main__":
    import argparse
    import traceback

    LOG_FILE = REGISTRY_DIR / "supervisor_crash.log"

    try:
        # Split argv on -- : supervisor args before, command after
        argv = sys.argv[1:]
        if "--" in argv:
            split_idx = argv.index("--")
            supervisor_argv = argv[:split_idx]
            cmd = argv[split_idx + 1:]
        else:
            supervisor_argv = argv
            cmd = []

        parser = argparse.ArgumentParser(description="Auto-restart supervisor")
        parser.add_argument("action", choices=["_run_loop"])
        parser.add_argument("--name", default="")
        parser.add_argument("--delay", type=int, default=2)
        parser.add_argument("--tmux-session", default=None)
        parser.add_argument("--session-id", default=None)
        parser.add_argument("--post-start-keys", default=None)
        parser.add_argument("--post-start-delay", type=int, default=18)
        parser.add_argument("--force", action="store_true",
                            help="override the singleton pre-flight and start even if "
                                 "a live supervisor already owns this name (GH#210)")

        args = parser.parse_args(supervisor_argv)

        if args.action == "_run_loop":
            # Propagate the return code. A supervisor that refuses to start and
            # then exits 0 tells the service manager it succeeded, which is the
            # same silent-success failure the refusal exists to end: systemd
            # would mark the unit active with nothing supervising anything.
            sys.exit(run_loop(cmd, name=args.name, restart_delay=args.delay,
                              tmux_session=args.tmux_session, session_id=args.session_id,
                              post_start_keys=args.post_start_keys,
                              post_start_delay=args.post_start_delay,
                              force=args.force) or 0)

    except Exception as e:
        # Top-level supervisor crash handler — bare Exception is intentional:
        # this is the last line of defense before the lxterminal window closes.
        # Specific exception types would let unexpected escapes vanish silently.
        error_msg = traceback.format_exc()
        print(f"\n[auto-restart] CRASH ({type(e).__name__}: {e}):\n{error_msg}", file=sys.stderr)
        # Log to file (persists after window closes)
        _ensure_registry_dir()
        with open(LOG_FILE, "a") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(f"argv: {sys.argv}\n")
            f.write(error_msg)
        print(f"[auto-restart] Crash log: {LOG_FILE}")
        print("[auto-restart] Press Enter to close...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
