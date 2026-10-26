"""Moving an agent's session from the legacy harness onto its primal daemon: the plan.

``macf_tools harness cutover`` reads the host and prints what a move would do for one
agent, step by step, with the rollback, and changes nothing. It is the runbook the host's
first move followed (persistent_layer 6.3), generated for the agent at hand from what is
actually installed, so no step names a unit that isn't there or misses one that is.

The plan is built from probes passed in, so every case can be tested without systemd,
tmux or a daemon: ``build_plan(..., probes=Probes(...))``. ``host_probes`` are the real ones.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from macf.pd.interface import Declaration, declaration_path
from macf.pd.names import systemd_unit
from macf.pd.session_unit import PANE_GRACE_S, tmux_socket

#: Where a declaration with the session unit is staged before the move.
STAGED_SUFFIX = ".cutover"
#: Where the declaration the move replaces is kept, for the rollback.
SAVED_SUFFIX = ".pre-cutover"


@dataclass(frozen=True)
class Check:
    """One thing the move depends on, read from the host, and whether it holds."""
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Command:
    """One command of a step, as an argument list, so what is printed is what would run.
    ``env`` is added to the caller's environment; ``may_fail`` marks a command whose failure
    means only that there was nothing to do, such as ending a session already gone."""
    argv: List[str]
    note: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    may_fail: bool = False
    #: How long the command may run, where it may take longer than the usual 120 s.
    timeout: Optional[float] = None

    def __str__(self) -> str:
        prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in self.env.items())
        return prefix + shlex.join(self.argv) + (f"      # {self.note}" if self.note else "")


@dataclass(frozen=True)
class Step:
    """A step, and the commands that undo it. A failed move undoes only the steps it
    reached, last first, so a step that never ran is never undone (head maintainer, on
    review: the old single rollback could copy a stale saved declaration back)."""
    what: str
    commands: List[Command]
    undo: List[Command] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    agent: str
    card: str
    ready: bool
    checks: List[Check]
    steps: List[Step] = field(default_factory=list)

    @property
    def rollback(self) -> List[Command]:
        """Every step's undo, last step first: what a failure at the last step runs."""
        return [c for step in reversed(self.steps) for c in step.undo]
    #: The staged declaration's session unit, whose state says whether the move took.
    session_unit: Optional[str] = None
    #: The init system the steps are written for: "systemd" or "launchd".
    init: Optional[str] = None


@dataclass(frozen=True)
class Probes:
    """The host, as the plan reads it.

    - ``systemd``: whether user units can be managed here at all.
    - ``unit_active``: ``systemctl --user is-active`` of one unit.
    - ``active_units``: the names of the user's active service units.
    - ``default_session``: whether the agent's session is on the default tmux server.
    - ``unit_session``: whether it is already on the session unit's own server.
    - ``daemon_answers``: None when the agent's daemon answers, else why not.
    - ``launchd``: whether per-user LaunchAgents can be managed here (macOS). Read only
      where ``systemd`` is False; on launchd ``unit_active`` and ``active_units`` speak of
      job labels in ``gui/<uid>``, with "active" meaning launchd reports the job running.
    - ``harness_label``: on launchd, the label of the legacy harness LaunchAgent installed
      for the agent, or None. A systemd host names its harness unit by convention.
    """
    systemd: bool
    unit_active: Callable[[str], str]
    active_units: Callable[[], List[str]]
    default_session: Callable[[str], bool]
    unit_session: Callable[[str], bool]
    daemon_answers: Callable[[], Optional[str]]
    launchd: bool = False
    harness_label: Callable[[str], Optional[str]] = lambda agent: None
    #: (pid, working directory, process start) of each live Claude Code client in the agent's
    #: project directory, however it was started (agent_stack.clients_here): a hand-started
    #: session. The start is ``notify.session.proc_start``, the fingerprint the core keeps for
    #: the units it adopts, so the move signals the process it planned for and no other.
    hand_started: Callable[[str], List[Tuple[int, str, str]]] = lambda agent: []
    #: Whether the daemon is installed under the service manager at all. One that isn't is
    #: installed by the move, after the declaration (``pd install``, undone by ``pd uninstall``).
    daemon_installed: Callable[[], bool] = lambda: True


def staged_path(home: Path) -> Path:
    path = declaration_path(home)
    return path.with_name(path.name + STAGED_SUFFIX)


def _staged_check(path: Path, card: str, runtime: Optional[str], init: str = "systemd") -> Check:
    try:
        declaration = Declaration.model_validate_json(path.read_text())
    except FileNotFoundError:
        return Check("staged declaration", False,
                     f"none at {path}: stage the declaration with the session unit there first")
    except (OSError, ValidationError) as e:
        return Check("staged declaration", False, f"{path} doesn't validate: {e}")
    if declaration.agent != card:
        return Check("staged declaration", False, f"{path} declares {declaration.agent}, not {card}")
    session = next((u for u in declaration.units if u.kind == "session"), None)
    if session is None:
        return Check("staged declaration", False, f"{path} declares no session unit (kind: session)")
    if session.stop_grace_s <= PANE_GRACE_S:
        return Check("staged declaration", False,
                     f"the session unit's stop_grace_s {session.stop_grace_s:g} must exceed the "
                     f"wrapper's {PANE_GRACE_S:g} s pane grace (persistent_layer 6.2)")
    # The unit's liveness variables need no check here: the daemon sets them from the unit
    # (persistent_layer 11.2), and a declared value that disagrees is refused at load.
    # A unit gets only its declared environment, so without this its tmux server sits under
    # /tmp, where attach, harness status and the rollback look for it in vain.
    declared = session.environment.get("XDG_RUNTIME_DIR")
    # macOS sets no XDG_RUNTIME_DIR, so there the unit and every client fall back to the same
    # per-user directory under /tmp (names.runtime_dir): agreement is what counts, both unset too.
    if init == "launchd" and not runtime:
        if declared:
            return Check("staged declaration", False,
                         f"the session unit's environment declares XDG_RUNTIME_DIR={declared}, which "
                         "this host's clients don't set, so its tmux server lands where nothing looks")
    elif not declared or (runtime and declared != runtime):
        return Check("staged declaration", False,
                     f"the session unit's environment must declare XDG_RUNTIME_DIR={runtime or '<yours>'} "
                     f"(it declares {declared or 'none'}), or its tmux server lands where nothing looks")
    return Check("staged declaration", True, f"{path} validates, with session unit {session.name}")


def default_socket(uid: Optional[int] = None) -> Path:
    """The default tmux server's socket, where the legacy harness runs. Every tmux command
    in a plan names its server's socket with ``-S``: inside a tmux client, ``TMUX`` outranks
    ``TMUX_TMPDIR``, so a pasted ``TMUX_TMPDIR=... tmux kill-server`` would end the server
    the operator is typing in."""
    import os
    return Path("/tmp") / f"tmux-{os.getuid() if uid is None else uid}" / "default"


@dataclass(frozen=True)
class _Init:
    """The commands that differ between init systems; every step is built from these, so the
    steps, their order and their undo are the same on systemd and launchd."""
    name: str
    describe: str
    harness: str
    daemon: str
    stop_clock: Callable[[str], List[Command]]
    start_clock: Callable[[str], List[Command]]
    stop_harness: Callable[[str], List[Command]]
    start_harness: Callable[[str], List[Command]]
    restart_daemon: Callable[[], Command]


def _systemd_init(agent: str, card: str, harness_unit: Optional[str]) -> _Init:
    def systemctl(*args: str) -> Command:
        return Command(["systemctl", "--user", *args])
    daemon = systemd_unit(card)
    return _Init("systemd", "systemd: the user's service manager (systemctl --user)",
                 harness_unit or f"cc-harness-{agent}.service", daemon,
                 stop_clock=lambda u: [systemctl("disable", "--now", u)],
                 start_clock=lambda u: [systemctl("enable", "--now", u)],
                 stop_harness=lambda u: [systemctl("stop", u), systemctl("disable", u)],
                 start_harness=lambda u: [systemctl("enable", "--now", u)],
                 restart_daemon=lambda: systemctl("restart", daemon))


def _launchd_init(agent: str, card: str, harness_label: Optional[str], uid: int,
                  launch_agents: Path) -> _Init:
    """launchd's counterparts: a job is stopped with ``bootout`` and kept from starting at
    the next login with ``disable``, the pair systemd's ``disable --now`` is; it is started
    again with ``enable``, then ``bootstrap`` of its plist, since launchd refuses to load a
    disabled job. The daemon restarts with ``kickstart -k`` (persistent_layer 3.1)."""
    from macf.platform import launchd

    def ctl(verb: str, label: str) -> Command:
        plist = str(launch_agents / f"{label}.plist") if verb == "bootstrap" else None
        return Command(launchd.launchctl_argv(verb, label, uid, plist_path=plist))

    def stop(label: str) -> List[Command]:
        return [ctl("bootout", label), ctl("disable", label)]

    def start(label: str) -> List[Command]:
        return [ctl("enable", label), ctl("bootstrap", label)]
    daemon = launchd.pd_label(card)
    return _Init("launchd", f"launchd: per-user LaunchAgents in gui/{uid} (launchctl)",
                 harness_label or f"<no harness LaunchAgent for {agent}>", daemon,
                 stop_clock=stop, start_clock=start, stop_harness=stop, start_harness=start,
                 restart_daemon=lambda: ctl("kickstart", daemon))


def build_plan(home: Path, card: str, agent: str, probes: Probes,
               staged: Optional[Path] = None, harness_unit: Optional[str] = None,
               runtime: Optional[str] = None, uid: Optional[int] = None,
               launch_agents: Optional[Path] = None) -> Plan:
    """What moving *agent*'s session onto its daemon would do, and whether it can be done now.

    *agent* is the session identifier (``Name_uuid6``), *card* the calling card, *runtime*
    the caller's ``XDG_RUNTIME_DIR`` (the process environment's by default), which the
    session unit must declare so its tmux server is where every client looks. On launchd,
    *uid* names the ``gui/<uid>`` domain and *launch_agents* the directory the plists of the
    jobs a step stops are in, to load them again on undo (``~/Library/LaunchAgents``).
    """
    import os
    from macf.pd.names import PD_IDENTIFIER
    runtime = runtime if runtime is not None else os.environ.get("XDG_RUNTIME_DIR")
    # Where the unit's tmux server will be, from the runtime directory it must declare.
    unit_base = Path(runtime) / PD_IDENTIFIER if runtime else None
    staged = staged or staged_path(home)
    live = declaration_path(home)
    saved = live.with_name(live.name + SAVED_SUFFIX)
    checks: List[Check] = []

    if probes.unit_session(agent):
        checks.append(Check("session", True,
                            "already runs as the primal daemon's session unit: nothing to move"))
        return Plan(agent, card, False, checks)
    if probes.systemd:
        init = _systemd_init(agent, card, harness_unit)
        legacy = probes.unit_active(init.harness) == "active"
    elif probes.launchd:
        label = probes.harness_label(agent)
        init = _launchd_init(agent, card, label, os.getuid() if uid is None else uid,
                             launch_agents or Path.home() / "Library" / "LaunchAgents")
        legacy = label is not None and probes.unit_active(label) == "active"
    else:
        checks.append(Check("init system", False,
                            "neither systemctl nor launchctl here: this plan covers systemd and "
                            "launchd hosts (persistent_layer 6.3)"))
        return Plan(agent, card, False, checks)
    checks.append(Check("init system", True, init.describe))

    checks.append(_staged_check(staged, card, runtime, init.name))
    why = probes.daemon_answers()
    # No daemon installed at all, as for a seat agent init left for this move: installing it is
    # a step. One installed that doesn't answer is a fault the move would only hide.
    install_daemon = why is not None and not probes.daemon_installed()
    checks.append(Check("daemon", why is None or install_daemon,
                        "answers on its socket" if why is None else
                        "not installed: the move installs it after the declaration (pd install)"
                        if install_daemon else why))
    if init.name == "launchd" and probes.harness_label(agent) is None:
        checks.append(Check("legacy harness", True, f"no harness LaunchAgent for {agent} is installed, "
                            "so there is no legacy harness to stop"))
    else:
        checks.append(Check("legacy harness", True, f"{init.harness} is active" if legacy else
                            f"{init.harness} isn't active, so there is no legacy session to stop"))
    held = probes.default_session(agent)
    checks.append(Check("legacy session", True, f"={agent} is on the default tmux server" if held
                        else f"no ={agent} on the default tmux server"))
    # A client started by hand, in a terminal, is held by no unit and no tmux server: it is
    # looked for only where neither holds the session, and is the session the move ends.
    clients = [] if (legacy or held) else sorted(probes.hand_started(agent))
    if clients:
        checks.append(Check("hand-started client", True,
                            f"Claude Code pid {', '.join(str(c[0]) for c in clients)} runs in "
                            f"{clients[0][1]}, held by no unit or tmux server"))
    clocks = sorted(u for u in probes.active_units() if "mail-clock" in u and u != init.daemon)
    checks.append(Check("duplicate clocks", True, ", ".join(clocks) + " running beside the daemon's"
                        if clocks else "none running beside the daemon's"))
    # A saved declaration from an earlier attempt is not this move's to restore or overwrite:
    # it may hold what the live one has since lost, or the reverse (head maintainer, on review).
    checks.append(Check("saved declaration", not saved.exists(),
                        f"{saved} is left from an earlier attempt: compare it with {live}, keep what "
                        "you need, and remove it" if saved.exists() else f"no {saved.name} from an earlier attempt"))

    steps: List[Step] = []
    if clocks:
        steps.append(Step("Stop the clocks that would type into the pane beside the daemon's",
                          [c for u in clocks for c in init.stop_clock(u)],
                          undo=[c for u in clocks for c in init.start_clock(u)]))
    if legacy or held:
        stop = init.stop_harness(init.harness) if legacy else []
        stop.append(Command(["tmux", "-S", str(default_socket()), "kill-session", "-t", f"={agent}"],
                            note="the pane a stop left behind, if any", may_fail=True))
        # A monitor the old session's hooks started is not a unit, so stopping the session
        # doesn't always end it; left running, it holds the transcript and the new session's
        # monitor stands down, so the unit never beats (host-side maintainer, on review).
        stop.append(Command([sys.executable, "-m", "macf.pd.cutover", "end-stale-monitors", str(home)],
                            note="transcript monitors of this agent whose session has ended"))
        steps.append(Step("Stop the legacy session (a session running here ends at this step)", stop,
                          undo=init.start_harness(init.harness) if legacy else []))
    if clients:
        grace = _session_grace(staged)
        pids = ", ".join(str(c[0]) for c in clients)
        end = [Command([sys.executable, "-m", "macf.pd.cutover", "end-client", str(pid), start, f"{grace:g}"],
                       note=f"SIGTERM to pid {pid} alone, only while it is still the process started "
                            f"at {start}, then up to {grace:g} s for it to exit",
                       timeout=grace + 30) for pid, _, start in clients]
        end.append(Command([sys.executable, "-m", "macf.pd.cutover", "end-stale-monitors", str(home)],
                           note="transcript monitors of this agent whose session has ended"))
        where = clients[0][1]
        steps.append(Step(f"Stop the hand-started client (pid {pids}; a session running here ends at "
                          "this step)", end,
                          undo=[Command(["true"], note=f"the hand-started session ended and isn't "
                                        f"restarted; resume it with claude -c in {where}")]))
    restart = [] if install_daemon else [init.restart_daemon()]
    end_unit = Command(["tmux", "-S", str(tmux_socket(agent, unit_base)), "kill-server"],
                       note="the unit's session, no longer declared, before the legacy one starts",
                       may_fail=True)
    if live.exists():
        steps.append(Step("Install the declaration with the session unit, keeping the old one",
                          [Command(["cp", str(live), str(saved)]), Command(["cp", str(staged), str(live)]),
                           *restart],
                          undo=[Command(["cp", str(saved), str(live)]), *restart, end_unit,
                                Command(["rm", str(saved)], note="restored, so no later attempt finds it")]))
    else:
        # A seat agent init staged for this move has no declaration yet: nothing to keep, and
        # the undo removes the one installed.
        steps.append(Step("Install the declaration with the session unit (there is none to keep)",
                          [Command(["cp", str(staged), str(live)]), *restart],
                          undo=[Command(["rm", str(live)], note="there was none before the move"),
                                *restart, end_unit]))
    if install_daemon:
        pd_env = {"MACEFF_AGENT_HOME_DIR": str(home)}
        steps.append(Step(f"Install the primal daemon under {init.name} (pd install), which starts the session unit",
                          [Command([sys.executable, "-m", "macf.cli", "pd", "install"], env=pd_env,
                                   timeout=PD_INSTALL_TIMEOUT_S)],
                          undo=[Command([sys.executable, "-m", "macf.cli", "pd", "uninstall"], env=pd_env,
                                        note="the daemon wasn't installed before the move",
                                        timeout=PD_INSTALL_TIMEOUT_S), end_unit]))
    steps.append(Step("Watch the session unit come up: starting, then running",
                      [Command(["macf_tools", "pd", "status"]), Command(["macf_tools", "harness", "status"])]))
    ready = all(c.ok for c in checks)
    session_unit = None
    if next(c for c in checks if c.name == "staged declaration").ok:   # it validated, so it reads cleanly
        declaration = Declaration.model_validate_json(staged.read_text())
        session_unit = next(u.name for u in declaration.units if u.kind == "session")
    return Plan(agent, card, ready, checks, steps, session_unit=session_unit, init=init.name)


def _daemon_installed(card: str, home: Path) -> bool:
    """Whether the service manager has a unit or LaunchAgent for this agent's daemon, as
    rendered or not: an existing one is the operator's to update with pd install, never
    replaced by the move."""
    from macf.pd import adapter
    if sys.platform.startswith("linux"):
        from macf.platform import systemd
        path, _ = systemd.render_pd_user_unit(card, adapter._program(home), str(Path.home()))
    elif sys.platform == "darwin":
        from macf.platform import launchd
        path, _ = launchd.render_pd_launch_agent(card, adapter._program(home), str(Path.home()),
                                                 adapter.LaunchdAdapter._log_dir(home))
    else:
        return False
    return Path(path).exists()


def _session_grace(staged: Path) -> float:
    """How long a hand-started client gets to exit: the staged session unit's stop grace, the
    time the daemon itself gives a session, else 30 s."""
    try:
        declaration = Declaration.model_validate_json(staged.read_text())
        session = next(u for u in declaration.units if u.kind == "session")
        return float(session.stop_grace_s)
    except (OSError, ValidationError, StopIteration):
        return HAND_STARTED_GRACE_S


#: A hand-started client's time to exit when no session unit's stop grace is declared.
HAND_STARTED_GRACE_S = 30.0
#: How long pd install or uninstall may take as a step: a grant probe at install may wait
#: up to its own 120 s for a person to answer a dialog.
PD_INSTALL_TIMEOUT_S = 300.0


def end_client(pid: int, start: str, grace_s: float, alive=None, argv_of=None, signal_pid=None,
               sleep=None, clock=None, same=None) -> bool:
    """End one hand-started client: SIGTERM to *pid* alone, never a group and never SIGKILL,
    then wait up to *grace_s* for it to exit. Returns whether it is gone. A pid that is no
    longer a Claude Code client, or no longer the process started at *start* (the plan's
    ``proc_start``, checked as the core checks an adopted unit), has already ended, and its
    number is not signalled."""
    import os
    import signal as sig
    import time
    from macf.agent_stack import _is_claude
    if pid <= 1:
        raise ValueError(f"refusing to signal pid {pid}")
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    argv_of = argv_of or _process_argv

    def _alive(p: int) -> bool:
        try:
            os.kill(p, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    alive = alive or _alive
    signal_pid = signal_pid or (lambda p: os.kill(p, sig.SIGTERM))
    if same is None:
        from macf.notify.session import verify_incarnation as same
    if not alive(pid) or not same(pid, start) or not _is_claude(argv_of(pid)):
        return True
    try:
        signal_pid(pid)
    except ProcessLookupError:
        return True
    deadline = clock() + grace_s
    while alive(pid):
        if clock() >= deadline:
            return False
        sleep(0.2)
    return True


class ProbeUnavailable(RuntimeError):
    """A program a check needs can't be run here, so the plan can't be built. Under launchd a
    job starts with PATH=/usr/bin:/bin:/usr/sbin:/sbin, where Homebrew's tmux isn't."""


def host_probes(home: Path, card: str, platform: Optional[str] = None) -> Probes:
    """The real host: systemctl or launchctl, tmux and the agent's daemon."""
    import os
    from macf.pd.client import status
    from macf.pd.session_unit import client_environment

    def run(*argv, env=None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(list(argv), capture_output=True, text=True, env=env)
        except FileNotFoundError as e:
            path = (env or os.environ).get("PATH", "")
            raise ProbeUnavailable(f"{argv[0]} isn't on PATH ({path}), so the plan can't be checked") from e

    systemd = shutil.which("systemctl") is not None
    launchd = (platform or sys.platform) == "darwin" and shutil.which("launchctl") is not None
    if launchd and not systemd:
        from macf.platform import launchd as ld
        uid = os.getuid()

        def job_active(label: str) -> str:
            out = run("launchctl", "print", f"gui/{uid}/{label}")
            return "active" if ld.parse_print(out.stdout + out.stderr).running else "inactive"

        def running_jobs() -> List[str]:
            # launchctl list: "PID<tab>Status<tab>Label", PID "-" for a job loaded but not running.
            out = run("launchctl", "list").stdout
            return [f[2] for f in (ln.split("\t") for ln in out.splitlines()[1:])
                    if len(f) == 3 and f[0].strip().isdigit()]

        def harness_label(agent: str) -> Optional[str]:
            # As agent init finds it (agent_stack._launchd_harness_live): a plist whose name
            # names the harness and this agent.
            agents = Path.home() / "Library" / "LaunchAgents"
            try:
                found = sorted(p.name[:-len(".plist")] for p in agents.glob("*.plist")
                               if "harness" in p.name and agent in p.name)
            except OSError:
                return None  # noqa: MACEFF003 - no readable LaunchAgents: no harness job to stop
            return found[0] if found else None
        unit_active, active_units = job_active, running_jobs
    else:
        harness_label = lambda agent: None  # noqa: E731

        def unit_active(unit: str) -> str:
            return run("systemctl", "--user", "is-active", unit).stdout.strip()

        def active_units() -> List[str]:
            out = run("systemctl", "--user", "list-units", "--type=service", "--state=active",
                      "--no-legend", "--plain").stdout
            return [line.split()[0] for line in out.splitlines() if line.strip()]

    def unit_session(agent: str) -> bool:
        env = client_environment(agent)
        return env is not None and run("tmux", "has-session", "-t", f"={agent}", env=env).returncode == 0

    def daemon_answers() -> Optional[str]:
        report = status(home, card)
        return None if report.source == "daemon" else f"doesn't answer ({report.source}): {report.why}"

    def hand_started(agent: str) -> List[Tuple[int, str, str]]:
        from macf import agent_stack
        from macf.notify.session import proc_start
        import argparse
        ctx = agent_stack.Context(home=Path(home), login_home=Path.home(), in_container=False,
                                  args=argparse.Namespace(project_dir=None), card=card)
        where = str(agent_stack.project_dir(ctx).resolve())
        found = [(pid, where, proc_start(pid)) for pid in agent_stack.clients_here(ctx)]
        return [(pid, w, start) for pid, w, start in found if start]   # one that ended as we looked is gone

    def daemon_installed() -> bool:
        return _daemon_installed(card, home)

    return Probes(
        systemd=systemd,
        unit_active=unit_active,
        active_units=active_units,
        default_session=lambda agent: run("tmux", "-S", str(default_socket()), "has-session",
                                          "-t", f"={agent}").returncode == 0,
        unit_session=unit_session,
        daemon_answers=daemon_answers,
        launchd=launchd,
        harness_label=harness_label,
        hand_started=hand_started,
        daemon_installed=daemon_installed,
    )


# ============================================================================
# Running the plan: armed outside the session, rolled back on any failure
# ============================================================================

#: How long the session unit has to read running after the daemon restarts.
COME_UP_S = 300.0
#: The transient unit ``--run`` starts, one per agent, so two moves can't overlap.
RUN_UNIT_PREFIX = "maceff-cutover-"

Runner = Callable[[Command], int]
Log = Callable[[str], None]


def run_command(command: Command) -> int:
    import os
    env = {**os.environ, **command.env} if command.env else None
    try:
        return subprocess.run(command.argv, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=command.timeout or 120).returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"⚠️ MACF: cutover: {command.argv[0]} did not run: {e}", file=sys.stderr)
        return 127


def execute(plan: Plan, run: Runner, came_up: Callable[[], bool], log: Log) -> bool:
    """Carry out *plan*'s steps in order; on the first failure, or if the session unit never
    reads running, carry out its rollback. Returns whether the move took. Only a ready plan
    is carried out: a check that fails here changes nothing."""
    if not plan.ready:
        log("not ready, so nothing was changed: " +
            "; ".join(f"{c.name}: {c.detail}" for c in plan.checks if not c.ok))
        return False
    reached: List[Step] = []
    for i, step in enumerate(plan.steps, 1):
        if step.what.startswith("Watch"):
            log(f"step {i}: waiting for the session unit to read running")
            if came_up():
                log("the session unit is running: the move took")
                return True
            log("the session unit didn't read running in time")
            break
        log(f"step {i}: {step.what}")
        reached.append(step)          # begun, so undone on failure, even part-way through
        failed = next((c for c in step.commands if _ran(c, run, log) != 0 and not c.may_fail), None)
        if failed is not None:
            log(f"step {i} failed at: {failed}")
            break
    log(f"rolling back the {len(reached)} step(s) reached, last first")
    for step in reversed(reached):
        for command in step.undo:
            _ran(command, run, log)   # every undo command is tried, whatever came before
    log("rolled back what the move had done; check macf_tools harness status")
    return False


def _ran(command: Command, run: Runner, log: Log) -> int:
    code = run(command)
    log(f"  {'ok' if code == 0 else f'exit {code}'}: {command}")
    return code


def came_up_by_status(home: Path, card: str, unit: str, timeout_s: float = COME_UP_S,
                      interval_s: float = 5.0, sleep=None, clock=None) -> Callable[[], bool]:
    """Whether the daemon reports the session *unit* running within *timeout_s*."""
    import time
    from macf.pd.client import status
    sleep, clock = sleep or time.sleep, clock or time.monotonic

    def poll() -> bool:
        deadline = clock() + timeout_s
        while clock() < deadline:
            try:
                report = status(home, card)
            except Exception as e:  # noqa: BLE001 - GUARD: a daemon mid-restart may refuse; ask again
                print(f"⚠️ MACF: cutover: the daemon couldn't be asked yet: {e}", file=sys.stderr)
            else:
                if report.source == "daemon" and any(
                        u.get("unit") == unit and u.get("state") == "running" for u in report.units):
                    return True
            sleep(interval_s)
        return False
    return poll


def arm_argv(agent: str, home: Path, staged: Path, log_path: Path, python: str,
             environ: Optional[Dict[str, str]] = None) -> List[str]:
    """The transient unit that carries the plan out, outside the session it stops: the
    session's own process tree ends at step 2, so nothing of the move may live in it.
    A ``PYTHONPATH`` the caller runs under is passed on, so the unit imports the same macf
    that printed the plan rather than whatever its manager's environment finds."""
    import os
    env = os.environ if environ is None else environ
    setenv = [f"--setenv=PYTHONPATH={env['PYTHONPATH']}"] if env.get("PYTHONPATH") else []
    return ["systemd-run", "--user", "--unit", f"{RUN_UNIT_PREFIX}{agent}", "--collect",
            "--property", "Type=exec", *setenv, "--",
            python, "-m", "macf.cli", "harness", "cutover", "--agent", agent, "--home", str(home),
            "--staged", str(staged), "--execute", "--log", str(log_path)]


def job_paths(home: Path, card: str, stamp: str) -> "tuple[Path, Path]":
    """Where the launchd job's plist and log go: beside the declaration. Not in
    ~/Library/LaunchAgents, so a job a reboot interrupted is never started again at login."""
    from macf.platform.launchd import cutover_label
    here = declaration_path(home).parent
    return here / f"{cutover_label(card)}.plist", here / f"cutover-{stamp}.log"


def job_environment(home: Path, environ: Dict[str, str]) -> Dict[str, str]:
    """The environment the one-shot launchd job runs the move in: the one the plan was checked
    in. launchd starts a job with only ``PATH=/usr/bin:/bin:/usr/sbin:/sbin`` and ``HOME``, so
    without this the job can't find Homebrew's tmux, or ``macf_tools``, and the plan it builds
    isn't the one the operator was shown. A ``PYTHONPATH`` is passed on, so the job imports the
    same macf that printed the plan."""
    env = {"PATH": environ.get("PATH") or "/usr/bin:/bin:/usr/sbin:/sbin",
           "HOME": environ.get("HOME") or str(Path.home()),
           "MACEFF_AGENT_HOME_DIR": str(home)}
    if environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = environ["PYTHONPATH"]
    return env


def arm_launchd(agent: str, card: str, home: Path, staged: Path, python: str, uid: int,
                stamp: str, environ: Optional[Dict[str, str]] = None, run=None) -> "tuple[Path, Path]":
    """The launchd counterpart of ``arm_argv``: write a one-shot LaunchAgent that runs the
    move and bootstrap it into ``gui/<uid>``, where launchd starts it at once, outside the
    session it stops. Returns (plist, log). Refuses while a job of this agent's move is
    loaded, as ``systemd-run`` refuses a unit name in use, so two moves can't overlap; a
    bootstrap that fails leaves no plist behind. Raises ``RuntimeError`` saying why."""
    import os
    from macf.platform import launchd
    env = os.environ if environ is None else environ
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True))
    label = launchd.cutover_label(card)
    plist, log_path = job_paths(home, card, stamp)
    loaded = run(launchd.launchctl_argv("print", label, uid))
    if launchd.parse_print((loaded.stdout or "") + (loaded.stderr or "")).loaded and loaded.returncode == 0:
        raise RuntimeError(f"{label} is already loaded: a move is under way, or one ended without "
                           f"removing its job; see launchctl print gui/{uid}/{label}")
    argv = [python, "-m", "macf.cli", "harness", "cutover", "--agent", agent, "--home", str(home),
            "--staged", str(staged), "--execute", "--job-plist", str(plist)]
    content = launchd.render_cutover_job(card, argv, str(log_path), job_environment(home, env))
    steps = [launchd.Step("write", path=str(plist), content=content),
             launchd.Step("launchctl", argv=launchd.launchctl_argv("bootstrap", label, uid, str(plist)))]
    try:
        launchd.apply_plan(steps, run=run)
    except FileExistsError as e:
        raise RuntimeError(f"{plist} is left from an earlier move: {e}") from e
    except RuntimeError:
        plist.unlink(missing_ok=True)       # nothing started, so nothing of it is left
        raise
    return plist, log_path


def remove_own_job(plist: Path, label: str, uid: int, log: Log, spawn=None) -> None:
    """The launchd job's last act: delete its plist, then boot itself out. The boot-out ends
    this process, so it runs detached, in a session of its own that outlives the job's
    process group, and is the very last thing done."""
    from macf.platform import launchd
    spawn = spawn or (lambda argv: subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                     start_new_session=True))
    try:
        plist.unlink(missing_ok=True)
        log(f"removed its own job: {plist}")
    except OSError as e:
        log(f"couldn't remove its own plist {plist}: {e}; remove it by hand")
    argv = launchd.launchctl_argv("bootout", label, uid)
    log(f"booting out its own job: {shlex.join(argv)}")
    try:
        spawn(argv)
    except OSError as e:
        log(f"couldn't boot out its own job: {e}; run {shlex.join(argv)}")


def execute_as_launchd_job(plan: Plan, run: Runner, came_up: Callable[[], bool], log: Log,
                           plist: Path, label: str, uid: int, spawn=None) -> bool:
    """``execute``, as the one-shot launchd job runs it: whatever the move's outcome, a step
    that raised included, the job removes its own plist and boots itself out after it."""
    try:
        return execute(plan, run, came_up, log)
    finally:
        remove_own_job(plist, label, uid, log, spawn)


def inside_session(pid: Optional[int] = None, ancestors=None, argv_of=None) -> Optional[int]:
    """The pid of a Claude Code client this process runs under, or None.

    ``--execute`` carries out steps that end the legacy session; run from inside that
    session, it would be killed part-way, and nothing would be left to roll the move back.
    ``--run`` hands it to the init system (a transient systemd unit, a launchd job), whose
    processes descend from the service manager, never from a client."""
    import os
    from macf.agent_stack import _is_claude
    if ancestors is None:
        from macf.supervisor import ancestor_pids as ancestors
    argv_of = argv_of or _process_argv
    for p in sorted(ancestors(os.getpid() if pid is None else pid)):
        if _is_claude(argv_of(p)):
            return p
    return None


def _process_argv(pid: int) -> List[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return [a.decode(errors="replace") for a in raw.split(b"\0") if a]
    except OSError:
        pass  # noqa: MACEFF003 - no procfs (macOS): ask ps
    try:
        out = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return out.split()


def format_plan(plan: Plan) -> str:
    lines = [f"Moving {plan.card}'s session onto its primal daemon: the plan. Nothing has been changed.", ""]
    for c in plan.checks:
        lines.append(f"  {'ok  ' if c.ok else 'NOT '} {c.name}: {c.detail}")
    if not plan.steps:
        return "\n".join(lines)
    lines.append("")
    lines.append("Ready: every check holds." if plan.ready else
                 "NOT READY: fix what the checks above name before running any step.")
    for i, step in enumerate(plan.steps, 1):
        lines += ["", f"{i}. {step.what}"] + [f"     {c}" for c in step.commands]
        if step.undo:
            lines += [f"   undo step {i}:"] + [f"     {c}" for c in step.undo]
    lines += ["", "If a step fails, undo it and every step before it, last first. Never undo a "
              "step that wasn't reached: its undo may restore what it never saved."]
    lines += ["", "Run the steps from a terminal outside the session they stop (step "
              f"{next(i for i, s in enumerate(plan.steps, 1) if s.what.startswith('Install'))} "
              "restarts the daemon; an earlier step may end the session you are typing in)."]
    # What only a person can do (host-side maintainer, on review).
    lines += ["", "When the new session starts:",
              "  - if it asks how to resume, answer \"continue\", never \"summarize\";",
              "  - scheduled jobs the old session made for itself lived in its process: "
              "recreate them once the move holds."]
    return "\n".join(lines)


def end_stale_monitors(home: Path, find=None, alive=None, signal_pid=None,
                       wait_s: float = 5.0, sleep=None) -> List[int]:
    """End this agent's transcript monitors whose session has ended: those reading a
    transcript under *home* whose owning process is gone. Returns the pids still alive
    afterwards (empty on success). A monitor whose owner lives is someone's, and left."""
    import os
    import signal as sig
    import time
    from macf.transcript_monitor.daemon import find_monitors
    find, sleep = find or find_monitors, sleep or time.sleep

    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    alive = alive or _alive
    signal_pid = signal_pid or (lambda pid: os.kill(pid, sig.SIGTERM))
    root = Path(home).resolve()
    stale = [m.pid for m in (find() or [])
             if m.owner and not alive(m.owner) and Path(m.transcript).resolve().is_relative_to(root)]
    for pid in stale:
        try:
            signal_pid(pid)
        except ProcessLookupError:
            pass  # noqa: MACEFF003 - ended between the listing and the signal, as wanted
    deadline = time.monotonic() + wait_s
    left = [p for p in stale if alive(p)]
    while left and time.monotonic() < deadline:
        sleep(0.1)
        left = [p for p in left if alive(p)]
    return left


if __name__ == "__main__":
    # python -m macf.pd.cutover end-stale-monitors <agent home>: a step of the move.
    if len(sys.argv) == 5 and sys.argv[1] == "end-client":
        gone = end_client(int(sys.argv[2]), sys.argv[3], float(sys.argv[4]))
        if not gone:
            print(f"⚠️ MACF: cutover: the hand-started client {sys.argv[2]} didn't exit within "
                  f"{sys.argv[4]} s", file=sys.stderr)
        sys.exit(0 if gone else 1)
    if len(sys.argv) == 3 and sys.argv[1] == "end-stale-monitors":
        left = end_stale_monitors(Path(sys.argv[2]))
        if left:
            print(f"⚠️ MACF: cutover: transcript monitor(s) {left} didn't end", file=sys.stderr)
        sys.exit(1 if left else 0)
    print("usage: python -m macf.pd.cutover end-stale-monitors <agent home>\n"
          "       python -m macf.pd.cutover end-client <pid> <proc start> <grace seconds>", file=sys.stderr)
    sys.exit(2)
