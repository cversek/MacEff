"""Tests for hook sidecar state persistence.

Coverage target: macf/src/macf/hooks/sidecar.py (update_sidecar, read_sidecar)

Sidecar files are the on-disk record of per-hook state under
/tmp/macf/{agent_id}/{session_id}/hooks/sidecar_{hook_name}.json, consumed
by `macf_tools hooks status`. Nothing exercised this module directly before
these tests (0% coverage) even though it is the writer/reader pair behind
that CLI surface. Every test monkeypatches get_hooks_dir/get_current_session_id
at the module level so nothing touches the real /tmp/macf tree.

Note (discovered while writing these tests): `update_sidecar`'s own
"load previous state for logging" step calls `read_json()` unguarded, and
`read_json()` raises `FileNotFoundError` when the sidecar doesn't exist yet
(see macf/src/macf/utils/json_io.py). Because that call sits inside
`update_sidecar`'s try/except, the FIRST call for a given hook_name in a
fresh session directory raises, is swallowed by the catch-all at the bottom,
and the sidecar is never written — silently. Every subsequent call hits the
same missing-file path, so the file never gets created at all through this
function. This looks like a real bug (flagged in the delegation checkpoint
for the PA), not intended behavior, but it is the current behavior, so the
happy-path tests below seed an existing sidecar file first to exercise the
intended "update on top of prior state" path — the shape every call after
the first is supposed to take, and the only shape currently reachable.
"""

import json

import pytest

from macf.hooks import sidecar


@pytest.fixture
def hooks_dir(tmp_path, monkeypatch):
    """Point sidecar's hooks-dir lookup at an isolated tmp directory."""
    d = tmp_path / "hooks"
    d.mkdir()
    monkeypatch.setattr(sidecar, "get_hooks_dir", lambda session_id=None, create=True: d)
    return d


def _seed(hooks_dir, hook_name, initial=None):
    """Pre-write a sidecar file so update_sidecar's previous-state read succeeds.

    See module docstring: read_json() raises on a missing file, and
    update_sidecar has no first-write guard, so tests that exercise the
    "update" path must seed a file first.
    """
    path = hooks_dir / f"sidecar_{hook_name}.json"
    path.write_text(json.dumps(initial if initial is not None else {"hook_name": hook_name}))
    return path


def test_update_then_read_round_trip(hooks_dir):
    """A written sidecar can be read back with the same custom fields."""
    _seed(hooks_dir, "stop")

    sidecar.update_sidecar("stop", {"session_id": "sess-abc", "mode": "AUTO_MODE"})
    result = sidecar.read_sidecar("stop", session_id="sess-abc")

    assert result["hook_name"] == "stop"
    assert result["session_id"] == "sess-abc"
    assert result["mode"] == "AUTO_MODE"


def test_update_sidecar_routes_to_detected_session_dir_when_marked_unknown(hooks_dir, monkeypatch):
    """A state dict with session_id 'unknown' routes the write via the detected session.

    Note: the *stored* session_id field in the sidecar JSON is a separate
    matter — see the bug noted in the module docstring, where `**state`
    clobbers the resolved value back to the caller's original "unknown"
    when building new_state. This test targets the part of auto-detection
    that does work correctly: which session's hooks_dir the file is routed
    into, which is what `get_hooks_dir(session_id, ...)` is called with.
    """
    _seed(hooks_dir, "stop")
    monkeypatch.setattr(sidecar, "get_current_session_id", lambda: "detected-session")
    seen_session_ids = []

    def _spy_get_hooks_dir(session_id=None, create=True):
        seen_session_ids.append(session_id)
        return hooks_dir

    monkeypatch.setattr(sidecar, "get_hooks_dir", _spy_get_hooks_dir)

    sidecar.update_sidecar("stop", {"session_id": "unknown"})

    assert seen_session_ids == ["detected-session"]


def test_update_sidecar_includes_captured_stdout_and_stderr(hooks_dir):
    """stdout/stderr, when given, land in the sidecar under their own keys."""
    _seed(hooks_dir, "pre_tool_use")

    sidecar.update_sidecar(
        "pre_tool_use",
        {"session_id": "sess-1"},
        stdout="printed output",
        stderr="printed error",
    )

    written = json.loads((hooks_dir / "sidecar_pre_tool_use.json").read_text())
    assert written["stdout_captured"] == "printed output"
    assert written["stderr_captured"] == "printed error"


def test_update_sidecar_no_op_and_no_warning_when_hooks_dir_unavailable(tmp_path, monkeypatch):
    """When get_hooks_dir returns None, update_sidecar returns quietly (no warning)."""
    marker = tmp_path / "hooks"
    monkeypatch.setattr(sidecar, "get_hooks_dir", lambda session_id=None, create=True: None)
    warnings_seen = []
    monkeypatch.setattr(sidecar, "emit_warning", lambda w: warnings_seen.append(w))

    sidecar.update_sidecar("stop", {"session_id": "sess-1"})

    assert warnings_seen == []
    assert not marker.exists()


def test_read_sidecar_returns_empty_dict_when_file_missing(hooks_dir):
    """Reading a hook name that was never written comes back empty, not an error."""
    result = sidecar.read_sidecar("never_written", session_id="sess-1")

    assert result == {}


def test_update_sidecar_emits_warning_when_write_fails(hooks_dir, monkeypatch):
    """A failure inside the write path is caught and reported, not raised."""
    _seed(hooks_dir, "stop")  # get past the previous-state read so write_json_safely is reached

    def _boom(path, data):
        raise ValueError("disk full (simulated)")

    monkeypatch.setattr(sidecar, "write_json_safely", _boom)
    warnings_seen = []
    monkeypatch.setattr(sidecar, "emit_warning", lambda w: warnings_seen.append(w))

    sidecar.update_sidecar("stop", {"session_id": "sess-1"})

    assert len(warnings_seen) == 1
    assert warnings_seen[0].kind == "sidecar_write_failed"
    assert "disk full" in warnings_seen[0].detail
