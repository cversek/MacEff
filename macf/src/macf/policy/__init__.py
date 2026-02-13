"""
Policy subpackage - policy lifecycle management.

Mirrors the task/ subpackage pattern. Modules:
- events.py: Policy injection event schemas and queries
- injection.py: Emit/retract policy injection events

Future refactoring candidates (currently scattered):
- utils/manifest.py: get_policies_for_task_type() -> policy/manifest.py
- utils/__init__.py: find_policy_file() -> policy/resolution.py
- event_queries.py: get_active_policy_injections_from_events() -> policy/events.py
"""
