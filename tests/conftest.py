"""
Pytest configuration for MacEff integration tests.

CRITICAL: All tests MUST be isolated from production state.
- Event log: Auto-isolated via set_log_path() AND MACF_EVENTS_LOG_PATH env var for ALL tests
- State files: Auto-isolated via set_state_root() for ALL tests

NOTE: Environment variable isolation is CRITICAL for subprocess tests.
set_log_path() only works in-process. Subprocesses (like hook scripts) inherit
environment variables but not Python module state. Both must be set.
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_event_log(tmp_path, monkeypatch):
    """
    Auto-use fixture that isolates event log for ALL tests.

    This prevents tests from reading/writing the real .maceff/agent_events_log.jsonl.
    Every test gets a fresh, empty event log in a temp directory.

    CRITICAL: Sets BOTH in-process path AND environment variable.
    - set_log_path(): For in-process code
    - MACF_EVENTS_LOG_PATH: For subprocess hooks (inherited by child processes)
    """
    from macf.agent_events_log import set_log_path

    # Create isolated event log path
    test_log_path = tmp_path / "agent_events_log.jsonl"

    # Set in-process isolation
    set_log_path(test_log_path)

    # Set environment variable for subprocess isolation (CRITICAL for hook tests)
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log_path))

    yield test_log_path

    # Reset to default after test (monkeypatch auto-resets env vars)
    set_log_path(None)


@pytest.fixture(autouse=True)
def isolate_state_files(tmp_path):
    """
    Auto-use fixture that isolates state files for ALL tests.

    This prevents tests from reading/writing the real .maceff/ state files.
    Every test gets a fresh, isolated agent root directory.
    """
    from macf.utils.state import set_state_root

    # Create isolated agent root with .maceff structure
    agent_root = tmp_path / "test_agent"
    maceff_dir = agent_root / ".maceff"
    maceff_dir.mkdir(parents=True, exist_ok=True)

    # Set isolation path
    set_state_root(agent_root)

    yield agent_root

    # Reset to default after test
    set_state_root(None)


@pytest.fixture
def temp_log_file(isolate_event_log):
    """
    Explicit fixture for tests that need direct access to log path.

    Returns the SAME path used by isolate_event_log autouse fixture.
    This ensures tests read from the same file that append_event writes to.
    """
    return isolate_event_log


@pytest.fixture
def isolated_agent_root(tmp_path):
    """
    Create isolated agent root directory for state file tests.

    Use this for tests that call functions with agent_root parameter.
    Creates proper .maceff/ directory structure.
    """
    agent_root = tmp_path / "test_agent"
    maceff_dir = agent_root / ".maceff"
    maceff_dir.mkdir(parents=True, exist_ok=True)

    return agent_root
