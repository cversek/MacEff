"""`macf_tools pd unit start|stop|restart NAME --reason TEXT` (cversek/MacEff#1007).

The daemon accepted these acts over its control socket, and nothing on the command line sent one,
so stopping a unit meant a script against the client. The verb says who asks, refuses an unknown
unit by naming the declared ones, and reads the unit's state back from the daemon: success is the
unit in the state the act asks for, never the request having been sent.
"""
import pytest

from macf import cli
from macf.pd import cli as pd_cli
from macf.pd import client
from macf.pd.interface import Response, UnitStatus

CARD = "Tester_abc123"


def status(**states):
    """A status reply: each keyword is a unit and (state, pid)."""
    return Response(ok=True, units=[UnitStatus(unit=n, state=s, pid=p, since=1.0)
                                    for n, (s, p) in states.items()])


@pytest.fixture
def daemon(monkeypatch):
    """A scripted daemon: what it is asked, and the status replies it gives in turn."""
    class Fake:
        asked = []
        statuses = []          # popped in order; the last one repeats

        def ask(self, card, request, **kw):
            assert card == CARD
            self.asked.append(request)
            if request["op"] != "status":
                return Response(ok=True, units=[])
            return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    fake = Fake()
    fake.asked, fake.statuses = [], []
    monkeypatch.setattr(client, "ask", fake.ask)
    monkeypatch.setattr(pd_cli, "_this_agent", lambda: (None, CARD))
    monkeypatch.setattr(pd_cli.time, "sleep", lambda s: None)
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    return fake


def run(*argv):
    """The command's exit status: main ends by exiting, so that is read from the exit."""
    try:
        cli.main(["pd", "unit", *argv])
    except SystemExit as e:
        return e.code or 0
    raise AssertionError("main returned instead of exiting")


def acts(daemon):
    return [r for r in daemon.asked if r["op"] != "status"]


def test_a_stop_is_asked_by_the_operator_outside_a_session_and_read_back(daemon, capsys):
    daemon.statuses = [status(worker=("running", 11)), status(worker=("stopped", None))]
    assert run("stop", "worker", "--reason", "GPU wanted") == 0
    assert acts(daemon) == [{"op": "stop", "unit": "worker", "reason": "GPU wanted",
                             "asked_by": {"kind": "operator"}}]
    assert "worker: stopped" in capsys.readouterr().out


def test_inside_a_session_the_agent_is_the_asker_with_its_card(daemon, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", "4242")
    daemon.statuses = [status(worker=("running", 11)), status(worker=("stopped", None))]
    assert run("stop", "worker", "--reason", "its own call") == 0
    assert acts(daemon)[0]["asked_by"] == {"kind": "agent", "card": CARD}


def test_asked_by_overrides_the_default(daemon, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", "4242")
    daemon.statuses = [status(worker=("running", 11)), status(worker=("stopped", None))]
    assert run("stop", "worker", "--reason", "he said so", "--asked-by", "operator") == 0
    assert acts(daemon)[0]["asked_by"] == {"kind": "operator"}


def test_an_unknown_unit_is_refused_naming_the_declared_ones(daemon, capsys):
    daemon.statuses = [status(worker=("running", 11), search=("running", 12))]
    assert run("stop", "wroker", "--reason", "typo") == 1
    err = capsys.readouterr().err
    assert "no unit 'wroker'" in err and "search, worker" in err
    assert acts(daemon) == []


def test_a_unit_that_does_not_reach_the_state_is_an_error(daemon, capsys):
    """The stop was asked, and the unit still reads running: the verb doesn't say it worked."""
    daemon.statuses = [status(worker=("running", 11))]
    assert run("stop", "worker", "--reason", "x", "--wait", "0") == 1
    assert "read running" in capsys.readouterr().err


def test_a_restart_is_done_only_with_a_new_process(daemon, capsys):
    """The old process may still read running a moment after the act, so the same pid is not a restart."""
    daemon.statuses = [status(worker=("running", 11)), status(worker=("running", 11)),
                       status(worker=("running", 22))]
    assert run("restart", "worker", "--reason", "new config") == 0
    assert "worker: running (pid 22)" in capsys.readouterr().out


def test_a_restart_held_for_a_quiet_window_says_so_and_is_not_an_error(daemon, capsys):
    held = Response(ok=True, units=[UnitStatus(unit="session", state="running", pid=7, since=1.0,
                                               restart_held_until="06:30")])
    daemon.statuses = [held]
    assert run("restart", "session", "--reason", "pick up a change") == 0
    assert "waits for the quiet window that ends at 06:30" in capsys.readouterr().out


def test_a_refusal_from_the_daemon_is_an_error_naming_it(daemon, capsys):
    def refuse(card, request, **kw):
        if request["op"] == "status":
            return status(worker=("running", 11))
        return Response(ok=False, error="a quiet window holds it")
    client.ask = refuse
    try:
        assert run("start", "worker", "--reason", "x") == 1
    finally:
        client.ask = daemon.ask
    assert "refused: a quiet window holds it" in capsys.readouterr().err


def test_a_daemon_that_cannot_be_reached_is_an_error(daemon, monkeypatch, capsys):
    def down(card, request, **kw):
        raise client.DaemonUnavailable("no usable daemon record")
    monkeypatch.setattr(client, "ask", down)
    assert run("stop", "worker", "--reason", "x") == 1
    assert "no usable daemon record" in capsys.readouterr().err


def test_a_reason_is_required(daemon, capsys):
    assert run("stop", "worker") == 2
    assert "--reason" in capsys.readouterr().err
    assert daemon.asked == []
