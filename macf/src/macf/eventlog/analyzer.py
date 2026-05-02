"""Generic structured-event JSONL analyzer.

Closes BUG #1069 — extracts the shared analysis pattern from
hermes_cc_delegate/analyze_log.py (Phase 4.4 of MISSION #1044) so future
JSONL logs (Telegram restart-events.jsonl, etc.) reuse the same percentile,
histogram, and tail logic instead of copy-pasting it per domain.

Each domain configures the analyzer with three field names:
- started_phase: phase value marking the start of a request (default: "started")
- success_field: bool field on terminal events indicating success (default: "success")
- elapsed_field: integer field on completed events for elapsed time (default: "elapsed_ms")

Anything beyond that is computed generically: phase counts, success rate,
elapsed-time percentiles (p50/p90/p99/min/max), grouping by an arbitrary
domain field (e.g., "trigger", "caller"), and tail of last N requests.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional


DEFAULT_STARTED_PHASE = "started"
DEFAULT_SUCCESS_FIELD = "success"
DEFAULT_ELAPSED_FIELD = "elapsed_ms"


def parse_since(spec: str) -> Optional[datetime]:
    """Parse a relative time spec ('1h', '30m', '24h', '7d') to a UTC threshold.

    Returns None for unparseable input so callers can pass through raw user
    arguments without pre-validating.
    """
    m = re.match(r"^(\d+)([smhd])$", spec or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {
        "s": timedelta(seconds=n),
        "m": timedelta(minutes=n),
        "h": timedelta(hours=n),
        "d": timedelta(days=n),
    }[unit]
    return datetime.now(timezone.utc) - delta


class EventLogAnalyzer:
    """Analyze a JSONL event log following the standard MACF shape.

    Shape: each line is a JSON object with at minimum a ``ts`` (ISO8601),
    ``request_id`` (or equivalent correlation key), and ``phase`` field.
    Domain-specific fields are passed through transparently.

    Args:
        path: Path to the JSONL file. Non-existent paths produce empty
            results (no exception) so analyzers can be used optimistically.
        started_phase: Phase name marking the start of a request lifecycle.
        success_field: Bool field on terminal events indicating success.
        elapsed_field: Integer field on completed events for elapsed time.
        correlation_field: Field name used to correlate started + terminal
            events (default: "request_id"). Some logs use "pid" instead.
    """

    def __init__(
        self,
        path: Path,
        started_phase: str = DEFAULT_STARTED_PHASE,
        success_field: str = DEFAULT_SUCCESS_FIELD,
        elapsed_field: str = DEFAULT_ELAPSED_FIELD,
        correlation_field: str = "request_id",
    ):
        self.path = Path(path)
        self.started_phase = started_phase
        self.success_field = success_field
        self.elapsed_field = elapsed_field
        self.correlation_field = correlation_field

    def events(self, since: Optional[datetime] = None) -> Iterator[dict]:
        """Yield events filtered by ``since`` (UTC threshold).

        Lines with bad JSON are skipped silently — the log is treated as
        append-only and may have partial writes during reads.
        """
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if since:
                    ts_str = event.get("ts", "")
                    try:
                        ts = datetime.fromisoformat(ts_str)
                    except (ValueError, TypeError):
                        continue
                    if ts < since:
                        continue
                yield event

    def summarize(
        self,
        since: Optional[datetime] = None,
        group_by: Optional[str] = None,
    ) -> dict:
        """Compute summary statistics across all events in the window.

        Returns dict with:
            total_started, phase_counts, success_count, completed_count,
            success_rate, elapsed_ms_p{50,90,99}, elapsed_ms_{min,max},
            and (if group_by) groups: {field_value: count}.
        """
        phases: Counter = Counter()
        terminal_outcomes: dict = defaultdict(list)
        elapsed_completed: List[int] = []
        groups: Counter = Counter()

        for event in self.events(since):
            phase = event.get("phase", "unknown")
            phases[phase] += 1
            rid = event.get(self.correlation_field, "")

            if phase == self.started_phase:
                if group_by:
                    val = event.get(group_by)
                    if val is not None:
                        groups[val] += 1
            else:
                # terminal event
                if rid:
                    terminal_outcomes[rid].append(event)
                if event.get(self.success_field) is True:
                    ms = event.get(self.elapsed_field)
                    if isinstance(ms, (int, float)):
                        elapsed_completed.append(int(ms))

        succeeded = sum(
            1
            for events in terminal_outcomes.values()
            for e in events
            if e.get(self.success_field) is True
        )
        # "completed" count = terminal events that have the success field set
        # (True or False). Skip events lacking the field entirely (e.g.
        # "rejected_recursion" outcomes that don't claim success/failure).
        completed_count = sum(
            1
            for events in terminal_outcomes.values()
            for e in events
            if e.get(self.success_field) is not None
        )
        success_rate = (succeeded / completed_count) if completed_count else None
        elapsed_completed.sort()

        result = {
            "total_started": phases.get(self.started_phase, 0),
            "phase_counts": dict(phases),
            "success_count": succeeded,
            "completed_count": completed_count,
            "success_rate": round(success_rate, 3) if success_rate is not None else None,
            "elapsed_ms_p50": _pct(elapsed_completed, 0.5),
            "elapsed_ms_p90": _pct(elapsed_completed, 0.9),
            "elapsed_ms_p99": _pct(elapsed_completed, 0.99),
            "elapsed_ms_min": elapsed_completed[0] if elapsed_completed else None,
            "elapsed_ms_max": elapsed_completed[-1] if elapsed_completed else None,
        }
        if group_by:
            result["groups"] = dict(groups)
            result["group_by_field"] = group_by
        return result

    def tail(self, n: int) -> List[dict]:
        """Return the last N requests as terminal-event records, oldest first.

        Each record carries the started ts, terminal phase, elapsed_ms (if
        available), success flag, and a short error/message excerpt.
        Requests without a terminal event (still in flight) are omitted.
        """
        by_id: dict = {}
        started_at: dict = {}
        for event in self.events():
            rid = event.get(self.correlation_field, "")
            if not rid:
                continue
            if event.get("phase") == self.started_phase:
                started_at[rid] = event.get("ts", "")
            else:
                by_id[rid] = {
                    self.correlation_field: rid,
                    "started_ts": started_at.get(rid, ""),
                    "terminal_phase": event.get("phase", "unknown"),
                    "elapsed_ms": event.get(self.elapsed_field),
                    "success": event.get(self.success_field),
                    "error": (event.get("msg") or event.get("error", ""))[:120],
                }
        rows = sorted(by_id.values(), key=lambda r: r.get("started_ts", ""))
        return rows[-n:] if n > 0 else rows


def _pct(vals: List[int], p: float) -> Optional[int]:
    """Compute percentile via simple index lookup. Returns None for empty lists."""
    if not vals:
        return None
    idx = int(len(vals) * p)
    return vals[min(idx, len(vals) - 1)]
