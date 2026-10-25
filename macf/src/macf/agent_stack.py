"""``macf_tools agent init``: the agent's whole persistent-layer stack, step by step.

``agent init`` used to write only the PA preamble. An agent reached a working primal daemon
only through a series of further commands, each of which had to be known. This module runs
them, in an order where each step finds what it needs already in place, and reports each one:
done, already done, skipped (and why), or refused (and why). Every step is idempotent, so a
second run reports everything as already done.

The steps, each skippable by its flag:

1. ``preamble`` - the PA preamble in CLAUDE.md (the existing behavior);
2. ``task-store`` - the home task store (``task store-init``) when absent;
3. ``declaration`` - a default primal daemon declaration where none exists. An existing one is
   never overwritten; what it lacks compared with the default is reported instead;
4. ``harness`` - the session's child script and settings (``harness install``), with the
   channels the declaration allows, the MacEff channel included;
5. ``channel`` - the MacEff channel plugin from the marketplace packaged with macf;
6. ``permissions`` - the mode-safety permission entries;
7. ``daemon`` - the daemon under the platform's service manager (``pd install``).

``pd install`` comes last although it is the heart of the stack: the daemon starts the session
unit as soon as it starts, and that session needs the child script, the channel plugin and its
permissions already in place.
"""
import argparse
import contextlib
import io
import json
import os
import pwd
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

DONE = "done"
ALREADY = "already done"
DRIFT = "found, with drift"
SKIPPED = "skipped"
REFUSED = "refused"
PLANNED = "planned"
#: Under --plan: what a step found it would do, having checked and changed nothing.
WOULD = "would do"

#: (step, what it does, the flag that skips it)
STEPS: List[Tuple[str, str, str]] = [
    ("preamble", "write the PA preamble into CLAUDE.md", "no_preamble"),
    ("task-store", "provision the home task store (task store-init) if absent", "no_task_store"),
    ("declaration", ("write a default primal daemon declaration (session, monitor, search) if none "
                     "exists; report what an existing one lacks"), "no_declaration"),
    ("harness", "install the session's child script with the declared channels (harness install)",
     "no_harness"),
    ("channel", "add the packaged maceff marketplace and install maceff-channel@maceff", "no_channel"),
    ("permissions", "add the mode-safety permission entries to the project's settings.local.json",
     "no_permissions"),
    ("daemon", "put the primal daemon under the service manager (pd install)", "no_daemon"),
]

#: The steps ``--update`` runs: the declaration only to report its drift, the channel and the
#: daemon to bring them current. The rest belong to a first init.
UPDATE_STEPS = ("declaration", "channel", "daemon")
#: Said for each other step under ``--update``.
NOT_UPDATED = "--update brings only the channel and the daemon current, and reports the declaration"
#: The fix a stale daemon is pointed at.
UPDATE_FIX = "macf_tools agent init --update"

#: Said where the container's provisioning, not agent init, owns a step.
CONTAINER_OWNS = "in a container, the container's start step installs this"

CLAUDE_TIMEOUT_S = 120


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The stack's flags on the ``agent init`` parser."""
    parser.add_argument("--plan", action="store_true",
                        help="print the steps agent init would take, and change nothing")
    for step, what, flag in STEPS:
        parser.add_argument(f"--{flag.replace('_', '-')}", dest=flag, action="store_true",
                            help=f"skip the {step} step ({what})")
    parser.add_argument("--project-dir", default=None, metavar="DIR",
                        help="where the session starts and its permissions live (default: the "
                             "harness's recorded choice, else MACEFF_PROJECT_DIR, else the agent home)")
    parser.add_argument("--telegram", action=argparse.BooleanOptionalAction, default=None,
                        help="declare the Telegram channel (default: when this login already uses it)")
    parser.add_argument("--update", action="store_true",
                        help="bring the persistent-layer stack current and nothing else: reinstall the "
                             "daemon's unit as rendered now, restart the daemon onto this macf (its units, "
                             "the session among them, carry across), and refresh the MacEff channel plugin; "
                             "never rewrites a declaration or restarts the session")
    parser.add_argument("--repoint", action="store_true",
                        help="with --update: let the daemon's unit move to the interpreter running this "
                             "command when the installed unit names another (a daemon pinned to its own "
                             "venv or checkout is otherwise left on it, and the step refuses)")


@dataclass
class Result:
    step: str
    status: str
    detail: str = ""


@dataclass
class Context:
    """What every step reads, resolved once."""

    home: Path
    login_home: Path
    in_container: bool
    args: argparse.Namespace
    card: Optional[str] = None
    card_error: str = ""
    #: Set when the declaration was staged for a cutover rather than installed.
    staged: Optional[Path] = None
    #: The declaration the harness and daemon steps act on (default or existing).
    declaration: Optional[Dict] = None
    #: --plan: every step checks what it finds and reports what it would do, changing nothing.
    dry_run: bool = False
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_card(ctx: Context) -> Optional[str]:
    """The agent's calling card from its own home, or None with the reason kept."""
    from macf.pd.names import IdentityError, agent_card
    try:
        ctx.card = agent_card(ctx.home)
        ctx.card_error = ""
    except IdentityError as e:
        ctx.card, ctx.card_error = None, str(e)
    return ctx.card


def _harness_settings(ctx: Context) -> Dict:
    from macf.pd.names import pd_id
    if not ctx.card:
        return {}
    try:
        data = json.loads((ctx.home / ".maceff" / f"harness_{pd_id(ctx.card)}.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def project_dir(ctx: Context) -> Path:
    chosen = (getattr(ctx.args, "project_dir", None) or _harness_settings(ctx).get("project_dir")
              or os.environ.get("MACEFF_PROJECT_DIR"))
    return Path(chosen).expanduser() if chosen else ctx.home


def unit_python() -> Path:
    """The interpreter the units run: the unversioned python3 beside this one where it exists,
    as the harness renders it, so an interpreter upgrade doesn't strand the declaration."""
    python = Path(sys.executable)
    unversioned = python.parent / "python3"
    return unversioned if unversioned.exists() else python


def session_runtime_dir(platform: Optional[str] = None, environ=None) -> Optional[str]:
    """The ``XDG_RUNTIME_DIR`` the default session unit declares: on Linux the caller's own,
    the value ``harness cutover`` checks the staged declaration against (it reads the same
    environment variable); on macOS none, since macOS sets none and the unit and its clients
    then agree on the per-user fallback under /tmp."""
    if not (platform or sys.platform).startswith("linux"):
        return None
    return (os.environ if environ is None else environ).get("XDG_RUNTIME_DIR") or None


def default_declaration(ctx: Context) -> Dict:
    from macf.pd import default_declaration as dd
    python = unit_python()
    claude = shutil.which("claude")
    recorded = list(_harness_settings(ctx).get("channels") or [])
    telegram_flag = getattr(ctx.args, "telegram", None)
    if telegram_flag is False:
        telegram = None
    else:
        telegram = dd.detect_telegram(ctx.login_home, recorded)
        if telegram is None and telegram_flag:
            telegram = dd.TELEGRAM
    return dd.build(
        ctx.card, agent_home=ctx.home, login_home=ctx.login_home,
        account=pwd.getpwuid(os.getuid()).pw_name, python=python,
        project_dir=project_dir(ctx),
        path_dirs=[str(python.parent), str(ctx.login_home / ".local" / "bin"),
                   str(Path(claude).parent) if claude else "", "/usr/local/bin", "/usr/bin", "/bin"],
        mail=dd.mail_configured(ctx.home), telegram=telegram, runtime_dir=session_runtime_dir())


def _validate(declaration: Dict) -> Optional[str]:
    """Why the daemon would refuse *declaration*, or None: the daemon's own model."""
    from pydantic import ValidationError

    from macf.pd.interface import Declaration
    try:
        Declaration.model_validate(declaration)
    except ValidationError as e:
        return str(e)
    return None


def _systemd_harness_live(ctx: Context) -> Optional[str]:
    """The legacy harness's systemd user unit, when it is active."""
    from macf.pd.names import pd_id
    unit = f"cc-harness-{pd_id(ctx.card)}.service"
    if not (ctx.login_home / ".config" / "systemd" / "user" / unit).exists():
        return None
    if shutil.which("systemctl") is None:
        return f"{unit} is installed, and without systemctl it can't be told whether it runs"
    try:
        out = subprocess.run(["systemctl", "--user", "is-active", unit],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return f"{unit} is installed and its state can't be read: {e}"
    state = out.stdout.strip()
    return f"{unit} is {state}" if state in ("active", "activating", "reloading") else None


def _launchd_harness_live(ctx: Context, platform: Optional[str] = None) -> Optional[str]:
    """macOS: a harness LaunchAgent for this card that launchd runs, the launchd counterpart
    of the systemd unit. Matched by its plist's name, which names the harness and the card's
    id; one launchd can't be asked about counts as live, since the cost of a wrong "no" is a
    second session."""
    if (platform or sys.platform) != "darwin":
        return None
    from macf.pd.names import pd_id
    agents = ctx.login_home / "Library" / "LaunchAgents"
    try:
        plists = sorted(p for p in agents.glob("*.plist")
                        if "harness" in p.name and pd_id(ctx.card) in p.name)
    except OSError as e:
        # A wrong "no" starts a second session on one conversation, so an unreadable
        # directory counts as a running session, as an unanswered launchctl does.
        return f"{agents} can't be read ({e}), so a harness LaunchAgent can't be ruled out"
    for plist in plists:
        label = plist.name[:-len(".plist")]
        if shutil.which("launchctl") is None:
            return f"the harness LaunchAgent {label} is installed, and without launchctl it can't be told whether it runs"
        from macf.platform import launchd
        try:
            out = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                                 capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            return f"the harness LaunchAgent {label} is installed and its state can't be read: {e}"
        status = launchd.parse_print(out.stdout + out.stderr)
        if status.running:
            return f"the harness LaunchAgent {label} is running" + (f" (pid {status.pid})" if status.pid else "")
    return None


def _is_claude(argv: List[str]) -> bool:
    """Whether a command line is a Claude Code client: the ``claude`` executable, or a
    JavaScript runtime running the client's script."""
    if not argv:
        return False
    if Path(argv[0]).name == "claude":
        return True
    return Path(argv[0]).name in ("node", "bun") and any(
        Path(a).name == "claude" or ("claude-code" in a and a.endswith("cli.js")) for a in argv[1:3])


def _clients_from_proc(proc: Path = Path("/proc")) -> List[Tuple[int, str]]:
    """(pid, cwd) of every Claude Code client this account owns, from procfs."""
    me, found = os.getuid(), []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.lstat().st_uid != me:
                continue
            argv = [a.decode(errors="replace") for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
            if not _is_claude(argv):
                continue
            found.append((int(entry.name), os.readlink(entry / "cwd")))
        except (OSError, ValueError):
            continue  # it ended while we looked, or is not ours to read
    return found


def _clients_from_ps() -> List[Tuple[int, str]]:
    """(pid, cwd) of every Claude Code client this account owns, from ps and lsof (macOS)."""
    env = {**os.environ, "LC_ALL": "C"}
    try:
        out = subprocess.run(["ps", "-U", str(os.getuid()), "-ww", "-o", "pid=,args="],
                             capture_output=True, text=True, timeout=10, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 2 or not fields[0].isdigit() or not _is_claude(fields[1:]):
            continue
        try:
            cwd = subprocess.run(["lsof", "-a", "-p", fields[0], "-d", "cwd", "-Fn"],
                                 capture_output=True, text=True, timeout=10, env=env).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        names = [ln[1:] for ln in cwd.splitlines() if ln.startswith("n")]
        if names:
            found.append((int(fields[0]), names[0]))
    return found


def _clients_from_sidecars() -> List[Tuple[int, str]]:
    """(pid, cwd) of every live session the client's own sidecars name (~/.claude/sessions)."""
    from macf.notify.session import live_sessions
    with contextlib.redirect_stderr(io.StringIO()):
        return [(s.pid, s.cwd) for s in live_sessions() if s.cwd]


def client_processes() -> List[Tuple[int, str]]:
    """(pid, cwd) of every live Claude Code client of this account, whatever started it."""
    walk = _clients_from_proc() if Path("/proc/self/cmdline").exists() else _clients_from_ps()
    return sorted(set(walk) | set(_clients_from_sidecars()))


def clients_in(directory: Path) -> List[int]:
    """The pids of live clients of this account whose working directory is *directory*."""
    here = Path(directory).resolve()
    return sorted({pid for pid, cwd in client_processes() if Path(cwd).resolve() == here})


def clients_here(ctx: Context) -> List[int]:
    """The pids of live clients whose working directory is the agent's project directory."""
    return clients_in(project_dir(ctx))


def _describe_clients(ctx: Context, pids: List[int]) -> str:
    return f"a Claude Code client already runs in {project_dir(ctx).resolve()} (pid {', '.join(map(str, pids))})"


def live_client_here(ctx: Context) -> Optional[str]:
    """A live client whose working directory is the agent's project directory: the session a
    session unit would resume in the same place, so a second client on the same transcript."""
    pids = clients_here(ctx)
    return _describe_clients(ctx, pids) if pids else None


def legacy_harness_live(ctx: Context) -> Optional[str]:
    """Why a session for this agent may already be running outside its daemon, or None: the
    legacy harness's systemd unit, its LaunchAgent on macOS, or any live client in the
    project directory, however it was started. A session unit started beside any of them
    would be a second client on one conversation (persistent_layer 6.2, 6.3)."""
    return _systemd_harness_live(ctx) or _launchd_harness_live(ctx) or live_client_here(ctx)


def service_manager_missing() -> Optional[str]:
    """Why this host has no service manager pd install can use, or None."""
    if sys.platform.startswith("linux"):
        return None if shutil.which("systemctl") else "systemctl is not on PATH, so there is no systemd to run the daemon"
    if sys.platform == "darwin":
        return None if shutil.which("launchctl") else "launchctl is not on PATH"
    return f"no service manager is supported on {sys.platform}"


def pd_unit_current(card: str, home: Path) -> bool:
    """Whether the service manager's unit for this daemon is installed and as rendered now."""
    from macf.pd import adapter
    if sys.platform.startswith("linux"):
        from macf.platform import systemd
        path, text = systemd.render_pd_user_unit(card, adapter._program(home), str(Path.home()))
        path = Path(path)
        return path.exists() and path.read_text() == text
    if sys.platform == "darwin":
        from macf.platform import launchd
        path, plist = launchd.render_pd_launch_agent(card, adapter._program(home), str(Path.home()),
                                                     adapter.LaunchdAdapter._log_dir(home))
        path = Path(path)
        return path.exists() and path.read_bytes() == plist
    return False


def _adapter():
    """This platform's outer-tier adapter, for the login running agent init."""
    from macf.pd import adapter
    return type(adapter.adapter_for(sys.platform))(user_home=Path.home())


def pd_unit_installed(card: str, home: Path) -> bool:
    """Whether the service manager has a unit for this daemon at all, current or not."""
    installed = getattr(_adapter(), "installed", None)
    return installed is not None and installed(card, home) is not None


def daemon_restart(card: str) -> None:
    """Restart the daemon under its service manager. Its units outlive it and the next daemon
    adopts them (persistent_layer 12.6), so the session keeps running."""
    tier = _adapter()
    restart = getattr(tier, "restart", None)
    if restart is None:
        raise RuntimeError(f"the {tier.platform} adapter offers no restart")
    restart(card)


def install_restarts() -> bool:
    """Whether this platform's forced install already restarts the daemon (launchd boots the
    job out and bootstraps it), so --update mustn't restart it again."""
    return bool(getattr(_adapter(), "install_restarts", False))


def unit_program(text: Optional[str]) -> Optional[str]:
    """The program an installed unit runs: a LaunchAgent's ``Program`` (or the first of its
    ``ProgramArguments``), a systemd unit's first ``ExecStart`` word. None if it can't be read."""
    import plistlib
    import shlex
    if not text:
        return None
    try:
        plist = plistlib.loads(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 - not a plist; read it as a systemd unit below
        plist = None
    if isinstance(plist, dict):
        args = plist.get("ProgramArguments") or []
        return plist.get("Program") or (args[0] if args else None)
    for line in text.splitlines():
        if line.startswith("ExecStart="):
            words = shlex.split(line[len("ExecStart="):])
            return words[0] if words else None
    return None


def program_change(ctx: Context) -> Optional[Tuple[str, str]]:
    """(installed, rendered) when the installed unit runs another program than this command
    would render, None when they agree or either can't be read. The rendered program is the
    interpreter running agent init, so on a login where several macf installs sit on PATH, a
    daemon pinned to its own venv would otherwise be moved by whichever one ran."""
    tier = _adapter()
    installed = getattr(tier, "installed", None)
    if installed is None:
        return None
    try:
        was = unit_program(installed(ctx.card, ctx.home))
        now = unit_program(tier.render(ctx.card, ctx.home))
    except (OSError, ValueError):
        return None  # noqa: MACEFF003 - unreadable is no finding; the currency checks still run
    return (was, now) if was and now and was != now else None


def daemon_build_drift(ctx: Context) -> Optional[str]:
    """How the running daemon's build differs from this command's, as ``pd status`` reads it,
    or None when they match or no daemon answers to say."""
    from macf.pd.client import status
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            report = status(ctx.home, ctx.card)
    except Exception:  # noqa: BLE001 - a readout that fails says nothing about the build
        return None  # noqa: MACEFF003 - no answer is no finding; the daemon step says what it can
    if report.source != "daemon":
        return None
    if not report.daemon_build:
        return f"the running daemon doesn't say which build it runs, so it is older than this command's {report.cli_build}"
    if report.daemon_build != report.cli_build:
        return f"the running daemon runs {report.daemon_build}, this command {report.cli_build}"
    return None


def currency_findings(ctx: Context) -> List[str]:
    """What keeps an installed daemon from being current: a unit that differs from what the
    renderer writes now, and a running daemon on another build."""
    found = []
    if not pd_unit_current(ctx.card, ctx.home):
        found.append("the installed unit differs from what this macf renders now")
    moved = program_change(ctx)
    if moved:
        found.append(f"the installed unit runs {moved[0]}; this command would render {moved[1]}")
    drift = daemon_build_drift(ctx)
    if drift:
        found.append(drift)
    return found


def _daemon_currency(ctx: Context, installed: str) -> Result:
    """An installed daemon: current, or what isn't, with the fix; under ``--update`` the fix,
    which reinstalls the unit as rendered now and restarts the daemon once. The session unit
    is never restarted: the new daemon adopts it, as any daemon restart does."""
    findings = currency_findings(ctx)
    if not findings:
        return Result("daemon", ALREADY, f"{installed}; the unit is as rendered and the daemon runs this build")
    lines = "\n".join(f"- {f}" for f in findings)
    if not getattr(ctx.args, "update", False):
        return Result("daemon", DRIFT, f"{installed}, but it isn't current:\n{lines}\n"
                                       f"{UPDATE_FIX} reinstalls the unit and restarts the daemon onto this "
                                       f"build; its units, the session among them, carry across")
    moved = program_change(ctx)
    if moved and not getattr(ctx.args, "repoint", False):
        # The daemon may be pinned on purpose to its own venv or checkout; moving it to
        # whichever macf ran this command is the operator's choice, not a side effect.
        return Result("daemon", REFUSED, f"the installed unit runs {moved[0]}, and this command would point "
                                         f"it at {moved[1]}. Run agent init --update with {moved[0]} to "
                                         f"keep the daemon where it is, or add --repoint to move it")
    if ctx.dry_run:
        return Result("daemon", WOULD, f"reinstall the unit as rendered now and restart the daemon onto this "
                                       f"build, its units carrying across:\n{lines}")
    from macf.pd.cli import cmd_pd_install
    rc, text = _captured(lambda: cmd_pd_install(argparse.Namespace(plan=False, force=True)))
    if rc != 0:
        return Result("daemon", REFUSED, "pd install --force: " + (text.replace("maceff_pd: ", "").strip() or f"exit {rc}"))
    if not install_restarts():
        try:
            daemon_restart(ctx.card)
        except (OSError, RuntimeError) as e:
            return Result("daemon", REFUSED, f"the unit was reinstalled, but the daemon wasn't restarted: {e}")
    return Result("daemon", DONE, "unit reinstalled as rendered now, daemon restarted onto this build; its units "
                                  "carry across, the session among them")


def _captured(fn: Callable[[], int]) -> Tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn()
    return rc, (out.getvalue() + err.getvalue()).strip()


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_task_store(ctx: Context) -> Result:
    from macf.task.reader import TaskReader
    _, rel = TaskReader._load_task_store_config()
    store = ctx.home / rel
    try:
        config = json.loads((ctx.home / ".maceff" / "config.json").read_text())
    except (OSError, ValueError):
        config = {}
    if store.is_dir() and (config.get("task_store") or {}).get("mode") == "home":
        return Result("task-store", ALREADY, str(store))
    if ctx.dry_run:
        return Result("task-store", WOULD, f"create {store} and point the config at it")
    from macf.cli import cmd_task_store_init
    rc, text = _captured(lambda: cmd_task_store_init(argparse.Namespace(home=str(ctx.home))))
    if rc != 0:
        return Result("task-store", REFUSED, _last_line(text))
    return Result("task-store", DONE, str(store))


def step_declaration(ctx: Context) -> Result:
    from macf.pd import default_declaration as dd
    from macf.pd.names import declaration_path, rendered_declaration_path
    if not resolve_card(ctx):
        return Result("declaration", REFUSED, f"{ctx.card_error}; set agent_identity.calling_card "
                                              f"in {ctx.home / '.maceff' / 'config.json'}")
    default = default_declaration(ctx)
    why = _validate(default)
    if why:
        return Result("declaration", REFUSED, f"the default declaration doesn't validate: {why}")
    path = declaration_path(ctx.home)
    if ctx.in_container and path != rendered_declaration_path(ctx.home):
        ctx.declaration = default
        return Result("declaration", SKIPPED,
                      "in a container the deployment renders the declaration from agents.yaml "
                      "(primal_daemon), and a declaration only in the home fails the start step")
    if os.path.lexists(path):
        try:
            existing = json.loads(Path(path).read_text())
        except (OSError, ValueError) as e:
            return Result("declaration", REFUSED, f"{path} exists and can't be read: {e}; left as it is")
        why = _validate(existing)
        ctx.declaration = existing
        lacks = dd.drift(existing, default)
        detail = f"{path} exists and is never overwritten"
        if why:
            return Result("declaration", REFUSED, f"{detail}; it doesn't validate: {why}")
        if lacks:
            return Result("declaration", DRIFT, detail + "; compared with the default it lacks:\n"
                          + "\n".join(f"- {d}" for d in lacks))
        return Result("declaration", ALREADY, f"{path} has every default unit")
    if getattr(ctx.args, "update", False):
        return Result("declaration", SKIPPED, f"none at {path}, and --update never writes one; run agent init "
                                              f"without --update for the default")
    target = Path(path)
    live = legacy_harness_live(ctx)
    if live:
        target = target.with_name(target.name + ".cutover")
        if target.exists():
            ctx.staged = target
            ctx.declaration = json.loads(target.read_text())
            return Result("declaration", ALREADY, f"staged at {target} for macf_tools harness cutover ({live})")
    if ctx.dry_run:
        ctx.declaration = default
        units = ", ".join(u["name"] for u in default["units"])
        if live:
            ctx.staged = target
            return Result("declaration", WOULD, f"stage the default declaration ({units}) at {target}, not "
                                                f"install it: {live}")
        return Result("declaration", WOULD, f"write the default declaration at {target}: units {units}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(default, indent=2) + "\n")
    os.replace(tmp, target)
    ctx.declaration = default
    if live:
        ctx.staged = target
        return Result("declaration", DONE, f"staged at {target}, not installed: {live}. A session "
                                           f"unit beside it would be a second client on one "
                                           f"conversation; stop that session deliberately, then run "
                                           f"macf_tools harness cutover")
    return Result("declaration", DONE, f"{target}: units {', '.join(u['name'] for u in default['units'])}")


def _declared_channel_flags(ctx: Context) -> List[str]:
    from macf.channels.marketplace import CHANNEL_FLAG
    from macf.pd import default_declaration as dd
    declared = (ctx.declaration or {}).get("allowlisted_channels")
    if declared is None:
        declared = (default_declaration(ctx) if ctx.card else {}).get("allowlisted_channels") or []
    flags = [dd.channel_flag(c["plugin"], c["marketplace"]) for c in declared]
    if CHANNEL_FLAG not in flags:
        flags.append(CHANNEL_FLAG)
    # Channels already recorded for the harness are kept, first: a reinstall that dropped one
    # would take that inbound link down with nothing to see.
    recorded = list(_harness_settings(ctx).get("channels") or [])
    return list(dict.fromkeys(recorded + flags))


def step_harness(ctx: Context) -> Result:
    if ctx.in_container:
        return Result("harness", SKIPPED, CONTAINER_OWNS)
    if not ctx.card and not resolve_card(ctx):
        return Result("harness", REFUSED, ctx.card_error)
    from macf.cli import cmd_harness_install
    from macf.pd.names import pd_id
    channels = _declared_channel_flags(ctx)

    def ns(check: bool) -> argparse.Namespace:
        return argparse.Namespace(agent=pd_id(ctx.card), home=str(ctx.home), channel=channels,
                                  project_dir=str(project_dir(ctx)), no_proxy=False, shell_prefix=None,
                                  remote_control=None, watchdog=False, check=check, force=False)
    rc, _ = _captured(lambda: cmd_harness_install(ns(True)))
    if rc == 0:
        return Result("harness", ALREADY, f"channels {' '.join(channels)}")
    if ctx.dry_run:
        return Result("harness", WOULD, f"install the child script and settings with channels {' '.join(channels)}")
    rc, text = _captured(lambda: cmd_harness_install(ns(False)))
    if rc != 0:
        return Result("harness", REFUSED, text.replace("Error: ", "").strip() or f"exit {rc}")
    return Result("harness", DONE, f"channels {' '.join(channels)}")


def _plugin_state(login_home: Path) -> Tuple[set, set]:
    plugins = login_home / ".claude" / "plugins"
    try:
        known = set(json.loads((plugins / "known_marketplaces.json").read_text()))
    except (OSError, ValueError, TypeError):
        known = set()
    try:
        installed = set((json.loads((plugins / "installed_plugins.json").read_text()).get("plugins") or {}))
    except (OSError, ValueError, TypeError, AttributeError):
        installed = set()
    return known, installed


def step_channel(ctx: Context) -> Result:
    from macf.channels.marketplace import CHANNEL_PLUGIN_ID, MARKETPLACE, packaged_marketplace
    known, installed = _plugin_state(ctx.login_home)
    update = getattr(ctx.args, "update", False)
    if MARKETPLACE in known and CHANNEL_PLUGIN_ID in installed and not update:
        return Result("channel", ALREADY, CHANNEL_PLUGIN_ID)
    claude = shutil.which("claude")
    if claude is None:
        return Result("channel", REFUSED, "the claude CLI is not on PATH; install Claude Code, then "
                                          "run agent init again")
    try:
        source = packaged_marketplace()
    except FileNotFoundError as e:
        return Result("channel", REFUSED, str(e))
    commands = []
    if ctx.dry_run:
        todo = ([f"add the marketplace {source}"] if MARKETPLACE not in known else
                [f"refresh the marketplace {MARKETPLACE}"] if update else []) + \
            ([f"install {CHANNEL_PLUGIN_ID}"] if CHANNEL_PLUGIN_ID not in installed else
             [f"refresh {CHANNEL_PLUGIN_ID}"] if update else [])
        return Result("channel", WOULD, "; ".join(todo))
    # Under --update, what is already there is refreshed, as a container's start step does.
    commands.append([claude, "plugin", "marketplace", "add", str(source)] if MARKETPLACE not in known
                    else [claude, "plugin", "marketplace", "update", MARKETPLACE])
    commands.append([claude, "plugin", "install", CHANNEL_PLUGIN_ID] if CHANNEL_PLUGIN_ID not in installed
                    else [claude, "plugin", "update", CHANNEL_PLUGIN_ID])
    if not update:
        commands = [c for c in commands if "update" not in c[2:4]]
    for argv in commands:
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as e:
            return Result("channel", REFUSED, f"{' '.join(argv[1:])}: {e}")
        if out.returncode != 0:
            said = _last_line(out.stderr) or _last_line(out.stdout) or f"exit {out.returncode}"
            return Result("channel", REFUSED, f"claude {' '.join(argv[1:])} failed: {said}")
    return Result("channel", DONE, f"{CHANNEL_PLUGIN_ID} from {source}" + (
        " (refreshed; the session loads it at its next start)" if update and CHANNEL_PLUGIN_ID in installed else ""))


def step_permissions(ctx: Context) -> Result:
    from macf.utils.claude_settings import ensure_mode_safety_permissions
    root = project_dir(ctx)
    if ctx.dry_run:
        missing = _missing_permissions(root)
        where = root / ".claude" / "settings.local.json"
        if missing is None:
            return Result("permissions", REFUSED, f"{where} can't be read")
        if not missing:
            return Result("permissions", ALREADY, str(where))
        return Result("permissions", WOULD, f"add {len(missing)} entr{'y' if len(missing) == 1 else 'ies'} to {where}")
    try:
        (root / ".claude").mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Result("permissions", REFUSED, f"{root / '.claude'} can't be made: {e}")
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = ensure_mode_safety_permissions(root)
    if result is None:
        return Result("permissions", REFUSED, _last_line(out.getvalue()) or "the settings couldn't be written")
    added = sum(len(v) for v in result.values())
    where = root / ".claude" / "settings.local.json"
    if not added:
        return Result("permissions", ALREADY, str(where))
    return Result("permissions", DONE, f"{added} entr{'y' if added == 1 else 'ies'} added to {where}")


def _missing_permissions(root: Path) -> Optional[List[str]]:
    """The entries ensure_mode_safety_permissions would add, by its own lists, without writing."""
    from macf.utils import claude_settings as cs
    try:
        settings, _path = cs._read_settings(root)
    except (OSError, ValueError):
        return None  # noqa: MACEFF003 - None is "can't read"; the caller refuses the step, naming the file
    perms = settings.get("permissions") or {}
    deny, ask, allow = (perms.get(k) or [] for k in ("deny", "ask", "allow"))
    return ([e for e in cs._PERMANENT_DENY if e not in deny] + [e for e in cs._PERMANENT_ASK if e not in ask]
            + [e for e in cs._PERMANENT_ALLOW if e not in allow]
            + [e for e in cs._DEFAULT_ASK if e not in ask and e not in allow])


def _declares_session(declaration: Optional[Dict]) -> bool:
    return any(u.get("kind") == "session" for u in (declaration or {}).get("units") or [])


def daemon_session_pid(ctx: Context, declaration: Optional[Dict]) -> Optional[int]:
    """The pid of this agent's session unit, as its running daemon confirms it, or None: no
    daemon answers, or it doesn't report the declared session unit up with a pid."""
    names = [u.get("name") for u in (declaration or {}).get("units") or [] if u.get("kind") == "session"]
    if not names or not ctx.card:
        return None
    from macf.pd.client import status
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            report = status(ctx.home, ctx.card)
    except Exception:  # noqa: BLE001 - a readout that fails confirms nothing
        return None  # noqa: MACEFF003 - unconfirmed, so the live-session guard keeps blocking
    if report.source != "daemon":
        return None
    for unit in report.units:
        if unit.get("unit") == names[0] and unit.get("state") in ("running", "waiting_on_a_person") \
                and unit.get("pid"):
            return int(unit["pid"])
    return None


def ancestors(pid: int) -> set:
    """*pid* and its ancestors (``supervisor.ancestor_pids``)."""
    from macf.supervisor import ancestor_pids
    return ancestor_pids(pid)


def step_daemon(ctx: Context) -> Result:
    if ctx.in_container:
        return Result("daemon", SKIPPED, "in a container, the container's start step starts the daemon")
    if ctx.staged:
        return Result("daemon", SKIPPED, f"the declaration is staged at {ctx.staged}; "
                                         f"macf_tools harness cutover installs it, and the daemon too "
                                         f"(pd install) where none is installed")
    missing = service_manager_missing()
    if missing:
        return Result("daemon", SKIPPED, f"{missing}; pd install has nothing to install into here")
    if not ctx.card and not resolve_card(ctx):
        return Result("daemon", REFUSED, ctx.card_error)
    from macf.pd.names import declaration_path
    from macf.utils.paths import find_agent_home
    path = declaration_path(ctx.home)
    if path.exists():
        try:
            declaration = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            return Result("daemon", REFUSED, f"{path} can't be read: {e}")
    elif ctx.dry_run and ctx.declaration is not None:
        declaration = ctx.declaration     # the one the declaration step would write
    else:
        return Result("daemon", REFUSED, f"no declaration at {path}")
    # Whatever the declaration step found, new, existing or drifted: a session unit started beside
    # a session already running would be a second client on one conversation (6.2, 6.3).
    # A client below this agent's own confirmed session unit is that unit's session, not a
    # second one.
    ours: List[int] = []
    if _declares_session(declaration):
        unit_pid = daemon_session_pid(ctx, declaration)
        pids = clients_here(ctx)
        ours = [p for p in pids if unit_pid is not None and unit_pid in ancestors(p)]
        foreign = [p for p in pids if p not in ours]
        live = _systemd_harness_live(ctx) or _launchd_harness_live(ctx) or \
            (_describe_clients(ctx, foreign) if foreign else None)
        # The daemon itself never starts a session unit beside such a session (persistent_layer
        # 6.2); this skip stays because installing it now would arm a session that starts on its
        # own the moment the person quits theirs, which is a move nobody chose. harness cutover
        # makes that move deliberately, and installs the daemon itself where none is.
        if live:
            return Result("daemon", SKIPPED, f"pd install not run: {live}. Its session unit would be a "
                                             f"second client on one conversation; stop that session "
                                             f"deliberately, then run macf_tools harness cutover")
        if ours:
            installed = f"pd install; the session runs as its daemon's unit (pid {unit_pid})"
            if not getattr(ctx.args, "update", False):
                return _daemon_currency(ctx, installed)
    resolved = Path(find_agent_home()).resolve()
    if resolved != ctx.home.resolve():
        return Result("daemon", REFUSED, f"pd install acts on the agent home {resolved}, not {ctx.home}; "
                                         f"run agent init from that agent's home")
    if ours:
        return _daemon_currency(ctx, installed)
    if pd_unit_current(ctx.card, ctx.home) or pd_unit_installed(ctx.card, ctx.home):
        return _daemon_currency(ctx, "the service manager's unit is installed")
    if ctx.dry_run:
        return Result("daemon", WOULD, "pd install: put the daemon under the service manager")
    from macf.pd.cli import cmd_pd_install
    rc, text = _captured(lambda: cmd_pd_install(argparse.Namespace(plan=False, force=False)))
    if rc != 0:
        return Result("daemon", REFUSED, text.replace("maceff_pd: ", "").strip() or f"exit {rc}")
    return Result("daemon", DONE, _last_line(text))


RUNNERS: Dict[str, Callable[[Context], Result]] = {
    "task-store": step_task_store,
    "declaration": step_declaration,
    "harness": step_harness,
    "channel": step_channel,
    "permissions": step_permissions,
    "daemon": step_daemon,
}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def print_plan(ctx: Context, header: str = "agent init will:") -> None:
    print(header)
    update = getattr(ctx.args, "update", False)
    for i, (step, what, flag) in enumerate(STEPS, 1):
        skip = f"  [skipped: --{flag.replace('_', '-')}]" if getattr(ctx.args, flag, False) else \
            "  [skipped: --update]" if update and step not in UPDATE_STEPS else ""
        print(f"  {i}. {step}: {what}{skip}")


def report(results: List[Result], header: str = "agent init:") -> None:
    print(f"\n{header}")
    for r in results:
        lines = (r.detail or "").splitlines() or [""]
        print(f"  {r.step}: {r.status}" + (f": {lines[0]}" if lines[0] else ""))
        for extra in lines[1:]:
            print(f"      {extra}")


def run_stack(args: argparse.Namespace, home: Path, *, in_container: bool,
              preamble: Callable[[], Result], login_home: Optional[Path] = None) -> Tuple[int, List[Result]]:
    """Print the plan, run each step not skipped, and report. Returns (exit code, results):
    1 when any step refused, else 0. A preamble the operator aborted stops the run there."""
    ctx = Context(home=Path(home), login_home=Path(login_home or Path.home()),
                  in_container=in_container, args=args)
    plan = getattr(args, "plan", False)
    ctx.dry_run = plan
    if not plan:   # under --plan the findings are the plan
        print_plan(ctx)
    results: List[Result] = []
    update = getattr(args, "update", False)
    if update and in_container:
        results.append(Result("update", SKIPPED, "in a container, the container's start step brings the stack "
                                                 "current when the container starts; nothing was changed"))
        report(results, "agent init --update:")
        return 0, results
    for step, _what, flag in STEPS:
        if update and step not in UPDATE_STEPS:
            results.append(Result(step, SKIPPED, NOT_UPDATED))
            continue
        if getattr(args, flag, False):
            results.append(Result(step, SKIPPED, f"--{flag.replace('_', '-')}"))
            continue
        if plan and step == "preamble":
            results.append(Result(step, PLANNED, "reconcile CLAUDE.md (checked when run, since it may ask first)"))
            continue
        try:
            result = preamble() if step == "preamble" else RUNNERS[step](ctx)
        except Exception as e:  # noqa: BLE001 - one step's defect is reported, the rest still run
            result = Result(step, REFUSED, f"{type(e).__name__}: {e}")
        results.append(result)
        if step == "preamble" and result.status == "aborted":
            print("Aborted.")
            return 0, results
    report(results, "agent init --plan (nothing changed):" if plan else "agent init:")
    return (1 if any(r.status == REFUSED for r in results) else 0), results
