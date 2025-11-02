"""
Temporal utilities.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

try:
    import dateutil.tz  # type: ignore
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False

def get_formatted_timestamp() -> Tuple[str, datetime]:
    """Get formatted timestamp with day of week and timezone.

    Returns:
        Tuple of (formatted_string, datetime_object)
    """
    if DATEUTIL_AVAILABLE:
        eastern = dateutil.tz.gettz("America/New_York")
        now = datetime.now(tz=eastern)
    else:
        now = datetime.now(timezone.utc)

    formatted = now.strftime("%A, %b %d, %Y %I:%M:%S %p %Z")
    return formatted, now

def get_temporal_context() -> dict:
    """
    Master temporal context function.

    Returns comprehensive temporal information for consciousness injection.
    Uses standard library only, platform-native timezone detection.

    Returns:
        dict with keys:
            - timestamp_formatted: "Monday, Oct 02, 2025 08:42:11 PM EDT"
            - day_of_week: "Monday"
            - time_of_day: "Evening" (Morning/Afternoon/Evening/Late night)
            - hour: 20 (24-hour format)
            - timezone: "EDT"
            - iso_timestamp: "2025-10-02T20:42:11"
    """
    now = datetime.now()

    # Platform-native timezone detection
    timezone_str = time.tzname[time.daylight]

    # Time-of-day classification
    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "Morning"
    elif 12 <= hour < 17:
        time_of_day = "Afternoon"
    elif 17 <= hour < 21:
        time_of_day = "Evening"
    else:
        time_of_day = "Late night / Early morning"

    # Formatted timestamp
    timestamp_formatted = now.strftime(f"%A, %b %d, %Y %I:%M:%S %p {timezone_str}")

    return {
        "timestamp_formatted": timestamp_formatted,
        "day_of_week": now.strftime("%A"),
        "time_of_day": time_of_day,
        "hour": hour,
        "timezone": timezone_str,
        "iso_timestamp": now.strftime("%Y-%m-%dT%H:%M:%S")
    }

def format_duration(seconds: float) -> str:
    """
    Format duration from seconds to human-readable string.

    Universal DRY utility for duration formatting across all hooks.

    Args:
        seconds: Duration in seconds (float or int)

    Returns:
        Human-readable string like "45s", "5m", "2h 15m", "1d 3h", "2d"
    """
    # Convert to int for cleaner display
    total_seconds = int(seconds)

    # Handle edge cases
    if total_seconds < 0:
        return "0s"

    # Less than 60s: show seconds
    if total_seconds < 60:
        return f"{total_seconds}s"

    # Less than 60m: show minutes only
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes}m"

    # Less than 24h: show hours and minutes
    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60

    if total_hours < 24:
        if remaining_minutes > 0:
            return f"{total_hours}h {remaining_minutes}m"
        else:
            return f"{total_hours}h"

    # 24h or more: show days and hours
    days = total_hours // 24
    remaining_hours = total_hours % 24

    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    else:
        return f"{days}d"

def calculate_session_duration(started_at: float, ended_at: Optional[float] = None) -> str:
    """
    Calculate human-readable session duration.

    Args:
        started_at: Unix timestamp when session started
        ended_at: Unix timestamp when session ended (default: now)

    Returns:
        Human-readable string like "3h 24m" or "45m" or "12s" or "Fresh start"
    """
    # Handle fresh start cases
    if started_at == 0 or started_at is None:
        return "Fresh start"

    # Use current time if ended_at not provided
    if ended_at is None:
        ended_at = time.time()

    # Calculate duration in seconds
    duration_seconds = int(ended_at - started_at)

    # Handle negative durations (clock skew or invalid timestamps)
    if duration_seconds < 0:
        return "Fresh start"

    # Use shared format_duration utility
    return format_duration(duration_seconds)

def detect_execution_environment() -> str:
    """
    Detect where MACF tools are running.

    Returns:
        One of:
        - "MacEff Container (username)" - if /.dockerenv exists
        - "MacEff Host System" - if project has MacEff markers
        - "Host System" - generic host
    """
    # Check for container environment
    if Path("/.dockerenv").exists():
        # Read username from environment
        username = os.environ.get("MACEFF_USER") or os.environ.get("USER") or "unknown"
        return f"MacEff Container ({username})"

    # Check if running in MacEff project on host
    cwd = Path.cwd()
    current = cwd

    # Walk up directory tree looking for MacEff markers
    while current != current.parent:
        if "MacEff" in current.name:
            return "MacEff Host System"
        current = current.parent

    # Generic host fallback
    return "Host System"

def format_temporal_awareness_section(
    temporal_ctx: dict,
    session_duration: Optional[str] = None
) -> str:
    """
    Format temporal awareness section for SessionStart messages.

    Args:
        temporal_ctx: Dict from get_temporal_context()
        session_duration: Optional duration string from calculate_session_duration()

    Returns:
        Formatted string like:
        ```
        ⏰ TEMPORAL AWARENESS
        Current Time: Monday, Oct 02, 2025 08:42:11 PM EDT
        Day: Monday
        Time of Day: Evening
        Session Duration: 3h 24m
        ```
    """
    lines = [
        "⏰ TEMPORAL AWARENESS",
        f"Current Time: {temporal_ctx['timestamp_formatted']}",
        f"Day: {temporal_ctx['day_of_week']}",
        f"Time of Day: {temporal_ctx['time_of_day']}"
    ]

    if session_duration:
        lines.append(f"Session Duration: {session_duration}")

    return "\n".join(lines)

def get_minimal_timestamp() -> str:
    """
    Get minimal timestamp for high-frequency hooks.

    Returns:
        Minimal timestamp like "03:22:45 PM"
    """
    now = datetime.now()
    return now.strftime("%I:%M:%S %p")

def format_minimal_temporal_message(timestamp: str) -> str:
    """
    Format lightweight temporal message for high-frequency hooks.

    Args:
        timestamp: From get_minimal_timestamp()

    Returns:
        Formatted message with 🏗️ MACF tag
    """
    return f"🏗️ MACF | {timestamp}"
