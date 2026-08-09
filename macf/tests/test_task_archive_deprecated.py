"""The `task archive` / `restore` / `archived` trio is retired and must FAIL CLOSED.

The bug that started it: `task archive` printed a ✅ success line while archiving
nothing — a false report of a state change. The durable requirement is that a
subcommand never report success for an operation it did not perform.

`restore` (restored *from* an archive) and `archived` (listed archives) were both
premised on `archive` producing real archives. With `archive` retired there is no
supported way to produce an archive, so the whole trio is retired together rather
than leaving `restore`/`archived` as paths into dead machinery. Every one must
never exit 0 and never print a success line.
"""

from types import SimpleNamespace

from macf import cli


# --- task archive -----------------------------------------------------------

def test_task_archive_fails_closed_with_deprecation_notice(capsys):
    rc = cli.cmd_task_archive(SimpleNamespace(task_id="77", no_cascade=False, json_output=False))
    out = capsys.readouterr().out
    assert rc == 2, "must fail closed — never exit 0 (which would read as a successful archive)"
    assert "DEPRECATED" in out
    assert "hide-completed" in out
    assert "✅ Archived" not in out  # the false-success line must be gone


def test_task_archive_deprecation_json(capsys):
    rc = cli.cmd_task_archive(SimpleNamespace(task_id="77", no_cascade=False, json_output=True))
    out = capsys.readouterr().out
    assert rc == 2
    assert '"deprecated": true' in out
    assert '"success": false' in out


# --- task restore -----------------------------------------------------------

def test_task_restore_fails_closed_with_deprecation_notice(capsys):
    rc = cli.cmd_task_restore(SimpleNamespace(archive_path_or_id="1", json_output=False))
    out = capsys.readouterr().out
    assert rc == 2, "must fail closed — never exit 0 (which would read as a successful restore)"
    assert "DEPRECATED" in out
    assert "hide-completed" in out
    assert "✅ Restored" not in out  # the old success line must be gone


def test_task_restore_deprecation_json(capsys):
    rc = cli.cmd_task_restore(SimpleNamespace(archive_path_or_id="1", json_output=True))
    out = capsys.readouterr().out
    assert rc == 2
    assert '"deprecated": true' in out
    assert '"success": false' in out


# --- task archived (list) ---------------------------------------------------

def test_task_archived_list_fails_closed_with_deprecation_notice(capsys):
    rc = cli.cmd_task_archived_list(SimpleNamespace(json_output=False))
    out = capsys.readouterr().out
    assert rc == 2, "must fail closed — never exit 0 (which would read as an authoritative listing)"
    assert "DEPRECATED" in out
    assert "hide-completed" in out
    assert "📦 Archived Tasks" not in out  # the old listing header must be gone


def test_task_archived_list_deprecation_json(capsys):
    rc = cli.cmd_task_archived_list(SimpleNamespace(json_output=True))
    out = capsys.readouterr().out
    assert rc == 2
    assert '"deprecated": true' in out
    assert '"success": false' in out
