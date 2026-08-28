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
from dataclasses import dataclass, field
from typing import List, Optional

SENTINEL_TASK_ID = "000"

#: Breadcrumb epoch component, e.g. ``.../t_1786375853``.
_TS_RE = re.compile(r'/t_(\d+)')
_CYCLE_RE = re.compile(r'/c_(\d+)')


@dataclass
class Touch:
    """One recorded moment of attention on one task.

    ``begins_dwell`` marks a touch that arrived from a *different* task — the
    moment attention moved rather than stayed. It is computed here, in
    chronological order, and carried on the record.

    That placement is deliberate. Deriving it at render time from whichever
    line happens to sit above would make it a statement about the display
    rather than about what happened, and reversing the output would silently
    invert its meaning while it went on looking authoritative.
    """
    timestamp: int
    task_id: str
    cycle: Optional[int]
    description: str
    begins_dwell: bool = False


@dataclass
class Frame:
    """An in-progress task, classified by whether a return is actually owed.

    ``state`` is one of:

    ``active``
        The current position of attention. Not a debt.
    ``parked``
        Waiting on an incomplete blocker. Legitimately set down, and flagging
        it would be crying wolf — the distinction that keeps this useful.
    ``enclosing``
        Attention is *inside* this frame, in a descendant of it. Not a debt:
        the work is proceeding one level down. A MISSION with a running phase
        is the ordinary case, and calling it a dropped frame would make the
        false-alarm rate scale with *good* decomposition discipline.
    ``ready``
        Was blocked, and every declared blocker has since resolved. The frame
        is ripe to pick back up. This is the most actionable fact the stack
        knows, and it used to be destroyed on its way through: when a blocker
        completed, ``blockers_open`` emptied and the task fell straight into the
        residual, so "this was waiting on something and that something is done"
        became indistinguishable from "nobody ever returned to this".
    ``deferred``
        Nothing blocking it, and attention went elsewhere without completing it.

    ``ready`` is EARNED by an observed transition, never inferred from current
    state: it requires that a blocker was declared and has since cleared. A task
    that was never blocked and simply got set down is ``deferred``. Without that
    rule everything drifts into ``ready`` over time and the signal dies exactly
    the way the old residual did — a state that eventually describes most of the
    list stops discriminating, which is the failure being fixed.

    ``deferred`` names the observable rather than the motive. The previous name,
    ``abandoned``, asserted something the data cannot support: a frame set down
    when priorities shifted and one genuinely forgotten are identical here —
    in_progress, no open blocker, attention elsewhere. Picking the uncharitable
    reading told operators they had dropped work they fully intended to return
    to, and a label wrong most of the time gets discounted in the cases where it
    is right.

    The five states partition the open frames exhaustively: attention is here,
    or below here, or the frame waits on something, or that something has
    cleared, or it was set down. That is why the last branch can be decided last
    without being a *residual* — a catch-all assigns its label to every case its
    author did not enumerate, which is how both ``enclosing`` and ``ready`` came
    to be missing.
    """
    task_id: str
    subject: str
    state: str
    last_touch: Optional[int]
    blockers_open: List[str]
    parent_completed: bool
    # Declared blockers that have reached a terminal status. Non-empty with an
    # empty blockers_open is what makes a frame `ready` rather than `deferred`,
    # and it is also the ordering signal: freshly ready outranks long-ready.
    blockers_resolved: List[str] = field(default_factory=list)


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
    # Mark the moves once, in the order they happened.
    previous = None
    for touch in touches:
        touch.begins_dwell = touch.task_id != previous
        previous = touch.task_id
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

    # Every ancestor of the active frame encloses it. Walking *up* from where
    # attention is costs one pass and answers the question directly; asking
    # instead "does any descendant happen to be in progress" would wrongly
    # absolve a parent whose child was dropped alongside it.
    enclosing_ids = set()
    seen = set()
    cursor = newest_id
    while cursor is not None and cursor not in seen:
        seen.add(cursor)
        node = by_id.get(cursor)
        parent_id = getattr(getattr(node, "mtmd", None), "parent_id", None)
        cursor = str(parent_id) if parent_id is not None else None
        if cursor is not None:
            enclosing_ids.add(cursor)

    frames = []
    for task in in_progress:
        tid = str(task.id)
        _declared = [str(b) for b in (getattr(task, "blocked_by", None) or [])]
        blockers_open = [
            b for b in _declared
            if b in by_id and by_id[b].status not in ("completed", "archived")
        ]
        blockers_resolved = [
            b for b in _declared
            if b in by_id and by_id[b].status in ("completed", "archived")
        ]
        parent_id = getattr(getattr(task, "mtmd", None), "parent_id", None)
        parent = by_id.get(str(parent_id)) if parent_id is not None else None
        parent_completed = bool(parent and parent.status in ("completed", "archived"))

        # Order encodes precedence. Where attention *is* outranks where it is
        # waiting: a frame with work running inside it is not "set down waiting
        # on a blocker", whatever its blocker list still says.
        if tid == newest_id:
            state = "active"
        elif tid in enclosing_ids:
            state = "enclosing"
        elif blockers_open:
            state = "parked"
        elif blockers_resolved:
            # A blocker was declared and has cleared: ripe to resume. Requires
            # the declaration, so a never-blocked frame cannot arrive here.
            state = "ready"
        else:
            state = "deferred"

        frames.append(Frame(
            task_id=tid,
            subject=getattr(task, "subject", "") or "",
            state=state,
            last_touch=last_touch(task),
            blockers_open=blockers_open,
            parent_completed=parent_completed,
            blockers_resolved=blockers_resolved,
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
