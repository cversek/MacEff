"""Unit tests for macf.observability.tool_metadata.

Covers each per-tool formatter (Skill, Bash, Read, Edit, Write, Task,
WebFetch, Grep, Glob, TaskCreate, TaskUpdate, TaskGet) plus the
default-fallback behavior for unknown tools and the graceful-
degradation case when expected fields are absent.
"""
from __future__ import annotations

from macf.observability import format_tool_metadata


# --- Skill ---------------------------------------------------------------

def test_skill_includes_skill_name():
    assert format_tool_metadata("Skill", {"skill": "maceff-delegation"}) == \
        "Skill: maceff-delegation"


def test_skill_missing_skill_falls_back_to_bare_name():
    assert format_tool_metadata("Skill", {}) == "Skill"


# --- Bash ----------------------------------------------------------------

def test_bash_shows_command_prefix():
    assert format_tool_metadata("Bash", {"command": "pytest tests/"}) == \
        "Bash: pytest tests/"


def test_bash_truncates_long_commands():
    long_cmd = "x" * 200
    out = format_tool_metadata("Bash", {"command": long_cmd})
    # 80 char body limit + "Bash: " prefix
    assert out.startswith("Bash: ")
    assert len(out) <= len("Bash: ") + 80


def test_bash_missing_command_falls_back():
    assert format_tool_metadata("Bash", {}) == "Bash"


# --- Read / Edit / Write -------------------------------------------------

def test_read_shows_basename_only():
    assert format_tool_metadata(
        "Read", {"file_path": "/abs/path/to/module.py"}
    ) == "Read: module.py"


def test_edit_shows_basename_only():
    assert format_tool_metadata(
        "Edit", {"file_path": "/some/file.txt"}
    ) == "Edit: file.txt"


def test_write_shows_basename_only():
    assert format_tool_metadata(
        "Write", {"file_path": "/x/y/z.md"}
    ) == "Write: z.md"


def test_read_missing_path_falls_back():
    assert format_tool_metadata("Read", {}) == "Read"


# --- Task (subagent delegation) ------------------------------------------

def test_task_with_subagent_type_and_description():
    out = format_tool_metadata(
        "Task",
        {
            "subagent_type": "DevOpsEng",
            "description": "migrate stderr sites to emit_warning",
        },
    )
    assert out.startswith("Task: [DevOpsEng]")
    assert "migrate stderr sites" in out


def test_task_with_only_subagent_type():
    assert format_tool_metadata(
        "Task", {"subagent_type": "TestEng"}
    ) == "Task: [TestEng]"


def test_task_missing_subagent_type_uses_placeholder():
    out = format_tool_metadata("Task", {"description": "do thing"})
    assert "[?]" in out


# --- WebFetch ------------------------------------------------------------

def test_webfetch_shows_domain():
    assert format_tool_metadata(
        "WebFetch", {"url": "https://example.com/foo/bar"}
    ) == "WebFetch: example.com"


def test_webfetch_missing_url_falls_back():
    assert format_tool_metadata("WebFetch", {}) == "WebFetch"


# --- Grep / Glob ---------------------------------------------------------

def test_grep_shows_pattern():
    assert format_tool_metadata(
        "Grep", {"pattern": "TODO"}
    ) == "Grep: TODO"


def test_glob_shows_pattern():
    assert format_tool_metadata(
        "Glob", {"pattern": "**/*.py"}
    ) == "Glob: **/*.py"


# --- Task* (CLI surfaces) ------------------------------------------------

def test_taskcreate_shows_subject():
    assert format_tool_metadata(
        "TaskCreate", {"subject": "fix bug"}
    ) == "TaskCreate: fix bug"


def test_taskupdate_shows_id_and_status():
    assert format_tool_metadata(
        "TaskUpdate", {"taskId": 42, "status": "in_progress"}
    ) == "TaskUpdate: #42 → in_progress"


def test_taskupdate_without_status_shows_id_only():
    assert format_tool_metadata(
        "TaskUpdate", {"taskId": 42}
    ) == "TaskUpdate: #42"


def test_taskget_shows_id():
    assert format_tool_metadata(
        "TaskGet", {"taskId": 99}
    ) == "TaskGet: #99"


# --- Default fallback ----------------------------------------------------

def test_unknown_tool_returns_bare_name():
    assert format_tool_metadata(
        "UnknownTool", {"anything": "ignored"}
    ) == "UnknownTool"


def test_non_dict_tool_input_does_not_crash():
    """Defensive: even if tool_input arrives as a non-dict, formatter
    returns sensible output without raising."""
    # None
    assert format_tool_metadata("Bash", None) == "Bash"  # type: ignore[arg-type]
    # String
    assert format_tool_metadata("Read", "not a dict") == "Read"  # type: ignore[arg-type]


# --- Edge cases ----------------------------------------------------------

def test_empty_strings_treated_as_missing():
    """Empty string in a field should fall through to the bare tool
    name, not produce an empty trailing colon."""
    assert format_tool_metadata("Skill", {"skill": ""}) == "Skill"
    assert format_tool_metadata("Bash", {"command": ""}) == "Bash"
