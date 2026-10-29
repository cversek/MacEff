"""The primal daemon declaration ``macf_tools agent init`` writes for a host agent that has none.

A host agent's declaration lives in its own home, ``<home>/.maceff/pd/declaration.json``
(``names.declaration_path``; persistent_layer 10.1). This module builds the default one and
compares an existing declaration against it. It never writes: the caller validates the result
with the daemon's own ``Declaration`` model, writes it only where none exists, and otherwise
reports what the existing one lacks.

The default declares three units:

- ``session``: the agent's Claude Code session, through ``macf_tools harness unit`` in the
  agent's project directory (persistent_layer 6.2);
- ``monitor``: the transcript monitor, ``python -m macf.transcript_monitor --follow``;
- ``search``: the search service, ``python -m macf.search_service.daemon --unit``.

Every unit is started with the declared environment and nothing inherited (persistent_layer
10.2), so each names ``PATH`` and ``HOME``.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from macf.channels.marketplace import CHANNEL_PLUGIN, MARKETPLACE

#: Telegram's channel plugin as Claude Code's official marketplace names it.
TELEGRAM = ("telegram", "claude-plugins-official")

#: The modules the monitor and search units run. A unit of an existing declaration counts as
#: the default's unit when it runs the same module, whatever it is named.
MONITOR_MODULE = "macf.transcript_monitor"
SEARCH_MODULE = "macf.search_service.daemon"

#: The session's wrapper reaps the pane for 10 s after its server goes, so the session's stop
#: grace must exceed that (persistent_layer 6.2).
SESSION_STOP_GRACE_S = 30.0

#: The variables that name the login a unit runs as. They belong to the unit's account, not its
#: program, so drift reports them missing whatever command the unit runs (cversek/MacEff#848).
LOGIN_VARIABLES = ("USER", "LOGNAME")


def channel_flag(plugin: str, marketplace: str) -> str:
    """A channel as the harness's ``--channels`` takes it."""
    return f"plugin:{plugin}@{marketplace}"


def parse_channel_flag(flag: str) -> Optional[Tuple[str, str]]:
    """``plugin:<plugin>@<marketplace>`` as (plugin, marketplace), or None for another shape."""
    if not flag.startswith("plugin:") or flag.count("@") != 1:
        return None
    plugin, marketplace = flag[len("plugin:"):].split("@")
    return (plugin, marketplace) if plugin and marketplace else None


def detect_telegram(login_home: Path, harness_channels: Sequence[str] = ()) -> Optional[Tuple[str, str]]:
    """The Telegram channel plugin this agent uses, or None.

    Taken from what is already installed, never guessed: a Telegram channel the agent's harness
    settings record, else ``telegram@<marketplace>`` enabled in the login's Claude Code user
    settings."""
    for flag in harness_channels:
        found = parse_channel_flag(flag)
        if found and found[0] == "telegram":
            return found
    path = Path(login_home) / ".claude" / "settings.json"
    try:
        settings = json.loads(path.read_text())
    except FileNotFoundError:
        return None  # noqa: MACEFF003 - no user settings means no Telegram enabled there
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: agent init: {path} can't be read ({e}), so Telegram isn't declared "
              f"as an operator channel; pass --telegram to declare it", file=sys.stderr)
        return None
    enabled = settings.get("enabledPlugins") if isinstance(settings, dict) else None
    if isinstance(enabled, dict):
        for key, on in sorted(enabled.items()):
            if on and isinstance(key, str) and key.startswith("telegram@") and key.count("@") == 1:
                return ("telegram", key.split("@", 1)[1])
    return None


def mail_configured(agent_home: Path) -> bool:
    """Whether the agent's amail settings name its pickup box (``<home>/.maceff/amail.json``),
    the file the daemon's mail notices read. A box only guessed would deliver nothing.

    Without the ``amail`` extra the package refuses to import, so there is no mail to
    route: the answer is no, not a refusal of every step that asks (cversek/MacEff#843)."""
    try:
        from macf.amail.pickup import GUESSED, resolve_pickup_box
    except ImportError:
        return False
    try:
        _box, how = resolve_pickup_box(Path(agent_home), env={})
    except (OSError, ValueError):
        return False
    return how != GUESSED


def _placeheld(path: Path, agent_home: Path) -> str:
    """A path as the declaration names it: ``{agent_home}`` where it is the home itself."""
    return "{agent_home}" if Path(path).resolve() == Path(agent_home).resolve() else str(path)


def build(card: str, *, agent_home: Path, login_home: Path, account: str, python: Path,
          project_dir: Path, path_dirs: Sequence[str], mail: bool,
          telegram: Optional[Tuple[str, str]], runtime_dir: Optional[str] = None) -> Dict[str, Any]:
    """The default declaration for *card*, as the JSON object written to disk.

    *runtime_dir* is the ``XDG_RUNTIME_DIR`` the session unit declares, so its tmux server is
    where attach, harness status and the cutover look for it (persistent_layer 6.3). The
    caller passes it on Linux and not on macOS, which sets none."""
    path = ":".join(dict.fromkeys(d for d in path_dirs if d))
    # The declaration states a unit's whole environment (persistent_layer 6.3), so the login
    # each unit runs as is stated too: without it the session read its login as unknown, and a
    # home with no calling card would take "unknown" for its name (cversek/MacEff#848).
    env = {"PATH": path, "HOME": str(login_home), "MACEFF_AGENT_HOME_DIR": "{agent_home}",
           "USER": account, "LOGNAME": account}
    py = str(python)
    units = [
        {"name": "session", "kind": "session",
         "command": [py, "-m", "macf.cli", "harness", "unit", "--home", "{agent_home}",
                     "--project-dir", _placeheld(project_dir, agent_home)],
         "account": account, "restart": "always", "liveness_interval_s": 120,
         "memory_limit_mb": 16384, "stop_grace_s": SESSION_STOP_GRACE_S,
         "environment": {**env, **({"XDG_RUNTIME_DIR": runtime_dir} if runtime_dir else {})}},
        {"name": "monitor", "command": [py, "-m", MONITOR_MODULE, "--follow"],
         # persistent_layer 6.4: measured 15-40 MB per monitor; 128 MB reports a leak early.
         "account": account, "restart": "always", "liveness_interval_s": 30,
         "memory_limit_mb": 128, "environment": dict(env)},
        {"name": "search", "command": [py, "-m", SEARCH_MODULE, "--unit"],
         "account": account, "restart": "always", "liveness_interval_s": 60,
         # search_service 2.1: a running copy holds about 1.3 GB; 2048 MB leaves headroom.
         "memory_limit_mb": 2048, "environment": dict(env)},
    ]
    channels = ([{"plugin": telegram[0], "marketplace": telegram[1]}] if telegram else []) + \
        [{"plugin": CHANNEL_PLUGIN, "marketplace": MARKETPLACE}]
    declaration: Dict[str, Any] = {
        "version": 1,
        "agent": card,
        "units": units,
        "allowlisted_channels": channels,
        # The channel's events count as the operator's only for the operator's own channel;
        # an empty list declares that none is (persistent_layer 1.4).
        "operator_channels": [f"plugin:{telegram[0]}:{telegram[0]}"] if telegram else [],
        "notice_routes": {"amail": "agent"} if mail else {},
    }
    return declaration


def _unit_key(unit: Dict[str, Any]) -> str:
    """Which default unit an existing unit stands for: the session by kind, the monitor and
    search by the module they run, anything else by its name."""
    if unit.get("kind") == "session":
        return "session"
    command = [str(a) for a in unit.get("command") or []]
    if MONITOR_MODULE in command or any(MONITOR_MODULE.replace(".", "/") in a for a in command):
        return "monitor"
    if any(a.startswith("macf.search_service") for a in command):
        return "search"
    return str(unit.get("name"))


def drift(existing: Dict[str, Any], default: Dict[str, Any]) -> List[str]:
    """What an existing declaration lacks compared with the default, one line each; empty when
    it has every default unit, channel and notice route. Only absences are named: a value the
    agent chose differently is the agent's, not drift."""
    out = []
    have = {_unit_key(u): u for u in existing.get("units") or []}
    for unit in default["units"]:
        if _unit_key(unit) not in have:
            out.append(f"no {unit['name']} unit: the default runs {' '.join(unit['command'])}")
            continue
        # A variable the default states and the default's own unit doesn't is an absence too:
        # the unit runs with only what its declaration states, so a home declared before the
        # default gained USER and LOGNAME would never be told (cversek/MacEff#848). A unit
        # running a command of the agent's own keeps the rest of its environment as the
        # agent's; the login is still compared, since it is the account's, not the program's.
        mine = have[_unit_key(unit)]
        wanted = list(unit.get("environment") or {})
        if [str(a) for a in mine.get("command") or []] != [str(a) for a in unit["command"]]:
            wanted = [k for k in wanted if k in LOGIN_VARIABLES]
        stated = mine.get("environment") or {}
        missing = [k for k in wanted if k not in stated]
        if missing:
            out.append(f"the {unit['name']} unit's environment lacks {', '.join(missing)}")
    declared = {(c.get("plugin"), c.get("marketplace")) for c in existing.get("allowlisted_channels") or []}
    for c in default.get("allowlisted_channels") or []:
        if (c["plugin"], c["marketplace"]) not in declared:
            out.append(f"allowlisted_channels lacks {c['plugin']}@{c['marketplace']}")
    routes = existing.get("notice_routes") or {}
    for source, route in sorted((default.get("notice_routes") or {}).items()):
        if source not in routes:
            out.append(f"notice_routes does not route {source} (the default routes it to {route})")
    return out
