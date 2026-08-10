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
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Allow MACF informational warnings (fallback notices) and the
        # checkpoint annotation, but fail on actual Python errors/tracebacks
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                assert line.startswith(('⚠️ MACF:', 'Last CCP:')) or not line, \
                    f"Unexpected stderr: {line}"


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
