"""The mask ENFORCED at delivery, not merely computable beside it.

Phase 4's primitive was built, mutation-tested and wired to nothing. A control
with no caller is a defect this corpus already names three times, and shipped
once. These tests exist so the wiring cannot quietly come loose again: they
exercise the mask through `adapter.deliver`, which is the only path a real
notice takes.

The phase criterion, stated as a test: an agent in a declared critical section
receives operator input and defers everything else; deferred notices arrive
afterwards, once each.
"""
import json
import os
import time

import pytest

from macf.notify import adapter, masking
from macf.notify.notice import Notice, amail_notice


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    sessions = tmp_path / ".claude" / "sessions"
    sessions.mkdir(parents=True)
    return sessions


def operator_notice(arrival_id):
    """A notice about the agent ITSELF -- the floor's first instance."""
    return Notice(source="operator", arrival_id=arrival_id, pointer="check your terminal")


# ---- the criterion ---------------------------------------------------------

def test_a_declared_critical_section_defers_the_world(runtime, home):
    """The world waits. Note there is no credential in this fixture: a deferral
    must not need one, or a momentarily unreachable session would LOSE the
    notice instead of holding it."""
    masking.declare_critical("mid-proof", 60)
    result = adapter.deliver(os.getpid(), amail_notice("world-1", count=1))
    assert result.outcome == adapter.DEFERRED
    assert "mid-proof" in result.detail


def test_the_same_section_still_admits_the_OPERATOR(runtime, home):
    """An agent may decline to be told about the world; not about itself.

    This reaches the credential check and fails there -- which is the proof it
    was NOT deferred. A refusal for a missing credential means the notice got
    past the mask.
    """
    masking.declare_critical("mid-proof", 60)
    result = adapter.deliver(os.getpid(), operator_notice("self-1"))
    assert result.outcome != adapter.DEFERRED
    assert result.outcome == adapter.REFUSED_NO_CREDENTIAL


def test_deferred_notices_arrive_AFTERWARDS_once_each(runtime, home, monkeypatch):
    """The second half of the criterion, and the half a drop would still pass."""
    masking.declare_critical("mid-proof", 60)
    for i in range(3):
        assert adapter.deliver(os.getpid(), amail_notice(f"w-{i}", count=1)).outcome == adapter.DEFERRED

    sent = []
    monkeypatch.setattr(adapter, "deliver", _recording_deliver(sent), raising=True)
    # Section over.
    masking.clear_declaration()
    mask = masking.load(None)
    adapter._flush_deferred(os.getpid(), mask)

    assert sorted(n.arrival_id for n in sent) == ["w-0", "w-1", "w-2"]
    # ONCE each: a second flush has nothing left to give.
    sent.clear()
    adapter._flush_deferred(os.getpid(), masking.load(None))
    assert sent == []


def _recording_deliver(sink):
    def fake(pid, notice, bypass_mask=False):
        sink.append(notice)
        return adapter.DeliveryResult(adapter.DELIVERED, pid, notice.arrival_id)
    return fake


# ---- the cross-process property the wiring exists for ----------------------

def test_a_declaration_written_by_ONE_process_is_honoured_by_ANOTHER(runtime, home):
    """The whole point of persisting it.

    `masking.load` is what a notifier calls; it shares no memory with whatever
    declared the section. Reading it back through `load` rather than through the
    object returned by `declare_critical` is the difference between testing a
    variable and testing the mechanism.
    """
    masking.declare_critical("compaction", 30)
    fresh = masking.load(None)
    assert fresh.critical is not None
    assert fresh.critical.label == "compaction"
    assert fresh.critical.active()


def test_a_loaded_mask_carries_NO_predicate_and_does_not_pretend_to(runtime, home):
    """A callable cannot be serialized. A mask that silently lost its predicate
    would look like a filter and behave like an open gate, so the absence is
    explicit."""
    masking.declare_critical("x", 30)
    assert masking.load(None).predicate is None


def test_a_lapsed_section_stops_deferring_without_anyone_clearing_it(runtime, home):
    """It lapses on its own. A section whose end depends on the agent coming
    back to cancel it is a mute that survives the agent being wedged."""
    masking.declare_critical("brief", 60, now=time.time() - 120)
    result = adapter.deliver(os.getpid(), amail_notice("after-lapse", count=1))
    assert result.outcome != adapter.DEFERRED


# ---- scoping ---------------------------------------------------------------

def test_the_deferred_QUEUE_is_per_conversation_not_per_uid(runtime):
    """Two conversations of one agent must not drink from one queue.

    Unscoped, a notice deferred by A is released into B -- delivered to a session
    that never deferred it, and never delivered to the one that did.
    """
    a = masking.Mask(session_id="sess-a")
    b = masking.Mask(session_id="sess-b")
    a.defer(amail_notice("only-a", count=1))

    assert [h["arrival_id"] for h in a.deferred()] == ["only-a"]
    assert b.deferred() == [], "conversation B can see A's held notice"
    assert a.deferred_path() != b.deferred_path()


def test_the_DECLARATION_is_per_conversation_too(runtime):
    masking.declare_critical("only-a", 60, session_id="sess-a")
    assert masking.load("sess-a").critical is not None
    assert masking.load("sess-b").critical is None


# ---- failure directions ----------------------------------------------------

def test_a_MALFORMED_declaration_delivers_rather_than_silences(runtime, home, capsys):
    """Fail OPEN. An unparseable byte sequence must not mute an agent
    indefinitely with nobody able to say why."""
    masking.declaration_path(None).write_text("{not json")
    result = adapter.deliver(os.getpid(), amail_notice("malformed", count=1))
    assert result.outcome != adapter.DEFERRED
    assert "delivering as if unmasked" in capsys.readouterr().err


def test_VALID_json_that_is_not_an_OBJECT_is_not_a_section(runtime, home):
    """A separate branch from malformed bytes, and it needs its own test.

    `"{not json"` never reaches the shape check -- the decoder rejects it first.
    Only well-formed JSON of the wrong TYPE exercises this, and without a case
    like it the shape check can be deleted with every test still green. Measured:
    it was.
    """
    masking.declaration_path(None).write_text("[1, 2, 3]")
    assert masking.load(None).critical is None
    result = adapter.deliver(os.getpid(), amail_notice("list-decl", count=1))
    assert result.outcome != adapter.DEFERRED


def test_a_declaration_with_no_EXPIRY_is_not_a_section(runtime, home):
    """An expiry is what makes a section lapse. Without one it is a permanent
    mute, so it is refused rather than honoured forever."""
    masking.declaration_path(None).write_text(json.dumps({"label": "forever"}))
    assert masking.load(None).critical is None


def test_a_section_of_zero_seconds_is_REFUSED_rather_than_recorded(runtime, capsys):
    """An already-expired section masks nothing while reading like it does."""
    assert masking.declare_critical("useless", 0) is None
    assert "masks nothing" in capsys.readouterr().err
    assert masking.load(None).critical is None


def test_a_deferral_that_could_not_be_HELD_is_announced_as_a_loss(runtime, home, monkeypatch, capsys):
    """A failed write is a DROP. Reporting it as a deferral would promise a
    later delivery that can never happen."""
    masking.declare_critical("mid-proof", 60)
    monkeypatch.setattr(masking.Mask, "defer", lambda self, notice, now=None: False)
    result = adapter.deliver(os.getpid(), amail_notice("lost", count=1))
    assert result.outcome == adapter.DEFERRED
    assert "now LOST" in capsys.readouterr().err


def test_release_deferred_honours_a_section_that_is_STILL_active(runtime, home):
    """A poller must not undo the mask it is polling around."""
    masking.declare_critical("mid-proof", 60)
    adapter.deliver(os.getpid(), amail_notice("held", count=1))
    assert adapter.release_deferred(os.getpid(), session_id=None) == []
    assert len(masking.load(None).deferred()) == 1


def test_a_released_notice_is_not_re_held_by_the_section_that_held_it(runtime, home):
    """`bypass_mask` on the way back in. Without it the release path re-decides each
    notice, the section holds it again, and "deferred" quietly means "never".

    The REAL deliver runs here. Stubbing it would make this vacuous -- `bypass_mask`
    only has an observable effect if the code it gates actually executes, and a
    recording stub skips exactly that code. Measured: the stubbed version of this
    test passed against a mutant that removed `bypass_mask`.

    The section is deliberately still ACTIVE during the flush, which is what
    makes the two behaviours differ: with bypass_mask the notice passes the mask and
    reaches the credential check, without it the same section holds it again and
    the queue refills.
    """
    masking.declare_critical("mid-proof", 60)
    assert adapter.deliver(os.getpid(), amail_notice("once", count=1)).outcome == adapter.DEFERRED
    assert len(masking.load(None).deferred()) == 1

    results = adapter._flush_deferred(os.getpid(), masking.load(None))

    # The property: the notice PASSED the still-active section rather than being
    # re-decided by it. It got as far as the credential check, which is beyond
    # the mask.
    assert results and results[0].outcome != adapter.DEFERRED, \
        "the released notice was re-held by the section that held it"

    # AND IT IS STILL ON DISK, which is the ira-76 fix rather than a regression.
    # Delivery refused here (no credential for this pid), so the entry is RETAINED
    # for the next poll instead of being destroyed. Under the previous design
    # `release` cleared on read and this queue would be empty -- the notice gone,
    # undelivered, on an entirely ordinary refusal. Retention is the point.
    assert len(masking.load(None).deferred()) == 1, \
        "an unconfirmed delivery must stay held, not be cleared on read"
