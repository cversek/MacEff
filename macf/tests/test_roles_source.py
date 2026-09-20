"""DutyTierSource: the out-of-session duty nag as a polled Source.

Edge-triggered on tier entry, primed silently, names only, and shaped for
the monitor's contract so it can be hosted by whatever process is long-lived.
"""
from datetime import date, datetime, timedelta

import pytest

from macf.notify.contracts import validate_source
from macf.roles import RoleStore
from macf.roles.source import EVENT, DutyTierSource


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "roles"))
    # Every test below polls at explicit 2026-09 datetimes. The declarations
    # the fixtures write must PRECEDE those dates, or the "never before the
    # duty was declared" floor drops the occurrences under test -- which is
    # exactly what happened once the wall clock passed 2026-09-15 (#397).
    # Pin the clock the store stamps with; the poll times stay explicit. The
    # date is chosen, not arbitrary: after Tue 09-08 (so a weekly:tue duty has
    # no undone earlier occurrence to be OVERDUE) and before the 2d horizon of
    # Tue 09-15 opens -- the same instant test_roles_priority pins.
    monkeypatch.setenv("MACF_ROLES_NOW", "2026-09-12T09:00")
    return RoleStore()


def test_the_store_stamps_with_the_same_clock_the_tiers_read(store, monkeypatch):
    """The regression test #397 was missing: MACF_ROLES_NOW must freeze the
    clock declarations are WRITTEN with, not only the one tiers READ. A store
    that stamps from the wall clock passes every pinned test until the wall
    clock overtakes the pinned dates, then fails all of them at once."""
    from macf.roles.priority import declared_on
    monkeypatch.setenv("MACF_ROLES_NOW", "2026-09-12T09:00")
    role, folder = store.create_role("Pinned", icon="🎓")
    d, _ = store.add_duty(role, folder, "sections", cadence="weekly:tue at 11:45", horizon="2d", why="w")
    assert role.tenure_start == date(2026, 9, 12)
    assert declared_on(d) == date(2026, 9, 12)
    # And the consequence the floor has: the very next Tuesday is an occurrence
    # from a pinned declaration, however far the wall clock has moved on.
    src = DutyTierSource(store, prime=False)
    assert [x.data["tier"] for x in src.poll(datetime(2026, 9, 14, 9, 0))] == ["DUE_SOON"]


def test_conforms_to_the_source_contract(store):
    src = DutyTierSource(store)
    assert validate_source(src) is src


def test_first_poll_primes_silently_then_reports_each_crossing_once(store):
    role, folder = store.create_role("Lab Course Assistant", icon="🎓")
    d, _ = store.add_duty(role, folder, "board plan", due=datetime(2026, 9, 15), horizon="3d", why="w")
    src = DutyTierSource(store)
    before = datetime(2026, 9, 11, 9, 0)
    assert src.poll(before) == []                       # primed: nothing due yet
    assert src.poll(before) == []
    inside = datetime(2026, 9, 12, 9, 0)                # horizon opens 09-12 00:00
    got = src.poll(inside)
    assert len(got) == 1 and got[0].event_name == EVENT
    data = got[0].data
    assert data["duty_id"] == d.id and data["tier"] == "DUE_SOON" and data["role_id"] == role.id
    assert data["arrival_id"].startswith(f"roles-{d.id}-DUE_SOON-")
    assert "board plan" not in str(data)                # names only, never the title or body
    assert src.poll(inside) == []                       # same tier, same entry: not reported again
    late = datetime(2026, 9, 16, 9, 0)
    got = src.poll(late)                                # OVERDUE is a new crossing
    assert [x.data["tier"] for x in got] == ["OVERDUE"]
    assert src.poll(late) == []


def test_priming_off_reports_what_is_already_due(store):
    role, folder = store.create_role("L", icon="🎓")
    store.add_duty(role, folder, "late", due=datetime(2026, 9, 10), horizon="1d", why="w")
    src = DutyTierSource(store, prime=False)
    assert [x.data["tier"] for x in src.poll(datetime(2026, 9, 12, 9))] == ["OVERDUE"]


def test_a_service_that_leaves_the_tier_re_arms_the_crossing(store):
    role, folder = store.create_role("L", icon="🎓")
    d, _ = store.add_duty(role, folder, "sections", cadence="weekly:tue at 11:45", horizon="2d", why="w")
    src = DutyTierSource(store, prime=False)
    t = datetime(2026, 9, 14, 9, 0)                     # inside the 2d horizon of Tue 09-15
    assert [x.data["tier"] for x in src.poll(t)] == ["DUE_SOON"]
    store.note_duty(d, folder, "taught", kind="occurrence", done_on=date(2026, 9, 15))
    assert src.poll(datetime(2026, 9, 16, 9, 0)) == [] # closed occurrence: no OVERDUE, key dropped
    assert [x.data["tier"] for x in src.poll(datetime(2026, 9, 21, 9, 0))] == ["DUE_SOON"]  # next Tuesday


def test_paused_roles_are_silent(store):
    role, folder = store.create_role("L", icon="🎓")
    store.add_duty(role, folder, "late", due=datetime(2026, 9, 10), horizon="1d", why="w")
    store.advance_role(role, folder, "paused")
    assert DutyTierSource(store, prime=False).poll(datetime(2026, 9, 12, 9)) == []
