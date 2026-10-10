"""Observation and attach (MIS-0002 R81-R102, R111).

Attach: R100 (attach_MUST_resolve_from_pd) and R101 (readout_MUST_say_nothing_attachable).
Observation acts: R82, R86-R90, R92, R94 and R111. The stream and presence land after.
"""
from dataclasses import dataclass

import pytest

from macf.observe import acts
from macf.utils.attach import CLIENT, NONE, TMUX, plan_attach, readout_line


@dataclass
class _Info:
    session_id: str
    kind: str


def _resp(state="running", pid=4187, proc_start="Sat Oct 10 10:23:30 2026"):
    return {"ok": True, "units": [{"unit": "session", "state": state, "pid": pid,
                                   "proc_start": proc_start, "since": 0.0}]}


def _plan(response, info=None, verified=True, chain=(4187, 4120, 4094), panes=None, **kw):
    return plan_attach(response, "session",
                       read_info=lambda pid: info,
                       verify=lambda pid, start: verified,
                       ancestors=lambda pid: list(chain),
                       tmux_panes=lambda: dict(panes or {}), **kw)


def test_attach_resolves_from_pd():
    """The daemon's pid decides: a client-hosted session attaches through the client,
    a tmux one by exact session name, never by a name lookup."""
    hosted = _plan(_resp(), info=_Info("32149023-da95-480f-bb4a-866d6bc083a0", "bg"))
    assert hosted.kind == CLIENT
    assert hosted.argv == ["claude", "attach", "32149023-da95-480f-bb4a-866d6bc083a0"]

    in_tmux = _plan(_resp(), info=_Info("89f47c46-71a2", "interactive"), panes={4120: "IraMacEff_ee9a78"})
    assert in_tmux.kind == TMUX
    assert in_tmux.argv == ["tmux", "attach", "-t", "=IraMacEff_ee9a78", "-d"]
    ro = _plan(_resp(), info=None, panes={4094: "x"}, read_only=True, control=True)
    assert ro.argv == ["tmux", "-CC", "attach", "-t", "=x", "-r"]


def test_no_answer_is_not_a_name_lookup():
    """A daemon that does not answer resolves nothing, even with a tmux session of the agent's name."""
    plan = _plan(None, panes={4120: "IraMacEff_ee9a78"})
    assert plan.kind == NONE and "did not answer" in plan.reason
    refused = _plan({"ok": False, "error": "peer is not the daemon's user"})
    assert refused.kind == NONE and "peer" in refused.reason


def test_a_recycled_pid_is_not_attached():
    plan = _plan(_resp(), info=_Info("x", "bg"), verified=False)
    assert plan.kind == NONE and "no longer" in plan.reason


def test_nothing_attachable_said():
    """R101: a stopped unit, a missing unit and a bare terminal each say why there is nothing to attach to."""
    stopped = _plan(_resp(state="stopped", pid=None))
    assert stopped.kind == NONE and "stopped" in stopped.reason
    missing = _plan({"ok": True, "units": []})
    assert missing.kind == NONE and "no unit named 'session'" in missing.reason
    bare = _plan(_resp(), info=_Info("x", "interactive"), panes={})
    assert bare.kind == NONE and "not under tmux" in bare.reason
    assert readout_line(bare).startswith("Attach:       nothing attachable hosts this session (")
    assert "claude attach" in readout_line(_plan(_resp(), info=_Info("abc", "bg")))


# ---------------------------------------------------------------------------
# Observation acts (R82, R86-R90, R92, R94, R111): events in the observed agent's log
# ---------------------------------------------------------------------------

ME, THEM = "IraMacEff@ee9a78", "ThomMacEff@ee5cd8"


def _host(card):
    return None


def _log(*events):
    return list(events)


def _invited(lease_until=None, now=None):
    inv = acts.invite(ME, THEM, 1200, {}, container_of=_host, lease_until=lease_until, now=now)
    return inv, _log(inv.event)


def test_onlooker_needs_invitation():
    """R82: nothing is admitted before the invitation, and only with its own secret after."""
    assert acts.admit(THEM, "anything", acts.fold([])) is None
    inv, log = _invited()
    state = acts.fold(log)
    assert acts.admit(THEM, inv.secret, state).stream_from == 1200
    assert acts.admit(THEM, "a guess", state) is None
    assert acts.admit("SomeoneElse@abcdef", inv.secret, state) is None


def test_observation_events():
    """R90: invite, pause, resume and end are each an event; the log, folded, is the state."""
    inv, log = _invited()
    log.append(acts.pause(THEM, acts.fold(log)))
    log.append(acts.resume(THEM, acts.fold(log)))
    log.append(acts.end(THEM, "observed", acts.fold(log)))
    assert [e["event"] for e in log] == [acts.EVENT_INVITE, acts.EVENT_PAUSE, acts.EVENT_RESUME, acts.EVENT_END]
    assert acts.fold(log)[THEM].status == acts.ENDED


def test_the_log_never_holds_the_secret():
    inv, log = _invited()
    assert inv.secret not in str(log) and len(inv.event["data"]["secret_sha256"]) == 64


def test_pause_resume():
    """R92: the owner pauses and resumes; a paused observation is still admitted, to show the pause."""
    inv, log = _invited()
    log.append(acts.pause(THEM, acts.fold(log)))
    state = acts.fold(log)
    assert state[THEM].status == acts.PAUSED and acts.admit(THEM, inv.secret, state) is not None
    with pytest.raises(acts.ActRefused):
        acts.pause(THEM, state)
    log.append(acts.resume(THEM, state))
    assert acts.fold(log)[THEM].status == acts.ACTIVE


def test_either_party_ends():
    """R86: the observed agent or the onlooker ends it; after that nothing is admitted."""
    for who in ("observed", "onlooker"):
        inv, log = _invited()
        log.append(acts.end(THEM, who, acts.fold(log)))
        state = acts.fold(log)
        assert state[THEM].ended_by == who and acts.admit(THEM, inv.secret, state) is None


def test_operator_ends():
    """R87: the operator may end any observation."""
    inv, log = _invited()
    log.append(acts.end(THEM, "operator", acts.fold(log)))
    assert acts.fold(log)[THEM].ended_by == "operator"
    with pytest.raises(acts.ActRefused):
        acts.end(THEM, "a passer-by", acts.fold(_invited()[1]))


def test_lease_ends_invitation():
    """R88: a lease ends the invitation at its declared time."""
    inv, log = _invited(lease_until=2000.0, now=1000.0)
    assert acts.expired(acts.fold(log), now=1999.0) == []
    owed = acts.expired(acts.fold(log), now=2000.0)
    log.extend(owed)
    state = acts.fold(log)
    assert state[THEM].status == acts.ENDED and acts.admit(THEM, inv.secret, state) is None
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=_host, lease_until=5.0, now=10.0)


def test_lease_end_same_event():
    """R89: a lease's end is the same event a party's end is, told apart only by who ended it."""
    _, log = _invited(lease_until=2000.0, now=1000.0)
    by_lease = acts.expired(acts.fold(log), now=3000.0)[0]
    by_party = acts.end(THEM, "onlooker", acts.fold(log))
    assert by_lease["event"] == by_party["event"] == acts.EVENT_END
    assert set(by_lease["data"]) == set(by_party["data"])
    assert by_lease["data"]["ended_by"] == "lease"


def test_onlooker_by_card():
    """R94: an invitation names its onlooker by calling card, never by login user."""
    for name in ("cversek", "thom", "ThomMacEff", "ThomMacEff@EE5CD8", "ThomMacEff@ee5cd8x"):
        with pytest.raises(acts.ActRefused):
            acts.invite(ME, name, 0, {}, container_of=_host)
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, ME, 0, {}, container_of=_host)


def test_no_invitation_across_containers():
    """R111: an agent in one container does not invite an onlooker in another, and an
    onlooker that cannot be placed is not invited either."""
    places = {ME: "container-a", THEM: "container-b"}
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=places.get)
    places[THEM] = "container-a"
    assert acts.invite(ME, THEM, 0, {}, container_of=places.get).event["event"] == acts.EVENT_INVITE

    def unknown(card):
        raise LookupError("no such agent here")
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=unknown)


def test_a_live_observation_is_not_invited_twice():
    _, log = _invited()
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 5, acts.fold(log), container_of=_host)
    log.append(acts.end(THEM, "observed", acts.fold(log)))
    again = acts.invite(ME, THEM, 5, acts.fold(log), container_of=_host)
    log.append(again.event)
    assert acts.fold(log)[THEM].status == acts.ACTIVE and acts.fold(log)[THEM].stream_from == 5
