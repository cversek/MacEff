"""The outer tier: how one platform's service manager keeps an agent's primal daemon alive.

The core imports no platform code. Each supported platform supplies one adapter that
renders and installs the outer tier for an agent: a systemd user unit on Linux, a
LaunchAgent on macOS (MIS-0002-R05 (macos_MUST_render_LaunchAgent)). Whatever it
renders restarts the daemon whenever it exits (MIS-0002-R03 (outer_tier_MUST_restart_pd))
and holds no agent configuration beyond the agent home, which is the daemon's only
argument (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)).
"""
from pathlib import Path
from typing import Dict, List, Protocol, runtime_checkable

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

    def install(self, card: str, agent_home: Path) -> Path:
        """Write and load the rendered unit; return where it was written."""

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
