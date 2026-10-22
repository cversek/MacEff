"""The outer tier: how one platform's service manager keeps an agent's primal daemon alive.

The core imports no platform code. Each supported platform supplies one adapter that
renders and installs the outer tier for an agent: a systemd user unit on Linux, a
LaunchAgent on macOS (MIS-0002-R05 (macos_MUST_render_LaunchAgent)). Whatever it
renders restarts the daemon whenever it exits (MIS-0002-R03 (outer_tier_MUST_restart_pd))
and holds no agent configuration beyond the agent home, which is the daemon's only
argument (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)).
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable

#: The platforms MacEff supports, by ``sys.platform`` value. Each needs an adapter
#: before the daemon can be installed there (MIS-0002-R10 (CI_MUST_fail_unrendered_unit)).
SUPPORTED_PLATFORMS = ("linux", "darwin")


@runtime_checkable
class PlatformAdapter(Protocol):
    """What every platform's outer tier provides."""

    #: The ``sys.platform`` value this adapter serves.
    platform: str

    def render(self, card: str, agent_home: Path) -> str:
        """The outer tier's unit text for this agent, with nothing in it but the home."""

    def install(self, card: str, agent_home: Path, force: bool = False) -> Path:
        """Write and load the rendered unit; return where it was written. An installed unit
        that differs from the rendering is refused unless ``force``."""

    def uninstall(self, card: str) -> None:
        """Unload and remove the unit, leaving the agent's home untouched."""

    def status(self, card: str) -> str:
        """What the service manager reports for the unit, in its own words."""


_ADAPTERS: Dict[str, PlatformAdapter] = {}


def register(adapter: PlatformAdapter) -> None:
    """Make an adapter the one for its platform. A second for the same platform is refused."""
    if not isinstance(adapter, PlatformAdapter):
        raise TypeError(f"{adapter!r} does not provide the platform adapter interface")
    if adapter.platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"{adapter.platform!r} is not a supported platform {SUPPORTED_PLATFORMS}")
    if adapter.platform in _ADAPTERS:
        raise ValueError(f"an adapter for {adapter.platform} is already registered")
    _ADAPTERS[adapter.platform] = adapter


def adapter_for(platform: str) -> PlatformAdapter:
    try:
        return _ADAPTERS[platform]
    except KeyError:
        raise LookupError(f"no outer tier is registered for {platform}") from None


def missing_renderings() -> List[str]:
    """The supported platforms that have no adapter yet (MIS-0002-R10)."""
    return [p for p in SUPPORTED_PLATFORMS if p not in _ADAPTERS]


def _program(agent_home: Path) -> List[str]:
    """The daemon's command line: the agent home is its only argument (MIS-0002-R04)."""
    return [sys.executable, "-m", "macf.pd", str(agent_home)]


def _run(argv: List[str]):
    # The C locale, so a service manager's messages are the ones matched below, whatever
    # language the host speaks.
    return subprocess.run(argv, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"})


class LaunchdAdapter:
    """macOS: a per-user LaunchAgent, rendered and loaded by ``macf.platform.launchd``."""

    platform = "darwin"

    def __init__(self, user_home: Optional[Path] = None, uid: Optional[int] = None,
                 run: Callable = _run):
        self._home = str(user_home or Path.home())
        self._uid = os.getuid() if uid is None else uid
        self._run = run

    @staticmethod
    def _log_dir(agent_home: Path) -> str:
        return str(Path(agent_home) / ".maceff" / "pd" / "log")

    def render(self, card: str, agent_home: Path) -> str:
        from macf.platform import launchd
        _path, plist = launchd.render_pd_launch_agent(card, _program(agent_home), self._home,
                                                      self._log_dir(agent_home))
        return plist.decode("utf-8")

    def install(self, card: str, agent_home: Path, force: bool = False) -> Path:
        from macf.pd.interface import channel_socket, control_socket, events_socket
        from macf.platform import launchd
        argv, log_dir = _program(agent_home), self._log_dir(agent_home)
        steps = launchd.install_plan(card, argv, self._home, log_dir, self._uid,
                                     [str(control_socket(card)), str(channel_socket(card)),
                                      str(events_socket(card))])
        launchd.apply_plan(steps, run=self._run, force=force)
        return Path(launchd.render_pd_launch_agent(card, argv, self._home, log_dir)[0])

    def uninstall(self, card: str) -> None:
        from macf.platform import launchd
        launchd.apply_plan(launchd.uninstall_plan(card, self._home, self._uid), run=self._run)

    def probe_grants(self, card: str, agent_home: Path, grants: List[str]) -> Dict[str, str]:
        """Each grant's verdict from the launchd context (MIS-0002-R64
        (adapter_MUST_test_grants_at_install)): a one-shot job run with the daemon's own
        interpreter, loaded from the daemon's state directory and booted out after."""
        import tempfile
        from macf.platform import launchd
        log_dir = self._log_dir(agent_home)
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(Path(agent_home) / ".maceff" / "pd")) as work:
            return launchd.run_grant_probe(card, _program(agent_home)[0], list(grants), work, log_dir,
                                           self._uid, self._run)

    def status(self, card: str) -> str:
        from macf.platform import launchd
        out = self._run(launchd.launchctl_argv("print", launchd.pd_label(card), self._uid))
        # launchctl print's own answers, measured on macOS 15.5: 113 for a service the user's
        # domain doesn't have, and 112 when there is no gui/<uid> domain at all, as over SSH or
        # at the login window (3.1).
        if out.returncode == 113:
            return "not loaded"
        if out.returncode == 112:
            return f"no GUI session for uid {self._uid}, so no LaunchAgent can run"
        if out.returncode != 0:
            return f"unknown: {(out.stderr or '').strip() or f'launchctl exit {out.returncode}'}"
        state = launchd.parse_print(out.stdout)
        words = ["running" if state.running else "loaded"]
        if state.pid:
            words.append(f"pid {state.pid}")
        if state.last_exit:
            words.append(f"last exit {state.last_exit}")
        return ", ".join(words)


class SystemdAdapter:
    """Linux: a systemd user unit, rendered by ``macf.platform.systemd``."""

    platform = "linux"

    def __init__(self, user_home: Optional[Path] = None, run: Callable = _run):
        self._home = str(user_home or Path.home())
        self._run = run

    def _unit(self, card: str, agent_home: Path):
        from macf.platform import systemd
        return systemd.render_pd_user_unit(card, _program(agent_home), self._home)

    def render(self, card: str, agent_home: Path) -> str:
        return self._unit(card, agent_home)[1]

    def install(self, card: str, agent_home: Path, force: bool = False) -> Path:
        from macf.pd.interface import channel_socket, check_socket_path, control_socket, events_socket
        from macf.platform import systemd
        # Every socket the daemon will bind is checked before anything is written, as the
        # LaunchAgent's plan does, so a path too long stops the install with its reason
        # rather than the daemon failing at bind (MIS-0002-R129 (adapter_MUST_check_socket_path_length)).
        for sock in (control_socket(card), channel_socket(card), events_socket(card)):
            check_socket_path(sock)
        path, text = self._unit(card, agent_home)
        path = Path(path)
        if path.exists() and path.read_text() != text and not force:
            raise FileExistsError(f"{path} exists and differs from the rendered unit; "
                                  f"review it, then install with force")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)  # whole or not at all
        for argv in (systemd.systemctl_argv("daemon-reload"), systemd.systemctl_argv("enable", path.name)):
            out = self._run(argv)
            if out.returncode != 0:
                raise RuntimeError(f"{' '.join(argv)} failed: {out.stderr.strip()}")
        return path

    def uninstall(self, card: str) -> None:
        from macf.pd.interface import systemd_unit
        from macf.platform import systemd
        name = systemd_unit(card)
        for verb in ("stop", "disable"):
            out = self._run(systemd.systemctl_argv(verb, name))
            if out.returncode == 0:
                continue
            said = out.stderr.strip()
            # A unit that was never loaded has nothing to stop or disable, and removal goes on.
            # Any other failure stops it, so a unit still running is never left without its file.
            if "not loaded" not in said and "does not exist" not in said:
                raise RuntimeError(f"systemctl {verb} {name} failed ({out.returncode}): {said}")
            print(f"⚠️ MACF: pd: systemctl {verb} {name}: {said}", file=sys.stderr)
        path = Path(self._home) / ".config" / "systemd" / "user" / name
        if path.exists():
            path.unlink()
        self._run(systemd.systemctl_argv("daemon-reload"))

    def status(self, card: str) -> str:
        from macf.pd.interface import systemd_unit
        from macf.platform import systemd
        out = self._run(systemd.systemctl_argv("show", systemd_unit(card)))
        if out.returncode != 0:
            return f"unknown: {out.stderr.strip()}"
        return ", ".join(line for line in out.stdout.splitlines() if line)


register(LaunchdAdapter())
register(SystemdAdapter())
