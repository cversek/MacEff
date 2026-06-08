"""Tests for macf.viz.markdown._open_in_browser.

Regression coverage for cversek/MacEff#113 — the silent-failure mode
when xdg-open dispatched to a hijacked text/html MIME handler. The fix
switched to Python's `webbrowser` module (web-browser scheme handler)
and added a clear manual-open fallback message instead of swallowing
failures.
"""
import webbrowser
from unittest.mock import patch

from macf.viz.markdown import _open_in_browser


def test_open_in_browser_uses_file_url():
    """Pass a file:// URL to webbrowser.open, not a raw filesystem path."""
    with patch("macf.viz.markdown.webbrowser.open", return_value=True) as mock_open:
        _open_in_browser("/tmp/macf_md_test.html")

    mock_open.assert_called_once_with("file:///tmp/macf_md_test.html")


def test_open_in_browser_silent_on_success(capsys):
    """No stderr noise when webbrowser.open returns True (browser launched)."""
    with patch("macf.viz.markdown.webbrowser.open", return_value=True):
        _open_in_browser("/tmp/macf_md_test.html")

    captured = capsys.readouterr()
    assert captured.err == ""


def test_open_in_browser_emits_manual_fallback_when_open_returns_false(capsys):
    """When webbrowser.open returns False, emit a clear manual-open line."""
    with patch("macf.viz.markdown.webbrowser.open", return_value=False):
        _open_in_browser("/tmp/macf_md_test.html")

    captured = capsys.readouterr()
    assert "Could not open browser" in captured.err
    assert "file:///tmp/macf_md_test.html" in captured.err
    assert "Open manually" in captured.err


def test_open_in_browser_emits_manual_fallback_on_webbrowser_error(capsys):
    """On webbrowser.Error (no browser registered), emit error + manual-open."""
    with patch("macf.viz.markdown.webbrowser.open",
               side_effect=webbrowser.Error("no browser found")):
        _open_in_browser("/tmp/macf_md_test.html")

    captured = capsys.readouterr()
    assert "Could not open browser" in captured.err
    assert "no browser found" in captured.err
    assert "file:///tmp/macf_md_test.html" in captured.err
    assert "Open manually" in captured.err


def test_open_in_browser_emits_manual_fallback_on_os_error(capsys):
    """On OSError (subprocess spawn failure inside webbrowser), surface it."""
    with patch("macf.viz.markdown.webbrowser.open",
               side_effect=OSError("subprocess spawn failed")):
        _open_in_browser("/tmp/macf_md_test.html")

    captured = capsys.readouterr()
    assert "Could not open browser" in captured.err
    assert "subprocess spawn failed" in captured.err
    assert "file:///tmp/macf_md_test.html" in captured.err
