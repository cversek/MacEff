"""Tests for the proxy rewrite feature gate (MACF_PROXY_REWRITE, default OFF).

Rewriting mutates the message-array prefix and can invalidate Anthropic
prompt-cache prefix stability, so it must never be on unless explicitly
requested.
"""
import pytest

from macf.proxy.server import _rewrite_enabled


def test_rewrite_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MACF_PROXY_REWRITE", raising=False)
    assert _rewrite_enabled() is False


@pytest.mark.parametrize("value", ["off", "0", "false", "no", "", "  ", "banana"])
def test_rewrite_disabled_for_falsy_and_garbage(monkeypatch, value):
    monkeypatch.setenv("MACF_PROXY_REWRITE", value)
    assert _rewrite_enabled() is False


@pytest.mark.parametrize("value", ["on", "1", "true", "yes", "ON", "True", " yes "])
def test_rewrite_enabled_for_truthy(monkeypatch, value):
    monkeypatch.setenv("MACF_PROXY_REWRITE", value)
    assert _rewrite_enabled() is True
