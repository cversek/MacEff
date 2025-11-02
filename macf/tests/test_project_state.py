"""
Test suite for project-scoped cycle persistence (Phase 1E).

Tests project state management that persists across sessions:
- Project state load/save operations
- Cycle increment functionality
- Session migration detection
- Backward compatibility (first run initialization)
"""

import tempfile
import time
from pathlib import Path
import pytest

from macf.utils import (
    get_agent_state_path,
    load_agent_state,
    save_agent_state,
    get_current_cycle_project,
    increment_cycle_project,
    detect_session_migration,
)


class TestProjectStateCore:
    """Core project state operations."""

    def test_project_state_roundtrip(self, tmp_path):
        """Project state saves and loads correctly."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # Save state
        state = {
            'current_cycle_number': 5,
            'cycle_started_at': 1234567890.0,
            'cycles_completed': 4,
            'last_session_id': 'session-abc123'
        }
        result = save_agent_state(state, agent_root)
        assert result is True

        # Load state back
        loaded = load_agent_state(agent_root)
        assert loaded['current_cycle_number'] == 5
        assert loaded['cycle_started_at'] == 1234567890.0
        assert loaded['cycles_completed'] == 4
        assert loaded['last_session_id'] == 'session-abc123'
        assert 'last_updated' in loaded  # Auto-added by save

    def test_cycle_increment(self, tmp_path):
        """Cycle increments correctly in project state."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # Initialize project state at cycle 10
        initial_state = {
            'current_cycle_number': 10,
            'cycle_started_at': 1234567890.0,
            'cycles_completed': 9,
            'last_session_id': 'old-session'
        }
        save_agent_state(initial_state, agent_root)

        # Increment cycle
        new_cycle = increment_cycle_project('new-session', agent_root)
        assert new_cycle == 11

        # Verify state updated correctly
        loaded = load_agent_state(agent_root)
        assert loaded['current_cycle_number'] == 11
        assert loaded['cycles_completed'] == 10
        assert loaded['last_session_id'] == 'new-session'
        assert loaded['cycle_started_at'] > 1234567890.0  # Timestamp updated

    def test_session_migration_detection(self, tmp_path):
        """Session migration detected when session ID changes."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # Save project state with old session
        state = {
            'current_cycle_number': 16,
            'last_session_id': 'session-old-abc123'
        }
        save_agent_state(state, agent_root)

        # Check with different session ID
        is_migration, old_id = detect_session_migration('session-new-xyz789', agent_root)
        assert is_migration is True
        assert old_id == 'session-old-abc123'

        # Check with same session ID
        is_migration, old_id = detect_session_migration('session-old-abc123', agent_root)
        assert is_migration is False
        assert old_id == 'session-old-abc123'


class TestProjectStateBackwardCompatibility:
    """Backward compatibility and edge cases."""

    def test_missing_file_returns_defaults(self, tmp_path):
        """Missing project state returns sensible defaults."""
        agent_root = tmp_path / "nonexistent"

        # Load should return empty dict
        state = load_agent_state(agent_root)
        assert state == {}

        # get_current_cycle should return 1
        cycle = get_current_cycle_project(agent_root)
        assert cycle == 1

        # detect_session_migration should return no migration
        is_migration, old_id = detect_session_migration('any-session', agent_root)
        assert is_migration is False
        assert old_id == ""

    def test_first_run_initialization(self, tmp_path):
        """First run creates valid project state."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # No project state exists yet
        assert not (agent_root / ".maceff" / "project_state.json").exists()

        # Increment cycle on first run
        new_cycle = increment_cycle_project('first-session', agent_root)
        assert new_cycle == 2  # Starts at 1, increments to 2

        # Verify state file created
        assert (agent_root / ".maceff" / "project_state.json").exists()

        # Verify state structure
        state = load_agent_state(agent_root)
        assert state['current_cycle_number'] == 2
        assert state['cycles_completed'] == 1
        assert state['last_session_id'] == 'first-session'
        assert 'cycle_started_at' in state
        assert 'last_updated' in state

    def test_creates_maceff_directory(self, tmp_path):
        """Save creates .maceff directory if missing."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # Directory doesn't exist yet
        assert not (agent_root / ".maceff").exists()

        # Save should create it
        state = {'current_cycle_number': 1}
        result = save_agent_state(state, agent_root)
        assert result is True
        assert (agent_root / ".maceff").exists()
        assert (agent_root / ".maceff" / "project_state.json").exists()


class TestProjectStateResilience:
    """Error handling and resilience."""

    def test_corrupted_json_returns_empty(self, tmp_path):
        """Corrupted project state returns empty dict gracefully."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()
        maceff_dir = agent_root / ".maceff"
        maceff_dir.mkdir()

        # Write corrupted JSON
        state_path = maceff_dir / "project_state.json"
        state_path.write_text("{ invalid json }")

        # Should return empty dict, not crash
        state = load_agent_state(agent_root)
        assert state == {}

        # Other functions should handle gracefully
        cycle = get_current_cycle_project(agent_root)
        assert cycle == 1  # Default value

    def test_no_last_session_id_field(self, tmp_path):
        """Migration detection handles missing last_session_id field."""
        agent_root = tmp_path / "project"
        agent_root.mkdir()

        # Save state without last_session_id
        state = {'current_cycle_number': 5}
        save_agent_state(state, agent_root)

        # Should not crash, should return no migration
        is_migration, old_id = detect_session_migration('any-session', agent_root)
        assert is_migration is False
        assert old_id == ""
