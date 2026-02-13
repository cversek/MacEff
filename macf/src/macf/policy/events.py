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


class PolicyInjectionsClearedAllData(TypedDict):
    """Schema for 'policy_injections_cleared_all' event data. Currently empty."""
    pass


# Event type constants
POLICY_INJECTION_ACTIVATED = "policy_injection_activated"
POLICY_INJECTION_CLEARED = "policy_injection_cleared"
POLICY_INJECTIONS_CLEARED_ALL = "policy_injections_cleared_all"

POLICY_LIFECYCLE_EVENTS = {
    POLICY_INJECTION_ACTIVATED,
    POLICY_INJECTION_CLEARED,
    POLICY_INJECTIONS_CLEARED_ALL,
}
