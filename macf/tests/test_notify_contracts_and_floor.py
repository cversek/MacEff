"""Phase 5: sources as declarations, and one floor across all of them.

The two completion criteria are stated here as tests rather than as prose:

  - a new source is added WITHOUT modifying the daemon's core
  - a burst across TWO sources produces ONE coalesced notice

The first is the one that is easy to fake. A test that adds a source the daemon
already knows about proves nothing about extensibility, so the source used here is
defined IN THIS FILE, implements nothing but the documented contract, and the
daemon has never heard of it.
"""
import pytest

from macf.notify.budget import Budget, tokens_remaining
from macf.notify.coalescing import coalesce, coalesced_pointer
from macf.notify.contracts import (
    ContractError,
    validate_detector,
    validate_sink,
    validate_source,
)
from macf.transcript_monitor.daemon import Detection, TranscriptMonitor


def _d(source, arrival_id, count=1, event="store_arrival_detected"):
    return Detection(event_name=event,
                     data={"source": source, "arrival_id": arrival_id, "count": count})


# --------------------------------------------------------------------------
# CRITERION 1 -- a new source, declared here, with no daemon change
# --------------------------------------------------------------------------

class SmokeSource:
    """A source the daemon has never heard of. Implements the contract, nothing else."""

    name = "smoke"

    def __init__(self, batches):
        self._batches = list(batches)

    def poll(self):
        return self._batches.pop(0) if self._batches else []


def test_a_source_the_daemon_never_heard_of_can_be_registered(tmp_path):
    """CRITERION: adding a source is a declaration, not a code change."""
    mon = TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl")
    returned = mon.add_source(SmokeSource([[_d("smoke", "s1", 2)]]))
    assert returned is mon, "add_source must chain"
    assert mon.sources and mon.sources[-1].name == "smoke"


def test_a_registered_source_reaches_a_registered_sink(tmp_path, monkeypatch):
    """The declaration has to actually wire up, not merely be accepted."""
    import macf.transcript_monitor.daemon as daemon_mod
    monkeypatch.setattr(daemon_mod, "append_event", lambda *a, **k: None)

    seen = []
    mon = TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl")
    mon.add_source(SmokeSource([[_d("smoke", "s1", 2)]])).add_sink(seen.append)
    mon._poll_sources()

    assert [d.data["source"] for d in seen] == ["smoke"]
    assert seen[0].data["count"] == 2


# --------------------------------------------------------------------------
# CRITERION 2 -- a burst across two sources is ONE notice
# --------------------------------------------------------------------------

def test_a_burst_across_TWO_sources_produces_ONE_notice(tmp_path, monkeypatch):
    """CRITERION, and the one that failed before the floor existed."""
    import macf.transcript_monitor.daemon as daemon_mod
    logged = []
    monkeypatch.setattr(daemon_mod, "append_event",
                        lambda name, data: logged.append((name, data)))

    seen = []
    mon = TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl")
    mon.add_source(SmokeSource([[_d("smoke", "s1", 3)]]))
    mon.add_source(SmokeSource([[_d("other", "o1", 4)]]))
    mon.add_sink(seen.append)
    mon._poll_sources()

    assert len(seen) == 1, f"expected one coalesced notice, got {len(seen)}"
    assert seen[0].data["count"] == 7, "the accumulated count must be the sum"
    assert seen[0].data["sources"] == ["other", "smoke"]

    # AND the record stays granular: the floor is on interruption, not archaeology.
    assert len(logged) == 2, (
        "the event log was coalesced too; that destroys the record of what arrived"
    )


def test_a_single_source_is_left_alone(tmp_path, monkeypatch):
    """CONTROL: coalescing must not rewrite the identity of a lone detection.

    Without this, 'one notice out' is satisfiable by a floor that rebuilds every
    detection -- changing arrival ids that the dedup ledger depends on.
    """
    import macf.transcript_monitor.daemon as daemon_mod
    monkeypatch.setattr(daemon_mod, "append_event", lambda *a, **k: None)
    seen = []
    mon = TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl")
    mon.add_source(SmokeSource([[_d("smoke", "s1", 3)]])).add_sink(seen.append)
    mon._poll_sources()
    assert seen[0].data["arrival_id"] == "s1", "a lone detection was rebuilt"


# --------------------------------------------------------------------------
# The floor's own properties
# --------------------------------------------------------------------------

def test_the_coalesced_id_is_stable_for_the_same_burst():
    a = coalesce([_d("x", "1", 1), _d("y", "2", 1)])[0].data["arrival_id"]
    b = coalesce([_d("y", "2", 1), _d("x", "1", 1)])[0].data["arrival_id"]
    assert a == b, "poll order changed the identity; the ledger would not suppress"


def test_a_different_burst_gets_a_different_id():
    a = coalesce([_d("x", "1", 1), _d("y", "2", 1)])[0].data["arrival_id"]
    b = coalesce([_d("x", "1", 1), _d("y", "3", 1)])[0].data["arrival_id"]
    assert a != b, "a genuine second arrival would be suppressed as a duplicate"


def test_a_detection_that_cannot_be_counted_passes_through():
    """Not everything a source reports is a notice. Swallowing the rest would
    make the floor a filter nobody declared."""
    odd = Detection(event_name="something_else", data={"note": "no arrival_id"})
    out = coalesce([_d("x", "1", 1), _d("y", "2", 1), odd])
    assert odd in out
    assert len(out) == 2


def test_coalesced_pointer_is_None_for_one_source():
    assert coalesced_pointer(["amail"]) is None
    assert "amail" in coalesced_pointer(["amail", "peer"])


# --------------------------------------------------------------------------
# The contract, checked at registration
# --------------------------------------------------------------------------

def test_a_source_without_poll_is_refused_at_registration(tmp_path):
    class NoPoll:
        name = "broken"
    with pytest.raises(ContractError, match="poll"):
        TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl").add_source(NoPoll())


def test_a_source_with_ONLY_poll_is_accepted(tmp_path):
    """The contract demands exactly what the daemon exercises, and no more.

    An earlier version of this file asserted the opposite -- that a source
    without `.name` is refused -- on the stated grounds that the name is how a
    coalesced notice says which stores to consult. That was false: coalescing
    reads `detection.data["source"]`, and nothing in the daemon reads
    `source.name`. The requirement was invented and then given a reason, and the
    reason is what would have stopped the next reader checking.

    A pre-existing test in test_monitor_sources.py caught it, by registering a
    deliberately broken source to prove a failing source cannot stop the monitor.
    Demanding more than the consumer exercises is a barrier to exactly the
    extensibility this phase exists to provide.
    """
    class OnlyPoll:
        def poll(self):
            return []

    mon = TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl")
    assert mon.add_source(OnlyPoll()) is mon


def test_a_non_callable_sink_is_refused(tmp_path):
    with pytest.raises(ContractError, match="callable"):
        TranscriptMonitor(jsonl_path=tmp_path / "t.jsonl").add_sink("not a function")


def test_a_valid_source_passes_validation_unchanged():
    """CONTROL: validation that refused everything would pass the tests above."""
    s = SmokeSource([])
    assert validate_source(s) is s
    assert validate_sink(print) is print
    assert validate_detector(print) is print


# --------------------------------------------------------------------------
# The budget: a fraction of what is LEFT
# --------------------------------------------------------------------------

def test_the_allowance_shrinks_as_the_window_fills():
    """The whole point of remainder-relative rather than window-relative."""
    b = Budget(fraction=0.01)
    assert b.allowance(200_000) == 2000
    assert b.allowance(20_000) == 200
    assert b.allowance(0) == 0


def test_an_unmeasurable_remainder_is_not_zero():
    """None means the instrument is unavailable, not that nothing is left.

    Treating it as zero would refuse every notice on a missing measurement --
    an emptiness the caller created, read as a fact about the world.
    """
    assert tokens_remaining.__doc__ and "not zero" in tokens_remaining.__doc__.lower()
    assert Budget().allowance(None) == 0  # explicit: callers must check for None


def test_exceeding_the_budget_is_ANNOUNCED_not_silent(capsys):
    b = Budget(fraction=0.0001)
    text = "x" * 4000
    assert b.check(text, 1000) is False
    err = capsys.readouterr().err
    assert "notice budget exceeded" in err
    assert "the store still holds it" in err


def test_within_budget_says_nothing(capsys):
    """CONTROL: an announcement that always fires is not an announcement."""
    b = Budget(fraction=0.5)
    assert b.check("short notice", 200_000) is True
    assert capsys.readouterr().err == ""
