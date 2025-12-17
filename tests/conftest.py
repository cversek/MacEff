"""
Pytest configuration for MacEff integration tests.

CRITICAL: All tests MUST be isolated from production state.
- Event log: Auto-isolated via set_log_path() for ALL tests
- State files: Auto-isolated via set_state_root() for ALL tests
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_event_log(tmp_path):
    """
    Auto-use fixture that isolates event log for ALL tests.

    This prevents tests from reading/writing the real .maceff/agent_events_log.jsonl.
    Every test gets a fresh, empty event log in a temp directory.
    """
    from macf.agent_events_log import set_log_path

    # Create isolated event log path
    test_log_path = tmp_path / "agent_events_log.jsonl"
    set_log_path(test_log_path)

    yield test_log_path

    # Reset to default after test
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
