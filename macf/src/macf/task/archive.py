"""Archiving tasks: put work down, on the record, reversibly.

An archived task is one the agent has put down without finishing it here: the
work moved to another agent, was abandoned, or belongs to a project that ended.
Archiving sets its status to ``archived``, appends an ``archive`` update that
carries the reason and the status it had, and sets the MTMD ``archived`` flag.
``unarchive`` reverses all three from that update. Nothing is copied anywhere:
the store keeps every task file, so a second copy could only drift from it.

Every change is read back from disk before it is reported. The command this
module replaces was retired for reporting a state change it had not made; an
archive whose write did not stick is a failure here, named, not a success.
"""

import copy
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .models import MacfTask, MacfTaskUpdate
from .reader import TaskReader, update_task_file

ARCHIVED = "archived"
ARCHIVE_UPDATE = "archive"
UNARCHIVE_UPDATE = "unarchive"


def is_archived(task: MacfTask) -> bool:
    """True for a task put down by `task archive`, or carrying the legacy MTMD flag.

    Two notions used to disagree: the tree read the MTMD flag and everything
    else read the status. One predicate, so every reader agrees.
    """
    if task.status == ARCHIVED:
        return True
    return bool(task.mtmd and getattr(task.mtmd, "archived", False))


@dataclass
class ArchiveReport:
    """What an archive or unarchive call did, counted from what was read back."""
    changed: List[str] = field(default_factory=list)       # read back in the new state
    unchanged: List[str] = field(default_factory=list)     # already in the target state
    failed: List[Dict[str, str]] = field(default_factory=list)  # {"id", "why"}
    missing: List[str] = field(default_factory=list)       # requested ids not in the store
    planned: List[MacfTask] = field(default_factory=list)  # the tasks considered, in order
    descoped: List[str] = field(default_factory=list)      # removed from sprint scope
    kept: List[str] = field(default_factory=list)          # archived by an earlier call; left archived
    root_of: Dict[str, str] = field(default_factory=dict)  # task id -> the requested id it came under

    @property
    def ok(self) -> bool:
        return not self.failed and not self.missing


def _subtree(root: MacfTask, children_of: Dict[Optional[str], List[MacfTask]]) -> List[MacfTask]:
    """The root and every descendant, depth first, each once (cycle-safe)."""
    out, seen, stack = [], set(), [root]
    while stack:
        t = stack.pop()
        if t.id in seen:
            continue
        seen.add(t.id)
        out.append(t)
        stack.extend(reversed(children_of.get(str(t.id), [])))
    return out


def plan(task_ids: List[str], cascade: bool, reader: TaskReader) -> ArchiveReport:
    """The tasks an archive or unarchive of `task_ids` would touch, without touching them."""
    from .hierarchy import children_index
    report = ArchiveReport()
    all_tasks = reader.read_all_tasks()
    by_id = {str(t.id): t for t in all_tasks}
    children_of = children_index(all_tasks)
    seen = set()
    for raw in task_ids:
        tid = str(raw).lstrip("#")
        root = by_id.get(tid)
        if root is None:
            report.missing.append(tid)
            continue
        for t in (_subtree(root, children_of) if cascade else [root]):
            if t.id not in seen:
                seen.add(t.id)
                report.planned.append(t)
                report.root_of[t.id] = root.id
    return report


def _same_archive_call(task: MacfTask, root: MacfTask) -> bool:
    """True when `task` was put down by the same `task archive` call as `root`.

    One call stamps every task it archives with one `archived_at` to the
    microsecond, so a descendant archived earlier, on its own, carries a
    different stamp and stays archived when its ancestor is unarchived. (The
    breadcrumb cannot serve: two calls in the same second share one.)
    """
    def stamp(t):
        return getattr(t.mtmd, "archived_at", None) if t.mtmd else None
    return stamp(task) == stamp(root)


def _prior_status(task: MacfTask) -> str:
    """The status recorded by the most recent archive update, else 'pending'."""
    for u in reversed((task.mtmd.updates if task.mtmd else None) or []):
        if getattr(u, "type", None) == ARCHIVE_UPDATE and getattr(u, "prior_status", None):
            return u.prior_status
    return "pending"


def _write(task: MacfTask, new_status: str, update: MacfTaskUpdate, archived_flag: bool,
           call_stamp: str, session_uuid: Optional[str]) -> bool:
    fields = {"status": new_status}
    if task.mtmd:
        new_mtmd = copy.deepcopy(task.mtmd)
        new_mtmd.updates.append(update)
        new_mtmd.archived = archived_flag
        new_mtmd.archived_at = call_stamp if archived_flag else None
        fields["description"] = task.description_with_updated_mtmd(new_mtmd)
    return update_task_file(task.id, fields, session_uuid)


def _apply(task_ids: List[str], *, archive: bool, reason: str, cascade: bool,
           dry_run: bool, breadcrumb: str, session_uuid: Optional[str]) -> ArchiveReport:
    reader = TaskReader(session_uuid)
    report = plan(task_ids, cascade, reader)
    if dry_run:
        return report

    by_id = {t.id: t for t in report.planned}
    call_stamp = datetime.now().isoformat(timespec="microseconds")
    for t in report.planned:
        if is_archived(t) == archive:
            report.unchanged.append(t.id)
            continue
        root = by_id.get(report.root_of.get(t.id, t.id), t)
        if not archive and t.id != root.id and not _same_archive_call(t, root):
            report.kept.append(t.id)
            continue
        if archive:
            new_status = ARCHIVED
            update = MacfTaskUpdate(breadcrumb=breadcrumb, agent="PA", type=ARCHIVE_UPDATE,
                                    description=f"Archived: {reason}", prior_status=t.status)
        else:
            # A task carrying only the legacy flag was never moved to `archived`:
            # its status is still its own, so unarchiving clears the flag only.
            new_status = _prior_status(t) if t.status == ARCHIVED else t.status
            update = MacfTaskUpdate(breadcrumb=breadcrumb, agent="PA", type=UNARCHIVE_UPDATE,
                                    description=f"Unarchived, back to {new_status}")
        wrote = _write(t, new_status, update, archive, call_stamp, reader.session_uuid)

        # Read back: the report counts what is on disk, never what was attempted.
        back = TaskReader(session_uuid).read_task(t.id)
        if not wrote:
            report.failed.append({"id": t.id, "why": "the task file could not be written"})
        elif back is None:
            report.failed.append({"id": t.id, "why": "the task file could not be read back"})
        elif is_archived(back) != archive or back.status != new_status:
            report.failed.append({"id": t.id, "why": f"read back as status {back.status!r}"})
        else:
            report.changed.append(t.id)
    return report


def archive_tasks(task_ids: List[str], reason: str, *, cascade: bool = True, dry_run: bool = False,
                  session_uuid: Optional[str] = None) -> ArchiveReport:
    """Archive each task (and, with cascade, its descendants); verify; record; descope."""
    from ..agent_events_log import append_event
    from ..utils.breadcrumbs import get_breadcrumb
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a reason is required: archiving puts work down, and the record says why")
    breadcrumb = get_breadcrumb()
    report = _apply(task_ids, archive=True, reason=reason, cascade=cascade, dry_run=dry_run,
                    breadcrumb=breadcrumb, session_uuid=session_uuid)
    if dry_run or not report.changed:
        return report

    # A task that is put down has nothing left for the sprint gate to wait on.
    from .scope import get_scope_state, remove_from_scope
    scoped = [tid for tid in report.changed if tid in get_scope_state()]
    if scoped:
        result = remove_from_scope(scoped)
        report.descoped = list(result.get("removed_ids", []))
        if not result.get("success"):
            print(f"⚠️ MACF: archived tasks could not be removed from scope (they stay scoped): "
                  f"{', '.join('#' + t for t in scoped)}", file=sys.stderr)

    append_event("task_archived", {
        "task_ids": report.changed, "roots": [str(t).lstrip("#") for t in task_ids],
        "reason": reason, "cascade": cascade, "breadcrumb": breadcrumb,
    })
    return report


def unarchive_tasks(task_ids: List[str], *, cascade: bool = True,
                    session_uuid: Optional[str] = None) -> ArchiveReport:
    """Put each archived task (and, with cascade, its archived descendants) back where it was."""
    from ..agent_events_log import append_event
    from ..utils.breadcrumbs import get_breadcrumb
    breadcrumb = get_breadcrumb()
    report = _apply(task_ids, archive=False, reason="", cascade=cascade, dry_run=False,
                    breadcrumb=breadcrumb, session_uuid=session_uuid)
    if report.changed:
        append_event("task_unarchived", {
            "task_ids": report.changed, "roots": [str(t).lstrip("#") for t in task_ids],
            "cascade": cascade, "breadcrumb": breadcrumb,
        })
    return report


def tracked_by_duties(task_ids: List[str]) -> Dict[str, List[str]]:
    """Task id -> titles of open role duties that track it, so their owner hears of it."""
    wanted = {str(t) for t in task_ids}
    found: Dict[str, List[str]] = {}
    try:
        from ..roles.store import RoleStore
        for duty, _path in RoleStore().all_duties():
            if getattr(duty, "state", None) in ("done", "deferred"):
                continue
            for tid in getattr(duty, "tracks", None) or []:
                if str(tid) in wanted:
                    found.setdefault(str(tid), []).append(duty.title)
    except (OSError, ValueError, ImportError) as e:
        print(f"⚠️ MACF: role duties not checked for tracked tasks (non-blocking): {e}", file=sys.stderr)
    return found
