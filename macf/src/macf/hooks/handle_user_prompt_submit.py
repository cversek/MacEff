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

# EXPERIMENT: Policy injection script path (Cycle 338, Phase 6 update)
# Use MACF_AGENT_ROOT if set, otherwise fallback to ClaudeTheBuilder location
_agent_root = os.environ.get("MACF_AGENT_ROOT", "/Users/cversek/gitwork/claude-the-builder/ClaudeTheBuilder")
POLICY_RECOMMEND_SCRIPT = Path(_agent_root) / "agent/public/experiments/2026-01-15_210000_002_Policy_Injection/artifacts/policy-recommend.py"


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

    EXPERIMENT (Cycle 338): Testing whether policy injection creates
    "ambient procedural awareness" - knowing how to act without looking up.

    Two-tier system:
    - High relevance (≥0.7): Inject CEP Navigation Guide
    - Medium relevance (0.5-0.7): Suggest discovery commands

    Returns empty string on any failure (graceful degradation).
    """
    if not POLICY_RECOMMEND_SCRIPT.exists():
        return ""

    if len(prompt) < 10:  # Skip very short prompts
        return ""

    try:
        result = subprocess.run(
            [sys.executable, str(POLICY_RECOMMEND_SCRIPT)],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=5.0  # 5s timeout (first call loads embedding model ~3s, subsequent <100ms)
        )

        if result.returncode == 0 and result.stdout.strip():
            output = json.loads(result.stdout)
            return output.get("additionalContext", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass  # Fail silently - don't block session

    return ""


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

        # Start Development Drive tracking with current UUID
        # Note: start_dev_drv() emits dev_drv_started event internally
        start_dev_drv(session_id, prompt_uuid=current_prompt_uuid)

        # Get breadcrumb
        breadcrumb = get_breadcrumb()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

        # Get token context
        token_info = get_token_info(session_id)
        auto_mode, _, _ = detect_auto_mode(session_id)

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
        prompt = hook_input.get('prompt', '') if hook_input else ''
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

