"""What the sender sends the operator, and when (the scheduler design, 4.3 and 5.5)."""
from datetime import datetime, timezone

from macf.pd.sender import due_sends

UTC = timezone.utc
ME = "Tester@abc123"


def at(text):
    return datetime.fromisoformat(text + ":00+00:00")


def remind(entry_id, when, **extra):
    return {"agent": ME, "id": entry_id, "when": when, "zone": "UTC", "start": "2026-10-19T08:00:00+00:00",
            "action": "remind", "purpose": "the weekly audit is due", "state": "active", **extra}


ACCEPTED = {"accepted_at": "2026-10-19T08:30:00+00:00"}


def test_an_accepted_reminder_is_sent_once_with_its_text():
    """At its time an accepted reminder sends its purpose, under an id the ledger keeps, and an id
    already sent is never sent again (the design, 4.3)."""
    entry = remind("e-000000000001", "cron:0 9 * * *", **ACCEPTED)
    first = due_sends([entry], sent=[], last_sent={}, now=at("2026-10-19 09:00"))
    assert [(s.id, s.text) for s in first] == [("e-000000000001@1792400400", "the weekly audit is due")]
    assert due_sends([entry], sent=[first[0].id], last_sent={}, now=at("2026-10-19 09:00")) == []


def test_a_missed_reminder_is_sent_once_late_for_its_newest_instant():
    entry = remind("e-000000000001", "cron:0 9 * * *", **ACCEPTED)
    sends = due_sends([entry], sent=[], last_sent={"e-000000000001": at("2026-10-19 09:00")},
                      now=at("2026-10-22 12:00"))
    assert len(sends) == 1 and sends[0].text.startswith("Late, due 2026-10-22T09:00:00+00:00: ")


def test_an_agents_text_never_leaves_unaccepted():
    """A waiting entry sends a fixed template naming it, never its purpose, once. An agent's
    reminder with no acceptance sends nothing; the operator's own sends its text."""
    waiting = remind("e-000000000002", "cron:0 9 * * *", state="waiting", marked=["a web fetch"])
    unaccepted = remind("e-000000000003", "cron:0 9 * * *")
    mine = remind("e-000000000004", "cron:0 9 * * *", agent="operator")
    sends = due_sends([waiting, unaccepted, mine], sent=[], last_sent={}, now=at("2026-10-19 09:00"))
    assert [s.id for s in sends] == ["e-000000000002@accept", "e-000000000004@1792400400"]
    assert "the weekly audit" not in sends[0].text and "a web fetch" in sends[0].text
    assert sends[1].text == "the weekly audit is due"
    assert due_sends([waiting], sent=["e-000000000002@accept"], last_sent={}, now=at("2026-10-19 10:00")) == []


def test_quiet_hours_hold_all_but_an_urgent_entry():
    calm = remind("e-000000000001", "cron:0 2 * * *", **ACCEPTED)
    urgent = remind("e-000000000002", "cron:0 2 * * *", quiet="urgent", **ACCEPTED)
    night = lambda now: at("2026-10-20 07:00")             # noqa: E731 - a quiet window to 07:00
    sends = due_sends([calm, urgent], sent=[], last_sent={}, now=at("2026-10-20 02:00"), quiet_until=night)
    assert [s.id.split("@")[0] for s in sends] == ["e-000000000002"]


def test_past_its_daily_bound_an_owner_gets_one_line_saying_so():
    entries = [remind(f"e-00000000000{i}", "cron:0 9 * * *", **ACCEPTED) for i in range(1, 5)]
    sends = due_sends(entries, sent=[], last_sent={}, now=at("2026-10-19 09:00"), bound=2)
    assert [s.id for s in sends][:2] == ["e-000000000001@1792400400", "e-000000000002@1792400400"]
    assert [s.id for s in sends][2:] == [f"rate:{ME}:2026-10-19"]
    assert due_sends(entries[2:], sent=[f"rate:{ME}:2026-10-19"], last_sent={}, now=at("2026-10-19 09:00"),
                     sent_today={ME: 2}, bound=2) == []
