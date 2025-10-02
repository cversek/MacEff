#!/usr/bin/env python3
"""Tests for SessionOperationalState persistence."""

import json
import time
from pathlib import Path

import pytest

from macf.utils import SessionOperationalState, get_session_dir


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    """SessionOperationalState persists across save/load."""
    # Mock session directory to use tmp_path
    session_id = "test-session-123"
    agent_id = "TestAgent"

    def mock_get_session_dir(session_id=None, agent_id=None, subdir=None, create=True):
        base = tmp_path / agent_id / session_id
        if subdir:
            base = base / subdir
        if create:
            base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr("macf.utils.get_session_dir", mock_get_session_dir)

    # Create and save state
    state = SessionOperationalState(session_id, agent_id)
    state.auto_mode = True
    state.auto_mode_source = "test"
    state.pending_todos = [
        {"content": "Task 1", "status": "pending"},
        {"content": "Task 2", "status": "in_progress"}
    ]

    assert state.save()

    # Load and verify
    loaded = SessionOperationalState.load(session_id, agent_id)
    assert loaded.session_id == session_id
    assert loaded.agent_id == agent_id
    assert loaded.auto_mode is True
    assert loaded.auto_mode_source == "test"
    assert len(loaded.pending_todos) == 2
    assert loaded.pending_todos[0]["content"] == "Task 1"


def test_load_missing_file_returns_default(tmp_path, monkeypatch):
    """Load with missing file returns default instance."""
    session_id = "nonexistent-session"
    agent_id = "TestAgent"

    # Mock to return non-existent directory
    def mock_get_session_dir(session_id=None, agent_id=None, subdir=None, create=False):
        return None

    monkeypatch.setattr("macf.utils.get_session_dir", mock_get_session_dir)

    # Should return default instance, not crash
    loaded = SessionOperationalState.load(session_id, agent_id)
    assert loaded.session_id == session_id
    assert loaded.agent_id == agent_id
    assert loaded.auto_mode is False
    assert loaded.auto_mode_source == "default"
    assert len(loaded.pending_todos) == 0


def test_load_invalid_json_returns_default(tmp_path, monkeypatch):
    """Load with invalid JSON returns default instance."""
    session_id = "corrupt-session"
    agent_id = "TestAgent"

    # Create directory with corrupt JSON
    session_dir = tmp_path / agent_id / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session_state.json").write_text("{ invalid json }")

    def mock_get_session_dir(session_id=None, agent_id=None, subdir=None, create=False):
        return session_dir

    monkeypatch.setattr("macf.utils.get_session_dir", mock_get_session_dir)

    # Should return default instance, not crash
    loaded = SessionOperationalState.load(session_id, agent_id)
    assert loaded.session_id == session_id
    assert loaded.agent_id == agent_id
    assert loaded.auto_mode is False


def test_timestamp_updates_on_save(tmp_path, monkeypatch):
    """Timestamp gets updated on save."""
    session_id = "timestamp-test"
    agent_id = "TestAgent"

    def mock_get_session_dir(session_id=None, agent_id=None, subdir=None, create=True):
        base = tmp_path / agent_id / session_id
        if subdir:
            base = base / subdir
        if create:
            base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr("macf.utils.get_session_dir", mock_get_session_dir)

    # Create and save
    state = SessionOperationalState(session_id, agent_id)
    original_timestamp = state.last_updated

    time.sleep(0.01)  # Small delay to ensure timestamp differs

    assert state.save()
    assert state.last_updated > original_timestamp


def test_compaction_counter_increments(tmp_path, monkeypatch):
    """Compaction counter can be incremented."""
    session_id = "compaction-test"
    agent_id = "TestAgent"

    def mock_get_session_dir(session_id=None, agent_id=None, subdir=None, create=True):
        base = tmp_path / agent_id / session_id
        if subdir:
            base = base / subdir
        if create:
            base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr("macf.utils.get_session_dir", mock_get_session_dir)

    # Create state
    state = SessionOperationalState(session_id, agent_id)
    assert state.compaction_count == 0

    # Increment and save
    state.compaction_count = 1
    assert state.save()

    # Load and verify
    loaded = SessionOperationalState.load(session_id, agent_id)
    assert loaded.compaction_count == 1
