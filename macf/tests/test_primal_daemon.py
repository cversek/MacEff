"""The primal daemon's core supervising fake units (MIS-0002 step 1).

A fake unit is a small script started as a real child process. It writes its own
liveness to the test's isolated event log, the way a real unit would, and can be told
to exit, fall silent, write liveness that cannot be read, report work in flight, or
report that it waits on a person.
"""
import json
import os
import pwd
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

import macf
import macf.pd.daemon as daemon_module
from macf.agent_events_log import CYCLE_BOUNDARY_EVENT, append_event, get_log_path
from macf.notify.session import proc_start, verify_incarnation
from macf.pd.core import Core, DeclarationRefused, backoff_s, load_declaration
from macf.pd.daemon import AlreadyRunning, Daemon, card_for_home
from macf.pd.interface import UNIT_STATES, Asker, DaemonRecord, Declaration, Peer, Unit, declaration_path

CARD = "Tester@abc123"
ME = pwd.getpwuid(os.getuid()).pw_name
# The directory that holds the package under test, for the fake units' PYTHONPATH:
# they get only the environment they are declared with.
MACF_SRC = str(Path(macf.__path__[0]).resolve().parent)
OPERATOR = Asker(kind="operator", card="Operator@000000")
#: The process an operator's act comes from, as the daemon records it off the socket.
PEER = Peer(uid=os.getuid(), pid=os.getpid(), proc_start=proc_start(os.getpid()) or "unknown")

FAKE_UNIT = r'''
import json, os, sys, time
from macf.notify.session import proc_start

spec = json.loads(sys.argv[1])
if spec.get("crash_once") and not os.path.exists(spec["crash_once"]):
    open(spec["crash_once"], "w").close()  # the next start finds it and runs
    sys.exit(1)
if spec.get("ignore_term"):
    import signal
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if spec.get("child_ignores_term"):
    # A child in the unit's process group that outlives SIGTERM, as a worker a unit
    # forked can; it writes its own pid once its handler is set.
    import subprocess
    subprocess.Popen([sys.executable, "-c",
                      "import os, signal, subprocess, sys, time\n"
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                      "def mark(path, pid):\n"
                      "    open(path + '.tmp', 'w').write(str(pid))\n"
                      "    os.replace(path + '.tmp', path)\n"
                      "mark(sys.argv[1], os.getpid())\n"
                      "if len(sys.argv) > 2:\n"
                      "    leader = os.getppid()\n"
                      "    while os.getppid() == leader:\n"
                      "        time.sleep(0.02)\n"
                      "    if len(sys.argv) > 3 and sys.argv[3] != 'now':\n"
                      "        while not os.path.exists(sys.argv[3]):\n"
                      "            time.sleep(0.02)\n"
                      "    late = subprocess.Popen([sys.executable, '-c', 'import signal, time; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'])\n"
                      "    mark(sys.argv[2], late.pid)\n"
                      "    if len(sys.argv) > 3:\n"
                      "        os._exit(0)\n"
                      "time.sleep(300)\n", spec["child_ignores_term"]]
                     + ([spec["child_forks_after"]] if spec.get("child_forks_after") else [])
                     + ([spec["child_forks_then_exits_on"]] if spec.get("child_forks_then_exits_on") else []))
log, me = os.environ["MACF_EVENTS_LOG_PATH"], os.getpid()
start, began = proc_start(me), time.monotonic()
if spec.get("dump"):
    tmp = spec["dump"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"env": dict(os.environ), "ppid": os.getppid()}, f)
    os.replace(tmp, spec["dump"])

def write(line):
    with open(log, "a") as f:
        f.write(line + "\n")

while True:
    t = time.monotonic() - began
    if "exit_after" in spec and t >= spec["exit_after"]:
        sys.exit(spec.get("code", 0))
    if spec.get("garbage"):
        write('{"event": "pd_unit_alive", "data": {"agent": "%s", "unit": "%s"}}' % (spec["agent"], spec["unit"]))
        write('{"event": "pd_unit_alive", "data": ')
    elif t < spec.get("alive_for", 1e9):
        data = {"agent": spec["agent"], "unit": spec["unit"], "pid": me,
                "proc_start": start, "interval_s": spec["interval"]}
        if spec.get("imposter"):
            data["pid"], data["proc_start"] = os.getppid(), proc_start(os.getppid())
        if spec.get("wrong_start"):
            data["proc_start"] = "not this process's start"
        for key in ("waiting_on", "in_flight"):
            if key in spec and t < spec.get(key + "_for", 1e9):
                data[key] = spec[key]
        write(json.dumps({"timestamp": time.time(), "event": "pd_unit_alive", "data": data}))
    time.sleep(spec["interval"])
'''


@pytest.fixture
def script(tmp_path):
    path = tmp_path / "fake_unit.py"
    path.write_text(FAKE_UNIT)
    return path


def make_unit(name, script, behaviour, *, interval=0.05, restart="on-failure", environment=None,
              stop_grace_s=1.0):
    env = {"MACF_EVENTS_LOG_PATH": str(get_log_path()), "PYTHONPATH": MACF_SRC}
    env.update(environment or {})
    spec = dict(behaviour, unit=name, agent=CARD, interval=interval)
    return Unit(name=name, command=[sys.executable, str(script), json.dumps(spec)], account=ME,
                restart=restart, liveness_interval_s=interval, memory_limit_mb=64, environment=env,
                stop_grace_s=stop_grace_s)


@pytest.fixture
def make_core():
    cores = []

    def make(units, **kwargs):
        options = {"backoff_base_s": 0.05, "backoff_cap_s": 0.2, "drain_timeout_s": 5.0}
        options.update(kwargs)
        core = Core(Declaration(version=1, agent=CARD, units=units), CARD, **options)
        cores.append(core)
        return core

    yield make
    for core in cores:
        core.shutdown("the test is over")


def drive(core, until, timeout=5.0):
    """Tick the core until ``until()`` holds; False if it never did."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        core.tick()
        if until():
            return True
        time.sleep(0.01)
    return False


def events(name, unit=None):
    rows = []
    for line in get_log_path().read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # a fake unit's deliberately unreadable liveness
    return [r["data"] for r in rows
            if r.get("event") == name and (unit is None or r["data"].get("unit") == unit)]


def states(unit):
    return [d["state"] for d in events("pd_unit_state", unit)]


def test_clean_parent(make_core, script, tmp_path, monkeypatch):
    """A unit is the daemon's own child and gets the declared environment, nothing inherited (R12)."""
    monkeypatch.setenv("PD_TEST_UNDECLARED", "inherited")
    dump = tmp_path / "seen.json"
    # A Python child started in the C locale adds LC_CTYPE to its own environment
    # (PEP 538). That is the child's doing, not an inheritance; turning it off keeps
    # the comparison below exact.
    unit = make_unit("worker", script, {"dump": str(dump)},
                     environment={"DECLARED": "yes", "PYTHONCOERCECLOCALE": "0"})
    core = make_core([unit])
    core.boot()

    assert drive(core, lambda: dump.exists() and core.state("worker") == "running")
    seen = json.loads(dump.read_text())
    assert seen["ppid"] == os.getpid()
    assert seen["env"]["DECLARED"] == "yes"
    assert "PD_TEST_UNDECLARED" not in seen["env"]
    assert set(seen["env"]) == set(unit.environment)


def test_env_rendered_at_start(make_core, script, tmp_path):
    """The environment comes from the declaration as it stands when the daemon starts (R13)."""
    home = tmp_path / "home"
    dump = tmp_path / "seen.json"
    for value in ("first", "second"):
        unit = make_unit("worker", script, {"dump": str(dump)}, environment={"SETTING": value})
        path = declaration_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(Declaration(version=1, agent=CARD, units=[unit]).model_dump_json())
        dump.unlink(missing_ok=True)

        core = make_core(load_declaration(home, CARD).units)
        core.boot()
        assert drive(core, lambda: dump.exists())
        assert json.loads(dump.read_text())["env"]["SETTING"] == value
        core.shutdown("next start")


def test_placeholders_filled_at_start(make_core, script, tmp_path):
    """A declared value names the agent home, the card or the runtime directory by
    placeholder, and the core fills each in when it starts the unit (R13). A core given no
    value for one fails the unit with the reason rather than start it with the braces."""
    dump = tmp_path / "seen.json"
    unit = make_unit("worker", script, {"dump": str(dump)},
                     environment={"WHERE": "{agent_home}/notes", "WHO": "{card}", "RUN": "{runtime_dir}"})
    core = make_core([unit], placeholders={"agent_home": "/homes/t", "card": CARD, "runtime_dir": "/run/t"})
    core.boot()
    assert drive(core, lambda: dump.exists())
    env = json.loads(dump.read_text())["env"]
    assert (env["WHERE"], env["WHO"], env["RUN"]) == ("/homes/t/notes", CARD, "/run/t")

    bare = make_core([make_unit("other", script, {}, environment={"WHERE": "{agent_home}"})])
    bare.boot()
    assert bare.state("other") == "failed"
    assert "{agent_home}" in events("pd_unit_state", "other")[-1]["reason"]


def test_states(make_core, script):
    """A unit moves through the listed states, and each move is an event naming why (R20)."""
    core = make_core([make_unit("worker", script, {"exit_after": 0.3, "code": 1})])
    core.boot()

    assert drive(core, lambda: states("worker").count("running") >= 2)
    core.stop("worker", OPERATOR, "the test is done with it", peer=PEER)
    assert drive(core, lambda: core.state("worker") == "stopped")

    seen = states("worker")
    assert seen[:6] == ["starting", "running", "failed", "starting", "running", "stopped"]
    assert set(seen) <= set(UNIT_STATES)
    assert all(d["reason"] for d in events("pd_unit_state", "worker"))
    asked = [(d["act"], d["asked_by"]["kind"]) for d in events("pd_control", "worker")]
    assert asked[:2] == [("start", "policy"), ("start", "policy")]
    assert asked[-1] == ("stop", "operator")


def test_starting_event_names_the_new_pid(make_core, script):
    """The 'starting' state event names the pid that was actually started. The event log is
    the only record of a state change (R16, R52); a stale or missing pid in it is a gap no
    other record fills."""
    core = make_core([make_unit("worker", script, {})])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")

    starting = [d for d in events("pd_unit_state", "worker") if d["state"] == "starting"]
    assert starting and starting[-1]["pid"] == core.pid("worker")


def test_liveness_verdicts(make_core, script):
    """Silence from the start, liveness that stops, liveness that cannot be read, liveness
    in another process's name, and liveness under the unit's own pid with a start time that
    isn't its own are five failures, and none of them is alive (service_supervision: unknown
    is not healthy; R15: a pid alone is not the unit)."""
    names = ("silent", "stale", "garbled", "imposter", "wrong_start")
    core = make_core([
        make_unit("silent", script, {"alive_for": 0}, restart="never"),
        # A unit that must beat before it goes quiet gets an interval a cold start on a
        # loaded runner can meet: at 0.05 s its first beat was due within 0.15 s (CI, Oct 14).
        make_unit("stale", script, {"alive_for": 1.0}, interval=0.5, restart="never"),
        make_unit("garbled", script, {"garbage": True}, restart="never"),
        make_unit("imposter", script, {"imposter": True}, restart="never"),
        make_unit("wrong_start", script, {"wrong_start": True}, restart="never"),
    ])
    core.boot()

    assert drive(core, lambda: all(core.state(u) == "failed" for u in names))
    reasons = {u: events("pd_unit_state", u)[-1]["reason"] for u in names}
    assert "stale" in reasons["stale"] and "running" in states("stale")
    for u in ("silent", "garbled", "imposter", "wrong_start"):
        assert "no liveness" in reasons[u] and "running" not in states(u)


def test_no_restart_while_waiting(make_core, script):
    """A unit waiting on a person is reported so, and its silence is not taken for death (R21, R22)."""
    core = make_core([make_unit("worker", script, {"waiting_on": "a permission prompt", "alive_for": 1.0},
                                interval=0.5)])   # its first beat must meet a cold start
    core.boot()

    assert drive(core, lambda: core.state("worker") == "waiting_on_a_person")
    pid = core.pid("worker")
    # silent for longer than three intervals, which a unit not waiting would fail for
    assert not drive(core, lambda: core.state("worker") != "waiting_on_a_person", timeout=3.0)
    assert core.pid("worker") == pid
    assert "failed" not in states("worker")
    assert "a permission prompt" in events("pd_unit_state", "worker")[-1]["reason"]


def test_work_in_flight_checked(make_core, script):
    """An asked restart waits for the unit's work in flight to drain (R49)."""
    core = make_core([make_unit("worker", script, {"in_flight": 1, "in_flight_for": 0.6})])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first = core.pid("worker")

    core.restart("worker", OPERATOR, "a new setting", peer=PEER)
    assert not drive(core, lambda: core.pid("worker") != first, timeout=0.3)
    assert drive(core, lambda: core.pid("worker") != first and core.state("worker") == "running")
    stopped = [d for d in events("pd_unit_state", "worker") if d["state"] == "stopped"]
    assert "drained" in stopped[-1]["reason"]


def test_unreported_work_is_taken_as_idle_and_said_so(make_core, script):
    """A unit that never reports work in flight is restarted at once, and the record says the
    daemon took it as idle rather than knew it was (R49)."""
    core = make_core([make_unit("worker", script, {})])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first = core.pid("worker")

    core.restart("worker", OPERATOR, "a new setting", peer=PEER)
    assert drive(core, lambda: core.pid("worker") not in (None, first) and core.state("worker") == "running")
    stopped = [d for d in events("pd_unit_state", "worker") if d["state"] == "stopped"]
    assert "taken as idle" in stopped[-1]["reason"]


def test_no_restart_exit_code(make_core, script):
    """A unit that exits with a no-restart code stays stopped, whatever its policy."""
    core = make_core([make_unit("worker", script, {"exit_after": 0.1, "code": 78}, restart="always")])
    core.boot()

    assert drive(core, lambda: core.state("worker") == "stopped")
    assert not drive(core, lambda: core.state("worker") != "stopped", timeout=0.5)
    assert states("worker").count("starting") == 1


def test_restart_always_after_clean_exit(make_core, script):
    """'always' means always: a unit that exits with its own declared success code is
    restarted too, not left stopped as if it had asked not to be (contrast the no-restart
    code above)."""
    core = make_core([make_unit("worker", script, {"exit_after": 0.05}, restart="always")])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first = core.pid("worker")

    assert drive(core, lambda: "stopped" in states("worker"))
    assert drive(core, lambda: core.pid("worker") not in (None, first)
                 and core.state("worker") == "running")


def test_foreign_account_refused(tmp_path, script):
    """A unit declared under another account refuses the whole declaration (R78)."""
    unit = make_unit("worker", script, {}).model_copy(update={"account": "someone-else"})
    path = declaration_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(Declaration(version=1, agent=CARD, units=[unit]).model_dump_json())

    with pytest.raises(DeclarationRefused, match="R78"):
        load_declaration(tmp_path, CARD)


def test_no_cross_agent_control(tmp_path, script):
    """A declaration naming another agent is refused whole, so one copied from another
    agent's home never starts that agent's units under this agent's name (R07)."""
    path = declaration_path(tmp_path)
    path.parent.mkdir(parents=True)
    unit = make_unit("worker", script, {})
    path.write_text(Declaration(version=1, agent="Someone@fff000", units=[unit]).model_dump_json())

    with pytest.raises(DeclarationRefused, match="R07"):
        load_declaration(tmp_path, CARD)


def test_stop_after_a_failure_is_stopped(make_core, script):
    """An operator's stop of a unit already failed and being killed ends in stopped, not failed."""
    core = make_core([make_unit("worker", script, {"alive_for": 0.15}, restart="never")])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "failed")
    core.stop("worker", OPERATOR, "taking it down", peer=PEER)
    assert drive(core, lambda: core.state("worker") == "stopped")
    assert "stopped as asked" in events("pd_unit_state", "worker")[-1]["reason"]


def test_drain_times_out(make_core, script):
    """A restart whose work in flight never drains goes ahead at the timeout, and says so (R49)."""
    core = make_core([make_unit("worker", script, {"in_flight": 1})], drain_timeout_s=0.3)
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first = core.pid("worker")

    core.restart("worker", OPERATOR, "a new setting", peer=PEER)
    assert drive(core, lambda: core.pid("worker") != first and core.state("worker") == "running")
    stopped = [d for d in events("pd_unit_state", "worker") if d["state"] == "stopped"]
    assert "did not drain" in stopped[-1]["reason"]


def test_outside_stop_beats_gates(make_core, script):
    """A unit that ignores SIGTERM is killed when its grace runs out, so a stop is never held (R48)."""
    core = make_core([make_unit("worker", script, {"ignore_term": True}, stop_grace_s=0.3)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")

    core.stop("worker", OPERATOR, "taking it down", peer=PEER)
    assert drive(core, lambda: core.state("worker") == "stopped")
    assert "SIGKILL" in events("pd_unit_state", "worker")[-1]["reason"]


def test_each_unit_has_its_own_stop_grace(make_core, script):
    """A stop kills each unit at its own declared grace: one that needs longer to flush is
    given it, and one that holds nothing is not kept waiting for it (R48)."""
    now = [1000.0]
    core = make_core([make_unit("quick", script, {"ignore_term": True}, stop_grace_s=0.2),
                      make_unit("slow", script, {"ignore_term": True}, stop_grace_s=30.0)],
                     clock=lambda: now[0])
    core.boot()
    assert drive(core, lambda: core.state("quick") == "running" and core.state("slow") == "running")

    core.stop("quick", OPERATOR, "down", peer=PEER)
    core.stop("slow", OPERATOR, "down", peer=PEER)
    now[0] += 1.0
    assert drive(core, lambda: core.state("quick") == "stopped")
    assert core.state("slow") != "stopped" and core.pid("slow") is not None
    now[0] += 30.0
    assert drive(core, lambda: core.state("slow") == "stopped")


def test_an_operator_act_needs_the_process_that_asked(make_core, script):
    """An operator's act is recorded with the process the kernel says asked for it, and one
    that comes without it is refused before anything is done (R52)."""
    core = make_core([make_unit("worker", script, {})])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")

    with pytest.raises(ValueError, match="records its peer"):
        core.stop("worker", OPERATOR, "no process named")
    assert core.state("worker") == "running"
    assert [d["act"] for d in events("pd_control", "worker")] == ["start"]


def test_log_rotation_followed(make_core, script):
    """Liveness written after the event log is rotated is still read."""
    core = make_core([make_unit("worker", script, {})])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")

    log = get_log_path()
    log.rename(log.with_name(log.name + ".1"))
    log.write_text("")
    assert not drive(core, lambda: core.state("worker") != "running", timeout=0.6)


def test_command_that_cannot_start(make_core, script, tmp_path):
    """A command that cannot be executed is a failure with its reason, not a crash of the core."""
    unit = make_unit("worker", script, {}, restart="never").model_copy(
        update={"command": [str(tmp_path / "no-such-program")]})
    core = make_core([unit])
    core.boot()
    assert core.state("worker") == "failed"
    assert "could not start" in events("pd_unit_state", "worker")[-1]["reason"]


def _crash(core):
    """What a daemon's crash leaves: its units still running and nobody supervising them.
    Returns their processes, so a test can reap one as init would once its parent is gone."""
    left = {}
    for name, r in core._units.items():
        if r.proc is not None:
            left[name] = r.proc
        r.proc, r.want_up, r.restart_at = None, False, None
    return left


@dataclass(frozen=True, kw_only=True)
class _Survivor:
    unit: Unit
    pid: int
    left: dict


def _survivor(make_core, script, **kwargs) -> _Survivor:
    """A unit started by a first daemon that then crashed, leaving it running."""
    unit = make_unit("worker", script, {}, **kwargs)
    first = make_core([unit])
    first.boot()
    assert drive(first, lambda: first.state("worker") == "running")
    pid = first.pid("worker")
    return _Survivor(unit=unit, pid=pid, left=_crash(first))


def test_survivor_adopted_not_started_twice(make_core, script):
    """The units outlive the daemon's exit: a daemon restarted after a crash adopts the unit its
    predecessor started, confirmed by pid and start time (R15), says it was carried (R47), and
    starts no second copy."""
    survivor = _survivor(make_core, script)
    starts_before = states("worker").count("starting")

    second = make_core([survivor.unit])
    second.boot()

    assert second.pid("worker") == survivor.pid
    assert states("worker").count("starting") == starts_before
    carried = [d for d in events("pd_unit_state", "worker") if d["reason"].startswith("carried")]
    assert carried and carried[-1]["pid"] == survivor.pid
    assert drive(second, lambda: second.state("worker") == "running")


def test_an_adopted_unit_reads_since_its_own_start(make_core, script):
    """An adopted unit's "since" is when its process began, not the adoption, so a daemon's
    restart doesn't make its units read as just restarted."""
    began = time.time()
    survivor = _survivor(make_core, script)
    time.sleep(1.5)
    second = make_core([survivor.unit])
    adopted_at = time.time()
    second.boot()
    since = {s.unit: s.since for s in second.statuses()}["worker"]
    # proc_start has one-second resolution on macOS.
    assert began - 1.0 <= since <= adopted_at - 0.5


def test_a_reused_pid_is_not_adopted(make_core, script):
    """A recorded pid whose start time no longer matches is another process now. The unit is
    started fresh and that process is left alone."""
    append_event("pd_unit_state", {"agent": CARD, "unit": "worker", "state": "running",
                                   "pid": os.getpid(), "proc_start": "not this process",
                                   "reason": "recorded by a daemon long gone"})
    core = make_core([make_unit("worker", script, {})])
    core.boot()
    assert core.pid("worker") not in (None, os.getpid())


def test_an_adopted_unit_that_dies_is_restarted(make_core, script):
    """An adopted unit is not this daemon's child, so its end is seen by probing it, and its
    exit status, which cannot be read, is taken as a failure under the restart policy."""
    survivor = _survivor(make_core, script, restart="on-failure")
    second = make_core([survivor.unit])
    second.boot()

    os.killpg(survivor.pid, signal.SIGKILL)
    survivor.left["worker"].wait(timeout=5)   # reaped, as init reaps a dead daemon's orphans
    assert drive(second, lambda: second.pid("worker") not in (None, survivor.pid)
                 and second.state("worker") == "running")
    failed = [d["reason"] for d in events("pd_unit_state", "worker") if d["state"] == "failed"]
    assert any("cannot see" in reason for reason in failed)


def test_an_adopted_unit_stops_when_asked(make_core, script):
    """Each unit leads its own process group, so a stop reaches an adopted unit as it reaches
    one this daemon started."""
    survivor = _survivor(make_core, script)
    second = make_core([survivor.unit])
    second.boot()

    second.stop("worker", OPERATOR, "the test is done with it", peer=PEER)
    survivor.left["worker"].wait(timeout=5)
    assert drive(second, lambda: second.state("worker") == "stopped")


def test_a_survivor_is_adopted_across_a_compaction(make_core, script):
    """A unit that runs steadily writes no state event, so after a compaction its last one
    sits before the boundary. The next daemon still adopts it: it reads back past the
    boundary and past its own start, as far as the previous daemon's."""
    unit = make_unit("worker", script, {})
    first = make_core([unit])
    first.record_start(os.getpid(), "the first daemon's start")
    first.boot()
    assert drive(first, lambda: first.state("worker") == "running")
    pid = first.pid("worker")
    _crash(first)
    append_event(CYCLE_BOUNDARY_EVENT, {"source": "test"})

    second = make_core([unit])
    second.record_start(os.getpid(), "the second daemon's start")
    second.boot()
    assert second.pid("worker") == pid
    assert states("worker").count("starting") == 1


def test_an_adopted_unit_that_went_silent_is_failed(make_core, script):
    """A unit that stopped writing liveness while no daemon ran is judged from its adoption,
    as a start is, so it becomes overdue instead of reading running forever (R15, R17)."""
    unit = make_unit("worker", script, {"alive_for": 1.0}, interval=0.5,   # its first beat
                     restart="never")                                     # must meet a cold start
    first = make_core([unit])
    first.boot()
    assert drive(first, lambda: first.state("worker") == "running")
    pid = first.pid("worker")
    left = _crash(first)
    time.sleep(1.2)   # silent now, with no daemon watching

    second = make_core([unit])
    second.boot()
    assert second.pid("worker") == pid
    assert drive(second, lambda: second.state("worker") == "failed", timeout=5.0)
    left["worker"].wait(timeout=5)


def _windowed(script):
    """A core whose one session unit never fails, with a quiet window ahead of now that the
    test can move the core's wall clock into and out of."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from macf.pd.interface import Window

    zone = "Asia/Kathmandu"
    ahead = datetime.now(ZoneInfo(zone))
    window = Window(start=(ahead + timedelta(hours=1)).strftime("%H:%M"),
                    end=(ahead + timedelta(hours=3)).strftime("%H:%M"))
    unit = make_unit("worker", script, {}, restart="always").model_copy(update={"kind": "session"})
    shift = {"s": 0.0}
    core = Core(Declaration(version=1, agent=CARD, units=[unit], quiet_windows=[window], timezone=zone),
                CARD, wall=lambda: time.time() + shift["s"], backoff_base_s=0.05, backoff_cap_s=0.2)
    return core, shift


def test_a_held_restart_is_the_operators_act_when_the_window_ends(script):
    """An operator's restart a quiet window holds is carried out when the window ends, as
    the operator's act with the process that asked (R50, R52). The unit never fails, so
    nothing but the held act can start its next run."""
    core, shift = _windowed(script)
    try:
        core.boot()
        assert drive(core, lambda: core.state("worker") == "running")
        first = core.pid("worker")
        shift["s"] = 2 * 3600.0   # inside the window
        core.restart("worker", OPERATOR, "asked during the window", peer=PEER)
        assert not drive(core, lambda: core.pid("worker") not in (None, first), timeout=0.5)
        shift["s"] = 0.0          # the window has ended
        assert drive(core, lambda: core.pid("worker") not in (None, first)
                     and core.state("worker") == "running")
        done = [d for d in events("pd_control", "worker") if d["act"] == "restart"][-1]
        assert done["asked_by"]["kind"] == "operator" and done["peer"]["pid"] == PEER.pid
        assert "held until a quiet window ended" in done["reason"]
    finally:
        core.shutdown("the test is over")


def test_a_stop_ends_a_held_restart(script):
    """A stop asked after a held restart wins: when the window ends the unit stays stopped
    (R48)."""
    core, shift = _windowed(script)
    try:
        core.boot()
        assert drive(core, lambda: core.state("worker") == "running")
        shift["s"] = 2 * 3600.0
        core.restart("worker", OPERATOR, "asked during the window", peer=PEER)
        core.stop("worker", OPERATOR, "and then stopped", peer=PEER)
        assert drive(core, lambda: core.state("worker") == "stopped")
        shift["s"] = 0.0
        assert not drive(core, lambda: core.state("worker") != "stopped", timeout=1.0)
    finally:
        core.shutdown("the test is over")


def test_backoff_doubles_to_its_cap():
    assert [backoff_s(n, 1.0, 8.0) for n in range(7)] == [0.0, 1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


# ---------------------------------------------------------------------------- the process

def make_home(tmp_path, units):
    """An agent home whose own files name it Tester@abc123, with the units declared."""
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "Tester"}}))
    path = declaration_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Declaration(version=1, agent=CARD, units=units).model_dump_json())
    return home


@pytest.fixture
def base():
    """A runtime directory short enough for a socket path on every platform."""
    path = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def run_daemon():
    running = []

    def run(home, base, **options):
        options = {"backoff_base_s": 0.05, "backoff_cap_s": 0.2, **options}
        daemon = Daemon(home, base=base, **options)
        daemon.start()
        thread = threading.Thread(target=daemon.serve, daemon=True)
        thread.start()
        running.append((daemon, thread))
        return daemon

    yield run
    for daemon, thread in running:
        daemon.stop(units=True)
        thread.join(timeout=10)
        daemon.core.shutdown("the test is over")   # units a plain stop left running


def ask(daemon, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(str(daemon.control_path))
        conn.sendall(json.dumps(request).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def unit_state(daemon, unit):
    return {u["unit"]: u["state"] for u in ask(daemon, {"op": "status"})["units"]}[unit]


def unit_pid(daemon, unit):
    return {u["unit"]: u["pid"] for u in ask(daemon, {"op": "status"})["units"]}[unit]


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_identity_not_from_env(tmp_path, script, monkeypatch):
    """The daemon's identity comes from its home's own files, whatever the environment says (R02)."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    monkeypatch.setenv("MACEFF_AGENT_NAME", "SomeoneElse")
    assert card_for_home(home) == CARD


def test_identity_needs_at_least_six_hex_chars(tmp_path, script):
    """The card's identifier is the first six characters of the agent's own id file; exactly
    six is the shortest usable identifier, not already too short to refuse."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    (home / ".maceff_primary_agent.id").write_text("abc123\n")  # exactly six: the boundary
    assert card_for_home(home) == "Tester@abc123"


def test_the_daemon_fills_in_its_own_values(tmp_path, script, base, run_daemon):
    """The values come from the daemon, not the declaration: the home it was given, the card
    read from that home, and the runtime directory it binds in (R13)."""
    dump = tmp_path / "seen.json"
    home = make_home(tmp_path, [make_unit("worker", script, {"dump": str(dump)}, environment={
        "WHERE": "{agent_home}", "WHO": "{card}", "RUN": "{runtime_dir}"})])
    run_daemon(home, base)
    assert wait_for(lambda: dump.exists())
    env = json.loads(dump.read_text())["env"]
    assert (env["WHERE"], env["WHO"], env["RUN"]) == (str(home), CARD, str(base))


def test_one_per_agent(tmp_path, script, base, run_daemon):
    """A second daemon for the same agent refuses to start while the first lives (R01)."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    first = run_daemon(home, base)
    with pytest.raises(AlreadyRunning):
        Daemon(home, base=base).start()

    first.stop()
    assert wait_for(lambda: not first.record_path.exists())
    second = run_daemon(home, base)
    assert ask(second, {"op": "status"})["ok"]


def test_no_network_listener(tmp_path, script, base, run_daemon):
    """The daemon listens on a Unix socket and nothing else (R80)."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert daemon._listener.family == socket.AF_UNIX
    assert "AF_INET" not in Path(daemon_module.__file__).read_text()


def test_record_names_the_daemon(tmp_path, script, base, run_daemon):
    """The record beside the socket names this process, and both go when the daemon stops."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    record = DaemonRecord.model_validate_json(daemon.record_path.read_text())
    assert record.pid == os.getpid() and verify_incarnation(record.pid, record.proc_start)
    assert daemon.control_path.exists()

    daemon.stop()
    assert wait_for(lambda: not daemon.record_path.exists() and not daemon.control_path.exists())


def test_a_signal_leaves_the_units_for_the_next_daemon(tmp_path, script, base, run_daemon):
    """A daemon that ends on a signal, as a restart through the outer tier ends it, leaves its
    units running, and the next daemon adopts them, so the session outlives a restart of the
    daemon. Stopping every unit is its own act (the operator's ruling of 2026-10-10)."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    first = run_daemon(home, base)
    assert wait_for(lambda: unit_state(first, "worker") == "running")
    pid = unit_pid(first, "worker")
    first.stop()
    assert wait_for(lambda: not first.record_path.exists())
    assert verify_incarnation(pid, proc_start(pid))   # still running, with no daemon
    second = run_daemon(home, base)
    assert unit_pid(second, "worker") == pid


def test_a_missing_record_does_not_let_a_second_daemon_in(tmp_path, script, base, run_daemon):
    """With the record gone, as a sweep of the runtime directory leaves it, the socket still
    answers, so a second daemon is refused and the first keeps its socket (R01)."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    first = run_daemon(home, base)
    first.record_path.unlink()
    with pytest.raises(AlreadyRunning):
        Daemon(home, base=base).start()
    assert ask(first, {"op": "status"})["ok"]


def test_a_stopping_daemon_removes_only_what_is_still_its_own(tmp_path, script, base, run_daemon):
    """A daemon that stops after a successor has bound the path and written its record
    removes neither."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    first = run_daemon(home, base)
    record = DaemonRecord.model_validate_json(first.record_path.read_text())
    theirs = record.model_copy(update={"pid": 1, "proc_start": "the successor's start"}).model_dump_json()
    first.control_path.unlink()
    successor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    successor.bind(str(first.control_path))
    first.record_path.write_text(theirs)
    try:
        first.stop()
        assert wait_for(lambda: first._listener.fileno() == -1)
        assert first.control_path.exists() and first.record_path.read_text() == theirs
    finally:
        successor.close()
        first.control_path.unlink(missing_ok=True)


def daemon_acts():
    """The daemon's own events in log order: its start, and its acts on units."""
    names = []
    for line in get_log_path().read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") in ("pd_daemon_start", "pd_unit_state", "pd_control"):
            names.append(row["event"])
    return names


def test_a_daemon_says_it_started_before_any_unit(tmp_path, script, base, run_daemon):
    """A daemon's life begins in the log with pd_daemon_start, naming the process its record
    names, before the first act on a unit, so what it observes can be folded from there."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")
    assert daemon_acts()[0] == "pd_daemon_start"
    record = DaemonRecord.model_validate_json(daemon.record_path.read_text())
    [start] = events("pd_daemon_start")
    assert (start["agent"], start["pid"], start["proc_start"]) == (CARD, record.pid, record.proc_start)


def test_a_refused_daemon_says_nothing_started(tmp_path, script, base, run_daemon):
    """A second daemon refused for the agent writes no start (R01), so it cannot end the
    life of the observations the running daemon made."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    run_daemon(home, base)
    with pytest.raises(AlreadyRunning):
        Daemon(home, base=base).start()
    assert len(events("pd_daemon_start")) == 1


def test_private_artifacts_are_mode_0600(tmp_path, script, base, run_daemon):
    """The control socket and the daemon record are reachable or readable by no one but this
    user, whatever the process umask would otherwise leave them."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert stat.S_IMODE(daemon.control_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(daemon.record_path.stat().st_mode) == 0o600


def test_control_events(tmp_path, script, base, run_daemon):
    """Status reports each unit, and a stop asked over the socket is done and recorded with
    who asked, as claimed, and the process that asked, as the kernel says (R48, R52)."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")

    reply = ask(daemon, {"op": "stop", "unit": "worker", "reason": "maintenance",
                         "asked_by": {"kind": "operator", "card": "Operator@000000"}})
    assert reply["ok"]
    assert wait_for(lambda: unit_state(daemon, "worker") == "stopped")
    control = events("pd_control", "worker")[-1]
    assert (control["act"], control["asked_by"]["kind"], control["reason"]) == ("stop", "operator", "maintenance")
    peer = control["peer"]
    assert (peer["uid"], peer["pid"]) == (os.getuid(), os.getpid())
    assert verify_incarnation(peer["pid"], peer["proc_start"])


def test_a_request_cannot_claim_an_inside_asker(tmp_path, script, base, run_daemon):
    """Over the socket the asker is the operator or the declared wind-down. A request that
    claims the daemon's own policy is refused, and nothing is done (R52)."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")

    reply = ask(daemon, {"op": "stop", "unit": "worker", "reason": "posing as policy",
                         "asked_by": {"kind": "policy"}})
    assert not reply["ok"] and "operator or the declared wind-down" in reply["error"]
    assert unit_state(daemon, "worker") == "running"
    assert all(d["reason"] != "posing as policy" for d in events("pd_control", "worker"))


def test_start_and_restart_over_socket(tmp_path, script, base, run_daemon):
    """The control socket's start and restart ops reach the core method of the same name, not
    each other's: restart gives a running unit a new pid, and start brings a stopped one back
    (R48, R52)."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")
    first = unit_pid(daemon, "worker")

    reply = ask(daemon, {"op": "restart", "unit": "worker", "reason": "pick up a change",
                         "asked_by": {"kind": "operator", "card": "Operator@000000"}})
    assert reply["ok"]
    assert wait_for(lambda: unit_state(daemon, "worker") == "running" and unit_pid(daemon, "worker") != first)

    reply = ask(daemon, {"op": "stop", "unit": "worker", "reason": "take it down",
                         "asked_by": {"kind": "operator", "card": "Operator@000000"}})
    assert reply["ok"]
    assert wait_for(lambda: unit_state(daemon, "worker") == "stopped")

    reply = ask(daemon, {"op": "start", "unit": "worker", "reason": "bring it back",
                         "asked_by": {"kind": "operator", "card": "Operator@000000"}})
    assert reply["ok"]
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")


def test_control_refuses_what_it_cannot_do(tmp_path, script, base, run_daemon):
    """An unknown operation, a unit outside the declaration, or a compaction is refused, and nothing is done."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    assert wait_for(lambda: unit_state(daemon, "worker") == "running")
    operator = {"kind": "operator"}

    assert not ask(daemon, {"op": "explode"})["ok"]
    reply = ask(daemon, {"op": "stop", "unit": "elsewhere", "reason": "x", "asked_by": operator})
    assert not reply["ok"] and "not a unit" in reply["error"]
    assert not ask(daemon, {"op": "compact", "reason": "x", "asked_by": operator})["ok"]
    assert unit_state(daemon, "worker") == "running"


def test_a_request_line_has_one_deadline(tmp_path, script, base, run_daemon, monkeypatch):
    """A client that sends its request a byte at a time is cut off when the line's deadline
    passes, not when it stops sending, so it cannot hold the loop that supervises the units."""
    monkeypatch.setattr(daemon_module, "REQUEST_TIMEOUT_S", 0.5)
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    stop = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(str(daemon.control_path))

        def dribble():   # a byte every 0.1 s, each well inside the deadline of the one before
            while not stop.is_set():
                try:
                    conn.sendall(b" ")
                except (BrokenPipeError, ConnectionResetError):
                    stop.set()   # the daemon has answered and closed its end
                    continue
                time.sleep(0.1)

        sender = threading.Thread(target=dribble, daemon=True)
        began = time.monotonic()
        sender.start()
        try:
            conn.settimeout(5)
            reply = conn.recv(4096)
            elapsed = time.monotonic() - began
        finally:
            stop.set()
            sender.join(timeout=2)
    assert b"no complete request line" in reply and elapsed < 2.0
    assert wait_for(lambda: unit_state(daemon, "worker") in ("starting", "running"))


def test_a_request_that_fails_inside_the_daemon_costs_only_itself(tmp_path, script, base, run_daemon,
                                                                   monkeypatch):
    """A request whose handling raises is answered with the failure, and the daemon goes on
    serving: one bad request must not end the daemon and leave its units unsupervised."""
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    real, calls = daemon.core.statuses, []

    def fails_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("a fault inside the daemon")
        return real()

    monkeypatch.setattr(daemon.core, "statuses", fails_once)
    reply = ask(daemon, {"op": "status"})
    assert reply["ok"] is False and "a fault inside the daemon" in reply["error"]
    assert wait_for(lambda: unit_state(daemon, "worker") in ("starting", "running"))


def test_runtime_dir_must_be_private(tmp_path, script, base):
    """A runtime directory that group or others can open is refused before anything binds."""
    base.chmod(0o755)
    with pytest.raises(OSError, match="open to its group or others"):
        Daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base=base).start()


def test_socket_path_too_long(tmp_path, script):
    """A socket path the kernel would refuse is refused first, saying why (R129)."""
    deep = tmp_path / ("d" * 120)
    with pytest.raises(OSError, match="longer than"):
        Daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base=deep)


def test_a_daemon_refuses_another_agents_declaration(tmp_path, script, base):
    """A declaration naming another agent is refused, so one copied from another agent's
    home never starts that agent's units under this agent's name (R07)."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    path = declaration_path(home)
    declared = Declaration.model_validate_json(path.read_text())
    path.write_text(declared.model_copy(update={"agent": "Someone@fff000"}).model_dump_json())

    with pytest.raises(DeclarationRefused, match="R07"):
        Daemon(home, base=base)


def test_refusals_name_the_policy(tmp_path, script, base, run_daemon):
    """A refusal names the policy that explains it, over the socket and when the daemon
    will not start (capability_boundaries: a refusal names its policy)."""
    pointer = "macf_tools policy navigate persistent_layer"
    daemon = run_daemon(make_home(tmp_path, [make_unit("worker", script, {})]), base)
    reply = ask(daemon, {"op": "explode"})
    assert not reply["ok"] and pointer in reply["error"]

    unusable = tmp_path / "unusable"
    (unusable / ".maceff").mkdir(parents=True)
    started = subprocess.run([sys.executable, "-m", "macf.pd", str(unusable)],
                             capture_output=True, text=True, timeout=60)
    assert started.returncode == 78
    assert pointer in started.stderr


def test_failures_count_and_clear(make_core, script, tmp_path):
    """A crash counts toward the restart backoff, and a unit that then runs stably for ten
    of its intervals, counted from its start, has the count cleared."""
    core = make_core([make_unit("worker", script, {"crash_once": str(tmp_path / "crashed")})])
    core.boot()
    assert drive(core, lambda: core.failures("worker") == 1)
    assert drive(core, lambda: core.state("worker") == "running")
    assert drive(core, lambda: core.failures("worker") == 0)


def test_shutdown_never_held(make_core, script):
    """The daemon's own shutdown kills a unit that ignores SIGTERM once the grace runs out in
    real time, so it never waits forever. The clock here stands still: a unit's own kill
    timer runs on the core's clock, and only shutdown's real-time fallback can end it."""
    core = make_core([make_unit("worker", script, {"ignore_term": True}, stop_grace_s=0.3)],
                     clock=lambda: 1000.0)
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    pid = core.pid("worker")

    stopping = threading.Thread(target=core.shutdown, args=("the daemon is stopping",), daemon=True)
    stopping.start()
    stopping.join(timeout=10)
    held = stopping.is_alive()
    if held:  # without the fallback: end the unit here, so the test fails without leaving it
        os.killpg(pid, signal.SIGKILL)  # the unit leads its own process group
        stopping.join(timeout=10)
    assert not held, "shutdown kept waiting on a unit that ignored SIGTERM"


def test_already_running_exits_75(tmp_path, script, run_daemon):
    """A second start of the agent's daemon from the command line exits 75, which tells an
    outer tier another daemon holds the slot, and names the policy."""
    xdg = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    try:
        base = xdg / "maceff_pd"
        base.mkdir(mode=0o700)
        home = make_home(tmp_path, [make_unit("worker", script, {})])
        run_daemon(home, base)
        env = {k: v for k, v in os.environ.items() if k != "MACF_EVENTS_LOG_PATH"}
        second = subprocess.run([sys.executable, "-m", "macf.pd", str(home)],
                                capture_output=True, text=True, timeout=60,
                                env={**env, "XDG_RUNTIME_DIR": str(xdg)})
        assert second.returncode == 75
        assert "macf_tools policy navigate persistent_layer" in second.stderr
    finally:
        shutil.rmtree(xdg, ignore_errors=True)


# Restart policy crossed with how a unit exits: every cell, so a branch only a pairing
# reaches cannot sit untested (the cell "always" with a clean exit once did).
RESTART_BY_EXIT = [
    # restart,     exit code, restarts, state it is left in when it does not restart
    ("always",     0,  True,  None),
    ("always",     78, False, "stopped"),
    ("always",     1,  True,  None),
    ("on-failure", 0,  False, "stopped"),
    ("on-failure", 78, False, "stopped"),
    ("on-failure", 1,  True,  None),
    ("never",      0,  False, "stopped"),
    ("never",      78, False, "stopped"),
    ("never",      1,  False, "failed"),
]


@pytest.mark.parametrize("restart, code, restarts, left", RESTART_BY_EXIT)
def test_restart_policy_by_exit(make_core, script, restart, code, restarts, left):
    """A unit that exits on its own is restarted exactly when its policy and its exit code
    together say so: success and failure under "always", failure under "on-failure", and
    never a code that asks not to be restarted."""
    core = make_core([make_unit("worker", script, {"exit_after": 0.2, "code": code}, restart=restart)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first = core.pid("worker")
    assert drive(core, lambda: core.state("worker") != "running" or core.pid("worker") != first)
    came_back = drive(core, lambda: core.pid("worker") not in (None, first), timeout=1.5)
    assert came_back == restarts
    if not restarts:
        assert core.state("worker") == left


def test_quiet_window(script):
    """A session's restart waits for the end of a quiet window its agent declared, whether
    its own policy or an operator asked for it, and its status says until when (R50). The
    window is set ahead of now in the timezone the declaration names, Kathmandu's, whose
    offset no test host is likely to share, so a core that read windows in its host's time
    would look in the wrong hours. The core's wall clock is moved into it and out again."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from macf.pd.interface import Window

    zone = "Asia/Kathmandu"
    ahead = datetime.now(ZoneInfo(zone))
    window = Window(start=(ahead + timedelta(hours=1)).strftime("%H:%M"),
                    end=(ahead + timedelta(hours=3)).strftime("%H:%M"))
    unit = make_unit("worker", script, {"exit_after": 0.3, "code": 1}, restart="always")
    shift = {"s": 0.0}
    core = Core(Declaration(version=1, agent=CARD, units=[unit.model_copy(update={"kind": "session"})],
                            quiet_windows=[window], timezone=zone), CARD,
                wall=lambda: time.time() + shift["s"], backoff_base_s=0.05, backoff_cap_s=0.2)

    def held():
        return next(s.restart_held_until for s in core.statuses() if s.unit == "worker")

    try:
        core.boot()
        assert drive(core, lambda: core.state("worker") == "running")
        first = core.pid("worker")
        assert held() is None
        shift["s"] = 2 * 3600.0   # inside the window
        assert drive(core, lambda: core.state("worker") != "running")
        assert not drive(core, lambda: core.pid("worker") not in (None, first), timeout=1.0)
        assert held() == window.end   # its policy's restart is due, and waits
        core.restart("worker", OPERATOR, "asked during the window", peer=PEER)
        assert not drive(core, lambda: core.pid("worker") not in (None, first), timeout=0.5)
        assert held() == window.end   # so does the one the operator asked for
        shift["s"] = 0.0          # the window has ended
        assert drive(core, lambda: core.pid("worker") not in (None, first), timeout=3.0)
        assert held() is None
    finally:
        core.shutdown("the test is over")


def test_no_own_compaction(make_core, script):
    """The core never compacts a session on its own initiative (R51): a session that keeps
    failing is restarted by its policy, and no act it records is a compaction."""
    unit = make_unit("worker", script, {"exit_after": 0.1, "code": 1}, restart="always")
    core = make_core([unit.model_copy(update={"kind": "session"})])
    core.boot()
    first = core.pid("worker")
    assert drive(core, lambda: core.pid("worker") not in (None, first))
    second = core.pid("worker")
    assert drive(core, lambda: core.pid("worker") not in (None, first, second))
    acts = [d.get("act") for d in events("pd_control", "worker")]
    assert acts and "compact" not in acts


def test_the_record_outlives_a_temp_cleaner(tmp_path, script, base, run_daemon):
    """Without XDG_RUNTIME_DIR the record lives in /tmp, where macOS's tmp_cleaner deletes a
    regular file untouched for three days. A running daemon refreshes its record, and writes
    it again if a cleaner already took it, so pd status keeps believing it."""
    home = make_home(tmp_path, [make_unit("worker", script, {})])
    daemon = run_daemon(home, base, record_refresh_s=0.1)
    old = time.time() - 4 * 86400
    os.utime(daemon.record_path, (old, old))
    assert wait_for(lambda: daemon.record_path.stat().st_mtime > old + 86400)
    daemon.record_path.unlink()
    assert wait_for(daemon.record_path.exists)
    assert json.loads(daemon.record_path.read_text())["pid"] == os.getpid()


def test_a_stop_never_signals_a_process_that_took_an_adopted_units_pid(make_core, script):
    """An adopted unit is not this daemon's child, so its pid can end and be reused between
    passes without the kernel telling the daemon. A stop probes the pid and start time first
    (MIS-0002-R15 (readout_MUST_probe_liveness)), and signals nothing that is no longer the
    process it adopted."""
    from macf.pd.core import _Adopted
    core = make_core([make_unit("worker", script, {})])
    stranger = subprocess.Popen(["/bin/sleep", "30"], start_new_session=True)
    try:
        r = core._units["worker"]
        recorded = "a start that is not this process's"
        r.proc, r.pid, r.proc_start = _Adopted(stranger.pid, recorded, core._probe), stranger.pid, recorded
        r.state = "running"
        core.stop("worker", OPERATOR, "test stop", peer=PEER)
        time.sleep(0.3)
        assert stranger.poll() is None, "the stop signalled a process that only took the adopted unit's pid"
    finally:
        stranger.kill()
        stranger.wait()


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _child_pid(path):
    assert wait_for(path.exists, timeout=5.0), "the unit's child never wrote its pid"
    return int(path.read_text())


def test_a_stop_reaches_the_units_whole_group(tmp_path, script, make_core):
    """A stop reaches every process the unit started (persistent_layer 10.2): a child in
    the unit's group that ignores SIGTERM outlives its leader's exit, and is killed at the
    stop's deadline rather than left running."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker)}, stop_grace_s=1.0)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    child = _child_pid(marker)
    core.stop("worker", OPERATOR, "test stop", peer=PEER)
    # The unit reads stopped only once its whole group has ended: at the first moment it
    # does, the child is already gone, and the reason says the group was killed.
    assert drive(core, lambda: core.state("worker") == "stopped", timeout=5.0)
    assert not _alive(child), f"the unit read stopped while its child {child} still ran"
    last = events("pd_unit_state", "worker")[-1]
    assert last["state"] == "stopped" and "killed at the stop's deadline" in last["reason"], last


def test_a_member_forked_after_the_leader_ended_is_reached_too(tmp_path, script, make_core):
    """A recorded member that forks after the leader's reap, then exits at once, as a wrapper
    running `cmd &` does, leaves only a process the first listing never saw. The group is
    listed again before the remnant is given up, so the newcomer is recorded and killed, and
    the unit reads stopped only once it is gone."""
    marker, grandchild, go = tmp_path / "child.pid", tmp_path / "grandchild.pid", tmp_path / "go"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker),
                                                   "child_forks_after": str(grandchild),
                                                   "child_forks_then_exits_on": str(go)},
                                stop_grace_s=1.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    child = _child_pid(marker)
    core.stop("worker", OPERATOR, "test stop", peer=PEER)
    assert drive(core, lambda: core._units["worker"].remnant is not None, timeout=3.0)
    # Between two passes: the recorded child forks the late process and exits.
    go.touch()
    late = _child_pid(grandchild)
    assert wait_for(lambda: not _alive(child), timeout=5.0)
    assert drive(core, lambda: core.state("worker") == "stopped", timeout=6.0)
    assert not _alive(child) and not _alive(late), f"child {_alive(child)}, late {_alive(late)}"


def test_a_restart_waits_for_the_old_group(tmp_path, script, make_core):
    """A restart starts the new incarnation only once the old one's group is gone, so two
    copies never run side by side, as systemd waits for a unit's cgroup to empty."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker)}, stop_grace_s=0.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first, child = core.pid("worker"), _child_pid(marker)
    marker.unlink()
    core.restart("worker", OPERATOR, "test restart", peer=PEER)
    seen_alive_with_new = []

    def new_incarnation():
        pid = core.pid("worker")
        if pid not in (None, first) and _alive(child):
            seen_alive_with_new.append(pid)
        return pid not in (None, first) and core.state("worker") == "running"
    assert drive(core, new_incarnation, timeout=8.0)
    assert not seen_alive_with_new, "the new incarnation started while the old group's child still ran"
    assert not _alive(child)


def test_a_second_stop_during_the_remnant_wait_does_not_read_stopped_early(tmp_path, script, make_core):
    """A stop asked again while the first one's remnant is still running records nothing new:
    the unit reads stopped once, when its group has ended."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker)}, stop_grace_s=1.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    child = _child_pid(marker)
    core.stop("worker", OPERATOR, "first stop", peer=PEER)
    assert drive(core, lambda: core._units["worker"].remnant is not None, timeout=3.0)
    core.stop("worker", OPERATOR, "second stop", peer=PEER)
    assert not (core.state("worker") == "stopped" and _alive(child)), "stopped while the group still ran"
    assert drive(core, lambda: core.state("worker") == "stopped", timeout=6.0)
    assert not _alive(child)
    stopped = [d for d in events("pd_unit_state", "worker") if d["state"] == "stopped"]
    assert len(stopped) == 1, [d["reason"] for d in stopped]


def test_a_fork_then_exit_as_the_leader_ends_is_reached(tmp_path, script, make_core):
    """A child that forks a replacement and exits the moment its leader ends, as a wrapper or a
    self-relaunching worker does, can race the first listing of the group: on Linux it is read
    from /proc entry by entry, and the child may be listed, then gone, before the replacement
    appears. The group is listed again when the first listing is empty. The race is not
    deterministic, so several stops are run; any one that leaves the replacement fails."""
    for i in range(6):
        marker, late_file = tmp_path / f"child{i}.pid", tmp_path / f"late{i}.pid"
        core = make_core([make_unit(f"worker{i}", script, {"child_ignores_term": str(marker),
                                                           "child_forks_after": str(late_file),
                                                           "child_forks_then_exits_on": "now"},
                                    stop_grace_s=0.5)])
        core.boot()
        assert drive(core, lambda: core.state(f"worker{i}") == "running")
        _child_pid(marker)
        core.stop(f"worker{i}", OPERATOR, "test stop", peer=PEER)
        late = _child_pid(late_file)
        assert drive(core, lambda: core.state(f"worker{i}") == "stopped", timeout=6.0)
        assert wait_for(lambda: not _alive(late), timeout=2.0), f"stop {i}: the replacement {late} outlived the stop"


def test_a_leader_that_crashes_takes_its_group_with_it(tmp_path, script, make_core):
    """A leader that exits on its own leaves no member of its group running: the group is
    sent SIGTERM, then SIGKILL at the unit's grace, as systemd ends a unit's cgroup and
    launchd a job's process group. The restart waits for the group, so two copies of the
    unit never run side by side."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker),
                                                   "exit_after": 0.5, "code": 1},
                                stop_grace_s=0.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first, child = core.pid("worker"), _child_pid(marker)
    marker.unlink()
    seen_alive_with_new = []

    def restarted():
        pid = core.pid("worker")
        if pid not in (None, first) and _alive(child):
            seen_alive_with_new.append(pid)
        return pid not in (None, first)
    assert drive(core, restarted, timeout=8.0)
    assert not seen_alive_with_new, "the unit restarted while its crashed leader's child still ran"
    assert not _alive(child), f"the crashed leader's child {child} outlived it"
    failed = [d for d in events("pd_unit_state", "worker") if d["state"] == "failed"]
    assert failed and "sent SIGTERM" in failed[0]["reason"], failed


def test_a_leader_that_ends_cleanly_reads_stopped_once_its_group_has(tmp_path, script, make_core):
    """A leader that exits with a success code and leaves a member running reads stopped
    only once that member has ended, as after a stop this core sent."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker),
                                                   "exit_after": 0.5, "code": 0},
                                restart="on-failure", stop_grace_s=0.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    child = _child_pid(marker)
    assert drive(core, lambda: core.state("worker") == "stopped", timeout=6.0)
    assert not _alive(child), f"the unit read stopped while its child {child} still ran"
    last = events("pd_unit_state", "worker")[-1]
    assert last["state"] == "stopped" and "killed at the stop's deadline" in last["reason"], last


def test_an_always_unit_that_ends_cleanly_restarts_after_its_group(tmp_path, script, make_core):
    """Under restart=always a clean exit restarts the unit, and with a member still running
    the start waits for that member's end rather than being lost while the stop is pending."""
    marker = tmp_path / "child.pid"
    core = make_core([make_unit("worker", script, {"child_ignores_term": str(marker),
                                                   "exit_after": 0.5, "code": 0},
                                restart="always", stop_grace_s=0.5)])
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    first, child = core.pid("worker"), _child_pid(marker)
    marker.unlink()
    assert drive(core, lambda: core.pid("worker") not in (None, first), timeout=8.0), \
        "a clean exit under restart=always was never restarted"
    assert not _alive(child)


def test_an_optional_unit_that_hangs_at_start_delays_no_other(tmp_path, script, make_core):
    """MIS-0002-R58 (optional_unit_MUST-NOT_delay_others): an optional unit that was started
    and hangs, alive as a process but never live, does not hold up the start of another
    unit, nor that unit's restart after a crash. The other unit runs within its own time
    while the hung one still reads starting."""
    hung = make_unit("indexer", script, {"alive_for": 0}, interval=10.0)
    hung = hung.model_copy(update={"optional": True})
    worker = make_unit("worker", script, {"crash_once": str(tmp_path / "crashed")})
    core = make_core([hung, worker])
    t0 = time.monotonic()
    core.start("indexer", OPERATOR, "the optional unit, started first", peer=PEER)
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running", timeout=3.0), \
        "the worker never ran while the optional unit hung"
    assert time.monotonic() - t0 < 3.0
    assert core.state("indexer") == "starting", "the optional unit was meant to still hang"
    starts = [d for d in events("pd_unit_state", "worker") if d["state"] == "starting"]
    assert len(starts) >= 2, "the worker's crash and restart were meant to happen meanwhile"


def test_a_unit_past_its_memory_limit_is_recorded_once_per_crossing(tmp_path, script, make_core, monkeypatch):
    """MIS-0002-R60: a running unit read above its declared limit is recorded once, with a
    notice owed, and recorded once more when it is read back below; readings that don't
    cross record nothing. The limit is not enforced: the unit keeps running."""
    import macf.pd.core as core_module
    readings = iter([10.0, 80.0, 90.0, 20.0, 30.0])           # limit is 64 MB
    monkeypatch.setattr(core_module, "tree_rss_mb", lambda pid: next(readings, 30.0))
    core = make_core([make_unit("worker", script, {})], memory_check_s=0.0)
    owed = []
    core.on_notice = lambda source, nid: owed.append((source, nid))
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    for _ in range(6):
        core.tick()
    over = events("pd_unit_over_limit", "worker")
    under = events("pd_unit_back_under_limit", "worker")
    assert [(d["used_mb"], d["limit_mb"]) for d in over] == [(80.0, 64)]
    assert [d["used_mb"] for d in under] == [20.0]
    assert [s for s, _ in owed] == ["pd_limit_exceeded"]
    assert core.state("worker") == "running"


def test_memory_is_read_over_the_whole_process_tree():
    """A child in a session of its own, as a session unit's claude under its tmux server, is
    still counted: the tree, not the process group."""
    import macf.pd.core as core_module
    child = subprocess.Popen([sys.executable, "-c", "import time; x = bytearray(60 * 1024 * 1024); time.sleep(30)"],
                             start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (core_module.tree_rss_mb(child.pid) or 0) < 50:
            time.sleep(0.1)
        assert core_module.tree_rss_mb(child.pid) >= 50
        alone = core_module.tree_rss_mb(child.pid)
        statm = Path("/proc/self/statm")
        if statm.exists():                  # this process's own resident memory, in MB
            own = int(statm.read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2 ** 20
            assert core_module.tree_rss_mb(os.getpid()) >= own + 0.9 * alone, "the child is under this test's tree"
        assert core_module.tree_rss_mb(2 ** 22 + 12345) is None
    finally:
        child.kill()
        child.wait()


def test_a_new_incarnation_over_its_limit_is_recorded_again(tmp_path, script, make_core, monkeypatch):
    """CTB's probe on #660: the over-limit state belongs to an incarnation, not the unit. A
    unit over its limit that restarts and goes over again is recorded and noticed again,
    naming the new pid."""
    import macf.pd.core as core_module
    monkeypatch.setattr(core_module, "tree_rss_mb", lambda pid: 80.0)   # limit is 64 MB
    core = make_core([make_unit("worker", script, {})], memory_check_s=0.0)
    owed = []
    core.on_notice = lambda source, nid: owed.append(source)
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    core.tick()
    first = core.pid("worker")
    core.restart("worker", OPERATOR, "a new setting", peer=PEER)
    assert drive(core, lambda: core.state("worker") == "running" and core.pid("worker") not in (None, first),
                 timeout=8.0)
    core.tick()
    over = events("pd_unit_over_limit", "worker")
    assert [d["pid"] for d in over] == [first, core.pid("worker")]
    assert owed == ["pd_limit_exceeded", "pd_limit_exceeded"]
