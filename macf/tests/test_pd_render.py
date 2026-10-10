"""Rendering a primal daemon for the host's own service manager.

This file holds the macOS rendering (MIS-0002 step 4). Linux renderings belong to
step 1 and get their own classes here.
"""
import plistlib
import shutil
import subprocess

import pytest

from macf.platform.launchd import launchctl_argv, pd_label, render_pd_launch_agent

CARD = "IraMacEff@ee9a78"
ARGV = ["/usr/bin/python3", "-m", "macf.pd", "--agent-home", "/Users/someone/agent"]


def _plist(**overrides):
    kwargs = dict(card=CARD, program_argv=ARGV, home="/Users/someone", log_dir="/tmp/maceff-logs")
    kwargs.update(overrides)
    path, data = render_pd_launch_agent(**kwargs)
    return path, plistlib.loads(data)


class TestMacOSLaunchAgent:
    """MIS-0002-R05 (macos_MUST_render_LaunchAgent), with R02, R03 and R06 as they apply on macOS."""

    def test_launchd_is_launchagent(self):
        """A per-user LaunchAgent in the user's GUI session, never a LaunchDaemon."""
        path, plist = _plist()
        assert path == "/Users/someone/Library/LaunchAgents/" + pd_label(CARD) + ".plist"
        assert "UserName" not in plist          # a LaunchDaemon key: root running as someone
        assert plist["LimitLoadToSessionType"] == "Aqua"

    def test_label_uses_maceff_pd_and_the_card(self):
        """R06's identifier, made unique per agent from the calling card, so two agents on
        one login never share a label."""
        assert pd_label(CARD) == "maceff_pd.IraMacEff_ee9a78"
        assert pd_label("ClaudeTheBuilder@6c888f") != pd_label(CARD)
        with pytest.raises(ValueError):
            pd_label("bad card/with slash")

    def test_launchd_restarts_the_daemon_whenever_it_exits(self):
        """On macOS launchd is the outer tier, so R03 is KeepAlive plus RunAtLoad."""
        _, plist = _plist()
        assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
        assert plist["ProgramArguments"] == ARGV

    def test_identity_never_travels_in_the_environment(self):
        """R02: the daemon reads its identity from the identity file, so the unit sets none."""
        _, plist = _plist()
        env = plist.get("EnvironmentVariables", {})
        assert not any(name.startswith("MACEFF_AGENT") for name in env)

    def test_launchctl_verbs_target_the_users_gui_domain(self):
        label = pd_label(CARD)
        argv = launchctl_argv("bootstrap", label, uid=501, plist_path="/x.plist")
        assert argv == ["launchctl", "bootstrap", "gui/501", "/x.plist"]
        assert launchctl_argv("kickstart", label, uid=501)[-1] == f"gui/501/{label}"
        with pytest.raises(ValueError):
            launchctl_argv("load", label, uid=501)   # the legacy verb is not offered

    @pytest.mark.live
    @pytest.mark.skipif(shutil.which("plutil") is None, reason="plutil is macOS-only")
    def test_rendered_plist_passes_plutil(self, tmp_path):
        _, data = render_pd_launch_agent(card=CARD, program_argv=ARGV, home=str(tmp_path), log_dir=str(tmp_path))
        target = tmp_path / "agent.plist"
        target.write_bytes(data)
        assert subprocess.run(["plutil", "-lint", str(target)], capture_output=True).returncode == 0
