"""
MACF Task Management Package

Provides CLI access to Claude Code native Task* tools with MacfTaskMetaData (MTMD)
support for hierarchy, version tracking, and lifecycle breadcrumbs.

Task files are stored at: ~/.claude/tasks/{session_uuid}/*.json
"""

from .models import MacfTask, MacfTaskMetaData, MacfTaskUpdate
from .reader import TaskReader, get_current_session_tasks, get_all_session_tasks, update_task_file, add_task_note
from .archive import (
    archive_task,
    restore_task,
    list_archived_tasks,
    ArchiveResult,
    RestoreResult,
    get_archive_dir,
)
from .protection import (
    ProtectionLevel,
    ProtectionResult,
    check_task_create,
    check_task_update_description,
    check_grant_in_events,
    clear_grant,
    create_grant,
    get_task_type,
    TYPES_REQUIRING_PLAN_CA,
    VALID_TASK_TYPES,
)

__all__ = [
    "MacfTask",
    "MacfTaskMetaData",
    "MacfTaskUpdate",
    # Custom dict models (task-type-specific validators)
    "SprintCustom",
    "PlayTimeCustom",
    "TaskReader",
    "get_current_session_tasks",
    "get_all_session_tasks",
    "update_task_file",
    "add_task_note",
    # Archive
    "archive_task",
    "restore_task",
    "list_archived_tasks",
    "ArchiveResult",
    "RestoreResult",
    "get_archive_dir",
    # Protection
    "ProtectionLevel",
    "ProtectionResult",
    "check_task_create",
    "check_task_update_description",
    "check_grant_in_events",
    "clear_grant",
    "create_grant",
    "get_task_type",
    "TYPES_REQUIRING_PLAN_CA",
    "VALID_TASK_TYPES",
]

_LAZY = {"SprintCustom": ".custom_models", "PlayTimeCustom": ".custom_models"}


def __getattr__(name):
    # Loaded on first use: the custom models import pydantic, which most task
    # commands never need (they read tasks; only creating a sprint or play time
    # and the sprint gate build these). ``from macf.task import SprintCustom``
    # still works; it arrives here.
    if name in _LAZY:
        import importlib
        value = getattr(importlib.import_module(_LAZY[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
