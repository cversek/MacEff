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


# ── Phase 2: plan and threshold lines ────────────────────────────────────────

@pytest.fixture
def opus(monkeypatch):
    monkeypatch.setattr("macf.utils.environment.current_model",
                        lambda session_id=None: {"id": "claude-opus-5-5", "display": "Opus 5.5", "source": "transcript"})


def test_band_line_shows_once_per_band(log, monkeypatch, opus):
    """A limit entering a band gets one line; the next prompt in the same band gets none; the next band gets one."""
    clock = {"t": T0}
    monkeypatch.setattr(budget.time, "time", lambda: clock["t"])
    budget.sample(fetch=lambda: reply_at(52, 10, 1), fresh=True)
    first = budget.prompt_notice()
    assert first and "session 52%" in first and "≥50%" in first
    assert budget.prompt_notice() is None
    clock["t"] += 600
    budget.sample(fetch=lambda: reply_at(77, 10, 1), fresh=True)
    assert "≥75%" in budget.prompt_notice()


def test_no_credential_is_read_where_nobody_asked(log, monkeypatch):
    """An installation with no sample in the last week never auto-samples: the hook reads no credential."""
    monkeypatch.setattr(budget, "read_token", lambda: pytest.fail("credential read without a prior sample"))
    monkeypatch.setattr(budget.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call without a prior sample"))
    assert budget.maybe_autosample(now=T0) is None
    assert budget.hook_lines("prompt", now=T0) is None


def test_autosample_waits_for_its_interval(log, monkeypatch, opus):
    clock = {"t": T0}
    monkeypatch.setattr(budget.time, "time", lambda: clock["t"])
    calls = []
    monkeypatch.setattr(budget, "fetch_reply", lambda **kw: calls.append(1) or REPLY)
    budget.sample(fetch=lambda: REPLY, fresh=True)
    clock["t"] += 120
    assert budget.maybe_autosample() is None and not calls
    clock["t"] += 600
    assert budget.maybe_autosample() is not None and len(calls) == 1


def test_wall_warning_once_per_window(log, monkeypatch, opus):
    """At the wall threshold the 5-hour window warns once, naming the remedy; a new window may warn again."""
    monkeypatch.setattr(budget.time, "time", lambda: T0)
    budget.sample(fetch=lambda: reply_at(93, 10, 1), fresh=True)
    w = budget.wall_warning()
    assert w and "93%" in w and "task note or checkpoint" in w
    assert budget.wall_warning() is None
    r = reply_at(95, 10, 1); r["limits"][0]["resets_at"] = "2026-09-23T22:49:00-04:00"
    budget.sample(fetch=lambda: r, fresh=True)
    assert budget.wall_warning() is not None


def test_burn_pace_line_moves_only_past_a_point(log, monkeypatch, opus):
    clock = {"t": T0}
    monkeypatch.setattr(budget.time, "time", lambda: clock["t"])
    budget.set_mode("burn", target=95, scope="week", by="2026-09-23T15:59:00-04:00")
    budget.sample(fetch=lambda: reply_at(1, 40, 1), fresh=True)
    assert "burn week: needs" in budget.prompt_notice()
    assert budget.prompt_notice() is None


def test_hook_lines_are_a_guard(log, monkeypatch):
    """Anything going wrong inside the budget code yields no line, never an exception in the hook."""
    monkeypatch.setattr(budget, "maybe_autosample", lambda now=None: 1 / 0)
    assert budget.hook_lines("prompt") is None and budget.hook_lines("wall") is None


def test_plan_lists_scoped_work_first_with_clean_subjects(log, monkeypatch, opus):
    from types import SimpleNamespace as NS
    tasks = [NS(id="60", status="in_progress", task_type="MISSION", subject="\x1b[2m #60\x1b[22m 🗺️ MISSION: Old"),
             NS(id="272", status="in_progress", task_type="PHASE", subject="#272 [^#270] 📋 Phase 2: plan"),
             NS(id="5", status="completed", task_type="PHASE", subject="done")]
    monkeypatch.setattr("macf.task.reader.TaskReader.read_all_tasks", lambda self: tasks)
    monkeypatch.setattr("macf.task.scope.get_scope_state", lambda: {"272": "active"})
    monkeypatch.setattr(budget.time, "time", lambda: T0)
    budget.sample(fetch=lambda: REPLY, fresh=True)
    work = budget.plan()["work"]
    assert [w["id"] for w in work] == ["272", "60"] and work[0]["scoped"]
    assert work[1]["subject"] == "🗺️ MISSION: Old"


# ── Phase 3: the burn gate ───────────────────────────────────────────────────

WORK = [{"id": "272", "type": "PHASE", "status": "in_progress", "scoped": True, "subject": "Phase 2: plan"}]


@pytest.fixture
def burning(log, monkeypatch, opus):
    """Burn to 95% of the week by the week's reset, week at 40%, open work present, clock at T0."""
    monkeypatch.setattr(budget.time, "time", lambda: T0)
    monkeypatch.setattr(budget, "open_work", lambda: list(WORK))
    budget.sample(fetch=lambda: reply_at(10, 40, 1), fresh=True)
    budget.set_mode("burn", target=95, scope="week")
    return monkeypatch


def test_burn_gate_holds_only_when_every_condition_holds(burning):
    g = budget.burn_gate(auto_mode=True)
    assert g["block"] and "Burn mode: week at 40% of a 95% target" in g["text"] and "#272" in g["text"]
    assert "budget mode set normal" in g["text"]
    assert not budget.burn_gate(auto_mode=False)["block"]                      # MANUAL_MODE never holds


def test_burn_gate_releases_on_target_deadline_no_work_or_normal(burning):
    burning.setattr(budget, "open_work", lambda: [])
    assert not budget.burn_gate(True)["block"]                                   # nothing worth spending it on
    burning.setattr(budget, "open_work", lambda: list(WORK))
    budget.set_mode("burn", target=95, scope="week", by="2026-09-01T00:00:00-04:00")
    assert not budget.burn_gate(True)["block"]                                   # deadline passed
    budget.set_mode("burn", target=35, scope="week")
    assert not budget.burn_gate(True)["block"]                                   # target already reached
    budget.set_mode("normal")
    assert not budget.burn_gate(True)["block"]                                   # the operator's escape


def _stop(auto):
    from unittest.mock import patch
    from macf.hooks.handle_stop import run
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(auto, "test")):
        return run(json.dumps({"stop_reason": "end_turn", "session_id": "test-sess"}))


@pytest.fixture
def stop_env(burning, tmp_path):
    burning.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    from macf.task.scope_gate_failsafe import reset
    reset()
    yield
    reset()


def test_stop_hook_holds_in_burn_and_fails_open_with_the_shared_failsafe(stop_env):
    from macf.task.scope_gate_failsafe import COUNT_INIT
    assert _stop(False).get("decision") != "block"
    results = [_stop(True) for _ in range(COUNT_INIT)]
    assert all(r.get("decision") == "block" and "Burn mode" in r["reason"] for r in results[:-1])
    assert all("idle-stop counter" in r["reason"] for r in results[:-1])
    assert results[-1].get("decision") != "block" and "fail-open" in results[-1].get("systemMessage", "")


def test_stop_hook_released_by_mode_normal(stop_env):
    assert _stop(True).get("decision") == "block"
    budget.set_mode("normal")
    assert _stop(True).get("decision") != "block"
