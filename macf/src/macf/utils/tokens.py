"""
Tokens utilities.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from .paths import find_project_root, get_session_dir, get_session_transcript_path
from .session import get_current_session_id
from .json_io import read_json, write_json_safely
from .claude_settings import get_autocompact_setting

CC2_TOTAL_CONTEXT = 200000


def get_usable_context() -> int:
    """
    Calculate usable context based on autocompact setting.

    Returns:
        Usable context in tokens:
        - 155k (200k - 45k buffer) if autocompact enabled
        - 200k (full) if autocompact disabled
    """
    autocompact_enabled = get_autocompact_setting()
    buffer = 45000 if autocompact_enabled else 0
    return CC2_TOTAL_CONTEXT - buffer

def get_token_info(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Get current token usage information from session JSONL or hooks state.

    Uses a smart caching strategy for performance:
    1. Check sidecar cache first (ultra-fast)
    2. Quick scan last 200KB of JSONL
    3. Full scan only if needed

    Args:
        session_id: Optional session ID to get tokens for specific session.
                   If not provided, uses current session.

    Returns:
        Dictionary with token counts and CLUAC level (matches /context display)
    """
    # Use CC2_TOTAL_CONTEXT to match /context display exactly
    # /context shows: actual_usage + autocompact_buffer = total displayed
    max_tokens = CC2_TOTAL_CONTEXT

    # If session_id provided, try to get tokens from JSONL file
    if session_id or (session_id := get_current_session_id()) != "unknown":
        # Smart cache invalidation strategy:
        # 1. Check cache for historical reference
        # 2. ALWAYS do a quick tail scan to get current value
        # 3. If current < cached, update cache (detects compaction)

        # Read cache from unified sidecar location
        sidecar_dir = get_session_dir(session_id, agent_id=None, subdir=None, create=False)
        cache_data = None
        cached_max = 0

        if sidecar_dir:
            cache_path = sidecar_dir / "token_cache.json"
            try:
                cache_data = read_json(cache_path)
                if cache_data and cache_data.get("session_id") == session_id:
                    cached_max = cache_data.get("max_tokens_used", 0)
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                pass  # Cache miss is non-critical, continue with cached_max = 0

        jsonl_path = get_session_transcript_path(session_id)

        if jsonl_path and Path(jsonl_path).exists():
            try:
                # Smart cache invalidation with real-time accuracy
                # ALWAYS scan tail to get CURRENT token value, not historical maximum
                current_tokens = 0
                last_timestamp = None

                with open(jsonl_path, "rb") as f:
                    file_size = f.seek(0, os.SEEK_END)

                    # Quick scan: Read last 200KB for most recent token value
                    # We scan MORE data (200KB vs 100KB) to ensure we find the
                    # latest assistant message
                    scan_size = min(200 * 1024, file_size)
                    if scan_size > 0:
                        f.seek(-scan_size, os.SEEK_END)
                        content = f.read().decode("utf-8", errors="ignore")

                        # Find compact_boundary marker (compaction detection)
                        # After compaction, pre-compaction messages have stale token counts
                        lines = content.split("\n")
                        last_boundary_idx = -1
                        for i, line in enumerate(lines):
                            if not line.strip():
                                continue
                            # Detect compact_boundary or summary markers
                            if '"compact_boundary"' in line or '"type":"summary"' in line:
                                last_boundary_idx = i

                        # Only scan lines AFTER the boundary (if found)
                        search_lines = lines[last_boundary_idx + 1:] if last_boundary_idx >= 0 else lines

                        # Find the LAST assistant message with token data (most recent)
                        assistant_messages = []
                        for line in search_lines:
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                if data.get("type") == "assistant":
                                    message = data.get("message", {})
                                    usage = message.get("usage", {})
                                    # Match TM! algorithm: sum ALL token types for total context
                                    total_tokens = 0
                                    total_tokens += usage.get(
                                        "cache_read_input_tokens", 0
                                    )
                                    total_tokens += usage.get(
                                        "cache_creation_input_tokens", 0
                                    )
                                    total_tokens += usage.get("input_tokens", 0)
                                    total_tokens += usage.get("output_tokens", 0)
                                    if total_tokens > 0:
                                        assistant_messages.append(
                                            {
                                                "tokens": total_tokens,
                                                "timestamp": data.get(
                                                    "timestamp", "unknown"
                                                ),
                                            }
                                        )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue

                        # Use the LAST (most recent) assistant message's token count
                        if assistant_messages:
                            current_tokens = assistant_messages[-1]["tokens"]
                            last_timestamp = assistant_messages[-1]["timestamp"]
                        elif last_boundary_idx >= 0:
                            # Compaction detected but no post-boundary messages yet
                            # Return conservative estimate (~30% usage)
                            return {
                                "tokens_used": 60000,
                                "tokens_remaining": max_tokens - 60000,
                                "percentage_used": 30.0,
                                "percentage_remaining": 70.0,
                                "cluac_level": 70,
                                "last_updated": "post_compaction",
                                "source": "post_compaction_estimate",
                            }

                    # If tail scan didn't find any data, do a full scan
                    if current_tokens == 0:
                        f.seek(0)
                        last_assistant_tokens = 0
                        for line in f:
                            try:
                                line = line.decode("utf-8", errors="ignore").strip()
                                if not line:
                                    continue
                                data = json.loads(line)
                                if data.get("type") == "assistant":
                                    message = data.get("message", {})
                                    usage = message.get("usage", {})
                                    # Match TM! algorithm: sum ALL token types for total context
                                    total_tokens = 0
                                    total_tokens += usage.get(
                                        "cache_read_input_tokens", 0
                                    )
                                    total_tokens += usage.get(
                                        "cache_creation_input_tokens", 0
                                    )
                                    total_tokens += usage.get("input_tokens", 0)
                                    total_tokens += usage.get("output_tokens", 0)
                                    if total_tokens > 0:
                                        # Always use the LATEST value, not the maximum
                                        last_assistant_tokens = total_tokens
                                        last_timestamp = data.get(
                                            "timestamp", "unknown"
                                        )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
                        current_tokens = last_assistant_tokens

                if current_tokens > 0:
                    # Add autocompact buffer dynamically based on settings
                    # Buffer is 45k if autocompact enabled, 0 if disabled
                    autocompact_enabled = get_autocompact_setting()
                    buffer = 45000 if autocompact_enabled else 0
                    tokens_used_with_buffer = current_tokens + buffer
                    tokens_remaining = max_tokens - tokens_used_with_buffer

                    # CLUAC is percentage REMAINING (not used)
                    # This matches the original CLUAC protocol where higher numbers = more danger
                    percentage_remaining = (
                        (tokens_remaining / max_tokens) * 100 if max_tokens > 0 else 0
                    )
                    # CLUAC level = percentage remaining (rounded)
                    # CLUAC100 = 100% remaining (0% used)
                    # CLUAC1 = 1% remaining (99% used)
                    cluac_level = round(percentage_remaining)

                    # Smart cache update: detect compaction events
                    # If current is significantly less than cached (>1k difference), update cache
                    # This automatically detects compaction resets
                    # FIXED: Lowered threshold from 10,000 to 1,000 for better cache accuracy
                    if sidecar_dir and (cached_max == 0 or abs(current_tokens - cached_max) > 1000):
                        cache_path = sidecar_dir / "token_cache.json"
                        write_json_safely(
                            cache_path,
                            {
                                "session_id": session_id,
                                "max_tokens_used": current_tokens,
                                "last_updated": last_timestamp,
                            },
                        )

                    return {
                        "tokens_used": tokens_used_with_buffer,
                        "tokens_remaining": tokens_remaining,
                        "percentage_used": (tokens_used_with_buffer / max_tokens) * 100,
                        "percentage_remaining": percentage_remaining,
                        "cluac_level": cluac_level,
                        "last_updated": last_timestamp,
                        "source": "jsonl",
                    }
            except Exception as e:
                print(f"⚠️ MACF: Token cache JSONL read failed (fallback: hooks_state): {e}", file=sys.stderr)

    # Fallback to hooks_state.json (original implementation)
    project_root = find_project_root()
    hooks_state_path = project_root / ".claude" / "hooks" / "hooks_state.json"

    if not hooks_state_path.exists():
        return {
            "tokens_used": 0,
            "tokens_remaining": max_tokens,
            "percentage_used": 0.0,
            "percentage_remaining": 100.0,
            "cluac_level": 0,
            "source": "default",
        }

    try:
        with open(hooks_state_path, "r") as f:
            state = json.load(f)

        token_data = state.get("token_tracking", {})
        tokens_used = token_data.get("total_tokens", 0)
        tokens_remaining = max_tokens - tokens_used
        percentage_used = (tokens_used / max_tokens) * 100 if max_tokens > 0 else 0
        percentage_remaining = 100 - percentage_used

        # Calculate CLUAC level (based on percentage remaining)
        # CLUAC level = percentage remaining (rounded)
        # CLUAC100 = 100% remaining (0% used)
        # CLUAC1 = 1% remaining (99% used)
        cluac_level = round(percentage_remaining)

        return {
            "tokens_used": tokens_used,
            "tokens_remaining": tokens_remaining,
            "percentage_used": percentage_used,
            "percentage_remaining": percentage_remaining,
            "cluac_level": cluac_level,
            "last_updated": token_data.get("last_updated", "unknown"),
            "source": "hooks_state",
        }
    except (json.JSONDecodeError, IOError, KeyError):
        return {
            "tokens_used": 0,
            "tokens_remaining": max_tokens,
            "percentage_used": 0.0,
            "percentage_remaining": 100.0,
            "cluac_level": 0,
            "source": "default",
        }

def format_token_context_minimal(token_info: Dict[str, Any]) -> str:
    """
    Format minimal CLUAC indicator for high-frequency hooks.

    Args:
        token_info: Dict from get_token_info()

    Returns:
        One-line string like "CLUAC 42 (58% used)"
    """
    cluac = token_info['cluac_level']
    percentage_used = token_info['percentage_used']
    return f"CLUAC {cluac} ({percentage_used:.0f}% used)"

def format_token_context_full(token_info: Dict[str, Any]) -> str:
    """
    Format full token context section for low-frequency hooks.

    Args:
        token_info: Dict from get_token_info()

    Returns:
        Multi-line formatted section with emoji header
    """
    return f"""📊 TOKEN/CONTEXT AWARENESS
Tokens Used: {token_info['tokens_used']:,} / {CC2_TOTAL_CONTEXT:,}
CLUAC Level: {token_info['cluac_level']} ({token_info['percentage_used']:.1f}% used)
Remaining: {token_info['tokens_remaining']:,} tokens"""

def get_boundary_guidance(cluac: int, auto_mode: bool) -> Optional[str]:
    """
    Get mode-aware boundary guidance based on CLUAC level.

    CRITICAL: Returns different messages for MANUAL vs AUTO mode.
    - MANUAL: User present → STOP work, await guidance
    - AUTO: User absent → Assess completion, prepare artifacts

    Args:
        cluac: CLUAC level (0-100, percentage remaining)
        auto_mode: True if AUTO_MODE enabled, False for MANUAL

    Returns:
        Warning string or None if CLUAC > 10
    """
    # No warnings above CLUAC 10
    if cluac > 10:
        return None

    # MANUAL MODE: User controls closure priorities
    if not auto_mode:
        if cluac <= 2:
            return "🚨 EMERGENCY (MANUAL): STOP immediately - report status, await user priorities"
        elif cluac <= 5:
            return "⚠️ PREPARATION THRESHOLD (MANUAL): Report status, STOP work, await user guidance"
        elif cluac <= 10:
            return "🟡 BOUNDARY APPROACHING (MANUAL): Strategic preparation recommended"

    # AUTO MODE: Autonomous preparation
    else:
        if cluac <= 2:
            return "⚠️ EMERGENCY (AUTO): Write critical artifacts NOW - CCP minimum, JOTEWR if possible"
        elif cluac <= 5:
            return "🟡 PREPARATION MODE (AUTO): Assess completion state, prepare CCP if incomplete"
        elif cluac <= 10:
            return "🟠 BOUNDARY APPROACHING (AUTO): Strategic choices matter - measure workflow costs"

    return None
