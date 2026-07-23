"""Tests for the PreToolUse touch-discipline nag.

The nag counts tool calls since the last task-store write (sidecar state
file keyed by store mtime) and emits a single ramping line at threshold
multiples. It must reset the moment any task file changes, stay silent
between thresholds, and honor the MACF_TOUCH_NAG_BASE=0 kill switch.
"""
import json
import time
from pathlib import Path

import pytest

from macf.hooks.handle_pre_tool_use import _touch_discipline_nag


@pytest.fixture
def nag_env(tmp_path, monkeypatch):
    """Fake task store + session dir; base threshold of 3 for fast tests."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "1.json").write_text("{}")

    session_dir = tmp_path / "session_hooks"
    session_dir.mkdir()

    class FakeReader:
        def __init__(self):
            self.tasks_dir = tasks_dir

    import macf.task
    import macf.utils
    monkeypatch.setattr(macf.task, "TaskReader", FakeReader)
    monkeypatch.setattr(macf.utils, "get_session_dir", lambda **kw: session_dir)
    monkeypatch.setenv("MACF_TOUCH_NAG_BASE", "3")
    return tasks_dir, session_dir


def _run_n(n, session="s"):
    out = []
    for _ in range(n):
        out.append(_touch_discipline_nag(session))
    return out


def test_silent_below_threshold(nag_env):
    assert _run_n(2) == ["", ""]


def test_fires_at_base_then_silent_then_ramps(nag_env):
    msgs = _run_n(9)
    assert msgs[2] != "" and "3 tool calls" in msgs[2]      # n == base
    assert msgs[3] == "" and msgs[4] == ""                   # between thresholds
    assert msgs[5] != "" and "6 tool calls" in msgs[5]      # n == 2*base
    assert msgs[8] != "" and "9 tool calls" in msgs[8]      # n == 3*base


def test_ramp_tone_escalates(nag_env):
    msgs = _run_n(9)
    assert msgs[2].startswith("\U0001f331")   # seedling
    assert msgs[5].startswith("\U0001f33f")   # herb
    assert msgs[8].startswith("\U0001f333")   # tree


def test_store_touch_resets_counter(nag_env):
    tasks_dir, _ = nag_env
    _run_n(2)
    # Touch the store (newer mtime), as any task note/start/complete would
    time.sleep(0.01)
    f = tasks_dir / "1.json"
    f.write_text("{}")
    now = time.time()
    import os
    os.utime(f, (now + 5, now + 5))
    msgs = _run_n(3)
    assert msgs[0] == "" and msgs[1] == ""    # counter restarted at 1, 2
    assert "3 tool calls" in msgs[2]          # fires again at base


def test_kill_switch(nag_env, monkeypatch):
    monkeypatch.setenv("MACF_TOUCH_NAG_BASE", "0")
    assert _run_n(5) == [""] * 5
