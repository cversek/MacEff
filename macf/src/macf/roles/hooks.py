"""What the hooks ask the roles store: nag, gate, prompt line, banner marker.

Everything here is derived from the duty records, the events log and *now*;
no sidecar state. The three nag properties from the mode-system policy hold:
computed from observed state (tier entry from due and horizon, tool calls
from events), naming the remedy (the exact command), cleared by the action
(a focus change, a service).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ..agent_events_log import read_events
from .focus import EVENT as FOCUS_EVENT
from .focus import current_focus
from .location import roles_dir
from .priority import DUE_SOON, OVERDUE, TIER_NAMES, Placement, duty_mark, now, rank, review_mark

if TYPE_CHECKING:
    from .models import Duty, Role
    from .store import RoleStore

# PreToolUse calls the nag, the banner marker and the store's mtime on every tool call.
# Building the roles models costs about 55 ms a call, more than the rest of the roles path,
# so those three reach the store and its models only when they must (#460).
NAG_CACHE_TTL_S = 60


def _store(store: Optional[RoleStore]) -> RoleStore:
    if store is not None:
        return store
    from .store import RoleStore
    return RoleStore()

TOUCH_NAG_BASE_DEFAULT = 20          # the touch nag's constant; MACF_TOUCH_NAG_BASE overrides both


def _base() -> int:
    try:
        return int(os.environ.get("MACF_TOUCH_NAG_BASE", TOUCH_NAG_BASE_DEFAULT))
    except ValueError:
        return TOUCH_NAG_BASE_DEFAULT


def _epoch(dt: datetime) -> float:
    return dt.timestamp()


def _serviced_since(duty: Duty, since: datetime) -> bool:
    """Any breadcrumbed update at or after *since* counts as a service --
    except the declaration itself (declaring a duty that is already due-now
    does not service it), a disengagement (putting a duty down does nothing
    for it) and a correction (an edit with no reason, such as a typo fix)."""
    for u in duty.updates:
        if u.kind in ("declare", "disengage", "correction"):
            continue
        try:
            if datetime.fromisoformat(u.at) >= since:
                return True
        except ValueError:
            continue
    return False


def _calls_since(entered_epoch: float, role_id: str) -> Tuple[int, bool]:
    """(tool calls since tier entry, acknowledged) from this cycle's events.

    Scans newest-first and stops at the first focus change TO the role after
    entry (acknowledged) or at the entry time. Cycle-scoped by default, so the
    scan is bounded by construction; an entry before this cycle counts this
    cycle's calls, which is the honest number for 'how long has this been
    ignored since I could have seen it'.
    """
    n = 0
    for ev in read_events(reverse=True):
        ts = ev.get("timestamp", 0)
        if ts < entered_epoch:
            break
        kind = ev.get("event")
        if kind == FOCUS_EVENT and ev.get("data", {}).get("role_id") == role_id:
            return n, True
        if kind == "tool_call_started":
            n += 1
    return n, False


def _fires(n: int, tier: int, base: int) -> Optional[str]:
    """The schedule, in units of the touch-nag base: DUE_SOON at B, 2B, 4B, ...;
    OVERDUE at every multiple of B with the tone ramp. Returns the tone glyph."""
    if base <= 0 or n <= 0:
        return None
    if tier == OVERDUE:
        if n % base == 0:
            k = n // base
            return "🌱" if k == 1 else ("🌿" if k == 2 else "🌳")
        return None
    k = n / base
    if k >= 1 and (k == int(k)) and (int(k) & (int(k) - 1)) == 0:   # 1, 2, 4, 8 ...
        p = int(k)
        return "🌱" if p == 1 else ("🌿" if p == 2 else "🌳")
    return None


def _due_now(store: RoleStore, at: datetime) -> List[Dict[str, Any]]:
    """Every active role's due-now duties, in the store's order and each role's rank: what
    the nag chooses from. Builds the models; the cache below spares most calls this."""
    out = []
    for role, folder in store.roles():
        if role.state != "active":
            continue
        duties = [d for d, _ in store.duties(folder)]
        for p in rank(duties, at, role.expires):
            if p.tier in (OVERDUE, DUE_SOON) and p.entered is not None:
                out.append({"role_id": role.id, "icon": role.icon, "title": role.title,
                            "duty": p.duty.title, "tier": p.tier, "entered": _epoch(p.entered),
                            "mark": duty_mark(p, at)})
    return out


def _nag_cache_path(root: Path) -> Path:
    """In the agent's own home, which only the agent writes. Not a shared temp
    directory: the nag prints what the cache holds into the agent's context, so a file
    another account could plant there would read as the agent's own duties."""
    from ..utils.paths import find_agent_home
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return Path(find_agent_home()) / ".maceff" / "cache" / f"roles_nag_{key}.json"


def _due_now_cached(at: datetime) -> List[Dict[str, Any]]:
    """``_due_now`` for the hook's own call, reused while the store is unchanged and for
    at most NAG_CACHE_TTL_S. Any write to the store rebuilds it at once; a duty crossing a
    tier boundary with no write shows up within the TTL, and its mark is at most that
    stale. A cache that can't be read or written only costs the rebuild. It lives in
    the agent home (``_nag_cache_path``)."""
    root = roles_dir()
    mtime = roles_store_mtime(root=root)
    path = _nag_cache_path(root)
    try:
        cached = json.loads(path.read_text())
        if (cached.get("root") == str(root) and cached.get("mtime") == mtime
                and 0 <= at.timestamp() - cached.get("at", 0) < NAG_CACHE_TTL_S):
            return cached["due_now"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    due = _due_now(_store(None), at)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}")
        tmp.write_text(json.dumps({"root": str(root), "mtime": mtime, "at": at.timestamp(), "due_now": due}))
        os.replace(tmp, path)
    except OSError as e:
        print(f"⚠️ MACF: roles nag cache not written ({e})", file=sys.stderr)
    return due


def conscientiousness_nag(store: Optional[RoleStore] = None, at: Optional[datetime] = None) -> str:
    """One line when a duty of an UNFOCUSED role is due-now and unacknowledged.

    Called with neither argument, as the hook calls it, it reads through the cache; the
    focus and the tool-call counts are always read live."""
    base = _base()
    if base <= 0:
        return ""
    due = _due_now_cached(now()) if store is None and at is None else _due_now(_store(store), at or now())
    focused = current_focus()
    for d in due:
        if d["role_id"] == focused:
            continue
        n, acked = _calls_since(d["entered"], d["role_id"])
        if acked:
            continue
        tone = _fires(n, d["tier"], base)
        if tone:
            return (f"{tone} Duty {TIER_NAMES[d['tier']]} in an unfocused role: {d['icon']} {d['title']} -- "
                    f"\"{d['duty']}\" ({d['mark']}). Focus it for the full list:  macf_tools role focus R{d['role_id']}")
    return ""


def due_now_unserviced(role: Role, duties: List[Duty], at: datetime) -> List[Placement]:
    """Duties at DUE_SOON/today/OVERDUE with no service since they entered that tier."""
    out = []
    for p in rank(duties, at, role.expires):
        if p.tier in (OVERDUE, DUE_SOON) and p.entered is not None and not _serviced_since(p.duty, p.entered):
            out.append(p)
    return out


def priority_list(role: Role, placed: List[Placement], at: datetime) -> str:
    lines = [f"🎯 {role.icon} {role.title} -- duty priorities:"]
    for p in placed:
        mark = duty_mark(p, at)
        lines.append(f"  {p.tier_name:<9} {p.duty.title}" + (f"  {mark}" if mark else ""))
    return "\n".join(lines)


def focus_gate(auto_mode: bool, store: Optional[RoleStore] = None, at: Optional[datetime] = None) -> Dict[str, Any]:
    """What the Stop hook injects for the focused role, and whether it blocks.

    Returns {"text": str, "role": the focused role's id, "block": bool,
    "unserviced": [duty ids]}. The stop is blocked only in AUTO_MODE and only
    while due-now duties are unserviced. Undated duties never block.
    """
    store = _store(store)
    from .store import RoleError
    at = at or now()
    focused = current_focus()
    if not focused:
        return {"text": "", "role": "", "block": False, "unserviced": []}
    try:
        role, folder = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return {"text": "", "role": "", "block": False, "unserviced": []}
    duties = [d for d, _ in store.duties(folder)]
    placed = rank(duties, at, role.expires)
    text = priority_list(role, placed, at)
    pending = due_now_unserviced(role, duties, at)
    if not pending:
        return {"text": text, "role": role.id, "block": False, "unserviced": []}
    names = ", ".join(f"\"{p.duty.title}\"" for p in pending)
    text += (f"\n\n🛡️ Due-now duties unserviced: {names}.\n"
             f"Service each (macf_tools role duty note|done|defer <id>), or put the role down honestly: "
             f"macf_tools role unfocus (recorded with what was due).")
    return {"text": text, "role": role.id, "block": bool(auto_mode), "unserviced": [p.duty.id for p in pending]}


def focus_text(focus: Dict[str, Any], session_id: str, reader: str) -> str:
    """The focus gate's text as one reader should get it: whole the first time,
    then only its lines that moved, and nothing at all when none did.

    ``reader`` names whose copy this is (the Stop hook sends ``"agent"`` for a
    block reason). Each reader is compared with its own last copy, because the
    agent sees a Stop only when it is blocked: one copy for every reader would
    tell the agent "unchanged" about lines it was never sent. The whole text
    goes out on a reader's first Stop in a session or cycle and every time when
    ``hooks.output`` is ``full``, and never again on a timer. Role lines that
    did not move are not repeated, not even as a heading, since restating them
    is what teaches a reader to skip the one that moved.
    """
    if not focus.get("text"):
        return ""
    from ..hooks.emission import emit
    header = focus["text"].splitlines()[0].rstrip(":")
    try:
        em = emit(f"stop_duties:{focus['role']}:{reader}", session_id, focus["text"], header, (),
                  periodic_full=False)
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: role lines sent whole, their last copy could not be compared: {e}", file=sys.stderr)
        return focus["text"]
    if not em.full and not em.changed:
        return ""
    return em.operator if reader == "operator" else em.agent


def prompt_line(store: Optional[RoleStore] = None, at: Optional[datetime] = None) -> str:
    """One line for UserPromptSubmit when the focused role has anything due
    today/overdue, or a review inside its horizon. Empty otherwise."""
    store = _store(store)
    from .store import RoleError
    at = at or now()
    focused = current_focus()
    if not focused:
        return ""
    try:
        role, folder = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return ""
    duties = [d for d, _ in store.duties(folder)]
    hot = [p for p in rank(duties, at, role.expires)
           if p.tier == OVERDUE or (p.tier == DUE_SOON and p.occurrence and p.occurrence.date() == at.date())]
    rm = review_mark(role, at)
    if not hot and not rm:
        return ""
    bits = [f"{p.duty.title} ({duty_mark(p, at)})" for p in hot]
    if rm:
        bits.append(f"review {rm}")
    return f"🎯 {role.icon} {role.title}: " + "; ".join(bits)


def focus_marker(store: Optional[RoleStore] = None) -> str:
    """The focused role's icon, for the banner's work-mode slot. Read from the role's own
    record without building the model, so an edited icon shows at once."""
    focused = current_focus()
    if not focused:
        return ""
    root = store.root if store is not None else roles_dir()
    for data in sorted(root.glob("*/data.json")) if root.exists() else []:
        try:
            role = json.loads(data.read_text())
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: {data} unreadable ({e}); skipped for the banner marker", file=sys.stderr)
            continue
        if role.get("id") == focused:
            return role.get("icon") or ""
    print(f"⚠️ MACF: focused role {focused} not found; no banner marker", file=sys.stderr)
    return ""


def roles_store_mtime(store: Optional[RoleStore] = None, root: Optional[Path] = None) -> float:
    """Newest write in the roles store, so the touch nag counts duty touches."""
    root = root or (store.root if store is not None else roles_dir())
    if not root.exists():
        return 0.0
    return max((p.stat().st_mtime for p in root.rglob("*.json")), default=0.0)


def charter_context(store: Optional[RoleStore] = None) -> str:
    """The focused role's charter for SessionStart: the Boundaries must be in
    context whenever the agent stands in a role, and a new session starts
    with none of what the focus command printed. Empty when nothing is focused."""
    focused = current_focus()
    if not focused:
        return ""
    store = _store(store)
    from .store import RoleError
    try:
        role, folder = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return ""
    charter = folder / "charter.md"
    if not charter.exists():
        return ""
    engaged = [d.title for d, _ in store.engaged() if d.role_id == role.id]
    from .focus import note_charter_shown
    note_charter_shown(role.id, charter.stat().st_mtime)
    head = f"🎯 You hold the role {role.icon} {role.title} (R{role.id}). Its charter follows; the Boundaries bind every act taken in it."
    if engaged:
        head += " Engaged duties: " + "; ".join(engaged) + "."
    return head + "\n\n" + charter.read_text().rstrip()
