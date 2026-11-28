"""Usage meter health: fault alarms and the rolled hourly summary."""

import json
import time
from datetime import datetime, timezone

from macf import usage_meter as um
from macf import usage_share as us
from macf.agent_events_log import append_event, read_events


def _line(mid, **usage):
    base = {"input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 0}
    base.update(usage)
    now = datetime.now(timezone.utc).isoformat()  # calls happen now: the hour's readers place them by their time
    return json.dumps({"type": "assistant", "timestamp": now,
                       "message": {"id": mid, "model": "m-a", "usage": base}}) + "\n"


def _write(path, *lines):
    with open(path, "a") as f:
        f.writelines(lines)


def _events(name):
    return [e["data"] for e in read_events(reverse=False, scope="all", only=name)]


def _faults(kind):
    return [d for d in _events(um.FAULT_EVENT) if d["kind"] == kind]


def _baselined(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("z"))
    um.meter_tick("sid", str(t))
    return t


def test_rebaselined_fires_and_resumes_instead_of_baselining(tmp_path, monkeypatch, capsys):
    t = _baselined(tmp_path)
    monkeypatch.setattr(um, "_file_start", lambda p: time.time() + 10_000)  # the lookup floor misses the event
    _write(t, _line("a"), _line("b"))
    r = um.meter_tick("sid", str(t))
    assert r == {"events": 1, "calls": 2}
    assert [d["baseline"] for d in _events(um.EVENT) if d.get("baseline")] == [True]  # only the first
    assert len(_faults("rebaselined")) == 1
    assert "earlier metering event" in capsys.readouterr().err


def test_main_silent_fires_with_tool_activity_and_no_main_calls(tmp_path):
    t = _baselined(tmp_path)
    for _i in range(3):
        append_event(um.TOOL_EVENT, {"tool": "Bash"})
    um.meter_tick("sid", str(t), now=time.time() + 700)
    f = _faults("main_silent")
    assert len(f) == 1 and "3 tool calls" in f[0]["detail"]


def test_neither_fires_when_healthy(tmp_path):
    t = _baselined(tmp_path)
    append_event(um.TOOL_EVENT, {"tool": "Bash"})
    _write(t, _line("a"))
    um.meter_tick("sid", str(t))  # counts a main call
    _write(t, _line("b"))
    um.meter_tick("sid", str(t), now=time.time() + 700)
    assert _events(um.FAULT_EVENT) == []


def test_each_fault_fires_at_most_once_an_hour(tmp_path, monkeypatch):
    t = _baselined(tmp_path)
    append_event(um.TOOL_EVENT, {"tool": "Bash"})
    now = time.time()
    um.meter_tick("sid", str(t), now=now + 700)
    um.meter_tick("sid", str(t), now=now + 1400)  # past the 10 minute gate, inside the hour
    assert len(_faults("main_silent")) == 1
    monkeypatch.setattr(um, "_file_start", lambda p: time.time() + 10_000)
    for i in range(3):
        _write(t, _line(f"x{i}"))
        um.meter_tick("sid", str(t), now=now + 1500 + 100 * i)
    assert len(_faults("rebaselined")) == 1


def test_usage_rolled_is_written_at_most_once_a_minute(tmp_path):
    t = _baselined(tmp_path)
    now = time.time()
    _write(t, _line("a"))
    um.meter_tick("sid", str(t), now=now)
    _write(t, _line("b"))
    um.meter_tick("sid", str(t), now=now + 10)
    assert len(_events(us.ROLLED_EVENT)) == 1
    _write(t, _line("c"))
    um.meter_tick("sid", str(t), now=now + 90)
    rolled = _events(us.ROLLED_EVENT)
    assert len(rolled) == 2 and rolled[1]["calls_1h"] == 3 and rolled[1]["fitted"] is False


def test_hook_suffix_reads_one_rolled_event(monkeypatch):
    now = time.time()
    append_event(us.ROLLED_EVENT, {"points_1h": 0.5, "calls_1h": 9, "rate": 1e-8, "fitted": False, "at": now})
    seen = []
    real = us.read_events

    def counting(*a, **k):
        for ev in real(*a, **k):
            seen.append(ev["event"])
            yield ev

    monkeypatch.setattr(us, "read_events", counting)
    assert us.hook_suffix(now=now + 5) == "· me ~0.50%/1h"
    assert seen == [us.ROLLED_EVENT]
    append_event(us.ROLLED_EVENT, {"points_1h": 0.25, "calls_1h": 9, "rate": 1e-8, "fitted": True, "at": now})
    seen.clear()
    assert us.hook_suffix(now=now + 5) == "· me 0.25%/1h"
    assert len(seen) == 1


def test_hook_suffix_falls_back_when_the_rolled_event_is_stale():
    now = time.time()
    append_event(us.ROLLED_EVENT, {"points_1h": 9.0, "calls_1h": 9, "rate": 1e-8, "fitted": True, "at": now})
    row = {"input_tokens": 1_000_000, "calls": 1}
    append_event(um.EVENT, {"path": "p", "cause": "operator", "by_model": {"m-a": row}, "calls": 1})
    later = now + 1000  # rolled is over 15 minutes old, the metered event is inside the hour
    expect = 1_000_000 * um.POINTS_PER_WEIGHTED_TOKEN
    out = us.hook_suffix(now=later)
    assert out.startswith("· me ~") and "9.0" not in out
    assert f"{expect:.2f}" in out or f"{expect:.3f}" in out


def test_main_silent_ignores_tool_activity_older_than_an_hour(tmp_path):
    t = _baselined(tmp_path)
    append_event(um.TOOL_EVENT, {"tool": "Bash"})
    um.meter_tick("sid", str(t), now=time.time() + 4000)
    assert _faults("main_silent") == []


def test_a_new_subagent_file_does_not_walk_the_cycle(tmp_path, monkeypatch):
    t = _baselined(tmp_path)
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    _write(sub / "a.jsonl", _line("w"))
    from macf import agent_events_log as ael
    real = ael.read_events
    scopes = []

    def counting(*a, **k):
        scopes.append(k.get("scope"))
        return real(*a, **k)

    monkeypatch.setattr(ael, "read_events", counting)
    monkeypatch.setattr(um, "_file_start", lambda p: time.time() + 5)  # born after metering began
    um.meter_tick("sid", str(t))
    assert "cycle" not in scopes


def test_main_silent_fires_when_only_a_subagent_is_metered(tmp_path):
    t = tmp_path / "s.jsonl"
    _write(t, _line("z"))
    sub = tmp_path / "sid" / "subagents"
    sub.mkdir(parents=True)
    sa = sub / "a.jsonl"
    _write(sa, _line("w"))
    um.meter_tick("sid", str(t))  # baselines both
    _write(sa, _line("x"), _line("y"))
    assert um.meter_tick("sid", str(t))["calls"] == 2
    append_event(um.TOOL_EVENT, {"tool": "Bash"})
    um.meter_tick("sid", str(t), now=time.time() + 700)
    assert len(_faults("main_silent")) == 1


def test_a_fault_repeats_after_its_hour_and_not_before():
    now = time.time()
    assert um._raise_fault("k", "d", now) is True
    assert um._raise_fault("k", "d", now + 100) is False
    assert um._raise_fault("k", "d", now + 3700) is True
    assert len(_faults("k")) == 2


def test_the_main_check_runs_at_most_every_ten_minutes(tmp_path):
    t = _baselined(tmp_path)
    now = time.time()
    um.meter_tick("sid", str(t), now=now + 10)
    um.meter_tick("sid", str(t), now=now + 70)
    assert len(_events(um.CHECKED_EVENT)) == 1
    um.meter_tick("sid", str(t), now=now + 700)
    assert len(_events(um.CHECKED_EVENT)) == 2


def test_the_fallback_stops_at_the_cycle_boundary(tmp_path, monkeypatch):
    t = _baselined(tmp_path)
    append_event("compaction_detected", {})
    monkeypatch.setattr(um, "_file_start", lambda p: time.time() + 10_000)
    _write(t, _line("a"))
    um.meter_tick("sid", str(t))
    assert _faults("rebaselined") == []
    assert [d.get("baseline") for d in _events(um.EVENT)] == [True, True]


def test_a_tick_without_new_calls_does_not_roll(tmp_path):
    t = _baselined(tmp_path)
    um.meter_tick("sid", str(t))
    assert _events(us.ROLLED_EVENT) == []
