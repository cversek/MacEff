"""Tests for the three new task-mutation CLI verbs shipped in Phase 2 of the
cversek/MacEff#112 umbrella closure.

Verbs covered:
  task reparent   — atomic parent_id change, grant-gated, cycle-safe
  task advance    — lifecycle state machine transition, event-emitting
  task metadata set-custom — dotted-path custom field setter, type-coercing

These tests follow the patterns established in test_task_mutation_bugs.py:
- patch macf.event_queries.get_latest_event for grant tests
- use MagicMock task fixtures rather than touching the live task store
- avoid any project-specific names in fixtures (generic placeholders only)

Patch targets:
  TaskReader     — macf.cli.TaskReader   (top-level import in cli.py)
  append_event   — macf.cli.append_event (top-level import in cli.py)
  update_task_file — macf.task.reader.update_task_file (local import inside cmds)
  get_breadcrumb — macf.utils.breadcrumbs.get_breadcrumb (local import)
  clear_grant    — macf.task.protection.clear_grant (local import)
  grant check    — macf.event_queries.get_latest_event (imported by protection.py)
"""
import copy
import argparse
from unittest.mock import patch, MagicMock

from macf.cli import (
    cmd_task_reparent,
    cmd_task_advance,
    cmd_task_metadata_set_custom,
)


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def _make_ns(**kwargs):
    """Build a minimal argparse.Namespace with given keyword args."""
    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _fake_task(task_id="10", parent_id="000", title="Test Task", custom=None):
    """Return a MagicMock resembling a MacfTask for a generic task."""
    task = MagicMock()
    task.id = task_id
    task.subject = f"📋 #{task_id}: {title}"

    mtmd = MagicMock()
    mtmd.parent_id = parent_id
    mtmd.title = title
    mtmd.task_type = None
    mtmd.updates = []
    mtmd.custom = copy.deepcopy(custom) if custom is not None else {}

    task.mtmd = mtmd
    task.parent_id = parent_id

    # with_updated_field returns a deep copy so tests can inspect the stored value
    def _with_updated_field(field, value, breadcrumb, description=""):
        new = MagicMock()
        new.parent_id = mtmd.parent_id
        new.title = mtmd.title
        new.task_type = mtmd.task_type
        new.custom = copy.deepcopy(mtmd.custom)
        setattr(new, field, value)
        return new

    mtmd.with_updated_field.side_effect = _with_updated_field

    # description_with_updated_mtmd returns a placeholder string
    task.description_with_updated_mtmd.return_value = "<!-- updated description -->"

    return task


def _fake_grant_event(task_ids, field=None, value=None, ts=200):
    data = {"task_ids": list(task_ids)}
    if field is not None:
        data["field"] = field
    if value is not None:
        data["value"] = value
    return {"event": "task_grant_update", "data": data, "timestamp": ts}


def _patch_grants(grant=None, cleared=None):
    """Patch get_latest_event in the module where protection.py imports it."""
    def side_effect(event_type, **_):
        if event_type == "task_grant_update":
            return grant
        if event_type == "task_grant_update_cleared":
            return cleared
        return None
    return patch("macf.event_queries.get_latest_event", side_effect=side_effect)


# Common patch targets for functions that are locally imported inside cmd functions.
# All three new cmd functions do `from .task import TaskReader, update_task_file`
# and `from .task.protection import check_grant_in_events, clear_grant` inside the
# function body.  The local import binds names from the macf.task / macf.task.protection
# namespaces, so we patch the *source* namespace — not macf.cli.
#
# TaskReader      — local import → macf.task.TaskReader
# update_task_file— local import → macf.task.update_task_file
# get_breadcrumb  — local import → macf.utils.breadcrumbs.get_breadcrumb
# clear_grant     — local import → macf.task.protection.clear_grant
# append_event    — cmd_task_advance does a local import from .agent_events_log,
#                   so patch the source module macf.agent_events_log.append_event
# grant check     — macf.event_queries.get_latest_event (imported inside protection.py)
_PATCH_TASK_READER = "macf.task.TaskReader"
_PATCH_UPDATE = "macf.task.update_task_file"
_PATCH_BREADCRUMB = "macf.utils.breadcrumbs.get_breadcrumb"
_PATCH_CLEAR_GRANT = "macf.task.protection.clear_grant"
_PATCH_APPEND_EVENT = "macf.agent_events_log.append_event"


# ---------------------------------------------------------------------------
# task reparent tests
# ---------------------------------------------------------------------------

class TestTaskReparent:
    """Tests for cmd_task_reparent."""

    def test_reparent_to_sentinel_stores_string(self):
        """Reparent to '000' sentinel must store the string '000', not int 0."""
        task = _fake_task(task_id="10", parent_id="5")
        grant = _fake_grant_event(["10"], field="parent_id", value="000")

        args = _make_ns(task_id="10", parent="000")
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True), \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             patch(_PATCH_CLEAR_GRANT), \
             _patch_grants(grant=grant):
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_reparent(args)

        assert rc == 0
        call_args = task.mtmd.with_updated_field.call_args
        stored_value = call_args[0][1]  # positional: (field, value, breadcrumb, description)
        assert stored_value == "000", f"Expected string '000', got {stored_value!r}"

    def test_reparent_to_digit_string_stores_string(self):
        """Reparent to '42' must store the string '42', not int 42."""
        task = _fake_task(task_id="10", parent_id="5")
        grant = _fake_grant_event(["10"], field="parent_id", value="42")

        def read_task_side(tid):
            return {"10": task, "42": _fake_task("42", parent_id="000")}.get(str(tid))

        args = _make_ns(task_id="10", parent="42")
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True), \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             patch(_PATCH_CLEAR_GRANT), \
             _patch_grants(grant=grant):
            MockReader.return_value.read_task.side_effect = read_task_side
            rc = cmd_task_reparent(args)

        assert rc == 0
        call_args = task.mtmd.with_updated_field.call_args
        stored_value = call_args[0][1]
        assert stored_value == "42", f"Expected string '42', got {stored_value!r}"

    def test_reparent_rejects_self_as_parent(self, capsys):
        """A task cannot be its own parent."""
        task = _fake_task(task_id="10", parent_id="000")
        args = _make_ns(task_id="10", parent="10")

        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             _patch_grants():
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_reparent(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "own parent" in out.lower()

    def test_reparent_rejects_cycle(self, capsys):
        """Reparenting A under B when B's parent is A must be rejected."""
        task_a = _fake_task(task_id="10", parent_id="000")
        task_b = _fake_task(task_id="20", parent_id="10")  # B's parent IS A

        reader_tasks = {"10": task_a, "20": task_b}
        args = _make_ns(task_id="10", parent="20")  # try to make A child of B

        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             _patch_grants():
            MockReader.return_value.read_task.side_effect = lambda tid: reader_tasks.get(str(tid))
            rc = cmd_task_reparent(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "cycle" in out.lower() or "loop" in out.lower()

    def test_reparent_without_grant_fails(self, capsys):
        """Changing parent_id on a task that already has one requires a grant."""
        task = _fake_task(task_id="10", parent_id="5")  # existing non-null parent
        args = _make_ns(task_id="10", parent="99")

        # No grant in event log
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             _patch_grants(grant=None):
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_reparent(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "grant" in out.lower()


# ---------------------------------------------------------------------------
# task advance tests
# ---------------------------------------------------------------------------

class TestTaskAdvance:
    """Tests for cmd_task_advance."""

    _STATE_MACHINE = {
        "submitted": ["under_review", "rejected"],
        "under_review": ["accepted", "rejected"],
        "accepted": ["complete"],
        "rejected": [],
    }

    def _make_task(self, current_state="submitted"):
        task = _fake_task(task_id="10", custom={
            "lifecycle_state_machine": copy.deepcopy(self._STATE_MACHINE),
            "lifecycle_state": current_state,
        })
        # Ensure custom is a real dict (not the MagicMock default)
        task.mtmd.custom = {
            "lifecycle_state_machine": copy.deepcopy(self._STATE_MACHINE),
            "lifecycle_state": current_state,
        }
        return task

    def test_advance_legal_transition_succeeds(self):
        """Advancing from 'submitted' to 'under_review' (a legal next state) must succeed."""
        task = self._make_task("submitted")
        captured_events = []

        def capture_event(event_type, data, hook_input=None):
            captured_events.append((event_type, data))
            return True

        args = _make_ns(task_id="10", state="under_review", reason="ready for review")
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             patch(_PATCH_APPEND_EVENT, side_effect=capture_event):
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_advance(args)

        assert rc == 0
        mock_update.assert_called_once()
        assert len(captured_events) == 1
        evt_type, evt_data = captured_events[0]
        assert evt_type == "task_lifecycle_advanced"
        assert evt_data["from_state"] == "submitted"
        assert evt_data["to_state"] == "under_review"
        assert evt_data["reason"] == "ready for review"

    def test_advance_illegal_transition_rejects(self, capsys):
        """Advancing from 'submitted' to 'complete' (not a legal next) must exit 1."""
        task = self._make_task("submitted")

        args = _make_ns(task_id="10", state="complete", reason="")
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             patch(_PATCH_APPEND_EVENT, return_value=True):
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_advance(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "illegal" in out.lower() or "legal" in out.lower()

    def test_advance_no_state_machine_rejects(self, capsys):
        """task advance on a task with no lifecycle_state_machine declared must exit 1."""
        task = _fake_task(task_id="10", custom={})
        task.mtmd.custom = {}  # no lifecycle_state_machine key

        args = _make_ns(task_id="10", state="anything", reason="")
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             patch(_PATCH_APPEND_EVENT, return_value=True):
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_advance(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "lifecycle_state_machine" in out


# ---------------------------------------------------------------------------
# task metadata set-custom tests
# ---------------------------------------------------------------------------

class TestTaskMetadataSetCustom:
    """Tests for cmd_task_metadata_set_custom."""

    def _make_task_with_real_mtmd(self, initial_custom=None):
        """
        Return a MagicMock task whose .mtmd is a real MacfTaskMetaData instance.

        This is required because cmd_task_metadata_set_custom does copy.deepcopy
        on task.mtmd — deepcopy of a MagicMock produces another MagicMock and
        dict mutations on its .custom attr don't persist as expected. A real
        dataclass instance deepcopies into a proper dict-bearing dataclass.
        """
        from macf.task.models import MacfTaskMetaData
        mtmd = MacfTaskMetaData()
        mtmd.custom = dict(initial_custom) if initial_custom else {}

        task = MagicMock()
        task.id = "10"
        task.mtmd = mtmd

        captured = {}

        def capture_description_with_updated_mtmd(new_mtmd):
            captured["new_mtmd"] = new_mtmd
            return "<!-- updated description -->"

        task.description_with_updated_mtmd.side_effect = capture_description_with_updated_mtmd
        task._captured = captured
        return task

    def _run(self, task_id_arg, path_arg, value_arg, use_json=False, task=None):
        """
        Run cmd_task_metadata_set_custom and return (rc, mock_update, captured_mtmd).

        captured_mtmd is the MacfTaskMetaData passed to description_with_updated_mtmd —
        the new_mtmd after the dotted-path mutation, which is what we want to inspect.
        """
        if task is None:
            task = self._make_task_with_real_mtmd()

        args = _make_ns(task_id=task_id_arg, path=path_arg, value=value_arg, json=use_json)

        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             _patch_grants():
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_metadata_set_custom(args)

        return rc, mock_update, task._captured.get("new_mtmd")

    def test_bool_coercion_true(self):
        """'true' (case-insensitive) must be coerced to Python True, not string."""
        task = self._make_task_with_real_mtmd()

        rc, mock_update, new_mtmd = self._run("10", "decision_gates.submitted", "true", task=task)

        assert rc == 0
        assert new_mtmd is not None
        stored = new_mtmd.custom.get("decision_gates", {}).get("submitted")
        assert stored is True, f"Expected True, got {stored!r}"

    def test_json_flag_stores_list(self):
        """--json '[1,2,3]' must store Python list [1, 2, 3]."""
        task = self._make_task_with_real_mtmd()

        rc, mock_update, new_mtmd = self._run("10", "gh_labels", "[1,2,3]", use_json=True, task=task)

        assert rc == 0
        assert new_mtmd is not None
        stored = new_mtmd.custom.get("gh_labels")
        assert stored == [1, 2, 3], f"Expected [1, 2, 3], got {stored!r}"

    def test_existing_key_requires_grant(self, capsys):
        """Setting a key that already exists in custom requires a grant."""
        task = self._make_task_with_real_mtmd(initial_custom={"flag": "old_value"})

        args = _make_ns(task_id="10", path="flag", value="new_value", json=False)
        with patch(_PATCH_TASK_READER) as MockReader, \
             patch(_PATCH_UPDATE, return_value=True) as mock_update, \
             patch(_PATCH_BREADCRUMB, return_value="s_test/c_0/g_abc/p_xyz/t_0"), \
             _patch_grants(grant=None):  # no grant present
            MockReader.return_value.read_task.return_value = task
            rc = cmd_task_metadata_set_custom(args)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "grant" in out.lower()

    def test_new_key_does_not_require_grant(self):
        """Setting a brand-new key in custom must NOT require a grant."""
        task = self._make_task_with_real_mtmd()  # empty custom, no grant needed

        rc, mock_update, new_mtmd = self._run("10", "new_key", "hello", task=task)

        assert rc == 0
        mock_update.assert_called_once()
        assert new_mtmd is not None
        assert new_mtmd.custom.get("new_key") == "hello"

    def test_invalid_json_rejects(self, capsys):
        """--json with invalid JSON must exit 1 with a descriptive message."""
        task = self._make_task_with_real_mtmd()

        rc, mock_update, _ = self._run("10", "key", "{bad json", use_json=True, task=task)

        assert rc == 1
        mock_update.assert_not_called()
        out = capsys.readouterr().out
        assert "json" in out.lower()
