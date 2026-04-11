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

_DEFAULT_CONTEXT = 200_000

# Known model context windows
_MODEL_CONTEXT_MAP = {
    "claude-opus-4-6[1m]": 1_000_000,
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}


_1M_WARNING_SHOWN = False


def get_total_context() -> int:
    """
    Get total context window size.

    Detection priority:
    1. MACF_CONTEXT_WINDOW env var (explicit override)
    2. Default 200k

    Emits one-time warning if model is claude-opus-4-6 and env var not set.

    Returns:
        Total context window in tokens
    """
    global _1M_WARNING_SHOWN
    env_val = os.environ.get("MACF_CONTEXT_WINDOW")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass

    if not _1M_WARNING_SHOWN:
        _1M_WARNING_SHOWN = True
        try:
            from .environment import detect_model
            model = detect_model()
            if model == "claude-opus-4-6":
                print(
                    "⚠️ MACF: Model 'claude-opus-4-6' detected. 1M context may be available.\n"
                    "   Check with /context. If 1M, set: export MACF_CONTEXT_WINDOW=1000000",
                    file=sys.stderr,
                )
        except (ImportError, OSError) as e:
            print(f"⚠️ MACF: model detection failed during context window check: {e}", file=sys.stderr)

    return _DEFAULT_CONTEXT


# Backward compatibility alias
CC2_TOTAL_CONTEXT = _DEFAULT_CONTEXT


def get_usable_context() -> int:
    """
    Calculate usable context based on autocompact setting.

    Returns:
        Usable context in tokens (total minus buffer if autocompact enabled)
    """
    total = get_total_context()
    autocompact_enabled = get_autocompact_setting()
    buffer = 45000 if autocompact_enabled else 0
    return total - buffer

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
        Dictionary with token counts and CL level (matches /context display)
    """
    # Use detected context window to match /context display
    max_tokens = get_total_context()

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
                                "cl_level": 70,
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
                    # Calculate raw CL from actual token usage
                    tokens_remaining = max_tokens - current_tokens
                    percentage_remaining = (
                        (tokens_remaining / max_tokens) * 100 if max_tokens > 0 else 0
                    )
                    # CL level = percentage remaining (rounded)
                    # CL100 = 100% remaining (0% used)
                    # CL1 = 1% remaining (99% used)
                    cl_level = round(percentage_remaining)

                    # AUTO_MODE penalty: subtract CL points for autocompact buffer.
                    # CC reserves ~33k tokens as autocompact buffer regardless of window size.
                    # The CL penalty is the buffer as a percentage of the window.
                    # On 200K: 33k/200k = 16.5% → CL penalty ~17
                    # On 1M:   33k/1M   = 3.3%  → CL penalty ~3
                    try:
                        from .cycles import detect_auto_mode
                        auto_mode, _ = detect_auto_mode(session_id)
                        if auto_mode:
                            autocompact_buffer = 33000  # CC's fixed autocompact reserve
                            buffer_pct = round((autocompact_buffer / max_tokens) * 100)
                            cl_level = max(0, cl_level - buffer_pct)
                    except (ImportError, OSError, KeyError) as e:
                        print(f"⚠️ MACF: AUTO_MODE detection failed (using raw CL): {e}", file=sys.stderr)

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
                        "tokens_used": current_tokens,
                        "tokens_remaining": tokens_remaining,
                        "percentage_used": (current_tokens / max_tokens) * 100,
                        "percentage_remaining": percentage_remaining,
                        "cl_level": cl_level,
                        "last_updated": last_timestamp,
                        "source": "jsonl",
                    }
            except Exception as e:
                print(f"⚠️ MACF: Token cache JSONL read failed: {e}", file=sys.stderr)

    # NOTE: hooks_state.json fallback REMOVED - event-first architecture
    # JSONL transcript parsing is the sole source of token data
    # Return default values if JSONL parsing fails
    return {
        "tokens_used": 0,
        "tokens_remaining": max_tokens,
        "percentage_used": 0.0,
        "percentage_remaining": 100.0,
        "cl_level": 100,
        "source": "default",
    }

def get_cluac_weather(cluac: int) -> str:
    """
    Get affirmative weather emoji + phrase based on CL level.

    Reframes scarcity instinct as state awareness - "I am at X" not "you should Y".
    Counters CC's hidden nags with visible affirmation.

    Args:
        cluac: CL level (0-100, percentage remaining)

    Returns:
        Emoji + short phrase (e.g., "🌅 Fresh context")
    """
    if cluac >= 70:
        return "🌅 Fresh context"
    elif cluac >= 40:
        return "🌤️ Abundance mode"
    elif cluac >= 15:
        return "🌆 Well-invested"
    elif cluac >= 5:
        return "🌙 Navigate to shore"
    else:
        return "🪂 Ready to jump"


def format_token_context_minimal(token_info: Dict[str, Any]) -> str:
    """
    Format minimal CL indicator for high-frequency hooks.

    Args:
        token_info: Dict from get_token_info()

    Returns:
        One-line string like "🌅 Fresh context | CL 42 (58% used)"
    """
    context_left_pct = token_info['cl_level']
    return f"CL{context_left_pct}"

def format_token_context_full(token_info: Dict[str, Any]) -> str:
    """
    Format full token context section for low-frequency hooks.

    Args:
        token_info: Dict from get_token_info()

    Returns:
        Multi-line formatted section with emoji header and weather framing
    """
    cluac = token_info['cl_level']
    weather = get_cluac_weather(cluac)
    return f"""📊 TOKEN/CONTEXT AWARENESS
{weather}
Tokens Used: {token_info['tokens_used']:,} / {get_total_context():,}
CL Level: {cluac} ({token_info['percentage_used']:.1f}% used)
Remaining: {token_info['tokens_remaining']:,} tokens"""

def get_boundary_guidance(cluac: int, auto_mode: bool) -> Optional[str]:
    """
    Get mode-aware boundary guidance based on CL level.

    CRITICAL: Returns different messages for MANUAL vs AUTO mode.
    - MANUAL: User present → STOP work, await guidance
    - AUTO: User absent → Assess completion, prepare artifacts

    Args:
        cluac: CL level (0-100, percentage remaining)
        auto_mode: True if AUTO_MODE enabled, False for MANUAL

    Returns:
        Warning string or None if CL > 10
    """
    # No warnings above CL 10
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
