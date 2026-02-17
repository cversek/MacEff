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
    get_latest_consciousness_artifacts,
    detect_auto_mode,
    get_temporal_context,
    get_rich_environment_string,
    format_duration,
    format_macf_footer,
    format_proprioception_awareness,
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
from macf.event_queries import (
    get_last_session_end_time_from_events,
    get_compaction_count_from_events,
    get_auto_mode_from_events,
    get_cycle_number_from_events
)


def detect_session_migration(current_session_id: str) -> tuple[bool, str, str]:
    """
    Detect session migration (new session ID without compaction).

    Session migration occurs when Claude Code creates a new session (crash recovery,
    manual restart) which orphans the previous TODO file in ~/.claude/todos/.

    EVENT-FIRST: Queries event log for last_session_id, event log is sole source of truth.

    Args:
        current_session_id: Current session ID

    Returns:
        Tuple of (migration_detected: bool, orphaned_todo_path: str, previous_session_id: str)
        - migration_detected: True if session ID changed
        - orphaned_todo_path: Path to orphaned TODO file (empty if not found)
        - previous_session_id: Previous session ID from events
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

    # NOTE: Event query is sole source of truth
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


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run SessionStart hook logic.

    Detects compaction events and provides consciousness recovery with:
    - Temporal awareness
    - Mode-aware branching (AUTO vs MANUAL)
    - Artifact discovery
    - Session state restoration

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict ready for JSON output with compaction recovery if detected
    """
    session_id = None

    try:
        # Parse input (may be empty for SessionStart)
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session ID from Claude Code's authoritative input
        # Claude Code provides session_id in hook input - this is the source of truth
        session_id = data.get("session_id")
        if not session_id:
            print("⚠️ MACF: No session_id in hook input, falling back to mtime detection", file=sys.stderr)
            session_id = get_current_session_id()

        # Log hook start
        log_hook_event({
            "hook_name": "session_start",
            "event_type": "HOOK_START",
            "session_id": session_id
        })

        # PHASE 1: Check source field FIRST (highest priority)
        # This distinguishes user-initiated /compact from crash-based session migration
        source = data.get('source')
        compaction_detected = False
        detection_method = None

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
        elif source == 'resume':
            # μC (microcompaction) resume — NOT a compaction, NOT a migration.
            # Same session continues. Skip all compaction/migration detection.
            # CRITICAL: Do NOT fall through to PHASE 3 JSONL scanning, which
            # would find stale compact_boundary markers from earlier real
            # compaction and falsely increment the cycle counter.
            compaction_detected = False
            detection_method = None

            log_hook_event({
                "hook_name": "session_start",
                "event_type": "RESUME_DETECTED",
                "session_id": session_id,
                "source": source
            })
            # Fall through to "no compaction detected" temporal awareness path
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

                # Get current cycle from events
                current_cycle = get_cycle_number_from_events()

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
            # Get current values from events BEFORE modifications
            compaction_info = get_compaction_count_from_events(session_id)
            current_compaction_count = compaction_info.get('count', 0)
            auto_mode, auto_mode_source, confidence = detect_auto_mode(session_id)

            # Emit state snapshot BEFORE modifications (preserves historical baseline)
            # All values from events, no state files
            from macf.agent_events_log import emit_state_snapshot
            emit_state_snapshot(
                session_id=session_id,
                snapshot_type="compaction_recovery",
                source="events",
                state_file_values={
                    "cycle_number": get_cycle_number_from_events(),
                    "compaction_count": current_compaction_count,
                    "auto_mode": auto_mode,
                    "auto_mode_source": auto_mode_source
                }
            )

            # Cycle number: current + 1 (event log is source of truth)
            # compaction_detected event captures the new cycle number
            cycle_number = get_cycle_number_from_events() + 1

            # Compaction count from events + 1 for this compaction
            new_compaction_count = current_compaction_count + 1

            # Scan filesystem for in_progress tasks (authoritative source of truth).
            # Filesystem scan is more reliable than event-log scan here because:
            # - Sentinel #000 may not have event-log entries from older sessions
            # - Event log scan stops at compaction boundary (chicken-and-egg)
            from macf.task.events import get_active_tasks_from_filesystem
            pre_compaction_active_tasks = get_active_tasks_from_filesystem()

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

            # Append auto_mode_detected event for forensic reconstruction
            # (auto_mode already detected earlier for state snapshot)
            append_event(
                event="auto_mode_detected",
                data={
                    "session_id": session_id,
                    "cycle": cycle_number,
                    "auto_mode": auto_mode,
                    "source": auto_mode_source,
                    "confidence": confidence
                },
                hook_input=data
            )

            # AFTER compaction boundary: re-emit task_started AND policy injections
            # for in_progress tasks. Both must land AFTER the boundary so
            # post-compaction reverse scans find them.
            if pre_compaction_active_tasks:
                # Re-emit task_started events (so proxy/queries see active tasks)
                from macf.task.events import emit_task_started_for_recovery
                restarted = emit_task_started_for_recovery(
                    pre_compaction_active_tasks,
                    source="compaction_recovery",
                )

                # Re-emit policy injections (so PreToolUse injects policies)
                from macf.policy.injection import emit_policy_injections_for_tasks
                reinjected = emit_policy_injections_for_tasks(
                    pre_compaction_active_tasks,
                    source="compaction_recovery",
                )

                if restarted or reinjected:
                    log_hook_event({
                        "hook_name": "session_start",
                        "event_type": "COMPACTION_RECOVERY",
                        "tasks": dict(pre_compaction_active_tasks),
                        "tasks_restarted": restarted,
                        "policies_reinjected": reinjected,
                    })

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
            # Pass event-derived values instead of state object
            recovery_msg = format_consciousness_recovery_message(
                session_id=session_id,
                auto_mode=auto_mode,
                compaction_count=new_compaction_count,
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
                "compaction_count": new_compaction_count
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

        # Get current cycle from events
        current_cycle = get_cycle_number_from_events()
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

        # Get last session end time from events (events are sole source)
        last_session_ended = get_last_session_end_time_from_events()

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

        # Format proprioception awareness (CLI capabilities + environment)
        # Only inject on fresh sessions, not resumes (token economy)
        # Fresh = first session, /clear, or significant time gap
        # Resume = source == 'resume' (continuing existing session)
        is_fresh_session = source != 'resume'
        proprioception_section = format_proprioception_awareness() if is_fresh_session else ""

        # Get compaction count from events (events are sole source)
        compaction_info = get_compaction_count_from_events(session_id)
        compaction_count = compaction_info.get('count', 0)

        # Format temporal awareness message
        message = f"""🏗️ MACF | Session Start
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}

Session Context:
- Time since last session: {gap_display}
- Compaction count: {compaction_count}
- Environment: {environment}

{token_section}

{manifest_section}

{proprioception_section}

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
    import sys
    try:
        output = run(sys.stdin.read())
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

