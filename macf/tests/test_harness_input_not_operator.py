"""Input the client delivers by itself is not the operator acting.

A background task's completion notice and a message from another session
arrive the way the operator's typing does: as user entries, as queued
entries, and as prompts. Counted as activity, each one cleared USER_IDLE.
"""

import json

from macf.transcript_monitor import daemon
from macf.transcript_monitor.daemon import detect_mid_turn_enqueue, detect_user_activity

TASK_NOTICE = ("<task-notification>\n<task-id>b1</task-id>\n"
               "<status>completed</status>\n</task-notification>")
PEER_MESSAGE = ('Another Claude session sent a message:\n'
                '<cross-session-message from="bridge:session_x">hi</cross-session-message>')


def _user(content, origin=None):
    entry = {"type": "user", "timestamp": "2026-10-09T20:28:30Z",
             "message": {"role": "user", "content": content}}
    if origin is not None:
        entry["origin"] = origin
    return entry


def _queued(content):
    return {"type": "queue-operation", "operation": "enqueue",
            "timestamp": "2026-10-09T20:28:29Z", "content": content}


def test_a_task_notice_or_a_peer_message_is_not_the_operator():
    assert detect_user_activity(_user(TASK_NOTICE, {"kind": "task-notification"})) is None
    assert detect_user_activity(_user(PEER_MESSAGE, {"kind": "peer", "from": "bridge:x"})) is None


def test_the_operators_typing_and_channels_still_count():
    assert detect_user_activity(_user("do your recovery", {"kind": "human"})).data["source"] == "direct"
    assert detect_user_activity(_user("/compact")).data["source"] == "direct"
    channel = detect_user_activity(
        _user('<channel source="plugin:telegram:telegram">hi</channel>',
              {"kind": "channel", "server": "plugin:telegram:telegram"})).data
    assert (channel["source"], channel["channel_server"]) == ("channel", "plugin:telegram:telegram")


def test_an_entry_without_an_origin_is_read_by_how_it_opens():
    assert detect_user_activity(_user(TASK_NOTICE)) is None
    assert detect_user_activity(_user([{"type": "text", "text": PEER_MESSAGE}])) is None
    quoted = "what does <task-notification> mean?"
    assert detect_user_activity(_user(quoted)).data["source"] == "direct"


def test_a_queued_notice_is_not_activity():
    assert detect_mid_turn_enqueue(_queued(TASK_NOTICE)) is None
    assert detect_mid_turn_enqueue(_queued(PEER_MESSAGE)) is None
    assert detect_mid_turn_enqueue(_queued("run it again")).data["source"] == "mid_turn_enqueue"


def test_a_running_monitor_records_nothing_for_a_notice(monkeypatch, tmp_path):
    emitted = []
    monkeypatch.setattr(daemon, "append_event", lambda name, data: emitted.append((name, data)))
    monitor = daemon.TranscriptMonitor(tmp_path / "s.jsonl")
    monitor._process_line(json.dumps(_queued(TASK_NOTICE)))
    monitor._process_line(json.dumps(_user(TASK_NOTICE, {"kind": "task-notification"})))
    assert emitted == []
    monitor._process_line(json.dumps(_user("I'm here", {"kind": "human"})))
    assert [(n, d["source"]) for n, d in emitted] == [("user_activity_detected", "direct")]
