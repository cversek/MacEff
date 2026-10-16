"""The plan for moving a session onto its primal daemon (persistent_layer 6.3): read from the
host, never acting on it. Every case is played on stand-in probes."""
import json
from dataclasses import replace
from pathlib import Path

from macf.pd.cutover import Probes, build_plan, format_plan, staged_path
from macf.pd.interface import Declaration, Unit, declaration_path

CARD, AGENT = "Resident@1a2b3c", "Resident_1a2b3c"
RUNTIME = "/run/user/4242"


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


def _stage(home: Path, *, grace=30.0, agent=CARD, session=True, runtime=RUNTIME, liveness=True):
    units = [Unit(name="amail-broker", command=["broker"], account="resident", restart="always",
                  liveness_interval_s=30, memory_limit_mb=64)]
    if session:
        env = {"XDG_RUNTIME_DIR": runtime} if runtime else {}
        if liveness:
            env.update(MACF_PD_UNIT="session", MACF_PD_LIVENESS_S="120")
        units.append(Unit(name="session", kind="session", command=["macf_tools", "harness", "unit"],
                          account="resident", restart="always", liveness_interval_s=120,
                          memory_limit_mb=16384, stop_grace_s=grace, environment=env))
    path = staged_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Declaration(version=1, agent=agent, units=units).model_dump_json())
    return path


def test_a_ready_host_gets_every_step_in_the_runbooks_order(tmp_path):
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(), runtime=RUNTIME)
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
    assert f"-S {RUNTIME}/maceff_pd/{AGENT}.tmux/" in rollback[kill]
    assert kill < rollback.index(f"systemctl --user enable --now cc-harness-{AGENT}.service")
    # every tmux command names its server's socket: inside a tmux client TMUX outranks TMUX_TMPDIR
    assert all(" -S " in c for c in flat + rollback if c.startswith("tmux"))
    assert not any("TMUX_TMPDIR=" in c for c in flat + rollback)


def test_an_already_moved_session_has_nothing_to_do(tmp_path):
    plan = build_plan(tmp_path, CARD, AGENT, _probes(unit_session=lambda agent: True), runtime=RUNTIME)
    assert not plan.ready and not plan.steps and "nothing to move" in plan.checks[0].detail


def test_each_unmet_check_says_not_ready(tmp_path):
    cases = {
        "no staged declaration": (lambda: None, _probes(), "none at"),
        "another agent's": (lambda: _stage(tmp_path, agent="Other@000000"), _probes(), "declares Other"),
        "no session unit": (lambda: _stage(tmp_path, session=False), _probes(), "no session unit"),
        "grace too short": (lambda: _stage(tmp_path, grace=5.0), _probes(), "must exceed"),
        "no runtime dir": (lambda: _stage(tmp_path, runtime=None), _probes(), "must declare XDG_RUNTIME_DIR"),
        "another runtime dir": (lambda: _stage(tmp_path, runtime="/run/user/1"), _probes(),
                                "declares /run/user/1"),
        "daemon silent": (lambda: _stage(tmp_path), _probes(daemon_answers=lambda: "no record"), "no record"),
    }
    for name, (stage, probes, words) in cases.items():
        staged_path(tmp_path).unlink(missing_ok=True)
        stage()
        plan = build_plan(tmp_path, CARD, AGENT, probes, runtime=RUNTIME)
        assert not plan.ready, name
        assert any(not c.ok and words in c.detail for c in plan.checks), (name, plan.checks)
        assert "NOT READY" in format_plan(plan), name


def test_a_session_unit_needs_no_liveness_variables_of_its_own(tmp_path):
    """The daemon sets them from the unit (#686), so the plan no longer asks for them."""
    _stage(tmp_path, liveness=False)
    assert build_plan(tmp_path, CARD, AGENT, _probes(), runtime=RUNTIME).ready


def test_no_systemd_is_said_not_guessed(tmp_path):
    plan = build_plan(tmp_path, CARD, AGENT, _probes(systemd=False), runtime=RUNTIME)
    assert not plan.ready and not plan.steps and "launchd" in plan.checks[0].detail


def test_only_what_is_installed_is_named(tmp_path):
    """No legacy harness and no duplicate clock: no step to stop them, and none in the rollback."""
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(unit_active=lambda unit: "inactive",
                                                     active_units=lambda: [],
                                                     default_session=lambda agent: False),
                      runtime=RUNTIME)
    assert plan.ready
    assert [s.what.split(",")[0] for s in plan.steps] == [
        "Install the declaration with the session unit", "Watch the session unit come up: starting"]
    assert not any("enable --now" in str(c) for c in plan.rollback)


def _ready(tmp_path):
    _stage(tmp_path)
    return build_plan(tmp_path, CARD, AGENT, _probes(), runtime=RUNTIME)


def _runner(fail_at=None):
    ran = []

    def run(command):
        ran.append(str(command))
        return 1 if fail_at is not None and len(ran) - 1 == fail_at else 0
    return run, ran


def test_a_move_that_comes_up_runs_every_step_and_no_rollback(tmp_path):
    from macf.pd.cutover import execute
    plan = _ready(tmp_path)
    run, ran = _runner()
    lines = []
    assert execute(plan, run, lambda: True, lines.append) is True
    acting = [str(c) for s in plan.steps if not s.what.startswith("Watch") for c in s.commands]
    assert ran == acting and plan.session_unit == "session"
    assert "the move took" in lines[-1]


def test_a_failure_undoes_only_the_steps_reached_last_first(tmp_path):
    """A planted failure at each command of each step: nothing after it runs, and the undo
    of every step begun runs, last step first. No step that wasn't reached is undone.
    Ending a session already gone isn't a failure."""
    from macf.pd.cutover import execute
    plan = _ready(tmp_path)
    acting = [(s, c) for s in plan.steps if not s.what.startswith("Watch") for c in s.commands]
    for i, (step, command) in enumerate(acting):
        run, ran = _runner(fail_at=i)
        took = execute(plan, run, lambda: True, lambda line: None)
        if command.may_fail:
            assert took is True, str(command)
            continue
        assert took is False, str(command)
        reached = plan.steps[:plan.steps.index(step) + 1]
        undo = [str(c) for s in reversed(reached) for c in s.undo]
        assert ran == [str(c) for _, c in acting[:i + 1]] + undo, str(command)


def test_a_failure_before_the_install_never_touches_the_declaration(tmp_path):
    """The head maintainer's case: a saved declaration left by an earlier attempt, and a
    failure at the first step. The plan refuses to start while one is there, and even a
    move that failed at step 1 runs no command that copies a declaration."""
    from macf.pd.cutover import execute
    plan = _ready(tmp_path)
    run, ran = _runner(fail_at=0)
    assert execute(plan, run, lambda: True, lambda line: None) is False
    assert not any(c.startswith("cp ") or c.startswith("rm ") for c in ran)
    live = declaration_path(tmp_path)
    live.with_name(live.name + ".pre-cutover").write_text("{}")
    stale = build_plan(tmp_path, CARD, AGENT, _probes(), runtime=RUNTIME)
    assert not stale.ready
    assert any(not c.ok and "left from an earlier attempt" in c.detail for c in stale.checks)


def test_the_install_undo_removes_the_saved_declaration_it_restored(tmp_path):
    plan = _ready(tmp_path)
    install = next(s for s in plan.steps if s.what.startswith("Install"))
    undo = [str(c) for c in install.undo]
    live = declaration_path(tmp_path)
    assert undo[0] == f"cp {live}.pre-cutover {live}"
    assert undo[-1].startswith(f"rm {live}.pre-cutover")


def test_stale_monitors_are_ended_and_live_ones_left(tmp_path):
    """A monitor of this agent whose session ended is ended; one whose owner lives, or one of
    another agent's home, is left (host-side maintainer, on review)."""
    from types import SimpleNamespace
    from macf.pd.cutover import end_stale_monitors
    mine = tmp_path / ".claude" / "projects" / "t.jsonl"
    other = tmp_path.parent / "elsewhere.jsonl"
    monitors = [SimpleNamespace(pid=11, owner=101, transcript=mine),      # owner gone: stale
                SimpleNamespace(pid=12, owner=102, transcript=mine),      # owner alive: left
                SimpleNamespace(pid=13, owner=103, transcript=other),     # another home: left
                SimpleNamespace(pid=14, owner=0, transcript=mine)]        # no owner: left
    living = {102, 12, 13, 14, 11}
    signalled = []

    def kill(pid):
        signalled.append(pid)
        living.discard(pid)
    left = end_stale_monitors(tmp_path, find=lambda: monitors, alive=lambda p: p in living,
                              signal_pid=kill, wait_s=0.1, sleep=lambda s: None)
    assert signalled == [11] and left == []
    plan = _ready(tmp_path)
    stop = next(s for s in plan.steps if s.what.startswith("Stop the legacy"))
    assert any("end-stale-monitors" in str(c) and str(tmp_path) in str(c) for c in stop.commands)


def test_a_session_that_never_comes_up_rolls_back(tmp_path):
    from macf.pd.cutover import execute
    plan = _ready(tmp_path)
    run, ran = _runner()
    assert execute(plan, run, lambda: False, lambda line: None) is False
    assert ran[-len(plan.rollback):] == [str(c) for c in plan.rollback]


def test_an_unready_plan_changes_nothing(tmp_path):
    from macf.pd.cutover import execute
    plan = build_plan(tmp_path, CARD, AGENT, _probes(), runtime=RUNTIME)   # nothing staged
    run, ran = _runner()
    lines = []
    assert execute(plan, run, lambda: True, lines.append) is False
    assert ran == [] and "nothing was changed" in lines[0]


def test_the_move_is_armed_outside_the_session(tmp_path):
    from macf.pd.cutover import arm_argv
    argv = arm_argv(AGENT, tmp_path, tmp_path / "staged", tmp_path / "log", "/usr/bin/python3", environ={})
    assert argv[:3] == ["systemd-run", "--user", "--unit"] and argv[3] == f"maceff-cutover-{AGENT}"
    assert not any(a.startswith("--setenv") for a in argv)
    with_path = arm_argv(AGENT, tmp_path, tmp_path / "staged", tmp_path / "log", "/usr/bin/python3",
                         environ={"PYTHONPATH": "/src"})
    assert "--setenv=PYTHONPATH=/src" in with_path[:with_path.index("--")]
    assert argv[argv.index("--") + 1:argv.index("--") + 3] == ["/usr/bin/python3", "-m"]
    assert "--execute" in argv and argv[argv.index("--log") + 1] == str(tmp_path / "log")


def test_coming_up_is_read_from_the_daemon(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from macf.pd import client
    from macf.pd.cutover import came_up_by_status
    reports = iter([RuntimeError("restarting"),
                    SimpleNamespace(source="event_log", why="", units=[]),
                    SimpleNamespace(source="daemon", why="", units=[{"unit": "session", "state": "starting"}]),
                    SimpleNamespace(source="daemon", why="", units=[{"unit": "session", "state": "running"}])])

    def status(home, card):
        r = next(reports)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(client, "status", status)
    clock = [0.0]
    poll = came_up_by_status(tmp_path, CARD, "session", timeout_s=100, interval_s=1,
                             sleep=lambda s: clock.__setitem__(0, clock[0] + s), clock=lambda: clock[0])
    assert poll() is True and clock[0] == 3


def test_the_plan_serializes_for_json(tmp_path):
    import dataclasses
    _stage(tmp_path)
    data = json.loads(json.dumps(dataclasses.asdict(build_plan(tmp_path, CARD, AGENT, _probes(),
                                                               runtime=RUNTIME))))
    assert data["ready"] is True and data["steps"][0]["commands"]
