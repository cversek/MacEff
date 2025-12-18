"""
Shared test fixtures and configuration for macf_tools test suite.

This module provides common fixtures, utilities, and configuration for all tests.
It follows pytest best practices for sharing test resources and maintaining
test isolation while providing realistic test environments.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from click.testing import CliRunner

# Test data constants
SAMPLE_SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
SAMPLE_AGENT_NAME = "TestAgent"
SAMPLE_TIMEZONE = "America/New_York"


@pytest.fixture(scope="session")
def test_data_dir():
    """Provide path to test data directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def cli_runner():
    """Provide Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_datetime():
    """Provide consistent datetime for testing."""
    test_time = datetime(2024, 3, 15, 14, 30, 45, tzinfo=timezone.utc)

    with patch('macf.cli.datetime') as mock_dt:
        mock_dt.now.return_value = test_time
        mock_dt.now.return_value.isoformat.return_value = test_time.isoformat()
        mock_dt.now.return_value.replace.return_value = test_time
        yield test_time


@pytest.fixture
def clean_temp_dir(tmp_path):
    """Provide clean temporary directory that gets cleaned up."""
    temp_dir = tmp_path / "macf_test"
    temp_dir.mkdir()

    # Ensure cleanup
    yield temp_dir

    # Cleanup happens automatically with tmp_path


@pytest.fixture(autouse=True)
def isolated_events_log(tmp_path, monkeypatch):
    """
    Isolate event logging to prevent test pollution of production JSONL.

    This fixture automatically applies to ALL tests (autouse=True) to ensure
    test events never pollute the production agent_events_log.jsonl file.

    The isolation prevents issues like:
    - Test session_ids appearing in production queries
    - Test prompt_uuids corrupting breadcrumb generation
    - Cross-test event pollution
    - Subprocess hooks writing to production log (CRITICAL)

    CRITICAL: Sets BOTH in-process path AND environment variable.
    - set_log_path(): For in-process code
    - MACF_EVENTS_LOG_PATH: For subprocess hooks (inherited by child processes)

    Yields:
        Path to isolated test events log
    """
    from macf.agent_events_log import set_log_path

    # Create isolated log path
    test_log = tmp_path / "test_events_log.jsonl"

    # Set in-process isolation
    set_log_path(test_log)

    # Set environment variable for subprocess isolation (CRITICAL for hook tests)
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))

    yield test_log

    # Reset to default (production) path after test (monkeypatch auto-resets env vars)
    set_log_path(None)


@pytest.fixture
def mock_environment_detection():
    """Mock environment detection utilities."""
    detection_mocks = {}

    with patch('os.path.exists') as mock_exists:
        with patch('pathlib.Path.cwd') as mock_cwd:
            with patch('pathlib.Path.home') as mock_home:
                detection_mocks['exists'] = mock_exists
                detection_mocks['cwd'] = mock_cwd
                detection_mocks['home'] = mock_home

                yield detection_mocks


class MockConsciousnessConfig:
    """Mock consciousness configuration for testing."""

    def __init__(self, agent_name=None, agent_root=None, settings=None):
        self.agent_name = agent_name or SAMPLE_AGENT_NAME
        self.agent_root = agent_root or Path(f"/tmp/test/{self.agent_name}/agent")
        self.settings = settings or self._default_settings()
        self._detection_performed = agent_name is None

    def _default_settings(self):
        return {
            "consciousness": {
                "session_retention_days": 7,
                "checkpoint_format": "structured"
            },
            "paths": {
                "temp_dir": "/tmp/macf",
                "logs_dir": "logs"
            },
            "features": {
                "reflection_enabled": True,
                "strategic_checkpoints": True
            }
        }

    def _detect_agent(self):
        return self.agent_name

    def _find_agent_root(self):
        return self.agent_root

    def _load_settings(self):
        return self.settings


@pytest.fixture
def mock_consciousness_config(tmp_path):
    """Provide mock consciousness configuration."""
    agent_root = tmp_path / "agent"
    agent_root.mkdir()

    # Create directory structure
    for subdir in ["public", "private"]:
        subdir_path = agent_root / subdir
        subdir_path.mkdir()

        # Create logs subdirectory
        (subdir_path / "logs").mkdir()

        # Create checkpoints subdirectory
        (subdir_path / "checkpoints").mkdir()

    config = MockConsciousnessConfig(agent_root=agent_root)

    with patch('macf.config.ConsciousnessConfig', return_value=config):
        yield config


@pytest.fixture
def sample_toml_config():
    """Provide sample TOML configuration content."""
    return """
[consciousness]
session_retention_days = 7
checkpoint_format = "structured"
reflection_triggers = ["delegation", "error", "milestone"]

[paths]
temp_dir = "/tmp/macf"
logs_dir = "logs"
checkpoints_dir = "checkpoints"

[features]
reflection_enabled = true
strategic_checkpoints = true
tactical_checkpoints = true
private_reflections = true

[metadata]
default_timezone = "UTC"
timestamp_format = "iso"
include_session_id = true
"""


@pytest.fixture
def sample_jsonl_session():
    """Provide sample JSONL session data."""
    base_time = datetime.now()

    return [
        {
            "uuid": SAMPLE_SESSION_ID,
            "timestamp": base_time.isoformat(),
            "type": "session_start"
        },
        {
            "uuid": SAMPLE_SESSION_ID,
            "timestamp": (base_time + timedelta(minutes=30)).isoformat(),
            "type": "activity",
            "data": {"command": "checkpoint", "type": "strategic"}
        },
        {
            "uuid": SAMPLE_SESSION_ID,
            "timestamp": (base_time + timedelta(hours=1)).isoformat(),
            "type": "activity",
            "data": {"command": "reflect", "trigger": "milestone"}
        }
    ]


@pytest.fixture
def mock_claude_project_structure(tmp_path):
    """Create comprehensive mock .claude project structure."""
    # Create .claude directory
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Create projects directory
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()

    # Create specific project
    project_dir = projects_dir / "test-consciousness-project"
    project_dir.mkdir()

    # Create uuid.jsonl with session data
    uuid_file = project_dir / "uuid.jsonl"
    session_entries = [
        json.dumps({"uuid": SAMPLE_SESSION_ID, "timestamp": datetime.now().isoformat()})
    ]
    uuid_file.write_text("\n".join(session_entries) + "\n")

    # Create agents directory structure
    agents_dir = claude_dir / "agents"
    agents_dir.mkdir()

    for agent_name in [SAMPLE_AGENT_NAME, "DevOpsEng", "TestEng"]:
        agent_dir = agents_dir / agent_name
        agent_dir.mkdir()

        # Create agent subdirectories
        for subdir in ["public", "private"]:
            subdir_path = agent_dir / subdir
            subdir_path.mkdir()
            (subdir_path / "logs").mkdir()
            (subdir_path / "checkpoints").mkdir()

    return claude_dir


@pytest.fixture
def mock_container_environment(monkeypatch):
    """Mock container environment indicators and settings."""
    # Set container environment variables
    container_env = {
        'USER': 'testuser',
        'HOME': '/home/testuser',
        'MACEFF_TZ': SAMPLE_TIMEZONE,
    }

    for key, value in container_env.items():
        monkeypatch.setenv(key, value)

    # Mock /.dockerenv file existence
    with patch('os.path.exists') as mock_exists:
        mock_exists.side_effect = lambda path: path == '/.dockerenv'
        yield container_env


@pytest.fixture
def mock_host_environment(tmp_path, monkeypatch):
    """Mock host environment with .claude project."""
    # Set host environment variables
    host_env = {
        'USER': 'hostuser',
        'HOME': str(tmp_path / 'home'),
        'TZ': SAMPLE_TIMEZONE,
    }

    for key, value in host_env.items():
        monkeypatch.setenv(key, value)

    # Create .claude project structure
    claude_project = mock_claude_project_structure(tmp_path)

    # Mock current working directory to be inside project
    monkeypatch.chdir(tmp_path)

    # Mock no /.dockerenv file
    with patch('os.path.exists') as mock_exists:
        mock_exists.side_effect = lambda path: '/.dockerenv' not in path and '.claude' in path
        yield {'env': host_env, 'claude_dir': claude_project}


@pytest.fixture
def sample_checkpoints_data():
    """Provide sample checkpoint data for testing."""
    base_time = datetime.now()

    checkpoints = []
    for i, (checkpoint_type, hours_ago) in enumerate([
        ("strategic", 1),
        ("tactical", 3),
        ("strategic", 6),
        ("operational", 12),
        ("tactical", 24),
    ]):
        timestamp = base_time - timedelta(hours=hours_ago)

        checkpoint = {
            "filename": f"{timestamp.strftime('%Y-%m-%d_%H%M%S')}_{checkpoint_type}_checkpoint.md",
            "timestamp": timestamp,
            "type": checkpoint_type,
            "note": f"Test {checkpoint_type} checkpoint {i+1}",
            "content": f"""---
timestamp: {timestamp.isoformat()}
type: {checkpoint_type}
agent: {SAMPLE_AGENT_NAME}
session_id: {SAMPLE_SESSION_ID}
note: Test {checkpoint_type} checkpoint {i+1}
---

# {checkpoint_type.title()} Checkpoint

This is test checkpoint content for {checkpoint_type} checkpoint {i+1}.

## Context

Created during test execution to verify checkpoint functionality.

## Details

- Checkpoint type: {checkpoint_type}
- Creation time: {timestamp.isoformat()}
- Test iteration: {i+1}
"""
        }
        checkpoints.append(checkpoint)

    return checkpoints


@pytest.fixture
def populated_agent_directory(mock_consciousness_config, sample_checkpoints_data):
    """Provide agent directory populated with sample checkpoints."""
    config = mock_consciousness_config

    # Create checkpoint files
    for checkpoint_data in sample_checkpoints_data:
        checkpoint_path = config.agent_root / "public" / "checkpoints" / checkpoint_data["filename"]
        checkpoint_path.write_text(checkpoint_data["content"])

    # Create some log files
    logs_dir = config.agent_root / "public" / "logs"

    # Create checkpoints.log (legacy format)
    checkpoints_log = logs_dir / "checkpoints.log"
    log_entries = []
    for checkpoint_data in sample_checkpoints_data[:3]:  # Only first 3 for log format
        entry = {
            "ts": checkpoint_data["timestamp"].isoformat(),
            "note": checkpoint_data["note"]
        }
        log_entries.append(json.dumps(entry))

    checkpoints_log.write_text("\n".join(log_entries) + "\n")

    yield config


@pytest.fixture
def mock_session_management():
    """Mock session management functions."""
    mocks = {}

    with patch('macf.session.get_current_session_id') as mock_get_session:
        with patch('macf.session.get_session_temp_dir') as mock_temp_dir:
            with patch('macf.session.cleanup_old_sessions') as mock_cleanup:
                mock_get_session.return_value = SAMPLE_SESSION_ID
                mock_temp_dir.return_value = Path(f"/tmp/macf/{SAMPLE_SESSION_ID}")
                mock_cleanup.return_value = 3  # 3 sessions cleaned

                mocks['get_session_id'] = mock_get_session
                mocks['get_temp_dir'] = mock_temp_dir
                mocks['cleanup'] = mock_cleanup

                yield mocks


@pytest.fixture
def mock_filesystem_operations():
    """Mock filesystem operations for testing without actual file I/O."""
    mocks = {}

    with patch('pathlib.Path.mkdir') as mock_mkdir:
        with patch('pathlib.Path.write_text') as mock_write:
            with patch('pathlib.Path.read_text') as mock_read:
                with patch('pathlib.Path.exists') as mock_exists:
                    with patch('pathlib.Path.iterdir') as mock_iterdir:
                        # Set up default behaviors
                        mock_mkdir.return_value = None
                        mock_write.return_value = None
                        mock_read.return_value = "test content"
                        mock_exists.return_value = True
                        mock_iterdir.return_value = []

                        mocks['mkdir'] = mock_mkdir
                        mocks['write_text'] = mock_write
                        mocks['read_text'] = mock_read
                        mocks['exists'] = mock_exists
                        mocks['iterdir'] = mock_iterdir

                        yield mocks


@pytest.fixture(scope="session")
def performance_test_data():
    """Generate large dataset for performance testing."""
    # Only generate if actually running performance tests
    import sys
    if 'performance' not in sys.argv and 'test_performance' not in str(sys.argv):
        return None

    base_time = datetime.now()
    large_dataset = []

    for i in range(1000):
        timestamp = base_time - timedelta(hours=i)
        checkpoint_type = ["strategic", "tactical", "operational"][i % 3]

        item = {
            "id": i,
            "timestamp": timestamp,
            "type": checkpoint_type,
            "filename": f"{timestamp.strftime('%Y-%m-%d_%H%M%S')}_{checkpoint_type}_checkpoint.md"
        }
        large_dataset.append(item)

    return large_dataset


@pytest.fixture
def error_simulation():
    """Provide utilities for simulating various error conditions."""
    class ErrorSimulator:
        @staticmethod
        def permission_error():
            return PermissionError("Permission denied")

        @staticmethod
        def file_not_found_error():
            return FileNotFoundError("No such file or directory")

        @staticmethod
        def invalid_json_error():
            return json.JSONDecodeError("Invalid JSON", "test", 0)

        @staticmethod
        def disk_full_error():
            return OSError(28, "No space left on device")

        @staticmethod
        def corrupted_config(original_content):
            """Return corrupted version of config content."""
            lines = original_content.split('\n')
            # Remove random closing brackets
            for i, line in enumerate(lines):
                if ']' in line and i % 3 == 0:
                    lines[i] = line.replace(']', '')
            return '\n'.join(lines)

        @staticmethod
        def corrupted_jsonl(original_entries):
            """Return corrupted version of JSONL entries."""
            corrupted = []
            for i, entry in enumerate(original_entries):
                if i % 3 == 0:
                    # Corrupt every third entry
                    corrupted.append(entry[:-1] + "CORRUPTED")
                else:
                    corrupted.append(entry)
            return corrupted

    return ErrorSimulator()


# Test utilities and helpers

def create_test_checkpoint_file(path: Path, checkpoint_type: str = "strategic",
                               note: str = "Test checkpoint",
                               timestamp: datetime = None) -> Path:
    """Create a test checkpoint file with proper format."""
    if timestamp is None:
        timestamp = datetime.now()

    content = f"""---
timestamp: {timestamp.isoformat()}
type: {checkpoint_type}
agent: {SAMPLE_AGENT_NAME}
session_id: {SAMPLE_SESSION_ID}
note: {note}
---

# {checkpoint_type.title()} Checkpoint

{note}

## Created for Testing

This checkpoint was created during test execution.
"""

    path.write_text(content)
    return path


def validate_checkpoint_format(content: str) -> dict:
    """Validate checkpoint file format and return metadata."""
    if not content.startswith('---'):
        raise ValueError("Missing YAML frontmatter")

    parts = content.split('---', 2)
    if len(parts) < 3:
        raise ValueError("Invalid YAML frontmatter structure")

    import yaml
    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")

    required_fields = ['timestamp', 'type', 'agent', 'note']
    for field in required_fields:
        if field not in metadata:
            raise ValueError(f"Missing required field: {field}")

    # Validate timestamp format
    try:
        datetime.fromisoformat(metadata['timestamp'].replace('Z', '+00:00'))
    except ValueError:
        raise ValueError("Invalid timestamp format")

    return metadata


def assert_valid_session_id(session_id: str):
    """Assert that session ID has valid format."""
    if not session_id:
        raise AssertionError("Session ID is empty")

    if len(session_id) < 8:
        raise AssertionError("Session ID too short")

    # Check for path traversal attempts
    if '../' in session_id or '\\' in session_id:
        raise AssertionError("Session ID contains invalid characters")

    # Should be filesystem safe
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise AssertionError("Session ID contains unsafe characters")


# Pytest configuration

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test (slow)"
    )
    config.addinivalue_line(
        "markers", "container: mark test as container-specific"
    )
    config.addinivalue_line(
        "markers", "host: mark test as host-specific"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Add integration marker for integration tests
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)

        # Add performance marker for performance tests
        if "performance" in item.name.lower():
            item.add_marker(pytest.mark.performance)

        # Add environment markers
        if "container" in item.name.lower():
            item.add_marker(pytest.mark.container)
        elif "host" in item.name.lower():
            item.add_marker(pytest.mark.host)


# Hook-specific fixtures for handle_* module tests

@pytest.fixture
def mock_session_state():
    """Return mock SessionOperationalState for hook testing."""
    state = MagicMock()
    state.auto_mode = False
    state.auto_mode_source = "default"
    state.auto_mode_confidence = 0.0
    state.pending_todos = []
    state.compaction_count = 0
    state.session_started_at = None
    state.last_compaction_at = None
    state.dev_drv_start = None
    state.dev_drv_prompt_uuid = None
    state.deleg_drv_start = None
    state.save = MagicMock(return_value=True)
    return state


@pytest.fixture
def mock_consciousness_artifacts():
    """Return mock ConsciousnessArtifacts for hook testing."""
    artifacts = MagicMock()
    artifacts.latest_checkpoint = Path("/test/agent/public/checkpoints/2025-10-07_strategic_ccp.md")
    artifacts.latest_reflection = Path("/test/agent/public/reflections/2025-10-07_jotewr.md")
    artifacts.latest_roadmap = Path("/test/agent/public/roadmaps/2025-10-07_plan.md")
    artifacts.__bool__ = MagicMock(return_value=True)
    return artifacts


@pytest.fixture
def hook_stdin_empty():
    """Return empty stdin for hook testing."""
    return ""


@pytest.fixture
def hook_stdin_read_tool():
    """Return Read tool stdin for hook testing."""
    return '{"tool_name": "Read", "tool_input": {"file_path": "/foo/bar/test.py"}}'


@pytest.fixture
def hook_stdin_write_tool():
    """Return Write tool stdin for hook testing."""
    return '{"tool_name": "Write", "tool_input": {"file_path": "/foo/bar/config.yaml"}}'


@pytest.fixture
def hook_stdin_bash_tool():
    """Return Bash tool stdin with long command for hook testing."""
    return '{"tool_name": "Bash", "tool_input": {"command": "very long command that exceeds forty characters and needs truncation"}}'


@pytest.fixture
def hook_stdin_task_tool():
    """Return Task tool stdin for delegation testing."""
    return '{"tool_name": "Task", "tool_input": {"subagent_type": "devops-eng"}}'


@pytest.fixture
def hook_stdin_todowrite():
    """Return TodoWrite tool stdin with various statuses."""
    return json.dumps({
        "tool_name": "TodoWrite",
        "tool_input": {
            "todos": [
                {"content": "Task 1", "status": "completed", "activeForm": "Completing task 1"},
                {"content": "Task 2", "status": "completed", "activeForm": "Completing task 2"},
                {"content": "Task 3", "status": "in_progress", "activeForm": "Working on task 3"},
                {"content": "Task 4", "status": "pending", "activeForm": "Starting task 4"},
                {"content": "Task 5", "status": "pending", "activeForm": "Starting task 5"},
                {"content": "Task 6", "status": "pending", "activeForm": "Starting task 6"}
            ]
        }
    })


@pytest.fixture
def hook_stdin_grep_tool():
    """Return Grep tool stdin with long pattern for hook testing."""
    return '{"tool_name": "Grep", "tool_input": {"pattern": "very long pattern that should be truncated to thirty characters"}}'


@pytest.fixture
def hook_stdin_glob_tool():
    """Return Glob tool stdin for hook testing."""
    return '{"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}}'


@pytest.fixture
def mock_temporal_context_hook():
    """Return fixed temporal context for hook testing."""
    return {
        "timestamp_formatted": "2025-10-08 12:45:30 AM EDT",
        "day_of_week": "Wednesday",
        "time_of_day": "12:45:30 AM",
        "session_duration_seconds": 1800,
        "session_duration_formatted": "30m",
        "gap_since_last_checkpoint_seconds": None,
        "gap_since_last_checkpoint_formatted": "Unknown"
    }


@pytest.fixture
def mock_minimal_timestamp_hook():
    """Return fixed minimal timestamp for high-frequency hooks."""
    return "12:45:30 AM"