"""Integration tests for Phase 1B Universal Temporal Awareness.

Tests the complete temporal infrastructure including:
- Temporal utilities integration
- DEV_DRV lifecycle tracking
- DELEG_DRV lifecycle tracking
- Hook message formatting
- Cross-component integration

Author: TestEng (pragmatic test suite)
"""

import pytest
import time
from pathlib import Path
from datetime import datetime

from macf.utils import (
    get_minimal_timestamp,
    get_temporal_context,
    format_minimal_temporal_message,
    format_temporal_awareness_section,
    format_macf_footer,
    detect_execution_environment,
    start_dev_drv,
    complete_dev_drv,
    get_dev_drv_stats,
    start_deleg_drv,
    complete_deleg_drv,
    get_deleg_drv_stats,
    get_last_user_prompt_uuid,
)
from unittest.mock import patch


@pytest.fixture(autouse=True)
def cleanup_test_state():
    """Clean up test session state files."""
    yield
    # Clean up /tmp/macf/test_agent/test_session_* directories
    import shutil
    test_base = Path("/tmp/macf/test_agent")
    if test_base.exists():
        shutil.rmtree(test_base)


class TestTemporalUtilitiesIntegration:
    """Integration tests for temporal utilities."""

    def test_minimal_timestamp_format(self):
        """Test minimal timestamp returns valid time format."""
        timestamp = get_minimal_timestamp()

        # Should match format: "HH:MM:SS AM/PM"
        assert len(timestamp) > 0
        assert ":" in timestamp
        assert any(period in timestamp for period in ["AM", "PM"])

    def test_temporal_context_all_fields(self):
        """Test temporal context returns all required fields."""
        context = get_temporal_context()

        # Verify all required fields present
        assert "timestamp_formatted" in context
        assert "day_of_week" in context
        assert "time_of_day" in context
        assert "hour" in context
        assert "timezone" in context
        assert "iso_timestamp" in context

        # Verify non-empty values
        assert len(context["timestamp_formatted"]) > 0
        assert len(context["day_of_week"]) > 0
        assert len(context["time_of_day"]) > 0
        assert isinstance(context["hour"], int)
        assert len(context["timezone"]) > 0
        assert len(context["iso_timestamp"]) > 0

    def test_minimal_temporal_message_format(self):
        """Test minimal temporal message formatter produces valid output."""
        timestamp = get_minimal_timestamp()
        message = format_minimal_temporal_message(timestamp)

        # Should include MACF tag and timestamp
        assert "🏗️ MACF" in message
        assert "|" in message
        assert any(period in message for period in ["AM", "PM"])

    def test_full_temporal_awareness_section(self):
        """Test full temporal awareness section has all fields."""
        temporal_ctx = get_temporal_context()
        section = format_temporal_awareness_section(temporal_ctx)

        # Should include all temporal context fields
        assert "Current Time" in section
        assert "Day" in section
        assert "Time of Day" in section
        assert "⏰ TEMPORAL AWARENESS" in section

    def test_macf_footer_format(self):
        """Test MACF footer format correctness."""
        footer = format_macf_footer()  # No args - auto-detects environment

        # Should include version and shortened tag
        assert "MACF" in footer
        assert "---" in footer  # Standard footer separator


class TestDEVDRVLifecycle:
    """Integration tests for Development Drive tracking."""

    @patch("macf.utils.drives._emit_event")
    def test_start_dev_drv_creates_timestamp(self, mock_emit):
        """Test starting DEV_DRV emits event with timestamp."""
        mock_emit.return_value = True
        session_id = "test_session_dev1"
        agent_id = "test_agent"

        result = start_dev_drv(session_id, agent_id)
        assert result is True

        # Verify event emitted with timestamp
        mock_emit.assert_called_once()
        event_data = mock_emit.call_args[0][1]
        assert "timestamp" in event_data
        assert isinstance(event_data["timestamp"], float)

    def test_complete_dev_drv_calculates_duration(self):
        """Test completing DEV_DRV calculates duration."""
        session_id = "test_session_dev2"
        agent_id = "test_agent"

        # Start and complete with measurable duration
        start_dev_drv(session_id, agent_id)
        time.sleep(0.1)  # 100ms duration

        success, duration = complete_dev_drv(session_id, agent_id)

        assert success is True
        assert duration >= 0.1  # At least 100ms

    def test_complete_dev_drv_without_start(self):
        """Test completing DEV_DRV without starting returns failure."""
        session_id = "test_session_dev3"
        agent_id = "test_agent"

        success, duration = complete_dev_drv(session_id, agent_id)

        assert success is False
        assert duration == 0.0

    def test_dev_drv_stats_accumulate(self):
        """Test DEV_DRV stats accumulate across multiple drives."""
        session_id = "test_session_dev4"
        agent_id = "test_agent"

        # Complete two DEV_DRVs
        start_dev_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_dev_drv(session_id, agent_id)

        start_dev_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_dev_drv(session_id, agent_id)

        # Check accumulated stats
        stats = get_dev_drv_stats(session_id, agent_id)
        assert stats["count"] == 2
        assert stats["total_duration"] >= 0.1

    def test_dev_drv_average_duration(self):
        """Test DEV_DRV average duration calculation."""
        session_id = "test_session_dev5"
        agent_id = "test_agent"

        # Complete multiple drives with known durations
        for _ in range(3):
            start_dev_drv(session_id, agent_id)
            time.sleep(0.05)
            complete_dev_drv(session_id, agent_id)

        stats = get_dev_drv_stats(session_id, agent_id)

        assert stats["count"] == 3
        assert stats["avg_duration"] > 0
        # Average should be roughly total/count
        expected_avg = stats["total_duration"] / stats["count"]
        assert abs(stats["avg_duration"] - expected_avg) < 0.001

    @patch("macf.utils.drives._emit_event")
    def test_dev_drv_state_persistence(self, mock_emit):
        """Test DEV_DRV event emitted (event-first architecture)."""
        mock_emit.return_value = True
        session_id = "test_session_dev6"
        agent_id = "test_agent"

        # Start emits event
        start_dev_drv(session_id, agent_id)

        # Event-first: verify event was emitted (persisted to JSONL)
        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0] == "dev_drv_started"


class TestDELEGDRVLifecycle:
    """Integration tests for Delegation Drive tracking."""

    @patch("macf.utils.drives._emit_event")
    def test_start_deleg_drv_creates_timestamp(self, mock_emit):
        """Test starting DELEG_DRV emits event with timestamp."""
        mock_emit.return_value = True
        session_id = "test_session_deleg1"
        agent_id = "test_agent"

        result = start_deleg_drv(session_id, agent_id)
        assert result is True

        # Verify event emitted with timestamp
        mock_emit.assert_called_once()
        event_data = mock_emit.call_args[0][1]
        assert "timestamp" in event_data
        assert isinstance(event_data["timestamp"], float)

    def test_complete_deleg_drv_calculates_duration(self):
        """Test completing DELEG_DRV calculates duration."""
        session_id = "test_session_deleg2"
        agent_id = "test_agent"

        # Start and complete with measurable duration
        start_deleg_drv(session_id, agent_id)
        time.sleep(0.1)  # 100ms duration

        success, duration = complete_deleg_drv(session_id, agent_id)

        assert success is True
        assert duration >= 0.1  # At least 100ms

    def test_complete_deleg_drv_without_start(self):
        """Test completing DELEG_DRV without starting returns failure."""
        session_id = "test_session_deleg3"
        agent_id = "test_agent"

        success, duration = complete_deleg_drv(session_id, agent_id)

        assert success is False
        assert duration == 0.0

    def test_deleg_drv_stats_accumulate(self):
        """Test DELEG_DRV stats accumulate across multiple delegations."""
        session_id = "test_session_deleg4"
        agent_id = "test_agent"

        # Complete two DELEG_DRVs
        start_deleg_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_deleg_drv(session_id, agent_id)

        start_deleg_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_deleg_drv(session_id, agent_id)

        # Check accumulated stats
        stats = get_deleg_drv_stats(session_id, agent_id)
        assert stats["count"] == 2
        assert stats["total_duration"] >= 0.1

    def test_deleg_drv_average_duration(self):
        """Test DELEG_DRV average duration calculation."""
        session_id = "test_session_deleg5"
        agent_id = "test_agent"

        # Complete multiple delegations with known durations
        for _ in range(3):
            start_deleg_drv(session_id, agent_id)
            time.sleep(0.05)
            complete_deleg_drv(session_id, agent_id)

        stats = get_deleg_drv_stats(session_id, agent_id)

        assert stats["count"] == 3
        assert stats["avg_duration"] > 0
        # Average should be roughly total/count
        expected_avg = stats["total_duration"] / stats["count"]
        assert abs(stats["avg_duration"] - expected_avg) < 0.001

    @patch("macf.utils.drives._emit_event")
    def test_deleg_drv_state_persistence(self, mock_emit):
        """Test DELEG_DRV event emitted (event-first architecture)."""
        mock_emit.return_value = True
        session_id = "test_session_deleg6"
        agent_id = "test_agent"

        # Start emits event
        start_deleg_drv(session_id, agent_id)

        # Event-first: verify event was emitted (persisted to JSONL)
        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0] == "deleg_drv_started"


class TestHookMessageFormatting:
    """Integration tests for hook message generation."""

    def test_minimal_temporal_message_includes_tag(self):
        """Test minimal temporal message includes 🏗️ tag."""
        timestamp = get_minimal_timestamp()
        message = format_minimal_temporal_message(timestamp)

        assert "🏗️" in message
        assert "MACF" in message

    def test_full_temporal_section_has_all_fields(self):
        """Test full temporal awareness section has all fields."""
        temporal_ctx = get_temporal_context()
        section = format_temporal_awareness_section(temporal_ctx)

        # All temporal context fields should be present
        required_fields = ["Current Time", "Day", "Time of Day"]
        for field in required_fields:
            assert field in section

    def test_dev_drv_completion_message_includes_stats(self):
        """Test DEV_DRV completion message includes stats."""
        session_id = "test_session_msg1"
        agent_id = "test_agent"

        # Complete a DEV_DRV to generate stats
        start_dev_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_dev_drv(session_id, agent_id)

        stats = get_dev_drv_stats(session_id, agent_id)

        # Stats should have valid data
        assert stats["count"] == 1
        assert stats["total_duration"] > 0
        assert stats["avg_duration"] > 0

    def test_deleg_drv_completion_message_includes_stats(self):
        """Test DELEG_DRV completion message includes stats."""
        session_id = "test_session_msg2"
        agent_id = "test_agent"

        # Complete a DELEG_DRV to generate stats
        start_deleg_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_deleg_drv(session_id, agent_id)

        stats = get_deleg_drv_stats(session_id, agent_id)

        # Stats should have valid data
        assert stats["count"] == 1
        assert stats["total_duration"] > 0
        assert stats["avg_duration"] > 0

    def test_environment_detection_returns_valid_string(self):
        """Test environment detection returns valid string."""
        env = detect_execution_environment()

        # Should return one of the valid environment types
        # MacEff Container (username), MacEff Host System, or Host System
        assert len(env) > 0
        assert any(keyword in env for keyword in ["MacEff", "Host", "Container"])


class TestCrossComponentIntegration:
    """End-to-end integration tests."""

    def test_complete_dev_drv_flow(self):
        """Test complete DEV_DRV flow: start → work → complete → stats."""
        session_id = "test_session_e2e1"
        agent_id = "test_agent"

        # Start DEV_DRV
        assert start_dev_drv(session_id, agent_id) is True

        # Simulate work
        time.sleep(0.1)

        # Complete DEV_DRV
        success, duration = complete_dev_drv(session_id, agent_id)
        assert success is True
        assert duration >= 0.1

        # Verify stats
        stats = get_dev_drv_stats(session_id, agent_id)
        assert stats["count"] == 1
        assert stats["total_duration"] >= 0.1
        assert stats["avg_duration"] >= 0.1

    def test_complete_deleg_drv_flow(self):
        """Test complete DELEG_DRV flow: start → delegate → complete → stats."""
        session_id = "test_session_e2e2"
        agent_id = "test_agent"

        # Start DELEG_DRV
        assert start_deleg_drv(session_id, agent_id) is True

        # Simulate delegation work
        time.sleep(0.1)

        # Complete DELEG_DRV
        success, duration = complete_deleg_drv(session_id, agent_id)
        assert success is True
        assert duration >= 0.1

        # Verify stats
        stats = get_deleg_drv_stats(session_id, agent_id)
        assert stats["count"] == 1
        assert stats["total_duration"] >= 0.1
        assert stats["avg_duration"] >= 0.1

    def test_temporal_awareness_available_in_all_formats(self):
        """Test temporal awareness available in all message formats."""
        # Minimal format
        timestamp = get_minimal_timestamp()
        minimal = format_minimal_temporal_message(timestamp)
        assert len(minimal) > 0
        assert "🏗️ MACF" in minimal

        # Full format
        temporal_ctx = get_temporal_context()
        full = format_temporal_awareness_section(temporal_ctx)
        assert len(full) > 0
        assert "Current Time" in full

        # Footer format
        footer = format_macf_footer()  # No args - auto-detects environment
        assert len(footer) > 0
        assert "MACF" in footer

    @patch("macf.utils.drives._emit_event")
    @patch("macf.event_queries.get_active_dev_drv_start")
    def test_stats_persist_and_accumulate_correctly(self, mock_get_active, mock_emit):
        """Test event emission accumulates correctly (event-first)."""
        mock_emit.return_value = True

        session_id = "test_session_e2e3"

        # Complete 3 DEV_DRVs with mocked start times
        for i in range(3):
            # Reset mock for start call
            mock_get_active.return_value = (time.time() - 0.05, f"uuid_{i}")
            start_dev_drv(session_id)
            complete_dev_drv(session_id)

        # Verify 6 events emitted (3 starts + 3 ends)
        assert mock_emit.call_count == 6

        # Verify event types alternated
        events = [call[0][0] for call in mock_emit.call_args_list]
        assert events.count("dev_drv_started") == 3
        assert events.count("dev_drv_ended") == 3

    def test_mixed_dev_and_deleg_tracking(self):
        """Test DEV_DRV and DELEG_DRV can be tracked independently."""
        session_id = "test_session_e2e4"
        agent_id = "test_agent"

        # Mix of DEV_DRV and DELEG_DRV
        start_dev_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_dev_drv(session_id, agent_id)

        start_deleg_drv(session_id, agent_id)
        time.sleep(0.05)
        complete_deleg_drv(session_id, agent_id)

        # Verify independent tracking
        dev_stats = get_dev_drv_stats(session_id, agent_id)
        deleg_stats = get_deleg_drv_stats(session_id, agent_id)

        assert dev_stats["count"] == 1
        assert deleg_stats["count"] == 1
        assert dev_stats["total_duration"] >= 0.05
        assert deleg_stats["total_duration"] >= 0.05

    @patch("macf.utils.drives._emit_event")
    @patch("macf.utils.drives.get_last_user_prompt_uuid")
    def test_dev_drv_uuid_lifecycle(self, mock_get_uuid, mock_emit):
        """Verify UUID included in emitted events (event-first architecture)."""
        mock_get_uuid.return_value = "msg_01TestUUID123"
        mock_emit.return_value = True

        session_id = "test_session_uuid"

        # Start DEV_DRV → verify UUID in event
        start_dev_drv(session_id)

        # Verify start event emitted with UUID
        start_call = mock_emit.call_args_list[0]
        assert start_call[0][0] == "dev_drv_started"
        assert start_call[0][1]["prompt_uuid"] == "msg_01TestUUID123"
