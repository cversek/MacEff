"""Presence by voice (MIS-0008 Q01, the operator's ruling of 2026-11-18): an utterance delivered on a channel the
declaration lists as the operator's resets USER_IDLE; when the operator's latest activity is wake-phrase voice
with no keyboard input since, the state is HANDS_FREE instead of USER_IDLE."""
from macf.agent_events_log import append_event, read_events
from macf.modes.detection import OPERATIONAL_MODES, detect_active_modes
from macf.pd.interface import UtteranceRequest
from macf.pd.voice_carriage import receipt_for


def request(trigger):
    from test_voice_channel import utterance_request
    return UtteranceRequest(**dict(utterance_request(), trigger=trigger))


def activity():
    return [e["data"] for e in read_events(limit=None) if e.get("event") == "user_activity_detected"]


def test_a_delivered_utterance_is_presence_only_where_voice_is_an_operator_channel(isolated_events_log):
    receipt_for("Tester_abc123", request("hold_key"), "utt-1", "capture", "delivered", None, operator=False)
    assert activity() == []
    receipt_for("Tester_abc123", request("hold_key"), "utt-2", "capture", "delivered", None, operator=True)
    receipt_for("Tester_abc123", request("wake_phrase"), "utt-3", "capture", "refused", "no channel", operator=True)
    assert [(a["source"], a["trigger"]) for a in activity()] == [("voice", "hold_key")]


def test_wake_phrase_voice_with_no_keyboard_since_is_hands_free_not_idle(isolated_events_log, monkeypatch):
    monkeypatch.setenv("MACF_USER_IDLE_TIMEOUT_MINS", "0")   # long past the idle window
    append_event("user_activity_detected", {"source": "voice", "trigger": "wake_phrase", "detector": "test"})
    modes = detect_active_modes("s", {})
    assert "HANDS_FREE" in modes and "USER_IDLE" not in modes
    assert OPERATIONAL_MODES["HANDS_FREE"]["emoji"] == "🗣️"


def test_a_key_started_utterance_is_never_hands_free(isolated_events_log):
    append_event("user_activity_detected", {"source": "voice", "trigger": "hold_key", "detector": "test"})
    modes = detect_active_modes("s", {})
    assert "HANDS_FREE" not in modes and "USER_IDLE" not in modes


def test_typing_after_wake_voice_ends_hands_free(isolated_events_log):
    append_event("user_activity_detected", {"source": "voice", "trigger": "wake_phrase", "detector": "test"})
    append_event("user_activity_detected", {"source": "direct", "detector": "test"})
    assert "HANDS_FREE" not in detect_active_modes("s", {})
