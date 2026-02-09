"""
Task protection module for Phase 5: Hook Integration.

Provides protection logic for task operations:
- MISSION/EXPERIMENT/DETOUR/DELEG_PLAN/SUBPLAN require plan_ca_ref
- Description changes require grant (with specific exceptions)
- Grant flow: keyword → confirmation → allow
- AUTO_MODE self-grant for LOW/MEDIUM operations

Protection Levels:
- HIGH: User grant required (delete, modify existing values, remove content)
- MEDIUM: Agent self-grant in AUTO_MODE (first assignment of null fields)
- LOW: Auto-allowed (append to description, custom additions, updates additions)

This module is called from BOTH:
- PreToolUse hook (for CC native TaskCreate/TaskUpdate)
- CLI commands (task edit, task delete, etc.)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Tuple, Set, List, Union
import re

from .models import MacfTaskMetaData


class ProtectionLevel(Enum):
    """Protection levels for task operations."""
    HIGH = "HIGH"      # User grant required always
    MEDIUM = "MEDIUM"  # Agent self-grant in AUTO_MODE
    LOW = "LOW"        # Auto-allowed


@dataclass
class ProtectionResult:
    """Result of protection check."""
    allowed: bool
    level: ProtectionLevel
    reason: str
    grant_hint: Optional[str] = None  # How to grant if blocked


# Task types that require plan_ca_ref (from task_management.md §2.1)
TYPES_REQUIRING_PLAN_CA: Set[str] = {
    "MISSION",      # roadmap.md
    "EXPERIMENT",   # protocol.md
    "DETOUR",       # roadmap.md
    "DELEG_PLAN",   # deleg_plan.md
    "SUBPLAN",      # subplan CA
}

# All valid task types
VALID_TASK_TYPES: Set[str] = {
    "MISSION", "EXPERIMENT", "DETOUR", "PHASE", "TASK", "BUG",
    "DELEG_PLAN", "SUBPLAN", "ARCHIVE", "GH_ISSUE"
}

# Emoji to type mapping (fallback when MTMD task_type not set)
EMOJI_TO_TYPE: Dict[str, str] = {
    "🗺️": "MISSION",
    "🧪": "EXPERIMENT",
    "↩️": "DETOUR",
    "📜": "DELEG_PLAN",
    "📋": "SUBPLAN",
    "📦": "ARCHIVE",
    "🔧": "TASK",
    "🐛": "BUG",
    "🐙": "GH_ISSUE",
}


def get_task_type(description: str, subject: str) -> Optional[str]:
    """
    Get task type from MTMD (authoritative) or subject line (fallback).

    Priority:
    1. MTMD task_type field (if present and valid)
    2. Subject line emoji (fallback)

    Args:
        description: Task description (may contain MTMD)
        subject: Task subject line

    Returns:
        Task type string or None if not determinable
    """
    # Try MTMD first (authoritative)
    mtmd = MacfTaskMetaData.parse(description)
    if mtmd and mtmd.task_type:
        if mtmd.task_type in VALID_TASK_TYPES:
            return mtmd.task_type

    # Fallback to subject line emoji detection
    for emoji, task_type in EMOJI_TO_TYPE.items():
        if emoji in subject:
            return task_type

    return None


def check_task_create(
    subject: str,
    description: str,
    auto_mode: bool = False
) -> ProtectionResult:
    """
    Check if TaskCreate operation should be allowed.

    Tasks with types in TYPES_REQUIRING_PLAN_CA require plan_ca_ref in MTMD.

    Args:
        subject: Task subject line
        description: Task description (may contain MTMD)
        auto_mode: Whether AUTO_MODE is active

    Returns:
        ProtectionResult indicating if creation is allowed
    """
    task_type = get_task_type(description, subject)

    # Check if this type requires plan_ca_ref
    requires_plan = task_type in TYPES_REQUIRING_PLAN_CA

    if not requires_plan:
        return ProtectionResult(
            allowed=True,
            level=ProtectionLevel.LOW,
            reason=f"Task type '{task_type or 'regular'}' does not require plan_ca_ref"
        )

    # Check for plan_ca_ref in description (MTMD block)
    mtmd = MacfTaskMetaData.parse(description)
    has_plan_ref = mtmd is not None and mtmd.plan_ca_ref is not None

    if has_plan_ref:
        return ProtectionResult(
            allowed=True,
            level=ProtectionLevel.LOW,
            reason=f"{task_type} has plan_ca_ref"
        )

    # Missing plan_ca_ref - HIGH protection (requires user intervention)
    ca_type = "roadmap.md" if task_type in ("MISSION", "DETOUR") else "protocol.md" if task_type == "EXPERIMENT" else "CA file"

    return ProtectionResult(
        allowed=False,
        level=ProtectionLevel.HIGH,
        reason=f"{task_type} requires plan_ca_ref in MTMD",
        grant_hint=(
            f"To create a {task_type}:\n"
            f"  1. Use /maceff:roadmap:draft to create {ca_type} first\n"
            f"  2. Or add plan_ca_ref to MTMD: plan_ca_ref: path/to/{ca_type}"
        )
    )


def check_task_update_description(
    task_id: int,
    old_description: str,
    new_description: str,
    auto_mode: bool = False,
    has_grant: bool = False
) -> ProtectionResult:
    """
    Check if TaskUpdate description change should be allowed.

    Allowed without grant:
    1. Appending to non-MTMD content (existing prefix preserved exactly)
    2. First assignment of null MTMD fields (null → value)
    3. Adding new fields to MTMD `custom` dict
    4. Adding entries to MTMD `updates` list

    Requires grant:
    - Modifying existing non-MTMD content (not just appending)
    - Modifying MTMD field that already has a value
    - Removing entries from `custom` or `updates`
    - Removing MTMD block entirely

    Args:
        task_id: Task ID being updated
        old_description: Current description
        new_description: Proposed new description
        auto_mode: Whether AUTO_MODE is active
        has_grant: Whether a grant exists for this operation

    Returns:
        ProtectionResult indicating if update is allowed
    """
    # Empty old description - anything goes (no content to protect)
    if not old_description.strip():
        return ProtectionResult(
            allowed=True,
            level=ProtectionLevel.LOW,
            reason="No existing content to protect"
        )

    # Parse MTMD from both
    old_mtmd = MacfTaskMetaData.parse(old_description)
    new_mtmd = MacfTaskMetaData.parse(new_description)

    # Extract non-MTMD content
    old_content = _extract_non_mtmd_content(old_description)
    new_content = _extract_non_mtmd_content(new_description)

    # Check 1: MTMD removal (old has MTMD, new doesn't)
    if old_mtmd and not new_mtmd:
        if has_grant:
            return ProtectionResult(
                allowed=True,
                level=ProtectionLevel.HIGH,
                reason="MTMD removal granted"
            )
        return ProtectionResult(
            allowed=False,
            level=ProtectionLevel.HIGH,
            reason="Removing MTMD block requires grant",
            grant_hint=_grant_hint_update(task_id)
        )

    # Check 2: Non-MTMD content modification
    # Allowed: new_content starts with old_content (appending only)
    if old_content:
        if not new_content.startswith(old_content):
            if has_grant:
                return ProtectionResult(
                    allowed=True,
                    level=ProtectionLevel.HIGH,
                    reason="Description modification granted"
                )
            return ProtectionResult(
                allowed=False,
                level=ProtectionLevel.HIGH,
                reason="Modifying existing description content requires grant (append-only without grant)",
                grant_hint=_grant_hint_update(task_id)
            )

    # Check 3: MTMD field modifications
    if old_mtmd and new_mtmd:
        mtmd_result = _check_mtmd_changes(old_mtmd, new_mtmd, has_grant, task_id)
        if mtmd_result:
            return mtmd_result

    # All checks passed - allowed
    return ProtectionResult(
        allowed=True,
        level=ProtectionLevel.LOW,
        reason="Description update is allowed (append-only or permitted MTMD changes)"
    )


def _extract_non_mtmd_content(description: str) -> str:
    """Extract description content excluding MTMD block."""
    pattern = r'<macf_task_metadata[^>]*>.*?</macf_task_metadata>'
    return re.sub(pattern, '', description, flags=re.DOTALL).strip()


def _check_mtmd_changes(
    old_mtmd: MacfTaskMetaData,
    new_mtmd: MacfTaskMetaData,
    has_grant: bool,
    task_id: int
) -> Optional[ProtectionResult]:
    """
    Check what changed between two MTMD instances.

    Allowed without grant:
    - First assignment (null → value) for any field
    - Adding to `custom` dict (new keys only)
    - Adding to `updates` list (appending only)

    Requires grant:
    - Modifying existing field value
    - Removing from `custom` or `updates`

    Returns:
        ProtectionResult if blocked, None if allowed
    """
    # Fields to check (excluding custom and updates which are handled separately)
    scalar_fields = [
        'creation_breadcrumb', 'created_cycle', 'created_by', 'task_type',
        'plan_ca_ref', 'experiment_ca_ref', 'parent_id',
        'repo', 'target_version', 'release_branch',
        'completion_breadcrumb', 'unblock_breadcrumb',
        'archived', 'archived_at'
    ]

    # Check scalar fields
    for field in scalar_fields:
        old_val = getattr(old_mtmd, field, None)
        new_val = getattr(new_mtmd, field, None)

        if old_val != new_val:
            # First assignment (null → value) is allowed
            if old_val is None or (isinstance(old_val, bool) and old_val is False and field == 'archived'):
                continue  # Allowed

            # Modification of existing value requires grant
            if has_grant:
                continue  # Allowed with grant

            return ProtectionResult(
                allowed=False,
                level=ProtectionLevel.HIGH,
                reason=f"Modifying MTMD field '{field}' requires grant (was: {old_val!r})",
                grant_hint=_grant_hint_update(task_id)
            )

    # Check updates list
    old_updates = old_mtmd.updates or []
    new_updates = new_mtmd.updates or []

    # Removal of updates requires grant
    if len(new_updates) < len(old_updates):
        if not has_grant:
            return ProtectionResult(
                allowed=False,
                level=ProtectionLevel.HIGH,
                reason="Removing MTMD updates requires grant",
                grant_hint=_grant_hint_update(task_id)
            )

    # Modification of existing updates requires grant
    for i, old_update in enumerate(old_updates):
        if i >= len(new_updates):
            break  # Already handled removal above
        new_update = new_updates[i]
        if old_update.breadcrumb != new_update.breadcrumb or old_update.description != new_update.description:
            if not has_grant:
                return ProtectionResult(
                    allowed=False,
                    level=ProtectionLevel.HIGH,
                    reason=f"Modifying MTMD updates[{i}] requires grant",
                    grant_hint=_grant_hint_update(task_id)
                )

    # Adding new updates is always allowed (lifecycle tracking)

    # Check custom dict
    old_custom = old_mtmd.custom or {}
    new_custom = new_mtmd.custom or {}

    # Removal of custom keys requires grant
    for key in old_custom:
        if key not in new_custom:
            if not has_grant:
                return ProtectionResult(
                    allowed=False,
                    level=ProtectionLevel.HIGH,
                    reason=f"Removing MTMD custom.{key} requires grant",
                    grant_hint=_grant_hint_update(task_id)
                )

    # Modification of existing custom keys requires grant
    for key in old_custom:
        if key in new_custom and old_custom[key] != new_custom[key]:
            if not has_grant:
                return ProtectionResult(
                    allowed=False,
                    level=ProtectionLevel.HIGH,
                    reason=f"Modifying MTMD custom.{key} requires grant",
                    grant_hint=_grant_hint_update(task_id)
                )

    # Adding new custom keys is always allowed

    return None  # All checks passed


def _grant_hint_update(task_id: int) -> str:
    """Generate grant hint for task update."""
    return (
        f"To modify task #{task_id} description:\n"
        f"  User: say 'granted!' or run: macf_tools task grant-update {task_id}"
    )


def check_grant_in_events(
    operation: str,
    task_ids: Union[str, List[str]],
    field: Optional[str] = None,
    value: Any = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a grant exists for an operation on specific task(s).

    Looks for grant events in the event log:
    - task_grant_update: Grant for description update
    - task_grant_delete: Grant for task deletion
    - task_grant_create: Grant for creating type without plan_ca_ref

    Args:
        operation: Operation type (update, delete, create)
        task_ids: Task ID(s) to check - must match exactly (set equality)

    Returns:
        Tuple of (has_grant, grant_event)
    """
    from macf.event_queries import get_latest_event

    # Normalize requested task_ids to set of strings
    if isinstance(task_ids, list):
        requested_set = set(str(tid) for tid in task_ids)
    else:
        requested_set = {str(task_ids)}

    # Check for explicit grant event
    grant_event_type = f"task_grant_{operation}"
    grant_event = get_latest_event(grant_event_type)

    if grant_event:
        grant_data = grant_event.get("data", {})
        grant_task_ids = grant_data.get("task_ids", [])

        # Normalize grant task_ids to set
        granted_set = set(str(tid) for tid in grant_task_ids)

        # Sets must match exactly
        if requested_set == granted_set:
            # Check if grant was cleared
            cleared_event = get_latest_event(f"task_grant_{operation}_cleared")
            if cleared_event:
                grant_ts = grant_event.get("timestamp", 0)
                cleared_ts = cleared_event.get("timestamp", 0)
                if cleared_ts > grant_ts:
                    return False, None

            # If field/value specified, verify they match the grant
            grant_field = grant_data.get("field")
            grant_value = grant_data.get("value")

            if grant_field is not None:
                if field != grant_field:
                    return False, None
                if grant_value is not None and value != grant_value:
                    return False, None

            return True, grant_event

    return False, None


def clear_grant(operation: str, task_ids: Union[str, List[str]], reason: str = "consumed"):
    """
    Clear a grant after it's been used.

    Args:
        operation: Operation type (update, delete, create)
        task_ids: Task ID(s) that were granted
        reason: Reason for clearing
    """
    from macf.agent_events_log import append_event

    # Normalize to list
    if isinstance(task_ids, list):
        ids_list = [str(tid) for tid in task_ids]
    else:
        ids_list = [str(task_ids)]

    append_event(
        event=f"task_grant_{operation}_cleared",
        data={
            "task_ids": ids_list,
            "reason": reason
        }
    )


def create_grant(
    operation: str,
    task_ids: Union[str, List[str]],
    reason: str = "",
    field: Optional[str] = None,
    value: Any = None,
):
    """
    Create a grant for an operation.

    Args:
        operation: Operation type (update, delete, create)
        task_ids: Task ID(s) - single string or list of strings (REQUIRED)
        reason: Reason for granting
        field: Specific field to grant modification for (optional)
        value: Expected new value for field (optional, requires field)
    """
    from macf.agent_events_log import append_event

    # Normalize to list
    if isinstance(task_ids, list):
        ids_list = [str(tid) for tid in task_ids]
    else:
        ids_list = [str(task_ids)]

    data = {
        "task_ids": ids_list,
        "reason": reason,
    }
    if field is not None:
        data["field"] = field
    if value is not None:
        data["value"] = value

    append_event(
        event=f"task_grant_{operation}",
        data=data
    )
