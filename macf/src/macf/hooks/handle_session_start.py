#!/usr/bin/env python3
"""
handle_session_start - SessionStart hook runner.

Compaction detection and consciousness recovery with mode-aware branching.
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any

from macf.utils import (
    get_current_session_id,
    SessionOperationalState,
    get_latest_consciousness_artifacts,
    detect_auto_mode,
    get_temporal_context,
    get_rich_environment_string,
    format_duration,
    format_macf_footer,
    get_agent_cycle_number,
    increment_agent_cycle,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    get_breadcrumb,
    format_manifest_awareness
)
from macf.hooks.compaction import detect_compaction
from macf.hooks.recovery import (
    format_consciousness_recovery_message,
    format_session_migration_message,
    format_fresh_session_manual_recovery_message
)
from macf.hooks.hook_logging import log_hook_event
from macf.agent_events_log import append_event
from macf.utils.state import get_session_state_path, read_json, write_json_safely


def detect_session_migration(current_session_id: str) -> tuple[bool, str, str]:
    """
    Detect session migration (new session ID without compaction).

    Session migration occurs when Claude Code creates a new session (crash recovery,
    manual restart) which orphans the previous TODO file in ~/.claude/todos/.

    EVENT-FIRST: Queries event log for last_session_id, falls back to agent_state.json.

    Args:
        current_session_id: Current session ID

    Returns:
        Tuple of (migration_detected: bool, orphaned_todo_path: str, previous_session_id: str)
        - migration_detected: True if session ID changed
        - orphaned_todo_path: Path to orphaned TODO file (empty if not found)
        - previous_session_id: Previous session ID from events or agent_state
    """
    # EVENT-FIRST: Query event log for last session ID (lazy import to avoid circular)
    try:
        from macf.event_queries import get_last_session_id_from_events
        previous_session_id = get_last_session_id_from_events()
    except Exception as e:
        print(f"⚠️ MACF: Event query for last session failed: {e}", file=sys.stderr)
        try:
            append_event("error", {
                "source": "handle_session_start.detect_session_migration",
                "error": str(e),
                "error_type": type(e).__name__,
                "fallback": "empty_previous_session"
            })
        except Exception as log_e:
            print(f"⚠️ MACF: Event logging also failed: {log_e}", file=sys.stderr)
        previous_session_id = ""

    # NOTE: Event query is now sole source of truth (Phase 7 complete)
    # If no previous_session_id from events, this is first run

    # Check if we have a previous session ID to compare
    if not previous_session_id:
        # First run - no previous session to migrate from
        return False, "", ""

    # Detect session ID change
    if previous_session_id == current_session_id:
        # Same session - no migration
        return False, "", previous_session_id

    # Session ID changed - look for orphaned TODO file
    from pathlib import Path

    todos_dir = Path.home() / ".claude" / "todos"
    if not todos_dir.exists():
        return True, "", previous_session_id  # Migration detected but no todos dir

    # Look for previous session's TODO file
    # Format: {session_id}-agent-{session_id}.json
    previous_todo_pattern = f"{previous_session_id}-agent-{previous_session_id}.json"
    previous_todo_path = todos_dir / previous_todo_pattern

    if previous_todo_path.exists():
        # Check file size (>100 bytes indicates content, not empty placeholder)
        file_size = previous_todo_path.stat().st_size
        if file_size > 100:
            return True, str(previous_todo_path), previous_session_id

    # Migration detected but no substantial TODO file found
    return True, "", previous_session_id


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run SessionStart hook logic.

    Detects compaction events and provides consciousness recovery with:
    - Temporal awareness
    - Mode-aware branching (AUTO vs MANUAL)
    - Artifact discovery
    - Session state restoration

    ⚠️  SIDE EFFECTS: This hook mutates project state on compaction detection

    Side effects (ONLY when testing=False):
    - Increments cycle counter in .maceff/agent_state.json
    - Increments compaction count in session state
    - Updates session timestamps

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
                 If False, apply mutations (production only).
        **kwargs: Additional parameters for future extensibility

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

        # Load session state EARLY for detection
        state = SessionOperationalState.load(session_id)

        # PHASE 1: Check source field FIRST (highest priority)
        # This distinguishes user-initiated /compact from crash-based session migration
        source = data.get('source')
        compaction_detected = False
        detection_method = None

        # PHASE 0.5: Clear policy_reads cache for non-resume sources
        # New cycle = new consciousness = fresh policy engagement required
        # Only 'resume' preserves cache (continuing same conversation)
        if source != 'resume' and not testing:
            state_path = get_session_state_path(session_id)
            try:
                session_state = read_json(state_path)
            except FileNotFoundError:
                # First run - no session state yet, nothing to clear
                session_state = {}
            if 'policy_reads' in session_state:
                session_state['policy_reads'] = {}
                write_json_safely(state_path, session_state)
                log_hook_event({
                    "hook_name": "session_start",
                    "event_type": "POLICY_CACHE_CLEARED",
                    "session_id": session_id,
                    "source": source,
                    "reason": "epistemological_humility"
                })

        if source == 'compact':
            # User-initiated compaction via /compact command
            # This creates new session ID (expected) + context loss (trauma)
            # Use compaction recovery, NOT migration recovery
            compaction_detected = True
            detection_method = "source_field"

            log_hook_event({
                "hook_name": "session_start",
                "event_type": "COMPACTION_CHECK",
                "session_id": session_id,
                "compaction_detected": True,
                "detection_method": "source_field",
                "source": source
            })
            # Fall through to compaction recovery (skip migration check)
        else:
            # PHASE 2: Check for session migration (new session ID without compaction)
            # This handles crash/restart scenarios where TODO file orphaned
            migration_detected, orphaned_todo_path, previous_session_id = detect_session_migration(session_id)

            if migration_detected:
                log_hook_event({
                    "hook_name": "session_start",
                    "event_type": "SESSION_MIGRATION_DETECTED",
                    "session_id": session_id,
                    "previous_session_id": previous_session_id,
                    "orphaned_todo_path": orphaned_todo_path
                })

                # Append migration_detected event with orphaned TODO file size
                orphaned_todo_size = 0
                if orphaned_todo_path:
                    try:
                        orphaned_todo_size = Path(orphaned_todo_path).stat().st_size
                    except Exception:
                        orphaned_todo_size = 0

                # Get current cycle from events (Phase 7: events are sole source)
                current_cycle = get_agent_cycle_number()

                append_event(
                    event="migration_detected",
                    data={
                        "previous_session": previous_session_id,
                        "current_session": session_id,
                        "orphaned_todo_size": orphaned_todo_size,
                        "current_cycle": current_cycle
                    },
                    hook_input=data
                )

                # Event log captures session_id via migration_detected event
                # Detection uses get_last_session_id_from_events() - state write removed

                # Get temporal context for migration message
                temporal_ctx = get_temporal_context()
                environment = get_rich_environment_string()

                # Detect AUTO_MODE for fresh sessions
                auto_mode, mode_source, mode_confidence = detect_auto_mode(session_id)

                # Log mode detection for fresh session
                log_hook_event({
                    "hook_name": "session_start",
                    "event_type": "FRESH_SESSION_MODE_DETECTED",
                    "session_id": session_id,
                    "auto_mode": auto_mode,
                    "mode_source": mode_source,
                    "mode_confidence": mode_confidence
                })

                # Branch based on mode
                if auto_mode:
                    # AUTO_MODE: Brief message, skill invocation, continue
                    migration_msg = format_session_migration_message(
                        previous_session_id=previous_session_id,
                        current_session_id=session_id,
                        orphaned_todo_path=orphaned_todo_path,
                        temporal_ctx=temporal_ctx,
                        environment=environment
                    )
                else:
                    # MANUAL_MODE: Require artifact review, await user authorization
                    artifacts = get_latest_consciousness_artifacts()
                    migration_msg = format_fresh_session_manual_recovery_message(
                        previous_session_id=previous_session_id,
                        current_session_id=session_id,
                        orphaned_todo_path=orphaned_todo_path,
                        artifacts=artifacts,
                        temporal_ctx=temporal_ctx,
                        environment=environment
                    )

                # Return migration recovery message
                return {
                    "continue": True,
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": f"<system-reminder>\n{migration_msg}\n</system-reminder>"
                    }
                }

            # PHASE 3: Fallback detection via JSONL transcript scanning
            # Fallback: JSONL transcript scanning for backward compatibility
            claude_dir = Path.home() / ".claude" / "projects"

            if claude_dir.exists():
                all_jsonl_files = []
                for project_dir in claude_dir.iterdir():
                    if project_dir.is_dir():
                        all_jsonl_files.extend(project_dir.glob("*.jsonl"))

                if all_jsonl_files:
                    latest_file = max(all_jsonl_files, key=lambda p: p.stat().st_mtime)
                    compaction_detected = detect_compaction(latest_file)
                    detection_method = "compact_boundary"

                    # Log detection result
                    log_hook_event({
                        "hook_name": "session_start",
                        "event_type": "COMPACTION_CHECK",
                        "session_id": session_id,
                        "compaction_detected": compaction_detected,
                        "detection_method": "compact_boundary",
                        "transcript": str(latest_file),
                        "source": source  # Log source even if not "compact"
                    })

        if compaction_detected:
            # Side-effects: Skip if testing mode
            if not testing:
                # Emit state snapshot BEFORE modifications (preserves historical baseline)
                # Phase 7: Values now from events, not state files
                from macf.agent_events_log import emit_state_snapshot
                emit_state_snapshot(
                    session_id=session_id,
                    snapshot_type="compaction_recovery",
                    source="events",
                    state_file_values={
                        "cycle_number": get_agent_cycle_number(),
                        "compaction_count": state.compaction_count,
                        "auto_mode": state.auto_mode,
                        "auto_mode_source": state.auto_mode_source
                    }
                )

            # Increment cycle number in agent state (survives session boundaries)
            # Pass testing parameter through (respects safe-by-default)
            cycle_number = increment_agent_cycle(session_id, testing=testing)

            # Compaction count from events (or state fallback + 1 for this compaction)
            new_compaction_count = state.compaction_count + 1

            # Append compaction_detected event
            append_event(
                event="compaction_detected",
                data={
                    "session_id": session_id,
                    "cycle": cycle_number,
                    "detection_method": detection_method,
                    "compaction_count": new_compaction_count
                },
                hook_input=data
            )

            # Detect AUTO_MODE
            auto_mode, source, confidence = detect_auto_mode(session_id)

            # Append auto_mode_detected event for forensic reconstruction
            append_event(
                event="auto_mode_detected",
                data={
                    "session_id": session_id,
                    "cycle": cycle_number,
                    "auto_mode": auto_mode,
                    "source": source,
                    "confidence": confidence
                },
                hook_input=data
            )

            # Get consciousness artifacts
            artifacts = get_latest_consciousness_artifacts()

            # Get temporal context
            temporal_ctx = get_temporal_context()
            environment = get_rich_environment_string()

            # Get token context
            token_info = get_token_info(session_id)

            # Get cycle stats
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

            # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
            return {
                "continue": True,
                "systemMessage": recovery_msg,  # TOP LEVEL - user sees this
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"<system-reminder>\n{recovery_msg}\n</system-reminder>"
                }
            }

        # No compaction detected - provide temporal awareness message
        import time

        # Get current cycle from events (Phase 7: events are sole source)
        current_cycle = get_agent_cycle_number()
        append_event(
            event="session_started",
            data={
                "session_id": session_id,
                "cycle": current_cycle
            },
            hook_input=data
        )

        # session_started event captures session_id for future migration detection
        # Detection uses get_last_session_id_from_events() - state write removed

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

        # Get breadcrumb
        breadcrumb = get_breadcrumb()
        last_session_ended = project_state.get('last_session_ended_at', None)

        # Calculate time gap since last session
        current_time = time.time()

        if last_session_ended is None:
            gap_display = "First session"
        else:
            time_gap_seconds = current_time - last_session_ended
            gap_display = format_duration(time_gap_seconds)

        # session_started event captures timestamp - state write removed

        # Get token context
        token_info = get_token_info(session_id)
        token_section = format_token_context_full(token_info)

        # Format manifest awareness
        manifest_section = format_manifest_awareness()

        # Format temporal awareness message
        message = f"""🏗️ MACF | Session Start
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}

Session Context:
- Time since last session: {gap_display}
- Compaction count: {state.compaction_count}
- Environment: {environment}

{token_section}

{manifest_section}

{format_macf_footer()}"""

        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_COMPLETE",
            "session_id": session_id,
            "compaction_detected": False,
            "time_gap": gap_display
        })

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        return {
            "continue": True,
            "systemMessage": message,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"<system-reminder>\n{message}\n</system-reminder>"
            }
        }

    except Exception as e:
        # Log error and fail gracefully
        import traceback
        error_details = traceback.format_exc()

        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_ERROR",
            "session_id": session_id if session_id else "unknown",
            "error": str(e),
            "error_type": type(e).__name__
        })

        # Return error in systemMessage so user can see it
        return {
            "continue": True,
            "systemMessage": f"⚠️ SessionStart hook error: {type(e).__name__}: {str(e)}\n\nCheck logs: macf_tools hooks logs\n\nFull traceback:\n{error_details}"
        }



if __name__ == "__main__":
    import json
    import os
    import sys
    # MACF_TESTING_MODE env var enables safe testing via subprocess
    testing_mode = os.environ.get('MACF_TESTING_MODE', '').lower() in ('true', '1', 'yes')
    try:
        output = run(sys.stdin.read(), testing=testing_mode)
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

