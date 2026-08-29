"""Headless launch: a container must be able to start a supervised session.

`auto-restart launch` had no working path on a host with no desktop terminal
emulator. It printed the tmux invocation that WOULD have worked and returned 1
-- output that reads exactly like success once a wrapper pipes it, which is how
a deployment came to report two agents started while starting none.

Two properties are under test and they are different:

  * a detached launch HAPPENS (tmux hosts the pane; no emulator is involved)
  * a decline is DISTINGUISHABLE from a failure, so a caller can tell
    "the supervisor died" from "here is what you could have typed"

The decline tests assert the exit CODE rather than the message, because the
code is what a wrapper branches on. Asserting only the text would pass on a
build that still returned 1 and printed nicer words -- the bug intact behind a
better error message.
"""

import shutil
import subprocess
import uuid

import pytest

from macf import supervisor
from macf.supervisor import EXIT_DECLINED, _launch_detached_tmux

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None, reason="tmux required for headless launch tests"
)


@pytest.fixture
def throwaway_session():
    """A uniquely-named tmux session, killed however the test ends.

    Unique because a fixed name collides with a real session on a developer's
    machine, and this test would then kill THAT.
    """
    name = f"macf-test-{uuid.uuid4().hex[:8]}"
    yield name
    subprocess.run(["tmux", "kill-session", "-t", f"={name}"],
                   capture_output=True)


# --- the primitive: does a session actually appear? -----------------------

def test_detached_launch_creates_a_real_session(throwaway_session):
    """The session EXISTS afterwards -- asked of tmux, not of our return value.

    A function that returns True is claiming a session was created; only tmux
    can confirm one was.
    """
    assert _launch_detached_tmux(throwaway_session, ["sleep", "30"]) is True
    found = subprocess.run(["tmux", "has-session", "-t", f"={throwaway_session}"],
                           capture_output=True)
    assert found.returncode == 0, "reported success but tmux has no such session"


def test_detached_launch_is_idempotent(throwaway_session):
    """Twice is not an error and does not stack a second session.

    Provisioning re-runs on every container start, so a second call must be
    survivable -- that is what `-A` buys.
    """
    assert _launch_detached_tmux(throwaway_session, ["sleep", "30"]) is True
    assert _launch_detached_tmux(throwaway_session, ["sleep", "30"]) is True
    listed = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True).stdout.split()
    assert listed.count(throwaway_session) == 1


def test_detached_launch_reports_failure_rather_than_claiming_success(monkeypatch):
    """tmux absent must be False, never True.

    The whole class of bug here is a launcher that reports having started
    something it did not.
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert _launch_detached_tmux("irrelevant", ["sleep", "30"]) is False


# --- the routing: what happens when no emulator exists --------------------

def _no_emulator(monkeypatch):
    """Simulate a headless host: every terminal lookup misses."""
    real = subprocess.run

    def fake(args, *a, **kw):
        if args and args[0] == "which":
            return subprocess.CompletedProcess(args, 1, "", "")
        return real(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", fake)


def test_headless_falls_back_to_detached_instead_of_declining(monkeypatch):
    """The bug itself: no emulator used to mean nothing started, exit 1.

    Falling back is safe to do automatically because this path ALREADY failed
    -- no working caller can reach it, so nothing can regress.
    """
    calls = []
    monkeypatch.setattr(supervisor, "_launch_detached_tmux",
                        lambda s, c: calls.append(s) or True)
    monkeypatch.setattr(supervisor, "_report_launch",
                        lambda *a, **kw: 4242)
    monkeypatch.setattr(supervisor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(supervisor.time, "sleep", lambda _: None)
    _no_emulator(monkeypatch)

    rc = supervisor.launch_in_terminal(["sleep", "30"], name="demo")

    assert calls, "headless host did not attempt a detached launch"
    assert rc != EXIT_DECLINED and rc != 1, f"reported a decline after starting: {rc}"


def test_declines_distinguishably_when_nothing_can_host(monkeypatch, capsys):
    """No emulator AND no tmux: exit code must not be a generic 1.

    A wrapper branches on the code. Returning 1 here is what let a script
    report a started agent and start none.
    """
    monkeypatch.setattr(supervisor, "_launch_detached_tmux", lambda s, c: False)
    monkeypatch.setattr(supervisor.platform, "system", lambda: "Linux")
    _no_emulator(monkeypatch)

    rc = supervisor.launch_in_terminal(["sleep", "30"], name="demo")

    assert rc == EXIT_DECLINED
    assert "NOTHING WAS STARTED" in capsys.readouterr().err


def test_detach_without_a_tmux_host_declines_rather_than_pretending(monkeypatch, capsys):
    """--detach with --no-tmux cannot work, and must say so rather than exit 0."""
    monkeypatch.setattr(supervisor.platform, "system", lambda: "Linux")
    rc = supervisor.launch_in_terminal(["sleep", "30"], name="demo",
                                       use_tmux=False, detach=True)
    assert rc == EXIT_DECLINED
    assert "Nothing was started" in capsys.readouterr().err


# --- the same host, the other command ------------------------------------

def test_harness_status_reports_missing_init_system_instead_of_raising(monkeypatch, capsys):
    """`harness status` on an init-less host must STATUS, not raise.

    The systemctl call used to throw FileNotFoundError into a broad handler
    that aborted the command, so a container operator lost the session, owner
    and proxy lines too -- the half of the report that does not depend on
    systemd at all, and the half they were asking for.

    Asserting the SESSION line is present is the real check: it proves the
    command ran PAST the systemctl call. Asserting only that no exception
    escaped would also pass if the function returned early in silence.
    """
    import argparse

    from macf import cli

    real_which = shutil.which
    monkeypatch.setattr(cli.shutil, "which",
                        lambda n: None if n == "systemctl" else real_which(n))

    rc = cli.cmd_harness_status(argparse.Namespace(agent="demo", home=None))
    out = capsys.readouterr().out

    assert rc == 0, "status aborted on a host with no init system"
    assert "no init system" in out
    assert "session:" in out, "aborted before the systemd-independent lines"


def test_decline_status_is_distinguishable_from_generic_failure():
    """Pin the LITERAL, because the requirement is about a specific number.

    The other tests here assert `rc == EXIT_DECLINED`, which is readable and
    tautological: it compares the code against itself, so redefining the
    constant moves the assertion with it. A mutation sweep proved that --
    setting `EXIT_DECLINED = 1` left every other test in this file GREEN while
    destroying the exact property the issue asks for, since 1 is what a
    crashed supervisor already returns.

    So this test states the requirement instead of the implementation: the
    decline code must not collide with generic failure, and it is 3 -- the
    value the generated maceff_harness_start already uses for "a decision for
    a human, not a retry". Changing it is a deliberate act that edits this
    line, not a silent one.
    """
    assert EXIT_DECLINED != 1, "a decline that returns 1 is indistinguishable from a crash"
    assert EXIT_DECLINED != 0, "a decline must not look like success"
    assert EXIT_DECLINED == 3


def test_successful_launch_exits_zero_not_the_pid(monkeypatch, tmp_path):
    """Success must be 0, because success WAS the supervisor's pid.

    Found by running the fix in a real headless container, not by a unit test:
    the launch worked, the session existed, and the command reported `EXIT: 56`
    -- the supervisor's pid used as a process exit status. Any caller written
    as `if macf_tools auto-restart launch ...` read a working launch as a
    failure, which defeats the distinguishable-decline this issue asks for:
    telling "started" from "declined" is meaningless while STARTED is already
    non-zero.

    It also fails silently in the worst direction. Exit statuses are masked to
    8 bits, so a pid of 256 would have reported 0 -- success by coincidence of
    arithmetic.
    """
    import json

    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "4242.json").write_text(json.dumps({"supervisor_pid": 4242}))
    monkeypatch.setattr(supervisor, "REGISTRY_DIR", reg)

    rc = supervisor._report_launch("demo", ["sleep", "30"], None, None,
                                   "demo-session", where="detached tmux session")
    assert rc == 0, f"a successful launch must exit 0, got {rc}"
