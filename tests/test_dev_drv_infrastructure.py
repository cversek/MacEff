#!/usr/bin/env python3
"""
Test suite for Development Drive (DEV_DRV) and Delegation Drive (DELEG_DRV) infrastructure.

Focuses on:
- Minimal timestamp formatting for high-frequency hooks
- SessionOperationalState drive tracking fields
- DEV_DRV lifecycle and stats accumulation
- DELEG_DRV lifecycle and stats accumulation
- Safe failure patterns (None handling)
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macf.utils import (
    SessionOperationalState,
    complete_deleg_drv,
    complete_dev_drv,
    format_macf_footer,
    format_minimal_temporal_message,
    get_deleg_drv_stats,
    get_dev_drv_stats,
    get_last_user_prompt_uuid,
    get_minimal_timestamp,
    start_deleg_drv,
    start_dev_drv,
)


# =============================================================================
# Minimal Timestamp Tests
# =============================================================================


def test_get_minimal_timestamp_format():
    """Test minimal timestamp returns correct format."""
    timestamp = get_minimal_timestamp()

    # Should match "HH:MM:SS AM/PM" format
    assert len(timestamp) == 11  # "03:22:45 PM"
    assert timestamp[2] == ":"
    assert timestamp[5] == ":"
    assert timestamp[8] == " "
    assert timestamp[-2:] in ("AM", "PM")


def test_format_minimal_temporal_message():
    """Test minimal temporal message includes 🏗️ tag."""
    timestamp = "03:22:45 PM"
    message = format_minimal_temporal_message(timestamp)

    assert "🏗️ MACF" in message
    assert timestamp in message
    assert message == "🏗️ MACF | 03:22:45 PM"


def test_format_macf_footer_shortened_tag():
    """Test MACF footer uses shortened 🏗️ tag."""
    footer = format_macf_footer()

    assert "🏗️ MACF Tools" in footer
    # Should include auto-detected environment
    assert "Environment:" in footer
    # Should NOT contain old long tag
    assert "🔴 MACF CONSCIOUSNESS INFRASTRUCTURE 🔴" not in footer


# =============================================================================
# SessionOperationalState Drive Fields Tests
# =============================================================================


def test_session_state_has_dev_drv_fields():
    """Test SessionOperationalState has DEV_DRV tracking fields."""
    state = SessionOperationalState(session_id="test", agent_id="agent")

    assert hasattr(state, "current_dev_drv_started_at")
    assert hasattr(state, "current_dev_drv_prompt_uuid")
    assert hasattr(state, "dev_drv_count")
    assert hasattr(state, "total_dev_drv_duration")

    # Defaults
    assert state.current_dev_drv_started_at is None
    assert state.current_dev_drv_prompt_uuid is None
    assert state.dev_drv_count == 0
    assert state.total_dev_drv_duration == 0.0


def test_session_state_has_deleg_drv_fields():
    """Test SessionOperationalState has DELEG_DRV tracking fields."""
    state = SessionOperationalState(session_id="test", agent_id="agent")

    assert hasattr(state, "current_deleg_drv_started_at")
    assert hasattr(state, "deleg_drv_count")
    assert hasattr(state, "total_deleg_drv_duration")

    # Defaults
    assert state.current_deleg_drv_started_at is None
    assert state.deleg_drv_count == 0
    assert state.total_deleg_drv_duration == 0.0


# =============================================================================
# DEV_DRV Lifecycle Tests
# =============================================================================


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_dev_drv_start(mock_config, mock_get_session_dir, tmp_path):
    """Test DEV_DRV start marks timestamp."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Start DEV_DRV
    success = start_dev_drv(session_id)
    assert success is True

    # Load and verify timestamp set
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.current_dev_drv_started_at is not None
    assert isinstance(state.current_dev_drv_started_at, float)


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_dev_drv_complete_updates_stats(mock_config, mock_get_session_dir, tmp_path):
    """Test DEV_DRV completion updates stats."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Start and complete DEV_DRV
    start_dev_drv(session_id)
    time.sleep(0.01)  # Small delay to ensure duration > 0
    success, duration = complete_dev_drv(session_id)

    assert success is True
    assert duration > 0

    # Verify stats updated
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.dev_drv_count == 1
    assert state.total_dev_drv_duration > 0
    assert state.current_dev_drv_started_at is None  # Cleared


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_dev_drv_stats_accumulation(mock_config, mock_get_session_dir, tmp_path):
    """Test DEV_DRV stats accumulate across multiple drives."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session_accumulation"  # Unique session ID

    # Run 3 DEV_DRVs
    for _ in range(3):
        start_dev_drv(session_id)
        time.sleep(0.01)
        complete_dev_drv(session_id)

    # Check stats
    stats = get_dev_drv_stats(session_id)
    assert stats["count"] == 3
    assert stats["total_duration"] > 0
    assert stats["avg_duration"] > 0
    assert stats["current_started_at"] is None


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_dev_drv_complete_without_start_fails_safely(mock_config, mock_get_session_dir, tmp_path):
    """Test completing DEV_DRV without starting fails safely."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Try to complete without starting
    success, duration = complete_dev_drv(session_id)

    assert success is False
    assert duration == 0.0


# =============================================================================
# DELEG_DRV Lifecycle Tests
# =============================================================================


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_deleg_drv_start(mock_config, mock_get_session_dir, tmp_path):
    """Test DELEG_DRV start marks timestamp."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Start DELEG_DRV
    success = start_deleg_drv(session_id)
    assert success is True

    # Load and verify timestamp set
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.current_deleg_drv_started_at is not None
    assert isinstance(state.current_deleg_drv_started_at, float)


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_deleg_drv_complete_updates_stats(mock_config, mock_get_session_dir, tmp_path):
    """Test DELEG_DRV completion updates stats."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Start and complete DELEG_DRV
    start_deleg_drv(session_id)
    time.sleep(0.01)  # Small delay to ensure duration > 0
    success, duration = complete_deleg_drv(session_id)

    assert success is True
    assert duration > 0

    # Verify stats updated
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.deleg_drv_count == 1
    assert state.total_deleg_drv_duration > 0
    assert state.current_deleg_drv_started_at is None  # Cleared


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_deleg_drv_stats_accumulation(mock_config, mock_get_session_dir, tmp_path):
    """Test DELEG_DRV stats accumulate across multiple drives."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session_deleg_accumulation"  # Unique session ID

    # Run 3 DELEG_DRVs
    for _ in range(3):
        start_deleg_drv(session_id)
        time.sleep(0.01)
        complete_deleg_drv(session_id)

    # Check stats
    stats = get_deleg_drv_stats(session_id)
    assert stats["count"] == 3
    assert stats["total_duration"] > 0
    assert stats["avg_duration"] > 0
    assert stats["current_started_at"] is None


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_deleg_drv_complete_without_start_fails_safely(mock_config, mock_get_session_dir, tmp_path):
    """Test completing DELEG_DRV without starting fails safely."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session"

    # Try to complete without starting
    success, duration = complete_deleg_drv(session_id)

    assert success is False
    assert duration == 0.0


# =============================================================================
# Safe Failure Patterns
# =============================================================================


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_dev_drv_stats_with_zero_count(mock_config, mock_get_session_dir, tmp_path):
    """Test DEV_DRV stats with zero count returns safe defaults."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session_zero_count"  # Unique session ID

    stats = get_dev_drv_stats(session_id)

    assert stats["count"] == 0
    assert stats["total_duration"] == 0.0
    assert stats["avg_duration"] == 0.0
    assert stats["current_started_at"] is None
    assert stats["prompt_uuid"] is None


@patch("macf.utils.get_session_dir")
@patch("macf.config.ConsciousnessConfig")
def test_deleg_drv_stats_with_zero_count(mock_config, mock_get_session_dir, tmp_path):
    """Test DELEG_DRV stats with zero count returns safe defaults."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path

    session_id = "test_session_deleg_zero_count"  # Unique session ID

    stats = get_deleg_drv_stats(session_id)

    assert stats["count"] == 0
    assert stats["total_duration"] == 0.0
    assert stats["avg_duration"] == 0.0
    assert stats["current_started_at"] is None


# =============================================================================
# DEV_DRV UUID Tracking Tests (Phase 1C)
# =============================================================================


@patch("macf.utils.get_session_dir")
@patch("macf.utils.drives.get_last_user_prompt_uuid")
@patch("macf.config.ConsciousnessConfig")
def test_uuid_captured_on_dev_drv_start(mock_config, mock_get_uuid, mock_get_session_dir, tmp_path):
    """Verify UUID captured when DEV_DRV starts."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path
    mock_get_uuid.return_value = "msg_01XYZ123abc"

    session_id = "test_session"

    # Start DEV_DRV
    success = start_dev_drv(session_id)
    assert success is True

    # Verify UUID captured
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.current_dev_drv_prompt_uuid == "msg_01XYZ123abc"


@patch("macf.utils.get_session_dir")
@patch("macf.utils.drives.get_last_user_prompt_uuid")
@patch("macf.config.ConsciousnessConfig")
def test_uuid_persists_in_state(mock_config, mock_get_uuid, mock_get_session_dir, tmp_path):
    """Verify UUID survives state save/load cycle."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path
    mock_get_uuid.return_value = "msg_01ABC456def"

    session_id = "test_session"

    # Start DEV_DRV with UUID
    start_dev_drv(session_id)

    # Load fresh state from disk
    state = SessionOperationalState.load(session_id, "test_agent")

    # UUID should still be present
    assert state.current_dev_drv_prompt_uuid == "msg_01ABC456def"


@patch("macf.utils.get_session_dir")
@patch("macf.utils.drives.get_last_user_prompt_uuid")
@patch("macf.config.ConsciousnessConfig")
def test_uuid_included_in_stats(mock_config, mock_get_uuid, mock_get_session_dir, tmp_path):
    """Verify get_dev_drv_stats() includes prompt_uuid."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path
    mock_get_uuid.return_value = "msg_01PQR789ghi"

    session_id = "test_session"

    # Start DEV_DRV
    start_dev_drv(session_id)

    # Get stats
    stats = get_dev_drv_stats(session_id)

    # Verify UUID in stats
    assert "prompt_uuid" in stats
    assert stats["prompt_uuid"] == "msg_01PQR789ghi"


@patch("macf.utils.get_session_dir")
@patch("macf.utils.drives.get_last_user_prompt_uuid")
@patch("macf.config.ConsciousnessConfig")
def test_uuid_cleared_on_completion(mock_config, mock_get_uuid, mock_get_session_dir, tmp_path):
    """Verify UUID cleared when DEV_DRV completes."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path
    mock_get_uuid.return_value = "msg_01STU012jkl"

    session_id = "test_session"

    # Start DEV_DRV with UUID
    start_dev_drv(session_id)
    time.sleep(0.01)

    # Complete DEV_DRV
    complete_dev_drv(session_id)

    # Verify UUID cleared
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.current_dev_drv_prompt_uuid is None


@patch("macf.utils.get_session_dir")
@patch("macf.utils.drives.get_last_user_prompt_uuid")
@patch("macf.config.ConsciousnessConfig")
def test_uuid_handles_missing_gracefully(mock_config, mock_get_uuid, mock_get_session_dir, tmp_path):
    """Verify generated UUID when get_last_user_prompt_uuid() returns None."""
    mock_config.return_value.agent_id = "test_agent"
    mock_get_session_dir.return_value = tmp_path
    mock_get_uuid.return_value = None  # Simulate failure

    session_id = "test_session"

    # Start DEV_DRV
    success = start_dev_drv(session_id)
    assert success is True  # Should not crash

    # Verify UUID is generated (gen_XXXXXXXX format) for event matching
    state = SessionOperationalState.load(session_id, "test_agent")
    assert state.current_dev_drv_prompt_uuid is not None
    assert state.current_dev_drv_prompt_uuid.startswith("gen_")
