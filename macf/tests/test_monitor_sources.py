"""The second input class: a store is a directory, not a stream of lines.

The monitor's detectors assume the world arrives as lines with a cursor. A mail
store has neither. These tests are about that generalisation and about the
properties it must not lose on the way.
"""
import pytest

from macf.transcript_monitor import daemon
from macf.transcript_monitor.sources import StoreSource


@pytest.fixture
def store(tmp_path):
    d = tmp_path / "pickup"
    d.mkdir()
    return d


def _arrive(store, name, body="From: someone\nSubject: hostile\n\nbody"):
    (store / name).write_text(body)


def test_priming_adopts_existing_mail_so_a_restart_announces_nothing(store):
    """A restart must not replay what is already sitting in the store.

    Replay would deliver a burst of stale wakes and re-notify mail the agent may
    already have read. What was missed while down is recovered from the gap
    record instead.
    """
    _arrive(store, "old-1.eml")
    _arrive(store, "old-2.eml")
    src = StoreSource(store).prime()
    assert src.poll() == []


def test_a_new_arrival_produces_one_detection_carrying_a_COUNT_and_no_names(store):
    src = StoreSource(store).prime()
    _arrive(store, "new-1.eml")
    detections = src.poll()
    assert len(detections) == 1
    data = detections[0].data
    assert data["count"] == 1
    assert "new-1.eml" not in repr(data), "a filename must not travel with the event"


def test_a_burst_is_ONE_detection_not_one_per_message(store):
    """Ten arrivals are one thing the agent needs to know and one store to read."""
    src = StoreSource(store).prime()
    for i in range(10):
        _arrive(store, f"burst-{i}.eml")
    detections = src.poll()
    assert len(detections) == 1
    assert detections[0].data["count"] == 10


def test_an_unchanged_store_is_not_an_event_however_much_mail_it_holds(store):
    """Edge-triggered on arrival, never level-triggered on state."""
    src = StoreSource(store).prime()
    _arrive(store, "one.eml")
    assert len(src.poll()) == 1
    for _ in range(20):
        assert src.poll() == [], "unread mail is not a new arrival"


def test_the_source_never_opens_a_message(store, monkeypatch):
    """Zero-bandwidth made STRUCTURAL rather than maintained.

    A source that cannot read a body cannot leak one, so the property survives
    edits by authors who never read the policy.
    """
    _arrive(store, "hostile.eml")
    src = StoreSource(store).prime()
    _arrive(store, "hostile-2.eml")

    real_open = open

    def forbidden(*a, **k):
        raise AssertionError(f"the source opened a file: {a!r}")

    monkeypatch.setattr("builtins.open", forbidden)
    detections = src.poll()
    monkeypatch.setattr("builtins.open", real_open)
    assert len(detections) == 1


def test_an_unreadable_store_is_NOT_reported_as_an_empty_one(store, monkeypatch, capsys):
    """'No mail' and 'cannot tell' are different facts.

    Treating the second as the first reports an unreadable store as a quiet one,
    which is the silence this whole subsystem exists to end.
    """
    src = StoreSource(store).prime()

    def denied(path):
        raise PermissionError("nope")

    monkeypatch.setattr("os.listdir", denied)
    assert src.poll() == []
    assert src.poll_failures >= 1
    assert "arrivals cannot be noticed" in capsys.readouterr().err


def test_a_missing_store_is_empty_rather_than_broken(tmp_path):
    """Polling ahead of provisioning is ordinary, not a fault."""
    src = StoreSource(tmp_path / "not-created-yet").prime()
    assert src.poll() == []
    assert src.poll_failures == 0


def test_a_redelivered_name_is_a_new_arrival_not_a_permanent_silence(store):
    """Departed entries leave the ledger, or a drained-then-resent message would
    never be announced again."""
    src = StoreSource(store).prime()
    _arrive(store, "again.eml")
    assert len(src.poll()) == 1
    (store / "again.eml").unlink()          # the agent drained it
    assert src.poll() == []
    _arrive(store, "again.eml")             # the sender resent it
    assert len(src.poll()) == 1


def test_the_arrival_id_is_stable_for_a_burst_and_distinct_between_bursts(store):
    """Idempotency needs the same burst to key the same, and a different one not to."""
    a = StoreSource(store).prime()
    _arrive(store, "x.eml")
    first = a.poll()[0].data["arrival_id"]

    b = StoreSource(store)
    b._primed = True
    b._seen = set()
    assert b.poll()[0].data["arrival_id"] == first, "same contents, same id"

    _arrive(store, "y.eml")
    c = StoreSource(store)
    c._primed = True
    c._seen = {"x.eml"}
    assert c.poll()[0].data["arrival_id"] != first


# ---- the monitor hosting a source ----

def test_the_monitor_polls_sources_and_offers_them_to_sinks(tmp_path, monkeypatch):
    """The generalisation, end to end: a non-line input reaches a sink."""
    emitted = []
    monkeypatch.setattr(daemon, "append_event",
                        lambda name, data: emitted.append((name, data)))
    store = tmp_path / "pickup"
    store.mkdir()
    src = StoreSource(store).prime()
    (store / "m.eml").write_text("x")

    delivered = []
    mon = daemon.TranscriptMonitor(tmp_path / "t.jsonl")
    mon.add_source(src).add_sink(delivered.append)
    mon._poll_sources()

    assert [n for n, _ in emitted] == ["store_arrival_detected"]
    assert len(delivered) == 1
    assert mon.get_stats()["sources"] == 1


def test_a_failing_SINK_does_not_lose_the_EVENT(tmp_path, monkeypatch, capsys):
    """The event log is the forensic record and must not depend on delivery."""
    emitted = []
    monkeypatch.setattr(daemon, "append_event",
                        lambda name, data: emitted.append(name))
    store = tmp_path / "pickup"
    store.mkdir()
    src = StoreSource(store).prime()
    (store / "m.eml").write_text("x")

    def broken(_):
        raise RuntimeError("delivery exploded")

    mon = daemon.TranscriptMonitor(tmp_path / "t.jsonl")
    mon.add_source(src).add_sink(broken)
    mon._poll_sources()

    assert emitted == ["store_arrival_detected"], "the event survives a failed sink"
    assert mon.sink_failures == 1
    assert "event still recorded" in capsys.readouterr().err


def test_a_failing_SOURCE_does_not_stop_the_monitor(tmp_path, capsys):
    """A source is an optional input; the transcript is the primary job."""
    class Exploding:
        def poll(self):
            raise RuntimeError("source exploded")

    mon = daemon.TranscriptMonitor(tmp_path / "t.jsonl")
    mon.add_source(Exploding())
    mon._poll_sources()   # must not raise
    assert mon.source_failures == 1
    assert "monitor continues" in capsys.readouterr().err
