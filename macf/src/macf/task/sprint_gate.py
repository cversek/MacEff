"""
Sprint and PLAY_TIME gate helpers for the Stop hook.

Provides:
  - get_sprint_play_time_in_scope(): detect SPRINT or PLAY_TIME task in active scope
  - emit_scope_nag(): SPRINT stop-gate message (scope-completion nag)
  - emit_chain_advance_suggestion(): PLAY_TIME chain-advance suggestion
  - should_fire_markov_for_play_time(): True only when chain exhausted + timer active

Policy specs:
  framework/policies/base/operations/autonomous_sprint.md  §2.3, §4.1
  framework/policies/base/operations/play_time.md          §2.2, §3.1
  framework/policies/base/operations/mode_system.md        §3.2, §7
"""

from typing import Any, Dict, Optional, Tuple

from ..modes.detection import WORK_MODES


def get_sprint_play_time_in_scope() -> Dict[str, Any]:
    """Scan active scope for a SPRINT or PLAY_TIME task.

    Returns a dict with keys:
      sprint_task  - MacfTask | None  (the SPRINT task, if any)
      play_time_task - MacfTask | None (the PLAY_TIME task, if any)
      open_children  - list[dict]     (active scoped tasks excluding the SPRINT parent)

    Resolution rules:
    - Reads the current scope via get_scope_check().
    - For each active task, reads the task file to get task_type from MTMD.
    - SPRINT and PLAY_TIME task types are set in MTMD by create_sprint /
      create_play_time (Phase 3) and are the authoritative source.
    """
    try:
        from .scope import get_scope_check
        from .reader import TaskReader
        from .custom_models import SprintCustom, PlayTimeCustom

        scope = get_scope_check()
        reader = TaskReader()

        sprint_task = None
        play_time_task = None
        # BUG #1067: only ACTIVE tasks count as open_children. Paused tasks
        # are explicitly excluded — they remain in scope (audit trail) but
        # do not block gate satisfaction.
        all_active = scope.get("active", [])

        for entry in all_active:
            tid = entry["id"]
            task = reader.read_task(tid)
            if not task or not task.mtmd:
                continue
            tt = task.mtmd.task_type
            if tt == "SPRINT" and sprint_task is None:
                sprint_task = task
            elif tt == "PLAY_TIME" and play_time_task is None:
                play_time_task = task

        # Open children = ACTIVE tasks (not paused, not inactive) that are NOT
        # the SPRINT parent itself. Per BUG #1067, paused-with-justification
        # is the structural carry-through exit.
        open_children = []
        if sprint_task is not None:
            sprint_id = str(sprint_task.id)
            open_children = [e for e in all_active if str(e["id"]) != sprint_id]

        return {
            "sprint_task": sprint_task,
            "play_time_task": play_time_task,
            "open_children": open_children,
            "paused_count": scope.get("paused_count", 0),
        }
    except (ImportError, OSError, ValueError) as e:
        import sys
        print(f"⚠️ MACF: sprint_gate scope detection failed: {e}", file=sys.stderr)
        return {
            "sprint_task": None,
            "play_time_task": None,
            "open_children": [],
        }


def emit_scope_nag(sprint_task: Any, open_children: list) -> str:
    """Format a SPRINT scope-completion nag message.

    Called by the Stop hook when a SPRINT task is in scope and children remain.
    Returns a string for the 'reason' field of the hook decision dict.

    Policy: autonomous_sprint.md §2.3 — hook emits nag listing open tasks.
    """
    count = len(open_children)
    lines = [f"  #{c['id']}: {c['subject']}" for c in open_children]
    task_list = "\n".join(lines)
    goal = ""
    if sprint_task and sprint_task.mtmd and sprint_task.mtmd.custom:
        goal = sprint_task.mtmd.custom.get("goal", "")

    header = f"🏃 SPRINT in progress"
    if goal:
        header += f': "{goal}"'

    return (
        f"{header}\n"
        f"{count} scoped task(s) remaining — complete them to clear the scope gate:\n"
        f"{task_list}\n"
        f"Complete with: macf_tools task complete <id> --report '...'\n"
        f"Emergency escape: macf_tools mode set MANUAL_MODE --justification <reason>"
    )


def emit_chain_advance_suggestion(
    play_time_task: Any,
    chain_position: int,
    predetermined_chain: list,
) -> str:
    """Format a PLAY_TIME chain-advance suggestion.

    Called when chain_position + 1 < len(predetermined_chain) and the
    agent reaches a gate point (scope cleared, timer still active).

    Returns a string for the 'reason' field of the hook decision dict.

    Policy: play_time.md §2.2 — suggest advancing chain to next mode.
    """
    current_mode = predetermined_chain[chain_position] if chain_position < len(predetermined_chain) else "?"
    next_mode = predetermined_chain[chain_position + 1]
    next_emoji = WORK_MODES.get(next_mode, {}).get("emoji", "")
    skill_suffix_map = {
        "DISCOVER":     "exploratory-self-motivation",
        "EXPERIMENT":   "experimental-self-motivation",
        "BUILD":        "generative-self-motivation",
        "CURATE":       "curative-self-motivation",
        "CONSOLIDATE":  "consolidative-self-motivation",
    }
    skill = f"maceff-{skill_suffix_map.get(next_mode, 'exploratory-self-motivation')}"

    goal = ""
    if play_time_task and play_time_task.mtmd and play_time_task.mtmd.custom:
        goal = play_time_task.mtmd.custom.get("goal", "")

    header = f"⏲️ PLAY_TIME chain advance: {current_mode} → {next_mode} {next_emoji}"
    if goal:
        header += f'\n   Session goal: "{goal}"'

    return (
        f"{header}\n"
        f"   Chain position: {chain_position} → {chain_position + 1} "
        f"(of {len(predetermined_chain)} steps)\n"
        f"   Invoke: /{skill}\n"
        f"   ULTRATHINK: choose the suggested skill or justify an override in task notes."
    )


def should_fire_markov_for_play_time(play_time_task: Any) -> bool:
    """Return True when PLAY_TIME chain is exhausted AND timer is active.

    This is the condition under which the Markov recommender should fire
    instead of a chain-advance suggestion.

    Policy: play_time.md §3.1 — recommender engages only after chain exhaustion.
    mode_system.md §4.5 — Markov gated on chain_exhausted + timer_active.
    """
    try:
        from .scope import get_active_timer
        if not play_time_task or not play_time_task.mtmd:
            return False
        custom = play_time_task.mtmd.custom
        if not custom:
            return False
        chain_exhausted = custom.get("chain_exhausted", False)
        if not chain_exhausted:
            return False
        timer = get_active_timer()
        return timer.get("active", False)
    except (ImportError, OSError, AttributeError) as e:
        import sys
        print(f"⚠️ MACF: timer check for PLAY_TIME failed: {e}", file=sys.stderr)
        return False


def parse_play_time_custom(task: Any) -> Optional[Any]:
    """Parse PlayTimeCustom from a task's MTMD custom dict.

    Returns a PlayTimeCustom instance or None if parsing fails.
    """
    try:
        from .custom_models import PlayTimeCustom
        if not task or not task.mtmd:
            return None
        custom = task.mtmd.custom
        if not custom:
            return None
        return PlayTimeCustom.from_dict(custom)
    except (ImportError, ValueError, TypeError, AttributeError) as e:
        # Pydantic ValidationError is ValueError-derived; missing fields → TypeError;
        # malformed task object → AttributeError. None signals "couldn't parse".
        import sys
        print(f"⚠️ MACF: parse_play_time_custom skipped task: {e}", file=sys.stderr)
        return None


def advance_play_time_chain(task: Any) -> Tuple[bool, Optional[str]]:
    """Atomically advance chain_position on a PLAY_TIME task's MTMD custom.

    Returns (success, error_message). Uses the same read-modify-write pattern
    as update_task_file (no external lock needed for single-agent use).

    Updates:
      chain_position += 1
      chain_exhausted = (new_position >= len(predetermined_chain))
      current_work_mode = predetermined_chain[new_position] if not exhausted
    """
    import copy

    try:
        from .reader import TaskReader, update_task_file
        from .custom_models import PlayTimeCustom

        if not task or not task.mtmd:
            return False, "task has no MTMD"

        custom = task.mtmd.custom
        if not custom:
            return False, "task has no custom dict"

        pt = PlayTimeCustom.from_dict(custom)
        chain = pt.predetermined_chain
        new_pos = pt.chain_position + 1
        # "Exhausted" semantics: agent is currently at the last chain entry,
        # so no more useful advances are possible. Triggers the moment we
        # ENTER the last mode rather than when we'd try to advance past it
        # (which never happens — there's no chain[N] to advance to). Fix
        # for Phase 8 friction finding #4.
        exhausted = new_pos >= len(chain) - 1

        new_custom = pt.model_dump()
        new_custom["chain_position"] = new_pos
        new_custom["chain_exhausted"] = exhausted
        # current_work_mode mirrors the chain unless we've gone past the end
        # (which only happens if a caller advances beyond the final entry —
        # leave the last mode as current in that case)
        if new_pos < len(chain):
            new_custom["current_work_mode"] = chain[new_pos]

        reader = TaskReader()
        stored_task = reader.read_task(task.id)
        if not stored_task or not stored_task.mtmd:
            return False, f"could not re-read task #{task.id}"

        new_mtmd = copy.deepcopy(stored_task.mtmd)
        new_mtmd.custom = new_custom
        new_description = stored_task.description_with_updated_mtmd(new_mtmd)
        ok = update_task_file(str(task.id), {"description": new_description})
        if not ok:
            return False, f"update_task_file failed for task #{task.id}"
        return True, None

    except Exception as e:
        return False, str(e)
