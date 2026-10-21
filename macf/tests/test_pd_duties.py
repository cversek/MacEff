"""Duties on the primal daemon (the scheduler design, 4.4)."""
from macf.pd.duties import NOTICE_DUTY_DUE, HostedDuties
from macf.roles.source import EVENT

CARD = "Tester@abc123"


def hosted(tmp_path, log, notices, current, clock):
    from macf.roles import source as rs
    h = HostedDuties(CARD, tmp_path / "roles", lambda e, d: log.append({"event": e, "data": d}) or True,
                     lambda: list(log), lambda s, i: notices.append((s, i)), lambda: clock[0])
    h.boot()
    h.source._current = lambda at: dict(current)          # the tiers, without a roles store on disk
    assert isinstance(h.source, rs.DutyTierSource)
    return h


def crossing(duty, tier="OVERDUE", entered="2026-10-19T09:00:00+00:00"):
    from macf.roles.priority import TIER_NAMES
    arrival = f"pd-{duty}-{tier}-20261019T0900"
    return (duty, TIER_NAMES.index(tier), entered), {"source": "pd", "duty_id": duty, "tier": tier,
                                                     "entered": entered, "arrival_id": arrival}


def test_a_duty_that_crossed_while_no_daemon_ran_is_announced_once_and_never_again(tmp_path):
    """A start announces a crossing it never announced, once, recorded before it is raised; a
    restart reads it back and stays quiet. Polls are spaced, and a crossing announced by some
    other poller isn't counted as this daemon's."""
    log, notices, clock = [], [], [0.0]
    k1, d1 = crossing("d1")
    k2, d2 = crossing("d2", "DUE_SOON")
    log.append({"event": EVENT, "data": {**d2, "source": "monitor", "agent": CARD}})   # another poller's
    h = hosted(tmp_path, log, notices, {k1: d1, k2: d2}, clock)
    h.tick()
    assert sorted(notices) == [(NOTICE_DUTY_DUE, d1["arrival_id"]), (NOTICE_DUTY_DUE, d2["arrival_id"])]
    ours = [e["data"] for e in log if e["data"].get("agent") == CARD]
    assert {d["duty_id"] for d in ours} == {"d1", "d2"}
    clock[0] = 30.0
    k3, d3 = crossing("d3")
    h.source._current = lambda at: {k1: d1, k2: d2, k3: d3}
    h.tick()
    assert len(notices) == 2                                   # within the poll spacing
    clock[0] = 61.0
    h.tick()
    assert notices[-1] == (NOTICE_DUTY_DUE, d3["arrival_id"]) and len(notices) == 3
    restarted = hosted(tmp_path, log, notices, {k1: d1, k2: d2, k3: d3}, [0.0])
    restarted.tick()
    assert len(notices) == 3


def test_a_roles_store_that_fails_is_said_once_and_the_daemon_goes_on(tmp_path, capsys):
    log, notices, clock = [], [], [0.0]
    h = hosted(tmp_path, log, notices, {}, clock)

    def broken(at):
        raise OSError("unreadable")
    h.source._current = broken
    for t in (0.0, 61.0, 122.0):
        clock[0] = t
        h.tick()
    assert capsys.readouterr().err.count("couldn't be read for duties") == 1 and notices == []
