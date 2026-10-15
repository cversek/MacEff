"""The plan for moving a session onto its primal daemon (persistent_layer 6.3): read from the
host, never acting on it. Every case is played on stand-in probes."""
import json
from dataclasses import replace
from pathlib import Path

from macf.pd.cutover import Probes, build_plan, format_plan, staged_path
from macf.pd.interface import Declaration, Unit, declaration_path

CARD, AGENT = "Resident@1a2b3c", "Resident_1a2b3c"


def _probes(**over) -> Probes:
    base = dict(systemd=True,
                unit_active=lambda unit: "active" if unit == f"cc-harness-{AGENT}.service" else "inactive",
                active_units=lambda: [f"cc-harness-{AGENT}.service", "aero-mail-clock.service",
                                      "macf-proxy.service"],
                default_session=lambda agent: True,
                unit_session=lambda agent: False,
                daemon_answers=lambda: None)
    base.update(over)
    return Probes(**base)


def _stage(home: Path, *, grace=30.0, agent=CARD, session=True):
    units = [Unit(name="amail-broker", command=["broker"], account="resident", restart="always",
                  liveness_interval_s=30, memory_limit_mb=64)]
    if session:
        units.append(Unit(name="session", kind="session", command=["macf_tools", "harness", "unit"],
                          account="resident", restart="always", liveness_interval_s=120,
                          memory_limit_mb=16384, stop_grace_s=grace))
    path = staged_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Declaration(version=1, agent=agent, units=units).model_dump_json())
    return path


def test_a_ready_host_gets_every_step_in_the_runbooks_order(tmp_path):
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(), base=tmp_path / "run")
    assert plan.ready and all(c.ok for c in plan.checks)
    whats = [s.what.split(" (")[0] for s in plan.steps]
    assert whats == ["Stop the clocks that would type into the pane beside the daemon's",
                     "Stop the legacy session",
                     "Install the declaration with the session unit, keeping the old one",
                     "Watch the session unit come up: starting, then running"]
    flat = [str(c) for s in plan.steps for c in s.commands]
    assert "systemctl --user disable --now aero-mail-clock.service" in flat
    assert f"systemctl --user stop cc-harness-{AGENT}.service" in flat
    assert f"systemctl --user restart maceff_pd-{AGENT}.service" in flat
    live = declaration_path(tmp_path)
    assert flat.index(f"cp {live} {live}.pre-cutover") < flat.index(f"cp {staged_path(tmp_path)} {live}")
    assert not any("macf-proxy" in c for c in flat), "the plan changes one thing at a time"
    # the rollback restores the declaration first, ends the unit's server before the legacy start
    rollback = [str(c) for c in plan.rollback]
    assert rollback[0] == f"cp {live}.pre-cutover {live}"
    kill = next(i for i, c in enumerate(rollback) if "kill-server" in c)
    assert str(tmp_path / "run" / f"{AGENT}.tmux") in rollback[kill]
    assert kill < rollback.index(f"systemctl --user enable --now cc-harness-{AGENT}.service")


def test_an_already_moved_session_has_nothing_to_do(tmp_path):
    plan = build_plan(tmp_path, CARD, AGENT, _probes(unit_session=lambda agent: True))
    assert not plan.ready and not plan.steps and "nothing to move" in plan.checks[0].detail


def test_each_unmet_check_says_not_ready(tmp_path):
    cases = {
        "no staged declaration": (lambda: None, _probes(), "none at"),
        "another agent's": (lambda: _stage(tmp_path, agent="Other@000000"), _probes(), "declares Other"),
        "no session unit": (lambda: _stage(tmp_path, session=False), _probes(), "no session unit"),
        "grace too short": (lambda: _stage(tmp_path, grace=5.0), _probes(), "must exceed"),
        "daemon silent": (lambda: _stage(tmp_path), _probes(daemon_answers=lambda: "no record"), "no record"),
    }
    for name, (stage, probes, words) in cases.items():
        staged_path(tmp_path).unlink(missing_ok=True)
        stage()
        plan = build_plan(tmp_path, CARD, AGENT, probes)
        assert not plan.ready, name
        assert any(not c.ok and words in c.detail for c in plan.checks), (name, plan.checks)
        assert "NOT READY" in format_plan(plan), name


def test_no_systemd_is_said_not_guessed(tmp_path):
    plan = build_plan(tmp_path, CARD, AGENT, _probes(systemd=False))
    assert not plan.ready and not plan.steps and "launchd" in plan.checks[0].detail


def test_only_what_is_installed_is_named(tmp_path):
    """No legacy harness and no duplicate clock: no step to stop them, and none in the rollback."""
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(unit_active=lambda unit: "inactive",
                                                     active_units=lambda: [],
                                                     default_session=lambda agent: False))
    assert plan.ready
    assert [s.what.split(",")[0] for s in plan.steps] == [
        "Install the declaration with the session unit", "Watch the session unit come up: starting"]
    assert not any("enable --now" in str(c) for c in plan.rollback)


def test_the_plan_serializes_for_json(tmp_path):
    import dataclasses
    _stage(tmp_path)
    data = json.loads(json.dumps(dataclasses.asdict(build_plan(tmp_path, CARD, AGENT, _probes()))))
    assert data["ready"] is True and data["steps"][0]["commands"]
