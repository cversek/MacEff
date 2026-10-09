"""
Test specifications for macf.utils.formatting module.

Regression coverage for get_claude_code_version() Strategy 1 (Linux
/proc-based detection), which previously exec'd any file whose path
contained the substring 'claude' — including our own hooks under
~/.claude/ — creating a self-sustaining fork loop on Linux hosts
(hook -> macf_tools env -> exec hook --version -> ...).
"""

import io
import builtins
import os
import platform
import sys
from unittest.mock import patch, Mock

import pytest

from macf.utils import formatting
from macf.utils.formatting import get_claude_code_version

REAL_SYSTEM = platform.system


FAKE_PPID = 999999


def _fake_proc_cmdline(monkeypatch, argv):
    """Route open() of /proc/FAKE_PPID/cmdline to an in-memory NUL-joined argv."""
    cmdline_bytes = b"\x00".join(a.encode() for a in argv) + b"\x00"
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path) == f"/proc/{FAKE_PPID}/cmdline":
            return io.BytesIO(cmdline_bytes)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Clear the lru_cache and neutralize non-Strategy-1 detection paths."""
    get_claude_code_version.cache_clear()
    monkeypatch.delenv("MACF_CC_VERSION", raising=False)
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("os.getppid", lambda: FAKE_PPID)
    monkeypatch.setattr("shutil.which", lambda _: None)
    yield
    get_claude_code_version.cache_clear()


class TestRunningSessionVersion:
    """The version of the session that is running, not of the launcher.

    An auto-update moves the launcher on PATH to a new version while a session
    keeps running the old one, and readouts then printed the new version for
    the old process.
    """

    def _launcher(self, monkeypatch, tmp_path, version):
        launcher = tmp_path / "launcher" / "claude"
        launcher.parent.mkdir()
        launcher.write_text(f'blah "{version} (Claude Code)" blah')
        monkeypatch.setattr("shutil.which", lambda _: str(launcher))

    def test_the_running_binary_wins_over_the_launcher(self, monkeypatch, tmp_path):
        self._launcher(monkeypatch, tmp_path, "2.1.290")
        monkeypatch.setenv("CLAUDE_PID", "4242")
        asked = []
        monkeypatch.setattr(formatting, "_running_executable",
                            lambda pid: asked.append(pid) or "/h/.local/share/claude/versions/2.1.281")
        assert get_claude_code_version() == "2.1.281"
        assert asked == [4242]

    def test_a_binary_without_a_version_in_its_name_is_read(self, monkeypatch, tmp_path):
        self._launcher(monkeypatch, tmp_path, "2.1.290")
        running = tmp_path / "claude"
        running.write_text('blah "2.1.200 (Claude Code)" blah')
        monkeypatch.setenv("CLAUDE_PID", "4242")
        monkeypatch.setattr(formatting, "_running_executable", lambda pid: str(running))
        assert get_claude_code_version() == "2.1.200"

    def test_without_a_running_session_the_launcher_answers(self, monkeypatch, tmp_path):
        self._launcher(monkeypatch, tmp_path, "2.1.290")
        assert get_claude_code_version() == "2.1.290"
        get_claude_code_version.cache_clear()
        monkeypatch.setenv("CLAUDE_PID", "4242")
        monkeypatch.setattr(formatting, "_running_executable", lambda pid: "")
        assert get_claude_code_version() == "2.1.290"

    @pytest.mark.skipif(REAL_SYSTEM() not in ("Darwin", "Linux"), reason="macOS and Linux only")
    def test_the_system_names_this_processs_own_binary(self, monkeypatch):
        monkeypatch.setattr("platform.system", REAL_SYSTEM)
        named = formatting._running_executable(os.getpid())
        assert os.path.realpath(named) == os.path.realpath(sys.executable)


class TestStrategy1HookRecursionRegression:
    """Strategy 1 must never exec a matched candidate file."""

    def test_skips_python_hook_in_parent_cmdline(self, monkeypatch, tmp_path):
        """
        A .py file under .claude/ in the parent cmdline (i.e. one of our
        own hooks) must be skipped entirely — not content-read, not exec'd.
        """
        hook = tmp_path / ".claude" / "hooks" / "session_start.py"
        hook.parent.mkdir(parents=True)
        hook.write_text("# hook script, no version pattern\n")
        _fake_proc_cmdline(monkeypatch, ["python3", str(hook), "--version"])

        run_mock = Mock(return_value=Mock(returncode=1, stdout=""))
        with patch("macf.utils.formatting.subprocess.run", run_mock):
            result = get_claude_code_version()

        exec_targets = [c.args[0][0] for c in run_mock.call_args_list]
        assert str(hook) not in exec_targets
        assert result == ""

    def test_never_execs_matched_candidate_without_version(self, monkeypatch, tmp_path):
        """
        Even a non-.py candidate matching 'claude' must not be exec'd when
        content extraction finds no version — the exec fallback is the
        dangerous half of the fork loop and was removed.
        """
        candidate = tmp_path / "claude"
        candidate.write_text("#!/bin/sh\necho not really claude\n")
        _fake_proc_cmdline(monkeypatch, ["sh", str(candidate)])

        run_mock = Mock(return_value=Mock(returncode=0, stdout="9.9.9 (Claude Code)"))
        with patch("macf.utils.formatting.subprocess.run", run_mock):
            result = get_claude_code_version()

        exec_targets = [c.args[0][0] for c in run_mock.call_args_list]
        assert str(candidate) not in exec_targets

    def test_extracts_version_from_genuine_bundle(self, monkeypatch, tmp_path):
        """A matched candidate whose content carries the CC version pattern works."""
        bundle = tmp_path / "claude"
        bundle.write_text('blah "2.1.99 (Claude Code)" blah')
        _fake_proc_cmdline(monkeypatch, ["node", str(bundle)])

        result = get_claude_code_version()

        assert result == "2.1.99"

    def test_env_var_override_wins(self, monkeypatch):
        """MACF_CC_VERSION short-circuits all detection strategies."""
        monkeypatch.setenv("MACF_CC_VERSION", "1.2.3")

        assert get_claude_code_version() == "1.2.3"


class TestFormatMacfBrand:
    """format_macf_brand — canonical banner first segment (issue #164)."""

    def test_bare_brand(self):
        from macf.utils.formatting import format_macf_brand
        assert format_macf_brand() == "🏗️ MACF"

    def test_auto_mode_true_appends_robot(self):
        from macf.utils.formatting import format_macf_brand
        assert format_macf_brand(auto_mode=True) == "🏗️ MACF 🤖"

    def test_auto_mode_false_bare(self):
        from macf.utils.formatting import format_macf_brand
        assert format_macf_brand(auto_mode=False) == "🏗️ MACF"

    def test_indicators_verbatim(self):
        from macf.utils.formatting import format_macf_brand
        assert format_macf_brand(indicators=" 🤖 ⚙️") == "🏗️ MACF 🤖 ⚙️"

    def test_indicators_take_precedence(self):
        from macf.utils.formatting import format_macf_brand
        assert format_macf_brand(auto_mode=True, indicators="") == "🏗️ MACF"

    def test_session_id_detection(self):
        from macf.utils.formatting import format_macf_brand
        with patch('macf.modes.auto.detect_auto_mode', return_value=(True, "event")):
            assert format_macf_brand(session_id="s-123") == "🏗️ MACF 🤖"

    def test_detection_failure_falls_back_to_bare(self):
        from macf.utils.formatting import format_macf_brand
        with patch('macf.modes.auto.detect_auto_mode', side_effect=OSError("boom")):
            assert format_macf_brand(session_id="s-123") == "🏗️ MACF"
