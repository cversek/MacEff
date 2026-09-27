"""A hook sends what changed since it last spoke, and the full block when a
reader could not have the old one (#407)."""

import json
from unittest.mock import patch

import pytest

from macf.agent_events_log import append_event
from macf.hooks.emission import ADDED, CHANGED, REMOVED, diff_body

from test_handle_user_prompt_submit import mock_dependencies  # noqa: F401  (fixture)


@pytest.fixture
def quiet_live_lines():
    """The block also carries a roles line and a budget line read from live
    stores; pin both so two runs differ only in what a test changes."""
    with patch("macf.budget.hook_lines", return_value=""), \
         patch("macf.roles.hooks.prompt_line", return_value=""):
        yield


def _prompt(prompt="do the thing"):
    from macf.hooks.handle_user_prompt_submit import run
    out = run(json.dumps({"session_id": "test-session-123", "prompt": prompt}))
    return out["hookSpecificOutput"]["additionalContext"], out["systemMessage"]


def _lines(ctx):
    return [l for l in ctx.splitlines() if l.strip() and "system-reminder>" not in l]


def test_an_unchanged_prompt_block_is_the_header_alone(mock_dependencies, quiet_live_lines):
    """The acceptance case: nothing changed but the clock."""
    first, _ = _prompt()
    second, _ = _prompt()
    assert "Day: Wednesday" in first, "the first emission of a session is the full block"
    body = _lines(second)
    assert len(body) == 1, body
    assert "DEV_DRV Started" in body[0] and "CL50" in body[0] and "s_test/c_1" in body[0]
    assert "unchanged" in body[0]


def test_a_changed_line_is_sent_and_nothing_else(mock_dependencies, quiet_live_lines):
    _prompt()
    mock_dependencies["temporal"].return_value = {
        "timestamp_formatted": "2025-10-08 06:00:00 AM EDT",
        "day_of_week": "Wednesday",
        "time_of_day": "Morning",
    }
    body = _lines(_prompt()[0])
    assert body[1:] == [f"{CHANGED} Time of Day: Morning"]


def test_the_first_emission_after_a_compaction_is_full(mock_dependencies, quiet_live_lines):
    """Recovery must see everything: the agent no longer holds the old block."""
    _prompt()
    append_event("compaction_detected", {"session_id": "test-session-123"})
    assert "Day: Wednesday" in _prompt()[0]


@pytest.mark.parametrize("env", [{"MACF_HOOK_OUTPUT": "full"}, {"MACF_HOOK_FULL_EVERY_MINS": "0"}])
def test_full_on_request_and_when_the_last_block_is_stale(mock_dependencies, quiet_live_lines,
                                                         monkeypatch, env):
    _prompt()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert "Day: Wednesday" in _prompt()[0]


def test_colour_reaches_the_operator_only(mock_dependencies, quiet_live_lines, monkeypatch):
    """The systemMessage never reaches the model; additionalContext does."""
    _prompt()
    mock_dependencies["temporal"].return_value = {
        "timestamp_formatted": "x", "day_of_week": "Thursday", "time_of_day": "y"}
    agent, operator = _prompt()
    assert "\033[" not in agent
    assert "\033[" in operator
    monkeypatch.setenv("NO_COLOR", "1")
    mock_dependencies["temporal"].return_value["day_of_week"] = "Friday"
    assert "\033[" not in _prompt()[1]


def test_diff_marks_changed_added_and_removed():
    entries, unchanged = diff_body(
        ["Day: Wed", "Model: a", "old nag"],
        ["Day: Thu", "Model: a", "new nag"],
    )
    assert unchanged == 1
    assert entries == [(CHANGED, "Day: Thu"), (ADDED, "new nag"), (REMOVED, "old nag")]


def test_another_sessions_emission_is_not_this_ones(mock_dependencies, quiet_live_lines):
    """A second client under the same agent home writes to the same log."""
    append_event("hook_emission", {"hook": "user_prompt_submit", "session_id": "other-session",
                                   "body": ["Day: Wednesday"], "full": True})
    assert "Day: Wednesday" in _prompt()[0]


@pytest.fixture
def quiet_stop():
    """Stop in MANUAL_MODE with the live focus and burn gates pinned open."""
    with patch("macf.hooks.handle_stop.get_current_session_id", return_value="test-session-123"), \
         patch("macf.hooks.handle_stop.complete_dev_drv", return_value=(True, 45)), \
         patch("macf.hooks.handle_stop.get_dev_drv_stats",
               return_value={"count": 5, "total_duration": 3600, "prompt_uuid": "abc12345"}), \
         patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(False, "test")), \
         patch("macf.roles.hooks.focus_gate", return_value={"text": "", "block": False, "unserviced": []}), \
         patch("macf.budget.burn_gate", return_value={"block": False, "text": ""}):
        yield


def test_the_stop_summary_is_diffed_for_the_operator(quiet_stop):
    from macf.hooks.handle_stop import run
    first = run("")["systemMessage"]
    second = run("")["systemMessage"]
    assert "Development Drive Stats:" in first
    assert "Development Drive Stats:" not in second
    assert "DEV_DRV Complete" in second and "drive 45s" in second and "unchanged" in second


def test_a_gate_reason_is_never_diffed(quiet_stop):
    """A blocking reason is the gate itself; it must arrive whole every time."""
    from macf.hooks.handle_stop import run
    from macf.task.scope import set_scope
    from macf.task.scope_gate_failsafe import reset
    reset()
    set_scope(["4242"])
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(True, "test")):
        first, second = run(""), run("")
    reset()
    assert first.get("decision") == second.get("decision") == "block"
    # Only the failsafe counter may differ between two blocked stops.
    def without_counter(reason):
        return [l for l in reason.splitlines() if "counter" not in l.lower()]
    assert "4242" in second["reason"]
    assert without_counter(first["reason"]) == without_counter(second["reason"])


def test_each_hook_diffs_against_its_own_last_block(mock_dependencies, quiet_live_lines, quiet_stop):
    """A session alternates prompt and stop; neither may diff against the other."""
    from macf.hooks.handle_stop import run as stop
    _prompt()
    assert "Development Drive Stats:" in stop("")["systemMessage"]
    assert "Day: Wednesday" not in _prompt()[0]


# ---- the week's usage rides in the one-line header, like the clock ------------------------

def _week(pct):
    """A budget sample carrying the all-models weekly limit."""
    append_event("budget_sampled", {"source": "test", "limits": [
        {"kind": "weekly_all", "scope": None, "percent": float(pct), "severity": "normal", "resets_at": None}]})


def test_the_stop_line_carries_the_week_after_the_drive_length(quiet_stop):
    from macf.hooks.handle_stop import run
    _week(42)
    assert "- This Drive: 45s\n- Weekly usage: 42%" in run("")["systemMessage"]
    _week(43)
    second = run("")["systemMessage"]
    assert "drive 45s | wk 43%" in second and "Weekly usage" not in second   # never a diff line


def test_the_prompt_line_ends_with_the_week(mock_dependencies, quiet_live_lines):
    _week(42)
    assert "Weekly usage: 42%" in _prompt()[0]
    _week(43)
    body = _lines(_prompt()[0])
    assert len(body) == 1 and "| wk 43% ·" in body[0], body

