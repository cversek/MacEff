"""
Unit tests for task ID type refactor (BUG #8).

Tests verify that task IDs are consistently handled as strings throughout the
task system, enabling proper sorting of sentinel ID "000" alongside numeric
IDs like "3", "8", "10".
"""

import pytest
from macf.task.models import MacfTask, MacfTaskMetaData


class TestStringTaskIDs:
    """Test suite for string-based task ID handling."""

    def test_sentinel_id_preserved_as_string(self):
        """Verify sentinel task ID "000" is preserved as string, not converted to 0."""
        # Create task with sentinel ID
        task_data = {
            "id": "000",
            "subject": "MACF TASK LIST",
            "description": "Sentinel task",
            "status": "in_progress"
        }

        task = MacfTask.from_json(task_data)

        # Verify ID is string "000", not int 0
        assert task.id == "000"
        assert isinstance(task.id, str)
        assert task.id != 0  # String "000" != integer 0

    def test_numeric_ids_stored_as_strings(self):
        """Verify numeric IDs are stored as strings for consistent type handling."""
        test_cases = [
            ("3", "3"),
            ("8", "8"),
            ("10", "10"),
            (3, "3"),    # Integer input converted to string
            (10, "10"),  # Integer input converted to string
        ]

        for input_id, expected_str in test_cases:
            task_data = {
                "id": input_id,
                "subject": f"Task {input_id}",
                "description": "Test task",
                "status": "pending"
            }

            task = MacfTask.from_json(task_data)

            assert task.id == expected_str
            assert isinstance(task.id, str)

    def test_mixed_id_sorting_with_zfill(self):
        """Verify tasks with mixed IDs ("000", "3", "8", "10") sort correctly."""
        # Create tasks with various IDs
        task_ids = ["000", "3", "8", "10", "5", "12", "1"]
        tasks = []

        for tid in task_ids:
            task_data = {
                "id": tid,
                "subject": f"Task {tid}",
                "description": "Test task",
                "status": "pending"
            }
            tasks.append(MacfTask.from_json(task_data))

        # Sort using zfill(3) for proper numeric-like ordering
        sorted_tasks = sorted(tasks, key=lambda t: t.id.zfill(3))
        sorted_ids = [t.id for t in sorted_tasks]

        # Expected order: "000", "1", "3", "5", "8", "10", "12"
        expected_order = ["000", "1", "3", "5", "8", "10", "12"]
        assert sorted_ids == expected_order

    def test_parent_id_string_in_mtmd(self):
        """Verify parent_id in MacfTaskMetaData is handled as string."""
        # Create MTMD with parent_id
        description = """
Some task description.

<macf_task_metadata version="1.0">
creation_breadcrumb: s_test/c_1/g_abc/p_123/t_1234567890
created_cycle: 1
created_by: PA
parent_id: "5"
</macf_task_metadata>
"""

        task_data = {
            "id": "10",
            "subject": "[^#5] Child task",
            "description": description,
            "status": "pending"
        }

        task = MacfTask.from_json(task_data)

        # Verify MTMD parent_id is string
        assert task.mtmd is not None
        assert task.mtmd.parent_id == "5"
        assert isinstance(task.mtmd.parent_id, str)

    def test_mtmd_bug_fix_fields_exist(self):
        """Verify plan field exists in MacfTaskMetaData for BUG tasks (uses plan, not fix_plan)."""
        # Create MTMD with BUG fix tracking fields
        description = """
Fix task ID type inconsistency.

<macf_task_metadata version="1.0">
creation_breadcrumb: s_test/c_382/g_abc/p_123/t_1234567890
created_cycle: 382
created_by: PA
task_type: BUG
plan: "Refactor task ID handling from Union[int, str] to pure str type"
</macf_task_metadata>
"""

        task_data = {
            "id": "8",
            "subject": "BUG: Task ID type inconsistency",
            "description": description,
            "status": "in_progress"
        }

        task = MacfTask.from_json(task_data)

        # Verify MTMD has BUG tracking fields (BUG tasks use 'plan', not 'fix_plan')
        assert task.mtmd is not None
        assert hasattr(task.mtmd, 'plan')
        assert hasattr(task.mtmd, 'plan_ca_ref')
        assert task.mtmd.plan == "Refactor task ID handling from Union[int, str] to pure str type"
        assert task.mtmd.task_type == "BUG"
