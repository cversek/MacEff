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
from typing import Callable, Dict, List, Optional

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


@dataclass(frozen=True)
class Probes:
    """The host, as the plan reads it.

    - ``systemd``: whether user units can be managed here at all.
    - ``unit_active``: ``systemctl --user is-active`` of one unit.
    - ``active_units``: the names of the user's active service units.
    - ``default_session``: whether the agent's session is on the default tmux server.
    - ``unit_session``: whether it is already on the session unit's own server.
    - ``daemon_answers``: None when the agent's daemon answers, else why not.
    """
    systemd: bool
    unit_active: Callable[[str], str]
    active_units: Callable[[], List[str]]
    default_session: Callable[[str], bool]
    unit_session: Callable[[str], bool]
    daemon_answers: Callable[[], Optional[str]]


def staged_path(home: Path) -> Path:
    path = declaration_path(home)
    return path.with_name(path.name + STAGED_SUFFIX)


def _staged_check(path: Path, card: str, runtime: Optional[str]) -> Check:
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
    if not declared or (runtime and declared != runtime):
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


def build_plan(home: Path, card: str, agent: str, probes: Probes,
               staged: Optional[Path] = None, harness_unit: Optional[str] = None,
               runtime: Optional[str] = None) -> Plan:
    """What moving *agent*'s session onto its daemon would do, and whether it can be done now.

    *agent* is the session identifier (``Name_uuid6``), *card* the calling card, *runtime*
    the caller's ``XDG_RUNTIME_DIR`` (the process environment's by default), which the
    session unit must declare so its tmux server is where every client looks.
    """
    import os
    from macf.pd.names import PD_IDENTIFIER
    runtime = runtime if runtime is not None else os.environ.get("XDG_RUNTIME_DIR")
    # Where the unit's tmux server will be, from the runtime directory it must declare.
    unit_base = Path(runtime) / PD_IDENTIFIER if runtime else None
    staged = staged or staged_path(home)
    harness_unit = harness_unit or f"cc-harness-{agent}.service"
    daemon_unit = systemd_unit(card)
    live = declaration_path(home)
    saved = live.with_name(live.name + SAVED_SUFFIX)
    checks: List[Check] = []

    if probes.unit_session(agent):
        checks.append(Check("session", True,
                            "already runs as the primal daemon's session unit: nothing to move"))
        return Plan(agent, card, False, checks)
    if not probes.systemd:
        checks.append(Check("init system", False,
                            "no systemctl here: this plan covers systemd hosts; a macOS host's move "
                            "goes through launchd (persistent_layer 6.3)"))
        return Plan(agent, card, False, checks)

    checks.append(_staged_check(staged, card, runtime))
    why = probes.daemon_answers()
    checks.append(Check("daemon", why is None, "answers on its socket" if why is None else why))
    legacy = probes.unit_active(harness_unit) == "active"
    checks.append(Check("legacy harness", True, f"{harness_unit} is active" if legacy else
                        f"{harness_unit} isn't active, so there is no legacy session to stop"))
    held = probes.default_session(agent)
    checks.append(Check("legacy session", True, f"={agent} is on the default tmux server" if held
                        else f"no ={agent} on the default tmux server"))
    clocks = sorted(u for u in probes.active_units() if "mail-clock" in u and u != daemon_unit)
    checks.append(Check("duplicate clocks", True, ", ".join(clocks) + " running beside the daemon's"
                        if clocks else "none running beside the daemon's"))
    # A saved declaration from an earlier attempt is not this move's to restore or overwrite:
    # it may hold what the live one has since lost, or the reverse (head maintainer, on review).
    checks.append(Check("saved declaration", not saved.exists(),
                        f"{saved} is left from an earlier attempt: compare it with {live}, keep what "
                        "you need, and remove it" if saved.exists() else f"no {saved.name} from an earlier attempt"))

    def systemctl(*args: str) -> Command:
        return Command(["systemctl", "--user", *args])

    steps: List[Step] = []
    if clocks:
        steps.append(Step("Stop the clocks that would type into the pane beside the daemon's",
                          [systemctl("disable", "--now", u) for u in clocks],
                          undo=[systemctl("enable", "--now", u) for u in clocks]))
    if legacy or held:
        stop = [systemctl("stop", harness_unit), systemctl("disable", harness_unit)] if legacy else []
        stop.append(Command(["tmux", "-S", str(default_socket()), "kill-session", "-t", f"={agent}"],
                            note="the pane a stop left behind, if any", may_fail=True))
        # A monitor the old session's hooks started is not a unit, so stopping the session
        # doesn't always end it; left running, it holds the transcript and the new session's
        # monitor stands down, so the unit never beats (host-side maintainer, on review).
        stop.append(Command([sys.executable, "-m", "macf.pd.cutover", "end-stale-monitors", str(home)],
                            note="transcript monitors of this agent whose session has ended"))
        steps.append(Step("Stop the legacy session (a session running here ends at this step)", stop,
                          undo=[systemctl("enable", "--now", harness_unit)] if legacy else []))
    steps.append(Step("Install the declaration with the session unit, keeping the old one",
                      [Command(["cp", str(live), str(saved)]), Command(["cp", str(staged), str(live)]),
                       systemctl("restart", daemon_unit)],
                      undo=[Command(["cp", str(saved), str(live)]), systemctl("restart", daemon_unit),
                            Command(["tmux", "-S", str(tmux_socket(agent, unit_base)), "kill-server"],
                                    note="the unit's session, no longer declared, before the legacy one starts",
                                    may_fail=True),
                            Command(["rm", str(saved)], note="restored, so no later attempt finds it")]))
    steps.append(Step("Watch the session unit come up: starting, then running",
                      [Command(["macf_tools", "pd", "status"]), Command(["macf_tools", "harness", "status"])]))
    ready = all(c.ok for c in checks)
    session_unit = None
    if checks[0].ok:      # the staged declaration validated, so it reads cleanly here
        declaration = Declaration.model_validate_json(staged.read_text())
        session_unit = next(u.name for u in declaration.units if u.kind == "session")
    return Plan(agent, card, ready, checks, steps, session_unit=session_unit)


def host_probes(home: Path, card: str) -> Probes:
    """The real host: systemctl, tmux and the agent's daemon."""
    from macf.pd.client import status
    from macf.pd.session_unit import client_environment

    def run(*argv, env=None) -> subprocess.CompletedProcess:
        return subprocess.run(list(argv), capture_output=True, text=True, env=env)

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

    return Probes(
        systemd=shutil.which("systemctl") is not None,
        unit_active=lambda unit: run("systemctl", "--user", "is-active", unit).stdout.strip(),
        active_units=active_units,
        default_session=lambda agent: run("tmux", "-S", str(default_socket()), "has-session",
                                          "-t", f"={agent}").returncode == 0,
        unit_session=unit_session,
        daemon_answers=daemon_answers,
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
                              capture_output=True, timeout=120).returncode
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
    if len(sys.argv) == 3 and sys.argv[1] == "end-stale-monitors":
        left = end_stale_monitors(Path(sys.argv[2]))
        if left:
            print(f"⚠️ MACF: cutover: transcript monitor(s) {left} didn't end", file=sys.stderr)
        sys.exit(1 if left else 0)
    print("usage: python -m macf.pd.cutover end-stale-monitors <agent home>", file=sys.stderr)
    sys.exit(2)
