"""Who asked for a compaction, recorded where the asking happens.

MIS-0002-R127 (harness_compaction_MUST_be_recorded): a compaction nobody asked for is
recorded with the harness as the asker. The PreCompact hook's ``trigger`` cannot tell
it apart: Claude Code 2.1.289 labels its own idle compaction "manual", 2.1.290 "auto".
What does tell it apart is the client's own transcript row after the boundary,
"Compacted while idle, before the prompt cache expired", and, for the other askers,
the ask itself: a typed ``/compact`` command row, or ``macf_tools inject compact``.
The rows below are copied from real 2.1.289 transcripts.
"""
import json
from unittest.mock import patch

from macf.transcript_monitor import daemon
from macf.transcript_monitor.daemon import detect_compaction_ask, detect_harness_compaction

IDLE_ROW = {"type": "system", "subtype": "informational",
            "content": "Compacted while idle, before the prompt cache expired",
            "level": "notice", "timestamp": "2026-10-09T21:49:27.900Z"}
TYPED_COMPACT_ROW = {"type": "user", "timestamp": "2026-10-09T20:04:53.736Z", "message": {
    "role": "user",
    "content": "<command-name>/compact</command-name>\n            <command-message>compact</command-message>\n            <command-args></command-args>"}}


def test_idle_marker_records_the_harness_as_asker():
    detection = detect_harness_compaction(IDLE_ROW)
    assert detection.event_name == "harness_compaction_detected"
    assert detection.data["asker"] == "harness"
    assert detection.data["timestamp"] == IDLE_ROW["timestamp"]


def test_other_informational_rows_are_not_compactions():
    row = dict(IDLE_ROW, content="Conversation compacted")
    assert detect_harness_compaction(row) is None


def test_typed_compact_command_is_the_operators_ask():
    detection = detect_compaction_ask(TYPED_COMPACT_ROW)
    assert detection.event_name == "compaction_asked"
    assert detection.data["asker"] == "operator"


def test_a_prompt_that_mentions_compact_is_not_an_ask():
    row = {"type": "user", "message": {"role": "user", "content": "should we /compact before lunch?"}}
    assert detect_compaction_ask(row) is None


def test_both_detectors_run_by_default():
    assert detect_harness_compaction in daemon.DEFAULT_DETECTORS
    assert detect_compaction_ask in daemon.DEFAULT_DETECTORS


def test_inject_compact_records_a_wind_down_ask(isolated_events_log):
    from macf import supervisor
    with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "agent-x"}), \
         patch.object(supervisor, "send_keys", return_value=0), \
         patch("macf.stop_bypass.arm"):
        assert supervisor.send_slash_to_self("compact") == 0
    events = [json.loads(line) for line in isolated_events_log.read_text().splitlines()]
    asks = [e for e in events if e["event"] == "compaction_asked"]
    assert asks and asks[-1]["data"]["asker"] == "wind_down"
    assert asks[-1]["data"]["via"] == "macf_tools inject"


def test_a_compact_the_framework_typed_is_not_the_operators(isolated_events_log, monkeypatch):
    """inject compact types /compact into the pane; the row it produces is not an operator's ask."""
    from macf import supervisor
    monkeypatch.setattr(supervisor, "_tmux_available", lambda: True)
    monkeypatch.setattr(supervisor, "_find_supervisor", lambda target: {"name": "n", "tmux_session": "s"})
    monkeypatch.setattr(supervisor.subprocess, "run", lambda argv, **kw: type("Done", (), {"returncode": 0})())
    assert detect_compaction_ask(TYPED_COMPACT_ROW).data["asker"] == "operator"
    assert supervisor.send_keys("n", ["/compact"], enter=True, kind="inject") == 0
    assert detect_compaction_ask(TYPED_COMPACT_ROW) is None
