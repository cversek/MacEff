"""`0` is not the root, and a task attached to it vanishes.

The tree root is `#000`. Passing `0` where a parent id is expected was accepted,
reported success, and orphaned the task: attached to a parent that does not
exist, it disappeared from `task tree` entirely.

#208 fixed exactly this on `task create`. `reparent`, `metadata set`, and the
grant that authorises them never inherited the repair. A property that holds on
the path that was fixed and not on its siblings is a coincidence of coverage,
not a property — so these tests cover the siblings.

The second defect is the one that made it invisible: `task doctor` reported the
corrupted tree as healthy. It compared each `[^#N]` marker against `parent_id`
on the same object, which is INTERNAL consistency. A task orphaned this way is
perfectly self-consistent and completely unreachable, so the check passed while
the tree was silently short by one. Referential integrity is a different
question and had to be asked separately.
"""
from macf.task.create import normalize_parent_id


class _T:
    def __init__(self, tid, parent):
        self.id = str(tid)
        self.parent_id = parent


class TestDoctorSeesOrphans:
    def test_reports_a_parent_that_does_not_exist(self):
        """The finding the doctor could not previously make."""
        from macf.cli import _doctor_check_parent_exists
        found = _doctor_check_parent_exists([_T("000", None), _T("5", "000"), _T("204", "0")])
        assert found == [("204", "0")]

    def test_clean_tree_reports_nothing(self):
        """A zero result has to be earned, not the only result it can produce."""
        from macf.cli import _doctor_check_parent_exists
        assert _doctor_check_parent_exists([_T("000", None), _T("5", "000"), _T("6", "5")]) == []

    def test_root_is_not_its_own_orphan(self):
        """The root has no parent to name and must not report itself."""
        from macf.cli import _doctor_check_parent_exists
        assert _doctor_check_parent_exists([_T("000", "000")]) == []

    def test_hash_prefixed_parent_still_resolves(self):
        """Stored ids carry a leading # in places; that is spelling, not absence."""
        from macf.cli import _doctor_check_parent_exists
        assert _doctor_check_parent_exists([_T("000", None), _T("7", "#000")]) == []


class TestZeroNormalisesToTheRoot:
    def test_every_zero_spelling_reaches_the_root(self):
        """The reparent/metadata/grant paths all route through this."""
        for spelling in ("0", "00", "000", 0, "#0", " 0 "):
            assert normalize_parent_id(spelling) == "000", spelling

    def test_a_real_parent_is_left_alone(self):
        """Normalisation must not quietly rewrite legitimate placements."""
        assert normalize_parent_id("42") == "42"
        assert normalize_parent_id("#42") == "42"


class TestReparentIsActuallyWired:
    """Normalising in a helper proves nothing about the command that calls it.

    This is the lesson from #289 applied before it could repeat: the predicate
    tests above would all pass while `reparent` kept storing "0", because the
    predicate and the command are different things and only one of them is what
    an operator runs.
    """

    def test_reparent_zero_stores_the_root(self, monkeypatch, capsys):
        import argparse
        import macf.cli as cli
        import macf.task as task_mod
        from macf.task.models import MacfTask, MacfTaskMetaData

        task = MacfTask(id="204", subject="[^#190] thing", description="",
                        status="pending",
                        mtmd=MacfTaskMetaData(parent_id="190", title="thing",
                                              updates=[], custom={}))

        class _Reader:
            session_path = None

            def read_task(self, tid):
                return task if str(tid) == "204" else None

            def read_all_tasks(self):
                return [task]

        writes = {}
        monkeypatch.setattr(task_mod, "TaskReader", _Reader)
        monkeypatch.setattr(task_mod, "update_task_file",
                            lambda tid, data: writes.update(data) or True)
        monkeypatch.setattr("macf.task.protection.check_grant_in_events",
                            lambda *a, **k: (True, None))
        monkeypatch.setattr("macf.task.protection.clear_grant", lambda *a, **k: None)

        rc = cli.cmd_task_reparent(argparse.Namespace(task_id="204", parent="0"))
        out = capsys.readouterr().out

        assert rc == 0, out
        assert "→ 000" in out, "the command should report the canonical root"
        assert "parent_id: '000'" in writes.get("description", ""), \
            "the STORED parent must be the root, not the orphaning '0'"
        # A root-level task carries no [^#N] marker by design, so the check is
        # that the stale one is gone rather than that a new one appeared. The
        # first version of this test asserted "[^#000]" and failed against
        # correct code — the marker's absence IS the correct rendering.
        assert "[^#190]" not in writes.get("subject", ""), \
            "the old parent marker must not survive the reparent"
