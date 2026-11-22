"""
Per-agent usage meter.

The account reports one whole-percent counter, so an agent cannot see what a loop of its
own costs. Each transcript line for an API call carries a ``usage`` record; this module
turns the new lines since the last look into ``usage_metered`` events in the agent's own
event log, and sums those events for the ``budget me`` view.

State lives in the events alone. A transcript's resume offset is the ``new_offset`` of its
latest ``usage_metered`` event, found with a read that crosses cycle boundaries and stops
at the first match, so a compaction does not reset it.

Counting rules:

- One API call is one ``message.id``. The same id appears on several lines (one per
  content block); the last usage seen for an id within a scan is the one counted.
- A call whose lines straddle two scans would be counted twice. Each event carries
  ``tail_id``, the id of the last call it counted, and the next scan skips lines with that
  id. The tail call's growth after the first scan is not recounted: a small, one-sided
  undercount, preferred to a double count.
- Only complete lines are consumed. A trailing partial line is left for the next scan.

Cause of an interval (``operator``, ``channel``, ``peer``, ``cron``, ``notice``, ``gate``,
``subagent``) comes from ``classify_prompt`` at prompt time and ``current_cause`` at meter
time.
"""

import glob
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

EVENT = "usage_metered"
TURN_CAUSE_EVENT = "turn_cause"
GATE_HELD_EVENT = "scope_gate_held"
FAULT_EVENT = "usage_meter_fault"
CHECKED_EVENT = "usage_meter_checked"
TOOL_EVENT = "tool_call_completed"
FAULT_REPEAT_S = 3600.0
MAIN_CHECK_EVERY_S = 600.0

#: Weights relative to one uncached input token, and the fitted points per weighted token.
RATE_LABEL = "provisional (fitted 2026-11-22)"
POINTS_PER_WEIGHTED_TOKEN = 4.08e-8
WEIGHTS = {
    "input_tokens": 1.0,
    "cache_write_1h_tokens": 2.0,
    "cache_write_5m_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
    "output_tokens": 5.0,
}
TOKEN_KINDS = tuple(WEIGHTS)

CAUSES = ("operator", "channel", "peer", "cron", "notice", "gate", "subagent")


def classify_prompt(text: str) -> str:
    """The cause of a turn from the prompt text that opened it.

    A channel tag or a cross-session message marks those sources wherever it sits. A text
    that starts with ``[cron:`` is a scheduled prompt (``cron``); one containing a
    ``<task-notification>`` block is a harness notice (``notice``). Everything else is
    ``operator``.
    """
    text = text or ""
    if "<channel source=" in text:
        return "channel"
    if "<cross-session-message" in text:
        return "peer"
    if text.lstrip().startswith("[cron:"):
        return "cron"
    if "<task-notification>" in text:
        return "notice"
    return "operator"


def current_cause() -> str:
    """The cause of the interval being metered now, from the newest of the latest
    ``turn_cause`` and ``scope_gate_held`` events; a held gate newer than the turn cause
    means a blocked Stop forced the turn. Defaults to ``operator`` with neither."""
    from macf.agent_events_log import read_events
    for ev in read_events(reverse=True, scope="all", only=(TURN_CAUSE_EVENT, GATE_HELD_EVENT)):
        if ev.get("event") == GATE_HELD_EVENT:
            return "gate"
        cause = (ev.get("data") or {}).get("cause")
        return cause if cause in CAUSES else "operator"
    return "operator"


@dataclass(frozen=True, kw_only=True)
class ScanResult:
    by_model: Dict[str, Dict[str, int]]
    calls: int
    new_offset: int
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    tail_id: Optional[str] = None


def _blank() -> Dict[str, int]:
    return {**{k: 0 for k in TOKEN_KINDS}, "calls": 0}


def _usage_row(usage: dict) -> Dict[str, int]:
    """Token counts of one usage record; cache writes split by lifetime."""
    cc = usage.get("cache_creation")
    total_write = int(usage.get("cache_creation_input_tokens") or 0)
    if isinstance(cc, dict) and ("ephemeral_5m_input_tokens" in cc or "ephemeral_1h_input_tokens" in cc):
        w5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
        w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
    else:
        w5, w1 = 0, total_write
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_write_5m_tokens": w5,
        "cache_write_1h_tokens": w1,
    }


def scan(path, offset: int = 0, skip_id: Optional[str] = None) -> ScanResult:
    """Total the API calls in the transcript at ``path`` from byte ``offset``.

    ``skip_id`` is the previous scan's ``tail_id``: lines for that call are not counted again.
    """
    path = Path(path)
    size = path.stat().st_size
    if offset > size:
        print(f"⚠️ MACF: usage meter: {path.name} is shorter than offset {offset}; rescanning from 0",
              file=sys.stderr)
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1  # only complete lines
    calls: Dict[str, dict] = {}
    order: List[str] = []
    pos = offset
    for raw in data[:end].split(b"\n")[:-1]:
        pos += len(raw) + 1
        if b'"usage"' not in raw or b'"assistant"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError as e:
            print(f"⚠️ MACF: usage meter: skipped a malformed line ending at byte {pos} of {path.name}: {e}",
                  file=sys.stderr)
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        if entry.get("type") != "assistant" or not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        mid = msg.get("id") or f"line@{pos}"
        if mid == skip_id:
            continue
        if mid not in calls:
            order.append(mid)
        calls[mid] = {"model": msg.get("model") or "unknown", "row": _usage_row(msg["usage"]),
                      "ts": entry.get("timestamp")}
    by_model: Dict[str, Dict[str, int]] = {}
    for mid in order:
        c = calls[mid]
        tot = by_model.setdefault(c["model"], _blank())
        for k, v in c["row"].items():
            tot[k] += v
        tot["calls"] += 1
    stamps = [calls[m]["ts"] for m in order if calls[m]["ts"]]
    return ScanResult(by_model=by_model, calls=len(order), new_offset=offset + end,
                      first_ts=min(stamps) if stamps else None, last_ts=max(stamps) if stamps else None,
                      tail_id=order[-1] if order else skip_id)


@dataclass(frozen=True, kw_only=True)
class _Resume:
    offset: int = 0
    tail_id: Optional[str] = None
    metering_since: Optional[float] = None
    at: Optional[float] = None


_BASELINE_TAIL_BYTES = 64 * 1024
_BOUND_SLACK_S = 60.0


_START_SCAN_LINES = 50
_START_SCAN_BYTES = 256 * 1024


def _file_start(path: str) -> float:
    """When a file began: the first timestamp among its opening lines, else its birth time, else 0.

    Never its mtime: a transcript being written has an mtime of now, so a floor taken from it
    finds none of the file's own events, and every tick would baseline it again. A transcript
    can open with records that carry no timestamp (a file-history snapshot), so several lines
    are tried. 0 means "unknown", which costs one unbounded walk and is never wrong.
    """
    from datetime import datetime
    try:
        with open(path, "rb") as f:
            head = f.read(_START_SCAN_BYTES)
    except OSError as e:
        print(f"⚠️ MACF: usage meter: cannot read {path}: {e}; reading the whole log for it", file=sys.stderr)
        return 0.0
    for raw in head.split(b"\n")[:_START_SCAN_LINES]:
        if b'"timestamp"' not in raw:
            continue
        try:
            stamp = json.loads(raw).get("timestamp")
            if stamp:
                return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError) as e:
            print(f"⚠️ MACF: usage meter: an unreadable opening line in {path} ({e}); trying the next",
                  file=sys.stderr)
    try:
        born = getattr(os.stat(path), "st_birthtime", None)
    except OSError as e:
        print(f"⚠️ MACF: usage meter: cannot stat {path}: {e}; reading the whole log for it", file=sys.stderr)
        born = None
    return float(born) if born else 0.0


def _walk(paths: List[str]) -> Dict[str, _Resume]:
    """Each path's resume point from its latest ``usage_metered`` event, in one reverse walk.

    No event about a file is older than the file, so the walk stops once it passes the oldest
    floor among the files still unfound (or when all are found).
    """
    from macf.agent_events_log import read_events
    floors = {p: _file_start(p) - _BOUND_SLACK_S for p in paths}
    found: Dict[str, _Resume] = {}
    for ev in read_events(reverse=True, scope="all", only=EVENT, since=min(floors.values())):
        d = ev.get("data") or {}
        p = d.get("path")
        if p in floors and p not in found:
            found[p] = _Resume(offset=int(d.get("new_offset") or 0), tail_id=d.get("tail_id"),
                               metering_since=d.get("metering_since"), at=ev.get("timestamp"))
        pending = [floors[q] for q in floors if q not in found]
        if not pending:
            break
        if ev.get("timestamp", 0) < min(pending):
            break
    return found


def _earlier_events(paths: List[str]) -> Dict[str, _Resume]:
    """The latest event of each path anywhere in the current cycle, without the file-age floor.

    Run only for files the floored walk did not find. A file with an event here has been metered
    before, so baselining it again would drop every call since: the lookup missed it, which is a
    fault. Bounded by the cycle, which holds finitely many events.
    """
    from macf.agent_events_log import read_events
    found: Dict[str, _Resume] = {}
    for ev in read_events(reverse=True, scope="cycle", only=EVENT):
        d = ev.get("data") or {}
        p = d.get("path")
        if p in paths and p not in found:
            found[p] = _Resume(offset=int(d.get("new_offset") or 0), tail_id=d.get("tail_id"),
                               metering_since=d.get("metering_since"), at=ev.get("timestamp"))
            if len(found) == len(paths):
                break
    return found


@dataclass(frozen=True, kw_only=True)
class _Lookup:
    points: Dict[str, _Resume]
    quiet: frozenset  # files not touched since their last tick: nothing to meter, nothing to look up
    lost: frozenset = frozenset()  # files whose earlier event the floored walk missed, found by the fallback


def _resume_points(main: str, others: List[str]) -> _Lookup:
    """Resume points for the main transcript and the subagent files.

    The main transcript is found first; its latest event is recent. A tick scans every file, so
    a file not modified since a minute before that event had nothing new at that tick or since:
    it is quiet and costs one ``stat``. Only the files touched since are looked up. Without a
    main event no file has one either (a tick baselines the main transcript first), so nothing
    more is walked.
    """
    points = _walk([main])
    lost = set()
    if main not in points:
        again = _earlier_events([main])
        if not again:
            return _Lookup(points={}, quiet=frozenset())
        points.update(again)
        lost.add(main)
    last_tick = points[main].at or 0.0
    busy, quiet = [], set()
    for p in others:
        try:
            touched = os.stat(p).st_mtime
        except OSError as e:
            print(f"⚠️ MACF: usage meter: cannot stat {p}: {e}; looking it up anyway", file=sys.stderr)
            touched = float("inf")
        if touched > last_tick - _BOUND_SLACK_S:
            busy.append(p)
        else:
            quiet.add(p)
    if busy:
        points.update(_walk(busy))
        since = points[main].metering_since or time.time()
        # only a file that began before metering did should have an event; a new one has none to find
        missed = [p for p in busy if p not in points and _file_start(p) < since]
        again = _earlier_events(missed) if missed else {}
        points.update(again)
        lost.update(again)
    return _Lookup(points=points, quiet=frozenset(quiet), lost=frozenset(lost))


def _baseline(path: str) -> _Resume:
    """Where metering of a file never seen before starts: the end of its last complete line, with
    the id of the last call in its final 64 KB so a call split across that point is not counted
    later. History is not read."""
    size = os.stat(path).st_size
    start = max(0, size - _BASELINE_TAIL_BYTES)
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    end = data.rfind(b"\n") + 1
    lines = data[:end].split(b"\n")[:-1]
    if start > 0 and lines:
        lines = lines[1:]  # the first line of a mid-file read is cut
    tail = None
    for raw in reversed(lines):
        if b'"usage"' not in raw:
            continue
        try:
            msg = json.loads(raw).get("message")
        except ValueError as e:
            print(f"⚠️ MACF: usage meter: a malformed line near the end of {path} ({e}); looking further back",
                  file=sys.stderr)
            continue
        if isinstance(msg, dict) and msg.get("id") and isinstance(msg.get("usage"), dict):
            tail = msg["id"]
            break
    return _Resume(offset=start + end, tail_id=tail)


def _fault_due(kind: str, now: float) -> bool:
    """True unless a ``usage_meter_fault`` of this kind was recorded in the last hour."""
    from macf.agent_events_log import read_events
    for ev in read_events(reverse=True, scope="all", only=FAULT_EVENT, since=now - FAULT_REPEAT_S):
        if (ev.get("data") or {}).get("kind") == kind:
            return False
    return True


def _raise_fault(kind: str, detail: str, now: float) -> bool:
    """Warn and record a fault, at most once an hour per kind. Returns whether it fired."""
    from macf.agent_events_log import append_event
    from macf.observability import Warning, emit_warning
    if not _fault_due(kind, now):
        return False
    emit_warning(Warning(source="usage_meter", kind=kind, detail=detail))
    append_event(FAULT_EVENT, {"kind": kind, "detail": detail})
    return True


def _check_main_silent(main: str, now: float, since: float) -> None:
    """Warn when tools ran in the last hour but the main transcript counted no calls.

    Runs at most once every ``MAIN_CHECK_EVERY_S``, found from the last ``usage_meter_checked``
    event. Both reads stop at the last hour or when metering began, whichever is later; the
    metered read stops at the first healthy event.
    """
    from macf.agent_events_log import append_event, read_events
    for ev in read_events(reverse=True, scope="all", only=CHECKED_EVENT, since=now - MAIN_CHECK_EVERY_S):
        return
    append_event(CHECKED_EVENT, {})
    tools = 0
    for ev in read_events(reverse=True, scope="all", only=(EVENT, TOOL_EVENT), since=max(now - 3600.0, since)):
        if ev.get("event") == TOOL_EVENT:
            tools += 1
            continue
        d = ev.get("data") or {}
        if d.get("path") == main and (d.get("calls") or 0) > 0:
            return
    if tools:
        _raise_fault("main_silent", f"{tools} tool calls in the last hour but the main transcript counted "
                                    f"no calls", now)


def meter_tick(session_id: str, transcript_path: str, now: Optional[float] = None) -> Optional[dict]:
    """Meter the new calls of a session's transcript and its subagents' transcripts.

    Emits one ``usage_metered`` event per file with new calls. A file with no earlier event gets
    a baseline event (``baseline: true``, ``calls: 0``) at its current end instead of a scan, so
    metering starts at first sight and a hook never pays for history. A file is baselined only
    if it began before metering did (``metering_since``, set by the main transcript's first
    event and copied into every later event); a file that began after it, such as a subagent
    that ran and ended within a turn, is scanned from offset 0. Returns a summary
    (``{"events": n, "calls": n}``), or None when nothing was recorded.

    Two faults are raised (``_raise_fault``): a file whose earlier event the lookup missed
    (``rebaselined``; it resumes from that event instead of baselining) and a main transcript
    that counted nothing while tools ran (``main_silent``). A tick that counted calls also
    records the rolling summary the hook line reads (``usage_share.roll``).
    """
    from macf.agent_events_log import append_event
    now = now or time.time()
    main = Path(transcript_path)
    files = [(str(main), None)]
    if session_id:
        sub_dir = main.parent / session_id / "subagents"
        files += [(p, "subagent") for p in sorted(glob.glob(str(sub_dir / "*.jsonl")))]
    live = [(p, c) for p, c in files if os.path.exists(p)]
    lookup = _resume_points(str(main), [p for p, _ in live if p != str(main)])
    resume = lookup.points
    cause = None
    events = calls = 0
    main_point = resume.get(str(main))
    since = (main_point.metering_since if main_point else None) or time.time()
    for path in sorted(lookup.lost):
        _raise_fault("rebaselined", f"{Path(path).name} had an earlier metering event the lookup missed; "
                                    f"resuming from it instead of baselining", now)
    for path, fixed_cause in live:
        if path in lookup.quiet:
            continue
        try:
            if path not in resume and (path == str(main) or _file_start(path) < since):
                base = _baseline(path)
                append_event(EVENT, {
                    "session_id": session_id, "path": path, "offset": base.offset, "new_offset": base.offset,
                    "first_ts": None, "last_ts": None, "by_model": {}, "calls": 0, "baseline": True,
                    "metering_since": since, "cause": fixed_cause or "operator", "tail_id": base.tail_id,
                })
                events += 1
                continue
            point = resume.get(path, _Resume())
            res = scan(path, point.offset, point.tail_id)
        except OSError as e:
            print(f"⚠️ MACF: usage meter: cannot read {path}: {e}; skipped this tick", file=sys.stderr)
            continue
        if not res.calls:
            continue
        if fixed_cause is None:
            cause = cause or current_cause()
        append_event(EVENT, {
            "session_id": session_id, "path": path, "offset": point.offset, "new_offset": res.new_offset,
            "first_ts": res.first_ts, "last_ts": res.last_ts, "by_model": res.by_model,
            "calls": res.calls, "cause": fixed_cause or cause, "tail_id": res.tail_id,
            "metering_since": since,
        })
        events += 1
        calls += res.calls
    if calls:
        from macf.usage_share import roll
        roll(now)
    try:
        _check_main_silent(str(main), now, since)
    except OSError as e:
        print(f"⚠️ MACF: usage meter: main-silent check skipped: {e}", file=sys.stderr)
    return {"events": events, "calls": calls} if events else None


# ── The budget me view ────────────────────────────────────────────────────────

def weighted(row: Dict[str, int], cache_read_weight: Optional[float] = None) -> float:
    w = dict(WEIGHTS)
    if cache_read_weight is not None:
        w["cache_read_input_tokens"] = cache_read_weight
    return sum(w[k] * row.get(k, 0) for k in TOKEN_KINDS)


@dataclass
class Summary:
    tokens: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in TOKEN_KINDS})
    by_model: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_cause: Dict[str, float] = field(default_factory=dict)
    low_by_cause: Dict[str, float] = field(default_factory=dict)
    calls: int = 0


def summarize(since: float) -> Summary:
    """Sum the ``usage_metered`` events at or after the epoch time ``since``."""
    from macf.agent_events_log import read_events
    s = Summary()
    for ev in read_events(reverse=True, scope="all", only=EVENT, since=since):
        d = ev.get("data") or {}
        cause = d.get("cause") or "operator"
        for model, row in (d.get("by_model") or {}).items():
            m = s.by_model.setdefault(model, _blank())
            for k in (*TOKEN_KINDS, "calls"):
                m[k] += row.get(k, 0)
                if k in s.tokens:
                    s.tokens[k] += row.get(k, 0)
            s.calls += row.get("calls", 0)
            s.by_cause[cause] = s.by_cause.get(cause, 0.0) + weighted(row)
            s.low_by_cause[cause] = s.low_by_cause.get(cause, 0.0) + weighted(row, 0.0)
    return s


def format_summary(s: Summary, label: str) -> str:
    """The view, kept to about 60 columns."""
    def n(x): return f"{int(x):,}"
    def short(x):
        x = float(x)
        return f"{x/1e6:.2f}M" if x >= 1e6 else f"{x/1e3:.1f}k" if x >= 1e3 else f"{x:.0f}"
    names = {"input_tokens": "input", "cache_write_1h_tokens": "cache write 1h",
             "cache_write_5m_tokens": "cache write 5m", "cache_read_input_tokens": "cache read",
             "output_tokens": "output"}
    total_w = sum(s.by_cause.values())
    low_w = sum(s.low_by_cause.values())
    lines = [f"usage, last {label}: {n(s.calls)} calls", "", "tokens"]
    lines += [f"  {names[k]:<15}{n(s.tokens[k]):>14}" for k in TOKEN_KINDS]
    lines += ["", "by model (calls, weighted)"]
    for model, row in sorted(s.by_model.items(), key=lambda kv: -weighted(kv[1])):
        lines.append(f"  {model[:30]:<30}{n(row['calls']):>7}{short(weighted(row)):>9}")
    lines += ["", "by cause (weighted)"]
    for cause, w in sorted(s.by_cause.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {cause:<15}{short(w):>10}{(100 * w / total_w if total_w else 0):>6.1f}%")
    lines += ["", f"points {total_w * POINTS_PER_WEIGHTED_TOKEN:.3f}"
                  f"  (low, reads 0: {low_w * POINTS_PER_WEIGHTED_TOKEN:.3f})",
              f"rate {RATE_LABEL}"]
    return "\n".join(lines)


def run_me(since_spec: str) -> str:
    from macf.cli import _parse_since
    from macf.usage_share import me_lines
    since = _parse_since(since_spec)
    return format_summary(summarize(since), since_spec) + "\n\n" + me_lines((time.time() - since) / 3600)
