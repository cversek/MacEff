"""
Pragmatic unit tests for cycle tracking infrastructure.

Testing philosophy: 4-6 tests per component, core functionality only.
"""

import pytest
import time
from pathlib import Path
import sys
import tempfile
import shutil

# Add macf to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "src"))

from macf.utils import (
    start_new_cycle,
    get_current_cycle_number,
    get_cycle_stats,
    SessionOperationalState
)


class TestCycleTracking:
    """Test cycle number management."""

    @pytest.fixture
    def test_session(self):
        """Create temporary test session."""
        session_id = "test_cycle_session"
        agent_id = "test_agent"
        yield session_id, agent_id
        # Cleanup - remove session state file
        try:
            state = SessionOperationalState.load(session_id, agent_id)
            state_file = Path(f"/tmp/macf/{agent_id}/{session_id}/session_state.json")
            if state_file.exists():
                state_file.unlink()
            # Clean up session directory
            session_dir = state_file.parent
            if session_dir.exists():
                shutil.rmtree(session_dir)
        except:
            pass

    def test_start_new_cycle_increments_number(self, test_session):
        """Starting new cycle increments from current."""
        session_id, agent_id = test_session

        # Get initial cycle number (should be 1)
        initial_cycle = get_current_cycle_number(session_id, agent_id)
        assert initial_cycle == 1

        # Start new cycle - should increment to 2
        new_cycle = start_new_cycle(session_id, agent_id)
        assert new_cycle == 2

        # Verify state persisted
        current_cycle = get_current_cycle_number(session_id, agent_id)
        assert current_cycle == 2

    def test_cycle_persists_across_session_restart(self, test_session):
        """Cycle number persists when session restarts without compaction."""
        session_id, agent_id = test_session

        # Set cycle to 47
        state = SessionOperationalState.load(session_id, agent_id)
        state.current_cycle_number = 47
        state.save()

        # Simulate session restart (new load)
        reloaded_cycle = get_current_cycle_number(session_id, agent_id)
        assert reloaded_cycle == 47

    def test_cycle_resets_on_compaction(self, test_session):
        """Cycle increments when compaction detected."""
        session_id, agent_id = test_session

        # Set up initial state
        state = SessionOperationalState.load(session_id, agent_id)
        state.current_cycle_number = 5
        state.compaction_count = 4
        state.save()

        # Simulate compaction: increment compaction_count and start new cycle
        state = SessionOperationalState.load(session_id, agent_id)
        state.compaction_count += 1
        state.save()
        new_cycle = start_new_cycle(session_id, agent_id)

        # Cycle should increment to 6
        assert new_cycle == 6

    def test_get_cycle_stats_returns_valid_dict(self, test_session):
        """Cycle stats dict has required keys."""
        session_id, agent_id = test_session

        stats = get_cycle_stats(session_id, agent_id)

        # Verify required keys
        required_keys = ['cycle_number', 'cycle_started_at', 'cycle_duration', 'cycles_completed']
        for key in required_keys:
            assert key in stats, f"Missing required key: {key}"

        # Verify types
        assert isinstance(stats['cycle_number'], int)
        assert isinstance(stats['cycle_started_at'], float)
        assert isinstance(stats['cycle_duration'], float)
        assert isinstance(stats['cycles_completed'], int)

    def test_first_cycle_is_one_not_zero(self, test_session):
        """Fresh start begins at Cycle 1, not Cycle 0."""
        session_id, agent_id = test_session

        # Fresh state should have cycle 1
        cycle = get_current_cycle_number(session_id, agent_id)
        assert cycle == 1

        # Verify via stats as well
        stats = get_cycle_stats(session_id, agent_id)
        assert stats['cycle_number'] == 1

    def test_cycle_duration_calculation(self, test_session):
        """Cycle duration calculated correctly."""
        session_id, agent_id = test_session

        # Set cycle_started_at to 60 seconds ago
        state = SessionOperationalState.load(session_id, agent_id)
        state.cycle_started_at = time.time() - 60
        state.save()

        # Get stats and verify duration is approximately 60 seconds
        stats = get_cycle_stats(session_id, agent_id)
        duration = stats['cycle_duration']

        # Allow 2 second tolerance for test execution time
        assert 58 <= duration <= 62, f"Duration {duration} not in expected range [58-62]"
