"""The primal daemon's core supervising fake units (MIS-0002 step 1).

A fake unit is a small script started as a real child process. It writes its own
liveness to the test's isolated event log, the way a real unit would, and can be told
to exit, fall silent, write liveness that cannot be read, report work in flight, or
report that it waits on a person.
"""
import json
import os
import pwd
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

import macf
from macf.agent_events_log import append_event, get_log_path
from macf.notify.session import proc_start
from macf.pd.core import Core, DeclarationRefused, backoff_s, load_declaration
from macf.pd.interface import UNIT_STATES, Asker, Declaration, Peer, Unit, declaration_path

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
    """Silence from the start, liveness that stops, liveness that cannot be read, and liveness
    in another process's name are four failures, and none of them is alive
    (service_supervision: unknown is not healthy; R15: a pid alone is not the unit)."""
    names = ("silent", "stale", "garbled", "imposter")
    core = make_core([
        make_unit("silent", script, {"alive_for": 0}, restart="never"),
        make_unit("stale", script, {"alive_for": 0.2}, restart="never"),
        make_unit("garbled", script, {"garbage": True}, restart="never"),
        make_unit("imposter", script, {"imposter": True}, restart="never"),
    ])
    core.boot()

    assert drive(core, lambda: all(core.state(u) == "failed" for u in names))
    reasons = {u: events("pd_unit_state", u)[-1]["reason"] for u in names}
    assert "stale" in reasons["stale"] and "running" in states("stale")
    for u in ("silent", "garbled", "imposter"):
        assert "no liveness" in reasons[u] and "running" not in states(u)


def test_no_restart_while_waiting(make_core, script):
    """A unit waiting on a person is reported so, and its silence is not taken for death (R21, R22)."""
    core = make_core([make_unit("worker", script, {"waiting_on": "a permission prompt", "alive_for": 0.2})])
    core.boot()

    assert drive(core, lambda: core.state("worker") == "waiting_on_a_person")
    pid = core.pid("worker")
    assert not drive(core, lambda: core.state("worker") != "waiting_on_a_person", timeout=1.0)
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


def test_backoff_doubles_to_its_cap():
    assert [backoff_s(n, 1.0, 8.0) for n in range(7)] == [0.0, 1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


