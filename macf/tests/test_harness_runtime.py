"""Runtime tier: the harness as a SUBJECT, observed from outside itself.

Why this file exists, and why the existing tiers could not have caught the
defect that motivated it.

`test_harness_render.py` asserts on the TEXT the generator produces.
`test_harness_integration.py` EXECUTES the generated wrapper and asserts on the
argv it builds -- a real improvement, and it caught the variadic `--channels`
defect. But it runs the wrapper with `stdout=subprocess.DEVNULL` and no
controlling terminal, and those are precisely the two conditions under which a
wrapper that REDIRECTS the client's stdout is invisible. A test that has already
thrown the client's stdout away cannot notice that something else threw it away
first. The tier was structurally incapable of the finding, which is a different
thing from having missed it.

Two properties of this subsystem defeat in-situ debugging and dictate the shape
here:

1. **Observation participates.** Instrumenting the harness changes it. The
   logging added to diagnose a restart loop is itself a redirection of the
   client's stdout. The measuring device sits inside the circuit, so the only
   trustworthy measurement is one taken by a process that is not the subject.

2. **The debugger is the subject.** An agent debugging its own harness dies when
   the harness restarts, so it can never observe its own restart -- only read a
   log written by the process that died. Hypotheses cannot survive their own
   experiment.

So: a real tmux pane (so a terminal exists to be lost), the real supervisor, a
fake client that REPORTS what it actually received, and observation across
wall-clock time. A restart loop is a property of a SEQUENCE of starts; no
single-point observation can express one, which is how a loop got read as a
clean restart-in-place.

Fixtures are torn down unconditionally and strays are reaped at session start
and end -- a probe that outlives its probing is a tmux session nobody owns.
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from macf.utils.harness import HarnessParams, render_child

PROBE_PREFIX = "maceff-probe-"

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "tmux"], capture_output=True).returncode != 0,
    reason="runtime tier needs tmux: the property under test is the presence of a terminal",
)


def _tmux(*args, **kw):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, **kw)


def _live_probe_sessions():
    r = _tmux("list-sessions", "-F", "#{session_name}")
    if r.returncode != 0:
        return []
    return [s for s in r.stdout.split() if s.startswith(PROBE_PREFIX)]


def _reap():
    """Kill any probe session. Exact-match targeting (`=name`): tmux resolves a
    bare name as a prefix, so `kill-session -t maceff-probe` would also match a
    real agent session that happened to share the prefix."""
    for name in _live_probe_sessions():
        _tmux("kill-session", "-t", f"={name}")


@pytest.fixture(scope="session", autouse=True)
def _no_stray_probes():
    """Reap before and after the whole run, so a crashed test cannot leave a
    session running past the probing it belonged to."""
    _reap()
    yield
    _reap()


class Probe:
    """One isolated harness subject: its own tmux session, client, and spool."""

    def __init__(self, tmp_path):
        self.dir = tmp_path
        self.session = PROBE_PREFIX + uuid.uuid4().hex[:8]
        self.reports = tmp_path / "client_reports.jsonl"
        self.bin = tmp_path / "bin"
        self.bin.mkdir(exist_ok=True)
        self.macf_tools = tmp_path / "macf_tools"
        self.pane_marker = "PANE-MARKER-" + uuid.uuid4().hex[:8]

    def install_client(self, mode="stay", lifetime=0.5, exit_code=0):
        """A fake client that records the world it was handed, then behaves.

        `mode='stay'` holds the pane like a healthy interactive client.
        `mode='exit'` returns `exit_code` after `lifetime` -- the shape of a
        client that gives up cleanly, which is the case indistinguishable from
        an operator typing /exit.
        """
        client = self.bin / "claude"
        client.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, time\n"
            "rec = {\n"
            "    'argv': sys.argv[1:],\n"
            "    'stdin_tty': os.isatty(0),\n"
            "    'stdout_tty': os.isatty(1),\n"
            "    'stderr_tty': os.isatty(2),\n"
            "    'pid': os.getpid(),\n"
            "    'started': time.time(),\n"
            "}\n"
            f"with open({str(self.reports)!r}, 'a') as fh:\n"
            "    fh.write(json.dumps(rec) + '\\n')\n"
            "    fh.flush()\n"
            # Print to the PANE as well. The log test needs the client to
            # render something: driving the pane with send-keys and relying on
            # tty echo tests the terminal's line discipline, not whether the
            # CLIENT's output reaches the log, which is the property that
            # matters. A real client is never silent.
            f"print({self.pane_marker!r}, flush=True)\n"
            f"mode, lifetime, code = {mode!r}, {lifetime!r}, {exit_code!r}\n"
            "if mode == 'stay':\n"
            "    time.sleep(3600)\n"
            "time.sleep(lifetime)\n"
            "sys.exit(code)\n"
        )
        client.chmod(0o755)

        self.macf_tools.write_text(
            '#!/bin/bash\n[ "$1" = mode ] && echo MANUAL_MODE\nexit 0\n'
        )
        self.macf_tools.chmod(0o755)
        return client

    def render_wrapper(self):
        wrapper = self.dir / "child"
        wrapper.write_text(
            render_child(
                HarnessParams(
                    agent=self.session,
                    home=self.dir,
                    python=Path("/bin/true"),
                    macf_tools=self.macf_tools,
                    child_path=wrapper,
                    registry_dir=self.dir / "reg",
                )
            )
        )
        wrapper.chmod(0o755)
        return wrapper

    def start_pane(self, command):
        """Run `command` in a detached tmux session -- a real pane, therefore a
        real terminal on all three descriptors."""
        env = f'PATH={self.bin}:{os.environ["PATH"]}'
        _tmux("new-session", "-d", "-s", self.session,
              f"env {env} {command}")

    def records(self):
        if not self.reports.exists():
            return []
        return [json.loads(l) for l in self.reports.read_text().splitlines() if l.strip()]

    def wait_for_records(self, n, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self.records()) >= n:
                return self.records()
            time.sleep(0.25)
        return self.records()

    def kill(self):
        _tmux("kill-session", "-t", f"={self.session}")
        self._reap_descendants()

    def _reap_descendants(self):
        """Kill anything still running out of this probe's directory.

        Killing the tmux session reaps the PANE's child -- the supervisor --
        but not the supervisor's own children. The fake client is a grandchild,
        so it survived, reparented to init, and kept running after the test that
        made it had passed. Three were found alive on a developer machine at 56,
        28 and 16 minutes: one per full-suite run.

        Matching on the probe's tmp_path is what makes this safe to do with a
        signal. The path is unique per test, so nothing outside this probe can
        match it -- a name-based kill (`pkill -f claude`) would be a loaded gun
        pointed at the developer's real session.
        """
        marker = str(self.dir)
        try:
            out = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
        except (OSError, ValueError) as e:
            # Say it. A teardown that silently declines to reap is exactly the
            # failure this method exists to fix -- the leak would come back
            # looking like it had never been addressed.
            print(f"⚠️ probe: could not enumerate descendants to reap: {e}",
                  file=sys.stderr)
            return
        for line in out.stdout.split():
            try:
                pid = int(line)
            except ValueError:
                continue
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


@pytest.fixture
def probe(tmp_path):
    p = Probe(tmp_path)
    try:
        yield p
    finally:
        p.kill()


class TestTheFixtureIsolatesAndCleansUp:
    """The fixture is itself a subject. A probe that leaks sessions is worse
    than no probe: it makes the host's tmux state a function of test history."""

    def test_no_process_survives_teardown(self, tmp_path):
        """The sibling test covers tmux SESSIONS. Processes are a separate
        escape route and were leaking through it unwatched: tmux reaps the
        pane's child, not its grandchild, so the fake client outlived every run
        that started one."""
        p = Probe(tmp_path)
        p.install_client(mode="stay")
        # The SUPERVISOR form on purpose, not the wrapper. tmux reaps the pane's
        # child; the leak is the pane-child's OWN child. Running the client
        # directly in the pane creates no grandchild, so a test written that way
        # passes whether or not the reap works -- which is exactly what the first
        # version of this test did, in 0.77s, with the reap disabled.
        p.start_pane(
            f"/usr/bin/env python3 -m macf.supervisor _run_loop "
            f"--name {p.session} --delay 1 --tmux-session {p.session} "
            f"-- {p.bin}/claude"
        )
        p.wait_for_records(1)
        assert subprocess.run(["pgrep", "-f", f"{tmp_path}/bin/claude"],
                              capture_output=True).returncode == 0, (
            "the grandchild never started, so this test would prove nothing"
        )

        p.kill()

        deadline = time.time() + 5
        while time.time() < deadline:
            if subprocess.run(["pgrep", "-f", f"{tmp_path}/bin/claude"],
                              capture_output=True).returncode != 0:
                return
            time.sleep(0.25)
        leaked = subprocess.run(["pgrep", "-af", f"{tmp_path}/bin/claude"],
                                capture_output=True, text=True).stdout
        pytest.fail(f"processes survived teardown:\n{leaked}")

    def test_the_probe_runs_in_its_own_session(self, probe):
        probe.install_client(mode="stay")
        probe.start_pane(str(probe.render_wrapper()))
        probe.wait_for_records(1)
        assert probe.session in _live_probe_sessions()

    def test_no_probe_session_survives_teardown(self, tmp_path):
        p = Probe(tmp_path)
        p.install_client(mode="stay")
        p.start_pane(str(p.render_wrapper()))
        p.wait_for_records(1)
        assert p.session in _live_probe_sessions()
        p.kill()
        deadline = time.time() + 5
        while time.time() < deadline and p.session in _live_probe_sessions():
            time.sleep(0.2)
        assert p.session not in _live_probe_sessions()


class TestTheClientKeepsTheTerminalItWasGiven:
    """The defect this tier was built for.

    A tmux pane hands the child a terminal on all three descriptors. Anything
    the wrapper does to stdout before exec'ing the client is done to the
    client's terminal, and a terminal is not a detail -- it is what an
    interactive client checks to decide whether it is interactive at all.
    """

    def test_a_bare_pane_gives_the_client_a_terminal(self, probe):
        """Positive control. Without it, a failure below is unattributable:
        `stdout_tty is False` would be equally consistent with 'the wrapper
        redirected it' and 'this test never had a terminal to begin with'."""
        probe.install_client(mode="stay")
        probe.start_pane(f"{probe.bin}/claude --no-wrapper")
        recs = probe.wait_for_records(1)
        assert recs, "the client never ran; the probe, not the subject, is broken"
        assert recs[0]["stdout_tty"] is True
        assert recs[0]["stdin_tty"] is True

    def test_the_wrapper_does_not_take_the_terminal_away(self, probe):
        """The wrapper must not leave the client's stdout a pipe."""
        probe.install_client(mode="stay")
        probe.start_pane(str(probe.render_wrapper()))
        recs = probe.wait_for_records(1)
        assert recs, "the client never ran under the wrapper"
        assert recs[0]["stdout_tty"] is True, (
            "the wrapper replaced the client's stdout with a pipe. An "
            "interactive client that cannot see a terminal may decline to be "
            "interactive: it renders once and exits 0, which the supervisor "
            "correctly treats as a clean exit and restarts -- a loop in which "
            "no layer is misbehaving."
        )


class TestTheLogIsStillWritten:
    """Replacing a redirect with `pipe-pane` swapped a mechanism that certainly
    logged for one that might not.

    `tmux pipe-pane` fails quietly when its target does not resolve, and the
    wrapper appends `|| true` so a failure cannot take the session down. Both
    are correct choices and together they mean a broken pipe-pane is INVISIBLE:
    the client comes up, the pane looks right, and the log is simply empty.
    That is the same shape as the defect this whole tier exists for -- and the
    log is the only diagnostic surface for it, so losing it silently would cost
    the next investigation everything it cost this one.

    Removing an instrument is a change to the system; it needs its own test.
    """

    def test_pane_output_reaches_the_log(self, probe):
        probe.install_client(mode="stay")
        wrapper = probe.render_wrapper()
        log = probe.dir / ".maceff" / f"harness_{probe.session}.log"
        probe.start_pane(str(wrapper))
        probe.wait_for_records(1)

        # The client prints a unique marker to the pane. Assert on THAT rather
        # than on echoed keystrokes: send-keys plus tty echo would exercise the
        # terminal's line discipline, while the property under test is whether
        # the CLIENT's own output reaches the log.
        deadline = time.time() + 10
        while time.time() < deadline:
            if log.exists() and probe.pane_marker in log.read_text(errors="replace"):
                return
            time.sleep(0.25)

        contents = log.read_text(errors="replace") if log.exists() else "<no file>"
        pytest.fail(
            f"the client's output never reached {log}. pipe-pane fails quietly "
            f"and a log holding only the start banner looks exactly like a "
            f"working one.\n--- log contents ---\n{contents}"
        )

    def test_the_start_banner_is_recorded(self, probe):
        """Every launch appends a timestamped marker. The start SEQUENCE is what
        makes a restart loop legible, so this line is not decoration -- it is
        the primary evidence, and it was what finally distinguished a real loop
        (five starts in twenty-six seconds) from three isolated restarts."""
        probe.install_client(mode="stay")
        probe.start_pane(str(probe.render_wrapper()))
        probe.wait_for_records(1)
        log = probe.dir / ".maceff" / f"harness_{probe.session}.log"
        deadline = time.time() + 10
        while time.time() < deadline:
            if log.exists() and "starting:" in log.read_text(errors="replace"):
                return
            time.sleep(0.25)
        pytest.fail("no start marker was written; a loop would leave no trace")


class TestARestartLoopIsVisibleAsASequence:
    """A loop cannot be observed at a point. These assert on the SHAPE of the
    start sequence over time, which is the observation that was missing when a
    loop was read as a deliberate exit."""

    def test_a_healthy_client_is_started_exactly_once(self, probe):
        probe.install_client(mode="stay")
        probe.start_pane(
            f"/usr/bin/env python3 -m macf.supervisor _run_loop "
            f"--name {probe.session} --delay 1 --tmux-session {probe.session} "
            f"-- {probe.bin}/claude"
        )
        probe.wait_for_records(1)
        time.sleep(4)
        assert len(probe.records()) == 1, (
            f"a client that stays up was restarted: {probe.records()}"
        )

    def test_a_client_that_exits_zero_produces_a_detectable_loop(self, probe):
        """Negative control on the detector itself: plant the defect and
        require the observation to fire. A loop detector never seen to detect a
        loop is not a detector."""
        probe.install_client(mode="exit", lifetime=0.3, exit_code=0)
        probe.start_pane(
            f"/usr/bin/env python3 -m macf.supervisor _run_loop "
            f"--name {probe.session} --delay 1 --tmux-session {probe.session} "
            f"-- {probe.bin}/claude"
        )
        recs = probe.wait_for_records(3, timeout=25)
        assert len(recs) >= 3, (
            f"expected repeated starts from a client that exits 0; saw {len(recs)}"
        )
        span = recs[-1]["started"] - recs[0]["started"]
        assert span < 20, "starts should cluster; a loop is starts-per-time"
