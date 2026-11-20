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
