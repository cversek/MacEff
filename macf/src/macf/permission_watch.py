"""A permission prompt nobody is answering, seen from outside the session.

While Claude Code shows a permission dialog, the whole session waits: no tool
runs, no scheduled prompt fires, and nothing the session could run to report
itself will run. The PermissionRequest hook tells the operator once, at the
moment the dialog opens. If that one message is missed, the agent waits for
hours and looks, from every angle but this one, exactly like an agent at rest.
Measured: three stalls of 3, 17 and 12 hours, each on a command an allow rule
was meant to cover.

This module answers "is any session of this agent waiting on a permission
dialog right now, and since when?" from the agent's event log, and `watch`
turns the answer into reminders. It must run OUTSIDE the session it watches (a
timer, a cron job, a supervisor): the watched session cannot run it while it
waits. Policy: autonomous_operation section 5.5.

How a wait is read. For each session, the newest event that decides the
question settles it: a ``permission_requested`` means waiting since that
event's time; any PROGRESS event (a tool starting or finishing, a prompt
starting or ending, a session starting or ending, a compaction) means not
waiting. Events that happen DURING a dialog decide nothing:
``notification_received`` fires because of the dialog, and
``user_activity_detected`` carries no session and fires while the operator
types anywhere.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

REQUEST = "permission_requested"
PROGRESS = frozenset({
    "tool_call_started",
    "tool_call_completed",
    "dev_drv_started",
    "dev_drv_ended",
    "session_started",
    "session_ended",
    "compaction_detected",
})

STATE_NAME = "permission_watch.json"


@dataclass(frozen=True)
class Waiting:
    """One session waiting on one permission dialog."""
    session_id: str
    since: float
    tool: str
    preview: str

    def age_minutes(self, now: float) -> float:
        return (now - self.since) / 60.0

    @property
    def key(self) -> str:
        return f"{self.session_id}@{self.since:.3f}"


def _session_of(event: dict) -> Optional[str]:
    data = event.get("data") or {}
    hook_input = event.get("hook_input") or {}
    return data.get("session_id") or hook_input.get("session_id")


def _preview(event: dict) -> str:
    hook_input = event.get("hook_input") or {}
    tool_input = hook_input.get("tool_input")
    if isinstance(tool_input, dict):
        text = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("skill")
        if text:
            return str(text)
    return str((event.get("data") or {}).get("tool_input_preview", ""))


def waiting(events_newest_first: Iterable[dict]) -> List[Waiting]:
    """Sessions whose newest deciding event is a permission request.

    ``events_newest_first`` must be newest first; the first deciding event
    seen for a session settles it and older ones are ignored.
    """
    decided: Dict[str, Optional[Waiting]] = {}
    for event in events_newest_first:
        name = event.get("event")
        if name != REQUEST and name not in PROGRESS:
            continue
        sid = _session_of(event)
        if not sid or sid in decided:
            continue
        if name == REQUEST:
            data = event.get("data") or {}
            decided[sid] = Waiting(
                session_id=sid,
                since=float(data.get("timestamp") or event.get("timestamp") or 0.0),
                tool=str(data.get("tool_name", "unknown")),
                preview=_preview(event),
            )
        else:
            decided[sid] = None
    return sorted((w for w in decided.values() if w is not None), key=lambda w: w.since)


def read_waiting() -> List[Waiting]:
    """``waiting`` over this agent's log, current cycle only.

    Cycle scope is exact here, not an approximation: a session that is waiting
    on a dialog cannot compact, so its request is in the current cycle.
    """
    from macf.agent_events_log import read_events
    return waiting(read_events(reverse=True, scope="cycle", only=PROGRESS | {REQUEST}))


def state_path() -> Path:
    from macf.agent_events_log import get_log_path
    return get_log_path().parent / STATE_NAME


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def _fmt_age(minutes: float) -> str:
    if minutes < 90:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h"


def reminder_text(w: Waiting, now: float, agent: str) -> str:
    started = time.strftime("%H:%M", time.localtime(w.since))
    command = w.preview if len(w.preview) <= 600 else w.preview[:600] + " ..."
    return (
        f"⏳ {agent} has been WAITING on a permission prompt for {_fmt_age(w.age_minutes(now))} "
        f"(since {started}). Nothing in that session runs until it is answered.\n"
        f"Tool: {w.tool}\n{command}"
    )


def resolved_text(key_state: dict, now: float, agent: str) -> str:
    minutes = (now - key_state["since"]) / 60.0
    return f"✅ {agent}: the permission prompt from {time.strftime('%H:%M', time.localtime(key_state['since']))} was answered (waited {_fmt_age(minutes)})."


def watch(
    current: List[Waiting],
    now: float,
    *,
    older_than_min: float,
    repeat_min: float,
    state: dict,
    send: Callable[[str], bool],
    agent: str,
) -> dict:
    """One pass: remind about each wait past ``older_than_min``, again every
    ``repeat_min``, and say once when a wait we reminded about is over.

    Returns the new state. A reminder that fails to send is not recorded as
    sent, so the next pass tries again.
    """
    new_state: dict = {}
    live = {w.key: w for w in current}
    for key, w in live.items():
        if w.age_minutes(now) < older_than_min:
            continue
        prior = state.get(key)
        due = prior is None or (now - prior["last_sent"]) / 60.0 >= repeat_min
        if due and send(reminder_text(w, now, agent)):
            new_state[key] = {"since": w.since, "last_sent": now, "tool": w.tool}
        elif prior is not None:
            new_state[key] = prior
    for key, prior in state.items():
        if key not in live and send(resolved_text(prior, now, agent)) is False:
            new_state[key] = prior  # try the all-clear again next pass
    return new_state


def as_json(current: List[Waiting], now: float) -> str:
    return json.dumps(
        [dict(asdict(w), age_minutes=round(w.age_minutes(now), 1)) for w in current],
        indent=2,
    )
