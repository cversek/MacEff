"""A command that can never run must not be retried forever.

The supervisor treated every child exit the same: count it, wait, relaunch. But
restarting is a response to a process that FAILED, and a command that does not
exist has not failed — it was never launchable, and no number of retries changes
that.

Measured before this existed (2026-08-07, live host): with the child binary
removed, the loop reached three restarts in eight seconds, kept its registry
entry marked "running", and surfaced nothing. The shell's "command not found"
went to a tmux pane that had already gone, so from every status surface a
silently spinning harness was indistinguishable from a healthy one.

Found while verifying a claim that turned out to be wrong. Migrating the harness
to Calling-Card-derived names orphaned the old child wrapper; the argument for
deleting it was that a stale shell would then "fail loudly" instead of quietly
launching a degraded session. It did not fail loudly. The deletion was still
right, but the reasoning was not, and this is where the real defect lived.

The negative controls are the important half of this file: a child that
genuinely crashes must still be restarted, or the fix would have replaced an
infinite loop with a supervisor that gives up on the first hiccup.
"""

import json
import os
import queue
import subprocess
import threading
import time
import sys
import textwrap

import pytest

from macf.supervisor import _unlaunchable_reason


class TestUnlaunchableReason:
    def test_a_missing_path_is_reported_with_its_path(self, tmp_path):
        reason = _unlaunchable_reason([str(tmp_path / "nope")])
        assert reason and "does not exist" in reason
        assert str(tmp_path / "nope") in reason, "the message must name what is missing"

    def test_a_non_executable_path_is_distinguished_from_a_missing_one(self, tmp_path):
        f = tmp_path / "present"
        f.write_text("#!/bin/sh\n")
        f.chmod(0o644)
        reason = _unlaunchable_reason([str(f)])
        assert reason and "not executable" in reason

    def test_an_executable_path_is_launchable(self, tmp_path):
        f = tmp_path / "ok"
        f.write_text("#!/bin/sh\nexit 0\n")
        f.chmod(0o755)
        assert _unlaunchable_reason([str(f)]) is None

    def test_a_bare_word_is_never_refused_here(self):
        """The child runs through an interactive shell precisely so aliases and
        shell functions resolve. Refusing a bare word would break the
        indirection that invocation exists to provide — the shell gets to
        decide, and its verdict arrives as an exit code instead."""
        assert _unlaunchable_reason(["definitely_not_a_command_xyz"]) is None
        assert _unlaunchable_reason(["claude"]) is None

    def test_an_empty_command_is_refused(self):
        assert _unlaunchable_reason([]) is not None


def _run_supervisor(tmp_path, name, target, delay=1, timeout=20, until=None):
    """Run a real supervisor against an isolated registry; return (rc, output).

    ``until`` is a predicate over the output so far. When it is satisfied the
    supervisor is stopped immediately, and the wall clock stops deciding the
    result.

    Why that matters: a supervisor under test never exits on its own, so the
    old version always waited out the full timeout and a test asserting "at
    least N restarts" was really asserting "the machine managed N iterations in
    T seconds". That is a race, not a property, and it duly failed 3 times in 12
    observations while being unreproducible on demand. Waiting for the CONDITION
    removes the race rather than making it less likely; the timeout survives as
    the failure path, not the success path.
    """
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "macf.supervisor", "_run_loop",
         "--name", name, "--delay", str(delay), "--", target],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    lines, q = [], queue.Queue()

    def _pump():
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_pump, daemon=True).start()

    deadline = time.monotonic() + timeout
    satisfied = False
    while time.monotonic() < deadline:
        try:
            line = q.get(timeout=0.1)
        except queue.Empty:
            if proc.poll() is not None and q.empty():
                break
            continue
        if line is None:
            break
        lines.append(line)
        if until is not None and until("".join(lines)):
            satisfied = True
            break

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    while True:
        try:
            line = q.get_nowait()
        except queue.Empty:
            break
        if line is None:
            break
        lines.append(line)

    output = "".join(lines)
    # A supervisor stopped because the condition was met has no meaningful
    # return code -- it was killed mid-supervision. None says that, rather than
    # handing back a signal number a caller might read as a verdict.
    rc = None if (satisfied or proc.returncode is not None and proc.returncode < 0) else proc.returncode
    return rc, output


def _registry(tmp_path, name):
    d = tmp_path / "macf" / "auto-restart"
    for f in d.glob("*.json") if d.is_dir() else []:
        data = json.loads(f.read_text())
        if data.get("name") == name:
            return data
    return None


def _script(tmp_path, name, body):
    f = tmp_path / name
    f.write_text(textwrap.dedent(body))
    f.chmod(0o755)
    return str(f)


class TestSupervisorRefusesTheUnlaunchable:
    def test_a_missing_child_is_refused_before_anything_is_registered(self, tmp_path):
        """No registry entry: a supervisor that never supervised anything must
        not leave a record saying it is running."""
        rc, out = _run_supervisor(tmp_path, "t", str(tmp_path / "gone"))
        assert rc == 1, "a refusal must exit non-zero or the service manager reads it as success"
        assert "REFUSING TO START" in out
        assert _registry(tmp_path, "t") is None

    def test_an_unresolvable_command_stops_instead_of_spinning(self, tmp_path):
        """The case the pre-flight cannot see: the shell resolves the name, not
        the filesystem, so the verdict arrives as exit 127."""
        rc, out = _run_supervisor(tmp_path, "t", "definitely_not_a_command_xyz")
        assert rc == 1
        assert "FATAL" in out
        assert out.count("Restart #") == 0, "it must not have entered the restart loop"

    def test_giving_up_is_recorded_as_failed_not_stopped(self, tmp_path):
        """"stopped" means someone asked it to stop. Overwriting "failed" with
        it erases the only signal that says the supervisor could not run what it
        was given."""
        _run_supervisor(tmp_path, "t", "definitely_not_a_command_xyz")
        reg = _registry(tmp_path, "t")
        assert reg is not None
        assert reg["status"] == "failed"
        assert "not found" in reg.get("failure_reason", "")


class TestSupervisionStillWorks:
    """Negative controls. Without these the fix above could have replaced an
    infinite retry loop with a supervisor that quits at the first exit."""

    def test_a_child_that_genuinely_crashes_is_still_restarted(self, tmp_path):
        crasher = _script(tmp_path, "crasher", """\
            #!/bin/bash
            exit 1
            """)
        rc, out = _run_supervisor(
            tmp_path, "t", crasher, delay=1, timeout=30,
            until=lambda text: text.count("Restart #") >= 2,
        )
        assert out.count("Restart #") >= 2, (
            "supervision must survive a crashing child.\n"
            "--- captured at the moment of failure, so this is diagnosable ---\n"
            f"  restarts seen : {out.count('Restart #')}\n"
            f"  returncode    : {rc}\n"
            f"  full output   : {out!r}\n"
            "The runner now stops as soon as the condition is met, so reaching\n"
            "here means the restarts genuinely did not happen within 30s rather\n"
            "than that the machine was slow."
        )
        assert "FATAL" not in out

    def test_exit_127_from_a_long_lived_child_is_not_treated_as_never_launched(self, tmp_path):
        """A child is entitled to exit 127 as its own considered result. Pairing
        the code with the lifetime is what separates "the shell could not find
        it" from "the program ran and returned that"."""
        late = _script(tmp_path, "late", """\
            #!/bin/bash
            sleep 4
            exit 127
            """)
        rc, out = _run_supervisor(tmp_path, "t", late, delay=1, timeout=16)
        assert "FATAL" not in out
        assert out.count("Restart #") >= 1
