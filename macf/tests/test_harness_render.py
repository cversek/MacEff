"""Tests for the harness generator.

The harness had existed as a hand-edited systemd unit on a single host, and its
stored copy had already drifted from the live one — missing the environment flag
that keeps the long-context window, so anyone installing from the artifact would
have got a silently degraded session. These tests assert on GENERATED output,
which is the thing that cannot drift from itself.

`systemd-analyze verify` is used as the well-formedness oracle, but on its
OUTPUT rather than its exit status: it exits 0 while printing "Unknown key ...,
ignoring" for both a missing ExecStart and a misplaced StartLimit directive.
Gating on the exit code would be the same instrument-reports-success defect these
invariants exist to catch.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from macf.utils.harness import (
    HarnessParams,
    render_child,
    render_tmux_conf,
    render_unit,
)

# Deliberately synthetic: nothing here may appear in a published artifact, and
# nothing about the developer's machine may leak into a render made from these.
SYNTH = HarnessParams(
    agent="testbot",
    home=Path("/opt/agents/testbot"),
    python=Path("/opt/py/bin/python3"),
    macf_tools=Path("/opt/py/bin/macf_tools"),
    child_path=Path("/opt/agents/testbot/.local/bin/maceff_cc_child_testbot"),
    path_prepend=("/opt/py/bin", "/opt/agents/testbot/.local/bin"),
)


def _verify(unit_text, tmp_path):
    """Run systemd's own parser and return its complaints.

    Returns the captured output, NOT the exit status — see module docstring.
    """
    p = tmp_path / "cc-harness-testbot.service"
    p.write_text(unit_text)
    r = subprocess.run(["systemd-analyze", "verify", str(p)],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


needs_systemd = pytest.mark.skipif(
    shutil.which("systemd-analyze") is None, reason="systemd-analyze not available"
)


class TestUnitIsWellFormed:
    @needs_systemd
    def test_rendered_unit_passes_systemds_own_parser(self, tmp_path):
        assert _verify(render_unit(SYNTH), tmp_path) == ""

    @needs_systemd
    def test_rendered_unit_without_proxy_also_passes(self, tmp_path):
        assert _verify(render_unit(SYNTH, attach_proxy=False), tmp_path) == ""

    @needs_systemd
    def test_the_oracle_can_actually_fail(self, tmp_path):
        """Negative control on the oracle itself.

        Stripping the ExecStart= prefix is a real bug this caught during
        development: the exec line became an unknown key and the unit would
        never have started anything.
        """
        broken = render_unit(SYNTH).replace("ExecStart=/bin/bash", "/bin/bash")
        assert "Unknown key" in _verify(broken, tmp_path)

    def test_exec_start_is_present_and_prefixed(self):
        lines = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStart=")]
        assert len(lines) == 1


class TestProxyAndFirstPartyFlag:
    def test_flag_travels_in_the_same_assignment_as_the_base_url(self):
        """Their separation is what let the context-window defect survive months."""
        unit = render_unit(SYNTH)
        (exec_line,) = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
        assert "ANTHROPIC_BASE_URL=" in exec_line
        i = exec_line.index("ANTHROPIC_BASE_URL=")
        j = exec_line.index("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1")
        # Same quoted BASE assignment: the flag must follow the URL with nothing
        # but the URL's own value between them.
        assert 0 < j - i < 80, "flag is not in the same assignment as the base URL"

    def test_neither_appears_without_the_other(self):
        unit = render_unit(SYNTH)
        assert unit.count("ANTHROPIC_BASE_URL=") == unit.count("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1")

    def test_proxy_attachment_is_probed_not_assumed(self):
        """A dead proxy must degrade to a direct agent, never a dead one."""
        exec_line = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStart=")][0]
        assert 'BASE=""' in exec_line          # default is direct
        assert "curl" in exec_line             # attachment is conditional on a probe
        assert "--max-time" in exec_line       # and cannot hang the boot path

    def test_no_proxy_render_carries_no_base_url_at_all(self):
        unit = render_unit(SYNTH, attach_proxy=False)
        assert "ANTHROPIC_BASE_URL" not in unit
        assert "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL" not in unit
        assert "macf-proxy.service" not in unit
        assert 'BASE=""' in unit


class TestNoHostIdentifiersLeak:
    """Published artifacts carry no host identity. Verified by scan, not by eye."""

    @pytest.mark.parametrize("render", [
        lambda: render_unit(SYNTH),
        lambda: render_unit(SYNTH, attach_proxy=False),
        lambda: render_child(SYNTH),
        lambda: render_tmux_conf(SYNTH),
    ])
    def test_render_contains_only_supplied_parameters(self, render):
        text = render()
        real_home = str(Path.home())
        user = Path.home().name
        assert real_home not in text, "a render must contain no absolute home path"
        # The username as a path component is the tell; a bare substring match
        # would false-positive on ordinary words.
        assert f"/{user}/" not in text
        import socket
        assert socket.gethostname() not in text


class TestChildEntrypoint:
    def test_continuity_is_the_default(self):
        """An unattended restart that silently began a fresh session would
        discard the agent's context with nothing to show it had happened."""
        child = render_child(SYNTH)
        assert "exec claude -c" in child

    def test_child_is_a_shell_script(self):
        assert render_child(SYNTH).startswith("#!/bin/bash")

    def test_session_name_defaults_to_the_agent(self):
        assert 'MACEFF_TMUX_SESSION:-testbot' in render_child(SYNTH)


class TestStopTargetsTheSupervisor:
    def test_exec_stop_disables_the_supervisor_rather_than_killing_the_child(self):
        """Killing the child just makes the supervisor restart it, so a stop
        that targets the child is not a stop."""
        (stop,) = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStop=")]
        assert "auto-restart disable" in stop
        assert "kill" not in stop
