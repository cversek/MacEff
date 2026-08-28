"""USER_IDLE must not clear because the agent was busy.

The old lookup scanned a fixed 200 rows for the most recent
`user_activity_detected`. Every macf_tools invocation appends an event, so a
working agent buried the user's last input past that window within minutes. The
scan then returned None, and `if last_activity and ...` read None as "the user
is present".

Measured live before the fix: the user's last input at 14:05:33, `😴` correctly
appearing at 14:15:45, and gone at 14:19:08 — the render on which exactly 200
events had accumulated since. Nothing had reset the timer.

The perverse part is what makes it worth a regression test: the mode meaning
"the agent is working alone" was switched off *by the agent working alone*, so
it degraded precisely under the load it exists to cover, and a lightly-used
session never reproduced it.

The fix asks a different question — was there any activity inside the window —
which is bounded by AGE rather than by row count. Volume cannot shrink an age.
"""
import time

import pytest


def _activity(ts, source="direct"):
    return {"event": "user_activity_detected", "timestamp": ts,
            "data": {"source": source, "detector": "test"}}


def _noise(ts):
    return {"event": "cli_command_invoked", "timestamp": ts, "data": {"command": "task"}}


@pytest.fixture
def scan(monkeypatch):
    def _run(events, cutoff, **kw):
        import macf.modes.detection as det
        monkeypatch.setattr(det, "read_events",
                            lambda limit=None, reverse=False: list(reversed(events)) if reverse else list(events))
        return det._had_user_activity_since(cutoff, **kw)
    return _run


class TestVolumeCannotHideTheUser:
    def test_finds_activity_under_250_agent_events(self, scan):
        """The regression. 250 > the old 200-row window, by design."""
        now = time.time()
        events = [_activity(now - 600)] + [_noise(now - 600 + i) for i in range(1, 251)]
        assert scan(events, now - 900) is True

    def test_still_false_when_the_activity_is_older_than_the_window(self, scan):
        """The window is a window — burying is the bug, expiry is the feature."""
        now = time.time()
        events = [_activity(now - 3600)] + [_noise(now - 300 + i) for i in range(1, 251)]
        assert scan(events, now - 600) is False

    def test_recent_activity_reads_as_present(self, scan):
        now = time.time()
        assert scan([_activity(now - 5)], now - 600) is True


class TestHonestNegatives:
    def test_no_events_at_all_is_false(self, scan):
        """False here means 'nothing in the interval', which IS idleness."""
        assert scan([], time.time() - 600) is False

    def test_source_filter_still_applies(self, scan):
        """USER_REMOTE's auto-clear needs CLI-typed input only, not channel traffic."""
        now = time.time()
        events = [_activity(now - 5, source="channel")]
        assert scan(events, now - 600, sources={"direct"}) is False
        assert scan(events, now - 600, sources={"channel"}) is True


class TestPermissionDenialCountsAsPresence:
    def test_a_rejected_tool_call_is_user_activity(self):
        """A rejection proves the user is watching the tool stream in real time.

        Shape verified against a live transcript: type "user", carrying
        toolDenialKind — which appears on denials and nowhere else. The general
        user-activity detector drops it because it also carries toolUseResult.
        """
        from macf.transcript_monitor.daemon import detect_permission_denial
        entry = {"type": "user", "toolDenialKind": "user-rejected",
                 "toolUseResult": "User rejected tool use", "timestamp": "2026-08-28T18:00:00Z"}
        det = detect_permission_denial(entry)
        assert det is not None
        assert det.event_name == "user_activity_detected"
        assert det.data["source"] == "direct"

    def test_an_ordinary_tool_result_is_not(self):
        """Over-correcting here would invent presence out of the agent's own work."""
        from macf.transcript_monitor.daemon import detect_permission_denial
        assert detect_permission_denial(
            {"type": "user", "toolUseResult": "ok", "timestamp": "x"}) is None
