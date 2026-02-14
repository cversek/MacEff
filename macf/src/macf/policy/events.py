"""
Policy injection event schemas and queries.

Defines canonical schemas for policy injection events and provides
query functions for reconstructing active injection state from the
immutable event log.

NOTE: Policy injection events are currently constructed manually in cli.py
(lines ~2267, ~2310, ~2345, ~4365). Future refactor should use these schemas
as the single source of truth for event construction, replacing inline dict
literals with schema-based builders.

Future refactoring candidates for this module:
- event_queries.py: get_active_policy_injections_from_events() belongs here
"""
from typing import Optional, TypedDict


# --- Event Schemas ---

class PolicyInjectionActivatedData(TypedDict, total=False):
    """Schema for 'policy_injection_activated' event data.

    Required fields present in all activations.
    Optional fields present only for task-triggered activations.
    """
    policy_name: str        # required
    policy_path: str        # required
    source: str             # "task_type_auto", "compaction_recovery", or omitted for manual
    task_id: str            # present only for task-triggered activations


class PolicyInjectionClearedData(TypedDict):
    """Schema for 'policy_injection_cleared' event data."""
    policy_name: str
    reason: Optional[str]   # e.g., "auto_clear_after_fire", or omitted for manual clear
    session_id: Optional[str]


class PolicyInjectionDeliveredData(TypedDict):
    """Schema for 'policy_injection_delivered' event data.

    Emitted when a task-bound policy has been injected into additionalContext
    but should remain "active" for proxy tracking until the task ends.
    Prevents re-injection on subsequent tool calls without clearing the
    injection (which would make the proxy report it as missing).

    Contrast with 'cleared': delivered = injected but still task-bound,
    cleared = no longer needed (task paused/completed/manual clear).
    """
    policy_name: str
    source: str             # original source: "task_type_auto", "compaction_recovery"


class PolicyInjectionsClearedAllData(TypedDict):
    """Schema for 'policy_injections_cleared_all' event data. Currently empty."""
    pass


# Event type constants
POLICY_INJECTION_ACTIVATED = "policy_injection_activated"
POLICY_INJECTION_DELIVERED = "policy_injection_delivered"
POLICY_INJECTION_CLEARED = "policy_injection_cleared"
POLICY_INJECTIONS_CLEARED_ALL = "policy_injections_cleared_all"

# Sources that indicate task-bound injections (don't auto-clear)
TASK_BOUND_SOURCES = {"task_type_auto", "compaction_recovery"}

POLICY_LIFECYCLE_EVENTS = {
    POLICY_INJECTION_ACTIVATED,
    POLICY_INJECTION_DELIVERED,
    POLICY_INJECTION_CLEARED,
    POLICY_INJECTIONS_CLEARED_ALL,
}
