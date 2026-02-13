"""
Policy injection lifecycle management.

Provides functions for emitting and querying policy injections
based on task state. Used by hooks and proxy.

Future refactoring candidates for this module:
- hooks/handle_pre_tool_use.py: inline policy reading + injection logic
- cli.py: manual append_event calls for policy injection/clear
"""
import sys
from typing import Dict, List

from .events import POLICY_INJECTION_ACTIVATED


def emit_policy_injections_for_tasks(
    active_tasks: Dict[str, str],
    source: str = "task_type_auto",
) -> List[str]:
    """
    Emit policy_injection_activated events for in_progress tasks.

    Looks up manifest task_type_policies mappings and emits events
    for each policy, making them visible to the pre_tool_use hook.

    Args:
        active_tasks: Dict of {task_id: task_type} from get_active_tasks_from_events()
        source: Event source tag (e.g., "compaction_recovery", "task_type_auto")

    Returns:
        List of policy names that were emitted.
    """
    from ..agent_events_log import append_event
    from ..utils.manifest import get_policies_for_task_type
    from ..utils import find_policy_file

    emitted: List[str] = []

    for task_id, task_type in active_tasks.items():
        policies = get_policies_for_task_type(task_type)
        for policy_name in policies:
            policy_path = find_policy_file(policy_name)
            if policy_path:
                append_event(POLICY_INJECTION_ACTIVATED, {
                    "policy_name": policy_name,
                    "policy_path": str(policy_path),
                    "source": source,
                    "task_id": str(task_id),
                })
                emitted.append(policy_name)
            else:
                print(
                    f"[policy] ⚠️ Policy '{policy_name}' not found "
                    f"for task #{task_id} ({task_type})",
                    file=sys.stderr
                )

    return emitted


def get_expected_policies_for_active_tasks(
    active_tasks: Dict[str, str],
) -> set:
    """
    Get the set of policy names expected for active tasks (no side effects).

    Used by proxy startup detection to compare expected vs actual injections.

    Args:
        active_tasks: Dict of {task_id: task_type}

    Returns:
        Set of policy name strings.
    """
    from ..utils.manifest import get_policies_for_task_type

    expected: set = set()
    for task_id, task_type in active_tasks.items():
        policies = get_policies_for_task_type(task_type)
        if policies:
            expected.update(policies)

    return expected
