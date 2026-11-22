"""Usage meter health: fault alarms and the rolled hourly summary."""

import json
import time

from macf import usage_meter as um
from macf import usage_share as us
from macf.agent_events_log import append_event, read_events


def _line(mid, **usage):
    base = {"input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 0}
    base.update(usage)
    return json.dumps({"type": "assistant", "timestamp": "2026-11-22T10:00:00Z",
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
    assert us.hook_suffix(now=now + 5) == "· me ~0.50%/h"
    assert seen == [us.ROLLED_EVENT]
    append_event(us.ROLLED_EVENT, {"points_1h": 0.25, "calls_1h": 9, "rate": 1e-8, "fitted": True, "at": now})
    seen.clear()
    assert us.hook_suffix(now=now + 5) == "· me 0.25%/h"
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
