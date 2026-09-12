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

ANSI_DIM, ANSI_RESET, ANSI_RED, ANSI_GREEN, ANSI_STRIKE = "\033[2m", "\033[0m", "\033[31m", "\033[32m", "\033[9m"
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
    """(duty id, epoch) of the role's newest-serviced duty."""
    best, best_ts = None, 0.0
    for d in duties:
        if d.updates:
            ts = _epoch(d.updates[-1].at)
            if ts >= best_ts:            # same second: the later record wins
                best, best_ts = d.id, ts
    return best, best_ts


def stanza_pointer(pairs: Sequence[Tuple[Role, Sequence[Duty]]]) -> Tuple[Optional[str], Optional[str], float]:
    """The stanza's ONE 👈: (role id, duty id or None, epoch) of the newest touch
    across every role and duty. A duty touch points at the duty's line when its
    role is expanded and at the role's collapsed line otherwise; a role-level
    note points at the role line. Unfocusing writes nothing, so the pointer
    stays where the last work was until something else is touched."""
    best = (None, None, 0.0)
    for role, duties in pairs:
        if role.updates:
            ts = _epoch(role.updates[-1].at)
            if ts >= best[2]:
                best = (role.id, None, ts)
        did, ts = role_pointer(duties)
        if did and ts >= best[2]:
            best = (role.id, did, ts)
    return best


def fit(text: str, width: Optional[int]) -> str:
    """Trim free text to *width* visible characters with the tree's '...' convention.
    0 or None disables, as --title-width 0 does for the tree."""
    if not width or width <= 0 or len(text) <= width:
        return text
    return text[:max(1, width - 3)].rstrip() + "..."


def _when(d: Duty) -> str:
    if d.due:
        return d.due.strftime("due %a %m-%d") + (d.due.strftime(" %H:%M") if (d.due.hour or d.due.minute) else "")
    if d.cadence:
        return d.cadence.split(" until ")[0]
    return ""


def role_line(role: Role, placed: List[Placement], all_duties: Sequence[Duty], focused: bool,
              at: datetime, ansi: bool = True, collapsed: bool = False,
              title_width: Optional[int] = 80) -> str:
    """One role line. Titles are trimmed to *title_width* the way the tree trims
    task titles (40 in succinct mode, 80 otherwise); the collapsed line's last/next
    labels get half that, since they are context, not the subject."""
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    state = f"[{role.state}"
    if role.review_by:
        state += f" · review {role.review_by:%m-%d}"
    state += "]"
    mark = most_urgent_mark([duty_mark(p, at) for p in placed] + [review_mark(role, at)])
    box = BOX.get(role.state, "?")
    if ansi and focused and role.state == "active":
        box = f"{ANSI_RED}◼{ANSI_RESET}"       # lit like an in_progress task: attention is here
    line = f"{box} {role.icon} {fit(role.title, title_width)}  {dim}{state}{reset}"
    if collapsed:
        half = (title_width // 2) if title_width else None
        ptr_id, ptr_ts = role_pointer(all_duties)
        last = next((d for d in all_duties if d.id == ptr_id), None)
        # In the scanning view the age is only shown when this line holds the
        # stanza's pointer; otherwise 'last' would repeat what 👈 says.
        nxt = next((p for p in placed if p.occurrence is not None and p.tier != DONE), None)
        bits = []
        # In the scanning view (title_width <= 40) the 👈 age already says when
        # the role was last touched; only 'next' earns its columns there.
        if last is not None and (half is None or half > 20):
            bits.append(f"last: {fit(last.title, half)} ({rel_age(ptr_ts, at.timestamp())})")
        if nxt is not None:
            bits.append(f"next: {fit(nxt.duty.title, half)} ({nxt.occurrence:%m-%d})")
        if bits:
            line += f"  {dim}· " + " · ".join(bits) + reset
    if mark:
        line += f"  {mark}"
    if focused:
        line += "  🎯"
    return line


def duty_line(p: Placement, at: datetime, pointer: Optional[Tuple[str, float]] = None, ansi: bool = True,
              title_width: Optional[int] = 80) -> str:
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    d = p.duty
    box = BOX.get(d.state, "?")
    if ansi and d.state == "done":
        box = f"{ANSI_GREEN}✔{ANSI_RESET}"
    elif ansi and d.state == "active":
        box = f"{ANSI_RED}◼{ANSI_RESET}"       # a duty with work in flight, as the tree shows in_progress
    when = _when(d)
    imp = "" if d.importance == "normal" else f" ({d.importance.upper()})"
    title = fit(d.title, title_width)
    if ansi and d.state == "done":
        title = f"{ANSI_DIM}{ANSI_STRIKE}{title}{ANSI_RESET}"   # as the tree strikes a completed task
    line = f"    {box} 📌 {title}{imp}"
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
           show_all: bool = False, title_width: Optional[int] = 80) -> List[str]:
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
    ptr_role, ptr_duty, ptr_ts = stanza_pointer(pairs)
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    finger = f"  👈 {dim}{rel_age(ptr_ts, at.timestamp())}{reset}" if ptr_role else ""
    for role, placed in rank_roles(pairs, focused_id, at):
        duties = next(ds for r, ds in pairs if r.id == role.id)
        expanded = mode == "all" or show_all or (mode == "focused" and role.id == focused_id)
        if not expanded:
            lines.append(role_line(role, placed, duties, role.id == focused_id, at, ansi, collapsed=True,
                                   title_width=title_width)
                         + (finger if role.id == ptr_role else ""))
            continue
        head = role_line(role, placed, duties, role.id == focused_id, at, ansi, title_width=title_width)
        if role.id == ptr_role and ptr_duty is None:
            head += finger                       # the newest touch was a note on the role itself
        lines.append(head)
        everything = rank(duties, at, role.expires, include_done=True)
        hidden = 0
        duty_ptr = (ptr_duty, ptr_ts) if role.id == ptr_role and ptr_duty else None
        for p in everything:                     # tier order; open duties never truncated
            if p.tier == DONE and not show_all and not touched_this_session(p.duty, session_id):
                hidden += 1
                continue
            lines.append(duty_line(p, at, duty_ptr, ansi, title_width))
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
