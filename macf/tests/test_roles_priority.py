"""Priority tiers and the calendar, held to the roles policy's tables.

Each tier has a positive and a negative case; every placement carries the
fact that produced it. Cadence expansion is checked across a month end and a
DST change (a day is a day). The .ics is checked for structure and RRULEs.
"""
import json
import re
from datetime import date, datetime, timedelta

import pytest

from macf.roles import calendar as cal
from macf.roles import priority as pr
from macf.roles.models import Duty, Role, Update


def _u(at="2026-09-11T09:00:00", **kw):
    return Update(breadcrumb="s_x/c_1/p_x/t_1", at=at, **kw)


def _duty(title, **kw):
    kw.setdefault("id", "%06x" % (abs(hash(title)) % 0xFFFFFF))
    kw.setdefault("role_id", "abc123")
    kw.setdefault("updates", [_u(kind="declare")])
    return Duty(title=title, **kw)


NOW = datetime(2026, 9, 12, 9, 0)


# ---- tiers: one positive and one negative case each ---------------------------

def test_overdue_bare_date_is_late_only_after_the_day_ends():
    d = _duty("x", due=datetime(2026, 9, 11), horizon="1d")
    assert pr.classify(d, [d], NOW).tier == pr.OVERDUE
    assert "1d past" in pr.classify(d, [d], NOW).reason
    still_that_day = datetime(2026, 9, 11, 23, 0)
    assert pr.classify(d, [d], still_that_day).tier == pr.DUE_SOON
    assert pr.duty_mark(pr.classify(d, [d], still_that_day), still_that_day) == "⏰ today"


def test_due_soon_opens_at_due_minus_horizon_measured_from_the_days_start():
    d = _duty("board plan", due=datetime(2026, 9, 15), horizon="3d")
    p = pr.classify(d, [d], NOW)
    assert p.tier == pr.DUE_SOON and p.entered == datetime(2026, 9, 12, 0, 0)
    assert "horizon 3d" in p.reason and "3d left" in p.reason
    assert pr.duty_mark(p, NOW) == "⏳3d"
    before = datetime(2026, 9, 11, 23, 59)
    q = pr.classify(d, [d], before)
    assert q.tier == pr.NORMAL and pr.duty_mark(q, before) == ""


def test_timed_due_uses_the_time():
    d = _duty("call", due=datetime(2026, 9, 12, 14, 0), horizon="2h")
    assert pr.classify(d, [d], datetime(2026, 9, 12, 11, 0)).tier == pr.NORMAL
    assert pr.classify(d, [d], datetime(2026, 9, 12, 12, 30)).tier == pr.DUE_SOON
    assert pr.classify(d, [d], datetime(2026, 9, 12, 14, 1)).tier == pr.OVERDUE


def test_blocking_outranks_important_and_blocked_sinks():
    a = _duty("rubric", id="aaaaaa")
    b = _duty("post grades", id="bbbbbb", depends_on=["aaaaaa"], importance="critical")
    c = _duty("welcome", id="cccccc", importance="high")
    placed = {p.duty.id: p for p in pr.rank([a, b, c], NOW)}
    assert placed["aaaaaa"].tier == pr.BLOCKING and "bbbbbb" in placed["aaaaaa"].reason
    assert placed["cccccc"].tier == pr.IMPORTANT and placed["cccccc"].reason == "importance high"
    assert placed["bbbbbb"].tier == pr.BLOCKED and "aaaaaa" in placed["bbbbbb"].reason
    assert [p.duty.id for p in pr.rank([a, b, c], NOW)] == ["aaaaaa", "cccccc", "bbbbbb"]
    # once the blocker is done, the dependent is no longer blocked and the blocker no longer blocking
    a_done = _duty("rubric", id="aaaaaa", state="done", evidence=["7"])
    placed = {p.duty.id: p for p in pr.rank([a_done, b], NOW, include_done=True)}
    assert placed["bbbbbb"].tier == pr.IMPORTANT and placed["aaaaaa"].tier == pr.DONE


def test_normal_orders_by_least_recently_serviced_and_done_is_hidden_by_default():
    old = _duty("old", id="aaaaaa", updates=[_u("2026-09-01T09:00:00", kind="declare")])
    new = _duty("new", id="bbbbbb", updates=[_u("2026-09-10T09:00:00", kind="declare")])
    done = _duty("done", id="cccccc", state="done", evidence=["7"])
    ranked = pr.rank([new, old, done], NOW)
    assert [p.duty.id for p in ranked] == ["aaaaaa", "bbbbbb"]
    assert ranked[0].tier == pr.NORMAL and "last serviced 2026-09-01" in ranked[0].reason
    assert [p.duty.id for p in pr.rank([new, old, done], NOW, include_done=True)][-1] == "cccccc"


def test_ties_within_a_tier_break_by_due_then_importance():
    a = _duty("a", id="aaaaaa", due=datetime(2026, 9, 15), horizon="7d", importance="low")
    b = _duty("b", id="bbbbbb", due=datetime(2026, 9, 14), horizon="7d", importance="low")
    c = _duty("c", id="cccccc", due=datetime(2026, 9, 15), horizon="7d", importance="critical")
    assert [p.duty.id for p in pr.rank([a, b, c], NOW)] == ["bbbbbb", "cccccc", "aaaaaa"]


def test_why_names_tier_and_fact():
    d = _duty("x", due=datetime(2026, 9, 15), horizon="3d")
    line = pr.why(pr.classify(d, [d], NOW))
    assert line.startswith("DUE_SOON") and "entered 2026-09-12 00:00" in line


# ---- cadence ---------------------------------------------------------------------

def test_cadence_occurrences_stop_at_until_and_never_precede_declaration():
    d = _duty("sections", cadence="weekly:tue at 11:45 dur 6h until 2026-12-15", horizon="2d")
    occ = pr.occurrences(d, date(2026, 9, 1), date(2027, 1, 31))
    assert occ[0] == datetime(2026, 9, 15, 11, 45)          # declared 09-11; 09-08 is before that
    assert occ[-1] == datetime(2026, 12, 15, 11, 45)        # until is inclusive
    assert all(o.weekday() == 1 for o in occ) and len(occ) == 14


def test_cadence_expires_from_the_role_when_no_until():
    d = _duty("sections", cadence="weekly:tue", horizon="2d")
    occ = pr.occurrences(d, date(2026, 9, 1), date(2027, 1, 31), role_expires=date(2026, 10, 1))
    assert occ[-1].date() == date(2026, 9, 29)


def test_monthly_skips_short_months_and_crosses_year_end():
    d = _duty("report", cadence="monthly:31", horizon="3d", updates=[_u("2026-01-01T09:00:00", kind="declare")])
    occ = [o.date() for o in pr.occurrences(d, date(2026, 1, 1), date(2026, 6, 30))]
    assert occ == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]
    d2 = _duty("m", cadence="monthly:15", horizon="1d", updates=[_u("2026-11-01T09:00:00", kind="declare")])
    occ2 = [o.date() for o in pr.occurrences(d2, date(2026, 11, 1), date(2027, 2, 1))]
    assert occ2 == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


def test_weekly_across_a_dst_change_keeps_the_wall_clock_time():
    # US DST ends 2026-11-01; the Tuesday before and after must both be 11:45 local.
    d = _duty("sections", cadence="weekly:tue at 11:45", horizon="2d", updates=[_u("2026-10-01T09:00:00", kind="declare")])
    occ = pr.occurrences(d, date(2026, 10, 25), date(2026, 11, 8))
    assert [o.time().isoformat(timespec="minutes") for o in occ] == ["11:45", "11:45"]
    assert [o.date() for o in occ] == [date(2026, 10, 27), date(2026, 11, 3)]


def test_current_occurrence_is_the_missed_one_until_the_next_arrives():
    d = _duty("sections", cadence="weekly:tue at 11:45", horizon="2d")
    # Tue 09-15 11:45 missed; on Wed 09-16 it is the current (OVERDUE) occurrence
    assert pr.current_occurrence(d, datetime(2026, 9, 16, 8, 0)) == datetime(2026, 9, 15, 11, 45)
    assert pr.classify(d, [d], datetime(2026, 9, 16, 8, 0)).tier == pr.OVERDUE
    # on Tue 09-22 12:00 the new occurrence has arrived: 09-15 becomes a missed cell, 09-22 ranks
    assert pr.current_occurrence(d, datetime(2026, 9, 22, 12, 0)) == datetime(2026, 9, 22, 11, 45)
    # a done_on note closes an occurrence: the next one ranks
    d2 = _duty("sections", cadence="weekly:tue at 11:45", horizon="2d",
               updates=[_u(kind="declare"), _u("2026-09-15T18:00:00", kind="occurrence", done_on=date(2026, 9, 15))])
    assert pr.current_occurrence(d2, datetime(2026, 9, 16, 8, 0)) == datetime(2026, 9, 22, 11, 45)
    assert pr.classify(d2, [d2], datetime(2026, 9, 16, 8, 0)).tier == pr.NORMAL
    assert pr.classify(d2, [d2], datetime(2026, 9, 20, 12, 0)).tier == pr.DUE_SOON


# ---- roles among themselves and the role line's mark --------------------------

def test_roles_order_focused_first_then_most_urgent_duty():
    r1 = Role(id="aaaaa1", title="Quiet", tenure_start=date(2026, 9, 1))
    r2 = Role(id="aaaaa2", title="Busy", tenure_start=date(2026, 9, 1))
    quiet = [_duty("q", id="d00001", role_id="aaaaa1")]
    busy = [_duty("b", id="d00002", role_id="aaaaa2", due=datetime(2026, 9, 10), horizon="1d")]
    order = [r.id for r, _ in pr.rank_roles([(r1, quiet), (r2, busy)], at=NOW)]
    assert order == ["aaaaa2", "aaaaa1"]
    order = [r.id for r, _ in pr.rank_roles([(r1, quiet), (r2, busy)], focused_id="aaaaa1", at=NOW)]
    assert order == ["aaaaa1", "aaaaa2"]


def test_most_urgent_mark_and_review_mark():
    assert pr.most_urgent_mark(["", "⏳3d", "🔴 OVERDUE 2d", "⏰ today"]) == "🔴 OVERDUE 2d"
    assert pr.most_urgent_mark(["⏳3d", "⏳1d"]) == "⏳1d"
    assert pr.most_urgent_mark(["🔴 OVERDUE 2d", "🔴 OVERDUE 5d"]) == "🔴 OVERDUE 5d"
    assert pr.most_urgent_mark(["", ""]) == ""
    r = Role(id="aaaaa1", title="T", tenure_start=date(2026, 9, 1), review_by=date(2026, 12, 15), review_horizon="14d")
    assert pr.review_mark(r, datetime(2026, 12, 5)) == "⏳10d"
    assert pr.review_mark(r, datetime(2026, 11, 1)) == ""
    assert pr.review_mark(r, datetime(2026, 12, 17)) == "🔴 OVERDUE 2d"


# ---- calendar ---------------------------------------------------------------------

@pytest.fixture
def semester():
    role = Role(id="aaaaa1", title="Lab Course Assistant", icon="🎓", tenure_start=date(2026, 9, 11),
                expires=date(2026, 12, 15), review_by=date(2026, 12, 15), review_horizon="14d")
    duties = [
        _duty("board plan", id="d00001", role_id="aaaaa1", due=datetime(2026, 9, 15), horizon="3d"),
        _duty("sections", id="d00002", role_id="aaaaa1", cadence="weekly:tue at 11:45 dur 6h", horizon="2d",
              updates=[_u(kind="declare"), _u("2026-09-15T18:00:00", kind="occurrence", done_on=date(2026, 9, 15))]),
        _duty("done thing", id="d00003", role_id="aaaaa1", state="done", evidence=["7"]),
    ]
    return role, duties


def test_events_walk_roles_and_duties_with_done_and_missed(semester):
    role, duties = semester
    at = datetime(2026, 9, 23, 9, 0)
    evs = cal.events([(role, duties)], date(2026, 9, 14), date(2026, 12, 16), at)
    kinds = [(e.when.date(), e.kind, e.title, e.done, e.missed) for e in evs]
    assert kinds[0] == (date(2026, 9, 15), "due", "board plan", False, False)
    assert kinds[1] == (date(2026, 9, 15), "occurrence", "sections", True, False)
    assert kinds[2] == (date(2026, 9, 22), "occurrence", "sections", False, True)
    assert kinds[3] == (date(2026, 9, 29), "occurrence", "sections", False, False)
    assert {k[1] for k in kinds if k[0] == date(2026, 12, 15)} == {"review", "expires", "occurrence"}
    assert all(e.title != "done thing" for e in evs)
    assert evs[-1].when.date() == date(2026, 12, 15)
    assert [e.when.date() for e in evs if e.kind == "occurrence"][-1] == date(2026, 12, 15)


def test_agenda_and_grid_render(semester):
    role, duties = semester
    at = datetime(2026, 9, 12, 9, 0)
    evs = cal.events([(role, duties)], date(2026, 9, 12), date(2026, 9, 25), at)
    text = cal.agenda(evs, date(2026, 9, 12), date(2026, 9, 25), at)
    assert "Tue 09-15" in text and "board plan" in text and "⏳3d" in text
    assert "11:45 +6h" in text and "✔ sections" in text
    g = cal.grid(evs, date(2026, 9, 12), date(2026, 9, 25), at)
    rows = g.splitlines()
    assert rows[0].startswith("┌") and rows[-1].startswith("└")
    assert all(len(r) == len(rows[0]) for r in rows[:3])       # frame lines align
    assert "•12 Sep" in g and "🎓 board plan" in g and "+1 more" in g


def test_ics_is_structurally_valid_with_rrules(semester, tmp_path):
    role, duties = semester
    s = cal.ics([(role, duties)], date(2026, 9, 12), date(2026, 9, 25), datetime(2026, 9, 12, 9, 0))
    assert s.startswith("BEGIN:VCALENDAR\r\n") and s.endswith("END:VCALENDAR\r\n")
    blocks = re.findall(r"BEGIN:VEVENT\r\n(.*?)END:VEVENT", s, re.S)
    assert len(blocks) == 4                                     # review, expires, board plan, sections
    for b in blocks:
        assert "UID:" in b and "DTSTAMP:" in b and "DTSTART" in b and "SUMMARY:" in b
    rr = [b for b in blocks if "RRULE:" in b]
    assert len(rr) == 1
    assert "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261215T235959" in rr[0]
    assert "DTSTART:20260915T114500" in rr[0] and "DTEND:20260915T174500" in rr[0]
    assert "DTSTART;VALUE=DATE:20260915" in s                    # bare-date due is an all-day event
    assert "done thing" not in s


def test_window_defaults():
    at = datetime(2026, 9, 12, 9, 0)
    assert cal.window(at=at) == (date(2026, 9, 12), date(2026, 9, 25))
    assert cal.window(weeks=1, at=at) == (date(2026, 9, 12), date(2026, 9, 18))
    assert cal.window(start=date(2026, 10, 1), end=date(2026, 10, 3), at=at) == (date(2026, 10, 1), date(2026, 10, 3))


# ---- the CLI verbs, with the clock pinned ------------------------------------------

@pytest.fixture
def cli_store(tmp_path, monkeypatch):
    from macf.roles import RoleStore
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "roles"))
    monkeypatch.setenv("MACF_ROLES_NOW", "2026-09-12T09:00")
    store = RoleStore()
    role, folder = store.create_role("Lab Course Assistant", icon="🎓", expires=date(2026, 12, 15))
    store.add_duty(role, folder, "board plan", due=datetime(2026, 9, 15), horizon="3d", why="afternoon draft")
    store.add_duty(role, folder, "sections", cadence="weekly:tue at 11:45 dur 6h", horizon="2d", why="prep")
    store.add_duty(role, folder, "rubric")
    return store


def _run(argv):
    import argparse
    from macf.roles.cli import add_role_parser
    p = argparse.ArgumentParser()
    add_role_parser(p.add_subparsers(dest="cmd"))
    args = p.parse_args(argv)
    return args.func(args)


def test_cli_why_and_show_order_and_marks(cli_store, capsys):
    assert _run(["role", "duty", "why", "board", "--json"]) == 0
    w = json.loads(capsys.readouterr().out)
    assert w["tier"] == "DUE_SOON" and w["mark"] == "⏳3d" and w["position"] == 1 and w["of"] == 3
    assert _run(["role", "show", "lab"]) == 0
    out = capsys.readouterr().out.splitlines()
    duty_lines = [l for l in out if "📌" in l]
    assert "board plan" in duty_lines[0] and "⏳3d" in duty_lines[0]
    assert "sections" in duty_lines[1] and "rubric" in duty_lines[2]
    assert "⏳3d" in out[0], out[0]                      # the role line carries the most urgent mark


def test_cli_calendar_agenda_grid_json_ics(cli_store, capsys, tmp_path):
    assert _run(["role", "calendar", "--weeks", "1"]) == 0
    out = capsys.readouterr().out
    assert "2026-09-12 → 2026-09-18" in out and "board plan" in out and "sections" in out
    assert _run(["role", "calendar", "--from", "2026-09-14", "--to", "2026-09-20", "--grid"]) == 0
    assert "┌" in capsys.readouterr().out
    assert _run(["role", "calendar", "--weeks", "2", "--json"]) == 0
    j = json.loads(capsys.readouterr().out)
    assert [e["title"] for e in j["events"]][:2] == ["board plan", "sections"]
    ics_path = tmp_path / "out.ics"
    assert _run(["role", "calendar", "--ics", str(ics_path)]) == 0
    assert ics_path.read_text().startswith("BEGIN:VCALENDAR")
    assert _run(["role", "calendar", "--from", "2026-09-20", "--to", "2026-09-10"]) == 1
    assert "before" in capsys.readouterr().out
