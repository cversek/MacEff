"""Controls for `_find_own_supervisor` — which pane a self-directed command types into.

This is the security-relevant half of `macf_tools inject`. The command itself is
a thin wrapper over an existing send-keys path; the question that decides whether
it is safe is WHOSE PANE it resolves to. A resolution that silently picks the
wrong supervisor types an operator's command into another agent's session, and
does so with no error anywhere — the send succeeds, at the wrong target.

So the tests below are about MISRESOLUTION, not about happy-path lookup. Each
plants a registry a naive matcher would get wrong.

The earlier version of this file tested the matcher against registries shaped
the way the matcher expected, which validated its implementation and not its
assumption. It passed while the resolver could not find a supervisor that was
running the whole time. `TestTheNamingConventionIsNotTheIdentity` is that case.
"""
import json

import pytest

from macf import supervisor


MY_PID = 424242
MY_LINEAGE = {111, MY_PID, 999}   # this process, its client, its supervisor


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """An isolated supervisor registry, with every entry live unless stated.

    Liveness is decided by `is_live_supervisor`, so both of its process checks
    are stubbed — a test registry has no real pids behind it.
    """
    monkeypatch.setattr(supervisor, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(supervisor, "_is_alive", lambda pid: pid != 0)
    monkeypatch.setattr(supervisor, "_is_supervisor_process", lambda pid: pid != 0)
    monkeypatch.setattr(supervisor, "_ancestor_pids", lambda: set(MY_LINEAGE))

    def write(name, *, tmux_session="", pid=1234, child_pid=0, created=0,
              status="running"):
        (tmp_path / f"{name}.json").write_text(json.dumps({
            "supervisor_pid": pid, "name": name, "tmux_session": tmux_session,
            "child_pid": child_pid, "created": created, "status": status,
        }))
    return write


def _session(monkeypatch, sid):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)


class TestTheNamingConventionIsNotTheIdentity:
    """The bug this file did not catch the first time.

    `launch_in_terminal` suffixes the tmux session name with the CC session id,
    and the resolver treated that convention as the way to find itself. A
    deployment that names its sessions by agent moniker satisfies no part of it,
    so `inject` reported the session unsupervised while its supervisor had been
    up for thirteen days.
    """

    def test_a_moniker_named_session_resolves_by_pid(self, registry, monkeypatch):
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("TheHarborMaster_ee5cd8", tmux_session="TheHarborMaster_ee5cd8",
                 pid=999, child_pid=MY_PID)
        assert supervisor._find_own_supervisor()["name"] == "TheHarborMaster_ee5cd8"

    def test_resolution_survives_a_session_id_that_is_recorded_nowhere(
            self, registry, monkeypatch):
        """`session_id: null` and no id in the tmux name is the observed state
        of a long-running supervisor, not a corrupt entry."""
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.setattr(supervisor, "_latest_session_id", lambda: None)
        registry("agent", tmux_session="agent", pid=999, child_pid=0)
        assert supervisor._find_own_supervisor()["name"] == "agent"

    def test_the_supervisors_own_pid_also_identifies_it(self, registry, monkeypatch):
        """A caller under the supervisor but not under the client it launched
        (a restart in flight) is still that supervisor's."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("mine", tmux_session="unrelated", pid=999, child_pid=7)
        assert supervisor._find_own_supervisor()["name"] == "mine"


class TestItDoesNotResolveToSomeoneElse:
    def test_another_agents_supervisor_is_not_selected(self, registry, monkeypatch):
        """THE FAILURE THAT MATTERS. A miss must return None so the caller
        refuses, never fall through to whatever supervisor happens to exist —
        typing an operator's command into another agent's pane is a send that
        SUCCEEDS at the wrong target, with no error anywhere."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("theirs", tmux_session="Agent_99999999-0000-0000-0000-000000000000",
                 pid=555, child_pid=556)
        assert supervisor._find_own_supervisor() is None

    def test_ancestry_wins_over_a_name_that_merely_matches(self, registry, monkeypatch):
        """Two candidates: one carrying my session id in its name, one actually
        supervising me. A pid is an identity and a name is a convention, so the
        pid decides — and a name collision cannot steer the send."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("lookalike", tmux_session="Agent_abcd1234", pid=555, child_pid=556)
        registry("mine", tmux_session="moniker", pid=999, child_pid=MY_PID)
        assert supervisor._find_own_supervisor()["name"] == "mine"

    def test_a_dead_supervisor_is_skipped_even_when_its_pid_is_an_ancestor(
            self, registry, monkeypatch):
        """A registry entry outlives its process. Resolving to a dead supervisor
        sends keys into a pane that no longer exists and reports success."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("stale", tmux_session="Agent_abcd1234", pid=999,
                 child_pid=MY_PID, status="stopped")
        assert supervisor._find_own_supervisor() is None

    def test_a_recycled_pid_is_not_a_supervisor(self, registry, monkeypatch):
        """Pids are reused. An entry pointing at whatever inherited the number
        is worse than no entry, so liveness asks whether the pid is STILL a
        supervisor and not merely alive."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        monkeypatch.setattr(supervisor, "_is_supervisor_process", lambda pid: False)
        registry("recycled", tmux_session="Agent_abcd1234", pid=999, child_pid=MY_PID)
        assert supervisor._find_own_supervisor() is None

    def test_the_newest_live_match_wins_when_a_session_was_relaunched(
            self, registry, monkeypatch):
        """Same client, supervisor restarted: two entries match and only the
        current one has a live pane."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("old", tmux_session="Agent_abcd1234", pid=999, child_pid=MY_PID,
                 created=100)
        registry("new", tmux_session="Agent_abcd1234", pid=999, child_pid=MY_PID,
                 created=200)
        assert supervisor._find_own_supervisor()["created"] == 200


class TestTheSessionIdFallbackStillWorks:
    """For a caller outside its own client's process tree — driving the agent
    from a separate ssh session — ancestry says nothing and the convention is
    the only signal left."""

    def test_a_short_prefix_match_is_accepted_when_ancestry_is_silent(
            self, registry, monkeypatch):
        monkeypatch.setattr(supervisor, "_ancestor_pids", lambda: {1, 2, 3})
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("mine", tmux_session="Agent_abcd1234", pid=999, child_pid=MY_PID)
        assert supervisor._find_own_supervisor()["name"] == "mine"


class TestItFailsClosed:
    def test_no_registry_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(supervisor, "REGISTRY_DIR", tmp_path / "absent")
        monkeypatch.setattr(supervisor, "_ancestor_pids", lambda: set(MY_LINEAGE))
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        assert supervisor._find_own_supervisor() is None

    def test_a_malformed_registry_entry_is_skipped_not_fatal(
            self, registry, monkeypatch, tmp_path):
        """One unreadable entry must not prevent resolving a good one — the
        loop-scoped rule: a bad input ends the iteration, not the search."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        (tmp_path / "broken.json").write_text("{not json")
        registry("mine", tmux_session="moniker", pid=999, child_pid=MY_PID)
        assert supervisor._find_own_supervisor()["name"] == "mine"


class TestAncestryWalk:
    def test_ppid_reports_the_real_parent(self):
        import os
        assert supervisor._ppid(os.getpid()) == os.getppid()

    def test_ppid_returns_zero_for_a_pid_that_cannot_be_read(self):
        """Fails to 0 rather than raising: this feeds a set-membership test,
        and a raise here would take down `inject` instead of falling back."""
        assert supervisor._ppid(-1) == 0

    def test_the_walk_includes_this_process_and_its_parent(self):
        import os
        pids = supervisor._ancestor_pids()
        assert os.getpid() in pids and os.getppid() in pids

    def test_the_walk_is_bounded(self, monkeypatch):
        """A parent chain that lies or loops must not spin — this runs inside a
        CLI an agent invokes."""
        monkeypatch.setattr(supervisor, "_ppid", lambda pid: pid + 1)
        assert len(supervisor._ancestor_pids(limit=8)) == 8
