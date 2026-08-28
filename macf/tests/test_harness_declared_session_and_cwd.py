"""The harness must consume the declarations, not re-derive them.

Two values were declared in agents.yaml, documented, and consumed by nothing:
the tmux session name and the project directory. Both defects were invisible
for the same reason -- the derived value happened to equal the declared one for
one of two agents, so half the deployment worked and the working half read as
confirmation.

These tests therefore assert against the DECLARATION, never against what the
code currently produces. A test written the other way is what let the original
defect ship: a verifier asserted the session slug equalled the value the code
computed, which encoded the bug as the expected result.

The cwd tests RUN the generated script against a stub tmux rather than grepping
it, because the property is "the session starts in the declared directory" and
the text is only a proxy for that.
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

from macf.models.agent_spec import AgentSpec
from macf.utils.harness import HarnessParams, render_start


def _params(tmp_path, project_dir=None, agent="manny1"):
    return HarnessParams(
        agent=agent,
        home=tmp_path,
        python=Path("/usr/bin/python3"),
        macf_tools=Path("/usr/local/bin/macf_tools"),
        child_path=tmp_path / ".local" / "bin" / f"maceff_cc_child_{agent}",
        project_dir=project_dir,
    )


def _stub_tmux(bin_dir: Path, log: Path):
    """A tmux that records its arguments and refuses has-session.

    has-session must FAIL, or the start script short-circuits before the call
    under test and the test passes without exercising anything.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    tmux = bin_dir / "tmux"
    tmux.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "has-session" ]; then exit 1; fi\n'
        f'printf "%s\\n" "$*" >> {log}\n'
        "exit 0\n"
    )
    tmux.chmod(tmux.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    # curl is probed for the proxy; a stub keeps the test off the network.
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/bash\nexit 1\n")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmux


def _run_start(tmp_path, params):
    bin_dir = tmp_path / "stubbin"
    log = tmp_path / "tmux_args.log"
    _stub_tmux(bin_dir, log)
    script = tmp_path / "start.sh"
    script.write_text(render_start(params))
    script.chmod(0o700)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=env, cwd=str(tmp_path)
    )
    return proc, (log.read_text() if log.exists() else "")


# --- the declaration ------------------------------------------------------

def test_agent_spec_carries_the_declared_session_name():
    """The key exists on the model, so pydantic stops discarding it.

    This is the whole defect in one assertion: before the field existed the key
    was dropped at load with no warning, so a declaration that had been written
    deliberately and commented emphatically had no effect whatsoever.
    """
    spec = AgentSpec(
        username="pa_agent", personality="agents/p.md", harness_session="agent1"
    )
    assert spec.harness_session == "agent1"


def test_session_name_is_absent_rather_than_guessed_when_undeclared():
    """Omitted means None, so the CALLER decides the fallback.

    If the model defaulted to a derived value here, a deployment could never
    distinguish 'declared to equal the agent key' from 'not declared', which is
    the ambiguity that hid the original bug.
    """
    spec = AgentSpec(username="pa_agent", personality="agents/p.md")
    assert spec.harness_session is None


# --- the working directory, exercised rather than inspected ---------------

def test_declared_project_dir_reaches_tmux(tmp_path):
    """The session is created IN the declared directory."""
    proj = tmp_path / "workspace" / "Proj"
    proj.mkdir(parents=True)
    proc, tmux_args = _run_start(tmp_path, _params(tmp_path, project_dir=proj))
    assert proc.returncode == 0, proc.stderr
    new_session = [ln for ln in tmux_args.splitlines() if "new-session" in ln]
    assert new_session, f"tmux never received new-session: {tmux_args!r}"
    assert f"-c {proj}" in new_session[0], new_session[0]


def test_no_declared_dir_leaves_cwd_untouched(tmp_path):
    """Absent declaration must not invent one -- previous behaviour preserved."""
    proc, tmux_args = _run_start(tmp_path, _params(tmp_path, project_dir=None))
    assert proc.returncode == 0, proc.stderr
    new_session = [ln for ln in tmux_args.splitlines() if "new-session" in ln]
    assert new_session
    assert " -c " not in new_session[0], new_session[0]


def test_missing_declared_dir_warns_instead_of_substituting_silently(tmp_path):
    """A vanished directory is REPORTED.

    Falling back without a word is how `claude -c` resumes a different
    conversation than the agent was working in, with nothing to show a
    substitution occurred. The warning must name the conversation risk, because
    a bare 'directory not found' does not tell the reader what it costs.
    """
    missing = tmp_path / "gone"
    proc, tmux_args = _run_start(tmp_path, _params(tmp_path, project_dir=missing))
    assert proc.returncode == 0, proc.stderr
    assert str(missing) in proc.stderr
    assert "resume a DIFFERENT" in proc.stderr
    new_session = [ln for ln in tmux_args.splitlines() if "new-session" in ln]
    assert new_session
    assert " -c " not in new_session[0], new_session[0]
