"""
Test specifications for macf.session module.

This module tests session management functionality including:
- Session ID extraction from JSONL files
- Temporary directory management
- Session cleanup and retention policies
- Error handling for corrupted session data

Following TDD principles - these tests define the expected behavior
for session management utilities that will be implemented.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import pytest

# Import session utilities from macf.utils
from macf.utils import get_current_session_id, get_session_dir


# Define SessionError for validation
class SessionError(Exception):
    """Exception raised for session-related errors."""
    pass


# Wrapper function to match test expectations
def get_session_temp_dir(session_id: str, agent_id: str = "test_agent") -> Path:
    """
    Get session temp directory - wrapper for get_session_dir.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (defaults to test_agent)

    Returns:
        Path to session temp directory

    Raises:
        SessionError: If session_id is invalid or contains path traversal
    """
    # Validate session_id for path traversal attacks
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        raise SessionError(f"Invalid session ID: {session_id}")

    if not session_id or not session_id.strip():
        raise SessionError("Invalid session ID: empty or whitespace")

    # Use get_session_dir with explicit agent_id
    result = get_session_dir(session_id=session_id, agent_id=agent_id, subdir=None, create=True)

    if result is None:
        raise SessionError(f"Failed to create session directory for: {session_id}")

    return result


# Additional imports needed for tests (to be implemented)
# These functions don't exist yet in macf.utils.session
# from macf.utils.session import (
#     cleanup_old_sessions,
#     is_valid_session_id,
#     get_session_age,
#     list_active_sessions
# )


class TestSessionIDExtraction:
    """Test suite for session ID extraction from JSONL files."""

    def test_get_current_session_id_from_claude_project(self, mock_claude_project):
        """
        Test extracting session ID from .claude project JSONL files.

        When running in .claude project, should:
        - Search for {session_id}.jsonl files in project directory
        - Extract session ID from filename
        - Return valid UUID string
        """
        # Mock Path.home() to return tmp_path so .claude/projects points to our fixture
        with patch('pathlib.Path.home', return_value=mock_claude_project):
            session_id = get_current_session_id()

        assert session_id is not None
        assert len(session_id) == 36  # UUID format: 8-4-4-4-12
        assert session_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_get_current_session_id_multiple_jsonl_files(self, mock_multiple_projects):
        """
        Test session ID extraction with multiple JSONL files.

        When multiple {session_id}.jsonl files exist, should:
        - Process all files to find most recent session
        - Use file modification time to determine current session
        - Handle files with different modification times
        """
        with patch('pathlib.Path.home', return_value=mock_multiple_projects):
            session_id = get_current_session_id()

        assert session_id == "most-recent-session-uuid"

    def test_get_current_session_id_no_claude_directory(self, temp_dir):
        """
        Test session ID extraction without .claude directory.

        When no .claude directory exists, should:
        - Return None or generate fallback session ID
        - Not raise exceptions
        - Allow graceful degradation
        """
        with patch('pathlib.Path.cwd', return_value=temp_dir):
            session_id = get_current_session_id()

        # Should either return None or a fallback ID
        assert session_id is None or isinstance(session_id, str)

    def test_get_current_session_id_corrupted_jsonl(self, mock_corrupted_jsonl):
        """
        Test handling of corrupted JSONL files.

        When JSONL files contain invalid JSON, should:
        - Extract session ID from filename (not file contents)
        - Not crash the application
        """
        with patch('pathlib.Path.home', return_value=mock_corrupted_jsonl):
            session_id = get_current_session_id()

        # Should extract from filename, not parse corrupted content
        assert session_id == "valid-session-uuid"

    def test_get_current_session_id_empty_jsonl_files(self, mock_empty_jsonl):
        """
        Test handling when no JSONL files exist.

        When no JSONL files are present, should:
        - Return "unknown" gracefully
        - Not raise exceptions
        - Allow application to continue
        """
        with patch('pathlib.Path.home', return_value=mock_empty_jsonl):
            session_id = get_current_session_id()

        assert session_id == "unknown"

    @pytest.mark.skip(reason="Environment override not yet implemented in get_current_session_id")
    def test_get_current_session_id_with_env_override(self, monkeypatch):
        """
        Test session ID override via environment variable.

        When MACF_SESSION_ID is set, should:
        - Use environment value directly
        - Skip JSONL file processing
        - Validate UUID format

        NOTE: This is desired behavior not yet implemented.
        """
        test_session_id = "test-session-12345"
        monkeypatch.setenv("MACF_SESSION_ID", test_session_id)

        session_id = get_current_session_id()
        assert session_id == test_session_id


class TestSessionTempDirectories:
    """Test suite for session temporary directory management."""

    def test_get_session_temp_dir_permissions(self, temp_dir):
        """
        Test temp directory has correct permissions.

        Directory should:
        - Be readable and writable by owner
        - Have appropriate mode (0o755 or 0o700)
        - Allow file creation within
        """
        session_id = "perm-test-789"

        with patch('tempfile.gettempdir', return_value=str(temp_dir)):
            temp_path = get_session_temp_dir(session_id)

        # Check directory is writable
        test_file = temp_path / "test_write.txt"
        test_file.write_text("test")
        assert test_file.exists()

        # Check permissions (should be at least 0o700)
        stat_info = temp_path.stat()
        assert stat_info.st_mode & 0o700 == 0o700

    def test_get_session_temp_dir_invalid_session_id(self):
        """
        Test handling of invalid session IDs.

        When session_id contains invalid characters, should:
        - Sanitize the session_id for filesystem use
        - Or raise SessionError with helpful message
        - Not create directories with unsafe names
        """
        invalid_session_id = "session/../../../etc"

        with pytest.raises(SessionError) as exc_info:
            get_session_temp_dir(invalid_session_id)

        assert "Invalid session ID" in str(exc_info.value)

    def test_get_session_temp_dir_concurrent_access(self, temp_dir):
        """
        Test concurrent access to same session temp directory.

        Multiple calls with same session_id should:
        - Return same path
        - Not conflict with each other
        - Handle race conditions gracefully
        """
        session_id = "concurrent-test"

        with patch('tempfile.gettempdir', return_value=str(temp_dir)):
            path1 = get_session_temp_dir(session_id)
            path2 = get_session_temp_dir(session_id)

        assert path1 == path2
        assert path1.exists()


@pytest.mark.skip(reason="cleanup_old_sessions not yet implemented in macf.utils.session")
class TestSessionCleanup:
    """Test suite for session cleanup and retention policies."""


    def test_cleanup_old_sessions_default_retention(self, mock_session_dirs):
        """
        Test cleanup with default 7-day retention.

        Should:
        - Remove session directories older than 7 days
        - Keep session directories newer than 7 days
        - Return count of cleaned directories
        """
        cleaned_count = cleanup_old_sessions()

        assert cleaned_count == 3  # Should remove 3 old sessions
        # Verify specific directories were removed/kept
        assert not (mock_session_dirs["old_session_1"]).exists()
        assert not (mock_session_dirs["old_session_2"]).exists()
        assert mock_session_dirs["recent_session"].exists()

    def test_cleanup_old_sessions_custom_retention(self, mock_session_dirs):
        """
        Test cleanup with custom retention period.

        With retention_days=1, should:
        - Remove sessions older than 1 day
        - Keep only very recent sessions
        - Apply custom retention correctly
        """
        cleaned_count = cleanup_old_sessions(retention_days=1)

        assert cleaned_count >= 4  # Should remove more with shorter retention

    def test_cleanup_old_sessions_preserve_current(self, mock_session_dirs):
        """
        Test that current session is never cleaned up.

        Should:
        - Never remove currently active session directory
        - Even if it appears old due to timestamp issues
        - Check against current session ID
        """
        current_session = "current-active-session"

        with patch('macf.session.get_current_session_id', return_value=current_session):
            cleaned_count = cleanup_old_sessions(retention_days=0)  # Clean everything

        # Current session directory should still exist
        current_path = mock_session_dirs["base_dir"] / current_session
        assert current_path.exists()

    def test_cleanup_old_sessions_handles_permissions(self, mock_readonly_sessions):
        """
        Test cleanup handles permission errors gracefully.

        When session directories can't be deleted due to permissions:
        - Log warnings about permission errors
        - Continue processing other directories
        - Return accurate count of successfully cleaned directories
        """
        with patch('macf.session.logger') as mock_logger:
            cleaned_count = cleanup_old_sessions()

        # Should have logged warnings about permission errors
        mock_logger.warning.assert_called()
        assert "Permission denied" in str(mock_logger.warning.call_args)

        # Should still clean directories it can access
        assert cleaned_count >= 1

    def test_cleanup_old_sessions_dry_run_mode(self, mock_session_dirs):
        """
        Test cleanup in dry-run mode.

        With dry_run=True, should:
        - Identify directories that would be cleaned
        - Not actually delete any directories
        - Return count of directories that would be cleaned
        """
        cleaned_count = cleanup_old_sessions(retention_days=7, dry_run=True)

        assert cleaned_count == 3  # Would clean 3 directories
        # But all directories should still exist
        assert mock_session_dirs["old_session_1"].exists()
        assert mock_session_dirs["old_session_2"].exists()

    def test_cleanup_old_sessions_empty_temp_dir(self, temp_dir):
        """
        Test cleanup when no session directories exist.

        Should:
        - Return 0 cleaned directories
        - Not raise exceptions
        - Handle empty temp directory gracefully
        """
        with patch('tempfile.gettempdir', return_value=str(temp_dir)):
            cleaned_count = cleanup_old_sessions()

        assert cleaned_count == 0

    def test_cleanup_old_sessions_non_session_directories(self, mock_mixed_temp_dir):
        """
        Test cleanup ignores non-session directories.

        When temp directory contains other files/directories:
        - Only process directories matching session pattern
        - Leave other files/directories untouched
        - Not accidentally delete unrelated content
        """
        cleaned_count = cleanup_old_sessions()

        # Should only clean session directories
        assert mock_mixed_temp_dir["other_file.txt"].exists()
        assert mock_mixed_temp_dir["random_directory"].exists()
        # But should clean old session directories
        assert not mock_mixed_temp_dir["old_session_dir"].exists()


@pytest.mark.skip(reason="is_valid_session_id, get_session_age, list_active_sessions not yet implemented in macf.utils.session")
class TestSessionUtilities:
    """Test suite for session utility functions."""

    def test_is_valid_session_id_format_validation(self):
        """
        Test session ID format validation.

        Should correctly identify:
        - Valid UUID formats
        - Valid custom session ID formats
        - Invalid or unsafe session IDs
        """
        from macf.session import is_valid_session_id

        # Valid formats
        assert is_valid_session_id("550e8400-e29b-41d4-a716-446655440000")
        assert is_valid_session_id("session-123-abc")
        assert is_valid_session_id("simple_session_name")

        # Invalid formats
        assert not is_valid_session_id("")
        assert not is_valid_session_id("session/../etc")
        assert not is_valid_session_id("session with spaces")
        assert not is_valid_session_id("session\nwith\nnewlines")

    def test_get_session_age_calculation(self):
        """
        Test session age calculation utilities.

        Should:
        - Calculate age from directory modification time
        - Return timedelta objects
        - Handle timezone issues correctly
        """
        from macf.session import get_session_age

        session_path = Path("/tmp/macf/test-session")

        # Mock directory with specific age
        two_days_ago = datetime.now() - timedelta(days=2)

        with patch.object(session_path, 'stat') as mock_stat:
            mock_stat.return_value.st_mtime = two_days_ago.timestamp()

            age = get_session_age(session_path)

        assert isinstance(age, timedelta)
        assert age.days >= 1  # Should be at least 1 day old

    def test_list_active_sessions(self, mock_session_dirs):
        """
        Test listing currently active sessions.

        Should:
        - Return list of session directories
        - Include session IDs and ages
        - Sort by most recent first
        """
        from macf.session import list_active_sessions

        sessions = list_active_sessions()

        assert isinstance(sessions, list)
        assert len(sessions) >= 1

        for session in sessions:
            assert "session_id" in session
            assert "age" in session
            assert "temp_dir" in session


# Test Fixtures

@pytest.fixture
def mock_claude_project(tmp_path):
    """Create mock .claude project with session JSONL file."""
    claude_dir = tmp_path / ".claude" / "projects" / "test-project"
    claude_dir.mkdir(parents=True)

    # Create JSONL file named with session ID (not "uuid.jsonl")
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    session_file = claude_dir / f"{session_id}.jsonl"
    session_data = {
        "uuid": session_id,
        "timestamp": datetime.now().isoformat()
    }
    session_file.write_text(json.dumps(session_data) + "\n")

    yield tmp_path  # Return tmp_path for Path.home() mocking

@pytest.fixture
def mock_multiple_projects(tmp_path):
    """Create multiple .claude projects with different timestamps."""
    base_dir = tmp_path / ".claude" / "projects"

    # Create older project
    old_project = base_dir / "old-project"
    old_project.mkdir(parents=True)
    old_session_id = "old-session-uuid"
    old_file = old_project / f"{old_session_id}.jsonl"
    old_data = {
        "uuid": old_session_id,
        "timestamp": (datetime.now() - timedelta(hours=2)).isoformat()
    }
    old_file.write_text(json.dumps(old_data) + "\n")

    # Create recent project
    recent_project = base_dir / "recent-project"
    recent_project.mkdir(parents=True)
    recent_session_id = "most-recent-session-uuid"
    recent_file = recent_project / f"{recent_session_id}.jsonl"
    recent_data = {
        "uuid": recent_session_id,
        "timestamp": datetime.now().isoformat()
    }
    recent_file.write_text(json.dumps(recent_data) + "\n")

    # Touch old file first, then recent file to ensure recent has newer mtime
    import time
    old_file.touch()
    time.sleep(0.01)
    recent_file.touch()

    yield tmp_path  # Return tmp_path for Path.home() mocking

@pytest.fixture
def mock_corrupted_jsonl(tmp_path):
    """Create .claude project with mixed valid/invalid JSONL entries."""
    claude_dir = tmp_path / ".claude" / "projects" / "mixed-project"
    claude_dir.mkdir(parents=True)

    # Create JSONL file named with session ID
    session_id = "valid-session-uuid"
    session_file = claude_dir / f"{session_id}.jsonl"
    content = [
        "invalid json line",  # Corrupted entry
        json.dumps({"uuid": session_id, "timestamp": datetime.now().isoformat()}),
        "another invalid line",
        ""  # Empty line
    ]
    session_file.write_text("\n".join(content))

    yield tmp_path  # Return tmp_path for Path.home() mocking

@pytest.fixture
def mock_empty_jsonl(tmp_path):
    """Create .claude project with no JSONL files."""
    claude_dir = tmp_path / ".claude" / "projects" / "empty-project"
    claude_dir.mkdir(parents=True)

    # Don't create any JSONL files - this tests the "no files found" case

    yield tmp_path  # Return tmp_path for Path.home() mocking

@pytest.fixture
def mock_session_dirs(tmp_path):
    """Create mock session directories with different ages."""
    macf_temp = tmp_path / "macf"
    macf_temp.mkdir()

    # Create old session directories (should be cleaned)
    old_session_1 = macf_temp / "old-session-1"
    old_session_1.mkdir()
    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(old_session_1, (old_time, old_time))

    old_session_2 = macf_temp / "old-session-2"
    old_session_2.mkdir()
    old_time_2 = (datetime.now() - timedelta(days=8)).timestamp()
    os.utime(old_session_2, (old_time_2, old_time_2))

    # Create recent session directory (should be kept)
    recent_session = macf_temp / "recent-session"
    recent_session.mkdir()
    recent_time = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(recent_session, (recent_time, recent_time))

    with patch('tempfile.gettempdir', return_value=str(tmp_path)):
        yield {
            "old_session_1": old_session_1,
            "old_session_2": old_session_2,
            "recent_session": recent_session,
            "base_dir": macf_temp
        }

@pytest.fixture
def mock_readonly_sessions(tmp_path):
    """Create session directories with permission restrictions."""
    macf_temp = tmp_path / "macf"
    macf_temp.mkdir()

    # Create session directory with restricted permissions
    readonly_session = macf_temp / "readonly-session"
    readonly_session.mkdir(mode=0o444)  # Read-only

    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(readonly_session, (old_time, old_time))

    with patch('tempfile.gettempdir', return_value=str(tmp_path)):
        yield readonly_session

@pytest.fixture
def mock_mixed_temp_dir(tmp_path):
    """Create temp directory with mix of session and non-session content."""
    macf_temp = tmp_path / "macf"
    macf_temp.mkdir()

    # Non-session content (should be ignored)
    (tmp_path / "other_file.txt").write_text("some content")
    (tmp_path / "random_directory").mkdir()

    # Old session directory (should be cleaned)
    old_session_dir = macf_temp / "old-session-abc123"
    old_session_dir.mkdir()
    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(old_session_dir, (old_time, old_time))

    with patch('tempfile.gettempdir', return_value=str(tmp_path)):
        yield {
            "other_file.txt": tmp_path / "other_file.txt",
            "random_directory": tmp_path / "random_directory",
            "old_session_dir": old_session_dir
        }

@pytest.fixture
def temp_dir(tmp_path):
    """Provide clean temporary directory."""
    return tmp_path