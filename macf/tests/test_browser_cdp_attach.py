"""MIS-0009 R01, R02: the backend attaches only to a local endpoint; the launcher refuses the default profile."""
import pytest

from macf.browser import guard


def test_attaches_to_given_endpoint_only():
    from macf.browser import cdp
    assert cdp.endpoint_ok("http://localhost:9222")
    assert cdp.endpoint_ok("http://127.0.0.1:9333")
    for bad in ("http://10.0.0.5:9222", "ws://example.com:9222", "file:///tmp/x", ""):
        assert not cdp.endpoint_ok(bad)


@pytest.mark.parametrize("rel", ["Library/Application Support/Google/Chrome",
                                 "Library/Application Support/Chromium",
                                 ".config/google-chrome", ".config/chromium"])
def test_launcher_refuses_default_profile(rel, tmp_path, monkeypatch):
    from macf.browser import cdp
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(guard.Refused):
        cdp.check_profile_dir(tmp_path / rel)
    with pytest.raises(guard.Refused):
        cdp.check_profile_dir(tmp_path / rel / "Default")
    assert cdp.check_profile_dir(tmp_path / ".chrome-debug-profile") == (tmp_path / ".chrome-debug-profile").resolve()
