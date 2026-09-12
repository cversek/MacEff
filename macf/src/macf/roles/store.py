"""The roles store: ``agent/public/roles/<date>_<id>_<Title>/``.

One folder per role holding ``data.json``, ``charter.md`` and one
``DUTY_<id>_<Title>.json`` per duty. Nothing here touches the task store
except to READ it: a duty's ``tracks`` and ``evidence`` are checked against
tasks that exist, and the role view resolves their status live.

Every mutation writes atomically (``write_json_safely``), appends a breadcrumbed
update to the record, and emits an event, the way the task system does. No
ordering is stored anywhere; the tiers compute it at render time.
"""
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from ..agent_events_log import append_event
from ..lifecycle import IllegalTransition, check_transition
from ..utils.breadcrumbs import get_breadcrumb
from ..utils.json_io import write_json_safely
from .models import (DUTY_MACHINE, ROLE_MACHINE, Duty, Role, Update, dump)

ROLES_DIR_ENV = "MACF_ROLES_DIR"
SCAFFOLD_BOUNDARIES = "What this role may do, and what it must not."
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CHARTER_SCAFFOLD = """# {title}

## Purpose

## Boundaries

What this role may do, and what it must not.

## Depends on

Spokes, corpora, people, handbooks.

## Wiki-Links

"""


class RoleError(Exception):
    """A refusal. The message is printed on one ❌ line; exit 1."""


def roles_dir() -> Path:
    """``MACF_ROLES_DIR`` if set (tests, isolation), else the agent home's store."""
    env = os.environ.get(ROLES_DIR_ENV)
    if env:
        return Path(env)
    from ..utils.paths import find_agent_home
    return find_agent_home() / "agent" / "public" / "roles"


def slug(title: str) -> str:
    """``Title_No_Spaces``: keep case and digits, one underscore between words."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", title.strip()).strip("_")
    return s[:60] or "Untitled"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _update(description: str, kind: str = "note", done_on: Optional[date] = None,
            agent: str = "PA") -> Update:
    return Update(breadcrumb=get_breadcrumb(), description=description, at=now_iso(),
                  agent=agent, kind=kind, done_on=done_on)


class RoleStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else roles_dir()

    # ---- reading -----------------------------------------------------------

    def role_dirs(self) -> List[Path]:
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir() and (p / "data.json").exists())

    def load_role(self, folder: Path) -> Role:
        import json
        return Role.model_validate(json.loads((folder / "data.json").read_text()))

    def roles(self) -> List[Tuple[Role, Path]]:
        return [(self.load_role(d), d) for d in self.role_dirs()]

    def duty_files(self, folder: Path) -> List[Path]:
        return sorted(folder.glob("DUTY_*.json"))

    def load_duty(self, path: Path) -> Duty:
        import json
        return Duty.model_validate(json.loads(path.read_text()))

    def duties(self, folder: Path) -> List[Tuple[Duty, Path]]:
        return [(self.load_duty(p), p) for p in self.duty_files(folder)]

    def all_duties(self) -> List[Tuple[Duty, Path]]:
        out: List[Tuple[Duty, Path]] = []
        for d in self.role_dirs():
            out.extend(self.duties(d))
        return out

    def all_ids(self) -> set:
        ids = set()
        for role, folder in self.roles():
            ids.add(role.id)
            for duty, _ in self.duties(folder):
                ids.add(duty.id)
        return ids

    def new_id(self) -> str:
        """Six hex characters, collision-checked within this store."""
        taken = self.all_ids()
        for _ in range(64):
            cand = uuid.uuid4().hex[:6]
            if cand not in taken:
                return cand
        raise RoleError("could not allocate a unique id after 64 draws")

    def find_role(self, ref: str) -> Tuple[Role, Path]:
        """By id, or by an unambiguous case-insensitive title prefix."""
        ref = (ref or "").strip()
        if not ref:
            raise RoleError("a role id or title prefix is required")
        pairs = self.roles()
        by_id = [p for p in pairs if p[0].id == ref.lower()]
        if by_id:
            return by_id[0]
        hits = [p for p in pairs if p[0].title.lower().startswith(ref.lower())]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise RoleError(f"no role matches {ref!r} (run: macf_tools role list)")
        names = ", ".join(f"{r.id} {r.title}" for r, _ in hits)
        raise RoleError(f"{ref!r} is ambiguous: {names}")

    def find_duty(self, ref: str, role: Optional[Role] = None) -> Tuple[Duty, Path]:
        ref = (ref or "").strip()
        if not ref:
            raise RoleError("a duty id or title prefix is required")
        pool = self.all_duties() if role is None else self.duties(self.folder_of(role))
        by_id = [p for p in pool if p[0].id == ref.lower()]
        if by_id:
            return by_id[0]
        hits = [p for p in pool if p[0].title.lower().startswith(ref.lower())]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise RoleError(f"no duty matches {ref!r}")
        names = ", ".join(f"{d.id} {d.title}" for d, _ in hits)
        raise RoleError(f"{ref!r} is ambiguous: {names}")

    def folder_of(self, role: Role) -> Path:
        for r, d in self.roles():
            if r.id == role.id:
                return d
        raise RoleError(f"role {role.id} has no folder in {self.root}")

    def role_of(self, duty: Duty) -> Tuple[Role, Path]:
        for r, d in self.roles():
            if r.id == duty.role_id:
                return r, d
        raise RoleError(f"duty {duty.id} names parent {duty.role_id}, which does not exist")

    # ---- writing -----------------------------------------------------------

    def save_role(self, role: Role, folder: Path) -> None:
        if not write_json_safely(folder / "data.json", dump(role)):
            raise RoleError(f"could not write {folder / 'data.json'}")

    def duty_path(self, folder: Path, duty: Duty) -> Path:
        existing = [p for p in self.duty_files(folder) if p.name.startswith(f"DUTY_{duty.id}_")]
        return existing[0] if existing else folder / f"DUTY_{duty.id}_{slug(duty.title)}.json"

    def save_duty(self, duty: Duty, folder: Path) -> Path:
        path = self.duty_path(folder, duty)
        if not write_json_safely(path, dump(duty)):
            raise RoleError(f"could not write {path}")
        return path

    def create_role(self, title: str, *, icon: str = "🎭", tenure_start: Optional[date] = None,
                    expires: Optional[date] = None, review_by: Optional[date] = None,
                    review_horizon: Optional[str] = None, resources: Iterable[str] = (),
                    charter_seed: str = "", wiki_links: Iterable[str] = (),
                    why: str = "") -> Tuple[Role, Path]:
        tenure_start = tenure_start or date.today()
        rid = self.new_id()
        role = Role(id=rid, title=title, icon=icon, tenure_start=tenure_start, expires=expires,
                    review_by=review_by, review_horizon=review_horizon,
                    resources=list(resources), wiki_links=list(wiki_links))
        folder = self.root / f"{tenure_start.isoformat()}_{rid}_{slug(role.title)}"
        if folder.exists():
            raise RoleError(f"{folder} already exists")
        folder.mkdir(parents=True)
        charter = CHARTER_SCAFFOLD.format(title=role.title)
        if charter_seed:
            charter = charter.replace("## Purpose\n\n", f"## Purpose\n\n{charter_seed.strip()}\n\n", 1)
        if role.wiki_links:
            # The charter is the role's knowledge-web node; the links given at
            # assignment go into it now rather than waiting for a hand edit.
            charter += " ".join(f"[[{w}]]" for w in role.wiki_links) + "\n"
        (folder / "charter.md").write_text(charter)
        role.updates.append(_update(why or "Role assigned", kind="assign"))
        self.save_role(role, folder)
        append_event("role_created", {"role_id": rid, "title": role.title, "icon": icon,
                                      "tenure_start": tenure_start.isoformat(),
                                      "expires": expires.isoformat() if expires else None,
                                      "review_by": review_by.isoformat() if review_by else None})
        return role, folder

    def add_duty(self, role: Role, folder: Path, title: str, *, body: str = "",
                 importance: str = "normal", due: Optional[datetime] = None,
                 horizon: Optional[str] = None, why: str = "", cadence: Optional[str] = None,
                 depends_on: Iterable[str] = (), tracks: Iterable[str] = (),
                 wiki_links: Iterable[str] = (), meta: bool = False) -> Tuple[Duty, Path]:
        if role.state in ("expired", "retired"):
            raise RoleError(f"role {role.id} is {role.state}; a duty cannot be added to it")
        # Dependencies may cross roles (BLOCKING counts dependents of any
        # role); each must exist. A duty is never a parent, so this is the
        # only relation between duties the store records.
        deps = [self.find_duty(d.strip())[0].id for d in depends_on if d.strip()]
        tr = self._check_tracks(tracks)
        if (due is not None or cadence is not None) and horizon is None:
            raise RoleError("a duty with --due or --cadence needs --horizon, reasoned from the duty "
                            "(roles policy: reasoning a horizon); record the reasoning with --why")
        if horizon is not None and not why:
            raise RoleError("--horizon needs --why: the reasoning is the duty's first note "
                            "(roles policy: reasoning a horizon)")
        duty = Duty(id=self.new_id(), role_id=role.id, title=title, body=body, importance=importance,
                    meta=meta, due=due, horizon=horizon, cadence=cadence, depends_on=deps, tracks=tr,
                    wiki_links=list(wiki_links), state="active" if tr else "pending")
        first = f"Declared. Horizon {horizon}: {why}" if horizon else (why or "Declared")
        duty.updates.append(_update(first, kind="declare"))
        path = self.save_duty(duty, folder)
        append_event("duty_added", {"duty_id": duty.id, "role_id": role.id, "title": duty.title,
                                    "due": due.isoformat() if due else None, "horizon": horizon,
                                    "cadence": cadence, "importance": importance})
        return duty, path

    # ---- servicing ---------------------------------------------------------

    def note_role(self, role: Role, folder: Path, text: str, kind: str = "note") -> Role:
        role.updates.append(_update(text, kind=kind))
        self.save_role(role, folder)
        append_event("role_serviced", {"role_id": role.id, "kind": kind})
        return role

    def note_duty(self, duty: Duty, folder: Path, text: str, kind: str = "note",
                  done_on: Optional[date] = None) -> Duty:
        duty.updates.append(_update(text, kind=kind, done_on=done_on))
        self.save_duty(duty, folder)
        append_event("duty_serviced", {"duty_id": duty.id, "role_id": duty.role_id, "kind": kind,
                                       "done_on": done_on.isoformat() if done_on else None})
        return duty

    def advance_role(self, role: Role, folder: Path, new_state: str, reason: str = "") -> Role:
        try:
            check_transition(ROLE_MACHINE, role.state, new_state)
        except (IllegalTransition, ValueError) as e:
            raise RoleError(str(e)) from e
        old = role.state
        role.state = new_state
        role.updates.append(_update(f"{old} → {new_state}" + (f": {reason}" if reason else ""), kind=new_state))
        self.save_role(role, folder)
        append_event("role_lifecycle_advanced", {"role_id": role.id, "from_state": old,
                                                 "to_state": new_state, "reason": reason})
        return role

    def advance_duty(self, duty: Duty, folder: Path, new_state: str, reason: str = "",
                     evidence: Iterable[str] = ()) -> Duty:
        try:
            check_transition(DUTY_MACHINE, duty.state, new_state)
        except (IllegalTransition, ValueError) as e:
            raise RoleError(str(e)) from e
        ev = list(evidence)
        if new_state == "done":
            if not ev:
                raise RoleError("duty done needs at least one --evidence pointer: a declaration is "
                                "satisfied only by an implementation on record (roles policy: done "
                                "requires evidence); an honest 'no longer needed' is defer --reason")
            self._check_evidence(ev)
            duty.evidence = sorted(set(duty.evidence) | set(ev))
        if new_state == "deferred" and not reason:
            raise RoleError("duty defer needs --reason")
        old = duty.state
        duty.state = new_state
        text = f"{old} → {new_state}" + (f": {reason}" if reason else "")
        if ev:
            text += f" [evidence: {', '.join(ev)}]"
        duty.updates.append(_update(text, kind=new_state))
        self.save_duty(duty, folder)
        append_event("duty_lifecycle_advanced", {"duty_id": duty.id, "role_id": duty.role_id,
                                                 "from_state": old, "to_state": new_state,
                                                 "reason": reason, "evidence": ev})
        return duty

    def engaged(self) -> List[Tuple[Duty, Path]]:
        """Every active duty across the store: the duties attention is on."""
        return [(d, p) for d, p in self.all_duties() if d.state == "active"]

    def disengage(self, duty: Duty, folder: Path, reason: str = "") -> Duty:
        """active -> pending: attention moved elsewhere. Not a service: putting a
        duty down does nothing for it, so the gate's bound does not move."""
        if duty.state != "active":
            return duty
        duty.state = "pending"
        duty.updates.append(_update("Disengaged" + (f": {reason}" if reason else ""), kind="disengage"))
        self.save_duty(duty, folder)
        append_event("duty_disengaged", {"duty_id": duty.id, "role_id": duty.role_id, "reason": reason})
        return duty

    def check_engageable(self, duty: Duty, folder: Path) -> None:
        """The refusals engage applies before writing anything."""
        if duty.state == "done":
            raise RoleError(f"duty {duty.id} is done; reactivate is not a thing a done duty does (declare a new one)")
        # A role whose charter still carries the scaffold's Boundaries line has
        # never said what it may do alone and what needs the operator; working
        # its duties is how an agent over-reaches on the operator's behalf.
        # The one exception is the meta duty that writes those Boundaries: the
        # scaffold cannot be replaced any other way.
        charter = folder / "charter.md"
        if not duty.meta and charter.exists() and SCAFFOLD_BOUNDARIES in charter.read_text():
            raise RoleError(f"the charter's Boundaries are still the scaffold ({charter}); write what this role "
                            "may do alone and what needs the operator's direction before engaging a duty "
                            "(roles policy: the charter; declare the charter as a --meta duty and engage that)")

    def engage(self, duty: Duty, folder: Path, note: str = "", task_ids: Iterable[str] = (),
               exclusive: bool = True) -> Duty:
        """Attention is on this duty now: the duty's `task start`.

        pending/deferred -> active with an 'engage' update (a service, so the
        gate's bound clears and the stanza pointer moves here). Engagement is
        exclusive by default: every other active duty in the store is
        disengaged first, because attention moved. A deliberate parallel
        engagement passes exclusive=False (see engage_set). Focusing the
        parent role is the caller's step, because focus is an event, not a
        record. Tracking tasks may be attached in the same breath.
        """
        self.check_engageable(duty, folder)
        if exclusive:
            for other, opath in self.engaged():
                if other.id != duty.id:
                    self.disengage(other, opath.parent, reason=f"engaged {duty.id} instead")
        ids = self._check_tracks(task_ids)
        if ids:
            duty.tracks = sorted(set(duty.tracks) | set(ids), key=lambda s: (len(s), s))
        old = duty.state
        duty.state = "active"
        text = "Engaged" + (f": {note}" if note else "") + (f" [tracks {', '.join('#' + i for i in ids)}]" if ids else "")
        duty.updates.append(_update(text, kind="engage"))
        self.save_duty(duty, folder)
        append_event("duty_serviced", {"duty_id": duty.id, "role_id": duty.role_id, "kind": "engage",
                                       "from_state": old, "tracks": ids})
        return duty

    def engage_set(self, pairs: List[Tuple[Duty, Path]], note: str = "", task_ids: Iterable[str] = ()) -> List[Duty]:
        """One command, several duties: the deliberate parallel engagement.
        Everything outside the set is disengaged; the set is engaged together."""
        keep = {d.id for d, _ in pairs}
        for d, p in pairs:
            self.check_engageable(d, p.parent)
        for other, opath in self.engaged():
            if other.id not in keep:
                self.disengage(other, opath.parent, reason="engaged " + ", ".join(sorted(keep)) + " instead")
        return [self.engage(d, p.parent, note, task_ids, exclusive=False) for d, p in pairs]

    def link(self, duty: Duty, folder: Path, task_ids: Iterable[str]) -> Duty:
        ids = self._check_tracks(task_ids)
        duty.tracks = sorted(set(duty.tracks) | set(ids), key=lambda s: (len(s), s))
        if duty.state == "pending":
            duty.state = "active"
        duty.updates.append(_update(f"tracks {', '.join('#' + i for i in ids)}", kind="link"))
        self.save_duty(duty, folder)
        append_event("duty_serviced", {"duty_id": duty.id, "role_id": duty.role_id, "kind": "link",
                                       "tracks": ids})
        return duty

    def unlink(self, duty: Duty, folder: Path, task_ids: Iterable[str]) -> Duty:
        ids = [str(i).lstrip("#") for i in task_ids]
        missing = [i for i in ids if i not in duty.tracks]
        if missing:
            raise RoleError(f"duty {duty.id} does not track {', '.join('#' + i for i in missing)}")
        duty.tracks = [t for t in duty.tracks if t not in ids]
        duty.updates.append(_update(f"no longer tracks {', '.join('#' + i for i in ids)}", kind="unlink"))
        self.save_duty(duty, folder)
        append_event("duty_serviced", {"duty_id": duty.id, "role_id": duty.role_id, "kind": "unlink",
                                       "tracks": ids})
        return duty

    # ---- migration from the task store -------------------------------------

    @staticmethod
    def task_title(task) -> str:
        """A task subject with its id, type markers and ROLE:/DUTY: prefixes removed."""
        t = _ANSI_RE.sub("", task.subject).strip()
        t = re.sub(r"^#\d+\s*", "", t)
        t = re.sub(r"^\[\^#\d+\]\s*", "", t)
        t = re.sub(r"^(?:[^\w\s]\s*)+", "", t)            # leading emoji markers
        t = re.sub(r"^(?:ROLE|DUTY)\s*:\s*", "", t, flags=re.I)
        t = re.sub(r"^(?:[^\w\s]\s*)+", "", t)
        return t.strip() or task.subject.strip()

    @staticmethod
    def task_updates(task) -> List[Update]:
        """A task's notes carried over as updates, keeping their breadcrumbs and
        stamped from the breadcrumb's own timestamp so the record's order holds."""
        out: List[Update] = []
        if not task.mtmd:
            return out
        for u in task.mtmd.updates:
            m = re.search(r"/t_(\d{10})", u.breadcrumb or "")
            at = datetime.fromtimestamp(int(m.group(1))).replace(microsecond=0).isoformat() if m else now_iso()
            out.append(Update(breadcrumb=u.breadcrumb or "migrated", description=u.description or "",
                              at=at, agent=u.agent or "PA", kind="migrated"))
        return out

    def create_role_from_task(self, task_id: str, **kw) -> Tuple[Role, Path]:
        task = self._task(str(task_id).lstrip("#"))
        if task is None:
            raise RoleError(f"task #{task_id} does not exist")
        title = kw.pop("title", None) or self.task_title(task)
        why = kw.pop("why", "") or f"Migrated from task #{task.id}"
        role, folder = self.create_role(title, why=why, **kw)
        carried = self.task_updates(task)
        if carried:
            role.updates = carried + role.updates
            self.save_role(role, folder)
        return role, folder

    def add_duty_from_task(self, role: Role, folder: Path, task_id: str, **kw) -> Tuple[Duty, Path]:
        task = self._task(str(task_id).lstrip("#"))
        if task is None:
            raise RoleError(f"task #{task_id} does not exist")
        title = kw.pop("title", None) or self.task_title(task)
        why = kw.pop("why", "")
        if kw.get("horizon") and not why:
            why = f"migrated from task #{task.id}; horizon reasoned at migration"
        duty, path = self.add_duty(role, folder, title, why=why, **kw)
        carried = self.task_updates(task)
        if carried:
            duty.updates = carried + duty.updates
            if task.status == "in_progress" and duty.state == "pending":
                duty.state = "active"
            self.save_duty(duty, folder)
        return duty, path

    # ---- the task store, read only -----------------------------------------

    @staticmethod
    def _task(task_id: str):
        from ..task import TaskReader
        return TaskReader().read_task(task_id)

    def _check_tracks(self, task_ids: Iterable[str]) -> List[str]:
        ids = [str(i).strip().lstrip("#") for i in task_ids if str(i).strip()]
        for tid in ids:
            if self._task(tid) is None:
                raise RoleError(f"--tracks names task #{tid}, which does not exist")
        return ids

    def _check_evidence(self, items: Iterable[str]) -> None:
        """A task id must exist and be completed; a path must exist."""
        from ..utils.paths import find_agent_home
        home = find_agent_home()
        for item in items:
            ref = item.strip()
            if re.fullmatch(r"#?\d+", ref):
                task = self._task(ref.lstrip("#"))
                if task is None:
                    raise RoleError(f"--evidence names task #{ref.lstrip('#')}, which does not exist")
                if task.status != "completed":
                    raise RoleError(f"--evidence names task #{task.id}, which is {task.status}, not completed; "
                                    "a duty is satisfied by an implementation on record")
                continue
            p = Path(ref)
            if not (p.exists() or (home / ref).exists()):
                raise RoleError(f"--evidence path {ref!r} does not exist (absolute, or relative to the agent home)")

    def live_tracks(self, duty: Duty) -> List[Tuple[str, Optional[str], Optional[str]]]:
        """(task id, status, subject) for each tracked task, status None if gone.

        Subjects in the store can carry terminal colour codes from the tree
        renderer; strip them so the role view prints plain text.
        """
        out = []
        for tid in duty.tracks:
            t = self._task(tid)
            subject = _ANSI_RE.sub("", t.subject).strip() if t else None
            out.append((tid, t.status if t else None, subject))
        return out
