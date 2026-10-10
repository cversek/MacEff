"""A task file is replaced whole or not at all (macf/utils/atomic.py).

On 2026-10-10 a full /home emptied a task file: the store opened it with mode "w",
which truncates, and then could not write. The task vanished from the tree.
"""
import errno
import json
import stat

import pytest

from macf.task import reader as task_reader
from macf.utils import atomic


def _enospc(*a, **k):
    raise OSError(errno.ENOSPC, "No space left on device")


def test_the_new_content_replaces_the_old_and_keeps_its_mode(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    path = store / "481.json"
    path.write_text('{"old": true}')
    path.chmod(0o640)
    atomic.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text()) == {"new": True}
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert [p.name for p in store.iterdir()] == ["481.json"]


def test_a_write_that_fails_on_a_full_disk_leaves_the_old_file_and_no_temp(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    path = store / "481.json"
    path.write_text('{"old": true}')
    monkeypatch.setattr(atomic.os, "fsync", _enospc)
    with pytest.raises(OSError):
        atomic.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert [p.name for p in store.iterdir()] == ["481.json"]


def test_a_task_update_that_fails_part_way_leaves_the_task_readable(tmp_path, monkeypatch):
    """The store-level red proof: on main, this left 481.json at 0 bytes."""
    monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(tmp_path))
    task = {"id": "481", "subject": "Phase 3", "description": "", "status": "pending",
            "blocks": [], "blockedBy": []}
    (tmp_path / "481.json").write_text(json.dumps(task))

    def fails_while_writing(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    # Fail at the point a full disk fails: after the file is open for writing.
    monkeypatch.setattr(task_reader.json, "dump", fails_while_writing)
    monkeypatch.setattr(atomic.os, "fsync", fails_while_writing)

    assert task_reader.update_task_file("481", {"status": "in_progress"}) is False
    assert json.loads((tmp_path / "481.json").read_text()) == task


def test_a_read_only_file_is_refused_as_open_for_writing_refused_it(tmp_path):
    """The sentinel task is 444 so it cannot be modified; a rename must not get around that."""
    store = tmp_path / "store"
    store.mkdir()
    path = store / "sentinel.json"
    path.write_text('{"old": true}')
    path.chmod(0o444)
    with pytest.raises(PermissionError):
        atomic.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert [p.name for p in store.iterdir()] == ["sentinel.json"]


def test_an_update_in_a_protected_store_lands_and_the_store_stays_protected(tmp_path, monkeypatch):
    """Review of this PR: a store is born 555, and a rename needs write permission on the
    directory. Before the fix the update returned False and the change was lost."""
    monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
    task = {"id": "481", "subject": "Phase 3", "description": "", "status": "pending",
            "blocks": [], "blockedBy": []}
    (store / "481.json").write_text(json.dumps(task))
    store.chmod(0o555)
    try:
        assert task_reader.update_task_file("481", {"status": "in_progress"}) is True
        assert json.loads((store / "481.json").read_text())["status"] == "in_progress"
        assert stat.S_IMODE(store.stat().st_mode) == 0o555
        assert [p.name for p in store.iterdir()] == ["481.json"]
    finally:
        store.chmod(0o755)


def test_a_new_file_gets_the_mode_open_would_give(tmp_path):
    import os
    store = tmp_path / "store"
    store.mkdir()
    old = os.umask(0o022)
    try:
        atomic.write_text_atomic(store / "new.json", "{}")
    finally:
        os.umask(old)
    assert stat.S_IMODE((store / "new.json").stat().st_mode) == 0o644


def test_two_writers_in_a_protected_store_both_land(tmp_path):
    """Re-review of this PR: without a lock, one writer restored 555 while the other was
    between its temporary file and its rename, and that update (and its cleanup) failed."""
    import subprocess
    import sys
    import time
    from pathlib import Path
    store = tmp_path / "store"
    store.mkdir()
    (store / "7.json").write_text(json.dumps({"id": "7", "subject": "s", "description": "",
                                              "status": "pending", "blocks": [], "blockedBy": []}))
    store.chmod(0o555)
    src = str(Path(task_reader.__file__).resolve().parents[2])
    go = tmp_path / "go"
    # Both writers wait for one start signal, so their updates overlap rather than run in turn.
    script = ("import os, sys, time\nfrom macf.task import reader\n"
              f"while not os.path.exists({str(go)!r}): time.sleep(0.001)\n"
              "fails = sum(not reader.update_task_file('7', {'activeForm': f'w{i}'}) for i in range(300))\n"
              "print(fails)\n")
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": src, "MACF_TASK_STORE_DIR": str(store), "HOME": str(tmp_path)}
    try:
        procs = [subprocess.Popen([sys.executable, "-c", script], env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for _ in range(2)]
        time.sleep(0.5)
        go.write_text("")
        outs = [p.communicate(timeout=120) for p in procs]
        assert [o[0].strip() for o in outs] == ["0", "0"], [o[1][-300:] for o in outs]
        assert [p.name for p in store.iterdir()] == ["7.json"]
        assert stat.S_IMODE(store.stat().st_mode) == 0o555
        json.loads((store / "7.json").read_text())
    finally:
        store.chmod(0o755)
