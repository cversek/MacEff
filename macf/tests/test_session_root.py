"""Per-session directories live under a root a test run can move."""
from pathlib import Path

from macf.hooks.hook_logging import log_hook_event


def test_session_root_defaults_and_follows_the_environment(monkeypatch, tmp_path):
    from macf.utils.paths import session_root

    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    assert session_root() == Path("/tmp/macf")
    monkeypatch.setenv("MACF_SESSION_ROOT", str(tmp_path))
    assert session_root() == tmp_path


def test_a_tests_hook_log_stays_out_of_the_live_session(monkeypatch, isolated_session_root):
    """A hook error logged by a test, with a live session's id in the environment, lands
    under the test run's root, not in that session's hook log under /tmp/macf."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "live-session-probe")
    log_hook_event({"hook_name": "probe", "event_type": "ERROR", "error": "a test's error"})

    assert list(isolated_session_root.glob("*/live-session-probe/hooks/hook_events.log"))
    assert not list(Path("/tmp/macf").glob("*/live-session-probe"))
