"""Where attention has been, and what it owes a return to.

The task tree shows *where* work is. It does not show the order attention moved
through it, and that ordering is the difference between a stack and a pile: a
tree with six open tasks tells you six things are unfinished, not which one you
were in the middle of and meant to come back to.

The ordering is not missing — it is discarded. Every task update carries a
breadcrumb with a ``t_`` timestamp, so the full visitation sequence is already
on disk. The tree's recency marker is the ``argmax`` over those timestamps, and
reducing an ordered trace to a single pointer throws away everything except its
last element.

This module performs the other reductions: the path attention actually took,
and the frames it left behind without returning.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

SENTINEL_TASK_ID = "000"

#: Breadcrumb epoch component, e.g. ``.../t_1786375853``.
_TS_RE = re.compile(r'/t_(\d+)')
_CYCLE_RE = re.compile(r'/c_(\d+)')


@dataclass
class Touch:
    """One recorded moment of attention on one task."""
    timestamp: int
    task_id: str
    cycle: Optional[int]
    description: str


@dataclass
class Frame:
    """An in-progress task, classified by whether a return is actually owed.

    ``state`` is one of:

    ``active``
        The current position of attention. Not a debt.
    ``parked``
        Waiting on an incomplete blocker. Legitimately set down, and flagging
        it would be crying wolf — the distinction that keeps this useful.
    ``abandoned``
        Unblocked, and attention went elsewhere without completing it. This is
        the dropped frame.
    """
    task_id: str
    subject: str
    state: str
    last_touch: Optional[int]
    blockers_open: List[str]
    parent_completed: bool


def _breadcrumbs(task):
    for update in (getattr(getattr(task, "mtmd", None), "updates", None) or []):
        bc = getattr(update, "breadcrumb", "") or ""
        if bc:
            yield bc, (getattr(update, "description", "") or "")


def last_touch(task) -> Optional[int]:
    """Epoch of the most recent recorded update, or None if never touched."""
    stamps = [int(m.group(1)) for bc, _ in _breadcrumbs(task)
              for m in [_TS_RE.search(bc)] if m]
    return max(stamps) if stamps else None


def visitation_trace(tasks) -> List[Touch]:
    """Every recorded touch across all tasks, in the order they happened.

    This is the path attention took. Consecutive touches on the same task are
    preserved rather than collapsed — the dwell is part of the shape.
    """
    touches = []
    for task in tasks:
        for bc, desc in _breadcrumbs(task):
            m = _TS_RE.search(bc)
            if not m:
                continue
            cyc = _CYCLE_RE.search(bc)
            touches.append(Touch(
                timestamp=int(m.group(1)),
                task_id=str(task.id),
                cycle=int(cyc.group(1)) if cyc else None,
                description=desc.replace("\n", " ").strip(),
            ))
    touches.sort(key=lambda t: t.timestamp)
    return touches


def open_frames(tasks) -> List[Frame]:
    """In-progress tasks, classified by whether a return is genuinely owed.

    Ordered oldest-touch first, so the frame most likely to have been forgotten
    is the one reported first.
    """
    by_id = {str(t.id): t for t in tasks}
    in_progress = [t for t in tasks
                   if t.status == "in_progress" and str(t.id) != SENTINEL_TASK_ID]
    if not in_progress:
        return []

    # The current position: whichever task was touched last overall. It is
    # in-progress by definition of being where we are, and is not a debt.
    newest_id, newest_ts = None, -1
    for task in tasks:
        ts = last_touch(task)
        if ts is not None and ts > newest_ts:
            newest_ts, newest_id = ts, str(task.id)

    frames = []
    for task in in_progress:
        tid = str(task.id)
        blockers_open = [
            str(b) for b in (getattr(task, "blocked_by", None) or [])
            if str(b) in by_id and by_id[str(b)].status not in ("completed", "archived")
        ]
        parent_id = getattr(getattr(task, "mtmd", None), "parent_id", None)
        parent = by_id.get(str(parent_id)) if parent_id is not None else None
        parent_completed = bool(parent and parent.status in ("completed", "archived"))

        if tid == newest_id:
            state = "active"
        elif blockers_open:
            state = "parked"
        else:
            state = "abandoned"

        frames.append(Frame(
            task_id=tid,
            subject=getattr(task, "subject", "") or "",
            state=state,
            last_touch=last_touch(task),
            blockers_open=blockers_open,
            parent_completed=parent_completed,
        ))

    frames.sort(key=lambda f: (f.last_touch is None, f.last_touch or 0))
    return frames


def contradictory_frames(tasks) -> List[Frame]:
    """Frames whose parent is complete while they are still running.

    A structural check needing no timestamps: a parent cannot honestly be
    complete while a child of it is in progress. Cheaper and more certain than
    the staleness heuristic, and it catches the case where a whole branch was
    declared finished with one phase still open.
    """
    return [f for f in open_frames(tasks)
            if f.parent_completed and f.state != "active"]
