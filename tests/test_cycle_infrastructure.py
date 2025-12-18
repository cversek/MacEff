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

    def test_increment_agent_cycle_returns_incremented_value(self, test_agent_root):
        """Increment function returns current+1 (safe-by-default, no persistence)."""
        session_id = "test_session_001"

        # Get initial cycle number (should be 1)
        initial_cycle = get_agent_cycle_number(test_agent_root)
        assert initial_cycle == 1

        # Increment cycle returns what WOULD be the new value
        new_cycle = increment_agent_cycle(session_id, test_agent_root)
        assert new_cycle == 2  # Returns current+1

    def test_increment_returns_consistent_value_without_persistence(self, test_agent_root):
        """Multiple increments return same value when testing=True (no state mutation)."""
        session_id = "test_session"

        # Each call returns current+1 without mutating state
        result_1 = increment_agent_cycle(session_id, test_agent_root)
        result_2 = increment_agent_cycle(session_id, test_agent_root)
        result_3 = increment_agent_cycle(session_id, test_agent_root)

        # All return 2 because state is never mutated (testing=True default)
        assert result_1 == 2
        assert result_2 == 2
        assert result_3 == 2

    def test_get_cycle_number_returns_one_for_fresh_state(self, test_agent_root):
        """Fresh agent state returns cycle 1."""
        cycle = get_agent_cycle_number(test_agent_root)
        assert cycle == 1

    def test_first_cycle_is_one_not_zero(self, test_agent_root):
        """Fresh start begins at Cycle 1, not Cycle 0."""
        # Fresh agent state should start at cycle 1
        cycle = get_agent_cycle_number(test_agent_root)
        assert cycle == 1

    # NOTE: Persistence/metadata tests removed - they require testing=False
    # which violates safe-by-default pattern. Integration tests for persistence
    # belong in hook integration tests where production paths are tested.
