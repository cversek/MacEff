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


def _stage(home: Path, *, grace=30.0, agent=CARD, session=True, runtime=RUNTIME, liveness=True,
           live=True):
    """Stage a declaration for the move, and by default a live one without the session unit
    beside it, as an agent already on its daemon has. ``live=False`` is a seat agent init
    staged for the move: no declaration installed yet."""
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
    current = declaration_path(home)
    if live and not current.exists():
        current.write_text(Declaration(version=1, agent=CARD, units=units[:1]).model_dump_json())
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


# ============================================================================
# macOS: the same checks, steps and rollback, through launchd
# ============================================================================

UID = 501
HARNESS_LABEL = f"com.maceff.harness.{AGENT}"
MAC_CLOCK = "com.maceff.aero-mail-clock"


def _mac_probes(**over) -> Probes:
    base = dict(systemd=False, launchd=True,
                harness_label=lambda agent: HARNESS_LABEL,
                unit_active=lambda label: "active" if label == HARNESS_LABEL else "inactive",
                active_units=lambda: [HARNESS_LABEL, MAC_CLOCK, "maceff_pd.Resident_1a2b3c"])
    base.update(over)
    return _probes(**base)


def _mac_ready(tmp_path, monkeypatch, **over):
    """A Mac host: no XDG_RUNTIME_DIR in the environment, and a staged declaration that
    declares none either, so the unit and its clients agree on the /tmp fallback."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    _stage(tmp_path, runtime=None)
    return build_plan(tmp_path, CARD, AGENT, _mac_probes(**over), uid=UID,
                      launch_agents=tmp_path / "LaunchAgents")


def test_a_mac_plan_names_launchd_and_lists_every_step(tmp_path, monkeypatch):
    plan = _mac_ready(tmp_path, monkeypatch)
    assert plan.ready and plan.init == "launchd", plan.checks
    init = next(c for c in plan.checks if c.name == "init system")
    assert init.ok and "launchd" in init.detail and f"gui/{UID}" in init.detail
    whats = [s.what.split(" (")[0] for s in plan.steps]
    assert whats == ["Stop the clocks that would type into the pane beside the daemon's",
                     "Stop the legacy session",
                     "Install the declaration with the session unit, keeping the old one",
                     "Watch the session unit come up: starting, then running"]
    flat = [str(c) for s in plan.steps for c in s.commands]
    assert not any("systemctl" in c for c in flat + [str(c) for c in plan.rollback])
    assert f"launchctl bootout gui/{UID}/{MAC_CLOCK}" in flat
    assert f"launchctl disable gui/{UID}/{MAC_CLOCK}" in flat
    assert f"launchctl bootout gui/{UID}/{HARNESS_LABEL}" in flat
    assert f"launchctl kickstart -k gui/{UID}/maceff_pd.Resident_1a2b3c" in flat
    live = declaration_path(tmp_path)
    assert flat.index(f"cp {live} {live}.pre-cutover") < flat.index(f"cp {staged_path(tmp_path)} {live}")
    # undo: the declaration first; a job is enabled before it is loaded again, from its plist
    rollback = [str(c) for c in plan.rollback]
    assert rollback[0] == f"cp {live}.pre-cutover {live}"
    plist = tmp_path / "LaunchAgents" / f"{HARNESS_LABEL}.plist"
    enable = rollback.index(f"launchctl enable gui/{UID}/{HARNESS_LABEL}")
    assert rollback[enable + 1] == f"launchctl bootstrap gui/{UID} {plist}"
    assert next(i for i, c in enumerate(rollback) if "kill-server" in c) < enable
    text = format_plan(plan)
    assert "init system: launchd" in text and "launchctl kickstart" in text


def test_a_mac_plan_without_a_harness_agent_names_only_what_is_installed(tmp_path, monkeypatch):
    plan = _mac_ready(tmp_path, monkeypatch, harness_label=lambda agent: None,
                      active_units=lambda: [], default_session=lambda agent: False)
    assert plan.ready
    assert [s.what.split(",")[0] for s in plan.steps] == [
        "Install the declaration with the session unit", "Watch the session unit come up: starting"]
    assert any("no harness LaunchAgent" in c.detail for c in plan.checks)


def test_a_mac_unit_must_agree_with_its_clients_on_the_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    _stage(tmp_path, runtime="/run/user/1")
    plan = build_plan(tmp_path, CARD, AGENT, _mac_probes(), uid=UID)
    assert not plan.ready
    assert any(not c.ok and "don't set" in c.detail for c in plan.checks)


def test_a_host_with_neither_init_system_is_told_so(tmp_path):
    plan = build_plan(tmp_path, CARD, AGENT, _probes(systemd=False), runtime=RUNTIME)
    assert not plan.ready and not plan.steps
    assert "neither systemctl nor launchctl" in plan.checks[0].detail


def _launchctl(loaded=False, bootstrap_rc=0):
    calls = []

    def run(argv):
        from subprocess import CompletedProcess
        calls.append(list(argv))
        if argv[1] == "print":
            if loaded:
                return CompletedProcess(argv, 0, "state = running\n\tpid = 77\n", "")
            return CompletedProcess(argv, 113, "", "Could not find service in domain for user gui: 501")
        if argv[1] == "bootstrap":
            return CompletedProcess(argv, bootstrap_rc, "", "Bootstrap failed: 5: Input/output error"
                                    if bootstrap_rc else "")
        return CompletedProcess(argv, 0, "", "")
    return run, calls


def test_run_on_macos_writes_and_bootstraps_a_one_shot_job(tmp_path):
    import plistlib
    from macf.pd.cutover import arm_launchd
    run, calls = _launchctl()
    plist, log = arm_launchd(AGENT, CARD, tmp_path, staged_path(tmp_path), "/usr/bin/python3", UID,
                             "20261025-120000", environ={"PYTHONPATH": "/src", "PATH": "/opt/homebrew/bin:/usr/bin",
                                                         "HOME": "/Users/r"}, run=run)
    label = "maceff_pd.Resident_1a2b3c.cutover"
    here = declaration_path(tmp_path).parent
    assert plist == here / f"{label}.plist" and log == here / "cutover-20261025-120000.log"
    job = plistlib.loads(plist.read_bytes())
    assert job["Label"] == label
    assert job["RunAtLoad"] is True and job["KeepAlive"] is False, "one run, never restarted"
    assert job["StandardOutPath"] == job["StandardErrorPath"] == str(log)
    argv = job["ProgramArguments"]
    assert argv[:3] == ["/usr/bin/python3", "-m", "macf.cli"] and "--execute" in argv
    assert argv[argv.index("--job-plist") + 1] == str(plist), "the job knows its own plist to remove"
    assert job["EnvironmentVariables"] == {"PYTHONPATH": "/src", "PATH": "/opt/homebrew/bin:/usr/bin",
                                           "HOME": "/Users/r", "MACEFF_AGENT_HOME_DIR": str(tmp_path)}, \
        "the job runs in the environment the plan was checked in, not launchd's bare one"
    assert calls[-1] == ["launchctl", "bootstrap", f"gui/{UID}", str(plist)]


def test_run_on_macos_refuses_while_a_move_is_loaded(tmp_path):
    import pytest
    from macf.pd.cutover import arm_launchd, job_paths
    run, calls = _launchctl(loaded=True)
    with pytest.raises(RuntimeError, match="already loaded"):
        arm_launchd(AGENT, CARD, tmp_path, staged_path(tmp_path), "/usr/bin/python3", UID, "s", run=run)
    assert not any(c[1] == "bootstrap" for c in calls)
    assert not job_paths(tmp_path, CARD, "s")[0].exists()


def test_a_bootstrap_that_fails_leaves_no_plist(tmp_path):
    import pytest
    from macf.pd.cutover import arm_launchd, job_paths
    run, _ = _launchctl(bootstrap_rc=5)
    with pytest.raises(RuntimeError, match="Input/output"):
        arm_launchd(AGENT, CARD, tmp_path, staged_path(tmp_path), "/usr/bin/python3", UID, "s", run=run)
    assert not job_paths(tmp_path, CARD, "s")[0].exists()


def _real_files(fail_on=None):
    """A runner that carries out cp and rm for real, so a rollback can be read from the
    files, and stands in for launchctl, tmux and the monitor sweep. *fail_on* fails the
    first command containing it."""
    import shutil as sh
    ran = []

    def run(command):
        ran.append(str(command))
        argv = command.argv
        if fail_on and fail_on in str(command) and not any(fail_on in r for r in ran[:-1]):
            return 1
        if argv[0] == "cp":
            sh.copyfile(argv[1], argv[2])
        elif argv[0] == "rm":
            Path(argv[1]).unlink()
        return 0
    return run, ran


def test_a_failing_mac_step_rolls_back_to_the_pre_cutover_declaration(tmp_path, monkeypatch):
    from macf.pd.cutover import execute
    plan = _mac_ready(tmp_path, monkeypatch)
    live = declaration_path(tmp_path)
    live.write_text('{"the": "declaration before the move"}')
    run, ran = _real_files(fail_on="launchctl kickstart")
    assert execute(plan, run, lambda: True, lambda line: None) is False
    assert live.read_text() == '{"the": "declaration before the move"}', "restored from .pre-cutover"
    assert not live.with_name(live.name + ".pre-cutover").exists(), "and the saved copy removed"
    assert ran.index(f"launchctl enable gui/{UID}/{HARNESS_LABEL}") > ran.index(f"cp {live}.pre-cutover {live}")
    # a session that never comes up rolls back the same way
    run, ran = _real_files()
    assert execute(plan, run, lambda: False, lambda line: None) is False
    assert live.read_text() == '{"the": "declaration before the move"}'
    assert not live.with_name(live.name + ".pre-cutover").exists()


def test_the_job_removes_its_own_plist_on_success_and_on_failure(tmp_path, monkeypatch):
    import pytest
    from macf.pd.cutover import execute_as_launchd_job
    plan = _mac_ready(tmp_path, monkeypatch)
    live = declaration_path(tmp_path)
    label = "maceff_pd.Resident_1a2b3c.cutover"

    def boom(command):
        raise OSError("a step that raised")
    cases = {"success": (_real_files()[0], True), "failure": (_real_files("launchctl kickstart")[0], False),
             "raised": (boom, None)}
    for name, (run, expected) in cases.items():
        live.write_text("{}")
        live.with_name(live.name + ".pre-cutover").unlink(missing_ok=True)
        plist = tmp_path / f"{label}.plist"
        plist.write_text("<plist/>")
        spawned, lines = [], []
        if expected is None:
            with pytest.raises(OSError):
                execute_as_launchd_job(plan, run, lambda: True, lines.append, plist, label, UID,
                                       spawn=spawned.append)
        else:
            took = execute_as_launchd_job(plan, run, lambda: True, lines.append, plist, label, UID,
                                          spawn=spawned.append)
            assert took is expected, name
        assert not plist.exists(), name
        assert spawned == [["launchctl", "bootout", f"gui/{UID}/{label}"]], name
        assert "booting out its own job" in lines[-1], name


def test_inside_a_claude_session_is_found_by_ancestry():
    from macf.pd.cutover import inside_session
    argvs = {10: ["/bin/zsh"], 11: ["node", "/opt/claude-code/cli.js"], 12: ["python3", "-m", "macf.cli"]}
    assert inside_session(12, ancestors=lambda pid: {10, 11, 12}, argv_of=argvs.get) == 11
    # a launchd job's ancestry is launchd's, never a client's
    assert inside_session(12, ancestors=lambda pid: {12}, argv_of=argvs.get) is None


def _cutover_args(tmp_path, *flags):
    from macf.cli import _build_parser
    return _build_parser().parse_args(["harness", "cutover", "--agent", AGENT, "--home", str(tmp_path),
                                       *flags])


def test_execute_on_macos_refuses_inside_the_session_it_would_end(tmp_path, monkeypatch, capsys):
    from macf import cli
    from macf.pd import cutover
    _stage(tmp_path, runtime=None)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(cutover, "host_probes", lambda home, card: _mac_probes())
    monkeypatch.setattr(cutover, "inside_session", lambda: 4242)
    ran, removed = [], []
    monkeypatch.setattr(cutover, "run_command", lambda c: ran.append(c) or 0)
    monkeypatch.setattr(cutover, "came_up_by_status", lambda *a, **k: (lambda: True))
    monkeypatch.setattr(cutover, "remove_own_job", lambda plist, label, uid, log, spawn=None: removed.append(plist))
    plist = tmp_path / "job.plist"
    rc = cli.cmd_harness_cutover(_cutover_args(tmp_path, "--execute", "--job-plist", str(plist)))
    out = capsys.readouterr().out
    assert rc == 1 and ran == [], "nothing of the move runs"
    assert "refused: this runs inside a Claude Code session (pid 4242)" in out and "--run" in out
    assert removed == [plist], "the job still removes itself"
    # outside a session, the same job carries the move out
    monkeypatch.setattr(cutover, "inside_session", lambda: None)
    assert cli.cmd_harness_cutover(_cutover_args(tmp_path, "--execute", "--job-plist", str(plist))) == 0
    assert ran and any("launchctl kickstart" in str(c) for c in ran)


def test_run_on_macos_goes_through_launchd_not_systemd_run(tmp_path, monkeypatch, capsys):
    from macf import cli
    from macf.pd import cutover
    _stage(tmp_path, runtime=None)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(cutover, "host_probes", lambda home, card: _mac_probes())
    armed = []

    def arm(agent, card, home, staged, python, uid, stamp):
        armed.append((agent, card))
        return tmp_path / "maceff_pd.Resident_1a2b3c.cutover.plist", tmp_path / "cutover-x.log"
    monkeypatch.setattr(cutover, "arm_launchd", arm)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("systemd-run")))
    assert cli.cmd_harness_cutover(_cutover_args(tmp_path, "--run")) == 0
    out = capsys.readouterr().out
    assert armed == [(AGENT, CARD)]
    assert "init system: launchd" in out and f"tail -f {tmp_path / 'cutover-x.log'}" in out


# ============================================================================
# A hand-started client: a plain claude -c in a terminal, held by no unit or tmux server
# ============================================================================

PROJECT = "/Users/resident/project"
START = "Sat Oct 25 12:00:00 2026"


def _hand_started(**over):
    base = dict(unit_active=lambda unit: "inactive", active_units=lambda: [],
                default_session=lambda agent: False, hand_started=lambda agent: [(4321, PROJECT, START)])
    base.update(over)
    return base


def test_a_hand_started_client_gets_a_step_naming_its_pid_on_both_init_systems(tmp_path, monkeypatch):
    _stage(tmp_path)
    systemd = build_plan(tmp_path, CARD, AGENT, _probes(**_hand_started()), runtime=RUNTIME)
    staged_path(tmp_path).unlink()
    mac = _mac_ready(tmp_path, monkeypatch, harness_label=lambda agent: None, **_hand_started())
    for plan in (systemd, mac):
        assert plan.ready, plan.checks
        whats = [s.what for s in plan.steps]
        assert whats[0].startswith("Stop the hand-started client (pid 4321"), whats
        assert whats[1].startswith("Install"), "stopped before anything is installed"
        end = [c for c in plan.steps[0].commands if "end-client" in c.argv]
        assert [c.argv[-3:] for c in end] == [["4321", START, "30"]], \
            "that pid, as the process started then, with the unit's 30 s stop grace"
        assert end[0].timeout > 30
        undo = [str(c) for c in plan.steps[0].undo]
        assert len(undo) == 1 and undo[0].startswith("true") and f"claude -c in {PROJECT}" in undo[0]
        assert "Stop the hand-started client (pid 4321" in format_plan(plan)


def test_a_session_a_harness_or_tmux_holds_is_not_taken_for_hand_started(tmp_path):
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(hand_started=lambda agent: [(4321, PROJECT, START)]),
                      runtime=RUNTIME)
    assert not any("hand-started" in s.what for s in plan.steps)


def test_the_hand_started_grace_is_the_session_units_stop_grace(tmp_path):
    from macf.pd.cutover import _session_grace
    _stage(tmp_path, grace=45.0)
    assert _session_grace(staged_path(tmp_path)) == 45.0
    staged_path(tmp_path).unlink()
    assert _session_grace(staged_path(tmp_path)) == 30.0


def _client(exits_after=None):
    """A stand-in client: alive until *exits_after* seconds after it is signalled, or forever."""
    state = {"t": 0.0, "signalled": [], "at": None}

    def alive(pid):
        return state["at"] is None or exits_after is None or state["t"] < state["at"] + exits_after

    def signal_pid(pid):
        state["signalled"].append(pid)
        state["at"] = state["t"]

    def sleep(s):
        state["t"] += s
    return state, dict(alive=alive, argv_of=lambda pid: ["claude", "-c"], signal_pid=signal_pid,
                       sleep=sleep, clock=lambda: state["t"], same=lambda pid, start: start == START)


def test_the_job_terminates_exactly_that_pid_and_waits_for_it(tmp_path):
    from macf.pd.cutover import end_client
    state, stubs = _client(exits_after=3.0)
    assert end_client(4321, START, 30.0, **stubs) is True
    assert state["signalled"] == [4321]
    assert 3.0 <= state["t"] < 30.0, "it waited for the exit, and no longer"


def test_a_client_that_wont_exit_aborts_the_move_before_install(tmp_path):
    from macf.pd.cutover import end_client, execute
    state, stubs = _client(exits_after=None)
    assert end_client(4321, START, 30.0, **stubs) is False and state["t"] >= 30.0
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(**_hand_started()), runtime=RUNTIME)
    ran = []

    def run(command):
        ran.append(str(command))
        return 1 if "end-client" in command.argv else 0
    lines = []
    assert execute(plan, run, lambda: True, lines.append) is False
    assert not any(c.startswith(("cp ", "rm ", "systemctl")) for c in ran), "nothing installed"
    assert any("claude -c in" in line for line in lines), "the log says how to resume"


def test_a_pid_no_longer_a_client_is_not_signalled():
    from macf.pd.cutover import end_client
    state, stubs = _client(exits_after=1.0)
    stubs["argv_of"] = lambda pid: ["/usr/sbin/sshd"]
    assert end_client(4321, START, 30.0, **stubs) is True and state["signalled"] == []


def test_pid_one_or_below_is_refused_and_never_signalled():
    """kill(0) or kill(-1) would signal a whole group or every process the user owns, and pid 1
    is init: a corrupt pid must refuse, not widen."""
    import pytest
    from macf.pd.cutover import end_client
    for pid in (1, 0, -1):
        state, stubs = _client(exits_after=1.0)
        with pytest.raises(ValueError):
            end_client(pid, START, 30.0, **stubs)
        assert state["signalled"] == [], pid


def test_a_client_in_another_directory_is_untouched(tmp_path, monkeypatch):
    from macf import agent_stack
    from macf.pd.cutover import host_probes
    project = tmp_path / "project"
    other = tmp_path / "elsewhere"
    project.mkdir()
    other.mkdir()
    monkeypatch.setenv("MACEFF_PROJECT_DIR", str(project))
    monkeypatch.setattr(agent_stack, "client_processes",
                        lambda: [(11, str(project)), (12, str(other))])
    monkeypatch.setattr("macf.notify.session.proc_start", lambda pid: f"start-{pid}")
    assert host_probes(tmp_path, CARD).hand_started(AGENT) == [(11, str(project.resolve()), "start-11")]


def test_a_pid_whose_start_time_changed_is_not_signalled():
    """The number came back as another process: the plan's start no longer matches."""
    from macf.pd.cutover import end_client
    state, stubs = _client(exits_after=1.0)
    assert end_client(4321, "Sat Oct 25 11:00:00 2026", 30.0, **stubs) is True
    assert state["signalled"] == []


# ============================================================================
# No daemon installed: the move installs it
# ============================================================================

def test_a_seat_agent_init_staged_reaches_a_ready_plan_that_installs_the_daemon(tmp_path):
    """agent init staged the declaration and skipped pd install: no live declaration and no
    daemon. The plan is ready, installs the declaration, then pd install, undone by uninstall."""
    _stage(tmp_path, live=False)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(**_hand_started(
        daemon_answers=lambda: "no record", daemon_installed=lambda: False)), runtime=RUNTIME)
    assert plan.ready, plan.checks
    assert any(c.name == "daemon" and "installs it" in c.detail for c in plan.checks)
    whats = [s.what for s in plan.steps]
    assert [w.split(" (")[0] for w in whats] == [
        "Stop the hand-started client", "Install the declaration with the session unit",
        "Install the primal daemon under systemd", "Watch the session unit come up: starting, then running"]
    live = declaration_path(tmp_path)
    install, daemon = plan.steps[1], plan.steps[2]
    assert [str(c) for c in install.commands] == [f"cp {staged_path(tmp_path)} {live}"], \
        "nothing to keep, and no daemon to restart yet"
    assert str(install.undo[0]).startswith(f"rm {live}")
    assert daemon.commands[0].argv[-3:] == ["macf.cli", "pd", "install"]
    assert daemon.commands[0].env == {"MACEFF_AGENT_HOME_DIR": str(tmp_path)}
    assert daemon.undo[0].argv[-3:] == ["macf.cli", "pd", "uninstall"]
    # a failure at the watch rolls back: uninstall first, then the declaration removed
    from macf.pd.cutover import execute
    run, ran = _runner()
    assert execute(plan, run, lambda: False, lambda line: None) is False
    tail = ran[-len(plan.rollback):]
    assert tail[0].endswith("pd uninstall      # the daemon wasn't installed before the move")
    assert any(c.startswith(f"rm {live}") for c in tail)


def test_a_daemon_installed_but_silent_still_stops_the_plan(tmp_path):
    _stage(tmp_path)
    plan = build_plan(tmp_path, CARD, AGENT, _probes(daemon_answers=lambda: "no record",
                                                     daemon_installed=lambda: True), runtime=RUNTIME)
    assert not plan.ready
    assert not any("pd install" in s.what for s in plan.steps)


def test_the_launchd_job_gets_a_path_even_from_a_bare_caller(tmp_path):
    from macf.pd.cutover import job_environment
    env = job_environment(tmp_path, {})
    assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin" and env["MACEFF_AGENT_HOME_DIR"] == str(tmp_path)
    assert "PYTHONPATH" not in env and env["HOME"]


def test_a_probe_whose_program_is_missing_says_so(tmp_path, monkeypatch):
    import pytest
    from macf.pd import cutover

    def no_program(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", argv[0])
    probes = cutover.host_probes(tmp_path, CARD)
    monkeypatch.setattr(cutover.subprocess, "run", no_program)
    with pytest.raises(cutover.ProbeUnavailable, match="tmux isn't on PATH"):
        probes.default_session(AGENT)


def test_a_plan_that_cant_be_built_changes_nothing_and_the_job_removes_itself(tmp_path, monkeypatch, capsys):
    from macf import cli
    from macf.pd import cutover

    def unbuildable(*a, **k):
        raise cutover.ProbeUnavailable("tmux isn't on PATH (/usr/bin:/bin), so the plan can't be checked")
    removed, ran = [], []
    monkeypatch.setattr(cutover, "build_plan", unbuildable)
    monkeypatch.setattr(cutover, "run_command", lambda c: ran.append(c) or 0)
    monkeypatch.setattr(cutover, "remove_own_job", lambda plist, label, uid, log, spawn=None: removed.append(plist))
    plist = tmp_path / "job.plist"
    assert cli.cmd_harness_cutover(_cutover_args(tmp_path, "--execute", "--job-plist", str(plist))) == 1
    assert removed == [plist] and ran == [], "the job removes itself; nothing of the move runs"
    assert "tmux isn't on PATH" in capsys.readouterr().err
    assert cli.cmd_harness_cutover(_cutover_args(tmp_path)) == 1, "the plan alone says it and exits 1"
    assert removed == [plist], "outside the job there is no job to remove"


def test_cutover_without_home_plans_for_the_agent_home_not_the_login_home(tmp_path, monkeypatch):
    """A host agent's home is rarely the login's ~. Without --home the plan is built for the
    home `macf_tools env` finds, or it finds neither the staged declaration nor the client."""
    from macf import cli
    from macf.cli import _build_parser
    from macf.pd import cutover
    from macf.utils.paths import find_agent_home
    agent_home, login = tmp_path / "agent_home", tmp_path / "login"
    agent_home.mkdir()
    login.mkdir()
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(agent_home))
    monkeypatch.setenv("HOME", str(login))
    find_agent_home.cache_clear()
    seen = []

    def record(home, *a, **k):
        seen.append(Path(home))
        raise cutover.ProbeUnavailable("stop here")
    monkeypatch.setattr(cutover, "host_probes", lambda home, card: None)
    monkeypatch.setattr(cutover, "build_plan", record)
    try:
        assert cli.cmd_harness_cutover(_build_parser().parse_args(["harness", "cutover", "--agent", AGENT])) == 1
        assert seen == [agent_home], f"planned for {seen}, not the agent home {agent_home}"
        other = tmp_path / "named"
        other.mkdir()
        cli.cmd_harness_cutover(_cutover_args(other))
        assert seen[-1] == other, "--home still names the home"
    finally:
        find_agent_home.cache_clear()
