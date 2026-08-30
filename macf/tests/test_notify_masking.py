"""An agent may decline to be told about the WORLD, never about ITSELF.

This is an authorization surface -- who may interrupt whom -- so the tests are
about where enforcement lives, not just what the outcome is. A floor the agent
can lower is not a floor.
"""
import json

import pytest

from macf.notify import masking
from macf.notify.masking import CriticalSection, Mask
from macf.notify.notice import Notice, amail_notice, daemon_notice


@pytest.fixture
def deferred(tmp_path):
    return tmp_path / "deferred.json"


def test_a_notice_about_the_agent_ITSELF_bypasses_the_mask_entirely(deferred):
    """The rule, not a list: a list is where the next case is missing."""
    m = Mask(predicate=lambda n: False, deferred_path=deferred)
    d = m.decide(daemon_notice("x", "check the notifier"))
    assert d.allow is True and d.defer is False
    assert "about the agent itself" in d.reason


def test_the_floor_is_checked_BEFORE_the_predicate_is_consulted(deferred):
    """Ordering IS the control.

    A mask that raises would otherwise swallow a supervision notice, and the
    failure would be silent -- the exact defect this subsystem exists to cure,
    reappearing in the mechanism built to cure it.
    """
    called = []

    def exploding(notice):
        called.append(notice.source)
        raise RuntimeError("mask is broken")

    m = Mask(predicate=exploding, deferred_path=deferred)
    d = m.decide(daemon_notice("x", "the notifier is down"))
    assert d.allow is True
    assert called == [], "the predicate must never even run for a self-notice"


def test_a_BROKEN_mask_fails_OPEN_and_says_so(deferred, capsys):
    """The cost of failing open is an unwanted notice. The cost of failing
    closed is a silence nobody can attribute."""
    m = Mask(predicate=lambda n: 1 / 0, deferred_path=deferred)
    d = m.decide(amail_notice("a", 1))
    assert d.allow is True
    assert "failed open" in d.reason
    assert "must not become a silence" in capsys.readouterr().err


def test_a_critical_section_defers_the_world_and_still_admits_the_self(deferred):
    """The completion criterion: operator input lands, everything else waits."""
    cs = CriticalSection(label="mid-migration", until=10_000.0)
    m = Mask(critical=cs, deferred_path=deferred)

    world = m.decide(amail_notice("a", 1), now=5_000.0)
    assert world.defer is True and world.suppress is False

    mine = m.decide(daemon_notice("b", "instruments down"), now=5_000.0)
    assert mine.allow is True

    op = m.decide(Notice(source="operator", arrival_id="c", pointer="read it"), now=5_000.0)
    assert op.allow is True, "operator input is the first instance of the rule, not an exception"


def test_a_critical_section_LAPSES_on_its_own(deferred):
    """A critical section that outlives its work is a permanent mute nobody
    remembers switching on."""
    cs = CriticalSection(label="short", until=1_000.0)
    m = Mask(critical=cs, deferred_path=deferred)
    assert m.decide(amail_notice("a", 1), now=999.0).defer is True
    assert m.decide(amail_notice("b", 1), now=1_001.0).allow is True


def test_deferred_is_NOT_dropped_and_releases_each_notice_ONCE(deferred):
    m = Mask(deferred_path=deferred)
    m.defer(amail_notice("one", 1))
    m.defer(amail_notice("two", 2))

    released = m.release()
    assert sorted(n.arrival_id for n in released) == ["one", "two"]
    assert m.release() == [], "a released notice must not release again"


def test_deferring_the_same_arrival_twice_holds_it_once(deferred):
    m = Mask(deferred_path=deferred)
    m.defer(amail_notice("same", 1))
    m.defer(amail_notice("same", 1))
    assert len(m.deferred()) == 1


def test_a_released_notice_cannot_carry_more_than_a_live_one(deferred):
    """Reconstructed from stored fields, never replayed verbatim.

    A deferral must not become a channel for content a live notice could not
    carry -- otherwise waiting is a way to smuggle.
    """
    m = Mask(deferred_path=deferred)
    m.defer(amail_notice("a", 3))
    # Someone tampers with the queue on disk.
    held = json.loads(deferred.read_text())
    held[0]["subject"] = "hostile subject"
    held[0]["sender"] = "Dr Evil"
    deferred.write_text(json.dumps(held))

    rendered = m.release()[0].render()
    assert "hostile subject" not in rendered
    assert "Dr Evil" not in rendered


@pytest.mark.parametrize("source", sorted(masking.SELF_SOURCES))
def test_every_self_source_is_unmaskable(source):
    n = Notice(source=source, arrival_id="x", pointer="p")
    assert masking.is_unmaskable(n) is True


def test_an_ordinary_world_source_is_maskable():
    """Both polarities. A floor that covers everything is not a floor."""
    assert masking.is_unmaskable(amail_notice("x", 1)) is False


def test_a_MASK_DECLINE_defers_rather_than_suppresses(deferred):
    """Found by the mutation sweep, not by design, and it is this phase's
    headline promise.

    A critical section deferring was tested; a MASK DECLINE deferring was not.
    The distinction is the whole difference between "not now" and "not ever",
    and an agent that declines a source for the next ten minutes has not asked
    to never hear about it. Suppressing here would make every masked arrival an
    unrecoverable silence.
    """
    m = Mask(predicate=lambda n: False, deferred_path=deferred)
    d = m.decide(amail_notice("a", 1))
    assert d.allow is False
    assert d.defer is True, "declined is 'not now', never 'not ever'"
    assert d.suppress is False
    assert "not dropped" in d.reason


def test_the_three_outcomes_are_actually_distinct(deferred):
    """allow / defer / suppress must not collapse into a bool.

    Two of them mean the notice survives; collapsing them turns a deferral into
    a drop at the first caller that treats `not allow` as `gone`.
    """
    m = Mask(predicate=lambda n: False, deferred_path=deferred)
    allowed = m.decide(daemon_notice("s", "p"))
    declined = m.decide(amail_notice("w", 1))
    assert (allowed.allow, allowed.defer, allowed.suppress) == (True, False, False)
    assert (declined.allow, declined.defer, declined.suppress) == (False, True, False)
