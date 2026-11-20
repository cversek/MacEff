"""Remote Control disconnects, recognized in the session transcript and alerted from outside it (#883).

When Remote Control drops, the session goes quiet for anyone away from its terminal, and the
only sign was one line in the pane. The client writes every disconnect into the transcript as a
``system``/``informational`` record, ``Remote Control disconnected — <reason> — run /<command>``,
and writes nothing when Remote Control comes back. The texts below are the eight such records in
one host session's transcript between 2026-09-23 and 2026-11-03, verbatim.
"""
import json

import pytest

from macf.pd import interface as pdi
from macf.pd import watch
from macf.transcript_monitor.remote_control import (EVENT_DISCONNECTED, EVENT_REMEDIED, RemoteControlWatch,
                                                    classify)

CARD = "Resident_1a2b3c"
NOW = 1_800_000_000.0

ENDED_GONE = ("Remote Control disconnected — the server no longer reports this session — it may have been "
              "deleted from another device or app (code 4090)")
ENDED_ARCHIVED = "Remote Control disconnected — this session was ended or archived from another device or app (code 4090)"
NO_TOKEN = "Remote Control disconnected — OAuth token unavailable — run /login to restore Remote Control"
JWT = "Remote Control disconnected — JWT refresh failed: no OAuth token — run /login"
EXPIRED = "Remote Control disconnected — Claude.ai login expired — run /login to restore Remote Control"
UNREACHABLE = ("Remote Control disconnected — could not reach the Remote Control server for about 30 minutes — "
               "run /remote-control to reconnect")
NO_RECONNECT = ("Remote Control disconnected — Couldn't reconnect to your Remote Control session. Retry, or start "
                "a fresh session without --resume. — run /remote-control to reconnect")


def _disconnect(text, ts="2026-11-03T12:45:46.947Z"):
    return {"type": "system", "subtype": "informational", "level": "warning", "content": text, "timestamp": ts}


def _command(name):
    return (f"<command-name>/{name}</command-name>\n            <command-message>{name}</command-message>\n"
            f"            <command-args></command-args>")


def _local(content, ts="2026-11-03T15:26:16.658Z"):
    return {"type": "system", "subtype": "local_command", "content": content, "timestamp": ts}


def _typed(content, ts="2026-11-03T15:26:16.658Z"):
    return {"type": "user", "message": {"role": "user", "content": content}, "timestamp": ts}


LOGIN_OK = _local("<local-command-stdout>Login successful</local-command-stdout>")


@pytest.mark.parametrize("text, kind, remedy, reason", [
    (ENDED_GONE, "ended", "/remote-control",
     "the server no longer reports this session — it may have been deleted from another device or app (code 4090)"),
    (ENDED_ARCHIVED, "ended", "/remote-control",
     "this session was ended or archived from another device or app (code 4090)"),
    (NO_TOKEN, "login", "/login", "OAuth token unavailable"),
    (JWT, "login", "/login", "JWT refresh failed: no OAuth token"),
    (EXPIRED, "login", "/login", "Claude.ai login expired"),
    (UNREACHABLE, "network", "/remote-control", "could not reach the Remote Control server for about 30 minutes"),
    (NO_RECONNECT, "network", "/remote-control",
     "Couldn't reconnect to your Remote Control session. Retry, or start a fresh session without --resume."),
])
def test_each_recorded_disconnect_is_classified_with_its_remedy(text, kind, remedy, reason):
    assert classify(text) == {"kind": kind, "remedy": remedy, "reason": reason}


def test_other_records_are_not_disconnects():
    assert classify("Compacted while idle, before the prompt cache expired") is None
    assert classify("") is None
    # A record of the same prefix in a wording not seen yet still counts, with no remedy guessed.
    assert classify("Remote Control disconnected — something new") == {
        "kind": "unknown", "remedy": None, "reason": "something new"}


def test_a_disconnect_is_recorded_once_with_what_to_do():
    rc = RemoteControlWatch(CARD)
    assert rc.state() is None
    found = rc(_disconnect(NO_TOKEN, ts="2026-09-25T00:37:07.480Z"))
    assert found.event_name == EVENT_DISCONNECTED
    assert found.data["agent"] == CARD
    assert found.data["kind"] == "login" and found.data["remedy"] == "/login"
    assert found.data["reason"] == "OAuth token unavailable"
    assert found.data["said"] == NO_TOKEN and found.data["timestamp"] == "2026-09-25T00:37:07.480Z"
    assert rc.state()["kind"] == "login"
    # The client wrote two records a second apart on 09-25; the second is the same stretch.
    assert rc(_disconnect(JWT, ts="2026-09-25T00:37:08.376Z")) is None


def test_a_login_disconnect_clears_only_on_a_successful_login():
    rc = RemoteControlWatch(CARD)
    rc(_disconnect(JWT))
    assert rc(_local(_command("remote-control"))) is None, "/remote-control can't restore a login"
    assert rc(_typed(_command("login"))) is None, "a /login typed is not yet a login that worked"
    assert rc(_local("<local-command-stdout>Login interrupted</local-command-stdout>")) is None
    found = rc(LOGIN_OK)
    assert found.event_name == EVENT_REMEDIED
    assert found.data["via"] == "/login" and found.data["agent"] == CARD
    assert rc.state() is None
    assert rc(LOGIN_OK) is None, "nothing to clear"


@pytest.mark.parametrize("text", [UNREACHABLE, NO_RECONNECT, ENDED_ARCHIVED])
def test_a_network_or_ended_disconnect_clears_on_remote_control_or_a_login(text):
    for record, via in [(_local(_command("remote-control")), "/remote-control"),
                        (_typed(_command("remote-control")), "/remote-control"),
                        (LOGIN_OK, "/login")]:
        rc = RemoteControlWatch(CARD)
        rc(_disconnect(text))
        found = rc(record)
        assert found is not None and found.event_name == EVENT_REMEDIED and found.data["via"] == via


def test_a_new_kind_of_disconnect_while_one_is_open_is_recorded():
    """A network drop that becomes a login failure needs a different remedy, so it is said."""
    rc = RemoteControlWatch(CARD)
    rc(_disconnect(UNREACHABLE))
    found = rc(_disconnect(EXPIRED))
    assert found is not None and found.data["kind"] == "login"
    assert rc(_local(_command("remote-control"))) is None


def _event(name, age_s, agent=CARD, **data):
    return {"timestamp": NOW - age_s, "event": name, "data": {"agent": agent, **data}}


def test_the_watch_reads_an_open_disconnect_as_unhealthy_and_a_remedy_as_alive():
    opened = _event(EVENT_DISCONNECTED, 9000, kind="login", remedy="/login", reason="JWT refresh failed: no OAuth token")
    f = watch.check_remote_control(CARD, opened, NOW)
    assert f.verdict == "RC-DISCONNECTED" and f.subject == "remote-control"
    assert "2 h 30 min" in f.detail and "JWT refresh failed: no OAuth token" in f.detail
    assert "run /login in its session" in f.detail and f"harness attach --card {CARD}" in f.detail
    assert watch.check_remote_control(CARD, _event(EVENT_REMEDIED, 60, via="/login"), NOW).verdict == "ALIVE"
    assert watch.check_remote_control(CARD, None, NOW).verdict == "ALIVE"
    unknown = _event(EVENT_DISCONNECTED, 60, kind="unknown", remedy=None, reason="something new")
    assert "run /login or /remote-control" in watch.check_remote_control(CARD, unknown, NOW).detail
    assert watch.exit_code([f]) == watch.EXIT_UNHEALTHY


def test_the_watch_finds_the_newest_remote_control_event_of_this_agent(tmp_path):
    log = tmp_path / "log.jsonl"
    rows = [_event(EVENT_DISCONNECTED, 600, kind="network", remedy="/remote-control", reason="r"),
            _event(EVENT_REMEDIED, 300, via="/remote-control"),
            _event(EVENT_DISCONNECTED, 100, agent="Other_9f9f9f", kind="login", remedy="/login", reason="x")]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert watch.last_remote_control_event(log, CARD, NOW)["event"] == EVENT_REMEDIED
    assert watch.last_remote_control_event(log, "Other_9f9f9f", NOW)["event"] == EVENT_DISCONNECTED
    assert watch.last_remote_control_event(log, CARD, NOW, lookback_s=200) is None


def _session_home(root):
    home = root / "Resident"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000")
    pdi.declaration_path(home).write_text(json.dumps({"version": 1, "agent": "Resident", "units": [
        {"name": "session", "kind": "session", "command": ["true"], "account": "resident", "restart": "always",
         "liveness_interval_s": 120.0, "memory_limit_mb": 64}]}))
    return home


def test_one_alert_off_the_session_and_one_recovery(tmp_path):
    """The alert goes by the watch's own command, never the session's channel, which is the one
    that broke (MIS-0002-R75): once when the disconnect opens, once when its remedy is run."""
    import sys
    home, sink = _session_home(tmp_path), tmp_path / "sink.txt"
    log = home / ".maceff" / "agent_events_log.jsonl"
    command = [sys.executable, "-c", f"import sys; open({str(sink)!r}, 'a').write(sys.stdin.read())"]
    config = watch.render_config([home], command, tmp_path / "state")
    with log.open("a") as fh:
        fh.write(json.dumps(_event(EVENT_DISCONNECTED, 60, kind="login", remedy="/login",
                                   reason="JWT refresh failed: no OAuth token")) + "\n")
    watch.run_pass(config, now=NOW, probe=None)
    watch.run_pass(config, now=NOW + 120, probe=None)
    text = sink.read_text()
    assert text.count("remote-control: RC-DISCONNECTED") == 1
    with log.open("a") as fh:
        fh.write(json.dumps(_event(EVENT_REMEDIED, -150, via="/login")) + "\n")
    watch.run_pass(config, now=NOW + 240, probe=None)
    assert "recovered: Resident_1a2b3c remote-control: ALIVE" in sink.read_text()


def test_every_session_monitor_watches_remote_control(tmp_path, monkeypatch):
    """The detector is only useful on the monitor that follows a session, under the agent's card."""
    from macf.transcript_monitor import daemon
    monkeypatch.setattr(daemon, "_own_card", lambda: CARD)
    monitor, _ = daemon._session_monitor(tmp_path / "session.jsonl", 1.0, 0, session_env={})
    watches = [d for d in monitor.detectors if isinstance(d, RemoteControlWatch)]
    assert len(watches) == 1 and watches[0].card == CARD


def test_a_later_disconnect_means_it_had_come_back_unrecorded():
    """A disconnect happens only to a connection, so one written well after another shows that
    Remote Control came back in between, which the client never records. On one host's
    transcript a login disconnect of 09-25 had no remedy before another on 10-04; reading the
    second as the same stretch would have swallowed its alert."""
    rc = RemoteControlWatch(CARD)
    rc(_disconnect(NO_TOKEN, ts="2026-09-25T00:37:07.480Z"))
    found = rc(_disconnect(EXPIRED, ts="2026-10-04T06:03:54.160Z"))
    assert found is not None and found.event_name == EVENT_DISCONNECTED
    assert found.data["after_unrecorded_reconnect"] is True
    first = RemoteControlWatch(CARD)(_disconnect(JWT))
    assert first.data["after_unrecorded_reconnect"] is False


def test_the_watch_alerts_again_for_a_disconnect_newer_than_its_open_stretch(tmp_path):
    import sys
    home, sink = _session_home(tmp_path), tmp_path / "sink.txt"
    log = home / ".maceff" / "agent_events_log.jsonl"
    command = [sys.executable, "-c", f"import sys; open({str(sink)!r}, 'a').write(sys.stdin.read())"]
    config = watch.render_config([home], command, tmp_path / "state")
    with log.open("a") as fh:
        fh.write(json.dumps(_event(EVENT_DISCONNECTED, 60, kind="login", remedy="/login", reason="first")) + "\n")
    watch.run_pass(config, now=NOW, probe=None)
    with log.open("a") as fh:
        fh.write(json.dumps(_event(EVENT_DISCONNECTED, -500, kind="login", remedy="/login", reason="second",
                                   after_unrecorded_reconnect=True)) + "\n")
    watch.run_pass(config, now=NOW + 600, probe=None)
    watch.run_pass(config, now=NOW + 720, probe=None)
    text = sink.read_text()
    assert text.count("RC-DISCONNECTED") == 2 and "second" in text


def _write(path, entries, tail=""):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries) + tail)


def test_a_watch_started_after_a_disconnect_still_records_the_remedy(tmp_path):
    """The session monitor starts at the end of the transcript, so a daemon restart between a disconnect
    and its /login left the new watch with nothing open: no remedy was recorded and the outside watch
    reported the disconnect for the rest of its lookback (THM's review of #1054)."""
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_disconnect(NO_TOKEN)])
    watch_ = RemoteControlWatch(CARD)
    watch_.prime(transcript)
    assert watch_.state() is not None and watch_.state()["kind"] == "login"
    done = watch_(LOGIN_OK)
    assert done is not None and done.event_name == EVENT_REMEDIED and watch_.state() is None


def test_priming_reports_nothing_and_a_remedied_disconnect_leaves_nothing_open(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_disconnect(NO_TOKEN), LOGIN_OK], tail='{"type": "system", "subt')   # a half-written last line
    watch_ = RemoteControlWatch(CARD)
    assert watch_.prime(transcript) == 2
    assert watch_.state() is None


def test_priming_reads_only_the_end_of_a_large_transcript(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_disconnect(NO_TOKEN)] + [_typed("x" * 200)] * 50)
    watch_ = RemoteControlWatch(CARD)
    watch_.prime(transcript, max_bytes=2000)      # the disconnect is before what is read
    assert watch_.state() is None


def test_every_session_monitor_primes_its_watch_from_the_transcript(tmp_path, monkeypatch):
    from macf.transcript_monitor import daemon
    transcript = tmp_path / "session.jsonl"
    _write(transcript, [_disconnect(NO_TOKEN)])
    monkeypatch.setattr(daemon, "_own_card", lambda: CARD)
    monitor, _ = daemon._session_monitor(transcript, 1.0, 0, session_env={})
    watches = [d for d in monitor.detectors if isinstance(d, RemoteControlWatch)]
    assert watches[0].state() is not None
