"""
Pragmatic unit tests for temporal utilities.

Testing philosophy: 4-6 tests per component, focus on core functionality,
skip exhaustive edge cases.
"""

import pytest
import time
from pathlib import Path
import sys
import os

# Add macf to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "src"))

from macf.utils import (
    get_temporal_context,
    calculate_session_duration,
    detect_execution_environment,
    format_temporal_awareness_section,
    format_macf_footer
)


class TestGetTemporalContext:
    """Test temporal context generation."""

    def test_returns_dict_with_required_keys(self):
        """Context dict has all required keys."""
        ctx = get_temporal_context()
        required_keys = ['timestamp_formatted', 'day_of_week', 'time_of_day', 'hour', 'timezone', 'iso_timestamp']
        for key in required_keys:
            assert key in ctx, f"Missing required key: {key}"

    def test_timestamp_formatted_has_correct_format(self):
        """Timestamp follows expected format pattern."""
        ctx = get_temporal_context()
        # Should contain date-like components and time
        assert ' ' in ctx['timestamp_formatted']
        assert ':' in ctx['timestamp_formatted']

    def test_time_of_day_classification_is_reasonable(self):
        """Time of day classification returns valid category."""
        ctx = get_temporal_context()
        valid_times = ['Morning', 'Afternoon', 'Evening', 'Late night / Early morning']
        assert ctx['time_of_day'] in valid_times

    def test_timezone_is_non_empty_string(self):
        """Timezone is populated."""
        ctx = get_temporal_context()
        assert isinstance(ctx['timezone'], str)
        assert len(ctx['timezone']) > 0


class TestCalculateSessionDuration:
    """Test session duration calculations."""

    def test_fresh_start_for_zero(self):
        """Returns 'Fresh start' for 0 timestamp."""
        assert calculate_session_duration(0.0) == "Fresh start"

    def test_fresh_start_for_none(self):
        """Returns 'Fresh start' for None timestamp."""
        assert calculate_session_duration(None) == "Fresh start"

    def test_formats_hours_correctly(self):
        """Formats duration with hours and minutes."""
        # 3 hours 24 minutes ago
        started_at = time.time() - (3 * 3600 + 24 * 60)
        result = calculate_session_duration(started_at)
        assert 'h' in result
        assert 'm' in result

    def test_formats_minutes_only(self):
        """Formats duration with only minutes for <1 hour."""
        # 45 minutes ago
        started_at = time.time() - (45 * 60)
        result = calculate_session_duration(started_at)
        assert 'm' in result
        assert 'h' not in result

    def test_handles_current_time_as_default_ended_at(self):
        """Uses current time when ended_at not provided."""
        started_at = time.time() - 60  # 1 minute ago
        result = calculate_session_duration(started_at)
        # Should be very recent (under 2 minutes)
        assert 'm' in result or 's' in result


class TestDetectExecutionEnvironment:
    """Test environment detection."""

    def test_returns_string(self):
        """Environment detection returns non-empty string."""
        env = detect_execution_environment()
        assert isinstance(env, str)
        assert len(env) > 0

    def test_contains_expected_keywords(self):
        """Environment string contains identifying keywords."""
        env = detect_execution_environment()
        # Should contain at least one expected keyword
        keywords = ['Host', 'MacEff', 'Container', 'Fallback']
        assert any(keyword in env for keyword in keywords)

    def test_handles_missing_env_vars_gracefully(self):
        """Works even without MACEFF_USER env var."""
        # Temporarily remove MACEFF_USER if present
        maceff_user = os.environ.pop('MACEFF_USER', None)
        try:
            env = detect_execution_environment()
            assert isinstance(env, str)
            assert len(env) > 0
        finally:
            # Restore if it existed
            if maceff_user:
                os.environ['MACEFF_USER'] = maceff_user


class TestFormatTemporalAwarenessSection:
    """Test temporal awareness section formatting."""

    def test_returns_non_empty_string(self):
        """Formatter returns non-empty formatted section."""
        ctx = get_temporal_context()
        section = format_temporal_awareness_section(ctx)
        assert isinstance(section, str)
        assert len(section) > 0

    def test_includes_timestamp_from_context(self):
        """Section includes timestamp."""
        ctx = get_temporal_context()
        section = format_temporal_awareness_section(ctx)
        # Should contain time-related content
        assert ':' in section  # Time formatting includes colons

    def test_includes_day_of_week(self):
        """Section includes day of week."""
        ctx = get_temporal_context()
        section = format_temporal_awareness_section(ctx)
        # Should contain day name
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        assert any(day in section for day in days)

    def test_optionally_includes_session_duration(self):
        """Section can include session duration when provided."""
        ctx = get_temporal_context()
        duration = "2h 15m"
        section = format_temporal_awareness_section(ctx, session_duration=duration)
        assert duration in section


class TestFormatMacfFooter:
    """Test MACF footer formatting."""

    def test_returns_non_empty_string(self):
        """Footer returns non-empty string."""
        footer = format_macf_footer()
        assert isinstance(footer, str)
        assert len(footer) > 0

    def test_includes_version_number(self):
        """Footer includes version information."""
        footer = format_macf_footer()
        # Should contain version-like pattern
        assert 'v' in footer.lower() or '.' in footer

    def test_includes_environment_string(self):
        """Footer includes environment identification."""
        footer = format_macf_footer()
        # Should auto-detect and include environment
        assert "Environment:" in footer
