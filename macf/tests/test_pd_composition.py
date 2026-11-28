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
    notice path, duties and the login check, and its daemon binds the MacEff channel's socket;
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
    assert not daemon.channel_path.exists(), "a system or fleet daemon bound the MacEff channel's socket"
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


# ---- the login window comes from the declaration at every site that judges expiry (#1027) -----------

def _with_reports(home, warn_days):
    reports = {"times": ["07:45"], "warn_days": warn_days, "missed": {"kind": "skip"}} if warn_days else None
    declaration_path(home).write_text(Declaration.model_validate(
        {"version": 1, "agent": CARD, "units": [], **({"timezone": "UTC", "reports": reports} if reports else {})}
    ).model_dump_json())
    return home


def test_the_daemons_login_check_judges_by_the_declared_window(tmp_path, base, isolated_events_log):
    """Without this the daemon recorded 'expiring' by the default three days whatever the declaration said, so
    the record and the outside watch disagreed (THM's review of #1058)."""
    from macf.pd.login import EXPIRING_S
    declared = Daemon(_with_reports(make_home(tmp_path / "a", []), 7), base=base)
    assert declared.login.expiring_s == 7 * 86400.0
    default = Daemon(_with_reports(make_home(tmp_path / "b", []), None), base=base / "b")
    assert default.login.expiring_s == EXPIRING_S


def _expiring(hours, ends=4_000_000_000.0):
    return lambda: {"state": "expiring", "refresh_expires_at": ends, "hours_left": hours, "detail": "test"}


def test_the_daemons_login_check_raises_its_warning_to_the_agent(tmp_path, base, isolated_events_log):
    """The login check warns the agent through the daemon's own notifier (#1161). Built without it,
    the feature is silently off in production while every unit test of the check passes (CTB's
    review of #1162)."""
    from macf.pd.login import NOTICE
    daemon = Daemon(make_home(tmp_path, []), base=base)
    daemon.login.assess_now = _expiring(10)
    daemon.login.tick()
    assert [o.source for o in daemon.notifier.owed.values()] == [NOTICE]


def test_the_daemons_login_check_reads_back_its_newest_warning(tmp_path, base, isolated_events_log):
    """A restarted daemon must not warn again for a step it already warned of: it reads its log's
    warnings newest first and takes this agent's newest. Built without the read-back, or reading the
    oldest, it warns the day's step a second time (CTB's review of #1162)."""
    from macf.agent_events_log import append_event
    from macf.pd.login import EVENT_WARNED, NOTICE
    ends = 4_000_000_000.0
    append_event(EVENT_WARNED, {"agent": CARD, "step": 1, "refresh_expires_at": ends})
    append_event(EVENT_WARNED, {"agent": CARD, "step": 2, "refresh_expires_at": ends})
    daemon = Daemon(make_home(tmp_path, []), base=base)
    daemon.login.assess_now = _expiring(10, ends)          # within the last day: step 2 of 3
    daemon.login.tick()
    assert NOTICE not in [o.source for o in daemon.notifier.owed.values()], "step 2 was already warned"
    assert [e["data"]["step"] for e in read_events(reverse=False, scope="all", only=(EVENT_WARNED,))] == [1, 2]


def test_pd_login_judges_by_the_declared_window(tmp_path, monkeypatch, capsys):
    import argparse
    from macf.pd import cli as pd_cli
    from macf.pd import login
    home = _with_reports(make_home(tmp_path, []), 7)
    seen = []
    monkeypatch.setattr(pd_cli, "_this_agent", lambda: (home, CARD))
    monkeypatch.setattr(login, "read_assessment", lambda expiring_s=login.EXPIRING_S, **k: seen.append(expiring_s)
                        or {"state": "ok", "detail": "stood in"})
    assert pd_cli.cmd_pd_login(argparse.Namespace(json=False)) == 0
    assert seen == [7 * 86400.0]
