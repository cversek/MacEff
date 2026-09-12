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
from .focus import current_focus_event
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


def last_touch(d: Duty) -> float:
    """Epoch of the duty's newest touch. A disengagement is not a touch:
    attention left that duty, it did not land there."""
    for u in reversed(d.updates):
        if u.kind != "disengage":
            return _epoch(u.at)
    return 0.0


def role_pointer(duties: Sequence[Duty]) -> Tuple[Optional[str], float]:
    """(duty id, epoch) of the role's newest-touched duty."""
    best, best_ts = None, 0.0
    for d in duties:
        ts = last_touch(d)
        if ts and ts >= best_ts:         # same second: the later record wins
            best, best_ts = d.id, ts
    return best, best_ts


def stanza_pointers(pairs: Sequence[Tuple[Role, Sequence[Duty]]],
                    expanded: Sequence[str] = (),
                    focus: Tuple[Optional[str], float] = (None, 0.0)) -> List[Tuple[str, Optional[str], float]]:
    """Where the stanza's 👈 goes: a list of (role id, duty id or None, epoch).

    Normally ONE entry, the newest touch across every role and duty. A duty
    touch points at the duty's line when its role is expanded and at the role's
    collapsed line otherwise. An expanded role's own line never carries the
    pointer for a role-level note (its 🎯 carries the focus age instead): the
    note hands the pointer to that role's newest-touched duty, or to nobody.
    Focusing IS a touch: when the focus event is the newest thing and the
    role has no active duty yet, the pointer comes up to the focused line
    after 🎯 and its age, and moves down once a duty is engaged. Unfocusing
    writes nothing, so the pointer stays where the last work was.

    Under a deliberate PARALLEL engagement -- more than one active duty across
    the store -- every active duty gets its own pointer and age, so the
    operator sees the situation at a glance.
    """
    active = [(role.id, d.id, last_touch(d)) for role, duties in pairs for d in duties if d.state == "active"]
    best = (None, None, 0.0)
    for role, duties in pairs:
        did, ts = role_pointer(duties)
        if role.updates:
            rts = _epoch(role.updates[-1].at)
            if rts >= ts:
                # the role note is this role's newest touch; expanded, it defers to the duty
                did, ts = (did if role.id in expanded else None), rts
        if role.id == focus[0] and focus[1] >= ts and not any(d.state == "active" for d in duties):
            did, ts = None, focus[1]         # the focus itself is the newest touch: the finger sits by 🎯
            if ts >= best[2]:
                best = (role.id, did, ts)
            continue
        if ts >= best[2] and (did or role.id not in expanded):
            best = (role.id, did, ts)
    if len(active) > 1:
        # attention is split across the engaged duties; a focus newer than all of
        # them is a third place attention went, and is shown too
        fresh_focus = best[0] == focus[0] and best[1] is None and best[2] > max(ts for _, _, ts in active)
        return active + ([best] if fresh_focus else [])
    return [best] if best[0] else []


def stanza_pointer(pairs: Sequence[Tuple[Role, Sequence[Duty]]]) -> Tuple[Optional[str], Optional[str], float]:
    """The single newest touch, for callers that want one answer (see stanza_pointers)."""
    ptrs = stanza_pointers(pairs)
    return ptrs[0] if len(ptrs) == 1 else max(ptrs, key=lambda t: t[2]) if ptrs else (None, None, 0.0)


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
              title_width: Optional[int] = 80, focused_since: float = 0.0) -> str:
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
    line = f"{box} {dim}R{role.id}{reset} {role.icon} {fit(role.title, title_width)}  {dim}{state}{reset}"
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
        # the age beside 🎯 is the FOCUS time (the focus event), not any duty's touch
        line += "  🎯" + (f" {dim}{rel_age(focused_since, at.timestamp())}{reset}" if focused_since else "")
    return line


def duty_line(p: Placement, at: datetime, pointers: Sequence[Tuple[str, float]] = (), ansi: bool = True,
              title_width: Optional[int] = 80) -> str:
    """*pointers* is the stanza's (duty id, epoch) set; this line gets 👈 if it is in it."""
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    d = p.duty
    box = BOX.get(d.state, "?")
    if ansi and d.state == "done":
        box = f"{ANSI_GREEN}✔{ANSI_RESET}"
    elif ansi and d.state == "active":
        box = f"{ANSI_RED}◼{ANSI_RESET}"       # a duty with work in flight, as the tree shows in_progress
    when = _when(d)
    imp = "" if d.importance == "normal" else f" ({d.importance.upper()})"
    imp += " (meta)" if d.meta else ""
    title = fit(d.title, title_width)
    if ansi and d.state == "done":
        title = f"{ANSI_DIM}{ANSI_STRIKE}{title}{ANSI_RESET}"   # as the tree strikes a completed task
    line = f"    {box} {dim}D{d.id}{reset} 📌 {title}{imp}"     # the code before the pin, as #N sits before a task
    if when:
        line += f"  {dim}{when}{reset}"
    mark = duty_mark(p, at)
    if mark:
        line += f"  {mark}"
    ts = dict(pointers).get(d.id)
    if ts:
        line += f"  👈 {dim}{rel_age(ts, at.timestamp())}{reset}"
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
    ranked = rank_roles(pairs, focused_id, at)
    expanded_ids = [r.id for r, _ in ranked
                    if mode == "all" or show_all or (mode == "focused" and r.id == focused_id)]
    focused_since = current_focus_event()[1] if focused_id else 0.0
    pointers = stanza_pointers(pairs, expanded_ids, (focused_id, focused_since))
    dim, reset = (ANSI_DIM, ANSI_RESET) if ansi else ("", "")
    for role, placed in ranked:
        duties = next(ds for r, ds in pairs if r.id == role.id)
        mine = [(did, ts) for rid, did, ts in pointers if rid == role.id]
        if role.id not in expanded_ids:
            line = role_line(role, placed, duties, role.id == focused_id, at, ansi, collapsed=True,
                             title_width=title_width, focused_since=focused_since)
            if mine:                             # a collapsed line holds its duties' pointers
                line += f"  👈 {dim}{rel_age(max(ts for _, ts in mine), at.timestamp())}{reset}"
            lines.append(line)
            continue
        head = role_line(role, placed, duties, role.id == focused_id, at, ansi, title_width=title_width,
                         focused_since=focused_since)
        if any(did is None for did, _ in mine):     # the focus is the newest touch: finger after 🎯 and its age
            head += f"  👈 {dim}{rel_age(focused_since, at.timestamp())}{reset}"
        lines.append(head)
        everything = rank(duties, at, role.expires, include_done=True)
        hidden = 0
        duty_ptr = [(did, ts) for did, ts in mine if did]
        for p in everything:                     # tier order; open duties never truncated
            if p.tier == DONE and not show_all and not touched_this_session(p.duty, session_id):
                hidden += 1
                continue
            lines.append(duty_line(p, at, duty_ptr, ansi, title_width))
        if hidden:
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
