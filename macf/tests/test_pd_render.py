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
ARGV = ["/usr/bin/python3", "-m", "macf.pd", "/Users/someone/agent"]


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

    def test_identifier(self):
        """R06's conformance test on macOS: the identifier, made unique per agent from the
        calling card, so two agents on one login never share a label. It is the form
        the primal daemon's interface gives ``launchd_label``."""
        assert pd_label(CARD) == "maceff_pd.IraMacEff_ee9a78"
        assert pd_label("ClaudeTheBuilder@6c888f") != pd_label(CARD)
        with pytest.raises(ValueError):
            pd_label("bad card/with slash")

    def test_outer_tier_restarts_pd(self):
        """R03 on macOS: launchd is the outer tier, so it is KeepAlive plus RunAtLoad. The
        conformance row names this test; the Linux rendering adds its own half."""
        _, plist = _plist()
        assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
        assert plist["ProgramArguments"] == ARGV

    def test_units_outlive_the_daemons_exit(self):
        """launchd leaves the daemon's process group alone when the daemon dies, so its units,
        the session among them, keep running for the restarted daemon to re-adopt."""
        _, plist = _plist()
        assert plist["AbandonProcessGroup"] is True

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


class TestMacOSInstall:
    """Install and removal as plans, applied only when asked (MIS-0002-R05, R129)."""

    SOCKETS = ["/tmp/maceff_pd-501/IraMacEff_ee9a78.control.sock"]

    def test_socket_path_length(self):
        """R129: a socket path the kernel would refuse stops the install before anything is written."""
        from macf.amail.broker import SUN_PATH_MAX
        from macf.platform.launchd import install_plan
        too_long = "/tmp/" + "d" * SUN_PATH_MAX + "/x.sock"
        with pytest.raises(OSError, match="longer than"):
            install_plan(CARD, ARGV, "/Users/someone", "/tmp/logs", 501, [too_long])

    def test_install_writes_the_plist_then_bootstraps(self):
        from macf.platform.launchd import install_plan
        steps = install_plan(CARD, ARGV, "/Users/someone", "/tmp/logs", 501, self.SOCKETS)
        assert [s.what for s in steps] == ["write", "launchctl"]
        assert steps[0].path.endswith("/Library/LaunchAgents/maceff_pd.IraMacEff_ee9a78.plist")
        assert steps[1].argv == ["launchctl", "bootstrap", "gui/501", steps[0].path]

    def test_apply_refuses_to_overwrite_a_changed_plist(self, tmp_path):
        from macf.platform.launchd import apply_plan, install_plan
        steps = install_plan(CARD, ARGV, str(tmp_path), str(tmp_path), 501, self.SOCKETS)
        ran = []
        ok = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
        assert apply_plan(steps, run=lambda argv: ran.append(argv) or ok)[0].startswith("write ")
        assert ran == [steps[1].argv]
        with open(steps[0].path, "ab") as fh:
            fh.write(b"<!-- hand edit -->")
        with pytest.raises(FileExistsError):
            apply_plan(steps, run=lambda argv: ok)
        apply_plan(steps, run=lambda argv: ok, force=True)

    def test_a_failed_launchctl_is_said_not_hidden(self, tmp_path):
        from macf.platform.launchd import apply_plan, uninstall_plan
        bad = type("R", (), {"returncode": 5, "stdout": "", "stderr": "Boot-out failed: 5: Input/output error"})
        with pytest.raises(RuntimeError, match="Input/output error"):
            apply_plan(uninstall_plan(CARD, str(tmp_path), 501), run=lambda argv: bad)

    def test_status_reads_launchctl_print(self):
        """Shapes measured on macOS: running with a pid, loaded but stopped, and absent."""
        from macf.platform.launchd import parse_print
        running = parse_print("\tstate = running\n\truns = 1\n\tpid = 8741\n\tlast exit code = (never exited)\n")
        assert running.loaded and running.running and running.pid == 8741
        stopped = parse_print("\tstate = not running\n\truns = 1\n\tlast exit code = 0\n")
        assert stopped.loaded and not stopped.running and stopped.pid is None and stopped.last_exit == "0"
        absent = parse_print('Bad request.\nCould not find service "maceff_pd.X_000000" in domain for user gui: 501\n')
        assert not absent.loaded and not absent.running


class TestMacOSFollowsTheInterface:
    """The label and the socket limit come from the step-1 interface, so one place names them."""

    def test_the_label_is_the_interfaces(self):
        from macf.pd.interface import launchd_label
        from macf.platform.launchd import pd_label
        assert pd_label(CARD) == launchd_label(CARD)
