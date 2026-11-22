"""The agent hears when its previous call ran on the operator's approval at a dialog (#1060, part 2).
Only that exception is said, once, at the next call's start; nothing is recorded for it."""
from macf import permission_watch as pw

SID = "aaaa1111-0000"


def ev(name, t, command, sid=SID, tool="Bash"):
    return {"event": name, "timestamp": t, "data": {"session_id": sid, "tool": tool, "tool_name": tool},
            "hook_input": {"session_id": sid, "tool_name": tool, "tool_input": {"command": command},
                           "cwd": "/w", "permission_mode": "auto"}}


def test_a_previous_call_approved_at_a_dialog_is_said():
    events = [ev("tool_call_started", 100, "git push"), ev("permission_requested", 101, "git push"),
              ev("tool_call_completed", 120, "git push"), ev("tool_call_started", 130, "ls")]
    note = pw.previous_call_note(events, SID)
    assert note and "git push" in note and "approved" in note and "dialog" in note


def test_a_previous_call_with_no_dialog_says_nothing():
    events = [ev("tool_call_started", 100, "git status"), ev("tool_call_completed", 101, "git status"),
              ev("tool_call_started", 130, "ls")]
    assert pw.previous_call_note(events, SID) is None


def test_the_approval_is_said_once_at_the_next_call_only():
    events = [ev("tool_call_started", 100, "git push"), ev("permission_requested", 101, "git push"),
              ev("tool_call_completed", 120, "git push"), ev("tool_call_started", 130, "ls"),
              ev("tool_call_completed", 131, "ls"), ev("tool_call_started", 140, "pwd")]
    assert pw.previous_call_note(events, SID) is None


def test_another_sessions_approval_is_not_said_to_this_one():
    other = "bbbb2222-0000"
    events = [ev("tool_call_started", 100, "git push", sid=other), ev("permission_requested", 101, "git push", sid=other),
              ev("tool_call_completed", 120, "git push", sid=other), ev("tool_call_started", 130, "ls")]
    assert pw.previous_call_note(events, SID) is None


def test_a_first_call_has_nothing_before_it():
    assert pw.previous_call_note([ev("tool_call_started", 100, "ls")], SID) is None


def _hook_out():
    import json
    from macf.hooks.handle_pre_tool_use import run
    return run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "true"}, "session_id": "s-note"}))


def test_the_hook_tells_the_agent_and_not_the_operators_status_line():
    from unittest.mock import patch
    with patch("macf.permission_watch.read_previous_call_note", return_value="Your previous call (Bash: git push) ran"):
        out = _hook_out()
    assert "Your previous call (Bash: git push) ran" in out["hookSpecificOutput"]["additionalContext"]
    assert "Your previous call" not in out["systemMessage"]


def test_the_hook_says_nothing_when_there_is_no_note_and_survives_a_failed_read():
    from unittest.mock import patch
    with patch("macf.permission_watch.read_previous_call_note", return_value=None):
        assert "Your previous call" not in _hook_out()["hookSpecificOutput"]["additionalContext"]
    with patch("macf.permission_watch.read_previous_call_note", side_effect=OSError("log gone")):
        out = _hook_out()
    assert out.get("continue") is True and "Your previous call" not in out["hookSpecificOutput"]["additionalContext"]


def test_a_denial_is_not_said_again_since_the_client_already_reports_it():
    events = [ev("tool_call_started", 100, "git push"), ev("permission_requested", 101, "git push"),
              ev("dev_drv_ended", 110, "", tool="none"), ev("tool_call_started", 130, "ls")]
    events[2] = {"event": "dev_drv_ended", "timestamp": 110, "data": {"session_id": SID}}
    assert pw.previous_call_note(events, SID) is None


def test_the_read_stops_at_the_previous_calls_start(monkeypatch):
    """It runs at every call's start over a log of hundreds of megabytes, so it reads back only as far
    as the previous call of this session started."""
    import macf.agent_events_log as log
    newest_first = [ev("tool_call_started", 130, "ls"), ev("tool_call_completed", 120, "git push"),
                    ev("permission_requested", 101, "git push"), ev("tool_call_started", 100, "git push")] + \
                   [ev("tool_call_completed", 90 - i, f"old {i}") for i in range(50)]
    taken = []

    def read_events(**kw):
        for e in newest_first:
            taken.append(e)
            yield e
    monkeypatch.setattr(log, "read_events", read_events)
    assert "git push" in (pw.read_previous_call_note(SID) or "")
    assert len(taken) == 4


# ---- through a real (isolated) event log -------------------------------------------------------

def _log(name, sid, command, tool="Bash"):
    from macf.agent_events_log import append_event
    append_event(name, {"session_id": sid, "tool": tool, "tool_name": tool},
                 hook_input={"session_id": sid, "tool_name": tool, "tool_input": {"command": command},
                             "cwd": "/w", "permission_mode": "auto"})


def test_the_note_reads_a_real_log_with_another_session_interleaved():
    other = "bbbb2222-0000"
    _log("tool_call_started", SID, "git push")
    _log("tool_call_started", other, "make")                 # another session's start, between ours
    _log("permission_requested", SID, "git push")
    _log("tool_call_completed", other, "make")
    _log("tool_call_completed", SID, "git push")
    _log("tool_call_started", other, "make test")
    _log("tool_call_started", SID, "ls")                    # this call
    note = pw.read_previous_call_note(SID)
    assert note and "git push" in note and "permissions how" in note


def test_a_first_call_in_a_long_log_reads_no_further_than_the_cap(monkeypatch):
    """A session's first call has no previous start to stop at; the cap keeps it from walking the log."""
    import macf.agent_events_log as log
    for i in range(500):
        _log("tool_call_completed", "bbbb2222-0000", f"old {i}")
    _log("tool_call_started", SID, "ls")
    real, taken = log.read_events, []

    def counting(**kw):
        for e in real(**kw):
            taken.append(e)
            yield e
    monkeypatch.setattr(log, "read_events", counting)
    assert pw.read_previous_call_note(SID, limit=400) is None
    assert len(taken) == 400


def test_a_failed_read_leaves_the_hook_output_and_warns(monkeypatch):
    from unittest.mock import patch
    import macf.hooks.handle_pre_tool_use as hook
    warned = []
    monkeypatch.setattr(hook, "emit_warning", lambda w: warned.append(w))
    with patch("macf.permission_watch.read_previous_call_note", side_effect=OSError("log gone")):
        out = _hook_out()
    assert out.get("continue") is True and "hookSpecificOutput" in out
    assert any(getattr(w, "kind", "") == "approval_note_failed" for w in warned)
