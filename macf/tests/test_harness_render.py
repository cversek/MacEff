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

import os
import shutil
import subprocess
from pathlib import Path

import re
import socket

import pytest

from macf.utils.harness import (
    HarnessParams,
    render_child,
    render_launch_functions,
    render_start,
    render_tmux_conf,
    render_unit,
)

# Deliberately synthetic: nothing here may appear in a published artifact, and
# nothing about the developer's machine may leak into a render made from these.
# registry_dir is pinned too — its default is resolved from the real environment,
# and a test that renders the developer's own runtime path would both leak it and
# pass for the wrong reason.
SYNTH = HarnessParams(
    agent="testbot",
    home=Path("/opt/agents/testbot"),
    python=Path("/opt/py/bin/python3"),
    macf_tools=Path("/opt/py/bin/macf_tools"),
    child_path=Path("/opt/agents/testbot/.local/bin/maceff_cc_child_testbot"),
    registry_dir=Path("/run/testbot/macf/auto-restart"),
    path_prepend=("/opt/py/bin", "/opt/agents/testbot/.local/bin"),
)


def _code_only(text):
    """Drop comment lines.

    A concept named in a comment is a MENTION, not a USE. Without this, an
    assertion that some construct is absent fails on the comment explaining why
    it is absent — which would push an author to delete the explanation in order
    to satisfy the check.
    """
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _real_start(tmp_path):
    """SYNTH, but with a start script that exists on disk.

    ``systemd-analyze`` checks that ExecStart's binary is executable, and it
    became able to say so only once ExecStart stopped being ``/bin/bash -c``.
    Keeping the oracle strict is worth materialising the file for.
    """
    script = tmp_path / "maceff_harness_start_testbot"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    from dataclasses import replace
    return replace(SYNTH, start_path=script)


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
        assert _verify(render_unit(_real_start(tmp_path)), tmp_path) == ""

    @needs_systemd
    def test_rendered_unit_without_proxy_also_passes(self, tmp_path):
        assert _verify(render_unit(_real_start(tmp_path), attach_proxy=False), tmp_path) == ""

    @needs_systemd
    def test_the_oracle_can_actually_fail(self, tmp_path):
        """Negative control on the oracle itself.

        A misspelled directive is silently ignored by systemd — the unit loads,
        reports as configured, and starts nothing. That is the whole reason this
        file reads the oracle's OUTPUT instead of its exit status, which stays 0
        throughout.
        """
        broken = render_unit(_real_start(tmp_path)).replace("ExecStart=", "ExecStartt=")
        assert "Unknown key" in _verify(broken, tmp_path)

    @needs_systemd
    def test_the_oracle_notices_an_exec_start_that_cannot_run(self, tmp_path):
        """Second negative control, and the one that made this file honest.

        ExecStart used to be ``/bin/bash -c '<everything>'``, so systemd only
        ever checked that bash exists. Now that it names the start script
        directly, systemd verifies the real target — and a unit pointing at a
        script that was never installed is caught here rather than at boot.
        """
        assert "not executable" in _verify(render_unit(SYNTH), tmp_path)

    def test_exec_start_is_present_and_prefixed(self):
        lines = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStart=")]
        assert len(lines) == 1


class TestProxyAndFirstPartyFlag:
    """These invariants live in the start script now, because the launch decision
    does. They used to be asserted on the unit — while a second, unasserted copy
    of the same logic sat in the operator's shell profile and had already lost the
    flag. Asserting the invariant on one of two implementations is how it stayed
    lost; there is now only one place for it to hold."""

    def test_flag_travels_in_the_same_assignment_as_the_base_url(self):
        """Their separation is what let the context-window defect survive months."""
        (line,) = [l for l in render_start(SYNTH).splitlines()
                   if "ANTHROPIC_BASE_URL=" in l]
        i = line.index("ANTHROPIC_BASE_URL=")
        j = line.index("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1")
        # Same quoted BASE assignment: the flag must follow the URL with nothing
        # but the URL's own value between them.
        assert 0 < j - i < 80, "flag is not in the same assignment as the base URL"

    def test_neither_appears_without_the_other(self):
        start = render_start(SYNTH)
        assert start.count("ANTHROPIC_BASE_URL=") == start.count("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1")

    def test_proxy_attachment_is_probed_not_assumed(self):
        """A dead proxy must degrade to a direct agent, never a dead one."""
        start = render_start(SYNTH)
        assert 'BASE=""' in start          # default is direct
        assert "curl" in start             # attachment is conditional on a probe
        assert "--max-time" in start       # and cannot hang the boot path

    def test_no_proxy_render_carries_no_base_url_at_all(self):
        start = render_start(SYNTH, attach_proxy=False)
        assert "ANTHROPIC_BASE_URL" not in start
        assert "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL" not in start
        assert 'BASE=""' in start
        assert "macf-proxy.service" not in render_unit(SYNTH, attach_proxy=False)

    def test_the_unit_carries_no_launch_logic_of_its_own(self):
        """The regression that started this: two implementations, one of which
        had lost the flag. The unit must delegate, not re-implement."""
        unit = render_unit(SYNTH)
        assert "ANTHROPIC_BASE_URL" not in unit
        assert "tmux new-session" not in unit


class TestOneImplementationOfStarting:
    def test_exec_start_invokes_the_start_script(self):
        (exec_line,) = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStart=")]
        assert exec_line == f"ExecStart={SYNTH.start}"

    def test_shell_launch_calls_the_same_script(self):
        """A terminal launch and a boot launch must not be able to disagree."""
        assert str(SYNTH.start) in render_launch_functions(SYNTH)

    def test_shell_launch_does_not_create_a_session_itself(self):
        fns = render_launch_functions(SYNTH)
        assert "tmux new-session" not in fns, "the shell must delegate starting, not repeat it"

    def test_start_script_is_executable_shell(self):
        assert render_start(SYNTH).startswith("#!/bin/bash")


class TestIdentityIsNotTakenFromTheName:
    """The failure this rewrite exists to prevent: on 2026-07-29 an unrelated ssh
    login owned the tmux session name, `has-session` matched, and launch attached
    to a shell while the harness stayed down for days with nothing logged."""

    def test_the_registry_and_the_process_table_are_both_consulted(self):
        start = render_start(SYNTH)
        assert str(SYNTH.registry) in start        # registry: keyed by supervisor pid
        assert "kill -0" in start                  # an entry outlives its process
        assert "ps -o args=" in start              # and a pid can be recycled

    def test_a_present_but_foreign_session_is_refused_not_reused(self):
        start = render_start(SYNTH)
        assert "exit 3" in start
        assert "rename-session" in start, "the remedy must be named, not left to the reader"

    @pytest.mark.parametrize("render", [render_unit, render_start, render_launch_functions, render_child])
    def test_every_tmux_target_matches_the_session_exactly(self, render):
        """tmux resolves `-t name` by PREFIX. `-t thm` matches "thm-stale-ssh",
        which is the very name an operator gives the imposter while moving it
        aside — so the remedy for a name collision did not resolve it. Measured
        on tmux 3.6."""
        for line in _code_only(render(SYNTH)).splitlines():
            for marker in ("has-session -t ", "send-keys -t ", "attach -t ", "attach -d -t "):
                if marker in line:
                    target = line.split(marker, 1)[1].lstrip()
                    assert target.startswith(("=", '"=')), f"loose target in: {line.strip()}"

    def test_pgrep_is_not_used_for_liveness(self):
        """pgrep -f on the supervisor's command line matches the TMUX SERVER,
        which keeps that command in its own argv — it reported a live supervisor
        nine days after the supervisor exited (measured 2026-08-07). This is the
        same mistake as trusting the name, one level down."""
        assert "pgrep" not in _code_only(render_start(SYNTH))
        assert "pgrep" not in _code_only(render_launch_functions(SYNTH))


class TestRegistryPathIsResolvedNotRestated:
    """The registry moved from a shared /tmp path to a per-user one because the
    shared directory is owned by whichever uid creates it first. A stale copy of
    the old literal does not crash — it matches nothing, so `stop` stops nothing
    and `is it running` always answers no."""

    @pytest.mark.parametrize("render", [render_unit, render_start, render_launch_functions])
    def test_no_render_hardcodes_the_superseded_shared_path(self, render):
        assert "/tmp/macf/auto-restart" not in render(SYNTH)

    def test_stop_looks_where_the_supervisor_actually_writes(self):
        (stop,) = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStop=")]
        assert str(SYNTH.registry) in stop

    def test_the_default_comes_from_the_supervisor_itself(self):
        from macf.supervisor import REGISTRY_DIR
        unpinned = HarnessParams(
            agent="testbot", home=Path("/opt/agents/testbot"),
            python=Path("/opt/py/bin/python3"), macf_tools=Path("/opt/py/bin/macf_tools"),
            child_path=Path("/opt/agents/testbot/.local/bin/maceff_cc_child_testbot"),
        )
        assert unpinned.registry == REGISTRY_DIR


class TestNoHostIdentifiersLeak:
    """Published artifacts carry no host identity. Verified by scan, not by eye."""

    @pytest.mark.parametrize("render", [
        lambda: render_unit(SYNTH),
        lambda: render_unit(SYNTH, attach_proxy=False),
        lambda: render_start(SYNTH),
        lambda: render_start(SYNTH, attach_proxy=False),
        lambda: render_launch_functions(SYNTH),
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
        # Same hazard, and it bites: a host named "Mac" is a substring of
        # "MacEff" in the template's own header, so a bare `in` check fails on
        # that machine while passing on a CI runner whose hostname is long and
        # random. Match on word boundaries — "Mac" then no longer matches
        # "MacEff", while a genuine leak of the hostname as a token still does.
        assert not re.search(rf"\b{re.escape(socket.gethostname())}\b", text), (
            "a render must contain no host identifier"
        )


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

    def test_channels_are_absent_unless_declared(self):
        """No default: a guessed channel is a claim about reachability."""
        assert "--channels" not in _code_only(render_child(SYNTH))

    def test_declared_channels_reach_the_client(self):
        """Dropping these costs no error and no log line — the session comes up
        and the agent is simply unreachable, which is the worst way to fail for
        the unattended case the harness exists to serve."""
        from dataclasses import replace
        p = replace(SYNTH, channels=("plugin:a@x", "plugin:b@y"))
        (line,) = [l for l in render_child(p).splitlines() if l.startswith("exec claude")]
        assert line == 'exec claude -c --channels plugin:a@x,plugin:b@y "$@"'


needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not available")


@needs_tmux
class TestStartScriptBehaviour:
    """Run the rendered script rather than only reading it.

    Asserting on render text is how a scope defect shipped elsewhere in this
    codebase: every string assertion passed while the thing examined the wrong
    set. These tests execute the script against a private tmux server
    (TMUX_TMPDIR) and a private registry directory, so the outcomes are observed
    rather than inferred.
    """

    @pytest.fixture
    def sandbox(self, tmp_path):
        reg = tmp_path / "registry"
        reg.mkdir()
        sock = tmp_path / "tmuxdir"
        sock.mkdir()
        p = HarnessParams(
            agent="probe", home=tmp_path,
            python=Path("/bin/sleep"), macf_tools=Path("/bin/true"),
            child_path=Path("/bin/true"), registry_dir=reg,
        )
        script = tmp_path / "start"
        script.write_text(render_start(p, attach_proxy=False))
        script.chmod(0o755)
        env = {**os.environ, "TMUX_TMPDIR": str(sock)}
        yield script, reg, env
        subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)

    def _run(self, script, env):
        return subprocess.run([str(script)], env=env, capture_output=True, text=True)

    def _fake_supervisor(self, reg, name="probe"):
        """A process the guard should accept: alive, and looking like a
        supervisor to `ps`, registered under its own pid."""
        proc = subprocess.Popen(
            ["bash", "-c",
             f'exec -a "python3 -m macf.supervisor _run_loop --name {name}" sleep 30'])
        (reg / f"{proc.pid}.json").write_text(
            f'{{"supervisor_pid": {proc.pid}, "name": "{name}", "status": "running"}}')
        return proc

    def test_creates_a_session_when_nothing_holds_the_name(self, sandbox):
        script, _reg, env = sandbox
        r = self._run(script, env)
        assert r.returncode == 0
        assert "started session" in r.stdout

    def test_a_session_whose_name_merely_starts_with_the_agent_is_not_ours(self, sandbox):
        """The live regression: renaming the imposter to "<agent>-stale-ssh" did
        NOT free the name, because tmux matched it by prefix for nine more days."""
        script, _reg, env = sandbox
        subprocess.run(["tmux", "new-session", "-d", "-s", "probe-stale-ssh", "sleep 30"],
                       env=env, check=True)
        r = self._run(script, env)
        assert r.returncode == 0, r.stderr
        assert "started session" in r.stdout
        sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                                  env=env, capture_output=True, text=True).stdout.split()
        assert "probe" in sessions and "probe-stale-ssh" in sessions

    def test_refuses_a_session_name_held_by_something_else(self, sandbox):
        """THE regression. A name-only guard returns 'already running' here and
        the harness silently never starts."""
        script, _reg, env = sandbox
        subprocess.run(["tmux", "new-session", "-d", "-s", "probe", "sleep 30"],
                       env=env, check=True)
        r = self._run(script, env)
        assert r.returncode == 3
        assert "not this harness" in r.stderr
        # and it must not have started a second thing alongside the imposter
        panes = subprocess.run(["tmux", "list-panes", "-t", "probe", "-F", "#{pane_pid}"],
                               env=env, capture_output=True, text=True).stdout.split()
        assert len(panes) == 1

    def test_is_a_no_op_when_this_harness_is_already_up(self, sandbox):
        script, reg, env = sandbox
        proc = self._fake_supervisor(reg)
        try:
            subprocess.run(["tmux", "new-session", "-d", "-s", "probe", "sleep 30"],
                           env=env, check=True)
            r = self._run(script, env)
            assert r.returncode == 0
            assert "already running" in r.stdout
        finally:
            proc.kill(); proc.wait()

    def test_refuses_to_start_a_second_client_for_a_live_supervisor(self, sandbox):
        """One agent with two clients on one task store is the state BUG #66
        describes; a missing session is not a reason to add another."""
        script, reg, env = sandbox
        proc = self._fake_supervisor(reg)
        try:
            r = self._run(script, env)
            assert r.returncode == 3
            assert "session 'probe' is gone" in r.stderr
        finally:
            proc.kill(); proc.wait()

    def test_a_registry_entry_whose_process_died_does_not_count(self, sandbox):
        """Entries outlive their processes — the live host had seven of them,
        one 'running' for a supervisor that exited nine days earlier."""
        script, reg, env = sandbox
        proc = self._fake_supervisor(reg)
        proc.kill(); proc.wait()
        r = self._run(script, env)
        assert r.returncode == 0
        assert "started session" in r.stdout

    def test_an_entry_for_a_different_agent_does_not_count(self, sandbox):
        script, reg, env = sandbox
        proc = self._fake_supervisor(reg, name="someone-else")
        try:
            r = self._run(script, env)
            assert r.returncode == 0, "another agent's supervisor is not ours"
        finally:
            proc.kill(); proc.wait()


class TestInstallChoicesSurviveForTheNextCheck:
    """Channels and the shell prefix cannot be re-derived from the environment.

    If they are not recorded, a later flagless `install --check` renders
    DIFFERENT artifacts and reports drift that does not exist — and the natural
    response to that report, `--force`, would strip the channel and take the
    agent off the air with nothing to see. Observed on a live host before this
    was added.
    """

    def _p(self, tmp_path, **kw):
        from dataclasses import replace
        return replace(SYNTH, home=tmp_path, **kw)

    def test_a_flagless_render_reproduces_what_was_installed(self, tmp_path):
        from macf.utils.harness import load_settings, save_settings
        installed = self._p(tmp_path, channels=("plugin:tg@x",), shell_prefix="short")
        save_settings(installed)
        assert load_settings(self._p(tmp_path)) == installed

    def test_explicit_flags_still_win_over_the_record(self, tmp_path):
        from macf.utils.harness import load_settings, save_settings
        save_settings(self._p(tmp_path, channels=("old:one",), shell_prefix="old"))
        got = load_settings(self._p(tmp_path, channels=("new:one",), shell_prefix="new"))
        assert got.channels == ("new:one",) and got.shell_prefix == "new"

    def test_a_missing_or_corrupt_record_is_not_fatal(self, tmp_path):
        """A first install has no record, and a truncated one must not stop the
        harness from being reinstallable."""
        from macf.utils.harness import load_settings
        assert load_settings(self._p(tmp_path)).channels == ()
        p = self._p(tmp_path)
        p.settings_path.parent.mkdir(parents=True, exist_ok=True)
        p.settings_path.write_text("{not json")
        assert load_settings(p).channels == ()


class TestStopTargetsTheSupervisor:
    def test_exec_stop_disables_the_supervisor_rather_than_killing_the_child(self):
        """Killing the child just makes the supervisor restart it, so a stop
        that targets the child is not a stop."""
        (stop,) = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStop=")]
        assert "auto-restart disable" in stop
        assert "kill" not in stop
