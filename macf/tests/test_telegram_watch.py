"""The outside watch reads a Telegram poller's liveness from the plugin's own files (#1069).

The poller writes ``bot.pid`` and a ``diag.jsonl`` whose records carry ``ts``, ``pid``,
``event`` and, every 60 s, a ``heartbeat``. A poller that ended unnoticed left the session
running without its operator's phone; each test is one way the files say so, or say it lives.
"""
import json
from datetime import datetime, timezone

import pytest

from macf.pd import interface as pdi
from macf.pd import watch

NOW = 1_800_000_000.0
CARD = "Resident_1a2b3c"
POLLER = 4242


def _iso(age_s):
    return datetime.fromtimestamp(NOW - age_s, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _state(tmp_path, pid=POLLER, beats=(30,), other_pid_beats=(), raw_pid=None):
    """A plugin state directory: bot.pid and a diag.jsonl with heartbeats *beats* seconds old."""
    d = tmp_path / "telegram"
    d.mkdir()
    (d / "bot.pid").write_text(str(pid) if raw_pid is None else raw_pid)
    lines = [{"ts": _iso(age), "pid": pid, "ppid": 1, "uptime_s": 9, "event": "heartbeat"} for age in beats]
    lines += [{"ts": _iso(age), "pid": 7, "ppid": 1, "uptime_s": 9, "event": "heartbeat"} for age in other_pid_beats]
    if beats or other_pid_beats:
        (d / "diag.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sorted(lines, key=lambda r: r["ts"])))
    return d


def _alive(*pids):
    return lambda pid: pid in pids


def test_a_running_poller_with_a_recent_heartbeat_is_alive(tmp_path):
    f = watch.check_telegram(CARD, _state(tmp_path, beats=(150, 90, 30)), NOW, _alive(POLLER))
    assert (f.subject, f.verdict) == ("telegram", "ALIVE"), f


def test_a_poller_that_is_gone_reads_down_with_the_remedy(tmp_path):
    f = watch.check_telegram(CARD, _state(tmp_path), NOW, _alive())
    assert f.verdict == "POLLER-DOWN" and f"pid {POLLER}" in f.detail
    assert "/mcp" in f.detail and CARD in f.detail


def test_a_running_poller_gone_silent_reads_down(tmp_path):
    f = watch.check_telegram(CARD, _state(tmp_path, beats=(600, 540)), NOW, _alive(POLLER))
    assert f.verdict == "POLLER-DOWN" and "last heartbeat" in f.detail


def test_a_reused_pid_with_only_another_pollers_heartbeats_reads_down(tmp_path):
    """bot.pid names a pid some other process now holds: the heartbeats in the file are not its."""
    f = watch.check_telegram(CARD, _state(tmp_path, beats=(), other_pid_beats=(20,)), NOW, _alive(POLLER))
    assert f.verdict == "POLLER-DOWN" and "no heartbeat" in f.detail


def test_a_heartbeat_just_inside_the_window_is_alive_and_just_past_it_is_not(tmp_path):
    inside = watch.check_telegram(CARD, _state(tmp_path, beats=(watch.POLLER_SILENT_S - 1,)), NOW, _alive(POLLER))
    assert inside.verdict == "ALIVE"
    past = tmp_path / "past"
    past.mkdir()
    outside = watch.check_telegram(CARD, _state(past, beats=(watch.POLLER_SILENT_S + 1,)), NOW, _alive(POLLER))
    assert outside.verdict == "POLLER-DOWN"


def test_no_pid_file_or_a_garbled_one_is_unknown_never_healthy(tmp_path):
    missing = watch.check_telegram(CARD, tmp_path / "nowhere", NOW, _alive(POLLER))
    assert missing.verdict == "CHECK-FAILED" and "bot.pid" in missing.detail
    garbled = tmp_path / "g"
    garbled.mkdir()
    assert watch.check_telegram(CARD, _state(garbled, raw_pid="not-a-pid"), NOW, _alive(POLLER)).verdict == "CHECK-FAILED"


def test_a_running_poller_without_a_diag_file_is_alive_and_says_why(tmp_path):
    f = watch.check_telegram(CARD, _state(tmp_path, beats=()), NOW, _alive(POLLER))
    assert f.verdict == "ALIVE" and "no diag.jsonl" in f.detail


def test_a_partial_last_line_is_skipped_not_fatal(tmp_path):
    d = _state(tmp_path, beats=(30,))
    with (d / "diag.jsonl").open("a") as fh:
        fh.write('{"ts": "2026-11-2')                       # the poller is mid-write
    assert watch.check_telegram(CARD, d, NOW, _alive(POLLER)).verdict == "ALIVE"


def test_a_newest_heartbeat_with_an_unreadable_stamp_falls_back_to_an_older_one(tmp_path):
    d = _state(tmp_path, beats=(30,))
    with (d / "diag.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": "not a time", "pid": POLLER, "event": "heartbeat"}) + "\n")
    assert watch.check_telegram(CARD, d, NOW, _alive(POLLER)).verdict == "ALIVE"      # the older, readable one
    stale = tmp_path / "s"
    stale.mkdir()
    d2 = _state(stale, beats=(600,))
    with (d2 / "diag.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": "not a time", "pid": POLLER, "event": "heartbeat"}) + "\n")
    assert watch.check_telegram(CARD, d2, NOW, _alive(POLLER)).verdict == "POLLER-DOWN"   # never healthy on garbage


def test_the_new_verdict_has_an_exit_code():
    f = watch.Finding(CARD, "telegram", "POLLER-DOWN", "x")
    assert watch.exit_code([f]) == watch.EXIT_UNHEALTHY


def _settings(home, name, body):
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / name).write_text(body if isinstance(body, str) else json.dumps(body))


def test_the_state_dir_comes_from_the_homes_settings_before_anything_else(tmp_path):
    home = tmp_path / "seat"
    _settings(home, "settings.json", {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "shared")}})
    _settings(home, "settings.local.json", {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "own")}})
    env = {watch.TELEGRAM_STATE_ENV: str(tmp_path / "process")}
    assert watch.telegram_state_dir(home, env) == (tmp_path / "own", "settings.local.json of the home")
    (home / ".claude" / "settings.local.json").unlink()
    assert watch.telegram_state_dir(home, env) == (tmp_path / "shared", "settings.json of the home")
    (home / ".claude" / "settings.json").unlink()
    assert watch.telegram_state_dir(home, env) == (tmp_path / "process", "the watch's environment")
    path, source = watch.telegram_state_dir(home, {})
    assert path.parts[-3:] == (".claude", "channels", "telegram") and source == "the default location"


def test_a_settings_file_without_the_key_or_unreadable_falls_through_and_says_so(tmp_path, capsys):
    home = tmp_path / "seat"
    _settings(home, "settings.local.json", {"permissions": {"allow": []}, "env": {"OTHER": "x"}})
    _settings(home, "settings.json", "{not json")
    path, source = watch.telegram_state_dir(home, {watch.TELEGRAM_STATE_ENV: str(tmp_path / "process")})
    assert (path, source) == (tmp_path / "process", "the watch's environment")
    assert "settings.json" in capsys.readouterr().err        # the unreadable one is said, not guessed past


def test_an_isolated_seat_whose_settings_name_its_directory_is_judged_by_that_directory(tmp_path):
    """CTB's finding on the first version: the seat's directory is set in its settings, which the watch's
    own environment never holds, so every isolated seat read CHECK-FAILED from the default directory."""
    import os
    home = _home(tmp_path, ["plugin:telegram:telegram"])
    seat_dir = _state(tmp_path, pid=os.getpid(), beats=(20,))
    _settings(home, "settings.local.json", {"env": {watch.TELEGRAM_STATE_ENV: str(seat_dir)}})
    (f,) = _telegram_findings(watch.check_home(home, NOW, probe=lambda pid, start: True))
    assert f.verdict == "ALIVE", f
    assert "settings.local.json of the home" in f.detail      # the finding says whose files were read


def _home(tmp_path, channels):
    home = tmp_path / "Resident"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000")
    declaration = {"version": 1, "agent": "Resident", "units": [
        {"name": "broker", "command": ["true"], "account": "resident", "restart": "always",
         "liveness_interval_s": 600.0, "memory_limit_mb": 64}]}
    if channels is not None:
        declaration["operator_channels"] = channels
    pdi.declaration_path(home).write_text(json.dumps(declaration))
    return home


def _telegram_findings(found):
    return [f for f in found if f.subject == "telegram"]


def test_a_home_that_declares_telegram_gets_the_finding(tmp_path):
    home = _home(tmp_path, ["plugin:telegram:telegram"])
    state = tmp_path / "plugin"
    found = watch.check_home(home, NOW, probe=lambda pid, start: True, telegram_dir=state)
    (f,) = _telegram_findings(found)
    assert f.verdict == "CHECK-FAILED"                     # nothing recorded there: unknown, not healthy


@pytest.mark.parametrize("channels", [None, [], ["plugin:other:other"]])
def test_a_home_that_does_not_declare_telegram_gets_none(tmp_path, channels):
    found = watch.check_home(_home(tmp_path, channels), NOW, probe=lambda pid, start: True,
                             telegram_dir=tmp_path / "plugin")
    assert _telegram_findings(found) == []


def test_without_process_probes_the_poller_pid_is_not_judged(tmp_path):
    """A home in a pid namespace this watch can't see: its own in-container pass checks it."""
    found = watch.check_home(_home(tmp_path, ["plugin:telegram:telegram"]), NOW, probe=None,
                             telegram_dir=tmp_path / "plugin")
    assert _telegram_findings(found) == []
