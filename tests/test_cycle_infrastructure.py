"""
Pragmatic unit tests for cycle tracking infrastructure.

Testing philosophy: 4-6 tests per component, core functionality only.

NOTE: Cycle tracking refactored from session-based to agent-based.
Uses agent_state.json (persists across sessions) instead of session state.
"""

import pytest
from pathlib import Path
import sys

# Add macf to path
sys.path.insert(0, str(Path(__file__).parent.parent / "macf" / "src"))

from macf.event_queries import get_cycle_number_from_events


class TestCycleTracking:
    """Test agent-based cycle number management."""

    def test_get_cycle_number_returns_one_for_fresh_state(self):
        """Fresh event log returns cycle 1."""
        # isolate_event_log fixture (autouse) handles isolation
        cycle = get_cycle_number_from_events()
        assert cycle == 1

    def test_first_cycle_is_one_not_zero(self):
        """Fresh start begins at Cycle 1, not Cycle 0."""
        # isolate_event_log fixture (autouse) handles isolation
        cycle = get_cycle_number_from_events()
        assert cycle == 1

    # NOTE: Persistence/metadata tests removed - they require testing=False
    # which violates safe-by-default pattern. Integration tests for persistence
    # belong in hook integration tests where production paths are tested.
