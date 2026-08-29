"""Tests for session-migration recovery message formatting and helpers.

Coverage target: macf/src/macf/hooks/recovery.py
    - format_session_migration_message()
    - _format_todo_list()
    - read_recovery_policy()

These are the pieces that produce the calm "🔄 SESSION MIGRATION DETECTED"
message (crash/restart, no compaction) documented in CLAUDE.md's SessionStart
Hook Mode-Aware Detection section, plus the TODO-list formatting used inside
recovery messages generally. None of the three were exercised before these
tests (existing test_recovery.py only covers format_consciousness_recovery_message,
the compaction-trauma path).
"""

from macf.hooks.recovery import (
    format_session_migration_message,
    read_recovery_policy,
    _format_todo_list,
)


def test_format_session_migration_message_includes_both_session_id_prefixes():
    """Both session IDs appear (truncated to their 8-char short form)."""
    msg = format_session_migration_message(
        previous_session_id="prevSESSIONXXXX",
        current_session_id="currSESSIONYYYY",
        orphaned_todo_path="/tmp/todos/prev.json",
    )

    assert "prevSESS" in msg
    assert "currSESS" in msg
    assert "SESSION MIGRATION DETECTED" in msg


def test_format_session_migration_message_shows_orphaned_path_when_given():
    """A real orphaned TODO path is echoed verbatim in the message."""
    msg = format_session_migration_message(
        previous_session_id="prev1234",
        current_session_id="curr1234",
        orphaned_todo_path="/tmp/todos/orphan-abc.json",
    )

    assert "/tmp/todos/orphan-abc.json" in msg


def test_format_session_migration_message_shows_fallback_when_path_empty():
    """An empty orphaned path produces the explicit 'no file found' fallback."""
    msg = format_session_migration_message(
        previous_session_id="prev1234",
        current_session_id="curr1234",
        orphaned_todo_path="",
    )

    assert "No orphaned TODO file found" in msg


def test_format_todo_list_filters_to_pending_and_in_progress_only():
    """Completed/other-status todos are dropped; pending and in_progress survive."""
    todos = [
        {"content": "Write report", "status": "pending"},
        {"content": "Old finished thing", "status": "completed"},
        {"content": "Fix the bug", "status": "in_progress"},
    ]

    result = _format_todo_list(todos)

    assert "Write report" in result
    assert "Fix the bug" in result
    assert "Old finished thing" not in result


def test_format_todo_list_returns_no_pending_message_when_nothing_relevant():
    """Empty list and an all-completed list both collapse to the same message."""
    assert _format_todo_list([]) == "No pending todos."
    assert _format_todo_list([{"content": "Done", "status": "completed"}]) == "No pending todos."


def test_read_recovery_policy_reads_custom_file_and_falls_back_when_missing(tmp_path):
    """A given path's content is returned verbatim; a missing path falls back."""
    policy_file = tmp_path / "custom_recovery.md"
    policy_file.write_text("Read the roadmap. Then wait.\n")

    assert read_recovery_policy(str(policy_file)) == "Read the roadmap. Then wait."

    missing = tmp_path / "does_not_exist.md"
    fallback = read_recovery_policy(str(missing))
    assert "No custom recovery policy found" in fallback
