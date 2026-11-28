"""Usage meter: scan rules, offset carry, causes, and the budget me totals."""

import json
import time

import pytest

from macf import usage_meter as um
from macf.agent_events_log import append_event, read_events


def _line(mid, model="m-a", ts="2026-11-22T10:00:00Z", **usage):
    base = {"input_tokens": 1, "cache_read_input_tokens": 0, "output_tokens": 0}
    base.update(usage)
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"id": mid, "model": model, "usage": base}}) + "\n"


def _write(path, *lines, mode="a"):
    with open(path, mode) as f:
        f.writelines(lines)


def _metered():
    return [e["data"] for e in read_events(reverse=False, scope="all", only=um.EVENT)]


def test_repeated_id_counts_once_with_last_usage(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a", output_tokens=5), _line("a", output_tokens=40), _line("b", output_tokens=7))
    r = um.scan(t, 0)
    assert r.calls == 2
    assert r.by_model["m-a"]["output_tokens"] == 47
    assert r.by_model["m-a"]["input_tokens"] == 2


def test_partial_trailing_line_is_not_consumed(tmp_path):
    t = tmp_path / "s.jsonl"
    full = _line("a")
    _write(t, full, _line("b")[:-15])
    r = um.scan(t, 0)
    assert r.calls == 1 and r.new_offset == len(full.encode())
    _write(t, _line("b")[-15:])
    assert um.scan(t, r.new_offset).calls == 1


def test_cache_write_split_and_fallback(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a", cache_creation_input_tokens=30,
                    cache_creation={"ephemeral_5m_input_tokens": 10, "ephemeral_1h_input_tokens": 20}),
           _line("b", cache_creation_input_tokens=50))
    row = um.scan(t, 0).by_model["m-a"]
    assert row["cache_write_5m_tokens"] == 10
    assert row["cache_write_1h_tokens"] == 20 + 50


def test_second_tick_sees_only_new_calls_across_compaction_and_straddle(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("z"))
    um.meter_tick("sid", str(t))  # baseline: history is not metered
    _write(t, _line("a"), _line("b"))
    assert um.meter_tick("sid", str(t))["calls"] == 2
    assert um.meter_tick("sid", str(t)) is None
    # more content blocks of the last call arrive, plus a new call, after a compaction
    append_event("compaction_detected", {})
    _write(t, _line("b", output_tokens=9), _line("c"))
    assert um.meter_tick("sid", str(t))["calls"] == 1
    ev = _metered()
    assert [e["calls"] for e in ev] == [0, 2, 1]
    assert ev[2]["offset"] == ev[1]["new_offset"]


def test_subagent_file_is_metered_as_subagent(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"))
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    sa = sub / "agent-1.jsonl"
    _write(sa, _line("w"))
    um.meter_tick("sid", str(t))  # baselines both files
    _write(t, _line("b"))
    _write(sa, _line("x"), _line("y"))
    assert um.meter_tick("sid", str(t))["events"] == 2
    causes = {e["path"].endswith("agent-1.jsonl"): e["cause"] for e in _metered() if e["calls"]}
    assert causes[True] == "subagent" and causes[False] == "unknown"  # no turn_cause since metering began


@pytest.mark.parametrize("text,cause", [
    ("hello", "operator"),
    ('<channel source="telegram" chat_id="1">hi</channel>', "channel"),
    ('<cross-session-message from="x">hi', "peer"),
    ("[cron:abc] check mail", "cron"),
    ("<task-notification>done</task-notification>", "notice"),
])
def test_prompt_classification(text, cause):
    assert um.classify_prompt(text) == cause


def test_gate_cause_only_when_held_is_newer_than_turn_cause(tmp_path):
    append_event("turn_cause", {"cause": "channel"})
    assert um.current_cause() == "channel"
    append_event("scope_gate_held", {"remaining": 1})
    assert um.current_cause() == "gate"
    append_event("turn_cause", {"cause": "operator"})
    assert um.current_cause() == "operator"


def test_budget_me_totals_and_points(tmp_path, capsys):
    row = {"input_tokens": 1_000_000, "cache_write_1h_tokens": 1_000_000, "cache_write_5m_tokens": 1_000_000,
           "cache_read_input_tokens": 10_000_000, "output_tokens": 1_000_000, "calls": 4}
    append_event(um.EVENT, {"path": "p", "cause": "cron", "by_model": {"m-a": row}, "calls": 4})
    s = um.summarize(time.time() - 3600)
    w = 1e6 * (1 + 2 + 1.25 + 5) + 10e6 * 0.1
    assert s.by_cause["cron"] == pytest.approx(w)
    out = um.format_summary(s, "1h")
    assert f"points {w * 4.08e-8:.3f}" in out
    assert f"low, reads 0: {(w - 1e6) * 4.08e-8:.3f}" in out
    assert max(len(x) for x in out.splitlines()) <= 60
    assert um.__file__.startswith(str(__import__("pathlib").Path(__file__).resolve().parents[1]))


def test_first_sighting_of_a_big_file_reads_only_its_tail(tmp_path):
    t = tmp_path / "big.jsonl"
    _write(t, *[_line(f"m{i}") for i in range(5000)])
    r = um.meter_tick("sid", str(t))
    ev = _metered()[0]
    assert r == {"events": 1, "calls": 0}
    assert ev["baseline"] is True and ev["calls"] == 0
    assert ev["new_offset"] == t.stat().st_size and ev["tail_id"] == "m4999"


def test_stop_hook_baselines_then_meters(tmp_path):
    from unittest.mock import patch
    from macf.hooks.handle_stop import run
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"))
    stdin = json.dumps({"stop_reason": "end_turn", "session_id": "sid", "transcript_path": str(t)})
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(False, "test")):
        run(stdin)
        assert [e["baseline"] for e in _metered()] == [True]
        _write(t, _line("b"), _line("c"))
        run(stdin)
    assert [e["calls"] for e in _metered()] == [0, 2]


def test_prompt_hook_records_turn_cause():
    from unittest.mock import patch
    from macf.hooks.handle_user_prompt_submit import run
    stdin = json.dumps({"session_id": "sid", "prompt": '<cross-session-message from="x">hi</cross-session-message>'})
    with patch("macf.hooks.handle_user_prompt_submit.detect_auto_mode", return_value=(False, "test")):
        try:
            run(stdin)
        except Exception as e:  # noqa: BLE001 - only the event written before any failure matters here
            print(f"hook failed after the cause was recorded: {e}")
    causes = [e["data"]["cause"] for e in read_events(reverse=False, scope="all", only=um.TURN_CAUSE_EVENT)]
    assert causes == ["peer"]


def test_subagent_born_after_metering_began_is_scanned_from_zero(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"))
    old = tmp_path / "sid" / "subagents" / "old.jsonl"
    old.parent.mkdir(parents=True)
    _write(old, _line("o1"), _line("o2"))
    um.meter_tick("sid", str(t))  # first tick: both files predate it and are baselined
    assert [e["baseline"] for e in _metered()] == [True, True]
    new = old.parent / "new.jsonl"
    _write(new, _line("n1", ts="2099-01-01T00:00:00Z"), _line("n2"), _line("n3"))
    r = um.meter_tick("sid", str(t))
    got = [e for e in _metered() if e["path"] == str(new)]
    assert r == {"events": 1, "calls": 3}
    assert got[0]["calls"] == 3 and got[0]["cause"] == "subagent" and not got[0].get("baseline")
    assert not [e for e in _metered() if e["path"] == str(old) and e["calls"]]


# ── Branch-level pins ─────────────────────────────────────────────────────────

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

from macf.agent_events_log import get_log_path

T0 = datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone.utc).timestamp()  # the default fixture timestamp


def _emit_at(ts, event, data):
    """An event with a chosen time, written the way append_event writes it."""
    with open(get_log_path(), "a") as f:
        f.write(json.dumps({"timestamp": ts, "event": event, "breadcrumb": "", "data": data, "hook_input": {}}) + "\n")


def test_scan_counts_every_class_and_skips_what_is_not_a_call(tmp_path, capsys):
    t = tmp_path / "s.jsonl"
    odd = [
        json.dumps({"type": "user", "message": {"id": "u", "usage": {"input_tokens": 99}}}) + "\n",
        json.dumps({"type": "assistant", "message": ["usage"]}) + "\n",
        json.dumps({"type": "assistant", "message": {"id": "q", "usage": "usage"}}) + "\n",
        '{"type": "assistant", "usage": broken}\n',
        json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 3}}}) + "\n",  # no id, no model
        json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 4}}}) + "\n",  # a second one
    ]
    _write(t, _line("a", ts="2026-11-22T10:05:00Z", input_tokens=10, cache_read_input_tokens=1000, output_tokens=20),
           _line("b", model="m-b", ts="2026-11-22T10:01:00Z", input_tokens=5, cache_read_input_tokens=300, output_tokens=2),
           _line("c", ts="2026-11-22T10:09:00Z", input_tokens=1, cache_read_input_tokens=50, output_tokens=1), *odd)
    r = um.scan(t, 0)
    assert r.calls == 5 and r.new_offset == t.stat().st_size
    assert r.by_model["m-a"] == {"input_tokens": 11, "cache_read_input_tokens": 1050, "output_tokens": 21,
                                 "cache_write_5m_tokens": 0, "cache_write_1h_tokens": 0, "calls": 2}
    assert r.by_model["m-b"]["cache_read_input_tokens"] == 300 and r.by_model["m-b"]["calls"] == 1
    assert r.by_model["unknown"]["input_tokens"] == 7 and r.by_model["unknown"]["calls"] == 2
    assert (r.first_ts, r.last_ts) == ("2026-11-22T10:01:00Z", "2026-11-22T10:09:00Z")
    assert r.tail_id == "line@" + str(r.new_offset)
    assert "malformed line" in capsys.readouterr().err
    assert um.scan(t, r.new_offset).calls == 0


def test_scan_from_an_offset_past_the_end_rescans_from_zero(tmp_path, capsys):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"), _line("b"))
    r = um.scan(t, t.stat().st_size + 500)
    assert r.calls == 2 and r.new_offset == t.stat().st_size
    assert "shorter than offset" in capsys.readouterr().err


def test_the_newest_event_for_a_file_wins(tmp_path):
    t = tmp_path / "s.jsonl"
    first = _line("a")
    _write(t, first, _line("b"), _line("c"))
    n1, n2 = len(first.encode()), len(first.encode()) + len(_line("b").encode())
    common = {"path": str(t), "metering_since": T0 - 1000}
    _emit_at(T0 + 1, um.EVENT, {**common, "new_offset": n1, "tail_id": "a"})
    _emit_at(T0 + 2, um.EVENT, {**common, "new_offset": n2, "tail_id": "b"})
    # a second, unseen file keeps the walk going past the newest event, to the older one
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    _write(sub / "x.jsonl", _line("x"))
    assert um.meter_tick("sid", str(t)) == {"events": 2, "calls": 2}  # c, and x born after metering began
    assert [e["offset"] for e in _metered() if e["path"] == str(t) and e.get("calls")][-1] == n2


@pytest.mark.parametrize("first_line_ts,event_at,found", [
    ("2026-11-22T10:00:00Z", T0 - 30, True),    # within the minute of slack before the file began
    ("2026-11-22T10:00:00Z", T0 - 200, False),  # older than the file can be: the walk stops short of it, the fallback finds it
    (None, T0 - 30, True),                       # no first-line timestamp: the next line's stands in
])
def test_the_lookup_floor_is_the_files_start_less_a_minute(tmp_path, first_line_ts, event_at, found):
    t = tmp_path / "s.jsonl"
    first = _line("a", ts=first_line_ts)
    _write(t, first, _line("b"))
    os.utime(t, (T0, T0))
    _emit_at(event_at, um.EVENT, {"path": str(t), "new_offset": len(first.encode()), "tail_id": "a",
                                  "metering_since": T0 - 1000})
    r = um.meter_tick("sid", str(t))
    # a miss by the floored walk is still resumed (and raises a rebaselined fault), never baselined
    assert r == {"events": 1, "calls": 1}
    assert not _metered()[-1].get("baseline")
    faults = [e for e in read_events(reverse=False, scope="all", only=um.FAULT_EVENT)]
    assert bool(faults) is (not found)


def test_a_transcript_opening_without_a_timestamp_is_resumed_not_rebaselined(tmp_path):
    """A live transcript can open with a record that has no timestamp (a file-history snapshot),
    and its mtime is always now. A floor taken from the mtime finds none of its events, so every
    tick baselined it again and its calls were never counted."""
    t = tmp_path / "s.jsonl"
    _write(t, json.dumps({"type": "file-history-snapshot", "snapshot": {}}) + "\n", _line("a", ts="2026-11-22T10:00:00Z"))
    assert um.meter_tick("sid", str(t)) == {"events": 1, "calls": 0}   # first sight: baseline
    _write(t, _line("b", ts="2026-11-22T10:05:00Z"))
    future = time.time() + 3600
    os.utime(t, (future, future))                                      # being written: mtime is now or later
    assert um.meter_tick("sid", str(t)) == {"events": 1, "calls": 1}   # resumed, b counted
    assert not _metered()[-1].get("baseline")


def test_a_file_with_no_timestamp_and_no_birth_time_walks_the_whole_log(tmp_path, monkeypatch):
    t = tmp_path / "s.jsonl"
    _write(t, json.dumps({"type": "file-history-snapshot"}))
    real = os.stat
    monkeypatch.setattr(um.os, "stat", lambda p, *a, **k: type("S", (), {"st_size": real(p).st_size, "st_mtime": time.time()})())
    assert um._file_start(str(t)) == 0.0


def test_the_start_is_the_first_timestamp_among_the_opening_lines(tmp_path):
    """Three opening records without a timestamp, then one with: that one is the start, not the
    birth time (a fresh tmp file's birth time is now, which would pass a looser test)."""
    t = tmp_path / "s.jsonl"
    snap = json.dumps({"type": "file-history-snapshot"}) + "\n"
    _write(t, snap, snap, snap, _line("a", ts="2025-01-02T03:04:05Z"))
    assert um._file_start(str(t)) == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp()


def test_with_no_timestamp_the_birth_time_is_the_start(tmp_path, monkeypatch):
    t = tmp_path / "s.jsonl"
    _write(t, json.dumps({"type": "file-history-snapshot"}))
    real = os.stat
    monkeypatch.setattr(um.os, "stat", lambda p, *a, **k: type("S", (), {
        "st_size": real(p).st_size, "st_mtime": time.time(), "st_birthtime": 1700000000.0})())
    assert um._file_start(str(t)) == 1700000000.0


def test_metering_since_is_read_back_and_copied_forward(tmp_path):
    t = tmp_path / "s.jsonl"
    first = _line("a")
    _write(t, first)
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    _emit_at(T0 + 1, um.EVENT, {"path": str(t), "new_offset": len(first.encode()), "tail_id": "a",
                                "metering_since": T0})
    born_after = sub / "born_after.jsonl"
    _write(born_after, _line("n", ts="2026-11-22T10:01:40Z"))   # T0 + 100 s: after metering began, before now
    born_before = sub / "born_before.jsonl"
    _write(born_before, _line("o", ts="2026-11-22T09:59:00Z"))  # before it
    _write(t, _line("b"))
    um.meter_tick("sid", str(t))
    ev = {os.path.basename(e["path"]): e for e in _metered() if e["path"] != str(t) or e.get("calls")}
    assert ev["born_after.jsonl"]["calls"] == 1 and not ev["born_after.jsonl"].get("baseline")
    assert ev["born_before.jsonl"]["baseline"] is True and ev["born_before.jsonl"]["cause"] == "subagent"
    assert {e["metering_since"] for e in ev.values()} == {T0}
    assert ev["s.jsonl"]["by_model"]["m-a"]["input_tokens"] == 1


def test_baseline_ignores_history_cut_lines_and_a_partial_tail(tmp_path):
    t = tmp_path / "s.jsonl"
    # One line whose last 64 KB is still valid JSON (leading spaces): a read that kept it would
    # mistake it for the last call.
    _write(t, " " * 70_000 + json.dumps({"message": {"id": "cut", "usage": {}}}) + "\n")
    assert um._baseline(str(t)).tail_id is None
    good = [_line(f"m{i}") for i in range(900)]  # well over 64 KB
    bad = ['{"type": "assistant", "usage": nope}\n', json.dumps({"message": {"usage": {}}}) + "\n",
           json.dumps({"type": "user", "text": "no counts here"}) + "\n"]
    _write(t, *good, *bad, mode="w")
    size = t.stat().st_size
    _write(t, '{"type": "assistant", "mess')  # a call still being written
    b = um._baseline(str(t))
    assert b.tail_id == "m899" and b.offset == size


def test_current_cause_reaches_across_a_compaction_and_ignores_a_bogus_cause():
    append_event("turn_cause", {"cause": "channel"})
    append_event("compaction_detected", {})
    assert um.current_cause() == "channel"
    append_event("scope_gate_held", {"remaining": 1})
    append_event("compaction_detected", {})
    assert um.current_cause() == "gate"
    append_event("turn_cause", {"cause": "bogus"})
    assert um.current_cause() == "operator"


def test_an_unreadable_file_is_skipped_with_a_warning(tmp_path, capsys):
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"))
    with patch.object(um, "_baseline", side_effect=OSError("gone")):
        assert um.meter_tick("sid", str(t)) is None
    assert "gone" in capsys.readouterr().err and not _metered()


def test_summary_text_totals_and_window():
    big = {"input_tokens": 2_000_000, "cache_write_1h_tokens": 500_000, "cache_write_5m_tokens": 0,
           "cache_read_input_tokens": 40_000_000, "output_tokens": 300_000, "calls": 120}
    small = {"input_tokens": 100, "cache_write_1h_tokens": 0, "cache_write_5m_tokens": 400,
             "cache_read_input_tokens": 1000, "output_tokens": 50, "calls": 3}
    now = time.time()
    _emit_at(now - 2 * 86400, um.EVENT, {"path": "p", "cause": "cron", "by_model": {"claude-opus-5-5": big}})
    _emit_at(now - 60, um.EVENT, {"path": "p", "cause": "gate", "by_model": {"claude-opus-5-5": big}})
    _emit_at(now - 30, um.EVENT, {"path": "q", "by_model": {"tiny": small}})  # no cause: operator
    s = um.summarize(now - 3600)
    assert s.calls == 123 and s.tokens["cache_read_input_tokens"] == 40_001_000 and s.tokens["input_tokens"] == 2_000_100
    assert set(s.by_cause) == {"gate", "operator"} and s.by_model["claude-opus-5-5"]["calls"] == 120
    expected = (
        'usage, last 1h: 123 calls\n'
        '\n'
        'tokens\n'
        '  input               2,000,100\n'
        '  cache write 1h        500,000\n'
        '  cache write 5m            400\n'
        '  cache read         40,001,000\n'
        '  output                300,050\n'
        '\n'
        'by model (calls, weighted as claude-opus-5-5)\n'
        '  claude-opus-5-5                   120    8.50M\n'
        '  tiny                                3      950\n'
        '  no price factor, weighed 1: tiny\n'
        '\n'
        'by cause (weighted)\n'
        '  gate                8.50M 100.0%\n'
        '  operator              950   0.0%\n'
        '\n'
        'points 0.347  (low, reads 0: 0.184)\n'
        'rate provisional (fitted 2026-11-22)'
    )
    assert um.format_summary(s, "1h") == expected


def test_budget_me_command_default_window_and_bad_since(capsys):
    from macf.cli import main
    for argv, code in ((["budget", "me"], 0), (["budget", "me", "--since", "7d"], 0),
                       (["budget", "me", "--since", "soon"], 2)):
        with patch.object(sys, "argv", ["macf_tools", *argv]):
            try:
                rc = main()
            except SystemExit as e:
                rc = e.code
        out = capsys.readouterr()
        assert (rc or 0) == code
        if code == 0:
            assert f"usage, last {argv[-1] if len(argv) > 2 else '1d'}:" in out.out
        else:
            assert "--since takes" in out.err


def test_hook_guards_for_the_meter_and_the_turn_cause(tmp_path):
    from macf.hooks import handle_stop, handle_user_prompt_submit as ups
    with patch("macf.usage_meter.meter_tick") as tick, patch.object(handle_stop, "emit_warning") as warn:
        handle_stop._meter_usage(json.dumps({"session_id": "sid"}))          # no transcript: nothing to meter
        handle_stop._meter_usage("")
        assert not tick.called and not warn.called
        handle_stop._meter_usage(json.dumps({"session_id": "sid", "transcript_path": "/x/t.jsonl"}))
        tick.assert_called_once_with("sid", "/x/t.jsonl")
        tick.side_effect = OSError("disk")
        handle_stop._meter_usage(json.dumps({"session_id": "sid", "transcript_path": "/x/t.jsonl"}))
        assert warn.call_args[0][0].kind == "usage_meter_failed" and "disk" in warn.call_args[0][0].detail
    with patch("macf.usage_meter.classify_prompt", side_effect=TypeError("bad")), \
            patch.object(ups, "emit_warning") as warn, \
            patch.object(ups, "detect_auto_mode", return_value=(False, "test")):
        ups.run(json.dumps({"session_id": "sid", "prompt": None}))
    assert any(c[0][0].kind == "turn_cause_failed" for c in warn.call_args_list)


def _count_reads():
    """Wrap read_events to count the usage_metered events a tick pulls and the walks it starts."""
    from macf import agent_events_log as ael
    real = ael.read_events
    stats = {"walks": 0, "events": 0}

    def counting(*a, **kw):
        counted = kw.get("only") == um.EVENT
        stats["walks"] += counted
        for ev in real(*a, **kw):
            stats["events"] += counted
            yield ev
    return patch.object(ael, "read_events", counting), stats


def test_quiet_files_are_not_looked_up_and_a_grown_one_still_is(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("m0"))
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    quiet = [sub / f"q{i}.jsonl" for i in range(3)]
    for q in quiet:
        _write(q, _line(q.stem))
        os.utime(q, (T0, T0))                    # untouched since long before any tick
    grows = sub / "grows.jsonl"
    _write(grows, _line("g0"))
    os.utime(grows, (T0, T0))
    um.meter_tick("sid", str(t))                 # baselines main; the old subagent files get no event of their own
    assert len(_metered()) == 1
    for i in range(500):
        append_event("noise", {"i": i})
    _write(t, _line("m1"))
    um.meter_tick("sid", str(t))                 # main's latest event is now recent
    # one call in main, none in the quiet files: only the main transcript is walked for
    _write(t, _line("m2"))
    ctx, stats = _count_reads()
    with ctx:
        assert um.meter_tick("sid", str(t)) == {"events": 1, "calls": 1}
    assert stats == {"walks": 1, "events": 1}    # the walk stopped at main's own latest event
    # a skipped subagent file that then grows is read from the end the first tick recorded for it
    _write(grows, _line("g1"), _line("g2"))
    r = um.meter_tick("sid", str(t))
    assert r == {"events": 1, "calls": 2}
    assert [e["calls"] for e in _metered() if e["path"] == str(grows)] == [2]
    assert not [e for e in _metered() if e["path"] in map(str, quiet) and e["calls"]]


def test_busy_files_each_resume_from_their_newest_event(tmp_path):
    t = tmp_path / "s.jsonl"
    main_line = _line("m0")
    _write(t, main_line)
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    paths, newest = {}, {}
    # Their floors differ (the files began 1000 s apart) and every event of one file is older than the
    # other's floor, so a walk bounded by the newest floor would lose the older file's events.
    for name, first_ts, base in (("a", "2026-11-22T10:00:00Z", T0), ("b", "2026-11-22T10:16:40Z", T0 + 1000)):
        lines = [_line(f"{name}{i}", ts=first_ts) for i in range(1, 4)]
        p = sub / f"{name}.jsonl"
        _write(p, *lines)
        sizes = [len(x.encode()) for x in lines]
        paths[name], newest[name] = p, sizes[0] + sizes[1]
        common = {"path": str(p), "metering_since": T0 - 1000}
        _emit_at(base + 10, um.EVENT, {**common, "new_offset": sizes[0], "tail_id": f"{name}1"})
        _emit_at(base + 200, um.EVENT, {**common, "new_offset": newest[name], "tail_id": f"{name}2"})
    # events are in time order: a-old, a-new, b-old, b-new; the main transcript's latest event is last
    _emit_at(time.time(), um.EVENT, {"path": str(t), "new_offset": len(main_line.encode()), "tail_id": "m0",
                                     "metering_since": T0 - 1000})
    assert um.meter_tick("sid", str(t)) == {"events": 2, "calls": 2}
    got = {os.path.basename(e["path"]): e["offset"] for e in _metered() if e.get("calls")}
    assert got == {"a.jsonl": newest["a"], "b.jsonl": newest["b"]}


def test_cause_lookup_stops_at_metering_since():
    now = time.time()
    _emit_at(now - 500, um.GATE_HELD_EVENT, {})            # a stale gate from before metering began
    assert um.current_cause(now - 100) == "unknown"
    _emit_at(now - 50, um.TURN_CAUSE_EVENT, {"cause": "channel"})
    assert um.current_cause(now - 100) == "channel"


def test_first_tick_writes_no_baseline_per_old_subagent_file(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("m0"))
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    for i in range(30):
        p = sub / f"old{i}.jsonl"
        _write(p, _line(f"o{i}"))
        os.utime(p, (T0, T0))
    um.meter_tick("sid", str(t))
    assert len(_metered()) == 1                            # main only
    skipped = [e["data"] for e in read_events(reverse=False, scope="all", only=um.SKIPPED_EVENT)]
    assert len(skipped) == 1 and len(skipped[0]["files"]) == 30
    p = sub / "old7.jsonl"
    _write(p, _line("woke"))                               # a finished file that grows is still metered
    assert um.meter_tick("sid", str(t)) == {"events": 1, "calls": 1}


def test_skipped_offsets_ignore_events_older_than_metering_start():
    now = time.time()
    _emit_at(now - 500, um.SKIPPED_EVENT, {"files": {"/old": 5}})
    _emit_at(now - 50, um.SKIPPED_EVENT, {"files": {"/new": 7}})
    assert um._skipped_offsets(now - 100) == {"/new": 7}


def test_skipped_offsets_newest_event_wins():
    now = time.time()
    _emit_at(now - 80, um.SKIPPED_EVENT, {"files": {"/f": 10}})
    _emit_at(now - 40, um.SKIPPED_EVENT, {"files": {"/f": 20}})
    assert um._skipped_offsets(now - 100) == {"/f": 20}


def test_skipped_event_is_written_once_across_ticks(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("m0"))
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    p = sub / "old.jsonl"
    _write(p, _line("o"))
    os.utime(p, (T0, T0))
    for i in range(4):
        um.meter_tick("sid", str(t))
        _write(t, _line(f"m{i + 1}"))
    assert len(list(read_events(reverse=False, scope="all", only=um.SKIPPED_EVENT))) == 1


def test_a_call_copied_into_a_fork_file_counts_once(tmp_path):
    """A fork's transcript opens with the parent's last call, same id: the session counts it once,
    whether the original was metered in an earlier tick or in the same one."""
    t = tmp_path / "s.jsonl"
    _write(t, _line("a"))
    um.meter_tick("sid", str(t))  # baseline
    _write(t, _line("p", output_tokens=7))
    um.meter_tick("sid", str(t))  # the parent's call, metered on its own
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    _write(sub / "f1.jsonl", _line("p", output_tokens=7, ts="2099-01-01T00:00:00Z"), _line("f1"))
    _write(t, _line("q"))
    _write(sub / "f2.jsonl", _line("q", ts="2099-01-01T00:00:00Z"), _line("f2"))
    assert um.meter_tick("sid", str(t)) == {"events": 3, "calls": 3}  # q in main, f1 and f2 in the forks
    counted = [m for e in _metered() for m in e.get("ids") or ()]
    assert sorted(counted) == ["f1", "f2", "p", "q"]
