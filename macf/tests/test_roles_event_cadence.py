"""An ``on:<event>`` cadence: a duty that recurs on an event in the agent's own log (#389).

Some standing obligations recur on a state change, not on the calendar: before a
rebuild, after a host reboot, after a compaction. Without this grammar they could
only be recorded untimed, indistinguishable from a one-shot duty.
"""
import time
from datetime import date, datetime, timedelta

import pytest

from macf.agent_events_log import CYCLE_BOUNDARY_EVENT, append_event
from macf.roles import RoleStore
from macf.roles import calendar as cal
from macf.roles.cadence import CadenceError, parse_cadence
from macf.roles.priority import DUE_SOON, NORMAL, OVERDUE, classify, duty_mark
from macf.roles.store import RoleError


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "roles"))
    monkeypatch.delenv("MACF_ROLES_NOW", raising=False)
    return RoleStore()


@pytest.fixture
def role(store):
    return store.create_role("Harbor Custodian", icon="⚓", expires=date(2027, 12, 31),
                             review_by=date(2027, 12, 31), review_horizon="14d")


def _place(duty, at=None):
    return classify(duty, [duty], at or datetime.now() + timedelta(seconds=1))


def _event(name):
    time.sleep(0.01)                     # the declaration and the event must not share an instant
    append_event(name, {})
    time.sleep(0.01)


def test_grammar():
    cad = parse_cadence("on:host_rebuild until 2027-01-31")
    assert (cad.kind, cad.event, cad.until) == ("event", "host_rebuild", date(2027, 1, 31))
    for bad in ("on:", "on:Host-Rebuild", "on:host_rebuild at 09:00", "on:host_rebuild dur 1h"):
        with pytest.raises(CadenceError):
            parse_cadence(bad)


def test_an_event_duty_needs_no_horizon_but_a_calendar_one_still_does(store, role):
    r, folder = role
    d, _ = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild")
    assert d.horizon is None
    with pytest.raises(RoleError):
        store.add_duty(r, folder, "weekly sweep", cadence="weekly:mon")


def test_the_event_opens_an_occurrence_and_a_done_on_note_closes_it(store, role):
    r, folder = role
    d, path = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild")
    assert _place(d).tier == NORMAL                         # nothing recorded yet
    _event("host_rebuild")
    p = _place(d)
    assert p.tier == DUE_SOON and "on host_rebuild" in p.reason
    assert duty_mark(p) == "⏰ on host_rebuild"
    store.note_duty(d, path.parent, "checked", done_on=date.today())
    d = store.find_duty(d.id)[0]
    assert _place(d).tier == NORMAL                         # closed
    _event("host_rebuild")                                  # the next occurrence
    assert _place(store.find_duty(d.id)[0]).tier == DUE_SOON


def test_a_note_without_done_on_services_but_does_not_close(store, role):
    r, folder = role
    d, path = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild")
    _event("host_rebuild")
    store.note_duty(d, path.parent, "started")
    assert _place(store.find_duty(d.id)[0]).tier == DUE_SOON


def test_a_horizon_is_the_grace_before_late(store, role):
    r, folder = role
    d, _ = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild",
                          horizon="1h", why="the volumes must be checked before the next job")
    _event("host_rebuild")
    assert _place(d).tier == DUE_SOON
    late = _place(d, datetime.now() + timedelta(hours=2))
    assert late.tier == OVERDUE and late.entered is not None


def test_an_event_before_the_declaration_is_not_an_occurrence(store, role):
    r, folder = role
    _event("host_rebuild")
    d, _ = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild")
    assert _place(d).tier == NORMAL


def test_a_compaction_is_an_event_like_any_other(store, role):
    """on:compaction_detected is the boundary itself, so it is always in a
    cycle-scoped read: the one event this cadence can never lose."""
    r, folder = role
    d, _ = store.add_duty(r, folder, "re-read the charter", cadence="on:" + CYCLE_BOUNDARY_EVENT)
    _event(CYCLE_BOUNDARY_EVENT)
    assert _place(d).tier == DUE_SOON


def test_the_calendar_shows_an_occurrence_when_its_event_happened(store, role):
    r, folder = role
    d, _ = store.add_duty(r, folder, "check the volumes", cadence="on:host_rebuild")
    _event("host_rebuild")
    today = date.today()
    evs = cal.events([(r, [d])], today - timedelta(days=1), today + timedelta(days=1))
    mine = [e for e in evs if e.duty is not None and e.duty.id == d.id]
    assert len(mine) == 1 and mine[0].when.date() == today and not mine[0].done
    assert "⏰ on host_rebuild" in cal.agenda(evs, today - timedelta(days=1), today + timedelta(days=1))
