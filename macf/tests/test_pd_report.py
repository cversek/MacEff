"""#1027, second slice: each declared report time is a schedule the scheduler already runs, and
``pd report`` prints the login line that wakes the session with it."""
import argparse

import pytest

from macf.pd import interface as pdi

CARD = "TheHarborMaster_ee5cd8"
OTHER = "IraMacEff_ee9a78"
MISSED = {"kind": "run_once_in_window", "window": {"start": "07:00", "end": "11:00"}}


def _declaration(reports=None, schedules=None, session_env=None):
    units = [{"name": "broker", "command": ["python3", "-m", "x"], "account": "a",
              "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 256}]
    if session_env is not None:
        units.append({"name": "session", "kind": "session", "command": ["python3", "-m", "y"], "account": "a",
                      "restart": "always", "liveness_interval_s": 120, "memory_limit_mb": 256,
                      "stop_grace_s": 30, "environment": session_env})
    decl = {"version": 1, "agent": CARD, "units": units, "timezone": "America/New_York",
            "reports": {"times": ["07:45", "19:45"], "missed": MISSED, **(reports or {})}}
    if schedules is not None:
        decl["schedules"] = schedules
    return pdi.Declaration.model_validate(decl)


def _reports_of(decl):
    return {s.name: s for s in decl.schedules if s.name.startswith("report-")}


# ---- the schedules ----------------------------------------------------------

def test_each_report_time_is_a_daily_schedule_into_the_agents_own_session():
    found = _reports_of(_declaration())
    assert sorted(found) == ["report-0745", "report-1945"]
    s = found["report-0745"]
    assert s.cron == "45 7 * * *" and s.target == CARD
    assert s.missed_run.kind == "run_once_in_window" and s.missed_run.window.start == "07:00"
    assert isinstance(s.run, pdi.CommandRun) and s.run.wake_when == "stdout"
    assert s.run.command[0] == "{python}" and s.run.command[-2:] == ["pd", "report"]


def test_a_schedule_the_declaration_names_itself_is_kept_and_not_doubled():
    own = {"name": "report-0745", "cron": "50 7 * * *", "missed_run": MISSED, "target": CARD,
           "run": {"command": ["true"], "wake_when": "exit_code"}, "timeout_s": 30}
    decl = _declaration(schedules=[own])
    names = [s.name for s in decl.schedules]
    assert names.count("report-0745") == 1 and "report-1945" in names
    assert _reports_of(decl)["report-0745"].cron == "50 7 * * *"


def test_a_declaration_read_back_from_its_own_dump_has_each_report_once():
    decl = _declaration()
    again = pdi.Declaration.model_validate(decl.model_dump(mode="json"))
    assert [s.name for s in again.schedules] == [s.name for s in decl.schedules]


def test_the_run_finds_its_home_and_the_login_variables_the_session_declares():
    """On macOS the stored login is found by USER and LOGNAME (#852, #1073)."""
    env = _reports_of(_declaration(session_env={"USER": "cv", "LOGNAME": "cv", "PATH": "/bin"}))[
        "report-1945"].run.environment
    assert env == {"MACEFF_AGENT_HOME_DIR": "{agent_home}", "USER": "cv", "LOGNAME": "cv"}


def test_no_reports_derive_no_schedules():
    decl = pdi.Declaration.model_validate({"version": 1, "agent": CARD, "units": []})
    assert decl.schedules == []


def test_the_daemon_fills_python_with_its_own_interpreter(tmp_path):
    import sys
    from macf.pd.daemon import placeholder_context
    ctx = placeholder_context(tmp_path, CARD, tmp_path / "run")
    assert ctx["python"] == sys.executable
    assert pdi.render("{python}", ctx) == sys.executable
    assert set(ctx) == set(pdi.PLACEHOLDERS)


# ---- pd report --------------------------------------------------------------

@pytest.fixture
def report(monkeypatch, tmp_path, capsys):
    from macf.pd import cli as pd_cli
    from macf.pd import core, login

    def run(verdict, reporter=None):
        decl = _declaration(reports={"reporter": reporter} if reporter else None)
        monkeypatch.setattr(pd_cli, "_this_agent", lambda: (tmp_path, CARD))
        monkeypatch.setattr(core, "load_declaration", lambda home, card: decl)
        monkeypatch.setattr(login, "read_assessment", lambda **kw: verdict)
        code = pd_cli.cmd_pd_report(argparse.Namespace())
        return code, capsys.readouterr().out
    return run


def test_report_says_a_good_login_is_good_until_its_date(report):
    # 2026-12-01 17:00 UTC is 12:00 in New York
    code, out = report({"state": "ok", "refresh_expires_at": 1796144400.0, "detail": "ends in 9.2 days"})
    assert code == 0 and out.strip() == "login: good until Tue 2026-12-01"


@pytest.mark.parametrize("state", ["expiring", "expired"])
def test_report_names_the_remedy_and_how_to_reach_the_session(report, state):
    code, out = report({"state": state, "refresh_expires_at": 1796144400.0, "detail": "the login's refresh grant ends in 20 h"})
    assert code == 0
    assert "run /login" in out and f"macf_tools harness attach --card {CARD}" in out
    assert "the login's refresh grant ends in 20 h" in out


def test_report_says_when_the_login_cannot_be_judged(report):
    code, out = report({"state": "unknown", "refresh_expires_at": None, "detail": "no credential reachable"})
    assert code == 0 and out.strip() == "login: can't be judged: no credential reachable"


def test_another_reporter_carries_the_login_line(report):
    code, out = report({"state": "expired", "refresh_expires_at": 1.0, "detail": "ended"}, reporter=OTHER)
    assert code == 0 and out.strip() == f"login: reported by {OTHER}"
