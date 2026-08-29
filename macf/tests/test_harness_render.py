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
    @pytest.mark.live
    @needs_systemd
    def test_rendered_unit_passes_systemds_own_parser(self, tmp_path):
        assert _verify(render_unit(_real_start(tmp_path)), tmp_path) == ""

    @pytest.mark.live
    @needs_systemd
    def test_rendered_unit_without_proxy_also_passes(self, tmp_path):
        assert _verify(render_unit(_real_start(tmp_path), attach_proxy=False), tmp_path) == ""

    @pytest.mark.live
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

    @pytest.mark.live
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

    def test_no_unguarded_array_expansion_under_set_u(self):
        """Under `set -u`, bash 3.2 aborts on an EMPTY array's `[@]` expansion;
        bash 4.4+ does not. macOS ships 3.2 and the shebang names /bin/bash, so
        the unguarded form kills every launch on macOS that declares no project
        dir — the default. Linux CI runs bash 5 and cannot reproduce it.

        That asymmetry is why this is a STATIC check rather than an execution
        test: the runtime failure is invisible in the only environment that runs
        automatically, so the control has to be one that CI can still fail on.

        The guarded form is `${name[@]+"${name[@]}"}`.
        """
        pattern = re.compile(r'"\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\}"')
        guarded = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\+')

        inspected = 0
        for render in (render_unit, render_start, render_launch_functions, render_child):
            text = render(SYNTH)
            if "set -u" not in text:
                continue
            inspected += 1
            for line in _code_only(text).splitlines():
                for m in pattern.finditer(line):
                    assert guarded.search(line), (
                        f"unguarded ${{{m.group(1)}[@]}} under `set -u` — aborts on "
                        f"bash 3.2 when empty. Write ${{{m.group(1)}[@]+\"${{{m.group(1)}[@]}}\"}}. "
                        f"Line: {line.strip()}"
                    )

        # Without this the test passes by examining nothing the day someone drops
        # `set -u`, and a green result would mean only that the loop never ran.
        assert inspected, "no rendered script carried `set -u`; this check inspected nothing"


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
        # "$PROMPT" trails deliberately — a resume with no prompt can be refused
        # outright; see TestAResumeCarriesAPrompt.
        assert line == 'exec claude -c "$PROMPT" "$@" --channels plugin:a@x,plugin:b@y'


needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not available")


@pytest.mark.live
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
    def sandbox(self, tmp_path, tmux_sandbox_env):
        reg = tmp_path / "registry"
        reg.mkdir()
        p = HarnessParams(
            agent="probe", home=tmp_path,
            python=Path("/bin/sleep"), macf_tools=Path("/bin/true"),
            child_path=Path("/bin/true"), registry_dir=reg,
        )
        script = tmp_path / "start"
        script.write_text(render_start(p, attach_proxy=False))
        script.chmod(0o755)
        # The env, its private socket directory, and the destructive
        # `kill-server` teardown all belong to the `tmux_sandbox_env` fixture in
        # conftest. Read its docstring before changing anything about how tmux
        # is reached from here: it carries the reasons for two non-obvious
        # choices that were each paid for once -- $TMUX stripped (an inherited
        # one made this fixture's teardown destroy the live agent harness on
        # this host) and PATH inherited (a from-scratch env cannot find tmux
        # under Homebrew, so the whole class crashed on macOS).
        yield script, reg, tmux_sandbox_env

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

    def test_the_sandbox_env_is_private_and_can_still_find_tmux(self, sandbox):
        """Blast-radius guard, and the most important test in this class.

        This fixture tears down with `tmux kill-server`. That is only survivable
        because the env selects a private server, and it selects one ONLY while
        $TMUX is absent -- an inherited $TMUX silently overrides TMUX_TMPDIR and
        points every client at the host's server. Restoring the natural
        `{**os.environ, ...}` spelling would make this class destroy the live
        agent harness again, with a green suite in CI to say it was fine.

        The PATH half is the opposite mistake and was made next: an env built
        from scratch is private but cannot find the tmux binary anywhere off the
        POSIX fallback path, so the whole class crashed on macOS while CI stayed
        green. Both halves are asserted here because a fix for either one alone
        reintroduces the other.

        Asserted on the env rather than by running the destructive path, so the
        guard costs nothing and cannot itself be the thing that goes wrong.
        """
        _script, _reg, env = sandbox
        assert "TMUX" not in env, (
            "the sandbox env inherited $TMUX; tmux will ignore TMUX_TMPDIR, this "
            "fixture's kill-server will run against the host, and every session "
            "on it -- including a live agent harness -- will be destroyed"
        )
        assert env.get("TMUX_TMPDIR"), "the private socket dir must still be set"
        assert env.get("PATH"), (
            "the sandbox env carries no PATH; the subprocess will fall back to "
            f"{os.confstr('CS_PATH')!r} and will not find tmux anywhere else -- "
            "which is every Homebrew install"
        )
        # The socket-path length invariant is asserted in the fixture itself,
        # where it covers every consumer rather than only this class.

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
        # Assert only what this test is about: the imposter was NOT mistaken for
        # ours and was left alone. Whether the newly created pane still exists a
        # moment later is tmux pane lifetime, not the guard -- asserting it made
        # this test flaky, which is worse than not asserting it.
        sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                                  env=env, capture_output=True, text=True).stdout.split()
        assert "probe-stale-ssh" in sessions

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


class TestAFailedLaunchStaysReadable:
    """A launch you cannot diagnose costs more than a launch that fails.

    Three failures in one evening printed their explanation into a tmux pane
    that vanished the instant the command exited, leaving nothing but `[exited]`
    and a shell prompt. The message existed; nobody could read it.
    """

    def test_the_pane_survives_its_command(self):
        assert "remain-on-exit on" in render_start(SYNTH)

    def test_remain_on_exit_targets_the_session_exactly(self):
        """Prefix matching again: setting the option on the wrong session
        would leave the real one vanishing exactly as before."""
        (line,) = [l for l in _code_only(render_start(SYNTH)).splitlines()
                   if "remain-on-exit" in l]
        assert '-t "=$SESSION"' in line

    def test_the_child_keeps_its_own_log(self):
        child = render_child(SYNTH)
        assert str(SYNTH.log_path) in child
        assert "pipe-pane" in child

    def test_the_child_logs_without_touching_the_clients_descriptors(self):
        """This test previously asserted the DEFECT as a requirement.

        It demanded `exec > >(tee -a ...)`, reasoning that a plain redirect
        would blank the pane and a `| tee` pipeline would make the supervisor
        wait on tee instead of the client. Both halves of that were true, and
        the conclusion was still wrong: process substitution avoids the
        pipeline but still replaces the client's stdout with a PIPE, and an
        interactive client deprived of a terminal can render one turn and exit
        0 -- producing a restart loop with no error in any log.

        The deeper mistake is the shape of the old assertion. Pinning a literal
        line of shell pins an IMPLEMENTATION; the property that actually
        matters -- the client still has a terminal -- is not visible in the
        source at all. It is measured in tests/test_harness_runtime.py, which
        runs the wrapper in a real pane and asks the client what it received.
        Keep this test negative and thin; the positive claim lives there.
        """
        child = _code_only(render_child(SYNTH))
        assert "exec claude" in child
        assert "exec >" not in child, (
            "the wrapper must not redirect the client's stdout; log the pane "
            "from outside with tmux pipe-pane"
        )
        assert "| tee" not in child, "a pipeline would hide the client's exit from the supervisor"
        assert "pipe-pane" in child

    def test_no_blind_keystrokes_are_sent_on_launch(self):
        """An unattended Enter accepts whatever is focused, not the prompt we
        had in mind. Startup dialogs are not stable across client versions, and
        a resume dialog defaulting to 'summarize' would silently discard the
        session's context with nothing recording that a choice was made."""
        child = _code_only(render_child(SYNTH))
        assert "send-keys" not in child, (
            "first launch is the operator's to answer; a menu a human has not "
            "seen is a menu a machine must not answer"
        )

    def test_the_launcher_says_where_the_log_is(self):
        assert str(SYNTH.log_path) in render_start(SYNTH)


class TestAResumeCarriesAPrompt:
    """`claude -c` with no prompt can refuse to resume and exit 1.

    Measured A/B on one conversation, same minute: without a prompt the client
    printed "No deferred tool marker found in the resumed session ... Provide a
    prompt to continue the conversation" and exited 1, every time; with a prompt
    it came up. The supervisor then did the right thing with exit 1 — retry —
    which turned an unsatisfiable command into an unbounded loop.
    """

    def test_the_client_is_given_an_initial_prompt(self):
        (line,) = [l for l in render_child(SYNTH).splitlines() if l.startswith("exec claude")]
        assert '"$PROMPT"' in line, "a resume with no prompt can be refused outright"

    def test_the_prompt_does_not_follow_a_variadic_flag(self):
        """`--channels` keeps consuming following words. A prompt placed after it
        is parsed as another channel and the client dies with "--channels entries
        must be tagged: <your prompt>" — which is what happened, in a restart
        loop, on a live host. The variadic flag must come last, where the only
        thing left to consume is its own values."""
        from dataclasses import replace
        p = replace(SYNTH, channels=("plugin:a@x",))
        (line,) = [l for l in render_child(p).splitlines() if l.startswith("exec claude")]
        assert line.index('"$PROMPT"') < line.index("--channels"), \
            "the prompt must precede the variadic flag"
        assert line.rstrip().endswith("plugin:a@x"), \
            "--channels must be last so nothing follows it to be swallowed"

    def test_the_prompt_is_never_empty(self):
        """An empty string would satisfy the shell and not the client."""
        child = _code_only(render_child(SYNTH))
        assigns = [l for l in child.splitlines() if l.strip().startswith("PROMPT=")]
        assert len(assigns) >= 2, "expected a mode-aware prompt with a fallback"
        for a in assigns:
            value = a.split("=", 1)[1].strip().strip('"')
            assert len(value) > 10, f"empty or trivial prompt: {a}"

    def test_the_prompt_depends_on_the_mode(self):
        child = render_child(SYNTH)
        assert "mode get" in child
        assert "AUTO_MODE RESUME" in child

    def test_the_send_keys_timing_hack_is_gone(self):
        """It guessed when the client was ready, and could not rescue a resume
        that never started. The initial prompt does the same job unconditionally."""
        child = _code_only(render_child(SYNTH))
        assert "AUTO_MODE RESUME" not in child.split("PROMPT=")[0], \
            "the re-orientation must arrive as the initial prompt, not via send-keys"


class TestWatchdogIsOptInAndSafe:
    """The supervisor is a child of the tmux server, so it dies with it, and the
    boot unit is oneshot+RemainAfterExit — systemd neither notices nor acts.
    The watchdog re-runs the already-idempotent start script on a timer."""

    def test_it_reuses_the_one_start_script(self):
        from macf.utils.harness import render_watchdog
        svc, _timer = render_watchdog(SYNTH)
        assert f"ExecStart={SYNTH.start}" in svc, "a second implementation would defeat the point"

    def test_the_timer_targets_the_watch_unit_not_the_boot_unit(self):
        from macf.utils.harness import render_watchdog
        _svc, timer = render_watchdog(SYNTH)
        assert f"Unit=cc-harness-{SYNTH.agent}-watch.service" in timer
        assert "OnUnitActiveSec" in timer

    @pytest.mark.live
    @needs_systemd
    def test_both_units_pass_systemds_own_parser(self, tmp_path):
        from dataclasses import replace
        from macf.utils.harness import render_watchdog
        script = tmp_path / "start"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        svc, timer = render_watchdog(replace(SYNTH, start_path=script))
        for name, text in ((f"cc-harness-testbot-watch.service", svc),
                           (f"cc-harness-testbot-watch.timer", timer)):
            p = tmp_path / name
            p.write_text(text)
            r = subprocess.run(["systemd-analyze", "verify", str(p)],
                               capture_output=True, text=True)
            assert (r.stdout + r.stderr).strip() == "", f"{name}: {(r.stdout + r.stderr).strip()}"


class TestStopTargetsTheSupervisor:
    def test_exec_stop_disables_the_supervisor_rather_than_killing_the_child(self):
        """Killing the child just makes the supervisor restart it, so a stop
        that targets the child is not a stop."""
        (stop,) = [l for l in render_unit(SYNTH).splitlines() if l.startswith("ExecStop=")]
        assert "auto-restart disable" in stop
        assert "kill" not in stop
