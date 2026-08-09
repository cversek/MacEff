"""Integration tests: RUN the rendered artifacts instead of reading them.

Every other test in this suite asserts on rendered *text*. That is a real gap
and it cost a live host an evening: a render can be textually perfect and
semantically invalid, and string assertions cannot tell the difference. Three
defects shipped through a fully green suite on 2026-08-07, and all three are the
same shape — *the command we generated does not do what the words suggest*:

1. ``claude -c`` with no prompt is REFUSED on some conversations ("No deferred
   tool marker found in the resumed session … Provide a prompt to continue"),
   exit 1, which the supervisor then retried forever.
2. ``--channels`` is VARIADIC, so a prompt placed after it was parsed as another
   channel: "--channels entries must be tagged: AUTO_MODE RESUME: …".
3. An f-string patch emitted ``\\\\`` where a line continuation was intended,
   silently truncating the tmux command.

None of those change whether an expected substring is present. All of them
change what the shell and the client actually receive.

The technique is a **stub on PATH**: a fake ``claude`` that records its argv and
exits. That makes the child wrapper's real argument construction observable —
quoting, ordering, and the empty-``$@`` case — offline, deterministically, and
without spending a single API call. What the stub cannot know is how the real
client PARSES that argv, so a second, skippable tier runs the real binary and
asserts it does not reject its own arguments.
"""

import json
import os
import subprocess
import shutil
from pathlib import Path

import pytest

from macf.utils.harness import HarnessParams, render_child


def _params(tmp_path, **kw):
    return HarnessParams(
        agent="probe",
        home=tmp_path,
        python=Path("/bin/true"),
        macf_tools=tmp_path / "macf_tools",
        child_path=tmp_path / "child",
        registry_dir=tmp_path / "reg",
        **kw,
    )


def _install_stubs(tmp_path, mode_output="MANUAL_MODE"):
    """A bin/ containing a fake `claude` that records argv, and a fake macf_tools."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    argv_file = tmp_path / "argv.json"

    claude = bin_dir / "claude"
    claude.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(argv_file)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    claude.chmod(0o755)

    # The child invokes macf_tools by ABSOLUTE path ($MACF = p.macf_tools), so
    # a stub on PATH is never consulted. Write it where the child will look --
    # found when the AUTO_MODE test received the MANUAL prompt.
    macf = tmp_path / "macf_tools"
    macf.write_text(f"#!/bin/bash\n[ \"$1\" = mode ] && echo {mode_output}\nexit 0\n")
    macf.chmod(0o755)
    return bin_dir, argv_file


def _run_child(tmp_path, p, mode_output="MANUAL_MODE", args=()):
    """Render the child wrapper, run it against stubs, return the argv it built."""
    bin_dir, argv_file = _install_stubs(tmp_path, mode_output)
    child = tmp_path / "child"
    child.write_text(render_child(p))
    child.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    # DEVNULL, not capture_output: the wrapper backgrounds a trust-prompt nudge
    # (`sleep 18; tmux send-keys ...`) that inherits stdout. With a pipe,
    # subprocess.run waits ~20s for EOF from a process we do not care about --
    # which stalled this whole file past pytest's timeout and looked like a
    # hang. Diagnosed by running one child outside pytest with a stopwatch:
    # argv was recorded instantly, the wait was all pipe.
    subprocess.run([str(child), *args], env=env, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads(argv_file.read_text())


class TestTheChildBuildsTheArgvItMeansTo:
    def test_a_prompt_is_actually_passed(self, tmp_path):
        """Defect 1: a resume with no prompt can be refused outright, and the
        supervisor retries the refusal forever."""
        argv = _run_child(tmp_path, _params(tmp_path))
        assert "-c" in argv
        prompts = [a for a in argv if not a.startswith("-") and " " in a]
        assert prompts, f"no prompt-like argument in {argv}"

    def test_the_prompt_is_one_argument_not_shattered_by_quoting(self, tmp_path):
        """A prompt has spaces. Losing the quotes turns it into a dozen
        positional arguments, which no string assertion would notice."""
        argv = _run_child(tmp_path, _params(tmp_path))
        multiword = [a for a in argv if len(a.split()) > 3]
        assert len(multiword) == 1, f"prompt is not a single argument: {argv}"

    def test_channels_receive_only_the_channel(self, tmp_path):
        """Defect 2, exactly. `--channels` is variadic; the prompt must not land
        in it. This is the assertion that was missing when the client died with
        "--channels entries must be tagged: AUTO_MODE RESUME: …"."""
        p = _params(tmp_path, channels=("plugin:tg@mkt",))
        argv = _run_child(tmp_path, p)
        i = argv.index("--channels")
        consumed = argv[i + 1:]
        assert consumed == ["plugin:tg@mkt"], \
            f"--channels swallowed more than its value: {consumed}"

    def test_the_mode_selects_the_prompt(self, tmp_path):
        auto = _run_child(tmp_path, _params(tmp_path), mode_output="AUTO_MODE")
        manual = _run_child(tmp_path, _params(tmp_path), mode_output="MANUAL_MODE")
        assert any("AUTO_MODE RESUME" in a for a in auto)
        assert not any("AUTO_MODE RESUME" in a for a in manual)

    def test_extra_arguments_survive(self, tmp_path):
        """`"$@"` is empty in practice, so a mistake there is invisible until the
        day it is not."""
        argv = _run_child(tmp_path, _params(tmp_path), args=("--verbose",))
        assert "--verbose" in argv

    def test_no_channels_configured_still_produces_a_valid_invocation(self, tmp_path):
        argv = _run_child(tmp_path, _params(tmp_path))
        assert "--channels" not in argv
        assert "-c" in argv

    def test_the_child_writes_its_log(self, tmp_path):
        """The log is what made defect 1 findable; if it silently stopped being
        written, the next failure goes back to being invisible."""
        p = _params(tmp_path)
        _run_child(tmp_path, p)
        assert p.log_path.exists(), "the child produced no log"
        assert "starting:" in p.log_path.read_text()


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude client not installed")
class TestTheRealClientAcceptsWhatWeGenerate:
    """The stub proves what argv we BUILD; only the real binary proves it PARSES.

    Run in an empty directory so `-c` has nothing to resume: the client then
    exits on its own without a conversation, and any *usage* error it prints is
    about our arguments rather than about the session. Skipped where the client
    is absent, so CI without it stays green — but on a developer machine this is
    the test that would have caught the variadic-flag defect in seconds.
    """

    def _usage_error(self, tmp_path, argv):
        """Return the client's usage complaint, or None if it had none.

        The asymmetry is the test: a usage error is printed and the process
        exits AT ONCE, while a valid invocation goes on to run. So a timeout is
        a PASS signal, not a failure — it means the arguments were accepted and
        the client got as far as doing work. stdin is closed so a client that
        does start cannot sit waiting on input forever.
        """
        try:
            r = subprocess.run(["claude", *argv], cwd=tmp_path, capture_output=True,
                               text=True, timeout=20, stdin=subprocess.DEVNULL)
            out = r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or b"") + (e.stderr or b"")).decode(errors="replace")
        for marker in ("must be tagged", "unknown option", "unrecognized",
                       "Invalid", "usage:"):
            if marker.lower() in out.lower():
                return out.strip().splitlines()[0]
        return None

    def test_the_generated_argument_order_is_accepted(self, tmp_path):
        work = tmp_path / "empty"
        work.mkdir()
        err = self._usage_error(work, [
            "-c", "AUTO_MODE RESUME: this session restarted.",
            "--channels", "plugin:telegram@claude-plugins-official"])
        assert err is None, f"the client rejected our own arguments: {err}"

    def test_the_order_we_replaced_really_was_rejected(self, tmp_path):
        """Negative control. Without it, the test above passes for any order —
        including one the client happens to tolerate — and proves nothing."""
        work = tmp_path / "empty2"
        work.mkdir()
        err = self._usage_error(work, [
            "-c", "--channels", "plugin:telegram@claude-plugins-official",
            "AUTO_MODE RESUME: this session restarted."])
        assert err is not None and "must be tagged" in err, \
            "the old broken order was NOT rejected — this check proves nothing"
