"""
Shared test fixtures and configuration for macf_tools test suite.

This module provides common fixtures, utilities, and configuration for all tests.
It follows pytest best practices for sharing test resources and maintaining
test isolation while providing realistic test environments.

EVENT LOG ISOLATION FOR SUBPROCESS TESTS
=========================================
Tests using subprocess.run(['macf_tools', ...]) emit cli_command_invoked events.
Without isolation, these pollute production agent_events_log.jsonl.

Pattern for CLI subprocess tests (see test_policy_cli.py):

    @pytest.fixture(autouse=True)
    def isolated_cli_env(tmp_path, monkeypatch):
        test_log = tmp_path / "test_cli_events.jsonl"
        monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
        yield test_log

This fixture is module-local (not global) because:
- Only CLI subprocess tests need it
- Hook execution tests (test_hook_execution.py) run scripts directly, no events
- Global autouse would add overhead where not needed
"""

import json
import os
import subprocess
import sys
import tempfile
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from click.testing import CliRunner

# Test data constants
SAMPLE_SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
SAMPLE_AGENT_NAME = "TestAgent"
SAMPLE_TIMEZONE = "America/New_York"


def _addressing(flat, domain="agents.test"):
    """Render the amail addressing config from a flat agent -> contacts mapping.

    Tests care about WHICH agent may write to WHOM, not about the file's
    nesting. This keeps that intent at the call site — `{"alpha": [...]}` —
    while producing the real shape the parser consumes, so the tests exercise
    the actual format rather than a fixture-only one.

    A bare-string contact is expanded to `{address, direction: "both"}`, and a
    mapping without a direction gets the same. THIS IS A STATED FIXTURE
    ASSUMPTION, not a shim over the parser: it means "this test is not about
    direction, and assumes full authority". The parser itself accepts neither
    form — `test_amail_contact_direction.py` pins that a bare address and a
    missing direction are both REFUSED, so this convenience cannot mask the
    requirement. Tests that ARE about direction state it explicitly and get
    exactly what they wrote.
    """
    import yaml

    def _entry(c):
        if isinstance(c, str):
            return {"address": c, "direction": "both"}
        return c if "direction" in c else {**c, "direction": "both"}

    flat = {a: [_entry(c) for c in cs] for a, cs in flat.items()}
    # uid and home are declared rather than resolved from `account`, because no
    # such accounts exist on a test machine. Uids are distinct per agent: the
    # uid table is the authentication table and the model refuses duplicates,
    # which is the property, not a fixture detail.
    return yaml.safe_dump({
        "domain": domain,
        "agents": {
            a: {"contacts": c, "uid": 9000 + i, "home": f"/home/{a}"}
            for i, (a, c) in enumerate(sorted(flat.items()))
        },
    })


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


@pytest.fixture(autouse=True)
def isolated_channel_state(tmp_path, monkeypatch):
    """Isolate the Telegram channel's state directory for EVERY test.

    Not a hypothetical. `test_harness_integration` launches the REAL client with
    `--channels plugin:telegram@claude-plugins-official` to prove the argument
    order parses. That client loads the plugin, which spawns a channel server,
    which reads `bot.pid` from the state dir it inherits -- the developer's live
    one -- SIGTERMs the running poller, takes the bot token, and then exits when
    the 20-second subprocess ends. Net effect: running the test suite silently
    kills the developer's Telegram for the rest of the session.

    Measured, not theorised: instrumenting the channel server produced
    `stale_poller_evicted{stale_pid}` followed by `shutdown{reason: SIGTERM}` at
    the exact second that test began, and `shutdown{reason: stdin-end}` when it
    ended. A second agent's poller, which sets its own state dir, survived all
    110 samples -- the control that rules out anything systemic.

    The isolation belongs HERE rather than in that one test because the hazard
    is not specific to it: any test that spawns a real client inherits this
    environment. A guard at the boundary catches the next one too.
    """
    d = tmp_path / "channel_state" / "telegram"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TELEGRAM_STATE_DIR", str(d))
    yield d


@pytest.fixture(autouse=True)
def isolated_agent_home(tmp_path, monkeypatch):
    """
    Isolate the agent home so tests can never write into the live agent's
    consciousness artifacts (ideas bank, task store, learnings, ...).

    Why this exists: find_agent_home() is lru_cached. The test process
    inherits the real MACEFF_AGENT_HOME_DIR from the developer's shell, so
    whichever test resolves the home first pins the LIVE home into the cache
    and every later per-test monkeypatch of the env var is silently ignored.
    Three separate suite runs wrote test ideas into a live agent's bank
    (2026-07-20 twice, 2026-07-22) before this fixture.

    Applies to ALL tests (autouse). It:
    - points MACEFF_AGENT_HOME_DIR at a per-test tmp home (inherited by
      subprocess CLI invocations too)
    - clears the find_agent_home cache before the test, so the tmp home
      actually takes effect regardless of test order
    - clears it again after, so no test leaks its home to the next

    Tests that need their own home layout can still monkeypatch the env var
    on top of this; the pre-cleared cache makes that reliable.

    This covers BOTH resolvers as of #252. It did not always: `ConsciousnessConfig`
    resolved the agent root by walking up from the cwd and never consulted this
    variable, so anything reaching the filesystem through that path addressed
    whatever directory pytest was started in — isolation that read as complete
    and was not. Anything added here later should be checked against both, since
    the fixture's coverage is a property of the resolvers rather than of itself.

    Yields:
        Path to the isolated agent home
    """
    from macf.utils.paths import find_agent_home

    test_home = tmp_path / "_macf_isolated_home"
    test_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(test_home))
    find_agent_home.cache_clear()

    yield test_home

    find_agent_home.cache_clear()


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path, monkeypatch):
    """Point the task store at a per-test directory, at the boundary.

    The agent home fixture above already isolates the store *indirectly*: the
    home store resolves through `find_agent_home()`, so isolating the home
    isolates the store as a side effect. That is true today and it is not
    something to rely on. It holds only while the store keeps resolving through
    that one function, it depends on an lru_cache being cleared, and if it ever
    stops holding, the failure mode is a silent write into the durable record of
    what an agent was doing -- discovered, if at all, by noticing a wrong status
    months later. That is exactly how it was discovered the first time.

    So the store is isolated here directly and for its own sake.
    `MACF_TASKS_DIR` also forces `TaskReader._resolve_home_store()` to return
    None, so neither backend can address anything outside `tmp_path`.

    Boundary isolation rather than patched write paths, deliberately. Patching
    named symbols covers the writes you predicted; a path you did not predict
    goes to the real store while the test passes. A test module that isolated by
    patching `_create_task_file`, `update_task_file` and `TaskReader` still
    re-opened a completed task in a live store, because the auto-start chain
    reached a write that was not in that set. An environment variable has no
    escape path. This is the same reasoning that removed the `testing`
    parameter: code-level isolation creates two universes and the tests then
    verify the wrong one.

    Tests needing a specific backend override this — `MACF_TASK_STORE_DIR` takes
    precedence, and `delenv` restores default resolution.

    Yields:
        Path to the isolated task directory
    """
    test_tasks = tmp_path / "_macf_isolated_tasks"
    test_tasks.mkdir(parents=True, exist_ok=True)
    # Both, and in this order. MACF_TASK_STORE_DIR outranks MACF_TASKS_DIR in
    # `_resolve_home_store`, so setting only the latter would leave the store
    # pointing at whatever a developer happens to export in their own shell --
    # isolation that works on the machine that does not need it and fails on the
    # one that does.
    monkeypatch.delenv("MACF_TASK_STORE_DIR", raising=False)
    monkeypatch.setenv("MACF_TASKS_DIR", str(test_tasks))

    yield test_tasks


class LiveStoreTouched(UserWarning):
    """The real task store changed while the suite ran.

    Its own category so it can be filtered to an error (`-W error::...`) by
    anyone who wants the CI behaviour locally.
    """


def _fingerprint(dirs):
    """Map every task file under `dirs` to (size, mtime_ns).

    Cheap enough to run twice per session over a few thousand files, and it
    catches modification of an existing file — which a count or a directory
    mtime does not. A completed task being flipped back to in-progress changes
    no filename and no file count.
    """
    seen = {}
    for d in dirs:
        for p in d.rglob("*.json"):
            try:
                st = p.stat()
            except OSError:
                continue
            seen[str(p)] = (st.st_size, st.st_mtime_ns)
    return seen


@pytest.fixture(scope="session", autouse=True)
def live_task_store_is_left_alone():
    """Fail the run if it wrote into the developer's real task store.

    The isolation above should make this impossible. The guard exists because
    the previous isolation was also believed to make it impossible, and the leak
    it missed was found months afterwards by noticing that a task which had
    completed cleanly was somehow in progress again — with a test fixture's
    breadcrumb in its update history.

    A leak that announces itself is worth more than one that has to be inferred
    from a wrong status later, so this reports at the end of the run rather than
    leaving the evidence to be stumbled on.

    Resolution happens at session start, before any per-test isolation applies,
    so the paths are the real ones. Where there is no live store — CI, a fresh
    checkout — there is nothing to fingerprint and the guard is inert.
    """
    from macf.task.reader import TaskReader

    targets = []
    try:
        home = TaskReader._resolve_home_store()
        if home and home.exists():
            targets.append(home)
        legacy = TaskReader._get_tasks_dir()
        if legacy.exists():
            targets.append(legacy)
    except (OSError, ValueError, ImportError) as e:
        print(f"⚠️ MACF: live task store guard could not resolve a store: {e}",
              file=sys.stderr)

    before = _fingerprint(targets)

    yield

    after = _fingerprint(targets)
    if before == after:
        return

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    detail = (
        "the LIVE task store changed during this run — task files are the "
        "durable record of what an agent was doing, and a test that can write "
        "there can make finished work look unfinished.\n"
        f"  added:   {added}\n"
        f"  changed: {changed}\n"
        f"  removed: {removed}"
    )

    # Strict only where a concurrent writer is impossible.
    #
    # This guard cannot see WHICH process wrote; it sees only that the store
    # differs. On a workstation the agent that owns the store is often working
    # in it while the suite runs, and those edits land inside the same window --
    # measured, on the run that prompted this branch, where the three files it
    # flagged were the author's own task notes. Failing on that would train
    # everyone to ignore the one message that matters, and a detector that
    # cries wolf gets muted, which is worse than not having one.
    #
    # In CI there is no other writer, so a difference means a test wrote it, and
    # there the run fails. Elsewhere it reports and lets a human judge, because
    # "these are my own edits" is a judgement only the human can make.
    if os.environ.get("CI"):
        pytest.fail(detail, pytrace=False)

    # `warnings.warn`, not a print. pytest captures fixture stdout/stderr, so a
    # printed notice is swallowed on a passing run — visible only when something
    # else already failed, which is precisely when it is not needed. Warnings go
    # to the end-of-run summary whether the run passed or not.
    warnings.warn(
        f"{detail}\n"
        "  (not failing outside CI: a concurrent writer on this machine is the "
        "benign explanation, and these are often the author's own edits. In CI "
        "there is no other writer and this is an error.)",
        LiveStoreTouched,
        stacklevel=1,
    )


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


# A unix socket path is capped by `sockaddr_un.sun_path`: 104 bytes on the BSDs
# and macOS, 108 on Linux. Nothing reports this as a length error -- the bind
# simply fails, and tmux surfaces it as "error connecting to <path> (File name
# too long)".
SUN_PATH_MAX = 104 if sys.platform == "darwin" else 108


@pytest.fixture
def tmux_sandbox_env():
    """An environment for driving tmux against a private, disposable server.

    Three properties, all load-bearing, each one learned from a failure rather
    than chosen up front:

    - **$TMUX is stripped.** A tmux client that inherits $TMUX attaches to THAT
      server and ignores TMUX_TMPDIR entirely. Every process inside a tmux pane
      has $TMUX set -- which is how an agent runs this suite, and never how CI
      runs it -- so a teardown `kill-server` reached the host's default server
      and destroyed every session on it, including a live agent harness.

    - **PATH is inherited.** An environment built from scratch carries no PATH,
      and POSIX then falls back to a fixed `/usr/bin:/bin:/usr/sbin:/sbin`
      (`os.confstr('CS_PATH')`). tmux is on that path under most Linux
      packaging and is not under Homebrew, so a from-scratch env cannot find
      the binary on macOS no matter what the developer's shell says.

    - **The socket directory is short, and is deliberately not `tmp_path`.**
      tmux appends `tmux-<uid>/default` to TMUX_TMPDIR, and macOS roots
      `tmp_path` under `/private/var/folders/<2>/<26>/T/`, which overruns
      SUN_PATH_MAX once pytest adds `pytest-of-<user>/pytest-<n>/<test>0/` --
      142 bytes measured against a 104-byte cap. Linux's `/tmp/...` stays
      under it.

    The first two pull against each other, which is why both natural spellings
    are wrong: `{**os.environ, ...}` keeps PATH but leaks $TMUX, and
    `{"TMUX_TMPDIR": ...}` drops $TMUX but loses PATH.

    Inheriting PATH also makes the `shutil.which("tmux")` skip guards on the
    classes that use this fixture meaningful again. A guard is only worth
    having if it queries the same thing the guarded operation will; while the
    env was scrubbed, `which()` consulted the real PATH, found Homebrew's tmux,
    declined to skip, and the subprocess then failed to find the same binary.
    """
    # macOS TMPDIR is too long to hold a socket, so ask for a short base
    # explicitly rather than accepting the platform default.
    base = "/tmp" if os.path.isdir("/tmp") else None
    with tempfile.TemporaryDirectory(prefix="macf-tmux-", dir=base) as sock:
        env = {k: v for k, v in os.environ.items() if k != "TMUX"}
        env["TMUX_TMPDIR"] = sock

        # Fail by name rather than by tmux's opaque "File name too long".
        probe = os.path.join(sock, f"tmux-{os.getuid()}", "default")
        assert len(probe) <= SUN_PATH_MAX, (
            f"tmux socket path is {len(probe)} bytes, over the {SUN_PATH_MAX}-byte "
            f"limit on this platform: {probe}"
        )

        yield env

        # This teardown is the destructive one, and it is survivable only
        # because the env above selects a private server. Target it explicitly
        # so a future edit that reintroduces $TMUX cannot turn this line into
        # kill-server against the host.
        subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)

@pytest.fixture
def temp_log_file(isolated_events_log):
    """The isolated event log path, for tests that read the file directly.

    A bridge, not a second isolation mechanism. ``isolated_events_log`` above is
    autouse and already redirects both the in-process path and the subprocess
    environment variable; this returns THAT path so a test asserting on file
    contents reads the same file ``append_event`` just wrote to.

    It exists because the suites consolidated here were written against a
    separate conftest that named the same object ``temp_log_file``. Aliasing was
    chosen over renaming call sites: the rename would have touched three modules
    to no behavioural end, and a wrong rename in a test that reads a log path is
    invisible -- it would read an empty file and pass.
    """
    return isolated_events_log


@pytest.fixture(autouse=True)
def _no_live_telegram_credentials(request, monkeypatch):
    """Refuse live Telegram credentials to every test by default.

    GH #330. ``isolated_channel_state`` above isolates TELEGRAM_STATE_DIR, which
    covers poller state -- the failure that evicted a live poller. It does not
    cover CONFIG RESOLUTION: ``resolve_telegram_config`` reads
    ``{project}/.claude/channels/telegram/`` then ``~/.claude/channels/telegram/``
    and consults no environment variable, so any test that reaches a hook's
    notify path sends a REAL message to a REAL person. Measured on this machine:
    the operator confirms receiving them routinely.

    Two paths, one covered, and from the outside the fixture looked complete.

    Scope of THIS fix, stated so it is not overread: it neutralises the
    IN-PROCESS path only. A test that spawns a subprocess gets a fresh
    interpreter where this patch does not exist, and no environment variable
    exists to carry the refusal across that boundary -- creating one is a product
    change and belongs to #330. ``test_hook_integration.py`` is skipped until
    then for exactly that reason.

    Opt out with ``@pytest.mark.live_telegram_config`` when a test's subject IS
    the resolution path.
    """
    if request.node.get_closest_marker("live_telegram_config"):
        return
    monkeypatch.setattr(
        "macf.channels.telegram.resolve_telegram_config",
        lambda: None,
        raising=True,
    )
