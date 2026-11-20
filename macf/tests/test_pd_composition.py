"""The base and the Agent Daemon (MIS-0002 6.1 and 6.2; MIS-0007 R74).

A primal daemon builds the Agent Daemon's components only where its declaration adds them, and a
system or fleet daemon adds none, so it runs the base alone: its units, its log, its control socket,
its scheduler and its broker, with no notice path, duties, login check, channel or mail."""
from __future__ import annotations

import json
import sys

import pytest

from macf.agent_events_log import read_events
from macf.pd import core as pd_core
from macf.pd.daemon import Daemon
from macf.pd.interface import Declaration, declaration_path

from test_primal_daemon import (CARD, ask, base, make_home, make_unit, run_daemon,  # noqa: F401 - fixtures
                                script)

AGENT_PARTS = ("notifier", "duties", "login", "dark_channel", "unread_mail", "receiver")


def declare(home, kind, units=()):
    """Rewrite the home's declaration as a daemon of ``kind``, with ``units``."""
    declaration_path(home).write_text(
        Declaration(version=1, agent=CARD, kind=kind, units=list(units)).model_dump_json())
    return home


def test_each_agent_component_is_built_only_where_its_declaration_adds_it(tmp_path, base,
                                                                         isolated_events_log):
    """MIS-0002-R183 (component_MUST_be_added_by_declaration): an agent's declaration adds the
    notice path, duties and the login check, and its daemon binds the MacEff Notification Channel's socket;
    the same home declared as a system daemon builds none of them and binds no channel socket."""
    agent = Daemon(make_home(tmp_path / "a", []), base=base)
    assert agent.agent
    assert all(getattr(agent, p) is not None for p in ("notifier", "duties", "login"))
    assert agent.core.on_notice == agent.notifier.raise_notice
    system = Daemon(declare(make_home(tmp_path / "s", []), "system"), base=base / "s")
    assert not system.agent
    assert all(getattr(system, p) is None for p in AGENT_PARTS)
    assert system.core.on_notice is None and system.scheduler.on_notice is None


def test_a_declaration_written_without_kind_stays_an_agents(tmp_path, base, isolated_events_log):
    """Every deployed declaration so far was written without ``kind``; each must stay an agent's,
    with its notice path, duties and login check. The raw file is written by hand, since a model
    dump spells out the default and would hide a change to it (the host-side maintainer's review
    on #947)."""
    home = make_home(tmp_path, [])
    raw = json.loads(declaration_path(home).read_text())
    raw.pop("kind", None)
    declaration_path(home).write_text(json.dumps(raw))
    assert "kind" not in declaration_path(home).read_text()
    daemon = Daemon(home, base=base)
    assert daemon.agent
    assert all(getattr(daemon, p) is not None for p in ("notifier", "duties", "login"))


@pytest.mark.parametrize("kind", ["system", "fleet"])
def test_a_system_or_fleet_declaration_builds_no_agent_component(kind, tmp_path, base, run_daemon,
                                                                 isolated_events_log):
    """MIS-0007 R74 (association_MUST_add_no_agent_component): a running system or fleet daemon
    has bound its control socket and never the channel's, and holds no agent component."""
    daemon = run_daemon(declare(make_home(tmp_path, []), kind), base)
    assert daemon.control_path.exists()
    assert not daemon.channel_path.exists(), "a system or fleet daemon bound the MacEff Notification Channel's socket"
    assert daemon._channel_listener is None
    assert all(getattr(daemon, p) is None for p in AGENT_PARTS)


def test_a_declaration_that_adds_no_component_runs_the_base_alone(tmp_path, base, script, run_daemon,
                                                                  isolated_events_log):
    """MIS-0002-R184 (base_MUST_stand_alone): with no component, the daemon still starts and
    supervises its declared unit, answers its control socket, and records the unit's liveness."""
    import time
    home = declare(make_home(tmp_path, []), "system", [make_unit("worker", script, {})])
    daemon = run_daemon(home, base)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if {u["unit"]: u["state"] for u in ask(daemon, {"op": "status"})["units"]}.get("worker") == "running":
            break
        time.sleep(0.05)
    else:
        pytest.fail("the base never ran its declared unit")
    alive = [e for e in read_events(reverse=False, scope="all", only=("pd_unit_alive",))
             if (e.get("data") or {}).get("unit") == "worker"]
    assert alive, "the base recorded no liveness for its unit"


def test_a_limit_crossed_without_notices_is_recorded(tmp_path, base, script, monkeypatch,
                                                     isolated_events_log):
    """MIS-0002-R60 (pd_MUST_notice_limit_exceeded), its base half: where no notices component is
    present, a unit read past its declared limit is recorded, and no notice is owed anyone."""
    used = [10.0]                                                   # the unit's limit is 64 MB
    monkeypatch.setattr(pd_core, "tree_rss_mb", lambda pid: used[0])
    home = declare(make_home(tmp_path, []), "system", [make_unit("worker", script, {})])
    daemon = Daemon(home, base=base, memory_check_s=0.0)
    core = daemon.core
    core.boot()
    try:
        from test_primal_daemon import drive
        assert drive(core, lambda: core.state("worker") == "running")
        used[0] = 80.0
        core.tick()
        [over] = [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_OVER_LIMIT,))]
        assert (over["unit"], over["used_mb"], over["limit_mb"]) == ("worker", 80.0, 64)
        assert daemon.notifier is None and core.on_notice is None
    finally:
        core.shutdown("the test is over")


def test_a_start_that_finds_its_daemon_running_holds_before_it_exits(tmp_path, monkeypatch):
    """MIS-0002-R185 (refused_start_MUST_hold_before_exit): a start that finds its principal's
    daemon already running holds before it exits 75, as a refused start does before 78, so an
    outer tier that restarts on exit doesn't spin."""
    import macf.pd.__main__ as main_module
    from macf.pd.daemon import AlreadyRunning

    class Running:
        def __init__(self, home):
            raise AlreadyRunning("another primal daemon of this agent is alive")

    monkeypatch.setattr(main_module, "Daemon", Running)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    monkeypatch.delenv("MACF_PD_REFUSED_HOLD_S", raising=False)
    held = []
    assert main_module.main([str(tmp_path)], hold=held.append) == 75
    assert held == [main_module.REFUSED_HOLD_S]
