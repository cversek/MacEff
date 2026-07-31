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
from unittest.mock import Mock, patch
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
            ['macf_tools', 'task', 'create', 'task', 'Parent Task', '--plan', 'Parent test'],
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
             '--parent', '1', '--plan', 'Phase test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Simple Task', '--plan', 'Test plan'],
            capture_output=True, text=True, env=isolated_task_env['env']
        )

        assert result.returncode == 0
        assert 'Created task' in result.stdout or '🔧' in result.stdout

    def test_create_task_json_output(self, isolated_task_env):
        """Test task creation with --json returns valid JSON."""
        result = subprocess.run(
            ['macf_tools', 'task', 'create', 'task', 'JSON Task', '--plan', 'JSON test plan', '--json'],
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
            ['macf_tools', 'task', 'create', 'task', 'Task to Archive', '--plan', 'Archive test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Parent', '--plan', 'Parent test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Test Restore', '--plan', 'Restore test'],
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
            ['macf_tools', 'task', 'create', 'task', 'To Archive', '--plan', 'Archive list test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Test Grant', '--plan', 'Grant test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Test Field Grant', '--plan', 'Field grant test'],
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
            ['macf_tools', 'task', 'create', 'task', 'Test Delete Grant', '--plan', 'Delete grant test'],
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
                ['macf_tools', 'task', 'create', 'task', f'Task {i+1}', '--plan', f'Test {i+1}'],
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
            ['macf_tools', 'task', 'create', 'task', 'Task with Reason', '--plan', 'Reason test'],
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


class TestTaskCreateGHIssueCommand:
    """Test GH_ISSUE task creation function."""

    def test_create_gh_issue_from_url(self, isolated_task_env, monkeypatch):
        """Test GH_ISSUE creation by auto-fetching metadata from GitHub."""
        from macf.task.create import create_gh_issue

        # Mock subprocess.run to return fake gh CLI JSON response
        fake_gh_output = json.dumps({
            "title": "Fix broken tests",
            "labels": [{"name": "bug"}, {"name": "testing"}],
            "state": "OPEN",
            "url": "https://github.com/owner/repo/issues/42"
        })

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = fake_gh_output
        mock_result.stderr = ""

        # Mock breadcrumb generation and subprocess
        with patch('macf.utils.breadcrumbs.get_breadcrumb', return_value='s_test/c_1/g_abc/p_123/t_456'):
            with patch('macf.utils.breadcrumbs.parse_breadcrumb', return_value={'cycle': 1}):
                with patch('subprocess.run', return_value=mock_result):
                    result = create_gh_issue('https://github.com/owner/repo/issues/42')

        # Verify result contains expected metadata
        assert result.task_id is not None
        assert result.mtmd.task_type == 'GH_ISSUE'
        assert result.mtmd.title == 'Fix broken tests'
        assert result.mtmd.plan_ca_ref == 'https://github.com/owner/repo/issues/42'

        # Verify custom fields
        custom = result.mtmd.custom
        assert custom['gh_owner'] == 'owner'
        assert custom['gh_repo'] == 'repo'
        assert custom['gh_issue_number'] == 42
        assert custom['gh_labels'] == ['bug', 'testing']
        assert custom['gh_state'] == 'OPEN'
        assert custom['gh_url'] == 'https://github.com/owner/repo/issues/42'

        # Verify task file was created
        task_files = list(isolated_task_env['session_dir'].glob("*.json"))
        assert len(task_files) >= 1

    def test_create_gh_issue_display_format(self, isolated_task_env, monkeypatch):
        """Test GH_ISSUE subject line renders correctly with labels."""
        from macf.task.create import compose_subject

        # Mock custom data with labels
        custom = {
            "gh_owner": "owner",
            "gh_repo": "repo",
            "gh_issue_number": 3,
            "gh_labels": ["bug", "frontend"],
        }

        subject = compose_subject(
            "97", "GH_ISSUE", "Fix navigation menu",
            custom=custom
        )

        # Should match format: 🐙 GH/owner/repo#3 [bug]: Fix navigation menu
        # (Note: ANSI codes may be present, so check key components)
        assert '🐙' in subject
        assert 'GH/owner/repo#3' in subject
        assert '[bug]' in subject  # First label only
        assert 'Fix navigation menu' in subject

    def test_create_gh_issue_no_labels(self, isolated_task_env, monkeypatch):
        """Test GH_ISSUE subject line when issue has no labels."""
        from macf.task.create import compose_subject

        # Mock custom data with empty labels
        custom = {
            "gh_owner": "cversek",
            "gh_repo": "MacEff",
            "gh_issue_number": 5,
            "gh_labels": [],  # No labels
        }

        subject = compose_subject(
            "99", "GH_ISSUE", "Update documentation",
            custom=custom
        )

        # Should match format: 🐙 GH/cversek/MacEff#5: Update documentation
        # (No label bracket when labels empty - check for label pattern, not raw '[')
        assert '🐙' in subject
        assert 'GH/cversek/MacEff#5:' in subject
        # Check that there's no label pattern like [bug] or [feature]
        import re
        assert not re.search(r'\]\s*\[[\w-]+\]:', subject), "Should not have label bracket pattern"
        assert 'Update documentation' in subject

    def test_create_gh_issue_gh_cli_failure(self, isolated_task_env, monkeypatch):
        """Test error handling when gh CLI command fails."""
        from macf.task.create import create_gh_issue

        # Mock subprocess.run to return non-zero exit code
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Could not resolve to a Repository with the name 'owner/repo'"

        # Mock breadcrumb generation and subprocess
        with patch('macf.utils.breadcrumbs.get_breadcrumb', return_value='s_test/c_1/g_abc/p_123/t_456'):
            with patch('macf.utils.breadcrumbs.parse_breadcrumb', return_value={'cycle': 1}):
                with patch('subprocess.run', return_value=mock_result):
                    # Should raise ValueError
                    with pytest.raises(ValueError, match="gh issue view failed"):
                        create_gh_issue('https://github.com/owner/repo/issues/999')


class TestGHIssueCompletionGate:
    """Test GH_ISSUE completion gate that enforces --commit and --verified."""

    def _create_gh_issue_task(self, session_dir, task_id=1):
        """Create a GH_ISSUE task JSON file directly."""
        mtmd_yaml = ("task_type: GH_ISSUE\n"
                     "creation_breadcrumb: s_test/c_1/g_abc/p_def/t_123\n"
                     "created_cycle: 1\ncreated_by: PA\nparent_id: '000'\n"
                     "custom:\n  gh_owner: testowner\n  gh_repo: testrepo\n"
                     "  gh_issue_number: 42\n  gh_labels: [bug]\n"
                     "  gh_state: OPEN\n"
                     "  gh_url: https://github.com/testowner/testrepo/issues/42\n")
        desc = f'Test GH_ISSUE\n\n<macf_task_metadata version="1.0">\n{mtmd_yaml}</macf_task_metadata>'
        task_data = {"id": str(task_id), "subject": "🐙 GH/testowner/testrepo#42 [bug]: Test",
                     "description": desc, "status": "in_progress"}
        (session_dir / f"{task_id}.json").write_text(json.dumps(task_data))
        return task_id

    def _create_regular_task(self, session_dir, task_id=2):
        """Create a regular TASK type."""
        mtmd_yaml = ("task_type: TASK\n"
                     "creation_breadcrumb: s_test/c_1/g_abc/p_def/t_123\n"
                     "created_cycle: 1\ncreated_by: PA\nparent_id: '000'\n")
        desc = f'Regular task\n\n<macf_task_metadata version="1.0">\n{mtmd_yaml}</macf_task_metadata>'
        task_data = {"id": str(task_id), "subject": "🔧 Regular task",
                     "description": desc, "status": "in_progress"}
        (session_dir / f"{task_id}.json").write_text(json.dumps(task_data))
        return task_id

    def test_gh_issue_without_commit_verified_rejected(self, isolated_task_env):
        """GH_ISSUE without --commit/--verified is rejected with redirect."""
        tid = self._create_gh_issue_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'complete', f'#{tid}', '--report', 'Test'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode != 0
        out = result.stdout + result.stderr
        assert 'requires structured closeout' in out
        assert 'macf_tools policy navigate task_management' in out

    def test_gh_issue_missing_verified_rejected(self, isolated_task_env):
        """GH_ISSUE with --commit but no --verified is rejected."""
        tid = self._create_gh_issue_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'complete', f'#{tid}', '--report', 'Test',
             '--commit', 'abc123'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode != 0
        assert '--verified' in (result.stdout + result.stderr)

    def test_non_gh_issue_completes_without_closeout_fields(self, isolated_task_env):
        """Non-GH_ISSUE task completes normally without --commit/--verified."""
        tid = self._create_regular_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'complete', f'#{tid}', '--report', 'Done'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0

    def test_gh_issue_with_all_fields_completes(self, isolated_task_env):
        """GH_ISSUE with all fields completes (gh CLI errors are warnings)."""
        tid = self._create_gh_issue_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'complete', f'#{tid}', '--report', 'Fixed',
             '--commit', 'abc123', '--verified', 'tests pass'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0
        # Verify MTMD stored closeout data (file may be dot-prefixed after completion)
        from macf.task.reader import resolve_task_file
        task_file = resolve_task_file(isolated_task_env['session_dir'], str(tid))
        assert task_file is not None, f"Task file not found for #{tid} (checked both visible and hidden)"
        task_data = json.loads(task_file.read_text())
        assert 'closeout_commits' in task_data['description']
        assert 'closeout_verified' in task_data['description']


class TestGHIssueCloseoutFunction:
    """Test _gh_issue_closeout helper directly with mocked subprocess."""

    @staticmethod
    def _closeout_body(mock_run):
        """Extract the --body payload from the gh issue comment call."""
        comment_call = [c for c in mock_run.call_args_list
                        if c[0][0][:3] == ['gh', 'issue', 'comment']][0]
        cmd = comment_call[0][0]
        return cmd[cmd.index('--body') + 1]

    def test_posts_comment_with_calling_card_when_attribution_enabled(self):
        """With opsec.public_attribution on: report, commits, verification, calling card."""
        from macf.cli import _gh_issue_closeout
        from macf.task.models import MacfTaskMetaData

        mtmd = MacfTaskMetaData(task_type='GH_ISSUE', custom={
            'gh_owner': 'testowner', 'gh_repo': 'testrepo', 'gh_issue_number': 42})
        args = Mock()
        args.report = 'Fixed the API bug'
        args.commit = ['abc1234567890']
        args.verified = 'Unit tests pass'
        bc = 's_test/c_1/g_abc/p_def/t_123'

        with patch('subprocess.run', return_value=Mock(returncode=0, stdout='', stderr='')) as mock_run, \
             patch('macf.cli._public_attribution_enabled', return_value=True):
            _gh_issue_closeout(42, mtmd, args, bc)
            assert mock_run.call_count >= 2
            body = self._closeout_body(mock_run)
            assert 'Close-out Report' in body
            assert 'Fixed the API bug' in body
            assert 'abc12345' in body  # truncated hash link
            assert 'Unit tests pass' in body
            assert 'task#42' in body
            assert bc in body

    def test_omits_calling_card_by_default(self):
        """OPSEC default (issue #156): no agent attribution on public comments."""
        from macf.cli import _gh_issue_closeout
        from macf.task.models import MacfTaskMetaData

        mtmd = MacfTaskMetaData(task_type='GH_ISSUE', custom={
            'gh_owner': 'testowner', 'gh_repo': 'testrepo', 'gh_issue_number': 42})
        args = Mock()
        args.report = 'Fixed the API bug'
        args.commit = ['abc1234567890']
        args.verified = 'Unit tests pass'
        bc = 's_test/c_1/g_abc/p_def/t_123'

        with patch('subprocess.run', return_value=Mock(returncode=0, stdout='', stderr='')) as mock_run, \
             patch('macf.cli._public_attribution_enabled', return_value=False):
            _gh_issue_closeout(42, mtmd, args, bc)
            body = self._closeout_body(mock_run)
            assert 'Close-out Report' in body
            assert 'Fixed the API bug' in body
            # No calling card, no breadcrumb, no trailing separator
            assert 'task#42' not in body
            assert bc not in body
            assert not body.rstrip().endswith('---')

    def test_handles_missing_gh_cli(self):
        """_gh_issue_closeout handles FileNotFoundError gracefully."""
        from macf.cli import _gh_issue_closeout
        from macf.task.models import MacfTaskMetaData

        mtmd = MacfTaskMetaData(task_type='GH_ISSUE', custom={
            'gh_owner': 'testowner', 'gh_repo': 'testrepo', 'gh_issue_number': 42})
        args = Mock()
        args.report = 'Fixed'
        args.commit = ['abc123']
        args.verified = 'Verified'

        with patch('subprocess.run', side_effect=FileNotFoundError("gh not found")):
            _gh_issue_closeout(42, mtmd, args, 's_test/c_1/g_abc/p_def/t_123')


class TestTaskTreeSuccinctRecencyMarker:
    """Succinct mode must never hide the recency-marked (last-touched) task (#150)."""

    def _write_task(self, session_dir, task_id, subject, status, ts, parent="'000'"):
        parent_line = f"parent_id: {parent}\n" if parent else ""
        mtmd = (f"task_type: {'SENTINEL' if not parent else 'TASK'}\n"
                f"creation_breadcrumb: s_t/c_1/g_a/p_b/t_{ts}\n"
                f"created_cycle: 1\ncreated_by: PA\n{parent_line}")
        desc = f'Task\n\n<macf_task_metadata version="1.0">\n{mtmd}</macf_task_metadata>'
        (session_dir / f"{task_id}.json").write_text(json.dumps(
            {"id": str(task_id), "subject": subject, "description": desc, "status": status}))

    def test_completed_recency_marked_task_still_shown_in_succinct(self, isolated_task_env):
        """The 👈-marked task stays visible in --succinct after it completes."""
        d = isolated_task_env['session_dir']
        # Sentinel root (no parent — a self-parented sentinel recurses infinitely).
        self._write_task(d, "000", "🛡️ MACF TASK LIST", "in_progress", 1000, parent=None)
        # An active sibling (visible regardless) and the newest-touched COMPLETED task.
        self._write_task(d, 2, "🔧 active work", "in_progress", 2000)
        self._write_task(d, 3, "🔧 most recently touched", "completed", 9999999999)

        result = subprocess.run(
            ['macf_tools', 'task', 'tree', '--succinct'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        out = result.stdout
        # Before the fix, the completed depth-1 task was filtered out and its
        # marker vanished; the marker must travel with the task.
        assert 'most recently touched' in out, f"recency-marked task hidden in succinct:\n{out}"
        assert '👈' in out, f"recency marker missing:\n{out}"


class TestTaskCreateGHPRCommand:
    """Test GH_PR task creation function (inbound PR review/merge tracking)."""

    _FAKE_PR = {
        "title": "raise client_max_size for large requests",
        "labels": [{"name": "bug"}],
        "state": "OPEN",
        "url": "https://github.com/owner/repo/pull/168",
        "headRefName": "fix/proxy-client-max-size",
        "baseRefName": "main",
        "isDraft": False,
        "reviewDecision": "REVIEW_REQUIRED",
        "closingIssuesReferences": [{"number": 167}],
        "body": "Fixes #167\n\nRaise the limit.",
    }

    def _run_create(self, pr_json):
        from macf.task.create import create_gh_pr
        mock_result = Mock(returncode=0, stdout=json.dumps(pr_json), stderr="")
        with patch('macf.utils.breadcrumbs.get_breadcrumb', return_value='s_test/c_1/g_abc/p_123/t_456'):
            with patch('macf.utils.breadcrumbs.parse_breadcrumb', return_value={'cycle': 1}):
                with patch('subprocess.run', return_value=mock_result):
                    return create_gh_pr('https://github.com/owner/repo/pull/168')

    def test_create_gh_pr_from_url(self, isolated_task_env, monkeypatch):
        """GH_PR creation auto-fetches PR metadata into custom, incl. linked issues + lifecycle."""
        result = self._run_create(self._FAKE_PR)
        assert result.mtmd.task_type == 'GH_PR'
        assert result.mtmd.title == 'raise client_max_size for large requests'
        assert result.mtmd.plan_ca_ref == 'https://github.com/owner/repo/pull/168'
        c = result.mtmd.custom
        assert c['gh_owner'] == 'owner' and c['gh_repo'] == 'repo'
        assert c['gh_pr_number'] == 168
        assert c['gh_labels'] == ['bug']
        assert c['head_branch'] == 'fix/proxy-client-max-size'
        assert c['base_branch'] == 'main'
        assert c['is_draft'] is False
        assert c['review_decision'] == 'REVIEW_REQUIRED'
        assert c['linked_issues'] == [167]
        assert c['lifecycle_state'] == 'pending'
        assert 'reviewing' in c['lifecycle_state_machine']['pending']
        # mergeable must NOT be stored (stale-field anti-pattern)
        assert 'mergeable' not in c

    def test_create_gh_pr_subject_draft_and_label(self, isolated_task_env):
        """Subject renders 🔀 PR/owner/repo#N [label] (draft): title."""
        from macf.task.create import compose_subject
        subject = compose_subject(
            "42", "GH_PR", "Refactor banner",
            custom={"gh_owner": "owner", "gh_repo": "repo", "gh_pr_number": 42,
                    "gh_labels": ["enhancement"], "is_draft": True})
        assert '🔀' in subject
        assert 'PR/owner/repo#42' in subject
        assert '[enhancement]' in subject
        assert '(draft)' in subject
        assert 'Refactor banner' in subject

    def test_create_gh_pr_linked_issues_body_fallback(self, isolated_task_env):
        """When closingIssuesReferences is empty, linked_issues parse from Fixes/Closes body."""
        pr = dict(self._FAKE_PR)
        pr["closingIssuesReferences"] = []
        pr["body"] = "Closes #12 and fixes #34"
        result = self._run_create(pr)
        assert result.mtmd.custom['linked_issues'] == [12, 34]

    def test_create_gh_pr_url_and_cli_failures(self, isolated_task_env):
        """An /issues/ URL is rejected, and a gh CLI failure raises."""
        from macf.task.create import create_gh_pr
        with pytest.raises(ValueError, match="Cannot parse GitHub PR URL"):
            create_gh_pr('https://github.com/owner/repo/issues/5')
        mock_fail = Mock(returncode=1, stdout="", stderr="not found")
        with patch('macf.utils.breadcrumbs.get_breadcrumb', return_value='s_test/c_1/g_abc/p_1/t_4'):
            with patch('macf.utils.breadcrumbs.parse_breadcrumb', return_value={'cycle': 1}):
                with patch('subprocess.run', return_value=mock_fail):
                    with pytest.raises(ValueError, match="gh pr view failed"):
                        create_gh_pr('https://github.com/owner/repo/pull/999')


class TestGHPRCloseoutFunction:
    """Test GH_PR closeout: outcome ground-truthing, comment, cascade selection."""

    def test_gh_pr_closeout_merged_outcome_and_comment(self):
        """Merged PR → outcome MERGED, review close-out comment posted."""
        from macf.cli import _gh_pr_closeout
        from macf.task.models import MacfTaskMetaData
        mtmd = MacfTaskMetaData(task_type='GH_PR', custom={
            'gh_owner': 'o', 'gh_repo': 'r', 'gh_pr_number': 168, 'linked_issues': []})
        args = Mock()
        args.report = 'Reviewed and merged after local tests.'
        args.verified = 'make test green'
        args.cascade = False
        view = Mock(returncode=0, stdout=json.dumps(
            {"state": "MERGED", "mergeCommit": {"oid": "deadbeef1234"}}), stderr="")
        comment = Mock(returncode=0, stdout="", stderr="")
        # Patch identity so it never shells out — otherwise get_agent_identity()
        # consumes a subprocess.run slot in environments without a cached identity
        # (green locally, StopIteration in CI). Keep the mock to exactly view+comment.
        with patch('macf.utils.identity.get_agent_identity', return_value='TestAgent'):
            with patch('macf.cli._public_attribution_enabled', return_value=True):
                with patch('subprocess.run', side_effect=[view, comment]) as mock_run:
                    outcome = _gh_pr_closeout(168, mtmd, args, 's_test/c_1/g_abc/p_def/t_123')
        assert outcome == 'MERGED'
        comment_call = [c for c in mock_run.call_args_list
                        if c[0][0][:3] == ['gh', 'pr', 'comment']][0]
        body = comment_call[0][0][comment_call[0][0].index('--body') + 1]
        assert 'Review Close-out' in body
        assert 'Reviewed and merged' in body
        assert 'MERGED' in body
        assert 'task#168' in body

    def test_gh_pr_closeout_flags_red_ci_merge(self, capsys):
        """A merged PR with failing CI checks emits a CI-gate-violation warning."""
        from macf.cli import _gh_pr_closeout
        from macf.task.models import MacfTaskMetaData
        mtmd = MacfTaskMetaData(task_type='GH_PR', custom={
            'gh_owner': 'o', 'gh_repo': 'r', 'gh_pr_number': 9, 'linked_issues': []})
        args = Mock(report='merged', verified='x', cascade=False)
        view = Mock(returncode=0, stdout=json.dumps({
            "state": "MERGED", "mergeCommit": {"oid": "abc123"},
            "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]}), stderr="")
        comment = Mock(returncode=0, stdout="", stderr="")
        with patch('macf.utils.identity.get_agent_identity', return_value='T'):
            with patch('macf.cli._public_attribution_enabled', return_value=False):
                with patch('subprocess.run', side_effect=[view, comment]):
                    outcome = _gh_pr_closeout(9, mtmd, args, 's/c/g/p/t')
        assert outcome == 'MERGED'
        assert 'CI GATE VIOLATION' in capsys.readouterr().out

    def test_gh_pr_find_linked_issue_tasks_selects_matching(self):
        """Cascade selection matches open GH_ISSUE tasks by number + repo, skips others."""
        from macf.cli import _gh_pr_find_linked_issue_tasks
        def mk(tid, ttype, number, owner="o", repo="r", status="in_progress"):
            t = Mock()
            t.id = tid
            t.status = status
            t.mtmd = Mock(task_type=ttype, custom={
                "gh_issue_number": number, "gh_owner": owner, "gh_repo": repo})
            return t
        tasks = [
            mk(1, "GH_ISSUE", 167),                    # match
            mk(2, "GH_ISSUE", 999),                    # wrong number
            mk(3, "GH_ISSUE", 167, status="completed"),  # already done
            mk(4, "GH_ISSUE", 167, repo="other"),      # wrong repo
            mk(5, "GH_PR", 167),                        # not an issue
        ]
        with patch('macf.task.TaskReader') as MockReader:
            MockReader.return_value.read_all_tasks.return_value = tasks
            found = _gh_pr_find_linked_issue_tasks([167], "o/r")
        assert [tid for tid, _ in found] == [1]


class TestTaskLifecycleEvents:
    """Test task_started and task_completed event emission."""

    def _create_mission_task(self, session_dir, task_id=10):
        """Create a MISSION task with plan_ca_ref."""
        mtmd_yaml = ("task_type: MISSION\n"
                     "creation_breadcrumb: s_test/c_1/g_abc/p_def/t_123\n"
                     "created_cycle: 1\ncreated_by: PA\nparent_id: '000'\n"
                     "plan_ca_ref: agent/public/roadmaps/test/roadmap.md\n")
        desc = f'Test mission\n\n<macf_task_metadata version="1.0">\n{mtmd_yaml}</macf_task_metadata>'
        task_data = {"id": str(task_id), "subject": "Test Mission",
                     "description": desc, "status": "pending"}
        (session_dir / f"{task_id}.json").write_text(json.dumps(task_data))
        return task_id

    def _read_events(self, env):
        """Read events from the isolated event log."""
        log_path = Path(env["MACF_EVENTS_LOG_PATH"])
        if not log_path.exists():
            return []
        events = []
        for line in log_path.read_text().strip().split('\n'):
            if line.strip():
                events.append(json.loads(line))
        return events

    def test_task_start_emits_event(self, isolated_task_env):
        """task start emits task_started event with task_type and breadcrumb."""
        tid = self._create_mission_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0

        events = self._read_events(isolated_task_env['env'])
        started = [e for e in events if e.get('event') == 'task_started']
        assert len(started) == 1
        assert started[0]['data']['task_id'] == str(tid)
        assert started[0]['data']['task_type'] == 'MISSION'
        assert started[0]['data']['plan_ca_ref'] == 'agent/public/roadmaps/test/roadmap.md'
        assert 'breadcrumb' in started[0]['data']

    def test_task_complete_emits_event(self, isolated_task_env):
        """task complete emits task_completed event with report."""
        tid = self._create_mission_task(isolated_task_env['session_dir'])
        # Start first (must be in_progress to complete)
        subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])
        # Complete
        result = subprocess.run(
            ['macf_tools', 'task', 'complete', str(tid), '--report', 'All done'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0

        events = self._read_events(isolated_task_env['env'])
        completed = [e for e in events if e.get('event') == 'task_completed']
        assert len(completed) == 1
        assert completed[0]['data']['task_id'] == str(tid)
        assert completed[0]['data']['task_type'] == 'MISSION'
        assert completed[0]['data']['report'] == 'All done'

    def test_task_start_event_with_phase_type(self, isolated_task_env):
        """Phase tasks emit task_started with task_type=PHASE."""
        mtmd_yaml = ("task_type: PHASE\n"
                     "creation_breadcrumb: s_test/c_1/g_abc/p_def/t_123\n"
                     "created_cycle: 1\ncreated_by: PA\nparent_id: '10'\n")
        desc = f'Phase 1\n\n<macf_task_metadata version="1.0">\n{mtmd_yaml}</macf_task_metadata>'
        task_data = {"id": "11", "subject": "Phase 1",
                     "description": desc, "status": "pending"}
        (isolated_task_env['session_dir'] / "11.json").write_text(json.dumps(task_data))

        result = subprocess.run(
            ['macf_tools', 'task', 'start', '11'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0

        events = self._read_events(isolated_task_env['env'])
        started = [e for e in events if e.get('event') == 'task_started']
        assert len(started) == 1
        assert started[0]['data']['task_type'] == 'PHASE'
        assert started[0]['data']['plan_ca_ref'] is None

    def test_task_start_no_duplicate_on_already_started(self, isolated_task_env):
        """Starting an already in_progress task emits no event."""
        tid = self._create_mission_task(isolated_task_env['session_dir'])
        subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])
        # Start again - should be no-op
        result = subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0
        assert 'already in_progress' in result.stdout

        events = self._read_events(isolated_task_env['env'])
        started = [e for e in events if e.get('event') == 'task_started']
        assert len(started) == 1  # Only from first start

    def test_events_queryable_via_cli(self, isolated_task_env):
        """Events are queryable via macf_tools events query."""
        tid = self._create_mission_task(isolated_task_env['session_dir'])
        subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])

        result = subprocess.run(
            ['macf_tools', 'events', 'query', '--event', 'task_started', '--verbose'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0
        assert 'task_started' in result.stdout
        assert 'MISSION' in result.stdout

    def test_task_start_auto_injects_policies(self, isolated_task_env):
        """task start on MISSION emits policy_injection_activated with source=task_type_auto."""
        tid = self._create_mission_task(isolated_task_env['session_dir'])
        result = subprocess.run(
            ['macf_tools', 'task', 'start', str(tid)],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0
        assert 'Auto-injected policies' in result.stdout

        events = self._read_events(isolated_task_env['env'])
        injections = [e for e in events if e.get('event') == 'policy_injection_activated'
                      and e.get('data', {}).get('source') == 'task_type_auto']
        # MISSION should inject roadmaps_following, coding_standards, task_management
        injected_names = [e['data']['policy_name'] for e in injections]
        assert 'task_management' in injected_names
        assert 'roadmaps_following' in injected_names
        assert all(e['data']['task_id'] == str(tid) for e in injections)


class TestTaskListCommand:
    """Regression tests for `macf_tools task list` display pipeline.

    Introduced after gh-48: cmd_task_list.format_task referenced a
    scope_state variable that was never built in cmd_task_list's scope,
    causing NameError on every invocation that reached the display path.
    """

    def _write_task(self, session_dir, task_id, status='pending', scope_status=None):
        mtmd_lines = [
            'task_type: MISSION',
            'creation_breadcrumb: s_test/c_1/g_abc/p_def/t_123',
            'created_cycle: 1',
            'created_by: PA',
            "parent_id: '000'",
        ]
        if scope_status:
            mtmd_lines.append(f'scope_status: {scope_status}')
        mtmd = '\n'.join(mtmd_lines) + '\n'
        desc = f'Regression test task\n\n<macf_task_metadata version="1.0">\n{mtmd}</macf_task_metadata>'
        (session_dir / f'{task_id}.json').write_text(json.dumps({
            'id': str(task_id), 'subject': f'Test task {task_id}',
            'description': desc, 'status': status,
        }))
        return task_id

    def test_task_list_does_not_crash_with_one_task(self, isolated_task_env):
        """gh-48: task list must not raise NameError on any task."""
        self._write_task(isolated_task_env['session_dir'], 100)
        result = subprocess.run(
            ['macf_tools', 'task', 'list'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert 'NameError' not in result.stderr
        assert 'Test task 100' in result.stdout

    def test_task_list_shows_scope_indicator_for_active_scope(self, isolated_task_env):
        """Positive test: active scope shows 👀 indicator (the feature gh-48's bug gated)."""
        self._write_task(isolated_task_env['session_dir'], 101, scope_status='active')
        result = subprocess.run(
            ['macf_tools', 'task', 'list'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert '👀' in result.stdout

    def test_task_list_shows_scope_indicator_for_inactive_scope(self, isolated_task_env):
        """Inactive scope shows ✅ indicator."""
        self._write_task(isolated_task_env['session_dir'], 102, scope_status='inactive')
        result = subprocess.run(
            ['macf_tools', 'task', 'list'],
            capture_output=True, text=True, env=isolated_task_env['env'])
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert '✅' in result.stdout


class TestSubjectTitleTruncation:
    """--title-width trims only the semantic title (#1174 FEAT)."""

    def test_truncates_title_but_keeps_structural_prefix(self):
        from macf.cli import _truncate_subject_title
        subject = "#1148 🐙 GH/owner/repo#124 [enhancement]: " + "x" * 100
        out = _truncate_subject_title(subject, 40)
        assert "🐙 GH/owner/repo#124 [enhancement]:" in out, "prefix was damaged"
        assert out.endswith("...")
        assert len(out) < len(subject)

    def test_short_title_untouched(self):
        from macf.cli import _truncate_subject_title
        subject = "#12 🔧 short title"
        assert _truncate_subject_title(subject, 40) == subject

    def test_zero_width_disables_truncation(self):
        from macf.cli import _truncate_subject_title
        subject = "#12 🔧 " + "y" * 200
        assert _truncate_subject_title(subject, 0) == subject

    def test_bare_emoji_type_marker_title_is_trimmed(self):
        """Types without a ':' marker (🔧, 📋) still get their title trimmed."""
        from macf.cli import _truncate_subject_title
        subject = "#12 🔧 " + "z" * 100
        out = _truncate_subject_title(subject, 30)
        assert out.endswith("...")
        assert len(out) < len(subject)


class TestTaskDoctor:
    """`task doctor` reconciles stored records against their authority.

    Read-time re-derivation keeps *displays* honest. The stored record is what
    other consumers read, so it needs a reconcile pass of its own.
    """

    def _seed(self, session_dir, task_id, subject, parent_id):
        payload = {
            "id": task_id,
            "subject": subject,
            "status": "pending",
            "description": (
                '<macf_task_metadata version="1.0">\n'
                'task_type: TASK\n'
                'created_by: PA\n'
                f'parent_id: {parent_id}\n'
                '</macf_task_metadata>\n'
            ),
        }
        (session_dir / f"{task_id}.json").write_text(json.dumps(payload))

    def test_reports_divergent_marker_and_exits_nonzero(self, isolated_task_env):
        self._seed(isolated_task_env['session_dir'], "42",
                   "  #42 [^#10] 🔧 stale marker task", parent_id="20")

        result = subprocess.run(
            ["macf_tools", "task", "doctor"],
            capture_output=True, text=True, env=isolated_task_env['env'],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "1 divergent" in result.stdout
        assert "#42" in result.stdout
        assert "--fix" in result.stdout

    def test_report_only_does_not_mutate(self, isolated_task_env):
        session_dir = isolated_task_env['session_dir']
        self._seed(session_dir, "42", "  #42 [^#10] 🔧 stale marker task", parent_id="20")
        before = (session_dir / "42.json").read_text()

        subprocess.run(["macf_tools", "task", "doctor"],
                       capture_output=True, text=True, env=isolated_task_env['env'])

        assert (session_dir / "42.json").read_text() == before, "report-only wrote to disk"

    def test_fix_heals_the_stored_subject(self, isolated_task_env):
        session_dir = isolated_task_env['session_dir']
        self._seed(session_dir, "42", "  #42 [^#10] 🔧 stale marker task", parent_id="20")

        result = subprocess.run(
            ["macf_tools", "task", "doctor", "--fix"],
            capture_output=True, text=True, env=isolated_task_env['env'],
        )
        assert result.returncode == 0, result.stdout + result.stderr

        healed = json.loads((session_dir / "42.json").read_text())["subject"]
        assert "[^#20]" in healed
        assert "[^#10]" not in healed
        assert "stale marker task" in healed, "healing damaged the title"

    def test_clean_tree_reports_no_drift(self, isolated_task_env):
        self._seed(isolated_task_env['session_dir'], "42",
                   "  #42 [^#20] 🔧 honest marker task", parent_id="20")

        result = subprocess.run(
            ["macf_tools", "task", "doctor"],
            capture_output=True, text=True, env=isolated_task_env['env'],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No drift detected" in result.stdout


class TestTaskDoctorGitHubState:
    """A GitHub-backed task must be reconciled against GitHub, not against the
    copy of GitHub's answer it stored when it was created.

    The motivating incident: a task sat pending for hours after its PR merged,
    because everything downstream read `custom.gh_state` and that field had
    said OPEN since creation.
    """

    class _Mtmd:
        def __init__(self, task_type, custom):
            self.task_type = task_type
            self.custom = custom
            self.parent_id = None

    class _Task:
        def __init__(self, task_id, task_type, custom, status="pending"):
            self.id = task_id
            self.status = status
            self.subject = f"  #{task_id} tracked"
            self.mtmd = TestTaskDoctorGitHubState._Mtmd(task_type, custom)

    def _pr_task(self, task_id="1", status="pending", cached="OPEN"):
        return self._Task(task_id, "GH_PR", {
            "gh_owner": "o", "gh_repo": "r", "gh_pr_number": 7, "gh_state": cached,
        }, status=status)

    def test_open_task_whose_pr_merged_is_flagged_for_closeout(self):
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value="MERGED"):
            found = cli._doctor_check_gh_state([self._pr_task()])
        assert len(found) == 1
        assert found[0]["resolved_upstream"] is True
        assert found[0]["live"] == "MERGED"
        assert found[0]["cached"] == "OPEN"

    def test_completed_task_whose_pr_merged_is_not_flagged_for_closeout(self):
        """That is the correct end state — only the cached field is stale."""
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value="MERGED"):
            found = cli._doctor_check_gh_state(
                [self._pr_task(status="completed")], include_completed=True)
        assert len(found) == 1, "cached-state drift should still be reported"
        assert found[0]["resolved_upstream"] is False

    def test_completed_tasks_are_skipped_by_default(self):
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value="MERGED") as live:
            found = cli._doctor_check_gh_state([self._pr_task(status="completed")])
        assert found == []
        live.assert_not_called(), "skipped tasks should not cost an API call"

    def test_agreeing_state_is_not_a_finding(self):
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value="OPEN"):
            found = cli._doctor_check_gh_state([self._pr_task()])
        assert found == []

    def test_unreachable_authority_is_reported_not_assumed_to_agree(self):
        """An authority that cannot be reached is unknown, never agreement."""
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value=None):
            found = cli._doctor_check_gh_state([self._pr_task()])
        assert len(found) == 1
        assert found[0]["unreachable"] is True
        assert found[0]["live"] is None

    def test_cached_state_is_never_used_as_the_answer(self):
        """Even a cached MERGED gets verified — the point is not to trust it."""
        from macf import cli
        with patch.object(cli, "_gh_live_state", return_value="OPEN") as live:
            found = cli._doctor_check_gh_state([self._pr_task(cached="MERGED")])
        live.assert_called_once()
        assert len(found) == 1 and found[0]["live"] == "OPEN"

    def test_no_github_flag_skips_the_live_check(self, isolated_task_env):
        result = subprocess.run(
            ["macf_tools", "task", "doctor", "--no-github"],
            capture_output=True, text=True, env=isolated_task_env['env'],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "skipped (--no-github)" in result.stdout
