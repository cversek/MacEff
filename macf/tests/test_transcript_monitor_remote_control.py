"""The transcript monitor recognizes a Remote Control disconnect from the record Claude Code writes (#883).

The records' quoted texts are the client's own; the fields around them are invented."""
import pytest

from macf.transcript_monitor.daemon import detect_remote_control_disconnect


def _row(content, subtype="informational", kind="system"):
    return {"type": kind, "subtype": subtype, "content": content, "timestamp": "2026-11-19T21:00:00.000Z"}


@pytest.mark.parametrize("reason,kind", [
    ("OAuth token unavailable", "login"),
    ("JWT refresh failed: no OAuth token", "login"),
    ("Claude.ai login expired", "login"),
    ("could not reach the Remote Control server for about 30 minutes", "network"),
    ("Couldn't reconnect to your Remote Control session", "network"),
    ("the server no longer reports this session", "ended_elsewhere"),
    ("this session was ended or archived from another device or app (code 4090)", "ended_elsewhere"),
])
def test_each_reason_kind_is_told_apart(reason, kind):
    remedy = {"login": "/login", "network": "/remote-control", "ended_elsewhere": "/remote-control"}[kind]
    d = detect_remote_control_disconnect(_row(f"Remote Control disconnected — {reason} — run {remedy}"))
    assert d is not None and d.event_name == "remote_control_disconnected"
    assert d.data["kind"] == kind and d.data["reason"] == reason and d.data["remedy"] == remedy
    assert d.data["timestamp"] == "2026-11-19T21:00:00.000Z" and d.data["detector"] == "transcript_monitor"


def test_an_unknown_reason_is_still_recognized_with_its_remedy():
    d = detect_remote_control_disconnect(_row("Remote Control disconnected — something new — run /remote-control to reconnect"))
    assert d.data["kind"] == "unknown" and d.data["reason"] == "something new"
    assert d.data["remedy"] == "/remote-control"


@pytest.mark.parametrize("row", [
    _row("Compacted while idle"),                                          # another informational row
    _row("Remote Control disconnected — x — run /login", subtype="api_error"),
    _row("Remote Control disconnected — x — run /login", kind="user"),    # a user typing the words is not the client
    {"type": "system", "subtype": "informational"},                        # no content
    {"type": "system", "subtype": "informational", "content": None},
])
def test_other_rows_are_not_a_disconnect(row):
    assert detect_remote_control_disconnect(row) is None
