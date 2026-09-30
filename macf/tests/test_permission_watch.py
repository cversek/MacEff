"""A permission prompt nobody answers is seen from outside the session.

Three stalls (3, 17 and 12 hours) each began with one PermissionRequest and
nothing after it. These tests pin how a wait is read from the event log and
how the watch turns it into reminders and an all-clear.
"""
from macf import permission_watch as pw
from macf.agent_events_log import append_event


def ev(name, t, sid="s1", **data):
    data.setdefault("session_id", sid)
    return {"event": name, "timestamp": t, "data": data, "hook_input": {"session_id": sid}}


def request(t, sid="s1", command="gh pr create -R o/r --title x"):
    e = ev("permission_requested", t, sid, tool_name="Bash", timestamp=t)
    e["hook_input"]["tool_input"] = {"command": command}
    return e


def newest_first(*events):
    return sorted(events, key=lambda e: e["timestamp"], reverse=True)


class TestWaiting:
    def test_a_request_with_nothing_after_it_is_a_wait(self):
        got = pw.waiting(newest_first(ev("tool_call_started", 100), request(101)))
        assert [(w.session_id, w.since, w.tool) for w in got] == [("s1", 101, "Bash")]

    def test_progress_after_the_request_means_it_was_answered(self):
        got = pw.waiting(newest_first(request(101), ev("tool_call_completed", 160)))
        assert got == []

    def test_a_denied_prompt_is_answered_by_the_end_of_the_turn(self):
        got = pw.waiting(newest_first(request(101), ev("dev_drv_ended", 130)))
        assert got == []

    def test_events_the_dialog_itself_causes_do_not_answer_it(self):
        # CC notifies because of the dialog; the operator typing elsewhere is not an answer
        activity = {"event": "user_activity_detected", "timestamp": 150, "data": {"detector": "x"}}
        got = pw.waiting(newest_first(request(101), ev("notification_received", 102), activity))
        assert len(got) == 1

    def test_sessions_are_read_independently(self):
        got = pw.waiting(newest_first(request(100, "a"), request(101, "b"), ev("tool_call_completed", 110, "b")))
        assert [w.session_id for w in got] == ["a"]

    def test_the_newest_request_is_the_one_waiting(self):
        got = pw.waiting(newest_first(request(100), ev("tool_call_completed", 105), request(200, command="second")))
        assert [(w.since, w.preview) for w in got] == [(200, "second")]

    def test_the_preview_is_the_full_command_not_the_truncated_log_preview(self):
        long = "gh pr create " + "x" * 400
        got = pw.waiting([request(100, command=long)])
        assert got[0].preview == long


class TestReadWaitingFromTheLog:
    def test_the_real_log_round_trip(self):
        append_event("tool_call_started", data={"session_id": "s9", "tool": "Bash"}, hook_input={"session_id": "s9"})
        append_event(
            "permission_requested",
            data={"session_id": "s9", "tool_name": "Bash", "timestamp": 1000.0},
            hook_input={"session_id": "s9", "tool_input": {"command": "git push"}},
        )
        got = pw.read_waiting()
        assert [(w.session_id, w.preview) for w in got] == [("s9", "git push")]

    def test_the_real_log_sees_the_answer(self):
        append_event(
            "permission_requested",
            data={"session_id": "s9", "tool_name": "Bash", "timestamp": 1000.0},
            hook_input={"session_id": "s9", "tool_input": {"command": "git push"}},
        )
        append_event("tool_call_completed", data={"session_id": "s9", "tool": "Bash", "success": True}, hook_input={"session_id": "s9"})
        assert pw.read_waiting() == []


class Outbox:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    def __call__(self, text):
        self.sent.append(text)
        return self.ok


def one_wait(since=0.0, command="gh pr create"):
    return [pw.Waiting(session_id="s1", since=since, tool="Bash", preview=command)]


def run(current, now, state, send, older=10, repeat=60):
    return pw.watch(current, now, older_than_min=older, repeat_min=repeat, state=state, send=send, agent="Agent@x")


class TestWatch:
    def test_a_young_wait_is_left_alone(self):
        out = Outbox()
        state = run(one_wait(), now=9 * 60, state={}, send=out)
        assert out.sent == [] and state == {}

    def test_a_wait_past_the_threshold_is_reminded_once_naming_the_command(self):
        out = Outbox()
        state = run(one_wait(command="gh pr create -R o/r"), now=11 * 60, state={}, send=out)
        assert len(out.sent) == 1 and "gh pr create -R o/r" in out.sent[0] and "11 min" in out.sent[0]
        state = run(one_wait(command="gh pr create -R o/r"), now=20 * 60, state=state, send=out)
        assert len(out.sent) == 1

    def test_the_reminder_repeats_after_the_repeat_interval(self):
        out = Outbox()
        state = run(one_wait(), now=11 * 60, state={}, send=out)
        state = run(one_wait(), now=(11 + 60) * 60, state=state, send=out)
        assert len(out.sent) == 2

    def test_an_answered_wait_gets_one_all_clear(self):
        out = Outbox()
        state = run(one_wait(), now=11 * 60, state={}, send=out)
        state = run([], now=30 * 60, state=state, send=out)
        assert "answered" in out.sent[-1] and "30 min" in out.sent[-1] and state == {}
        run([], now=40 * 60, state=state, send=out)
        assert len(out.sent) == 2

    def test_a_reminder_that_failed_to_send_is_tried_again(self):
        down, up = Outbox(ok=False), Outbox()
        state = run(one_wait(), now=11 * 60, state={}, send=down)
        assert state == {}
        run(one_wait(), now=12 * 60, state=state, send=up)
        assert len(up.sent) == 1

    def test_a_wait_we_never_reminded_about_gets_no_all_clear(self):
        out = Outbox()
        state = run(one_wait(), now=5 * 60, state={}, send=out)
        run([], now=6 * 60, state=state, send=out)
        assert out.sent == []
