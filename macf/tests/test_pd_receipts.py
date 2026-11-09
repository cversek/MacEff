"""A notice written to the channel and never received is said (cversek/MacEff#904).

With no managed settings, the client refused the channel plugin for two days: every notice was
written to the channel, recorded `pd_notice_delivered`, and dropped, and nothing said so. The
session's prompt hook records `notice_received` for each notice it takes, so a delivery with no
receipt after the session has taken a turn is the sign, whatever the cause.
"""
import time

from macf.agent_events_log import append_event
from macf.pd import receipts
from macf.pd.cli import _say_receipts

T0 = 1794240000.0


def delivered(aid, sent_at, via="channel", source="amail"):
    return {"event": "pd_notice_delivered", "timestamp": sent_at,
            "data": {"source": source, "arrival_id": aid, "sent_at": sent_at, "via": via}}


def received(aid, at):
    return {"event": "notice_received", "timestamp": at, "data": {"notice_id": aid}}


def turn(at):
    return {"event": "dev_drv_started", "timestamp": at, "data": {}}


def test_a_notice_with_no_receipt_after_a_later_turn_is_unreceived():
    [missing] = receipts.unreceived([delivered("a1", T0), turn(T0 + 600)])
    assert (missing.source, missing.arrival_id, missing.sent_at) == ("amail", "a1", T0)


def test_a_received_notice_is_not_counted():
    assert receipts.unreceived([delivered("a1", T0), received("a1", T0 + 1), turn(T0 + 600)]) == []


def test_a_busy_session_is_given_until_its_next_turn():
    """A notice written during a long turn is taken when the turn ends, so no turn since, or
    one only inside the grace, is not yet evidence."""
    assert receipts.unreceived([delivered("a1", T0)]) == []
    assert receipts.unreceived([delivered("a1", T0), turn(T0 + receipts.GRACE_S - 1)]) == []


def test_a_keystroke_wake_is_not_counted():
    assert receipts.unreceived([delivered("a1", T0, via="keystroke"), turn(T0 + 600)]) == []


def test_pd_status_says_so_from_the_event_log(capsys):
    now = time.time()
    append_event("pd_notice_delivered", {"source": "amail", "arrival_id": "a1",
                                         "sent_at": now - 600, "via": "channel"})
    append_event("pd_notice_delivered", {"source": "amail", "arrival_id": "a2",
                                         "sent_at": now - 500, "via": "channel"})
    append_event("notice_received", {"notice_id": "a2"})
    append_event("dev_drv_started", {})
    _say_receipts()
    out = capsys.readouterr().out
    assert "1 notice(s) written to the channel in the last day were never received" in out
