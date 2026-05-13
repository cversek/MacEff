"""Integration tests: macf.channels.telegram + observability.Warning.

Verifies the network-failure path translates into a structured Warning
that flows cleanly through emit_warning to both channels (stderr +
systemMessage). Also exercises NotifyResult backward-compat semantics so
existing ``bool()`` callers keep working.
"""
from __future__ import annotations

import io
import ssl
import sys
import urllib.error
import urllib.request

import pytest

from macf.channels.telegram import (
    NotifyResult,
    _build_network_warning,
    _classify_network_exception,
    send_telegram_notification,
)
from macf.observability import Warning, emit_warning, reset_dedup_registry


@pytest.fixture(autouse=True)
def _isolate_dedup():
    reset_dedup_registry()
    yield
    reset_dedup_registry()


def _fake_config(monkeypatch: pytest.MonkeyPatch, configured: bool = True):
    """Stub ``resolve_telegram_config`` so tests don't depend on a real
    Telegram setup."""
    if configured:
        monkeypatch.setattr(
            "macf.channels.telegram.resolve_telegram_config",
            lambda: ("FAKE_TOKEN", "12345"),
        )
    else:
        monkeypatch.setattr(
            "macf.channels.telegram.resolve_telegram_config",
            lambda: None,
        )


def _capture_stderr(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    return buf


# --- NotifyResult shape ---------------------------------------------------

def test_notifyresult_truthiness_matches_success():
    """bool(result) follows result.success — preserves the legacy bool API."""
    assert bool(NotifyResult(success=True)) is True
    assert bool(NotifyResult(success=False)) is False
    assert bool(NotifyResult(success=False, warning=Warning(
        source="telegram", kind="x", detail="y"
    ))) is False


# --- Classification helpers ----------------------------------------------

def test_classify_httperror_401_is_auth_failed():
    """HTTP 401 maps to a token-rejected diagnostic."""
    e = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    kind, cause, remediation = _classify_network_exception(e)
    assert kind == "auth_failed"
    assert "token" in cause.lower()
    assert "TELEGRAM_BOT_TOKEN" in remediation


def test_classify_httperror_500_is_telegram_5xx():
    """HTTP 5xx maps to a Telegram-side outage diagnostic."""
    e = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
    kind, _, _ = _classify_network_exception(e)
    assert kind == "telegram_api_5xx"


def test_classify_ssl_error_is_handshake_failed():
    """ssl.SSLError maps to TLS handshake diagnostic."""
    kind, cause, _ = _classify_network_exception(ssl.SSLError("handshake failed"))
    assert kind == "ssl_handshake_failed"
    assert "TLS" in cause


def test_classify_timeout_is_request_timeout():
    """TimeoutError maps to request_timeout."""
    kind, _, _ = _classify_network_exception(TimeoutError("slow"))
    assert kind == "request_timeout"


def test_classify_url_error_is_api_unreachable():
    """Bare URLError (DNS, conn refused, etc.) maps to api_unreachable."""
    kind, cause, _ = _classify_network_exception(
        urllib.error.URLError("name resolution failed")
    )
    assert kind == "api_unreachable"
    assert "api.telegram.org" in cause


def test_build_warning_includes_page_tag_when_paginated():
    """Multi-page failure includes 'page N/M' in detail."""
    w = _build_network_warning(ssl.SSLError("x"), page=2, total=3)
    assert "page 2/3" in w.detail


def test_build_warning_omits_page_tag_when_single_page():
    """Single-page failure omits the page tag."""
    w = _build_network_warning(ssl.SSLError("x"), page=1, total=1)
    assert "page" not in w.detail.lower()


# --- End-to-end: send_telegram_notification --------------------------------

def test_send_returns_success_when_urlopen_succeeds(monkeypatch: pytest.MonkeyPatch):
    """Happy path: urlopen returns, NotifyResult.success is True, no warning."""
    _fake_config(monkeypatch)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **kw: None
    )

    result = send_telegram_notification("hello")

    assert result.success is True
    assert result.warning is None
    assert bool(result) is True


def test_send_returns_warning_on_ssl_error(monkeypatch: pytest.MonkeyPatch):
    """SSL failure: NotifyResult carries a structured Warning with the right kind."""
    _fake_config(monkeypatch)

    def _raise(*a, **kw):
        raise ssl.SSLError("handshake error")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)

    result = send_telegram_notification("hello")

    assert result.success is False
    assert result.warning is not None
    assert result.warning.source == "telegram"
    assert result.warning.kind == "ssl_handshake_failed"
    assert "handshake error" in result.warning.detail


def test_send_returns_warning_on_http_401(monkeypatch: pytest.MonkeyPatch):
    """HTTP 401 from the API: NotifyResult.warning.kind is auth_failed."""
    _fake_config(monkeypatch)

    def _raise(*a, **kw):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _raise)

    result = send_telegram_notification("hello")

    assert result.success is False
    assert result.warning.kind == "auth_failed"


def test_send_returns_falsy_when_telegram_not_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    """No Telegram config: NotifyResult(success=False, warning=None)."""
    _fake_config(monkeypatch, configured=False)

    result = send_telegram_notification("hello")

    assert result.success is False
    assert result.warning is None
    assert bool(result) is False


def test_send_bails_on_first_page_failure_with_correct_page_tag(
    monkeypatch: pytest.MonkeyPatch,
):
    """Multi-page send fails on page 1 → warning carries 'page 1/N'."""
    _fake_config(monkeypatch)

    def _raise(*a, **kw):
        raise ssl.SSLError("x")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)

    # Force pagination: text longer than page_size.
    result = send_telegram_notification("X" * 9000, page_size=4000)

    assert result.warning is not None
    assert "page 1/" in result.warning.detail


# --- Integration: emit_warning consumes the returned Warning -------------

def test_warning_from_send_flows_through_emit_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    """End-to-end: send fails → caller passes Warning to emit_warning → both
    stderr and systemMessage carry the framed diagnostic."""
    _fake_config(monkeypatch)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(ssl.SSLError("certificate verify failed")),
    )
    stderr_buf = _capture_stderr(monkeypatch)

    result = send_telegram_notification("hello")
    assert result.warning is not None

    emission = emit_warning(result.warning)

    # Stderr line
    stderr_output = stderr_buf.getvalue()
    assert "telegram" in stderr_output
    assert "certificate verify failed" in stderr_output
    assert "TLS handshake" in stderr_output

    # systemMessage
    msg = emission["systemMessage"]
    assert "ssl_handshake_failed" in msg
    assert "TLS handshake" in msg
    assert "trust store" in msg  # remediation
