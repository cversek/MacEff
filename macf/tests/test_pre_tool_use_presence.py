"""The per-call line shows presence (MIS-0002-R91), only for an agent that declares a daemon.

An agent with no declaration has no daemon to vouch for presence, so its line carries
nothing rather than "unknown" on every call. One with a declaration whose daemon isn't
alive says ``presence: unknown`` (persistent_layer 5.3), never "nobody". One whose
daemon is alive shows the onlookers and surfaces its own log records.
"""
import json
import os
from unittest.mock import patch

from macf.agent_events_log import append_event
from macf.notify.session import proc_start
from macf.observe import presence
from macf.observe.acts import EVENT_INVITE
from macf.pd.names import declaration_path, record_path

WATCHER = "Watcher@abc123"


def _home(tmp_path, declared):
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "Tester"}}))
    if declared:
        declaration_path(home).parent.mkdir(parents=True)
        declaration_path(home).write_text("{}")
    return home


def _invite():
    append_event(EVENT_INVITE, {"onlooker": WATCHER, "observed": "Tester@abc123", "stream_from": 0,
                                "secret_sha256": "ab" * 32})


def _line(home, monkeypatch):
    from macf.hooks.handle_pre_tool_use import run
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    out = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "true"}, "session_id": "s-pr"}))
    return json.dumps(out)


def test_no_declaration_no_segment(tmp_path, monkeypatch, isolated_events_log):
    """Even with an onlooker in the log and a daemon that would read as alive."""
    _invite()
    with patch.object(presence, "daemon_alive", return_value=True):
        out = _line(_home(tmp_path, declared=False), monkeypatch)
    assert "presence" not in out and "onlookers" not in out


def test_a_declared_daemon_not_alive_says_unknown(tmp_path, monkeypatch, isolated_events_log):
    with patch.object(presence, "daemon_alive", return_value=False):
        out = _line(_home(tmp_path, declared=True), monkeypatch)
    assert "presence: unknown" in out


def test_a_live_daemon_shows_who_watches(tmp_path, monkeypatch, isolated_events_log):
    _invite()
    with patch.object(presence, "daemon_alive", return_value=True):
        out = _line(_home(tmp_path, declared=True), monkeypatch)
    assert f"onlookers: {WATCHER}" in out and "presence: unknown" not in out


def test_alive_means_the_record_names_this_very_process(tmp_path):
    """The daemon's record must name a live process by pid and start time; a record whose
    pid now belongs to another incarnation, or that can't be read, is not alive."""
    card = "Tester@abc123"
    assert not presence.daemon_alive(card, base=tmp_path)
    record_path(card, tmp_path).write_text(json.dumps({"pid": os.getpid(), "proc_start": proc_start(os.getpid())}))
    assert presence.daemon_alive(card, base=tmp_path)
    record_path(card, tmp_path).write_text(json.dumps({"pid": os.getpid(), "proc_start": "Thu Jan  1 00:00:00 1970"}))
    assert not presence.daemon_alive(card, base=tmp_path)
    record_path(card, tmp_path).write_text("not json")
    assert not presence.daemon_alive(card, base=tmp_path)
