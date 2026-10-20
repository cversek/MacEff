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
    first = due_sends([entry], sent=[], now=at("2026-10-19 09:00"))
    assert [(s.id, s.text) for s in first] == [("e-000000000001@1792400400", "the weekly audit is due")]
    assert due_sends([entry], sent=[first[0].id], now=at("2026-10-19 09:00")) == []


def test_a_missed_reminder_is_sent_once_late_for_its_newest_instant():
    entry = remind("e-000000000001", "cron:0 9 * * *", **ACCEPTED)
    sends = due_sends([entry], sent=["e-000000000001@1792400400"], now=at("2026-10-22 12:00"))
    assert len(sends) == 1 and sends[0].text.startswith("Late, due 2026-10-22T09:00:00+00:00: ")


def test_an_agents_text_never_leaves_unaccepted():
    """A waiting entry sends a fixed template naming it, never its purpose, once. An agent's
    reminder with no acceptance sends nothing; the operator's own sends its text."""
    waiting = remind("e-000000000002", "cron:0 9 * * *", state="waiting", marked=["a web fetch"])
    unaccepted = remind("e-000000000003", "cron:0 9 * * *")
    mine = remind("e-000000000004", "cron:0 9 * * *", agent="operator")
    sends = due_sends([waiting, unaccepted, mine], sent=[], now=at("2026-10-19 09:00"))
    assert [s.id for s in sends] == ["e-000000000002@accept", "e-000000000004@1792400400"]
    assert "the weekly audit" not in sends[0].text and "a web fetch" in sends[0].text
    assert sends[1].text == "the weekly audit is due"
    assert due_sends([waiting], sent=["e-000000000002@accept"], now=at("2026-10-19 10:00")) == []


def test_quiet_hours_hold_all_but_an_urgent_entry():
    calm = remind("e-000000000001", "cron:0 2 * * *", **ACCEPTED)
    urgent = remind("e-000000000002", "cron:0 2 * * *", quiet="urgent", **ACCEPTED)
    def night(now):                                         # a quiet window to 07:00
        return at("2026-10-20 07:00")
    sends = due_sends([calm, urgent], sent=[], now=at("2026-10-20 02:00"), quiet_until=night)
    assert [s.id.split("@")[0] for s in sends] == ["e-000000000002"]


def test_past_its_daily_bound_an_owner_gets_one_line_saying_so():
    entries = [remind(f"e-00000000000{i}", "cron:0 9 * * *", **ACCEPTED) for i in range(1, 5)]
    sends = due_sends(entries, sent=[], now=at("2026-10-19 09:00"), bound=2)
    assert [s.id for s in sends][:2] == ["e-000000000001@1792400400", "e-000000000002@1792400400"]
    assert [s.id for s in sends][2:] == [f"rate:{ME}:2026-10-19"]
    assert due_sends(entries[2:], sent=[f"rate:{ME}:2026-10-19"], now=at("2026-10-19 09:00"),
                     sent_today={ME: 2}, bound=2) == []


def _home_with(tmp_path, *events):
    import json

    from test_primal_daemon import make_home
    home = make_home(tmp_path, [])
    with (home / ".maceff" / "agent_events_log.jsonl").open("a") as fh:
        for kind, data in events:
            fh.write(json.dumps({"event": kind, "data": data}) + "\n")
    return home


def _alert(tmp_path, code_file):
    """An alert command that appends what it's given to a file and exits with the code in
    ``code_file``, so a test can make it refuse."""
    import sys
    out = tmp_path / "phone.txt"
    ledger = tmp_path / "state" / "sent.jsonl"
    script = ("import sys, pathlib; open(sys.argv[1], 'a').write(sys.stdin.read()); "
              "open(sys.argv[3], 'a').write(pathlib.Path(sys.argv[4]).read_text()); "
              "sys.exit(int(pathlib.Path(sys.argv[2]).read_text()))")
    return [sys.executable, "-c", script, str(out), str(code_file), str(tmp_path / "seen"), str(ledger)], out


def test_the_runner_sends_each_reminder_once_through_the_alert_command(tmp_path):
    """Across passes, a due reminder reaches the alert command once, with a header naming its
    owner. A refused send is tried again; one whose outcome was never written counts as sent,
    so the operator never gets two (the design, 4.3)."""
    import json

    from macf.pd.entries import EVENT_ENTRY_ADDED, EVENT_ENTRY_REMOVED
    from macf.pd.sender import LEDGER, SenderConfig, run_pass
    from test_primal_daemon import CARD
    code = tmp_path / "code"
    code.write_text("1")
    command, phone = _alert(tmp_path, code)
    home = _home_with(
        tmp_path,
        (EVENT_ENTRY_ADDED, {**remind("e-000000000001", "cron:0 9 * * *", **ACCEPTED), "agent": CARD}),
        (EVENT_ENTRY_ADDED, {**remind("e-000000000002", "cron:0 9 * * *", **ACCEPTED), "agent": CARD}),
        (EVENT_ENTRY_REMOVED, {"agent": CARD, "id": "e-000000000002"}),                # removed
        (EVENT_ENTRY_ADDED, {**remind("e-000000000003", "cron:0 9 * * *", **ACCEPTED), "agent": "Other@def456"}))
    config = SenderConfig(homes=[str(home)], alert_command=command, state_dir=str(tmp_path / "state"))
    assert run_pass(config, at("2026-10-19 09:00")) == 0          # refused: nothing counts as sent
    code.write_text("0")
    assert run_pass(config, at("2026-10-19 09:00")) == 1
    assert run_pass(config, at("2026-10-19 09:05")) == 0          # never twice
    assert phone.read_text().count("the weekly audit is due") == 2   # the refused try, then the send
    assert f"MacEff reminder from {CARD}" in phone.read_text()
    assert '"state": "sending"' in (tmp_path / "seen").read_text()   # recorded before the command ran

    ledger = tmp_path / "state" / LEDGER
    with ledger.open("a") as fh:                                  # died while sending the 20th's
        fh.write(json.dumps({"id": "e-000000000001@1792486800", "owner": CARD, "day": "2026-10-20",
                             "state": "sending", "ts": 0}) + "\n")
    assert run_pass(config, at("2026-10-20 09:00")) == 0


def test_quiet_hours_by_weekday_and_date():
    """A window is read in the sender's zone on the days it starts, past midnight when its end
    comes first; a quiet date is quiet all day (the design, 4.3)."""
    from zoneinfo import ZoneInfo

    from macf.pd.sender import QuietWindow, SenderConfig, quiet_until
    new_york = ZoneInfo("America/New_York")
    config = SenderConfig(homes=[], alert_command=["true"], state_dir="s", timezone="America/New_York",
                          quiet=[QuietWindow(start="22:00", end="07:00", days=["MO", "TU", "WE", "TH", "SU"]),
                                 QuietWindow(start="12:00", end="13:00", days=["SA"])],
                          quiet_dates=["2026-12-25"])

    def local(text):
        return datetime.fromisoformat(text).replace(tzinfo=new_york)
    assert quiet_until(config, local("2026-10-19T23:30")) == local("2026-10-20T07:00")   # Monday night
    assert quiet_until(config, local("2026-10-20T06:59")) == local("2026-10-20T07:00")   # Monday's, past midnight
    assert quiet_until(config, local("2026-10-20T07:00")) is None
    assert quiet_until(config, local("2026-10-23T23:30")) is None                        # Friday isn't quiet
    assert quiet_until(config, local("2026-10-24T06:00")) is None                        # nor Friday's night
    assert quiet_until(config, local("2026-10-24T12:30")) == local("2026-10-24T13:00")   # Saturday noon
    assert quiet_until(config, local("2026-12-25T15:00")) == local("2026-12-26T00:00")
    assert quiet_until(config, at("2026-10-19 00:00")) is None   # given in UTC: Sunday 20:00 in New York


def test_the_runner_holds_a_reminder_through_quiet_hours(tmp_path):
    """Due at 02:00 inside the quiet window, a reminder waits for its end and goes then, saying
    it's late."""
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.sender import QuietWindow, SenderConfig, run_pass
    from test_primal_daemon import CARD
    code = tmp_path / "code"
    code.write_text("0")
    command, phone = _alert(tmp_path, code)
    home = _home_with(tmp_path, (EVENT_ENTRY_ADDED, {**remind("e-000000000001", "cron:0 2 * * *", **ACCEPTED),
                                                     "agent": CARD}))
    config = SenderConfig(homes=[str(home)], alert_command=command, state_dir=str(tmp_path / "state"),
                          quiet=[QuietWindow(start="22:00", end="07:00")])
    assert run_pass(config, at("2026-10-20 02:00")) == 0
    assert run_pass(config, at("2026-10-20 07:00")) == 1
    assert "Late, due 2026-10-20T02:00:00+00:00" in phone.read_text()
