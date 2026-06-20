"""
Tokens utilities.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from .paths import find_project_root, get_session_dir, get_session_transcript_path
from .session import get_current_session_id
from .json_io import read_json, write_json_safely
from .claude_settings import get_autocompact_setting


def _compaction_lower_bound_iso(session_id: str) -> str:
    """Return an ISO-8601 lower bound on post-compaction assistant timestamps.

    Queries the event log for the most recent ``compaction_detected`` event
    matching this session and converts its epoch timestamp to a string in
    Claude Code's transcript format (``YYYY-MM-DDTHH:MM:SS.mmmZ``) so it
    sorts lexicographically against assistant-message ``timestamp`` strings
    from the JSONL transcript. Returns ``""`` when there is no session or
    no recorded compaction — both are legitimate empty-state cases (every
    real ISO timestamp sorts above the empty string, so an empty bound
    accepts all messages, matching the pre-#111 behavior).

    Closes cversek/MacEff#111: the bound tells ``get_token_info`` that any
    assistant message older than the recorded compaction is either a
    pre-compaction turn or a preserved-segment replay; either way, it must
    be filtered out of the tail-scan / full-scan selectors. A wrong-type
    ``timestamp`` on the event record is a contract violation by
    ``append_event`` and will raise naturally — not silently swallowed.

    Closes cversek/MacEff#118: takes the LATER of two compaction anchors.
    ``compaction_detected`` is written by SessionStart ~3-4s AFTER the
    boundary; ``pre_compact`` is written by the PreCompact hook BEFORE
    compaction. During the read-before-write transient (compaction done but
    ``compaction_detected`` not yet emitted), only ``pre_compact`` is present —
    using its timestamp as the lower bound rejects the pre-compaction tail and
    preserved-segment replays that would otherwise leak a stale high token
    count into the CL meter for a few seconds.
    """
    if not session_id:
        return ""
    from ..event_queries import (
        get_latest_compaction_event,
        get_latest_precompact_event,
    )
    epochs = [
        ev["timestamp"]
        for ev in (
            get_latest_compaction_event(session_id),
            get_latest_precompact_event(session_id),
        )
        if ev is not None
    ]
    if not epochs:
        return ""
    epoch = max(epochs)
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{int((epoch - int(epoch)) * 1000):03d}Z"
    )

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

    Detection priority (unified config layer per cversek/MacEff#96 Phase 2-4):
    1. ``MACF_CONTEXT_WINDOW`` env var (explicit override)
    2. ``.maceff/config.json`` ``context.window`` (per-project default)
    3. Default 200k (fallback)

    Emits one-time warning if model is claude-opus-4-6 and the resolution
    fell through to the default.

    Returns:
        Total context window in tokens
    """
    global _1M_WARNING_SHOWN
    from macf.config import resolve_setting
    value, source = resolve_setting(
        "MACF_CONTEXT_WINDOW",
        "context.window",
        _DEFAULT_CONTEXT,
        coerce=int,
    )
    if source != "default":
        return value

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

        # Compaction-anchored lower bound on valid assistant-message timestamps.
        # Empty string when there is no session or no compaction yet — every
        # real ISO timestamp sorts above "", so the bound is a no-op then.
        # Otherwise, pre-compaction turns and preserved-segment replays (which
        # carry their ORIGINAL older timestamps) get filtered out of both
        # scan paths below. Closes cversek/MacEff#111 and subsumes #110.
        min_ts_iso = _compaction_lower_bound_iso(session_id)

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

                        # Find the LAST assistant message with token data (most recent).
                        # `min_ts_iso` filter (when non-empty) rejects pre-compaction
                        # turns and preserved-segment replays whose timestamps are
                        # older than the recorded compaction event — closes #111
                        # and also subsumes the #110 fix because replays carry
                        # original older timestamps.
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
                                        ts = data.get("timestamp", "unknown")
                                        # Drop pre-compaction messages when an
                                        # anchor exists. Empty `min_ts_iso`
                                        # (no compaction yet) is a no-op since
                                        # every real ISO string >= "".
                                        if ts >= min_ts_iso:
                                            assistant_messages.append(
                                                {
                                                    "tokens": total_tokens,
                                                    "timestamp": ts,
                                                }
                                            )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue

                        # Pick the assistant message with the latest TIMESTAMP, not
                        # the last in FILE ORDER. CC's compaction emits a
                        # preservedSegment block in the compact_boundary, and the
                        # preserved messages are RE-EMITTED into the JSONL with
                        # their ORIGINAL (older) timestamps and ORIGINAL usage
                        # blocks intact. The replays can sit near EOF in long
                        # sessions; trusting file order picks up a phantom pre-
                        # compaction tally as "current". Timestamp-priority skips
                        # them automatically because the truly-current in-cycle
                        # turn has the latest timestamp. The `>=` comparator means
                        # later-in-file wins on ties (preserves legacy behavior
                        # for content with missing/equal timestamps; only strictly
                        # OLDER timestamps lose). Closes cversek/MacEff#110.
                        if assistant_messages:
                            latest = assistant_messages[0]
                            latest_ts_so_far = latest.get("timestamp", "")
                            for m in assistant_messages[1:]:
                                ts = m.get("timestamp", "")
                                if ts >= latest_ts_so_far:
                                    latest = m
                                    latest_ts_so_far = ts
                            current_tokens = latest["tokens"]
                            last_timestamp = latest["timestamp"]
                        elif last_boundary_idx >= 0:
                            # Compaction detected but no post-boundary in-cycle
                            # message yet. Return a conservative estimate scaled
                            # to the ACTUAL context window: the fixed 60000 was
                            # 200K-calibrated, so its hardcoded 30%/CL70 were
                            # wrong on 1M (60000 is ~6% there). Derive the bands
                            # from max_tokens so the CL meter is sane on any
                            # window. (cversek/MacEff#118)
                            est_tokens = min(60000, max_tokens)
                            pct_used = round(est_tokens / max_tokens * 100, 1)
                            return {
                                "tokens_used": est_tokens,
                                "tokens_remaining": max_tokens - est_tokens,
                                "percentage_used": pct_used,
                                "percentage_remaining": round(100 - pct_used, 1),
                                "cl_level": round(100 - pct_used),
                                "last_updated": "post_compaction",
                                "source": "post_compaction_estimate",
                            }

                    # If tail scan didn't find any data, do a full scan.
                    # Same timestamp-priority discipline as the tail scan (see
                    # comment above): pick the assistant message with the
                    # latest timestamp, not the last seen in file order. The
                    # full-scan loop keeps O(1) memory by tracking the
                    # running latest-timestamp winner rather than materializing
                    # every assistant message. Closes cversek/MacEff#110 in
                    # the fallback path too.
                    if current_tokens == 0:
                        f.seek(0)
                        latest_tokens = 0
                        # Initialize the running-latest timestamp to the
                        # compaction lower bound (if any). The full-scan
                        # `>=` test then naturally rejects any message older
                        # than the bound — same #111 + #110 filter as the
                        # tail-scan path.
                        latest_ts = min_ts_iso
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
                                        ts = data.get("timestamp", "")
                                        # `>=` (not strict `>`) so later-in-file
                                        # wins on missing/equal timestamps —
                                        # preserves legacy behavior for content
                                        # without timestamps. Only strictly
                                        # OLDER timestamps lose, which is
                                        # exactly the preserved-segment-replay
                                        # case we need to skip.
                                        if ts >= latest_ts:
                                            latest_tokens = total_tokens
                                            latest_ts = ts
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
                        current_tokens = latest_tokens
                        if latest_ts:
                            last_timestamp = latest_ts

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

    # AUTO MODE: Curate perishable wisdom, then continue sprint/playtime work.
    # CL on 1M context is more elastic than scarcity instinct believes —
    # CL10 ≈ 100K remaining, CL5 ≈ 50K, CL2 ≈ 20K. Wind-down framing is
    # an inherited 200K-era reflex; curate-then-continue fits the substrate.
    else:
        if cluac <= 2:
            return "⚠️ DEEP CURATION (AUTO): Finalize active curation step (learning/idea/web), then resume sprint/playtime — substrate is elastic"
        elif cluac <= 5:
            return "🟡 CURATION WINDOW (AUTO): Curate perishable wisdom (learnings, ideas, knowledge web), then continue sprint/playtime work"
        elif cluac <= 10:
            return "🟠 CURATION REMINDER (AUTO): Capture pending learnings + ideas; continue sprint/playtime work in parallel"

    return None
