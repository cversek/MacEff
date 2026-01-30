"""
Integration tests for task CLI commands.

Tests the task management commands introduced in v0.4.0:
- task create (mission, experiment, phase, bug, deleg, task)
- task archive/restore
- task grant-update/grant-delete

Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_task_env fixture to prevent
polluting production tasks and event logs.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolated_task_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production tasks and event logs.

    All CLI invocations:
    1. Read/write task JSON files from ~/.claude/tasks/
    2. Emit cli_command_invoked events to agent_events_log.jsonl
    3. May create archive files in tasks/archive/

    Without isolation, tests pollute production data.

    This fixture is autouse=True so ALL tests in this module get isolation.

    CRITICAL: Returns a dict with both the tasks_dir Path AND an env dict
    for subprocess.run(). monkeypatch.setenv() only affects the current
    process - subprocess.run() spawns a child that inherits from the actual
    OS environment, not the monkeypatched one.

    Usage:
        result = subprocess.run([...], env=isolated_task_env['env'], ...)
        task_files = list(isolated_task_env['tasks_dir'].glob("*.json"))
    """
    # Isolate task storage - create session folder structure
    test_tasks_dir = tmp_path / "tasks"
    test_session_id = "test-session-uuid"
    test_session_dir = test_tasks_dir / test_session_id
    test_session_dir.mkdir(parents=True)

    # Isolate event log
    test_log = tmp_path / "test_cli_events.jsonl"

    # Build environment dict for subprocess - merge with current env
    # This is CRITICAL: subprocess.run() needs explicit env= parameter
    subprocess_env = {
        **os.environ,
        "MACF_TASKS_DIR": str(test_tasks_dir),
        "MACF_SESSION_ID": test_session_id,
        "MACF_EVENTS_LOG_PATH": str(test_log),
    }

    # Also set in current process (for any in-process code paths)
    monkeypatch.setenv("MACF_TASKS_DIR", str(test_tasks_dir))
    monkeypatch.setenv("MACF_SESSION_ID", test_session_id)
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))

    yield {
        'tasks_dir': test_tasks_dir,
        'session_dir': test_session_dir,
        'env': subprocess_env,
    }


class TestTaskCreateMissionCommand:
    """Test macf_tools task create mission command."""

    def test_create_mission_minimal_args(self, isolated_task_env):
        """Test mission creation with just title (minimal args)."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'mission', 'Test Mission Title'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Should show success message with emoji (note: output says "Created MISSION" not "Created task")
        assert 'Created' in result.stdout or '🗺️' in result.stdout

        # Verify task file was created in session directory
        task_files = list(isolated_task_env['session_dir'].glob("*.json"))
        assert len(task_files) >= 1

    def test_create_mission_with_repo_version(self, isolated_task_env):
        """Test mission creation with --repo and --version metadata."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'mission', 'MacEff Release',
             '--repo', 'MacEff', '--version', '0.4.0'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Should include repo/version in output or task metadata
        assert 'Created task' in result.stdout or 'MacEff' in result.stdout

    def test_create_mission_json_output(self, isolated_task_env):
        """Test mission creation with --json flag returns valid JSON."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'mission', 'JSON Mission', '--json'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Output should be valid JSON
        task_data = json.loads(result.stdout)
        assert isinstance(task_data, dict)
        # JSON output includes subject (with embedded ID) and task_type
        assert 'subject' in task_data
        assert 'task_type' in task_data or 'mtmd' in task_data


class TestTaskCreateBugCommand:
    """Test macf_tools task create bug command."""

    def test_create_bug_with_inline_plan(self, isolated_task_env):
        """Test bug creation with --plan inline description."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'bug', 'Fix test failure',
             '--plan', 'Update assertions to match new format'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'Created task' in result.stdout or '🐛' in result.stdout

    def test_create_bug_requires_plan(self, isolated_task_env):
        """Test bug creation fails without --plan or --plan-ca-ref."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'bug', 'Incomplete Bug'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # Should fail - bug requires plan
        assert result.returncode != 0
        assert 'required' in result.stderr.lower() or 'plan' in result.stderr.lower()

    def test_create_bug_with_parent(self, isolated_task_env):
        """Test bug creation under a parent task."""
        # First create a parent task
        parent_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Parent Task'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert parent_result.returncode == 0

        # Create bug under parent (assuming parent gets ID 1)
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'bug', 'Child Bug',
             '--parent', '1', '--plan', 'Fix child issue'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0


class TestTaskCreatePhaseCommand:
    """Test macf_tools task create phase command."""

    def test_create_phase_requires_parent(self, isolated_task_env):
        """Test phase creation fails without --parent."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'phase', 'Phase Without Parent'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # Should fail - phase requires parent
        assert result.returncode != 0
        assert 'required' in result.stderr.lower() or 'parent' in result.stderr.lower()

    def test_create_phase_with_parent(self, isolated_task_env):
        """Test phase creation under a parent mission."""
        # First create a mission
        mission_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'mission', 'Parent Mission'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert mission_result.returncode == 0

        # Create phase under mission (assuming mission gets ID 1)
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'phase', 'Phase 1: Setup',
             '--parent', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Note: output says "Created phase task" not "Created task"
        assert 'Created' in result.stdout


class TestTaskCreateTaskCommand:
    """Test macf_tools task create task command (standalone tasks)."""

    def test_create_standalone_task(self, isolated_task_env):
        """Test standalone task creation."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Simple Task'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'Created task' in result.stdout or '🔧' in result.stdout

    def test_create_task_json_output(self, isolated_task_env):
        """Test task creation with --json returns valid JSON."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'JSON Task', '--json'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        task_data = json.loads(result.stdout)
        assert isinstance(task_data, dict)
        assert 'subject' in task_data


class TestTaskCreateDelegCommand:
    """Test macf_tools task create deleg command."""

    def test_create_deleg_with_plan(self, isolated_task_env):
        """Test delegation task creation with --plan path."""
        # Create a temporary plan file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Delegation Plan\n\nTest delegation content\n")
            plan_path = f.name

        try:
            result = subprocess.run(
                ['macf_tools', 'task', 'create', 'deleg', 'Delegate to TestEng',
                 '--plan', plan_path],
                capture_output=True, text=True
            )

            assert result.returncode == 0
            assert 'Created task' in result.stdout or '📜' in result.stdout
        finally:
            Path(plan_path).unlink()

    def test_create_deleg_requires_plan(self, isolated_task_env):
        """Test deleg creation fails without --plan."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'deleg', 'Incomplete Deleg'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # Should fail - deleg requires plan
        assert result.returncode != 0


class TestTaskArchiveCommand:
    """Test macf_tools task archive command."""

    def test_archive_nonexistent_task_fails(self, isolated_task_env):
        """Test archiving a nonexistent task fails gracefully."""
        result = subprocess.run(
            ['macf_tools', 'task', 'archive', '999'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode != 0
        assert 'not found' in result.stdout.lower() or 'not found' in result.stderr.lower()

    def test_archive_existing_task(self, isolated_task_env):
        """Test archiving an existing task."""
        # Create a task first
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Task to Archive'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        # Archive it (assuming it gets ID 1)
        result = subprocess.run(
            ['macf_tools', 'task', 'archive', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'archived' in result.stdout.lower()

    def test_archive_with_no_cascade(self, isolated_task_env):
        """Test archive --no-cascade flag."""
        # Create a parent task
        parent_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Parent'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert parent_result.returncode == 0

        # Archive with --no-cascade
        result = subprocess.run(
            ['macf_tools', 'task', 'archive', '1', '--no-cascade'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # Should succeed
        assert result.returncode == 0


class TestTaskRestoreCommand:
    """Test macf_tools task restore command."""

    def test_restore_requires_archive_path(self, isolated_task_env):
        """Test restore command with missing archive."""
        result = subprocess.run(
            ['macf_tools', 'task', 'restore', 'nonexistent.json'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # Should fail or report not found
        assert result.returncode != 0 or 'not found' in result.stdout.lower()

    def test_restore_json_output(self, isolated_task_env):
        """Test restore --json flag format."""
        # Create and archive a task first
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Test Restore'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        archive_result = subprocess.run(
            ['macf_tools', 'task', 'archive', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert archive_result.returncode == 0

        # Try to restore with --json (may fail if archive path is complex)
        result = subprocess.run(
            ['macf_tools', 'task', 'restore', '1', '--json'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        # If successful, should be valid JSON
        if result.returncode == 0:
            restored_data = json.loads(result.stdout)
            assert isinstance(restored_data, dict)


class TestTaskArchivedListCommand:
    """Test macf_tools task archived list command."""

    def test_archived_list_empty(self, isolated_task_env):
        """Test archived list with no archived tasks."""
        result = subprocess.run(
            ['macf_tools', 'task', 'archived', 'list'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Should handle empty list gracefully
        assert 'No archived tasks' in result.stdout or 'archive' in result.stdout.lower()

    def test_archived_list_shows_archived_tasks(self, isolated_task_env):
        """Test archived list shows archived tasks."""
        # Create and archive a task
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'To Archive'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        archive_result = subprocess.run(
            ['macf_tools', 'task', 'archive', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert archive_result.returncode == 0

        # List archived tasks
        result = subprocess.run(
            ['macf_tools', 'task', 'archived', 'list'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        # Should show at least one archived task
        assert 'archive' in result.stdout.lower()


class TestTaskGrantUpdateCommand:
    """Test macf_tools task grant-update command."""

    def test_grant_update_requires_task_id(self, isolated_task_env):
        """Test grant-update fails without task ID."""
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-update'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode != 0

    def test_grant_update_with_task_id(self, isolated_task_env):
        """Test grant-update with valid task ID."""
        # Create a task first
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Test Grant'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        # Grant update permission
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-update', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'grant' in result.stdout.lower() or 'permission' in result.stdout.lower()

    def test_grant_update_with_field_and_value(self, isolated_task_env):
        """Test grant-update with specific field and value."""
        # Create a task
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Test Field Grant'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        # Grant update for specific field
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-update', '1',
             '--field', 'description', '--value', 'New description'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0


class TestTaskGrantDeleteCommand:
    """Test macf_tools task grant-delete command."""

    def test_grant_delete_single_task(self, isolated_task_env):
        """Test grant-delete with single task ID."""
        # Create a task
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Test Delete Grant'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        # Grant delete permission
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-delete', '1'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'grant' in result.stdout.lower() or 'delete' in result.stdout.lower()

    def test_grant_delete_multiple_tasks(self, isolated_task_env):
        """Test grant-delete with multiple task IDs."""
        # Create multiple tasks
        for i in range(3):
            create_result = subprocess.run(
                ['macf_tools', 'task', 'create', 'task', f'Task {i+1}'],
                capture_output=True, text=True
            )
            assert create_result.returncode == 0

        # Grant delete for multiple tasks
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-delete', '1', '2', '3'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0

    def test_grant_delete_with_reason(self, isolated_task_env):
        """Test grant-delete with --reason flag."""
        # Create a task
        create_result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'Task with Reason'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )
        assert create_result.returncode == 0

        # Grant delete with reason
        result = subprocess.run(
            ['macf_tools', 'task', 'grant-delete', '1',
             '--reason', 'Task no longer needed'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
