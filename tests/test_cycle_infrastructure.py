"""
Pragmatic unit tests for cycle tracking infrastructure.

Testing philosophy: 4-6 tests per component, core functionality only.

NOTE: Cycle tracking refactored from session-based to agent-based.
Uses agent_state.json (persists across sessions) instead of session state.
"""

import pytest
import time
from pathlib import Path
import sys
import tempfile
import shutil

# Add macf to path
sys.path.insert(0, str(Path(__file__).parent.parent / "macf" / "src"))

from macf.utils import (
    get_agent_cycle_number,
    increment_agent_cycle,
    load_agent_state,
    save_agent_state,
)


class TestCycleTracking:
    """Test agent-based cycle number management."""

    @pytest.fixture
    def test_agent_root(self):
        """Create temporary agent root for testing."""
        # Create temp directory for agent state
        temp_dir = Path(tempfile.mkdtemp())
        agent_root = temp_dir / "test_agent"
        agent_root.mkdir(parents=True, exist_ok=True)

        yield agent_root

        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

    def test_increment_agent_cycle_increments_number(self, test_agent_root):
        """Incrementing agent cycle increments from current."""
        session_id = "test_session_001"

        # Get initial cycle number (should be 1)
        initial_cycle = get_agent_cycle_number(test_agent_root)
        assert initial_cycle == 1

        # Increment cycle - should go to 2
        new_cycle = increment_agent_cycle(session_id, test_agent_root)
        assert new_cycle == 2

        # Verify state persisted
        current_cycle = get_agent_cycle_number(test_agent_root)
        assert current_cycle == 2

    def test_cycle_persists_across_sessions(self, test_agent_root):
        """Cycle number persists across multiple sessions (agent-scoped)."""
        session_id_1 = "session_001"
        session_id_2 = "session_002"

        # First session increments to cycle 2
        increment_agent_cycle(session_id_1, test_agent_root)
        assert get_agent_cycle_number(test_agent_root) == 2

        # Second session increments to cycle 3
        increment_agent_cycle(session_id_2, test_agent_root)
        assert get_agent_cycle_number(test_agent_root) == 3

        # Cycle persists (agent-scoped, not session-scoped)
        final_cycle = get_agent_cycle_number(test_agent_root)
        assert final_cycle == 3

    def test_cycle_increments_on_compaction(self, test_agent_root):
        """Cycle increments when SessionStart hook detects compaction."""
        session_id = "compaction_session"

        # Simulate multiple compactions
        cycle_1 = increment_agent_cycle(session_id, test_agent_root)
        assert cycle_1 == 2  # First compaction: 1 -> 2

        cycle_2 = increment_agent_cycle(session_id, test_agent_root)
        assert cycle_2 == 3  # Second compaction: 2 -> 3

        cycle_3 = increment_agent_cycle(session_id, test_agent_root)
        assert cycle_3 == 4  # Third compaction: 3 -> 4

    def test_first_cycle_is_one_not_zero(self, test_agent_root):
        """Fresh start begins at Cycle 1, not Cycle 0."""
        # Fresh agent state should start at cycle 1
        cycle = get_agent_cycle_number(test_agent_root)
        assert cycle == 1

    def test_agent_state_tracks_metadata(self, test_agent_root):
        """Agent state includes cycle metadata (timestamps, counts)."""
        session_id = "metadata_session"

        # Increment cycle
        increment_agent_cycle(session_id, test_agent_root)

        # Load state and verify metadata
        state = load_agent_state(test_agent_root)

        assert 'current_cycle_number' in state
        assert 'cycle_started_at' in state
        assert 'cycles_completed' in state
        assert 'last_session_id' in state

        # Verify types
        assert isinstance(state['current_cycle_number'], int)
        assert isinstance(state['cycle_started_at'], float)
        assert isinstance(state['cycles_completed'], int)
        assert isinstance(state['last_session_id'], str)

        # Verify values
        assert state['current_cycle_number'] == 2
        assert state['cycles_completed'] == 1
        assert state['last_session_id'] == session_id

    def test_cycle_started_at_timestamp_updates(self, test_agent_root):
        """cycle_started_at timestamp updates on increment."""
        session_id = "timestamp_session"

        # Record time before increment
        before = time.time()

        # Increment cycle
        increment_agent_cycle(session_id, test_agent_root)

        # Record time after increment
        after = time.time()

        # Load state and check timestamp
        state = load_agent_state(test_agent_root)
        cycle_started_at = state['cycle_started_at']

        # Timestamp should be between before and after
        assert before <= cycle_started_at <= after
