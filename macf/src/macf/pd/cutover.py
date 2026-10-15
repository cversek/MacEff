"""Moving an agent's session from the legacy harness onto its primal daemon: the plan.

``macf_tools harness cutover`` reads the host and prints what a move would do for one
agent, step by step, with the rollback, and changes nothing. It is the runbook the host's
first move followed (persistent_layer 6.3), generated for the agent at hand from what is
actually installed, so no step names a unit that isn't there or misses one that is.

The plan is built from probes passed in, so every case can be tested without systemd,
tmux or a daemon: ``build_plan(..., probes=Probes(...))``. ``host_probes`` are the real ones.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import ValidationError

from macf.pd.interface import Declaration, declaration_path
from macf.pd.names import systemd_unit
from macf.pd.session_unit import PANE_GRACE_S, tmux_dir

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
class Step:
    what: str
    commands: List[str]


@dataclass(frozen=True)
class Plan:
    agent: str
    card: str
    ready: bool
    checks: List[Check]
    steps: List[Step] = field(default_factory=list)
    rollback: List[str] = field(default_factory=list)


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


def _staged_check(path: Path, card: str) -> Check:
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
    return Check("staged declaration", True, f"{path} validates, with session unit {session.name}")


def build_plan(home: Path, card: str, agent: str, probes: Probes,
               staged: Optional[Path] = None, harness_unit: Optional[str] = None,
               base: Optional[Path] = None) -> Plan:
    """What moving *agent*'s session onto its daemon would do, and whether it can be done now.

    *agent* is the session identifier (``Name_uuid6``), *card* the calling card.
    """
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

    checks.append(_staged_check(staged, card))
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

    steps: List[Step] = []
    if clocks:
        steps.append(Step("Stop the clocks that would type into the pane beside the daemon's",
                          [f"systemctl --user disable --now {u}" for u in clocks]))
    if legacy or held:
        stop = []
        if legacy:
            stop += [f"systemctl --user stop {harness_unit}", f"systemctl --user disable {harness_unit}"]
        stop.append(f"tmux kill-session -t ={agent}      # the pane a stop left behind, if any")
        steps.append(Step("Stop the legacy session (a session running here ends at this step)", stop))
    steps.append(Step("Install the declaration with the session unit, keeping the old one",
                      [f"cp {live} {saved}", f"cp {staged} {live}",
                       f"systemctl --user restart {daemon_unit}"]))
    steps.append(Step("Watch the session unit come up: starting, then running",
                      ["macf_tools pd status", "macf_tools harness status"]))

    rollback = [f"cp {saved} {live}", f"systemctl --user restart {daemon_unit}",
                f"TMUX_TMPDIR={tmux_dir(agent, base)} tmux kill-server   # the unit's session, "
                "no longer declared, before the legacy one starts"]
    if legacy:
        rollback.append(f"systemctl --user enable --now {harness_unit}")
    rollback += [f"systemctl --user enable --now {u}" for u in clocks]
    ready = all(c.ok for c in checks)
    return Plan(agent, card, ready, checks, steps, rollback)


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
        default_session=lambda agent: run("tmux", "has-session", "-t", f"={agent}").returncode == 0,
        unit_session=unit_session,
        daemon_answers=daemon_answers,
    )


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
    lines += ["", "Rollback, at any step:"] + [f"     {c}" for c in plan.rollback]
    lines += ["", "Run the steps from a terminal outside the session they stop (step "
              f"{next(i for i, s in enumerate(plan.steps, 1) if s.what.startswith('Install'))} "
              "restarts the daemon; an earlier step may end the session you are typing in)."]
    return "\n".join(lines)
