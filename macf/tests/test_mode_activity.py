"""What counts as the operator's activity: conformance for MIS-0002's presence rules.

Two producers record the operator's activity, the prompt hook and the
transcript monitor, and USER_IDLE and USER_REMOTE are read from what they
record. MIS-0002 section 11 names the first three tests here. The door audit
after them runs every way input reaches a session through both producers, so a
door nobody classified shows up as a failing row rather than as a mode that
quietly turns off.
"""

import json

import pytest

from macf.hooks.handle_user_prompt_submit import record_user_activity_from_payload
from macf.transcript_monitor.daemon import (
    DEFAULT_DETECTORS,
    detect_mid_turn_enqueue,
    detect_user_activity,
)
from macf.utils.input_origin import WAKE_OPENING

WAKE = f"{WAKE_OPENING} amail: new message 2026-10-10T07:12:03Z-ab12"
TELEGRAM = '<channel source="plugin:telegram:telegram" chat_id="1">on my way</channel>'
MACEFF_NOTICE = '<channel source="plugin:maceff-channel:maceff" kind="amail">new mail</channel>'
TASK_NOTICE = "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>"
PEER = '<cross-session-message from="bridge:session_x" from-name="a session">hi</cross-session-message>'
HAND_BACK = '<agent-message from="a6f1">\n[Subagent hand-back] The final report.\n</agent-message>'
CRON = "[cron:D1] Scheduled GitHub check for the duty"
RECOVERY = "You compacted yourself. Read your checkpoint, then continue."


def _user(content, origin=None, **fields):
    entry = {"type": "user", "timestamp": "2026-10-10T07:00:00Z",
             "message": {"role": "user", "content": content}, **fields}
    if origin is not None:
        entry["origin"] = origin
    return entry


def _queued(content):
    return {"type": "queue-operation", "operation": "enqueue",
            "timestamp": "2026-10-10T06:59:59Z", "content": content}


ANSWERED = {"type": "user", "timestamp": "2026-10-10T07:00:00Z",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "A"}]},
            "toolUseResult": {"questions": [{"question": "Which?"}], "answers": {"Which?": "A"}}}
REJECTED = {"type": "user", "timestamp": "2026-10-10T07:00:00Z",
            "toolDenialKind": "user-rejected", "toolUseResult": "User rejected tool use"}


def _activity(log_path):
    if not log_path.exists():
        return []
    events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    return [e for e in events if e.get("event") == "user_activity_detected"]


def _hook_records(log_path, prompt):
    """The sources the prompt hook records for ``prompt``."""
    before = len(_activity(log_path))
    record_user_activity_from_payload(prompt)
    return [e["data"]["source"] for e in _activity(log_path)[before:]]


def _monitor_records(*entries):
    """The sources a monitor records for these transcript entries, and which detectors fired."""
    sources, fired = [], set()
    for entry in entries:
        for detector in DEFAULT_DETECTORS:
            detection = detector(entry)
            if detection is not None and detection.event_name == "user_activity_detected":
                sources.append(detection.data["source"])
                fired.add(detector.__name__)
    return sources, fired


def test_wake_is_not_operator_activity(isolated_events_log):
    """MIS-0002-R106: a wake is not the operator, typed or queued, through either producer."""
    typed = _user(WAKE, {"kind": "human"}, promptSource="typed", turnOrigin="human")
    assert _hook_records(isolated_events_log, WAKE) == []
    assert _monitor_records(typed, _queued(WAKE))[0] == []
    # The operator's own typing still counts, and only the opening is read.
    assert _hook_records(isolated_events_log, "back now") == ["direct"]
    quoting = _user(f"what does {WAKE_OPENING} mean?", {"kind": "human"})
    assert _monitor_records(quoting)[0] == ["direct"]


def test_source_from_origin_or_opening_tag(isolated_events_log):
    """MIS-0002-R121: a channel event's source comes from its origin record, and
    from the tag that opens its text only where there is no record."""
    from_record = detect_user_activity(
        _user(TELEGRAM, {"kind": "channel", "server": "plugin:telegram:telegram"})).data
    assert (from_record["source"], from_record["channel_server"]) == ("channel", "plugin:telegram:telegram")
    assert detect_user_activity(_user(TELEGRAM, {"kind": "human"})).data["source"] == "direct"

    from_tag = detect_mid_turn_enqueue(_queued(TELEGRAM)).data
    assert (from_tag["source"], from_tag["channel_server"]) == ("channel", "plugin:telegram:telegram")
    assert _hook_records(isolated_events_log, TELEGRAM) == ["channel"]

    later = detect_mid_turn_enqueue(_queued(f"see {TELEGRAM}")).data
    assert later["source"] == "mid_turn_enqueue" and "channel_server" not in later


def test_dialog_answer_counts():
    """MIS-0002-R128: a person's answer to a dialog is the operator acting."""
    assert _monitor_records(ANSWERED)[0] == ["direct"]
    unanswered = {**ANSWERED, "toolUseResult": {"questions": [{"question": "Which?"}]}}
    assert _monitor_records(unanswered)[0] == []


def _gap(reason):
    return pytest.mark.xfail(strict=True, reason=f"known gap: {reason}")


# Each door: what the prompt hook is given (None where it never fires), the
# transcript entries the door writes, and what each producer should record.
# A row marked as a gap states the right answer and fails today; strict, so
# the pull request that fixes it must also unmark it.
DOORS = [
    pytest.param("typed prompt", "fix the thing",
                 [_user("fix the thing", {"kind": "human"}, promptSource="typed")],
                 ["direct"], ["direct"], id="typed"),
    pytest.param("accepted suggestion", "run the tests",
                 [_user("run the tests", {"kind": "human"}, promptSource="suggestion_accepted")],
                 ["direct"], ["direct"], id="suggestion"),
    pytest.param("typed while a turn runs", "also check the docs",
                 [_queued("also check the docs")],
                 ["direct"], ["mid_turn_enqueue"], id="typed-mid-turn"),
    pytest.param("channel message", TELEGRAM,
                 [_queued(TELEGRAM),
                  _user(TELEGRAM, {"kind": "channel", "server": "plugin:telegram:telegram"}, isMeta=True)],
                 ["channel"], ["channel"], id="channel"),
    pytest.param("MacEff channel notice", MACEFF_NOTICE, [_queued(MACEFF_NOTICE)], [], [],
                 marks=_gap("the MacEff channel is told apart by name when it lands"), id="maceff-notice"),
    pytest.param("task notification", TASK_NOTICE,
                 [_queued(TASK_NOTICE), _user(TASK_NOTICE, {"kind": "task-notification"})],
                 [], [], id="task-notification"),
    pytest.param("another session's message", PEER,
                 [_queued(PEER), _user(PEER, {"kind": "peer"})], [], [], id="peer"),
    pytest.param("subagent hand-back", HAND_BACK, [_queued(HAND_BACK)], [], [], id="hand-back"),
    pytest.param("session cron prompt", CRON,
                 [_queued(CRON), _user(CRON, isMeta=True, promptSource="system", turnOrigin="scheduled")],
                 [], [], marks=_gap("a queued copy is read by its delivered twin"), id="cron"),
    pytest.param("inject", "/compact",
                 [_user("/compact", {"kind": "human"}, promptSource="typed")], [], [],
                 marks=_gap("keys the framework types are recorded first"), id="inject"),
    pytest.param("supervisor keys after a start", "/maceff:resume",
                 [_user("/maceff:resume", {"kind": "human"}, promptSource="typed")], [], [],
                 marks=_gap("keys the framework types are recorded first"), id="supervisor-keys"),
    pytest.param("recovery prompt after a self-compaction", RECOVERY,
                 [_user(RECOVERY, {"kind": "human"}, promptSource="typed")], [], [],
                 marks=_gap("keys the framework types are recorded first"), id="recovery-prompt"),
    pytest.param("typed wake", WAKE,
                 [_queued(WAKE), _user(WAKE, {"kind": "human"}, promptSource="typed")],
                 [], [], id="wake"),
    pytest.param("dialog answer", None, [ANSWERED], None, ["direct"], id="dialog-answer"),
    pytest.param("permission rejection", None, [REJECTED], None, ["direct"], id="rejection"),
]


@pytest.mark.parametrize("door, prompt, entries, hook, monitor", DOORS)
def test_every_door_is_counted_as_audited(isolated_events_log, door, prompt, entries, hook, monitor):
    if prompt is not None:
        assert _hook_records(isolated_events_log, prompt) == hook, f"prompt hook, {door}"
    assert _monitor_records(*entries)[0] == monitor, f"transcript monitor, {door}"


ACTIVITY_DETECTORS = {"detect_user_activity", "detect_permission_denial",
                      "detect_dialog_answer", "detect_mid_turn_enqueue"}
OTHER_DETECTORS = {"detect_compact_boundary", "detect_api_error", "detect_context_collapse"}


def test_the_audit_reaches_every_detector():
    """A detector added to the monitor is placed here before it can count anything:
    among those that record activity, each one exercised by a door, or among the rest."""
    assert {d.__name__ for d in DEFAULT_DETECTORS} == ACTIVITY_DETECTORS | OTHER_DETECTORS
    fired = set()
    for param in DOORS:
        if not param.marks:
            fired |= _monitor_records(*param.values[2])[1]
    assert fired == ACTIVITY_DETECTORS
