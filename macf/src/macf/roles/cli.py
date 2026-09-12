"""``macf_tools role ...`` -- the verbs the roles policy names.

Handlers take an argparse namespace and return an exit code. Refusals are one
``❌`` line and exit 1, the amail/gmail shape; ``--json`` prints the record and
nothing else. Registration is one call from the main parser so this file owns
the whole surface.
"""
import argparse
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from . import calendar as cal
from .models import ICON_SHELF, Duty, Role, dump
from .priority import (duty_mark, most_urgent_mark, now, rank, rank_roles, review_mark, why)
from .store import RoleError, RoleStore

STATE_BOX = {"active": "◼", "pending": "◻", "paused": "⏸", "expired": "✔", "retired": "✔",
             "done": "✔", "deferred": "⏸"}


# ---- helpers -----------------------------------------------------------------

def _one_line(e: Exception) -> str:
    """A pydantic ValidationError flattened to ``field: message``; anything else as is."""
    errors = getattr(e, "errors", None)
    if callable(errors):
        try:
            parts = []
            for err in errors():
                loc = ".".join(str(x) for x in err.get("loc", ()))
                msg = err.get("msg", "")
                msg = msg[len("Value error, "):] if msg.startswith("Value error, ") else msg
                parts.append(f"{loc}: {msg}" if loc else msg)
            if parts:
                return "; ".join(parts)
        except (TypeError, AttributeError, KeyError):
            pass
    return str(e)


def _fail(e: Exception, as_json: bool = False) -> int:
    msg = _one_line(e)
    if as_json:
        print(json.dumps({"ok": False, "error": msg}, indent=2))
    else:
        print(f"❌ {msg}")
    return 1


def _date(text: Optional[str], flag: str) -> Optional[date]:
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise RoleError(f"{flag} needs YYYY-MM-DD, not {text!r}") from None


def _datetime(text: Optional[str], flag: str) -> Optional[datetime]:
    if text is None:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise RoleError(f"{flag} needs YYYY-MM-DD or YYYY-MM-DDTHH:MM, not {text!r}")


def _csv(items: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for chunk in items or []:
        out.extend(x.strip() for x in chunk.split(",") if x.strip())
    return out


def _role_line(role: Role, duties: List[Duty], at=None) -> str:
    at = at or now()
    state = f"[{role.state}"
    if role.review_by:
        state += f" · review {role.review_by.strftime('%m-%d')}"
    if role.expires:
        state += f" · expires {role.expires.isoformat()}"
    state += "]"
    n_open = sum(1 for d in duties if d.state in ("pending", "active"))
    placed = rank(duties, at, role.expires)
    mark = most_urgent_mark([duty_mark(p, at) for p in placed] + [review_mark(role, at)])
    line = f"{STATE_BOX.get(role.state, '?')} {role.icon} {role.id}  {role.title}  {state}  duties {n_open} open / {len(duties)}"
    return line + (f"  {mark}" if mark else "")


def _duty_line(d: Duty, mark: str = "") -> str:
    when = ""
    if d.due:
        when = f"  due {d.due.strftime('%a %m-%d')}" + (d.due.strftime(' %H:%M') if (d.due.hour or d.due.minute) else "")
    elif d.cadence:
        when = f"  {d.cadence}"
    imp = "" if d.importance == "normal" else f"  ({d.importance.upper()})"
    hz = f"  horizon {d.horizon}" if d.horizon else ""
    return f"{STATE_BOX.get(d.state, '?')} 📌 {d.id}  {d.title}{when}{hz}{imp}" + (f"  {mark}" if mark else "")


def _role_record(store: RoleStore, role: Role, folder) -> Dict[str, Any]:
    rec = dump(role)
    rec["folder"] = str(folder)
    rec["duties"] = [dump(d) for d, _ in store.duties(folder)]
    return rec


# ---- role verbs --------------------------------------------------------------

def cmd_role_create(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        icon = args.icon or "🎭"
        role, folder = store.create_role(
            args.title, icon=icon,
            tenure_start=_date(args.tenure_start, "--tenure-start"),
            expires=_date(args.expires, "--expires"),
            review_by=_date(args.review_by, "--review-by"),
            review_horizon=args.review_horizon,
            resources=_csv(args.resource), charter_seed=args.charter or "",
            wiki_links=_csv(args.wiki_links), why=args.why or "")
    except (RoleError, ValueError) as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(_role_record(store, role, folder), indent=2))
        return 0
    print(f"✅ Role {role.id} assigned: {role.icon} {role.title}")
    print(f"   {folder}")
    print(f"   charter: {folder / 'charter.md'} (scaffold -- write it)")
    if icon not in ICON_SHELF:
        print(f"   icon {icon!r} is not on the policy shelf; kept as given")
    return 0


def cmd_role_list(args: argparse.Namespace) -> int:
    store = RoleStore()
    pairs = store.roles()
    if not getattr(args, "all", False):
        pairs = [p for p in pairs if p[0].state in ("active", "paused")]
    if args.json:
        print(json.dumps([_role_record(store, r, f) for r, f in pairs], indent=2))
        return 0
    if not pairs:
        print("no roles" + ("" if getattr(args, "all", False) else " (--all shows expired and retired)"))
        return 0
    at = now()
    ranked = rank_roles([(r, [d for d, _ in store.duties(f)]) for r, f in pairs], at=at)
    for role, placed in ranked:
        print(_role_line(role, [p.duty for p in placed] + [d for d, _ in store.duties(store.folder_of(role)) if d.state in ("done", "deferred")], at))
    return 0


def cmd_role_show(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        role, folder = store.find_role(args.role)
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(_role_record(store, role, folder), indent=2))
        return 0
    at = now()
    duties = [d for d, _ in store.duties(folder)]
    print(_role_line(role, duties, at))
    print(f"   folder:  {folder}")
    print(f"   tenure:  from {role.tenure_start}" + (f" to {role.expires}" if role.expires else ""))
    if role.review_by:
        rm = review_mark(role, at)
        print(f"   review:  {role.review_by} (horizon {role.review_horizon})" + (f"  {rm}" if rm else ""))
    for r in role.resources:
        print(f"   resource: {r}")
    show_done = getattr(args, "all", False)
    for p in rank(duties, at, role.expires, include_done=show_done):
        d = p.duty
        print("   " + _duty_line(d, duty_mark(p, at)))
        for tid, status, subject in store.live_tracks(d):
            print(f"        tracks #{tid} [{status or 'missing'}] {subject or ''}")
        for ev in d.evidence:
            print(f"        evidence {ev}")
    hidden = sum(1 for d in duties if d.state in ("done", "deferred"))
    if hidden and not show_done:
        print(f"   ({hidden} done/deferred hidden; --all shows them)")
    if role.updates:
        print("   updates:")
        for u in role.updates[-(len(role.updates) if show_done else 5):]:
            print(f"     {u.at}  {u.kind:<8} {u.description}")
    return 0


def cmd_role_note(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        role, folder = store.find_role(args.role)
        store.note_role(role, folder, args.message)
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(role), indent=2))
    else:
        print(f"✅ noted on {role.icon} {role.title}")
    return 0


def _advance_role(args: argparse.Namespace, new_state: str) -> int:
    store = RoleStore()
    try:
        role, folder = store.find_role(args.role)
        store.advance_role(role, folder, new_state, getattr(args, "reason", "") or "")
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(role), indent=2))
    else:
        print(f"✅ {role.icon} {role.title} is now {new_state}")
    return 0


def cmd_role_pause(args): return _advance_role(args, "paused")
def cmd_role_resume(args): return _advance_role(args, "active")
def cmd_role_expire(args): return _advance_role(args, "expired")
def cmd_role_retire(args): return _advance_role(args, "retired")


def cmd_role_review(args: argparse.Namespace) -> int:
    """Record a review: outcome, and the next review date with its horizon."""
    store = RoleStore()
    try:
        role, folder = store.find_role(args.role)
        nxt = _date(args.next, "--next")
        if nxt and not (args.next_horizon or role.review_horizon):
            raise RoleError("--next needs --next-horizon (or an existing review horizon on the role)")
        text = f"Reviewed: {args.outcome}"
        if nxt:
            role.review_by = nxt
            if args.next_horizon:
                role.review_horizon = args.next_horizon
            text += f"; next review {nxt} (horizon {role.review_horizon})"
        Role.model_validate(dump(role))          # re-run the model's rules after the edit
        store.note_role(role, folder, text, kind="review")
        if args.expire:
            store.advance_role(role, folder, "expired", "at review")
        elif args.retire:
            store.advance_role(role, folder, "retired", "at review")
    except (RoleError, ValueError) as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(role), indent=2))
    else:
        print(f"✅ review recorded on {role.icon} {role.title}" + (f"; next {role.review_by}" if role.review_by else ""))
    return 0


# ---- duty verbs --------------------------------------------------------------

def cmd_duty_add(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        role, folder = store.find_role(args.role)
        duty, path = store.add_duty(
            role, folder, args.title, body=args.body or "", importance=args.importance,
            due=_datetime(args.due, "--due"), horizon=args.horizon, why=args.why or "",
            cadence=args.cadence, depends_on=_csv(args.depends_on), tracks=_csv(args.tracks),
            wiki_links=_csv(args.wiki_links))
    except (RoleError, ValueError) as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
        return 0
    print(f"✅ Duty {duty.id} declared under {role.icon} {role.title}")
    print("   " + _duty_line(duty))
    print(f"   {path}")
    return 0


def cmd_duty_show(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        role, _ = store.role_of(duty)
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        rec = dump(duty)
        rec["path"] = str(path)
        rec["live_tracks"] = [{"task": t, "status": s, "subject": sub} for t, s, sub in store.live_tracks(duty)]
        print(json.dumps(rec, indent=2))
        return 0
    print(_duty_line(duty))
    print(f"   role:    {role.icon} {role.title} ({role.id})")
    if duty.body:
        print(f"   body:    {duty.body}")
    if duty.depends_on:
        print(f"   after:   {', '.join(duty.depends_on)}")
    for tid, status, subject in store.live_tracks(duty):
        print(f"   tracks:  #{tid} [{status or 'missing'}] {subject or ''}")
    for ev in duty.evidence:
        print(f"   evidence: {ev}")
    if duty.wiki_links:
        print(f"   links:   {' '.join('[[' + w + ']]' for w in duty.wiki_links)}")
    print(f"   path:    {path}")
    for u in duty.updates:
        extra = f" (done_on {u.done_on})" if u.done_on else ""
        print(f"     {u.at}  {u.kind:<8} {u.description}{extra}")
    return 0


def cmd_duty_note(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        done_on = _date(args.done_on, "--done-on")
        if done_on and not duty.cadence:
            raise RoleError("--done-on marks an occurrence of a cadence duty; this duty has no cadence "
                            "(use duty done --evidence for a one-off)")
        store.note_duty(duty, path.parent, args.message, kind="occurrence" if done_on else "note", done_on=done_on)
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ noted on 📌 {duty.title}" + (f" (occurrence {done_on} done)" if done_on else ""))
    return 0


def cmd_duty_done(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        store.advance_duty(duty, path.parent, "done", args.note or "", evidence=_csv(args.evidence))
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ 📌 {duty.title} done; evidence {', '.join(duty.evidence)}")
    return 0


def cmd_duty_defer(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        store.advance_duty(duty, path.parent, "deferred", args.reason or "")
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ 📌 {duty.title} deferred: {args.reason}")
    return 0


def cmd_duty_reactivate(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        store.advance_duty(duty, path.parent, "pending", args.reason or "")
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ 📌 {duty.title} is pending again")
    return 0


def cmd_duty_link(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        store.link(duty, path.parent, _csv(args.tasks))
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ 📌 {duty.title} tracks {', '.join('#' + t for t in duty.tracks)}")
    return 0


def cmd_duty_unlink(args: argparse.Namespace) -> int:
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        store.unlink(duty, path.parent, _csv(args.tasks))
    except RoleError as e:
        return _fail(e, args.json)
    if args.json:
        print(json.dumps(dump(duty), indent=2))
    else:
        print(f"✅ 📌 {duty.title} tracks {', '.join('#' + t for t in duty.tracks) or 'nothing'}")
    return 0


def cmd_duty_why(args: argparse.Namespace) -> int:
    """The tier and the fact that put the duty there."""
    store = RoleStore()
    try:
        duty, path = store.find_duty(args.duty)
        role, folder = store.role_of(duty)
    except RoleError as e:
        return _fail(e, args.json)
    at = now()
    duties = [d for d, _ in store.duties(folder)]
    placed = rank(duties, at, role.expires, include_done=True)
    p = next(x for x in placed if x.duty.id == duty.id)
    position = [x.duty.id for x in placed if x.tier != 6].index(duty.id) + 1 if p.tier != 6 else None
    if args.json:
        print(json.dumps({"duty_id": duty.id, "tier": p.tier_name, "reason": p.reason,
                          "occurrence": p.occurrence.isoformat() if p.occurrence else None,
                          "entered": p.entered.isoformat() if p.entered else None,
                          "mark": duty_mark(p, at), "position": position,
                          "of": sum(1 for x in placed if x.tier != 6)}, indent=2))
        return 0
    mark = duty_mark(p, at)
    print(f"📌 {duty.title}  ({role.icon} {role.title})" + (f"  {mark}" if mark else ""))
    print(f"   {why(p)}")
    if position:
        print(f"   position {position} of {sum(1 for x in placed if x.tier != 6)} open duties in this role")
    return 0


def cmd_role_calendar(args: argparse.Namespace) -> int:
    store = RoleStore()
    at = now()
    try:
        start, end = cal.window(args.weeks, _date(getattr(args, "from_", None), "--from"), _date(args.to, "--to"), at)
    except RoleError as e:
        return _fail(e, args.json)
    if end < start:
        return _fail(RoleError("--to is before --from"), args.json)
    pairs = [(r, [d for d, _ in store.duties(f)]) for r, f in store.roles()]
    evs = cal.events(pairs, start, end, at)
    if args.ics:
        from pathlib import Path
        out = Path(args.ics)
        out.write_text(cal.ics(pairs, start, end, at))
        if not args.json:
            print(f"✅ wrote {out} ({sum(1 for _ in open(out)) } lines)")
    if args.json:
        print(json.dumps({"from": start.isoformat(), "to": end.isoformat(),
                          "events": [e.to_json() for e in evs]}, indent=2))
        return 0
    if args.ics:
        return 0
    print(cal.grid(evs, start, end, at) if args.grid else cal.agenda(evs, start, end, at))
    return 0


def cmd_role_focus(args: argparse.Namespace) -> int:
    """Focus a role (an event), or with no argument say which is focused."""
    from .focus import current_focus, set_focus
    from .hooks import due_now_unserviced
    store = RoleStore()
    previous = current_focus()
    if not args.role:
        if args.json:
            print(json.dumps({"focused": previous}, indent=2))
            return 0
        if previous:
            try:
                role, _ = store.find_role(previous)
                print(f"🎯 {role.icon} {role.title} ({role.id})")
            except RoleError:
                print(f"🎯 {previous} (role not found; run: macf_tools role unfocus)")
        else:
            print("no role is focused")
        return 0
    try:
        role, folder = store.find_role(args.role)
        if role.state != "active":
            raise RoleError(f"{role.title} is {role.state}; only an active role can be focused")
    except RoleError as e:
        return _fail(e, args.json)
    if previous == role.id:
        print(f"🎯 {role.icon} {role.title} is already focused" if not args.json else json.dumps({"focused": role.id}))
        return 0
    set_focus(role.id, previous, note=args.note or "")
    if args.json:
        print(json.dumps({"focused": role.id, "previous": previous}, indent=2))
        return 0
    print(f"🎯 focused {role.icon} {role.title}" + (f" (was {previous})" if previous else ""))
    at = now()
    pending = due_now_unserviced(role, [d for d, _ in store.duties(folder)], at)
    if pending:
        print("   due now, unserviced: " + "; ".join(f"{p.duty.title} ({duty_mark(p, at)})" for p in pending))
    return 0


def cmd_role_unfocus(args: argparse.Namespace) -> int:
    """Always allowed; records the due-now duties left unserviced at the moment of escape."""
    from .focus import current_focus, set_focus
    from .hooks import due_now_unserviced
    store = RoleStore()
    previous = current_focus()
    if not previous:
        print("no role is focused" if not args.json else json.dumps({"focused": None}))
        return 0
    unserviced = []
    try:
        role, folder = store.find_role(previous)
        at = now()
        unserviced = [{"duty_id": p.duty.id, "title": p.duty.title, "tier": p.tier_name}
                      for p in due_now_unserviced(role, [d for d, _ in store.duties(folder)], at)]
        if args.note:
            store.note_role(role, folder, args.note, kind="unfocus")
        label = f"{role.icon} {role.title}"
    except RoleError:
        label = previous
    set_focus(None, previous, unserviced, note=args.note or "")
    if args.json:
        print(json.dumps({"focused": None, "previous": previous, "unserviced_due_now": unserviced}, indent=2))
        return 0
    print(f"✅ unfocused {label}")
    if unserviced:
        print("   left due-now and unserviced (recorded): " + "; ".join(u["title"] for u in unserviced))
        if not args.note:
            print("   an honest escape says why: macf_tools role note <id> \"...\", or duty defer --reason")
    return 0


# ---- registration ------------------------------------------------------------

def add_role_parser(sub: argparse._SubParsersAction) -> None:
    role = sub.add_parser("role", help="standing positions and their duties (roles policy)")
    rs = role.add_subparsers(dest="role_cmd")

    def js(p):
        p.add_argument("--json", action="store_true", help="print the record as JSON")

    p = rs.add_parser("create", help="assign a role (the ceremony is the maceff-assign-role skill)")
    p.add_argument("title")
    p.add_argument("--icon", help="one glyph; the policy shelf: " + " ".join(ICON_SHELF))
    p.add_argument("--tenure-start", help="YYYY-MM-DD (default today)")
    p.add_argument("--expires", help="YYYY-MM-DD")
    p.add_argument("--review-by", help="YYYY-MM-DD; needs --review-horizon")
    p.add_argument("--review-horizon", help="e.g. 14d; reasoned, never defaulted")
    p.add_argument("--resource", action="append", help="path or URL the role depends on (repeatable, or comma-separated)")
    p.add_argument("--charter", help="seed text for the charter's Purpose")
    p.add_argument("--wiki-links", action="append", help="concepts, comma-separated")
    p.add_argument("--why", help="first note on the role")
    js(p); p.set_defaults(func=cmd_role_create)

    p = rs.add_parser("list", help="active and paused roles (--all for every state)")
    p.add_argument("--all", action="store_true")
    js(p); p.set_defaults(func=cmd_role_list)

    p = rs.add_parser("show", help="a role, its duties with live task status, recent updates")
    p.add_argument("role", help="id or title prefix")
    p.add_argument("--all", action="store_true", help="include done/deferred duties and every update")
    js(p); p.set_defaults(func=cmd_role_show)

    p = rs.add_parser("note", help="a breadcrumbed note on the role")
    p.add_argument("role"); p.add_argument("message")
    js(p); p.set_defaults(func=cmd_role_note)

    for verb, fn, hlp in (("pause", cmd_role_pause, "pause: duties leave every ordering and gate"),
                          ("resume", cmd_role_resume, "resume a paused role"),
                          ("expire", cmd_role_expire, "tenure ended by date (terminal)"),
                          ("retire", cmd_role_retire, "appointment ended early or replaced (terminal)")):
        p = rs.add_parser(verb, help=hlp)
        p.add_argument("role"); p.add_argument("--reason", default="")
        js(p); p.set_defaults(func=fn)

    p = rs.add_parser("review", help="record the tenure review and set the next review date")
    p.add_argument("role")
    p.add_argument("--outcome", required=True, help="what the review concluded")
    p.add_argument("--next", help="next review_by, YYYY-MM-DD")
    p.add_argument("--next-horizon", help="horizon for the next review, e.g. 14d")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--expire", action="store_true", help="the appointment ended at this review")
    g.add_argument("--retire", action="store_true", help="the appointment is being given up at this review")
    js(p); p.set_defaults(func=cmd_role_review)

    p = rs.add_parser("focus", help="hold one role: its duties become a prioritized scope for the hooks")
    p.add_argument("role", nargs="?", help="id or title prefix; omit to show the current focus")
    p.add_argument("--note", help="why, recorded on the event")
    js(p); p.set_defaults(func=cmd_role_focus)

    p = rs.add_parser("unfocus", help="put the focused role down (always allowed; what was due is recorded)")
    p.add_argument("--note", help="why -- the honest escape; also noted on the role")
    js(p); p.set_defaults(func=cmd_role_unfocus)

    p = rs.add_parser("calendar", help="roles x duties as an agenda, a week grid, JSON, or an .ics file")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--weeks", type=int, help="window from today (default 2)")
    g.add_argument("--from", dest="from_", help="YYYY-MM-DD")
    p.add_argument("--to", help="YYYY-MM-DD (with --from)")
    p.add_argument("--grid", action="store_true", help="a week grid instead of the agenda")
    p.add_argument("--ics", metavar="PATH", help="write an iCalendar file")
    js(p); p.set_defaults(func=cmd_role_calendar)

    duty = rs.add_parser("duty", help="duties: declarations that point at their implementations")
    ds = duty.add_subparsers(dest="duty_cmd")

    p = ds.add_parser("add", help="declare a duty under a role")
    p.add_argument("role", help="role id or title prefix")
    p.add_argument("title")
    p.add_argument("--body", help="what must be true (a declaration, not a procedure)")
    p.add_argument("--importance", choices=("critical", "high", "normal", "low"), default="normal")
    p.add_argument("--due", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    p.add_argument("--cadence", help="daily | weekly:tue[,thu] | monthly:15  [at HH:MM] [dur 6h] [until YYYY-MM-DD]")
    p.add_argument("--horizon", help="lead time before due at which the duty is DUE_SOON: 3d, 36h, 90m")
    p.add_argument("--why", help="the reasoning behind the horizon (required with --horizon); the duty's first note")
    p.add_argument("--depends-on", action="append", help="duty ids that must be done first, comma-separated")
    p.add_argument("--tracks", action="append", help="task ids implementing this duty, comma-separated")
    p.add_argument("--wiki-links", action="append", help="concepts, comma-separated")
    js(p); p.set_defaults(func=cmd_duty_add)

    p = ds.add_parser("show", help="a duty with live task status and every update")
    p.add_argument("duty", help="id or title prefix")
    js(p); p.set_defaults(func=cmd_duty_show)

    p = ds.add_parser("note", help="a breadcrumbed note; --done-on marks a cadence occurrence done")
    p.add_argument("duty"); p.add_argument("message")
    p.add_argument("--done-on", help="YYYY-MM-DD of the occurrence this note completes")
    js(p); p.set_defaults(func=cmd_duty_note)

    p = ds.add_parser("done", help="satisfied: needs --evidence (a completed task id or a CA path)")
    p.add_argument("duty")
    p.add_argument("--evidence", action="append", help="completed task id (#N) or CA path; repeatable")
    p.add_argument("--note", help="what satisfied it")
    js(p); p.set_defaults(func=cmd_duty_done)

    p = ds.add_parser("defer", help="set aside with a reason (kept for the record)")
    p.add_argument("duty"); p.add_argument("--reason", required=True)
    js(p); p.set_defaults(func=cmd_duty_defer)

    p = ds.add_parser("reactivate", help="a deferred duty is owed again")
    p.add_argument("duty"); p.add_argument("--reason", default="")
    js(p); p.set_defaults(func=cmd_duty_reactivate)

    p = ds.add_parser("link", help="point the duty at the tasks implementing it")
    p.add_argument("duty"); p.add_argument("tasks", nargs="+", help="task ids")
    js(p); p.set_defaults(func=cmd_duty_link)

    p = ds.add_parser("why", help="the priority tier and the fact that put the duty there")
    p.add_argument("duty")
    js(p); p.set_defaults(func=cmd_duty_why)

    p = ds.add_parser("unlink", help="stop tracking tasks")
    p.add_argument("duty"); p.add_argument("tasks", nargs="+")
    js(p); p.set_defaults(func=cmd_duty_unlink)
