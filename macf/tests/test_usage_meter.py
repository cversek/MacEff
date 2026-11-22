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
    assert causes[True] == "subagent" and causes[False] == "operator"


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
