"""The agent's login, checked from its stored expiry dates without a model turn (#884)."""
import json

import pytest

from macf.pd import login
from macf.pd import watch

NOW = 1_800_000_000.0
DAY = 86400.0


def _cred(ends_s, access="secret-access", refresh="secret-refresh"):
    oauth = {"accessToken": access, "refreshToken": refresh, "expiresAt": int((NOW + 3600) * 1000)}
    if ends_s is not None:
        oauth["refreshTokenExpiresAt"] = int(ends_s * 1000)
    return json.dumps({"claudeAiOauth": oauth})


@pytest.mark.parametrize("ends,state", [
    (NOW + 30 * DAY, "ok"),
    (NOW + 2 * DAY, "expiring"),
    (NOW - 12 * DAY, "expired"),
])
def test_the_verdict_comes_from_the_refresh_grants_end(ends, state):
    verdict = login.assess(_cred(ends), NOW)
    assert verdict["state"] == state
    assert verdict["refresh_expires_at"] == pytest.approx(ends, abs=0.001)
    assert "secret" not in json.dumps(verdict), "no token leaves the read"


@pytest.mark.parametrize("raw,why", [
    (None, "no credential reachable"),
    ("not json", "not the client's JSON"),
    (_cred(None), "no refresh expiry"),
])
def test_a_credential_that_cant_be_judged_reads_unknown(raw, why):
    verdict = login.assess(raw, NOW)
    assert verdict["state"] == "unknown" and why in verdict["detail"]


def test_the_daemon_records_at_start_on_a_change_and_once_a_day():
    events, clock = [], [0.0]
    verdicts = iter([{"state": "ok"}, {"state": "ok"}, {"state": "expiring"}, {"state": "expiring"}])
    check = login.HostedLoginCheck("Resident_1a2b3c", lambda e, d: events.append((e, d)),
                                   assess_now=lambda: next(verdicts), clock=lambda: clock[0])
    check.tick()                                    # at start: recorded
    clock[0] = login.POLL_S - 1
    check.tick()                                    # too soon to read again
    clock[0] = login.POLL_S
    check.tick()                                    # read, unchanged, under a day: not recorded
    clock[0] = 2 * login.POLL_S
    check.tick()                                    # changed: recorded
    clock[0] = 2 * login.POLL_S + login.RECORD_EVERY_S
    check.tick()                                    # unchanged, but a day since: recorded
    assert [d["state"] for _, d in events] == ["ok", "expiring", "expiring"]
    assert all(e == login.EVENT and d["agent"] == "Resident_1a2b3c" for e, d in events)


def test_a_check_that_raises_records_unknown_and_the_daemon_goes_on(capsys):
    events = []

    def broken():
        raise RuntimeError("boom")
    login.HostedLoginCheck("Resident_1a2b3c", lambda e, d: events.append(d), assess_now=broken,
                           clock=lambda: 0.0).tick()
    assert events[0]["state"] == "error"


def test_two_keychain_entries_judge_the_newest_not_silence(monkeypatch):
    """#936: a Mac commonly holds two entries under the one service, a newer "unknown" in use
    and the stale original (#852). Reading those as unknown made the check silent on every such
    Mac, both maintainers' included. The verdict comes from the newest entry, the login in use,
    which read_credential returns; agents sharing one macOS login share that one Claude login."""
    import macf.budget as budget
    monkeypatch.setattr(login.sys, "platform", "darwin")
    monkeypatch.setattr(budget, "keychain_accounts", lambda: ["unknown", "operator"])
    monkeypatch.setattr(budget, "read_credential", lambda: _cred(NOW - DAY))
    verdict = login.read_assessment(now=NOW)
    assert verdict["state"] == "expired", verdict["detail"]


def _event(ends):
    return {"timestamp": NOW - 3600, "event": login.EVENT,
            "data": {"agent": "Resident_1a2b3c", "state": "ok", "refresh_expires_at": ends}}


def test_the_watch_judges_the_recorded_end_against_now():
    """Recorded ok a day ago, but past its end now: expired, with how to reach the session."""
    f = watch.check_login("Resident_1a2b3c", _event(NOW - 60), NOW)
    assert f.verdict == "LOGIN-EXPIRED"
    assert "/login" in f.detail and "harness attach --card Resident_1a2b3c" in f.detail
    assert watch.check_login("Resident_1a2b3c", _event(NOW + DAY), NOW).verdict == "LOGIN-EXPIRING"
    assert watch.check_login("Resident_1a2b3c", _event(NOW + 30 * DAY), NOW).verdict == "ALIVE"
    assert watch.check_login("Resident_1a2b3c", None, NOW) is None, "no daemon here records logins"
    unknown = {"timestamp": NOW, "event": login.EVENT,
               "data": {"agent": "Resident_1a2b3c", "state": "unknown", "refresh_expires_at": None,
                        "detail": "no credential reachable"}}
    assert watch.check_login("Resident_1a2b3c", unknown, NOW) is None, \
        "a login with no date (an API key) is not a fault, and would page at every pass"
    broken = {**unknown, "data": {**unknown["data"], "state": "error", "detail": "the check failed: OSError"}}
    assert watch.check_login("Resident_1a2b3c", broken, NOW).verdict == "CHECK-FAILED", \
        "a check that itself broke is said"


def test_the_watch_finds_the_newest_login_event_of_this_agent(tmp_path):
    log = tmp_path / "log.jsonl"
    rows = [_event(NOW - 60), {**_event(NOW + 30 * DAY), "timestamp": NOW - 60},
            {"timestamp": NOW - 30, "event": login.EVENT,
             "data": {"agent": "Other_9f9f9f", "refresh_expires_at": NOW - 999}}]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    found = watch.last_login_event(log, "Resident_1a2b3c", NOW)
    assert found["data"]["refresh_expires_at"] == NOW + 30 * DAY


def test_the_warning_window_is_the_declarations_when_it_names_one():
    """A login ending in 5 days is ok by the default three-day window and expiring by a week's (#1027)."""
    raw = _cred(NOW + 5 * DAY)
    assert login.assess(raw, NOW)["state"] == "ok"
    assert login.assess(raw, NOW, expiring_s=7 * DAY)["state"] == "expiring"


def test_the_watch_warns_by_the_declarations_window_too():
    f = watch.check_login("Resident_1a2b3c", _event(NOW + 5 * DAY), NOW, expiring_s=7 * DAY)
    assert f.verdict == "LOGIN-EXPIRING"
    assert watch.check_login("Resident_1a2b3c", _event(NOW + 5 * DAY), NOW).verdict == "ALIVE"


def test_a_stand_in_for_the_daemons_check_still_works_with_the_default_window(monkeypatch, capsys):
    """Test suites replace login.daemon_assessment with a function taking nothing (#884), and the
    default window must keep calling it that way (#1027)."""
    monkeypatch.setattr(login, "daemon_assessment", lambda: {"state": "ok", "refresh_expires_at": None,
                                                             "hours_left": None, "detail": "stood in"})
    sent = []
    check = login.HostedLoginCheck("Resident_1a2b3c", lambda event, data: sent.append(data))
    check.tick()
    assert [d["state"] for d in sent] == ["ok"] and "failed" not in capsys.readouterr().err


def test_a_declared_window_reaches_the_daemons_check(monkeypatch):
    seen = []
    monkeypatch.setattr(login, "daemon_assessment", lambda expiring_s=login.EXPIRING_S:
                        seen.append(expiring_s) or {"state": "ok", "refresh_expires_at": None,
                                                    "hours_left": None, "detail": ""})
    login.HostedLoginCheck("Resident_1a2b3c", lambda event, data: None, expiring_s=7 * DAY).tick()
    assert seen == [7 * DAY]


# ---------------------------------------------------------------- the warning to the agent (#1161)

def _warning_check(hours_seq, ends_seq=None, warned_before=None, expiring_s=login.EXPIRING_S):
    """A check fed one verdict per poll, recording events and raised notices."""
    events, notices, clock = [], [], [0.0]
    ends_seq = ends_seq or [NOW + 30 * DAY] * len(hours_seq)
    verdicts = iter({"state": "x", "refresh_expires_at": e, "hours_left": h, "detail": ""}
                    for h, e in zip(hours_seq, ends_seq, strict=True))
    check = login.HostedLoginCheck("Resident_1a2b3c", lambda e, d: events.append((e, d)),
                                   assess_now=lambda: next(verdicts), clock=lambda: clock[0],
                                   expiring_s=expiring_s,
                                   raise_notice=lambda s, i: notices.append((s, i)),
                                   warned_before=warned_before)
    for n in range(len(hours_seq)):
        clock[0] = n * login.POLL_S
        check.tick()
    return events, notices


def test_the_agent_is_warned_once_at_the_window_at_a_day_and_at_the_end():
    hours = [100, 72, 71, 30, 24, 23, 1, 0, -5, -30]
    events, notices = _warning_check(hours)
    steps = [d["step"] for e, d in events if e == login.EVENT_WARNED]
    assert steps == [1, 2, 3], "one warning per step, never repeated while the step holds"
    assert [s for s, _ in notices] == [login.NOTICE] * 3
    assert [i.split(":")[1] for _, i in notices] == ["1", "2", "3"]


def test_a_login_first_seen_expired_is_warned_once_not_three_times():
    events, notices = _warning_check([-700, -701])
    assert [d["step"] for e, d in events if e == login.EVENT_WARNED] == [3]
    assert len(notices) == 1


def test_a_renewed_login_starts_its_steps_again():
    old, new = NOW + 2 * DAY, NOW + 30 * DAY
    events, notices = _warning_check([48, 700, 70], ends_seq=[old, new, new])
    assert [d["step"] for e, d in events if e == login.EVENT_WARNED] == [1, 1]
    assert len(notices) == 2
    # Each grant's warning has its own arrival id: a renewed grant's first step must not reuse the
    # old grant's, or a reader keyed on the id takes the new warning for one already delivered
    # (Ira's review of #1162).
    assert notices[0][1] != notices[1][1]


def test_a_restart_reads_back_the_warning_already_given():
    ends = NOW + 30 * DAY
    earlier = [{"event": login.EVENT_WARNED, "data": {"agent": "Someone_else", "step": 0, "refresh_expires_at": ends}},
               {"event": login.EVENT_WARNED, "data": {"agent": "Resident_1a2b3c", "step": 2,
                                                      "refresh_expires_at": ends}}]
    events, notices = _warning_check([20, 10, -1], warned_before=lambda: iter(earlier))
    assert [d["step"] for e, d in events if e == login.EVENT_WARNED] == [3], "step 2 was already given"


def test_a_verdict_with_no_date_warns_of_nothing():
    events, notices = [], []
    verdicts = iter([{"state": "unknown", "refresh_expires_at": None, "hours_left": None, "detail": ""}])
    login.HostedLoginCheck("Resident_1a2b3c", lambda e, d: events.append(e), assess_now=lambda: next(verdicts),
                           raise_notice=lambda s, i: notices.append(i)).tick()
    assert notices == [] and login.EVENT_WARNED not in events


@pytest.mark.parametrize("window,steps", [
    (7 * DAY, [7 * DAY, DAY, 0.0]),
    (DAY, [DAY, 0.0]),
    (0.0, [0.0]),
])
def test_the_steps_follow_the_declared_window(window, steps):
    assert login.warn_steps(window) == steps


def test_the_warning_is_recorded_before_its_notice_is_raised():
    order = []
    verdicts = iter([{"state": "expiring", "refresh_expires_at": NOW, "hours_left": 10, "detail": ""}])
    login.HostedLoginCheck("Resident_1a2b3c", lambda e, d: order.append(e), assess_now=lambda: next(verdicts),
                           raise_notice=lambda s, i: order.append("notice")).tick()
    assert order.index(login.EVENT_WARNED) < order.index("notice")


def test_the_channel_and_the_notifier_both_carry_the_login_notice():
    from macf.pd.notifier import INTERNAL_SOURCES, channel_takes
    assert login.NOTICE in INTERNAL_SOURCES
    assert channel_takes(login.NOTICE, f"login:3:{int(NOW)}")
