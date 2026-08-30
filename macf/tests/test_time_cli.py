"""
Integration tests for time CLI command.

Tests the time command which provides temporal awareness.
Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_cli_env fixture to prevent
polluting production event logs with cli_command_invoked events.
"""

import subprocess
from datetime import datetime
import pytest


@pytest.fixture(autouse=True)
def isolated_cli_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production event logs.

    All CLI invocations emit cli_command_invoked events. Without isolation,
    tests pollute the production agent_events_log.jsonl file.

    This fixture is autouse=True so ALL tests in this module get isolation.
    """
    test_log = tmp_path / "test_cli_time.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


RECOGNISED_STDERR_PREFIXES = ('⚠️ MACF:', 'Last CCP:')


def unrecognised_stderr_lines(stderr):
    """stderr lines matching no known prefix.

    Extracted so it can be tested against synthetic input. Asserting on the real
    subprocess proves nothing when that subprocess emits no stderr at all -- an
    empty list then means "nothing to check", which is indistinguishable from
    "everything checked out". Found by mutating the prefix list and watching the
    test still pass.
    """
    return [
        line for line in (stderr or "").strip().split("\n")
        if line and not line.startswith(RECOGNISED_STDERR_PREFIXES)
    ]


class TestTimeCommand:
    """Test macf_tools time command."""

    def test_time_executes_successfully(self):
        """Test time command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert result.stdout.strip()  # Should produce output

    def test_time_outputs_iso8601_format(self):
        """Test time outputs valid ISO 8601 timestamp."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp = result.stdout.strip()

        # Should be parseable as ISO 8601
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            pytest.fail(f"Output '{timestamp}' is not valid ISO 8601 format")

    def test_time_includes_timezone(self):
        """Test time output includes timezone information."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp = result.stdout.strip()

        # ISO 8601 with timezone should have + or - offset
        assert '+' in timestamp or '-' in timestamp or timestamp.endswith('Z')

    def test_time_is_current(self):
        """Test time output is reasonably current (within 5 seconds)."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp_str = result.stdout.strip()
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now(timestamp.tzinfo)

        # Should be within 5 seconds of current time
        diff = abs((now - timestamp).total_seconds())
        assert diff < 5, f"Timestamp difference {diff}s exceeds 5s threshold"

    def test_time_no_error_output(self):
        """Test time command produces no unexpected error output.

        Note: MACF fallback warnings to stderr are expected when running
        in test environment without session events - these are informational,
        not errors. The checkpoint annotation is also expected there: stdout
        carries a machine-readable timestamp, so human-facing annotation goes
        to stderr by design rather than as a warning.
        """
        import os

        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Allow MACF informational warnings (fallback notices) and the
        # checkpoint annotation, but fail on actual Python errors/tracebacks.
        #
        # The assertion is NOT relaxed on purpose. It exists to catch a Python
        # traceback reaching stderr, and loosening it to make an unexplained
        # failure go away would remove the only thing that noticed.
        #
        # What is fixed here is the EVIDENCE. This failed once in a full-suite
        # run and has never reproduced; the run was captured with -q and the
        # offending line was lost, so every subsequent investigation had to work
        # from the fact that something unrecognised happened. A flake with no
        # artifact is a flake nobody can fix, and the moment of failure is the
        # only moment the artifact exists.
        unexpected = unrecognised_stderr_lines(result.stderr)
        assert not unexpected, (
            "unrecognised stderr from `macf_tools time`.\n"
            f"  offending lines : {unexpected}\n"
            "--- captured so the next person does not have to reproduce it ---\n"
            f"  returncode      : {result.returncode}\n"
            f"  full stderr     : {result.stderr!r}\n"
            f"  full stdout     : {result.stdout!r}\n"
            f"  cwd             : {os.getcwd()}\n"
            f"  MACEFF_AGENT_HOME_DIR : {os.environ.get('MACEFF_AGENT_HOME_DIR')!r}\n"
            f"  MACF_EVENTS_LOG_PATH  : {os.environ.get('MACF_EVENTS_LOG_PATH')!r}\n"
            f"  PYTHONWARNINGS        : {os.environ.get('PYTHONWARNINGS')!r}\n"
            "A leading candidate is an interpreter warning reaching stderr -- a\n"
            "DeprecationWarning from a deprecated call path would match neither\n"
            "prefix. If that is what the capture shows, name that warning\n"
            "specifically rather than widening the prefix list."
        )


class TestTimeKeepsStdoutMachineReadable:
    """The checkpoint annotation must not reach stdout.

    This class exists because the tests above could not reliably see the
    regression they were written to catch. `time` emits the annotation only when
    it resolves an agent root that actually holds checkpoints, and the resolver
    walks up from the CWD -- so whether the suite caught a broken contract was
    decided by which directory pytest happened to be started in. Run from the
    package: green. Run from a populated agent home: red, on the same commit.

    A test whose outcome depends on the caller's working directory is not
    pinning anything. Here the agent root is supplied explicitly and populated,
    so the annotation is guaranteed to be produced and the only open question is
    which stream it lands on.
    """

    @pytest.fixture
    def populated_agent_root(self, tmp_path, monkeypatch):
        """An agent root holding one checkpoint, selected explicitly."""
        checkpoints = tmp_path / "agent" / "private" / "checkpoints"
        checkpoints.mkdir(parents=True)
        (checkpoints / "2026-01-01_000000_Probe_ccp.md").write_text("# probe\n")
        monkeypatch.setenv("MACF_AGENT_ROOT", str(tmp_path / "agent"))
        return checkpoints

    def _run(self):
        return subprocess.run(['macf_tools', 'time'], capture_output=True, text=True)

    def test_the_annotation_is_actually_emitted(self, populated_agent_root):
        """Guards the guard: without this, the purity test below would pass
        vacuously on any commit where the annotation simply failed to resolve."""
        result = self._run()
        assert result.returncode == 0
        assert 'Last CCP:' in result.stderr, (
            "the checkpoint annotation was not produced at all, so the "
            "stdout-purity assertion below proves nothing"
        )

    def test_stdout_carries_only_the_timestamp(self, populated_agent_root):
        """The documented contract: one ISO-8601 timestamp, parseable whole."""
        result = self._run()
        assert result.returncode == 0
        assert 'Last CCP:' not in result.stdout
        datetime.fromisoformat(result.stdout.strip())


class TestStderrRecognition:
    """The recognition rule, tested against synthetic input.

    The subprocess assertion above cannot demonstrate this: on a machine where
    `macf_tools time` writes nothing to stderr, it passes without examining
    anything, and a broken rule would look identical to a clean run.
    """

    def test_a_traceback_line_is_unrecognised(self):
        stderr = 'Traceback (most recent call last):\n  File "x.py", line 1'
        assert unrecognised_stderr_lines(stderr) == [
            "Traceback (most recent call last):", '  File "x.py", line 1'
        ]

    def test_a_deprecation_warning_is_unrecognised(self):
        """The leading candidate for the one observed failure. A warning reaching
        stderr matches neither prefix, which is the correct answer -- the remedy
        would be to name that warning, not to widen the list."""
        stderr = "/path/mod.py:12: DeprecationWarning: read_events(limit=) is deprecated"
        assert len(unrecognised_stderr_lines(stderr)) == 1

    def test_the_expected_lines_are_recognised(self):
        """Both polarities. A rule that rejects everything is not a rule."""
        stderr = "⚠️ MACF: fallback in use\nLast CCP: 2 hours ago\n"
        assert unrecognised_stderr_lines(stderr) == []

    def test_empty_stderr_is_not_evidence_of_anything(self):
        """Documents the trap this class exists for: an empty result is the
        absence of input, not a passing check."""
        assert unrecognised_stderr_lines("") == []
        assert unrecognised_stderr_lines(None) == []
