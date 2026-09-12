"""The 🎭 ROLES stanza and the trace header, per the roles policy's display rules.

The stanza goes BELOW the main tree because the terminal pins the bottom.
Line grammar: status box, icon, title, [state · review MM-DD], approach
mark, 🎯 for the focused role, then 👈 and age. The focused role is expanded
to every open duty in tier order and never truncated; other roles collapse to
one line carrying last and next. Completed duties follow the succinct rule:
shown while touched in this session, hidden after a restart, always with
--all.
"""
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Duty, Role
from .priority import (DONE, Placement, duty_mark, most_urgent_mark, now, rank, rank_roles,
                       review_mark)
from .store import RoleError, RoleStore

ANSI_DIM, ANSI_RESET, ANSI_RED, ANSI_GREEN = "\033[2m", "\033[0m", "\033[31m", "\033[32m"
BOX = {"active": "◼", "pending": "◻", "paused": "⏸", "expired": "✔", "retired": "✔", "done": "✔", "deferred": "⏸"}
MODES = ("none", "collapsed", "focused", "all")


def tree_display_preference() -> str:
    """``roles.tree_display`` from .maceff/config.json; default 'focused'."""
    try:
        import json
        from ..utils.paths import find_agent_home
        cfg = json.loads((find_agent_home() / ".maceff" / "config.json").read_text())
        v = (cfg.get("roles") or {}).get("tree_display")
        return v if v in MODES else "focused"
    except (OSError, ValueError, AttributeError):
        return "focused"


def _epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0.0


def rel_age(epoch: float, at_epoch: Optional[float] = None) -> str:
    secs = max(0, int((at_epoch or time.time()) - epoch))
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def touched_this_session(duty: Duty, session_id: Optional[str]) -> bool:
    """The succinct rule: a done/deferred duty stays visible while its last
    update's breadcrumb carries this session's id."""
    if not session_id or not duty.updates:
        return False
    return duty.updates[-1].breadcrumb.startswith(f"s_{session_id[:8]}")


def role_pointer(duties: Sequence[Duty]) -> Tuple[Optional[str], float]:
    """(duty id, epoch) of the role's newest-serviced duty: the role's own 👈."""
    best, best_ts = None, 0.0
    for d in duties:
        if d.updates:
            ts = _epoch(d.updates[-1].at)
            if ts >= best_ts:            # same second: the later record wins
                best, best_ts = d.id, ts
    return best, best_ts


def _when(d: Duty) -> str:
    if d.due:
        return d.due.strftime("due %a %m-%d") + (d.due.strftime(" %H:%M") if (d.due.hour or d.due.minute) else "")
    if d.cadence:
        return d.cadence.split(" until ")[0]
    return ""


def role_line(role: Role, placed: List[Placement], all_duties: Sequence[Duty], focused: bool,
              at: datetime, ansi: bool = True, collapsed: bool = False) -> str:
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    state = f"[{role.state}"
    if role.review_by:
        state += f" · review {role.review_by:%m-%d}"
    state += "]"
    mark = most_urgent_mark([duty_mark(p, at) for p in placed] + [review_mark(role, at)])
    line = f"{BOX.get(role.state, '?')} {role.icon} {role.title}  {dim}{state}{reset}"
    if collapsed:
        ptr_id, ptr_ts = role_pointer(all_duties)
        last = next((d for d in all_duties if d.id == ptr_id), None)
        nxt = next((p for p in placed if p.occurrence is not None and p.tier != DONE), None)
        bits = []
        if last is not None:
            bits.append(f"last: {last.title} ({rel_age(ptr_ts, at.timestamp())})")
        if nxt is not None:
            bits.append(f"next: {nxt.duty.title} ({nxt.occurrence:%m-%d})")
        if bits:
            line += f"  {dim}· " + " · ".join(bits) + reset
    if mark:
        line += f"  {mark}"
    if focused:
        line += "  🎯"
    return line


def duty_line(p: Placement, at: datetime, pointer: Optional[Tuple[str, float]] = None, ansi: bool = True) -> str:
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    d = p.duty
    box = BOX.get(d.state, "?")
    if ansi and d.state == "done":
        box = f"{ANSI_GREEN}✔{ANSI_RESET}"
    when = _when(d)
    imp = "" if d.importance == "normal" else f" ({d.importance.upper()})"
    line = f"    {box} 📌 {d.title}{imp}"
    if when:
        line += f"  {dim}{when}{reset}"
    mark = duty_mark(p, at)
    if mark:
        line += f"  {mark}"
    if pointer and pointer[0] == d.id and pointer[1]:
        line += f"  👈 {dim}{rel_age(pointer[1], at.timestamp())}{reset}"
    return line


def stanza(store: RoleStore, mode: str = "focused", focused_id: Optional[str] = None,
           session_id: Optional[str] = None, at: Optional[datetime] = None, ansi: bool = True,
           show_all: bool = False) -> List[str]:
    """Lines for the 🎭 ROLES stanza. Empty when there are no roles or mode is none."""
    if mode == "none":
        return []
    at = at or now()
    pairs = [(r, [d for d, _ in store.duties(f)]) for r, f in store.roles()]
    if not show_all:
        pairs = [(r, ds) for r, ds in pairs if r.state in ("active", "paused")]
    if not pairs:
        return []
    lines = ["🎭 ROLES"]
    for role, placed in rank_roles(pairs, focused_id, at):
        duties = next(ds for r, ds in pairs if r.id == role.id)
        expanded = mode == "all" or show_all or (mode == "focused" and role.id == focused_id)
        pointer = role_pointer(duties)
        if not expanded:
            lines.append(role_line(role, placed, duties, role.id == focused_id, at, ansi, collapsed=True)
                         + (f"  👈 {ANSI_DIM if ansi else ''}{rel_age(pointer[1], at.timestamp())}{ANSI_RESET if ansi else ''}"
                            if pointer[0] else ""))
            continue
        head = role_line(role, placed, duties, role.id == focused_id, at, ansi)
        if pointer[0]:
            head += f"  👈 {ANSI_DIM if ansi else ''}{rel_age(pointer[1], at.timestamp())}{ANSI_RESET if ansi else ''}"
        lines.append(head)
        everything = rank(duties, at, role.expires, include_done=True)
        hidden = 0
        for p in everything:                     # tier order; open duties never truncated
            if p.tier == DONE and not show_all and not touched_this_session(p.duty, session_id):
                hidden += 1
                continue
            lines.append(duty_line(p, at, pointer, ansi))
        if hidden:
            dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
            lines.append(f"    {dim}({hidden} done/deferred hidden; task roles --all shows them){reset}")
    return lines


def trace_header(store: RoleStore, focused_id: Optional[str], at: Optional[datetime] = None) -> List[str]:
    """The stanza above the work stack: focus, last serviced duty, next due."""
    if not focused_id:
        return []
    at = at or now()
    try:
        role, folder = store.find_role(focused_id)
    except RoleError as e:
        # A dangling focus must not break the trace; it is named instead.
        return [f"🎯 focus: {focused_id} (role not found: {e}; run: macf_tools role unfocus)"]
    duties = [d for d, _ in store.duties(folder)]
    placed = rank(duties, at, role.expires)
    ptr_id, ptr_ts = role_pointer(duties)
    last = next((d.title for d in duties if d.id == ptr_id), None)
    nxt = next((p for p in placed if p.occurrence is not None), None)
    top = placed[0] if placed else None
    parts = [f"🎯 focus: {role.icon} {role.title}"]
    if last:
        parts.append(f"last serviced: {last} ({rel_age(ptr_ts, at.timestamp())})")
    if nxt:
        parts.append(f"next due: {nxt.duty.title} ({nxt.occurrence:%a %m-%d}{'  ' + duty_mark(nxt, at) if duty_mark(nxt, at) else ''})")
    elif top:
        parts.append(f"top duty: {top.duty.title} ({top.tier_name})")
    return ["   " + " · ".join(parts)]


def next_duty_line(store: RoleStore, focused_id: Optional[str], at: Optional[datetime] = None) -> Optional[str]:
    """For the post-completion hand-back: the focused role's next due duty."""
    if not focused_id:
        return None
    at = at or now()
    try:
        role, folder = store.find_role(focused_id)
    except RoleError as e:
        print(f"⚠️ MACF: focused role {focused_id} not found ({e}); run macf_tools role unfocus", file=sys.stderr)
        return None
    placed = rank([d for d, _ in store.duties(folder)], at, role.expires)
    nxt = next((p for p in placed if p.occurrence is not None), None) or (placed[0] if placed else None)
    if not nxt:
        return None
    mark = duty_mark(nxt, at)
    return f"🎯 {role.icon} {role.title}: next duty {nxt.duty.title} ({nxt.tier_name}{', ' + mark if mark else ''})"
