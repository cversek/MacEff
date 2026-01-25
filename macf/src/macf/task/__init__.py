"""
MACF Task Management Package

Provides CLI access to Claude Code native Task* tools with MacfTaskMetaData (MTMD)
support for hierarchy, version tracking, and lifecycle breadcrumbs.

Task files are stored at: ~/.claude/tasks/{session_uuid}/*.json
"""

from .models import MacfTask, MacfTaskMetaData, MacfTaskUpdate
from .reader import TaskReader, get_current_session_tasks, get_all_session_tasks

__all__ = [
    "MacfTask",
    "MacfTaskMetaData",
    "MacfTaskUpdate",
    "TaskReader",
    "get_current_session_tasks",
    "get_all_session_tasks",
]
