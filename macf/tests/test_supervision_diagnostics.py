"""Supervision diagnostics: the facts an agent needs before trusting anything else.

Written after an evening in which "am I running under the harness?" was answered
by hand at least six times — from ``$TMUX``, ps ancestry walks, tmux
introspection and greps of the supervisor registry — by the person who had just
written the harness, and came out wrong twice.

The load-bearing test here is the context-window one. That failure is invisible
by construction: a non-first-party base URL without the escape-hatch flag drops
the window to a fifth of what every surface reports, with no log line and no
error. An alarm for it is only worth having if it has been observed firing, so
each state has an explicit case.
"""

import json

import pytest

from macf.supervisor import is_live_supervisor
from macf.utils.supervision import (
    FIRST_PARTY_FLAG,
    context_window_integrity,
    format_diagnosis,
)


class TestContextWindowIntegrity:
    def test_no_base_url_is_first_party(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv(FIRST_PARTY_FLAG, raising=False)
        assert context_window_integrity()["status"] == "direct"

    def test_the_default_host_is_first_party(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        monkeypatch.delenv(FIRST_PARTY_FLAG, raising=False)
        assert context_window_integrity()["status"] == "first-party"

    def test_a_proxy_with_the_flag_is_reported_ok(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:8019")
        monkeypatch.setenv(FIRST_PARTY_FLAG, "1")
        assert context_window_integrity()["status"] == "proxied-ok"

    def test_a_proxy_without_the_flag_is_DEGRADED(self, monkeypatch):
        """THE check. This state costs 80% of the context window and announces
        itself nowhere — it recurred the same evening it was fixed, from a shell
        still holding a pre-fix function."""
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:8019")
        monkeypatch.delenv(FIRST_PARTY_FLAG, raising=False)
        r = context_window_integrity()
        assert r["status"] == "DEGRADED"
        assert FIRST_PARTY_FLAG in r["detail"], "the remedy must be named, not implied"

    def test_the_first_party_host_on_another_port_does_not_pass(self, monkeypatch):
        """The host comparison includes the port. api.anthropic.com:8443 is NOT
        first-party to the client, and a check that ignored the port would give
        a false all-clear to exactly the interception setup that causes this."""
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com:8443")
        monkeypatch.delenv(FIRST_PARTY_FLAG, raising=False)
        assert context_window_integrity()["status"] == "DEGRADED"

    def test_a_malformed_base_url_does_not_claim_first_party(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "not a url")
        monkeypatch.delenv(FIRST_PARTY_FLAG, raising=False)
        assert context_window_integrity()["status"] == "DEGRADED"


class TestLiveSupervisorPredicate:
    """Three conditions, each excluding a state observed on a live host."""

    def test_a_stopped_entry_is_not_live(self):
        assert not is_live_supervisor({"status": "stopped", "supervisor_pid": 1})

    def test_an_entry_for_a_dead_pid_is_not_live(self):
        """Entries outlive their processes; seven stale ones sat in one
        registry, the oldest still claiming a supervisor nine days gone."""
        assert not is_live_supervisor({"status": "running", "supervisor_pid": 999999})

    def test_a_live_pid_that_is_not_a_supervisor_is_not_live(self, monkeypatch):
        """Pids are recycled. An entry pointing at whatever inherited the
        number is worse than no entry: it asserts health about a stranger."""
        import os
        assert not is_live_supervisor({"status": "running", "supervisor_pid": os.getpid()})

    def test_the_predicate_can_say_yes(self, monkeypatch):
        """Negative control on the predicate itself — three ways to say no and
        no way to say yes would pass every test above and be useless."""
        import os
        monkeypatch.setattr("macf.supervisor.subprocess.run",
                            lambda *a, **k: type("R", (), {"stdout": "python -m macf.supervisor x"})())
        assert is_live_supervisor({"status": "running", "supervisor_pid": os.getpid()})


class TestFormatting:
    """A negative must name what was checked; a default must say it is one."""

    def _d(self, **over):
        base = {
            "agent": {"identifier": "Agent_abc123", "calling_card": "Agent@abc123",
                      "resolved_from": "calling card", "is_default": False,
                      "candidates": None, "installed": []},
            "supervision": {"supervised": False, "supervisors": [],
                            "other_live_supervisors": [], "name_collision": False},
            "session": {"in_tmux": False, "socket": None, "name": None,
                        "clients_attached": None, "matches_expected": None},
            "context_window": {"status": "direct", "detail": "no ANTHROPIC_BASE_URL"},
            "artifacts": {"missing": None},
        }
        for k, v in over.items():
            base[k] = {**base[k], **v}
        return base

    def test_an_unsupervised_session_says_what_that_costs(self):
        out = format_diagnosis(self._d())
        assert "NONE running" in out
        assert "not supervised" in out

    def test_a_defaulted_agent_is_labelled_a_default(self):
        """The defect this whole line of work started from: a guessed name
        reported as a finding, so ABSENT read as 'there is no harness here'."""
        out = format_diagnosis(self._d(agent={"is_default": True, "identifier": "agent"}))
        assert "DEFAULT" in out

    def test_a_name_collision_is_called_out(self):
        out = format_diagnosis(self._d(supervision={"name_collision": True}))
        assert "COLLISION" in out
        assert "one task store" in out

    def test_multiple_attached_clients_are_called_out(self):
        out = format_diagnosis(self._d(
            session={"in_tmux": True, "name": "s", "clients_attached": 3,
                     "matches_expected": True}))
        assert "CLIENTS" in out

    def test_a_session_that_is_not_the_harness_is_called_out(self):
        out = format_diagnosis(self._d(
            session={"in_tmux": True, "name": "other", "clients_attached": 1,
                     "matches_expected": False}))
        assert "NOT the harness session" in out

    def test_a_degraded_window_is_warned_about(self):
        out = format_diagnosis(self._d(
            context_window={"status": "DEGRADED", "detail": "flag not set"}))
        assert "⚠️" in out and "CONTEXT" in out


class TestDiagnoseIsTotal:
    def test_it_returns_every_section_even_with_nothing_running(self, monkeypatch, tmp_path):
        from macf.utils import supervision
        monkeypatch.setattr(supervision, "live_supervisors", lambda: [])
        # Ancestry reads the live registry; without this the answer would
        # depend on whether the test runs under a supervisor.
        monkeypatch.setattr("macf.supervisor._find_own_supervisor", lambda: None)
        monkeypatch.setenv("MACEFF_AGENT_NAME", "probe")
        d = supervision.diagnose()
        for key in ("agent", "supervision", "session", "context_window", "artifacts"):
            assert key in d, f"{key} missing — a diagnostic that omits a section reads as a clean one"
        assert d["supervision"]["supervised"] is False


class TestSupervisionByAncestry:
    """The readout the restart policy branches on. A supervisor is named by the
    deployment's --name, which need not be the calling card; keyed on the name,
    a renamed agent read as unsupervised while its supervisor was running."""

    SUP = {"supervisor_pid": 4242, "child_pid": 4243, "name": "agent1",
           "restart_count": 0, "tmux_session": "agent1"}

    def _diagnose(self, monkeypatch, own, agent=None):
        from macf.utils import supervision
        monkeypatch.setattr(supervision, "live_supervisors", lambda: [self.SUP])
        monkeypatch.setattr("macf.supervisor._find_own_supervisor", lambda: own)
        monkeypatch.setenv("MACEFF_AGENT_NAME", "CardName")
        return supervision.diagnose(agent)

    def test_a_renamed_agent_is_supervised_by_its_ancestor(self, monkeypatch):
        s = self._diagnose(monkeypatch, own=self.SUP)["supervision"]
        assert s["supervised"] is True
        assert s["resolved_by"] == "ancestry"
        assert s["name_differs"] is True
        assert s["other_live_supervisors"] == []

    def test_no_ancestor_and_no_matching_name_is_unsupervised(self, monkeypatch):
        s = self._diagnose(monkeypatch, own=None)["supervision"]
        assert s["supervised"] is False and s["resolved_by"] is None
        assert [o["pid"] for o in s["other_live_supervisors"]] == [4242]

    def test_an_explicitly_named_agent_is_not_answered_by_this_process_ancestry(self, monkeypatch):
        """Ancestry says who supervises THIS process, nothing about another agent."""
        s = self._diagnose(monkeypatch, own=self.SUP, agent="SomeoneElse")["supervision"]
        assert s["supervised"] is False

    def test_the_readout_names_the_supervisor_and_how_it_was_found(self, monkeypatch):
        from macf.utils import supervision
        text = supervision.format_diagnosis(self._diagnose(monkeypatch, own=self.SUP))
        assert "pid 4242" in text and "named agent1" in text and "found by ancestry" in text
        assert "NONE running" not in text


def test_an_artifact_check_that_could_not_run_says_so(monkeypatch):
    """Swallowed, the failure left no artifacts line and the readout looked clean."""
    from macf.utils import supervision

    def broken(**_):
        raise OSError("harness home unreadable")

    monkeypatch.setattr(supervision, "live_supervisors", lambda: [])
    monkeypatch.setattr("macf.supervisor._find_own_supervisor", lambda: None)
    monkeypatch.setattr("macf.utils.harness.default_params", broken)
    monkeypatch.setenv("MACEFF_AGENT_NAME", "probe")
    text = supervision.format_diagnosis(supervision.diagnose())
    assert "ARTIFACTS:  not checked -- OSError: harness home unreadable" in text
