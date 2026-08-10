"""Calling Card → session identifier, and the harness agent resolver.

Session-management identity used to be a second, unregistered namespace: the
harness named its tmux session and systemd unit after a nickname that appeared
nowhere else in the framework. An operator holding the Calling Card could not
derive the session name, a tool holding the session name could not recover the
Calling Card, and `harness status` therefore had no default it could resolve —
so it guessed, and reported the guess as a finding.

The character rules asserted here were MEASURED on 2026-08-07 (tmux 3.6,
systemd 257), not read from documentation. The measurement mattered: it refuted
the claim in the originating issue that '@' had to be substituted for systemd's
sake. It does not — a concrete unit named `cc-harness-Name@abc.service` enables,
symlinks, starts and reports active. '@' is substituted by convention, because
that is how systemd spells a template instance. The two reasons are different
and only one of them is a constraint.
"""

import shutil
import subprocess

import pytest

from macf.utils.harness import installed_agents, resolve_agent
from macf.utils.identity import (
    calling_card_from_identifier,
    session_identifier,
)

CARD = "TheHarborMaster@ee5cd8"
IDENT = "TheHarborMaster_ee5cd8"


class TestSubstitution:
    def test_the_calling_card_maps_to_a_derivable_identifier(self):
        assert session_identifier(CARD) == IDENT

    def test_an_operator_can_get_back_from_the_identifier_to_the_agent(self):
        """The direction that lets status name the agent behind a session."""
        assert calling_card_from_identifier(IDENT) == CARD

    def test_a_moniker_containing_the_separator_survives_the_round_trip(self):
        """Split on the LAST separator: the one that was the '@'."""
        assert calling_card_from_identifier(session_identifier("Under_Score@ff0011")) == "Under_Score@ff0011"

    @pytest.mark.parametrize("card", [
        "A.B@abc123",     # tmux rewrites '.' silently
        "A:B@abc123",     # tmux rewrites ':' silently; systemd rejects it
        "A B@abc123",     # whitespace
        "A/B@abc123",     # path separator
    ])
    def test_characters_that_do_not_survive_a_tool_are_substituted(self, card):
        ident = session_identifier(card)
        assert not (set(ident) & set(".:/ \t@"))

    def test_runs_are_collapsed(self):
        """"A..B" and "A_B" differing only by underscore count is a distinction
        no human reads correctly out of a session list."""
        assert session_identifier("A..B@abc123") == "A_B_abc123"

    def test_identifier_is_stable(self):
        assert session_identifier(CARD) == session_identifier(CARD)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not available")
class TestTheSubstitutionIsActuallyNecessary:
    """Negative controls. Without these the rules above are just assertions —
    and the originating issue shows how easily an unmeasured assertion about
    these tools turns out to be wrong."""

    def _roundtrip(self, name, env):
        """Create a session under `name`; report the name tmux actually stored.

        `env` comes from the `tmux_sandbox_env` fixture, which selects a private
        server without scrubbing PATH. Building it here as
        `{"TMUX_TMPDIR": ...}` was the earlier spelling and left the subprocess
        with no PATH at all, so tmux was unreachable wherever it lives outside
        the POSIX fallback -- every Homebrew install, i.e. every macOS.
        """
        subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", name, "sleep 5"],
                       env=env, capture_output=True)
        stored = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                                env=env, capture_output=True, text=True).stdout.strip()
        addressable = subprocess.run(["tmux", "has-session", "-t", f"={name}"],
                                     env=env, capture_output=True).returncode == 0
        subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)
        return stored, addressable

    @pytest.mark.parametrize("bad", ["Name.suffix", "Name:suffix"])
    def test_tmux_silently_rewrites_these_and_the_name_stops_addressing(self, bad, tmux_sandbox_env):
        """The failure mode that motivates substituting at all: new-session
        SUCCEEDS, and the name you asked for addresses nothing afterwards."""
        stored, addressable = self._roundtrip(bad, tmux_sandbox_env)
        assert stored != bad, "tmux accepted this verbatim — the rule may be stale"
        assert not addressable

    def test_the_substituted_form_survives_and_addresses(self, tmux_sandbox_env):
        stored, addressable = self._roundtrip(IDENT, tmux_sandbox_env)
        assert stored == IDENT
        assert addressable

    def test_at_sign_is_a_convention_choice_not_a_tmux_constraint(self, tmux_sandbox_env):
        """Recorded so the choice stays revisable: tmux keeps '@' verbatim, so
        substituting it is ours to reconsider, not a limit we ran into."""
        stored, addressable = self._roundtrip(CARD, tmux_sandbox_env)
        assert stored == CARD
        assert addressable


class TestResolverNeverPassesAGuessOffAsAFinding:
    def test_an_explicit_flag_wins_and_says_so(self):
        assert resolve_agent("chosen") == ("chosen", "flag")

    def test_the_environment_override_is_named_as_the_source(self, monkeypatch):
        monkeypatch.setenv("MACEFF_AGENT_NAME", "fromenv")
        assert resolve_agent() == ("fromenv", "MACEFF_AGENT_NAME")

    def test_falls_back_to_the_calling_card(self, monkeypatch):
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: CARD)
        assert resolve_agent() == (IDENT, "calling card")

    def test_a_single_installed_unit_resolves(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "x@unknown")
        (tmp_path / "cc-harness-solo.service").write_text("")
        assert resolve_agent(unit_dir=tmp_path) == ("solo", "the only installed unit")

    def test_several_installed_units_are_listed_rather_than_picked(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "x@unknown")
        for n in ("alpha", "beta"):
            (tmp_path / f"cc-harness-{n}.service").write_text("")
        agents, source = resolve_agent(unit_dir=tmp_path)
        assert source == "ambiguous"
        assert agents == ["alpha", "beta"]

    def test_an_unresolvable_identity_does_not_manufacture_a_name(self, monkeypatch, tmp_path):
        """'unknown' is what identity returns when no UUID resolves. Deriving a
        session name from it would invent an identifier for the one agent whose
        identity could not be established."""
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "Someone@unknown")
        assert resolve_agent(unit_dir=tmp_path) == ("agent", "default")

    def test_the_default_is_labelled_as_a_default(self, monkeypatch, tmp_path):
        """The whole defect in one assertion: the caller must be able to tell a
        guess from a resolution, because it is the caller that prints ABSENT."""
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "x@unknown")
        assert resolve_agent(unit_dir=tmp_path)[1] == "default"


class TestInstalledAgents:
    def test_lists_only_harness_units(self, tmp_path):
        (tmp_path / "cc-harness-one.service").write_text("")
        (tmp_path / "unrelated.service").write_text("")
        assert installed_agents(tmp_path) == ["one"]

    def test_a_missing_unit_directory_is_empty_not_an_error(self, tmp_path):
        assert installed_agents(tmp_path / "nope") == []


class TestWatchdogUnitsAreNotAgents:
    """The watchdog shares the unit-name prefix but is not an agent. Counting it
    would make resolution ambiguous and break every command that resolves by
    enumeration — an installed helper disabling the thing it helps."""

    def test_a_watchdog_unit_is_not_enumerated_as_an_agent(self, tmp_path):
        (tmp_path / "cc-harness-Real_abc123.service").write_text("")
        (tmp_path / "cc-harness-Real_abc123-watch.service").write_text("")
        assert installed_agents(tmp_path) == ["Real_abc123"]

    def test_resolution_stays_unambiguous_with_a_watchdog_installed(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
        monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "x@unknown")
        (tmp_path / "cc-harness-Real_abc123.service").write_text("")
        (tmp_path / "cc-harness-Real_abc123-watch.service").write_text("")
        assert resolve_agent(unit_dir=tmp_path) == ("Real_abc123", "the only installed unit")
