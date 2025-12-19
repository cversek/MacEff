"""
Integration tests for TODO recovery intelligence using event log forensics.

Tests the enhanced maceff-todo-restoration skill's ability to:
- Query migration_detected events from agent_events_log
- Apply size + cycle heuristics for intelligent restoration decisions
- Append completion/skip events after restoration attempts
"""

import json
import tempfile
import time
from pathlib import Path
from typing import List

import pytest

from macf.agent_events_log import (
    append_event,
    query_events,
    set_log_path,
)


@pytest.fixture
def temp_event_log(tmp_path):
    """Create temporary event log for testing."""
    log_path = tmp_path / "test_events.jsonl"
    set_log_path(log_path)
    yield log_path
    set_log_path(None)  # Reset to default


def append_migration_event(
    orphaned_todo_size: int,
    current_cycle: int,
    previous_session: str = "prev-session-123",
    current_session: str = "curr-session-456"
) -> bool:
    """Helper to append migration_detected event."""
    return append_event(
        event="migration_detected",
        data={
            "previous_session": previous_session,
            "current_session": current_session,
            "orphaned_todo_size": orphaned_todo_size,
            "current_cycle": current_cycle
        }
    )


def append_restoration_event(event_type: str, session_id: str, reason: str) -> bool:
    """Helper to append restoration outcome event."""
    return append_event(
        event=event_type,
        data={
            "session_id": session_id,
            "reason": reason
        }
    )


def get_unrestored_migrations() -> List[dict]:
    """
    Query for migration events without corresponding restoration events.

    Returns:
        List of migration events that haven't been restored or skipped
    """
    # Get all migration events
    migrations = query_events({'event_type': 'migration_detected'})

    # Get all restoration events
    restorations = query_events({'event_type': 'todo_restoration_completed'})
    skips = query_events({'event_type': 'todo_restoration_skipped'})

    # Extract session IDs from restoration/skip events
    restored_sessions = {
        event['data']['session_id']
        for event in (restorations + skips)
        if 'session_id' in event.get('data', {})
    }

    # Find migrations without restoration
    unrestored = [
        m for m in migrations
        if m['data']['current_session'] not in restored_sessions
    ]

    return unrestored


class TestTodoRecoveryIntelligence:
    """Integration tests for event log-based TODO recovery intelligence."""

    def test_empty_file_skipped(self, temp_event_log):
        """Empty TODO file (size < 100) should be skipped with event appended."""
        # Arrange: Migration with small file
        append_migration_event(orphaned_todo_size=50, current_cycle=172)

        # Act: Query unrestored migrations
        unrestored = get_unrestored_migrations()

        # Assert: Found unrestored migration
        assert len(unrestored) == 1
        assert unrestored[0]['data']['orphaned_todo_size'] == 50

        # Simulate skip decision
        session_id = unrestored[0]['data']['current_session']
        append_restoration_event(
            event_type="todo_restoration_skipped",
            session_id=session_id,
            reason="empty_file_below_threshold"
        )

        # Verify: No longer appears as unrestored
        unrestored_after = get_unrestored_migrations()
        assert len(unrestored_after) == 0

        # Verify: Skip event recorded
        skips = query_events({'event_type': 'todo_restoration_skipped'})
        assert len(skips) == 1
        assert skips[0]['data']['reason'] == "empty_file_below_threshold"

    def test_substantial_work_restored(self, temp_event_log):
        """Large TODO file (>200 bytes) in advanced cycle (>50) triggers restore."""
        # Arrange: Migration with substantial file at an advanced cycle
        append_migration_event(orphaned_todo_size=450, current_cycle=75)

        # Act: Query unrestored migrations
        unrestored = get_unrestored_migrations()

        # Assert: Found candidate for restoration
        assert len(unrestored) == 1
        migration = unrestored[0]
        assert migration['data']['orphaned_todo_size'] == 450
        assert migration['data']['current_cycle'] == 75

        # Simulate restore decision
        session_id = migration['data']['current_session']
        append_restoration_event(
            event_type="todo_restoration_completed",
            session_id=session_id,
            reason="substantial_work_advanced_cycle"
        )

        # Verify: No longer appears as unrestored
        unrestored_after = get_unrestored_migrations()
        assert len(unrestored_after) == 0

        # Verify: Completion event recorded
        completions = query_events({'event_type': 'todo_restoration_completed'})
        assert len(completions) == 1
        assert completions[0]['data']['reason'] == "substantial_work_advanced_cycle"

    def test_ambiguous_asks_user(self, temp_event_log):
        """Edge cases (medium size, early cycle) should prompt user decision."""
        # Arrange: Migration with ambiguous context
        append_migration_event(orphaned_todo_size=150, current_cycle=10)

        # Act: Query unrestored migrations
        unrestored = get_unrestored_migrations()

        # Assert: Found migration requiring judgment
        assert len(unrestored) == 1
        migration = unrestored[0]

        # Verify heuristics indicate ambiguity
        size = migration['data']['orphaned_todo_size']
        cycle = migration['data']['current_cycle']

        # Neither clearly skip (size < 100) nor clearly restore (size > 200 AND cycle > 50)
        assert size >= 100  # Not empty
        assert not (size > 200 and cycle > 50)  # Not clearly substantial

    def test_completion_event_appended(self, temp_event_log):
        """Restoration creates todo_restoration_completed event."""
        # Arrange: Migration event
        append_migration_event(orphaned_todo_size=300, current_cycle=100)
        unrestored = get_unrestored_migrations()
        session_id = unrestored[0]['data']['current_session']

        # Act: Append completion event
        success = append_restoration_event(
            event_type="todo_restoration_completed",
            session_id=session_id,
            reason="manual_restoration"
        )

        # Assert: Event appended successfully
        assert success is True

        # Verify: Event queryable
        completions = query_events({'event_type': 'todo_restoration_completed'})
        assert len(completions) == 1
        assert completions[0]['data']['session_id'] == session_id

    def test_skip_event_appended(self, temp_event_log):
        """Skip creates todo_restoration_skipped event."""
        # Arrange: Migration event
        append_migration_event(orphaned_todo_size=20, current_cycle=5)
        unrestored = get_unrestored_migrations()
        session_id = unrestored[0]['data']['current_session']

        # Act: Append skip event
        success = append_restoration_event(
            event_type="todo_restoration_skipped",
            session_id=session_id,
            reason="trivial_file"
        )

        # Assert: Event appended successfully
        assert success is True

        # Verify: Event queryable
        skips = query_events({'event_type': 'todo_restoration_skipped'})
        assert len(skips) == 1
        assert skips[0]['data']['reason'] == "trivial_file"

    def test_query_unrestored_migrations(self, temp_event_log):
        """Set difference query correctly identifies unrestored migrations."""
        # Arrange: Multiple migrations with mixed restoration states
        append_migration_event(
            orphaned_todo_size=100,
            current_cycle=50,
            previous_session="old-1",
            current_session="new-1"
        )
        append_migration_event(
            orphaned_todo_size=200,
            current_cycle=75,
            previous_session="old-2",
            current_session="new-2"
        )
        append_migration_event(
            orphaned_todo_size=300,
            current_cycle=100,
            previous_session="old-3",
            current_session="new-3"
        )

        # Restore first migration
        append_restoration_event(
            event_type="todo_restoration_completed",
            session_id="new-1",
            reason="test"
        )

        # Skip third migration
        append_restoration_event(
            event_type="todo_restoration_skipped",
            session_id="new-3",
            reason="test"
        )

        # Act: Query unrestored
        unrestored = get_unrestored_migrations()

        # Assert: Only second migration unrestored
        assert len(unrestored) == 1
        assert unrestored[0]['data']['current_session'] == "new-2"
        assert unrestored[0]['data']['orphaned_todo_size'] == 200
