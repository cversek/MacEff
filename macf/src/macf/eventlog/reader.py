"""Reading the agent's event log as lines a person can follow (``macf_tools events query``).

One line per event by default: the time, the event's name, and a short summary drawn from a
table of the events agents read most (the persistent layer's wakes, units and notices, tool
calls, prompts and permission dialogs), with a generic fallback for every other event.
``--verbose`` prints every field, and ``--json`` prints each event as one JSON line for scripts.

A scan bounded by ``--after`` stops at the first event older than the cutoff, reading the log
newest first: bounded in time, the unit the question is asked in, so a busy log can't shrink it
(``coding_standards`` §6.3).
"""
import fnmatch
import json
import os
import re
import time
from datetime import date, datetime
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

#: Events written by concurrent processes can land slightly out of timestamp order, so a scan
#: newest first stops only once it is this far past the cutoff.
CUTOFF_GRACE_S = 5.0
FALLBACK_FIELDS = 4
VALUE_CHARS = 80

RELATIVE = re.compile(r"^(\d+)([smhd])$")
CLOCK = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
EPOCH = re.compile(r"^\d+(\.\d+)?$")
UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _ids(value) -> str:
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value or "")


#: How the summary shows each event read most often. A tuple names the data fields shown, in
#: order, as ``field=value``; a callable builds the text. Any other event shows its first few
#: data fields.
SUMMARY: Dict[str, Union[Tuple[str, ...], Callable[[dict], str]]] = {
    "pd_wake_sent": lambda d: f"mail: {_ids(d.get('ids'))}" if d.get("ids") else f"{d.get('chars', '?')} chars",
    "pd_wake_held": ("reason", "waiting"),
    "pd_unit_state": ("unit", "state", "reason"),
    "pd_unit_alive": ("unit", "pid", "in_flight", "waiting_on"),
    "pd_control": ("act", "unit", "asked_by", "reason"),
    "pd_notice_delivered": ("source", "via", "arrival_id"),
    "store_arrival_detected": ("source", "count"),
    "tool_call_started": ("tool", "file_path"),
    "tool_call_completed": ("tool", "success"),
    "cli_command_invoked": lambda d: " ".join(str(a) for a in d["argv"]) if isinstance(d.get("argv"), list)
                                     else str(d.get("command", "")),
    "user_activity_detected": ("source", "detector", "content_preview"),
    "dev_drv_started": ("prompt_preview",),
    "dev_drv_ended": ("duration",),
    "permission_requested": ("tool_name", "tool_input_preview"),
    "task_started": ("task_id", "task_type"),
    "task_completed": ("task_id", "task_type"),
    "mode_change": ("mode", "enabled"),
    "work_mode_change": ("mode",),
    "keys_sent": ("kind", "text"),
    "compaction_detected": ("cycle", "detection_method"),
    "notification_received": ("notification_type", "message_preview"),
}


def parse_when(spec: str, now: Optional[float] = None, tz=None) -> float:
    """The epoch a time names: ``30m``, ``2h`` or ``7d`` before now (the relative form ``events
    analyze --since`` takes), ``09:00`` or ``09:00:30`` today, an ISO time (local when it names no
    zone) or an epoch. Raises ValueError for anything else, naming the forms it takes."""
    text = (spec or "").strip()
    now = time.time() if now is None else now
    rel = RELATIVE.match(text)
    if rel:
        return now - int(rel.group(1)) * UNIT_S[rel.group(2)]
    clock = CLOCK.match(text)
    if clock:
        hour, minute, second = int(clock.group(1)), int(clock.group(2)), int(clock.group(3) or 0)
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"not a clock time: {spec!r}")
        today = datetime.fromtimestamp(now, tz=tz) if tz else datetime.fromtimestamp(now)
        return today.replace(hour=hour, minute=minute, second=second, microsecond=0).timestamp()
    if EPOCH.match(text):
        return float(text)
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"not a time: {spec!r} (use 30m, 2h, 7d, 09:00, an ISO time or an epoch)") from None
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz) if tz else when.astimezone()
    return when.timestamp()


def matches(name: str, patterns: Sequence[str]) -> bool:
    """True when ``name`` matches any of the patterns, which may use shell globs (``pd_wake_*``)."""
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def _short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= VALUE_CHARS else text[:VALUE_CHARS - 1] + "…"


def summary_of(event: dict) -> str:
    """The short summary of one event, from ``SUMMARY`` or its first few data fields."""
    data = event.get("data")
    if not isinstance(data, dict):
        return _short(data) if data not in (None, "", [], {}) else ""
    how = SUMMARY.get(str(event.get("event", "")))
    if callable(how):
        return _short(how(data))
    fields = how if how else list(data)[:FALLBACK_FIELDS]
    return "  ".join(f"{k}={_short(data[k])}" for k in fields
                     if k in data and data[k] not in (None, "", [], {}))


def _when(event: dict) -> Optional[float]:
    """The event's epoch, or None when it carries no numeric timestamp (shown as ``??:??:??``,
    and outside any time bound's reach)."""
    ts = event.get("timestamp")
    return float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None


def format_line(event: dict, tz=None, today: Optional[date] = None) -> str:
    """``HH:MM:SS  name  summary``, with the date in front when the event isn't from ``today``."""
    ts = _when(event)
    if ts is None:
        stamp = "??:??:??"
    else:
        moment = datetime.fromtimestamp(ts, tz=tz) if tz else datetime.fromtimestamp(ts)
        stamp = moment.strftime("%H:%M:%S") if moment.date() == today else moment.strftime("%m-%d %H:%M:%S")
    return f"{stamp}  {event.get('event', '?')}  {summary_of(event)}".rstrip()


def format_verbose(event: dict, tz=None) -> str:
    """The event's line, then every field: the breadcrumb, each data field, and the hook input."""
    lines = [format_line(event, tz), f"  breadcrumb: {event.get('breadcrumb', '')}"]
    data = event.get("data")
    if isinstance(data, dict):
        lines += [f"  {k}: {v if isinstance(v, str) else json.dumps(v, default=str)}" for k, v in data.items()]
    elif data not in (None, ""):
        lines.append(f"  data: {json.dumps(data, default=str)}")
    for key, value in event.items():
        if key not in ("timestamp", "event", "breadcrumb", "data") and value not in (None, "", {}, []):
            lines.append(f"  {key}: {json.dumps(value, default=str)}")
    return "\n".join(lines)


def select(events_newest_first: Iterable[dict], after: Optional[float] = None, before: Optional[float] = None,
           patterns: Sequence[str] = (), limit: Optional[int] = None,
           keep: Optional[Callable[[dict], bool]] = None) -> List[dict]:
    """The matching events, oldest first. ``events_newest_first`` must be newest first: the scan
    stops past ``after`` and once ``limit`` events match, so it reads no further than asked."""
    out: List[dict] = []
    for event in events_newest_first:
        ts = _when(event)
        if after is not None and ts is not None and ts < after:
            if ts < after - CUTOFF_GRACE_S:
                break
            continue
        if before is not None and ts is not None and ts >= before:
            continue
        if patterns and not matches(str(event.get("event", "")), patterns):
            continue
        if keep is not None and not keep(event):
            continue
        out.append(event)
        if limit and len(out) >= limit:
            break
    out.reverse()
    return out


def follow(path, keep: Callable[[dict], bool], sleep: Callable[[float], None] = time.sleep,
           poll_s: float = 1.0) -> Iterator[dict]:
    """Events appended to the log at ``path`` from now on that ``keep`` accepts, as they arrive,
    until the caller stops. A line still being written is held until it ends; a log that shrinks
    (rotated) is read again from its start."""
    position = os.path.getsize(path) if os.path.exists(path) else 0
    partial = ""
    while True:
        sleep(poll_s)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size < position:
            position, partial = 0, ""
        if size == position:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            handle.seek(position)
            chunk = handle.read()
            position = handle.tell()
        lines = (partial + chunk).split("\n")
        partial = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and keep(event):
                yield event
