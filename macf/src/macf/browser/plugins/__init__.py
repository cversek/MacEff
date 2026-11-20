"""Browser plugins: site adapters that declare their hosts and verbs, held to that declaration (MIS-0009 6.6).

A plugin is a module with PLUGIN (a Plugin), add_arguments(subparsers) and run(backend, args). Framework plugins
live in this package. An agent's private plugins live in its private plugin directory and never enter the
repository (R32); a private plugin can't take a framework plugin's name.
"""
import importlib
import importlib.util
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from macf.browser import guard


@dataclass(frozen=True)
class Plugin:
    name: str
    hosts: Tuple[str, ...]
    verbs: Tuple[str, ...]
    irreversible: Tuple[str, ...] = ()
    no_capture: bool = False
    origin: str = "framework"
    module: object = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        if not self.hosts:
            raise ValueError(f"plugin {self.name} declares no hosts (MIS-0009-R30)")
        if not self.verbs:
            raise ValueError(f"plugin {self.name} declares no verbs (MIS-0009-R30)")
        stray = set(self.irreversible) - set(self.verbs)
        if stray:
            raise ValueError(f"plugin {self.name} marks undeclared verbs irreversible: {sorted(stray)}")


def enforce(plugin: Plugin, verb: str, url: str, operator_said: Optional[str]) -> None:
    """Hold a plugin to its declaration before it acts (R31)."""
    if verb not in plugin.verbs:
        raise guard.Refused(f"plugin {plugin.name} declares no verb {verb!r} (MIS-0009-R31)")
    if not guard.host_in_scope(url, plugin.hosts):
        raise guard.Refused(f"plugin {plugin.name} may act only on {list(plugin.hosts)}, not "
                            f"{guard.host_of(url)} (MIS-0009-R31)")
    if verb in plugin.irreversible and not (operator_said or "").strip():
        raise guard.Refused(f"{plugin.name} {verb} is irreversible: it needs the operator's words (MIS-0009-R17)")


def _usable(module, origin: str) -> Optional[Plugin]:
    plugin = getattr(module, "PLUGIN", None)
    if not isinstance(plugin, Plugin) or not callable(getattr(module, "run", None)) \
            or not callable(getattr(module, "add_arguments", None)):
        print(f"⚠️ MACF: browser plugin {getattr(module, '__name__', '?')} skipped (not loaded): it needs "
              f"PLUGIN, add_arguments and run", file=sys.stderr)
        return None
    return Plugin(plugin.name, tuple(plugin.hosts), tuple(plugin.verbs), tuple(plugin.irreversible),
                  plugin.no_capture, origin, module)


def private_dir_default() -> Optional[Path]:
    """The agent's private plugin directory: {agent_home}/.maceff/browser_plugins (MIS-0009 Q02, provisional)."""
    try:
        from macf.utils import find_agent_home
        home = find_agent_home()
    except (ImportError, OSError, RuntimeError) as e:
        print(f"⚠️ MACF: agent home not found (no private browser plugins): {e}", file=sys.stderr)
        return None
    return Path(home) / ".maceff" / "browser_plugins" if home else None


def discover(private_dir: Optional[Path] = None) -> Dict[str, Plugin]:
    """Framework plugins from this package, then private ones from private_dir (R32)."""
    found: Dict[str, Plugin] = {}
    for info in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except ImportError as e:
            print(f"⚠️ MACF: browser plugin {info.name} failed to import (skipped): {e}", file=sys.stderr)
            continue
        plugin = _usable(module, "framework")
        if plugin:
            found[plugin.name] = plugin
    if private_dir and Path(private_dir).is_dir():
        for path in sorted(Path(private_dir).glob("*.py")):
            spec = importlib.util.spec_from_file_location(f"macf_private_browser_plugin_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as e:  # noqa: BLE001 - a private plugin's own failure must not stop the others; said below
                print(f"⚠️ MACF: private browser plugin {path.name} failed to load (skipped): {e}", file=sys.stderr)
                continue
            plugin = _usable(module, "private")
            if plugin is None:
                continue
            if plugin.name in found:
                print(f"⚠️ MACF: private browser plugin {path.name} skipped: {plugin.name!r} is a framework "
                      f"plugin's name", file=sys.stderr)
                continue
            found[plugin.name] = plugin
    return found
