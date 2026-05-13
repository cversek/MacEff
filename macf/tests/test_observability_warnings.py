"""Unit tests for macf.observability.warnings.

Covers the dual-channel contract (stderr + systemMessage), the dedup
fingerprint behavior, dataclass construction defaults, and the optional
field rendering rules.
"""
from __future__ import annotations

import io
import sys

import pytest

from macf.observability import Warning, emit_warning, reset_dedup_registry


@pytest.fixture(autouse=True)
def _isolate_dedup_registry():
    """Each test gets a clean module-level registry.

    Tests that pass their own ``_registry`` ignore this; tests that
    exercise the module-level state get isolation for free.
    """
    reset_dedup_registry()
    yield
    reset_dedup_registry()


def _capture_stderr(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    return buf


def _make_warning(**overrides) -> Warning:
    """Build a Warning with sensible defaults; override per test."""
    defaults = dict(
        source="telegram",
        kind="api_unreachable",
        detail="connection refused on api.telegram.org",
        likely_cause="network blocked or DNS failure",
        user_remediation="check connectivity and retry",
    )
    defaults.update(overrides)
    return Warning(**defaults)


# --- Dataclass shape ------------------------------------------------------

def test_warning_construction_with_defaults():
    """Required fields populate; optional fields use documented defaults."""
    w = Warning(source="config", kind="missing_key", detail="ANTHROPIC_API_KEY not set")

    assert w.source == "config"
    assert w.kind == "missing_key"
    assert w.detail == "ANTHROPIC_API_KEY not set"
    assert w.likely_cause == ""
    assert w.user_remediation == ""
    assert w.full_trace_path is None
    assert w.severity == "warning"


def test_warning_is_frozen():
    """frozen=True: attempting to mutate raises FrozenInstanceError."""
    w = _make_warning()
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        w.source = "different"  # type: ignore[misc]


def test_fingerprint_is_source_colon_kind():
    """Fingerprint format is stable + predictable."""
    w = Warning(source="redis", kind="connection_timeout", detail="x")
    assert w.fingerprint() == "redis:connection_timeout"


def test_fingerprint_is_stable_across_instances():
    """Two Warnings with same source+kind produce the same fingerprint."""
    a = Warning(source="telegram", kind="api_unreachable", detail="reason a")
    b = Warning(source="telegram", kind="api_unreachable", detail="reason b")
    assert a.fingerprint() == b.fingerprint()


# --- Dual-channel emission ------------------------------------------------

def test_emit_writes_to_stderr(monkeypatch: pytest.MonkeyPatch):
    """First emission writes a stderr line containing source + detail + cause."""
    buf = _capture_stderr(monkeypatch)
    w = _make_warning()

    emit_warning(w)

    output = buf.getvalue()
    assert "telegram" in output
    assert "connection refused on api.telegram.org" in output
    assert "network blocked or DNS failure" in output


def test_emit_returns_system_message_in_dict():
    """Return dict carries the agent-visible systemMessage with all populated fields."""
    w = _make_warning()

    result = emit_warning(w)

    assert "systemMessage" in result
    msg = result["systemMessage"]
    assert "telegram" in msg
    assert "api_unreachable" in msg
    assert "connection refused on api.telegram.org" in msg
    assert "network blocked or DNS failure" in msg
    assert "check connectivity and retry" in msg


def test_emit_omits_empty_optional_fields_from_system_message(
    monkeypatch: pytest.MonkeyPatch,
):
    """Empty likely_cause / user_remediation produce no corresponding lines."""
    _capture_stderr(monkeypatch)  # suppress stderr noise
    w = Warning(source="stop_hook", kind="recovered", detail="restored from snapshot")

    result = emit_warning(w)

    msg = result["systemMessage"]
    assert "Cause:" not in msg
    assert "Recovery:" not in msg
    assert "restored from snapshot" in msg


def test_emit_includes_full_trace_path_when_set(monkeypatch: pytest.MonkeyPatch):
    """full_trace_path appears in systemMessage if provided."""
    _capture_stderr(monkeypatch)
    w = _make_warning(full_trace_path="/tmp/macf/proxy_captures/trace.log")

    result = emit_warning(w)

    assert "/tmp/macf/proxy_captures/trace.log" in result["systemMessage"]


# --- Deduplication --------------------------------------------------------

def test_dedup_appends_count_suffix_on_repeat(monkeypatch: pytest.MonkeyPatch):
    """Second emission with same fingerprint adds (×2); third adds (×3)."""
    buf = _capture_stderr(monkeypatch)
    w = _make_warning()

    emit_warning(w)
    emit_warning(w)
    emit_warning(w)

    lines = buf.getvalue().splitlines()
    assert len(lines) == 3
    assert "(×" not in lines[0]
    assert "(×2)" in lines[1]
    assert "(×3)" in lines[2]


def test_dedup_disabled_suppresses_suffix(monkeypatch: pytest.MonkeyPatch):
    """dedupe=False: every emission is verbatim, no count suffix."""
    buf = _capture_stderr(monkeypatch)
    w = _make_warning()

    emit_warning(w, dedupe=False)
    emit_warning(w, dedupe=False)

    lines = buf.getvalue().splitlines()
    assert len(lines) == 2
    assert "(×" not in lines[0]
    assert "(×" not in lines[1]


def test_dedup_registry_is_per_fingerprint(monkeypatch: pytest.MonkeyPatch):
    """Two distinct fingerprints don't cross-pollute counts."""
    buf = _capture_stderr(monkeypatch)
    w_telegram = _make_warning()
    w_redis = Warning(source="redis", kind="connection_timeout", detail="timed out")

    emit_warning(w_telegram)
    emit_warning(w_redis)
    emit_warning(w_telegram)  # second telegram

    lines = buf.getvalue().splitlines()
    # First two emissions are first-of-fingerprint, no suffix.
    assert "(×" not in lines[0]
    assert "(×" not in lines[1]
    # Third is the second telegram — gets (×2).
    assert "(×2)" in lines[2]


def test_emit_accepts_injected_registry(monkeypatch: pytest.MonkeyPatch):
    """Caller-provided registry isolates dedup state from module-level."""
    _capture_stderr(monkeypatch)
    w = _make_warning()
    registry: dict = {}

    emit_warning(w, _registry=registry)
    emit_warning(w, _registry=registry)

    assert registry[w.fingerprint()] == 2


def test_reset_dedup_registry_clears_module_state(monkeypatch: pytest.MonkeyPatch):
    """reset_dedup_registry() makes the next emission first-of-fingerprint again."""
    buf = _capture_stderr(monkeypatch)
    w = _make_warning()

    emit_warning(w)
    emit_warning(w)  # (×2)
    reset_dedup_registry()
    emit_warning(w)  # back to first-of-fingerprint

    lines = buf.getvalue().splitlines()
    assert "(×2)" in lines[1]
    assert "(×" not in lines[2]
