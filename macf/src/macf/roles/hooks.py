"""What the hooks ask the roles store: nag, gate, prompt line, banner marker.

Everything here is derived from the duty records, the events log and *now*;
no sidecar state. The three nag properties from the mode-system policy hold:
computed from observed state (tier entry from due and horizon, tool calls
from events), naming the remedy (the exact command), cleared by the action
(a focus change, a service).
"""
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..agent_events_log import read_events
from .focus import EVENT as FOCUS_EVENT
from .focus import current_focus
from .models import Duty, Role
from .priority import DUE_SOON, OVERDUE, Placement, duty_mark, now, rank, review_mark
from .store import RoleError, RoleStore

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
    does not service it) and a disengagement (putting a duty down does nothing
    for it)."""
    for u in duty.updates:
        if u.kind in ("declare", "disengage"):
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


def conscientiousness_nag(store: Optional[RoleStore] = None, at: Optional[datetime] = None) -> str:
    """One line when a duty of an UNFOCUSED role is due-now and unacknowledged."""
    base = _base()
    if base <= 0:
        return ""
    store = store or RoleStore()
    at = at or now()
    focused = current_focus()
    for role, folder in store.roles():
        if role.state != "active" or role.id == focused:
            continue
        duties = [d for d, _ in store.duties(folder)]
        for p in rank(duties, at, role.expires):
            if p.tier not in (OVERDUE, DUE_SOON) or p.entered is None:
                continue
            n, acked = _calls_since(_epoch(p.entered), role.id)
            if acked:
                continue
            tone = _fires(n, p.tier, base)
            if tone:
                mark = duty_mark(p, at)
                return (f"{tone} Duty {p.tier_name} in an unfocused role: {role.icon} {role.title} -- "
                        f"\"{p.duty.title}\" ({mark}). Focus it for the full list:  macf_tools role focus R{role.id}")
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

    Returns {"text": str, "block": bool, "unserviced": [duty ids]}. The list is
    injected on every Stop; the stop is blocked only in AUTO_MODE and only while
    due-now duties are unserviced. Undated duties never block.
    """
    store = store or RoleStore()
    at = at or now()
    focused = current_focus()
    if not focused:
        return {"text": "", "block": False, "unserviced": []}
    try:
        role, folder = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return {"text": "", "block": False, "unserviced": []}
    duties = [d for d, _ in store.duties(folder)]
    placed = rank(duties, at, role.expires)
    text = priority_list(role, placed, at)
    pending = due_now_unserviced(role, duties, at)
    if not pending:
        return {"text": text, "block": False, "unserviced": []}
    names = ", ".join(f"\"{p.duty.title}\"" for p in pending)
    text += (f"\n\n🛡️ Due-now duties unserviced: {names}.\n"
             f"Service each (macf_tools role duty note|done|defer <id>), or put the role down honestly: "
             f"macf_tools role unfocus (recorded with what was due).")
    return {"text": text, "block": bool(auto_mode), "unserviced": [p.duty.id for p in pending]}


def prompt_line(store: Optional[RoleStore] = None, at: Optional[datetime] = None) -> str:
    """One line for UserPromptSubmit when the focused role has anything due
    today/overdue, or a review inside its horizon. Empty otherwise."""
    store = store or RoleStore()
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
    """The focused role's icon, for the banner's work-mode slot."""
    focused = current_focus()
    if not focused:
        return ""
    store = store or RoleStore()
    try:
        role, _ = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); no banner marker", file=sys.stderr)
        return ""
    return role.icon


def roles_store_mtime(store: Optional[RoleStore] = None) -> float:
    """Newest write in the roles store, so the touch nag counts duty touches."""
    store = store or RoleStore()
    if not store.root.exists():
        return 0.0
    return max((p.stat().st_mtime for p in store.root.rglob("*.json")), default=0.0)


def charter_context(store: Optional[RoleStore] = None) -> str:
    """The focused role's charter for SessionStart: the Boundaries must be in
    context whenever the agent stands in a role, and a new session starts
    with none of what the focus command printed. Empty when nothing is focused."""
    focused = current_focus()
    if not focused:
        return ""
    store = store or RoleStore()
    try:
        role, folder = store.find_role(focused)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return ""
    charter = folder / "charter.md"
    if not charter.exists():
        return ""
    engaged = [d.title for d, _ in store.engaged() if d.role_id == role.id]
    head = f"🎯 You hold the role {role.icon} {role.title} (R{role.id}). Its charter follows; the Boundaries bind every act taken in it."
    if engaged:
        head += " Engaged duties: " + "; ".join(engaged) + "."
    return head + "\n\n" + charter.read_text().rstrip()
