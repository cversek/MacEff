#!/usr/bin/env python3
"""
handle_user_prompt_submit - UserPromptSubmit hook runner.

DEV_DRV start tracking + full temporal + token/CLUAC awareness injection.
EXPERIMENT: Claude-mem associative memory injection (Cycle 337)
"""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, Any

from macf.utils import (
    get_temporal_context,
    format_macf_footer,
    get_rich_environment_string,
    get_current_session_id,
    start_dev_drv,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)
from macf.hooks.hook_logging import log_hook_event

# EXPERIMENT: Memory injection script path (Cycle 337)
MEMORY_RECALL_SCRIPT = Path(__file__).parent.parent.parent / "agent/public/experiments/2026-01-15_140000_001_Claude-Mem_Associative_Injection/artifacts/memory-recall.py"

# NOTE: recommend module imported lazily inside get_policy_injection() (heavy deps ~3s)


def get_memory_injection(prompt: str) -> str:
    """
    Query claude-mem for associative memories relevant to the prompt.

    EXPERIMENT (Cycle 337): Testing whether injected memories feel more
    like "remembering" than explicit tool calls.

    Returns empty string on any failure (graceful degradation).
    """
    if not MEMORY_RECALL_SCRIPT.exists():
        return ""

    if len(prompt) < 10:  # Skip very short prompts
        return ""

    try:
        result = subprocess.run(
            [sys.executable, str(MEMORY_RECALL_SCRIPT)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=0.2  # 200ms hard timeout
        )

        if result.returncode == 0 and result.stdout.strip():
            output = json.loads(result.stdout)
            return output.get("additionalContext", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass  # Fail silently - don't block session

    return ""


def get_policy_injection(prompt: str) -> str:
    """
    Query policy index for relevant policy recommendations.

    Fast path: Socket client to warm search service (45ms)
    Fallback: Direct import of recommend module (4000ms on first call)

    Logs warnings when fallback is used - not silent failures.
    Returns empty string on any failure (graceful degradation).
    """
    if len(prompt) < 10:  # Skip very short prompts
        return ""

    # Fast path: Try socket client first (stdlib only, no heavy imports)
    try:
        from macf.search_service.client import get_policy_injection as client_get_injection
        result = client_get_injection(prompt)
        if result:  # Service returned a result
            return result
        # Empty result means service unavailable - fall through with warning
    except ImportError as e:
        # Client module not available - log and fall through
        print(f"⚠️ MACF: search_service.client not available: {e}", file=sys.stderr)
    except Exception as e:
        # Unexpected error - log with traceback
        print(f"⚠️ MACF: search_service.client error: {e}", file=sys.stderr)
        log_hook_event({
            "hook_name": "user_prompt_submit",
            "event_type": "WARNING",
            "warning": "search_service_client_failed",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "fallback": "direct_recommend_import"
        })

    # Slow path fallback: Direct import (4s on first call)
    # Log that we're using fallback so user knows service isn't running
    print("⚠️ MACF: Search service unavailable, using slow fallback (4s)", file=sys.stderr)
    log_hook_event({
        "hook_name": "user_prompt_submit",
        "event_type": "WARNING",
        "warning": "search_service_fallback",
        "message": "Using direct recommend import (slow path ~4s)",
        "hint": "Start search service: macf_tools search-service start"
    })

    try:
        from macf.utils.recommend import get_recommendations
        formatted, _ = get_recommendations(prompt)
        return formatted
    except ImportError:
        return ""  # recommend module not available
    except Exception as e:
        # Log fallback error too
        log_hook_event({
            "hook_name": "user_prompt_submit",
            "event_type": "ERROR",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "context": "direct_recommend_fallback_failed"
        })
        return ""  # Fail gracefully - don't block session


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run UserPromptSubmit hook logic.

    Tracks DEV_DRV start and injects temporal + token/CLUAC awareness.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DEV_DRV started message + comprehensive awareness
    """
    try:
        # Parse stdin to get session_id and transcript_path from Claude Code
        try:
            hook_input = json.loads(stdin_json) if stdin_json else {}
            session_id = hook_input.get('session_id')
            transcript_path = hook_input.get('transcript_path')
        except (json.JSONDecodeError, AttributeError):
            session_id = None
            transcript_path = None

        # Fallback to filesystem discovery if stdin parsing failed
        if not session_id:
            session_id = get_current_session_id()

        # Get current message UUID from JSONL (message written before hook fires)
        from macf.utils.session import get_last_user_prompt_uuid
        current_prompt_uuid = get_last_user_prompt_uuid(session_id)

        # Extract prompt preview for forensic recovery (first 200 chars)
        prompt = hook_input.get('prompt', '') if hook_input else ''
        prompt_preview = prompt[:200] if prompt else None

        # Start Development Drive tracking with current UUID and prompt preview
        # Note: start_dev_drv() emits dev_drv_started event internally
        start_dev_drv(session_id, prompt_uuid=current_prompt_uuid, prompt_preview=prompt_preview)

        # Get breadcrumb
        breadcrumb = get_breadcrumb()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

        # Get token context
        token_info = get_token_info(session_id)
        auto_mode, _ = detect_auto_mode(session_id)

        # Format temporal section with breadcrumb
        temporal_section = f"""🏗️ MACF | DEV_DRV Started
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}"""

        # Format token section
        token_section = format_token_context_full(token_info)

        # Get boundary guidance (if CLUAC ≤ 10)
        boundary_guidance = get_boundary_guidance(token_info['cluac_level'], auto_mode)

        # EXPERIMENT: Get associative memory injection (Cycle 337)
        # DISABLED: Testing if this causes CLUAC 17 limit
        # Note: prompt already extracted above for prompt_preview
        memory_injection = ""  # get_memory_injection(prompt)

        # EXPERIMENT: Get policy recommendation injection (Cycle 338)
        policy_injection = get_policy_injection(prompt)

        # Format footer
        footer = format_macf_footer()

        # Combine sections into plain content (DRY - single source)
        sections = [
            temporal_section,
            token_section,
            boundary_guidance if boundary_guidance else "",
            memory_injection if memory_injection else "",  # EXPERIMENT: associative memories
            policy_injection if policy_injection else "",  # EXPERIMENT: policy recommendations
            footer
        ]
        plain_content = chr(10).join([s for s in sections if s])

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        return {
            "continue": True,
            "systemMessage": plain_content,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"<system-reminder>\n{plain_content}\n</system-reminder>"
            }
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "user_prompt_submit",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        error_msg = f"🏗️ MACF | ❌ UserPromptSubmit hook error: {e}"
        return {
            "continue": True,
            "systemMessage": error_msg,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"<system-reminder>\n{error_msg}\n</system-reminder>"
            }
        }



if __name__ == "__main__":
    import json
    import sys
    try:
        output = run(sys.stdin.read())
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

