"""
handle_session_start - SessionStart hook runner.

Compaction detection and consciousness recovery with mode-aware branching.
"""
import json
from pathlib import Path
from typing import Dict, Any

from ..utils import (
    get_current_session_id,
    SessionOperationalState,
    get_latest_consciousness_artifacts,
    detect_auto_mode,
    get_temporal_context,
    detect_execution_environment,
    get_current_cycle_project
)
from .compaction import detect_compaction
from .recovery import format_consciousness_recovery_message
from .logging import log_hook_event


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run SessionStart hook logic.

    Detects compaction events and provides consciousness recovery with:
    - Temporal awareness
    - Mode-aware branching (AUTO vs MANUAL)
    - Artifact discovery
    - Session state restoration

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict ready for JSON output with compaction recovery if detected
    """
    session_id = None

    try:
        # Parse input (may be empty for SessionStart)
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session ID
        session_id = get_current_session_id()

        # Log hook start
        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_START",
            "session_id": session_id
        })

        # Find current session JSONL for compaction detection
        claude_dir = Path.home() / ".claude" / "projects"
        compaction_detected = False

        if claude_dir.exists():
            all_jsonl_files = []
            for project_dir in claude_dir.iterdir():
                if project_dir.is_dir():
                    all_jsonl_files.extend(project_dir.glob("*.jsonl"))

            if all_jsonl_files:
                latest_file = max(all_jsonl_files, key=lambda p: p.stat().st_mtime)
                compaction_detected = detect_compaction(latest_file)

                # Log detection result
                log_hook_event({
                    "hook_name": "session_start",
                    "event_type": "COMPACTION_CHECK",
                    "session_id": session_id,
                    "compaction_detected": compaction_detected,
                    "detection_method": "compact_boundary",
                    "transcript": str(latest_file)
                })

        if compaction_detected:
            # Load session state
            state = SessionOperationalState.load(session_id)

            # Increment compaction count
            state.compaction_count += 1
            state.save()

            # Detect AUTO_MODE
            auto_mode, source, confidence = detect_auto_mode(session_id)
            state.auto_mode = auto_mode
            state.auto_mode_source = source
            state.auto_mode_confidence = confidence
            state.save()

            # Get consciousness artifacts
            artifacts = get_latest_consciousness_artifacts()

            # Get temporal context
            temporal_ctx = get_temporal_context()
            environment = detect_execution_environment()

            # Get cycle stats
            cycle_number = get_current_cycle_project()
            cycle_stats = {
                'cycle_number': cycle_number
            }

            # Format comprehensive recovery message
            recovery_msg = format_consciousness_recovery_message(
                session_id=session_id,
                state=state,
                artifacts=artifacts,
                temporal_ctx=temporal_ctx,
                environment=environment,
                cycle_stats=cycle_stats
            )

            # Log recovery triggered
            log_hook_event({
                "hook_name": "session_start",
                "event_type": "RECOVERY_TRIGGERED",
                "session_id": session_id,
                "auto_mode": auto_mode,
                "compaction_count": state.compaction_count
            })

            # Return recovery message with hookSpecificOutput
            return {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"<system-reminder>\n{recovery_msg}\n</system-reminder>"
                }
            }

        # No compaction detected - return minimal continue
        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_COMPLETE",
            "session_id": session_id,
            "compaction_detected": False
        })

        return {"continue": True}

    except Exception as e:
        # Log error and fail gracefully
        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_ERROR",
            "session_id": session_id if session_id else "unknown",
            "error": str(e),
            "error_type": type(e).__name__
        })

        return {"continue": True}
