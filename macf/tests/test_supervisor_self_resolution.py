"""Controls for `_find_own_supervisor` — which pane a self-directed command types into.

This is the security-relevant half of `macf_tools inject`. The command itself is
a thin wrapper over an existing send-keys path; the question that decides whether
it is safe is WHOSE PANE it resolves to. A resolution that silently picks the
wrong supervisor types an operator's command into another agent's session, and
does so with no error anywhere — the send succeeds, at the wrong target.

So the tests below are about MISRESOLUTION, not about happy-path lookup. Each
plants a registry a naive matcher would get wrong.
"""
import json

import pytest

from macf import supervisor


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """An isolated supervisor registry, with every entry alive unless stated."""
    monkeypatch.setattr(supervisor, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(supervisor, "_is_alive", lambda pid: pid != 0)

    def write(name, *, tmux_session, pid=1234, created=0):
        (tmp_path / f"{name}.json").write_text(json.dumps({
            "supervisor_pid": pid, "tmux_session": tmux_session, "created": created,
        }))
    return write


def _session(monkeypatch, sid):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)


class TestItResolvesToThisSession:
    def test_matches_the_supervisor_whose_tmux_session_carries_this_session_id(
            self, registry, monkeypatch):
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("mine", tmux_session="Agent_abcd1234-1111-2222-3333-444444444444")
        assert supervisor._find_own_supervisor()["tmux_session"].endswith("444444444444")

    def test_a_short_prefix_match_is_accepted(self, registry, monkeypatch):
        """tmux session names are truncated in practice, so the first id segment
        is the usable key."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("mine", tmux_session="Agent_abcd1234")
        assert supervisor._find_own_supervisor() is not None


class TestItDoesNotResolveToSomeoneElse:
    def test_another_agents_supervisor_is_not_selected(self, registry, monkeypatch):
        """THE FAILURE THAT MATTERS. A miss must return None so the caller
        refuses, never fall through to whatever supervisor happens to exist —
        typing an operator's command into another agent's pane is a send that
        SUCCEEDS at the wrong target, with no error anywhere."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("theirs", tmux_session="Agent_99999999-0000-0000-0000-000000000000")
        assert supervisor._find_own_supervisor() is None

    def test_a_dead_supervisor_is_skipped_even_when_its_session_matches(
            self, registry, monkeypatch):
        """A registry entry outlives its process. Resolving to a dead supervisor
        sends keys into a pane that no longer exists and reports success."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("stale", tmux_session="Agent_abcd1234", pid=0)
        assert supervisor._find_own_supervisor() is None

    def test_the_newest_live_match_wins_when_a_session_was_relaunched(
            self, registry, monkeypatch):
        """Same session id, supervisor restarted: two entries match and only the
        current one has a live pane."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        registry("old", tmux_session="Agent_abcd1234", created=100)
        registry("new", tmux_session="Agent_abcd1234", created=200)
        assert supervisor._find_own_supervisor()["created"] == 200


class TestItFailsClosed:
    def test_no_registry_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(supervisor, "REGISTRY_DIR", tmp_path / "absent")
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        assert supervisor._find_own_supervisor() is None

    def test_a_malformed_registry_entry_is_skipped_not_fatal(
            self, registry, monkeypatch, tmp_path):
        """One unreadable entry must not prevent resolving a good one — the
        loop-scoped rule: a bad input ends the iteration, not the search."""
        _session(monkeypatch, "abcd1234-1111-2222-3333-444444444444")
        (tmp_path / "broken.json").write_text("{not json")
        registry("mine", tmux_session="Agent_abcd1234")
        assert supervisor._find_own_supervisor() is not None
