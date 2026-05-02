"""Tests for the generic structured-event JSONL analyzer (BUG #1069)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from macf.eventlog import EventLogAnalyzer, parse_since


def _write_jsonl(path: Path, events: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestParseSince:
    def test_parses_h_unit(self):
        thresh = parse_since("1h")
        assert thresh is not None
        # Roughly an hour ago
        assert datetime.now(timezone.utc) - thresh - timedelta(hours=1) < timedelta(seconds=2)

    def test_parses_d_unit(self):
        thresh = parse_since("7d")
        assert thresh is not None

    def test_returns_none_on_garbage(self):
        assert parse_since("nope") is None
        assert parse_since("") is None
        assert parse_since(None) is None  # type: ignore[arg-type]


class TestEventLogAnalyzerEvents:
    def test_missing_file_yields_nothing(self, tmp_path):
        analyzer = EventLogAnalyzer(tmp_path / "nope.jsonl")
        assert list(analyzer.events()) == []

    def test_skips_blank_and_malformed_lines(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text(
            json.dumps({"ts": _now_iso(), "phase": "started", "request_id": "r1"}) + "\n"
            "\n"
            "{ not json }\n"
            + json.dumps({"ts": _now_iso(), "phase": "completed", "request_id": "r1", "success": True, "elapsed_ms": 10}) + "\n"
        )
        analyzer = EventLogAnalyzer(path)
        events = list(analyzer.events())
        assert len(events) == 2

    def test_since_filters_old_events(self, tmp_path):
        path = tmp_path / "log.jsonl"
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()
        _write_jsonl(path, [
            {"ts": old_ts, "phase": "started", "request_id": "old"},
            {"ts": new_ts, "phase": "started", "request_id": "new"},
        ])
        analyzer = EventLogAnalyzer(path)
        recent = list(analyzer.events(since=parse_since("1h")))
        assert len(recent) == 1
        assert recent[0]["request_id"] == "new"


class TestEventLogAnalyzerSummarize:
    def test_basic_success_rate_and_percentiles(self, tmp_path):
        path = tmp_path / "log.jsonl"
        ts = _now_iso()
        _write_jsonl(path, [
            {"ts": ts, "phase": "started", "request_id": "r1"},
            {"ts": ts, "phase": "completed", "request_id": "r1", "success": True, "elapsed_ms": 100},
            {"ts": ts, "phase": "started", "request_id": "r2"},
            {"ts": ts, "phase": "completed", "request_id": "r2", "success": True, "elapsed_ms": 200},
            {"ts": ts, "phase": "started", "request_id": "r3"},
            {"ts": ts, "phase": "timeout", "request_id": "r3", "success": False},
        ])
        summary = EventLogAnalyzer(path).summarize()

        assert summary["total_started"] == 3
        assert summary["completed_count"] == 3  # 2 success + 1 fail terminal
        assert summary["success_count"] == 2
        assert summary["success_rate"] == round(2 / 3, 3)
        assert summary["elapsed_ms_min"] == 100
        assert summary["elapsed_ms_max"] == 200
        # Percentiles on 2 values: index = floor(2 * p)
        assert summary["elapsed_ms_p50"] == 200  # idx 1
        assert summary["phase_counts"] == {"started": 3, "completed": 2, "timeout": 1}

    def test_group_by_passes_through_field(self, tmp_path):
        path = tmp_path / "log.jsonl"
        ts = _now_iso()
        _write_jsonl(path, [
            {"ts": ts, "phase": "started", "request_id": "r1", "trigger": "T1"},
            {"ts": ts, "phase": "started", "request_id": "r2", "trigger": "T1"},
            {"ts": ts, "phase": "started", "request_id": "r3", "trigger": "T2"},
        ])
        summary = EventLogAnalyzer(path).summarize(group_by="trigger")
        assert summary["groups"] == {"T1": 2, "T2": 1}
        assert summary["group_by_field"] == "trigger"

    def test_custom_phase_and_field_names(self, tmp_path):
        """Adapter pattern: a domain log with non-default field names still analyzes."""
        path = tmp_path / "restart.jsonl"
        ts = _now_iso()
        _write_jsonl(path, [
            {"ts": ts, "phase": "spawn", "pid": 100},
            {"ts": ts, "phase": "exit", "pid": 100, "ok": True, "duration_ms": 50},
            {"ts": ts, "phase": "spawn", "pid": 101},
            {"ts": ts, "phase": "exit", "pid": 101, "ok": False, "duration_ms": 75},
        ])
        analyzer = EventLogAnalyzer(
            path,
            started_phase="spawn",
            success_field="ok",
            elapsed_field="duration_ms",
            correlation_field="pid",
        )
        summary = analyzer.summarize()
        assert summary["total_started"] == 2
        assert summary["success_count"] == 1
        assert summary["completed_count"] == 2
        assert summary["elapsed_ms_min"] == 50

    def test_empty_log_returns_safe_zeros(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        summary = EventLogAnalyzer(path).summarize()
        assert summary["total_started"] == 0
        assert summary["success_rate"] is None
        assert summary["elapsed_ms_min"] is None


class TestEventLogAnalyzerTail:
    def test_returns_terminal_records_for_last_n(self, tmp_path):
        path = tmp_path / "log.jsonl"
        # Distinct started timestamps so sort order is deterministic
        base = datetime.now(timezone.utc)
        _write_jsonl(path, [
            {"ts": (base - timedelta(seconds=30)).isoformat(),
             "phase": "started", "request_id": "old"},
            {"ts": (base - timedelta(seconds=29)).isoformat(),
             "phase": "completed", "request_id": "old", "success": True, "elapsed_ms": 1000},
            {"ts": (base - timedelta(seconds=10)).isoformat(),
             "phase": "started", "request_id": "mid"},
            {"ts": (base - timedelta(seconds=9)).isoformat(),
             "phase": "completed", "request_id": "mid", "success": False, "elapsed_ms": 500},
            {"ts": base.isoformat(),
             "phase": "started", "request_id": "new"},
            {"ts": base.isoformat(),
             "phase": "timeout", "request_id": "new", "success": False},
        ])
        analyzer = EventLogAnalyzer(path)
        rows = analyzer.tail(2)
        assert len(rows) == 2
        # Oldest-first → second-most-recent then most-recent
        assert rows[0]["request_id"] == "mid"
        assert rows[1]["request_id"] == "new"
        assert rows[1]["terminal_phase"] == "timeout"

    def test_tail_skips_in_flight_requests(self, tmp_path):
        """A started-only request (no terminal yet) is not in the tail."""
        path = tmp_path / "log.jsonl"
        ts = _now_iso()
        _write_jsonl(path, [
            {"ts": ts, "phase": "started", "request_id": "r1"},
            {"ts": ts, "phase": "completed", "request_id": "r1", "success": True, "elapsed_ms": 50},
            {"ts": ts, "phase": "started", "request_id": "r2"},
            # r2 has NO terminal — still in flight
        ])
        rows = EventLogAnalyzer(path).tail(10)
        ids = [r["request_id"] for r in rows]
        assert "r1" in ids
        assert "r2" not in ids
