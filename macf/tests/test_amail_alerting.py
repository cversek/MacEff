"""Reproducing the nine-hour alert storm, and proving it cannot recur.

Every component behaved as built. The defects were in what the condition MEANT
and WHO was told, so these tests are about meaning and routing, not mechanism.
"""
import json

import pytest

from macf.amail import alerting as a


@pytest.fixture
def edge(tmp_path):
    return a.EdgeState(tmp_path / "edge.json")


def test_THE_INCIDENT_no_longer_pages(tmp_path):
    """The exact shape: mail in the box of an agent that has NEVER RUN.

    Nine hours, 36 pages, for two messages belonging to agents with no session
    ever started. Wall-clock said 'overdue'; the recipient's own clock said zero.
    """
    f = a.classify_aged_pickup("pa_manny2", "msg.eml", age_s=32400, bound_s=900,
                               liveness=a.INACTIVE)
    assert f.kind == a.EXPECTED_STATE
    assert f.route == a.NOBODY
    assert f.pages is False
    # the signal is DEMOTED, never deleted -- it is how you find an unstarted agent
    assert "agent nobody started" in f.message


def test_a_recipient_that_HAS_been_running_and_has_not_drained_is_a_real_fault(tmp_path):
    """Both polarities. A rule that never fires is not a rule."""
    f = a.classify_aged_pickup("pa_live", "msg.eml", age_s=32400, bound_s=900,
                               liveness=a.ALIVE, active_s=5000)
    assert f.kind == a.RECIPIENT_FAULT
    assert f.route == a.AGENT, "the party that can drain the box is told, not the operator"
    assert f.pages is False, "the operator is the terminus of LAST resort"


def test_raising_the_threshold_does_not_fix_a_wrong_clock(tmp_path):
    """The corollary that makes it a rule rather than a bug.

    Under a wall-clock bound, ANY threshold is eventually exceeded by an agent
    that never runs -- the condition just arrives later. Only the clock changes
    the answer, which is why tuning made the disguise more convincing.
    """
    for bound in (900, 9_000, 90_000, 900_000):
        wall = a.classify_aged_pickup("pa_x", "m.eml", age_s=bound * 10,
                                      bound_s=bound, liveness=a.INACTIVE)
        assert wall.pages is False, f"bound {bound}: still must not page"
        assert wall.kind == a.EXPECTED_STATE


def test_active_time_within_bound_is_not_a_fault_however_old_the_wall_clock(tmp_path):
    f = a.classify_aged_pickup("pa_x", "m.eml", age_s=999_999, bound_s=900,
                               liveness=a.ALIVE, active_s=100)
    assert f.kind == a.EXPECTED_STATE
    assert "clock that matters" in f.message


def test_unmeasurable_liveness_becomes_a_KNOWN_unknown_not_a_silent_pass(tmp_path):
    """Unknown must neither page nor vanish.

    It is reported as a gap in the INSTRUMENT, keyed per box rather than per
    entry -- a hundred undrained messages behind one broken probe is one
    instrument problem, not a hundred alerts.
    """
    f1 = a.classify_aged_pickup("pa_x", "one.eml", 99999, 900, a.UNKNOWN)
    f2 = a.classify_aged_pickup("pa_x", "two.eml", 99999, 900, a.UNKNOWN)
    assert f1.kind == a.INSTRUMENT_GAP
    assert f1.route == a.OPERATOR
    assert f1.pages is False
    assert f1.key == f2.key, "one broken probe is one finding, not one per message"


def test_a_persisting_condition_notifies_ONCE_not_once_per_interval(edge):
    """1 arrival -> 1 notice. The level-triggered version produced 1 -> 36."""
    findings = [a.classify_system("watcher-dead", "the inbound watcher is not running")]

    t = edge.transitions(findings)
    assert len(t.new) == 1 and not t.ongoing and not t.recovered
    edge.commit(findings)

    for _ in range(35):
        t = edge.transitions(findings)
        assert t.new == [], "a true-and-persisting condition must not re-notify"
        assert len(t.ongoing) == 1
        edge.commit(findings)


def test_recovery_is_itself_a_notice(edge):
    """Told when it breaks and never when it heals, a reader cannot learn the
    current state except by asking."""
    findings = [a.classify_system("watcher-dead", "watcher down")]
    edge.commit(findings)
    t = edge.transitions([])
    assert t.recovered == ["watcher-dead"]
    assert t.new == [] and t.ongoing == []


def test_expected_state_never_enters_the_edge_ledger(edge, tmp_path):
    """Otherwise an inactive agent's mailbox would 'recover' every time the
    sweep ran, producing a recovery notice for a condition that was never
    an alert."""
    ok = a.classify_aged_pickup("pa_x", "m.eml", 99999, 900, a.INACTIVE)
    edge.commit([ok])
    assert json.loads((tmp_path / "edge.json").read_text()) == {}
    t = edge.transitions([])
    assert (t.new, t.ongoing, t.recovered) == ([], [], [])


def test_escalation_requires_that_the_ACTOR_was_told_first(tmp_path):
    """The operator is the terminus of last resort. A finding whose actor was
    never notified has no escalation case: nobody has failed to act yet."""
    f = a.classify_aged_pickup("pa_live", "m.eml", 9999, 900, a.ALIVE, active_s=5000)
    assert a.escalation_due(f, notified_at=None, grace_s=600, now=10_000) is False
    assert a.escalation_due(f, notified_at=9_000, grace_s=600, now=9_100) is False
    assert a.escalation_due(f, notified_at=9_000, grace_s=600, now=9_700) is True

    sysf = a.classify_system("k", "m")
    assert a.escalation_due(sysf, notified_at=0, grace_s=0, now=10_000) is False, (
        "a system fault is already AT the operator; there is nowhere to escalate")


def test_routing_separates_the_two_classes(tmp_path):
    findings = [
        a.classify_system("watcher-dead", "watcher down"),
        a.classify_aged_pickup("pa_live", "m.eml", 9999, 900, a.ALIVE, active_s=5000),
        a.classify_aged_pickup("pa_idle", "m.eml", 9999, 900, a.INACTIVE),
    ]
    grouped = a.route(findings)
    assert len(grouped[a.OPERATOR]) == 1
    assert len(grouped[a.AGENT]) == 1
    assert len(grouped[a.NOBODY]) == 1
    assert sum(1 for f in findings if f.pages) == 1, (
        "exactly one of these three can wake a human")


# ---- the liveness probe: the piece that makes the fix real in production ----

@pytest.fixture
def homes(tmp_path):
    return tmp_path / "homes"


def _agent(homes, name, last_active=None):
    log = homes / name / a.EVENT_LOG_RELPATH
    log.parent.mkdir(parents=True, exist_ok=True)
    if last_active is None:
        return log
    log.write_text("{}\n")
    import os
    os.utime(log, (last_active, last_active))
    return log


def test_an_agent_that_has_NEVER_RUN_reports_inactive_with_zero_accrued(homes):
    """The incident's exact case, at the probe layer.

    No event log at all means no session has ever started. The wall-clock check
    could not see this, which is why it paged for nine hours.
    """
    (homes / "pa_never").mkdir(parents=True)
    probe = a.event_log_liveness_probe(homes)
    assert probe("pa_never") == (a.INACTIVE, 0.0)


def test_an_agent_idle_SINCE_the_mail_arrived_has_accrued_nothing(homes):
    """Absolute liveness is the wrong question.

    An agent that ran for months and stopped before this mail landed has had no
    opportunity to drain it, so it owes nothing against THIS delivery.
    """
    _agent(homes, "pa_stopped", last_active=1000.0)
    probe = a.event_log_liveness_probe(homes)
    assert probe("pa_stopped", 5000.0) == (a.INACTIVE, 0.0)


def test_an_agent_active_AFTER_the_mail_arrived_accrues_from_arrival(homes):
    """Both polarities: the fault must still be reachable."""
    _agent(homes, "pa_busy", last_active=9000.0)
    probe = a.event_log_liveness_probe(homes)
    state, accrued = probe("pa_busy", 5000.0)
    assert state == a.ALIVE
    assert accrued == 4000.0


def test_an_unstattable_marker_is_UNKNOWN_and_NEVER_inactive(homes, monkeypatch, capsys):
    """'I could not see it' is not 'it never ran'.

    Converting a permissions error into INACTIVE would EXCUSE A REAL FAULT on
    the strength of a broken instrument -- the opposite error to the incident,
    and a worse one, because it is silent.
    """
    _agent(homes, "pa_denied", last_active=9000.0)

    def denied(self):
        raise PermissionError("broker cannot read this home")

    monkeypatch.setattr("pathlib.Path.stat", denied)
    probe = a.event_log_liveness_probe(homes)
    assert probe("pa_denied") == (a.UNKNOWN, None)
    assert "not assumed" in capsys.readouterr().err


def test_the_probe_and_the_classifier_compose_into_the_incident_verdict(homes):
    """End to end at the seam: probe output feeds classification unchanged."""
    (homes / "pa_never").mkdir(parents=True)
    probe = a.event_log_liveness_probe(homes)
    state, accrued = probe("pa_never")
    finding = a.classify_aged_pickup("pa_never", "m.eml", age_s=32400,
                                     bound_s=900, liveness=state, active_s=accrued)
    assert finding.pages is False
    assert finding.kind == a.EXPECTED_STATE


def test_the_probe_answers_PER_ENTRY_not_per_box(homes):
    """Two messages, one box, hours apart -- and the agent ran between them.

    A box-level answer applies the oldest entry's verdict to every entry beside
    it. The first wiring of this did exactly that.
    """
    _agent(homes, "pa_mixed", last_active=7000.0)
    probe = a.event_log_liveness_probe(homes)
    old_state, old_accrued = probe("pa_mixed", 5000.0)   # arrived BEFORE activity
    new_state, new_accrued = probe("pa_mixed", 9000.0)   # arrived AFTER activity
    assert (old_state, old_accrued) == (a.ALIVE, 2000.0)
    assert (new_state, new_accrued) == (a.INACTIVE, 0.0)
