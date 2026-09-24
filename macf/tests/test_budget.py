"""Tests for macf.budget: the subscription's rate limits as a budget (sample, status, log, mode).

No network: the endpoint reply is a recorded fixture and the credential a fake. The reply deliberately carries
fields outside the limits list, one of them holding the fake token, so the custody test can prove that nothing
but the declared limit fields reaches output or the events log.
"""
import argparse
import io
import json
from contextlib import redirect_stdout

import pytest

from macf import budget
from macf.cli import cmd_budget, cmd_budget_status

FAKE_TOKEN = "sk-ant-oat01-FAKE-TOKEN-MUST-NEVER-APPEAR"
T0 = 1_790_190_000.0  # 2026-09-23 around 14:20 EDT

REPLY = {
    "limits": [
        {"kind": "session", "percent": 15, "severity": "normal", "resets_at": "2026-09-23T17:49:00-04:00", "scope": None},
        {"kind": "weekly_all", "percent": 76, "severity": "normal", "resets_at": "2026-09-23T15:59:00-04:00", "scope": None},
        {"kind": "weekly_scoped", "percent": 80, "severity": "warning", "resets_at": "2026-09-23T15:59:00-04:00",
         "scope": {"model": {"display_name": "Fable", "id": "claude-fable-5-1"}}},
    ],
    "nimbus_quill": {"echo": FAKE_TOKEN, "account": "someone@example.com"},
}


def reply_at(session_pct, week_pct, scoped_pct):
    r = json.loads(json.dumps(REPLY))
    r["limits"][0]["percent"], r["limits"][1]["percent"], r["limits"][2]["percent"] = session_pct, week_pct, scoped_pct
    return r


@pytest.fixture
def log(isolated_events_log):
    return isolated_events_log


def test_bare_budget_output_unchanged(monkeypatch, capsys):
    """`macf_tools budget` with no subcommand prints exactly the context thresholds it always has."""
    for k in ("MACEFF_TOKEN_WARN", "MACEFF_TOKEN_HARD", "MACEFF_BUDGET_MODE", "MACEFF_TOKEN_USED"):
        monkeypatch.delenv(k, raising=False)
    assert cmd_budget(argparse.Namespace()) == 0
    assert json.loads(capsys.readouterr().out) == {"mode": "concise/default", "thresholds": {"warn": 0.85, "hard": 0.95}}


def test_sample_keeps_only_declared_fields_and_never_the_token(log, capsys):
    """A sample stores kind, scope name, percent, severity, reset; the token and the reply's other fields go nowhere."""
    s = budget.sample(fetch=lambda: REPLY, now=T0)
    assert [budget.label(l) for l in s["limits"]] == ["session", "week", "Fable"]
    assert set(s["limits"][2]) == {"kind", "scope", "percent", "severity", "resets_at"}
    text = log.read_text()
    assert "budget_sampled" in text
    for leak in (FAKE_TOKEN, "someone@example.com", "nimbus_quill", "claude-fable-5-1"):
        assert leak not in text


def test_fetch_puts_the_token_only_in_the_request_header(monkeypatch):
    """The token source is called once and its value travels in the Authorization header, not the result."""
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        return Resp(json.dumps(REPLY).encode())

    monkeypatch.setattr(budget.urllib.request, "urlopen", fake_urlopen)
    reply = budget.fetch_reply(token_source=lambda: FAKE_TOKEN)
    assert seen["auth"] == f"Bearer {FAKE_TOKEN}"
    assert FAKE_TOKEN not in json.dumps(budget.parse_limits(reply))


def test_second_fetch_within_the_interval_reuses_the_last_sample(log, monkeypatch):
    """Hooks may call sample often; the endpoint is hit at most once per MIN_FETCH_INTERVAL unless --fresh."""
    clock = {"t": T0}
    monkeypatch.setattr(budget.time, "time", lambda: clock["t"])
    calls = []
    fetch = lambda: calls.append(1) or REPLY
    budget.sample(fetch=fetch)
    clock["t"] = T0 + 60
    assert budget.sample(fetch=fetch)["reused"] and len(calls) == 1
    budget.sample(fetch=fetch, fresh=True)
    clock["t"] = T0 + 60 + budget.MIN_FETCH_INTERVAL + 1
    assert not budget.sample(fetch=fetch)["reused"] and len(calls) == 3


def test_manual_sample_parses_the_pasted_summary(log):
    """With no credential the operator pastes: session, week and a model scope, optional @reset."""
    s = budget.sample(manual="session 24 @18:50 week 3% Fable 4", now=T0)
    by = {budget.label(l): l for l in s["limits"]}
    assert by["session"]["percent"] == 24 and by["session"]["resets_at"]
    assert by["week"]["kind"] == "weekly_all" and by["Fable"]["kind"] == "weekly_scoped"
    with pytest.raises(budget.BudgetError):
        budget.parse_manual("nothing useful")


def test_status_rate_and_projection(log, monkeypatch):
    """Two samples an hour apart in the same window give the burn rate and the projection to the reset."""
    clock = {"t": T0}
    monkeypatch.setattr(budget.time, "time", lambda: clock["t"])  # one clock for budget and the events log
    budget.sample(fetch=lambda: reply_at(10, 70, 74), fresh=True)
    clock["t"] = T0 + 3600
    budget.sample(fetch=lambda: reply_at(20, 72, 78), fresh=True)
    st = budget.status()
    week = next(r for r in st["limits"] if r["label"] == "week")
    assert week["rate_window"] == pytest.approx(2.0)
    assert week["projected_at_reset"] is not None and week["projected_at_reset"] >= 72


def test_burn_mode_reports_the_pace_needed(log, monkeypatch):
    """In burn with a target and a deadline, the scoped limit carries the %/h still needed."""
    monkeypatch.setattr(budget.time, "time", lambda: T0)
    budget.sample(fetch=lambda: reply_at(10, 70, 60), fresh=True)
    budget.set_mode("burn", target=95, scope="Fable", by="2026-09-23T15:59:00-04:00")
    st = budget.status()
    fable = next(r for r in st["limits"] if r["label"] == "Fable")
    assert fable["pace_needed"] > 0 and st["mode"]["mode"] == "burn"
    budget.set_mode("normal")
    assert budget.current_mode()["mode"] == "normal"
    with pytest.raises(budget.BudgetError):
        budget.set_mode("normal", target=50)


def test_status_without_samples_says_what_to_do(log, capsys):
    """No samples is a refusal that names the command, through the CLI's error path."""
    assert cmd_budget_status(argparse.Namespace(json=False, brief=False)) == 1
    assert "budget sample" in capsys.readouterr().err


def test_status_names_the_running_model_and_what_it_spends(log, monkeypatch):
    """Session and week always fill; a per-model weekly cap fills only when it is this model's family."""
    monkeypatch.setattr(budget.time, "time", lambda: T0)
    monkeypatch.setattr("macf.utils.environment.current_model",
                        lambda session_id=None: {"id": "claude-opus-5-5", "display": "Opus 5.5", "source": "transcript"})
    budget.sample(fetch=lambda: REPLY, fresh=True)
    st = budget.status()
    assert st["model"]["display"] == "Opus 5.5"
    spend = {r["label"]: r["spending"] for r in st["limits"]}
    assert spend == {"session": True, "week": True, "Fable": False}
    assert "Opus 5.5" in budget.format_status(st, brief=True) and "(not this model)" in budget.format_status(st)
