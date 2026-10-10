"""The macOS rendering of a primal daemon: a per-user LaunchAgent.

MIS-0002-R05 (macos_MUST_render_LaunchAgent). A LaunchDaemon would run as root,
without the user's keychain or privacy grants, and its failures look like ordinary
network or authentication errors. A LaunchAgent in the user's GUI session holds what
the user holds. On macOS launchd is the outer tier: KeepAlive restarts the daemon
whenever it exits (MIS-0002-R03 (outer_tier_MUST_restart_pd)).

Rendering only. Nothing here runs launchctl; the argv it builds is for the installer.
"""
import plistlib
import re
from typing import List, Optional, Tuple

PD_IDENTIFIER = "maceff_pd"
_CARD = re.compile(r"^([A-Za-z0-9_-]+)@([0-9a-f]+)$")
_VERBS = ("bootstrap", "bootout", "kickstart", "print")


def pd_label(card: str) -> str:
    """The launchd label for one agent's primal daemon.

    MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd) names the identifier; several
    agents can share one login, so the label adds the calling card, taken from the
    identity file and never from the environment (MIS-0002-R02
    (pd_MUST-NOT_take_identity_from_env)). ``Name@idfrag`` becomes ``maceff_pd.Name.idfrag``.
    """
    match = _CARD.match(card or "")
    if match is None:
        raise ValueError(f"not a calling card: {card!r} (expected Name@hexid)")
    return f"{PD_IDENTIFIER}.{match.group(1)}.{match.group(2)}"


def render_pd_launch_agent(card: str, program_argv: List[str], home: str,
                           log_dir: str) -> Tuple[str, bytes]:
    """The plist for one agent's primal daemon, and where it belongs.

    *program_argv* starts the daemon; the plist carries no declaration and no agent
    configuration (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)), and no
    identity in its environment.
    """
    if not program_argv:
        raise ValueError("program_argv is empty")
    label = pd_label(card)
    plist = {
        "Label": label,
        "ProgramArguments": list(program_argv),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Background",
        "StandardOutPath": f"{log_dir}/{label}.out.log",
        "StandardErrorPath": f"{log_dir}/{label}.err.log",
    }
    path = f"{home}/Library/LaunchAgents/{label}.plist"
    return path, plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


def launchctl_argv(verb: str, label: str, uid: int, plist_path: Optional[str] = None) -> List[str]:
    """The launchctl command for *verb* on this user's GUI domain.

    Only the domain-target verbs are offered; the legacy load/unload are not.
    """
    if verb not in _VERBS:
        raise ValueError(f"unsupported launchctl verb {verb!r}; use one of {', '.join(_VERBS)}")
    domain = f"gui/{uid}"
    if verb == "bootstrap":
        if not plist_path:
            raise ValueError("bootstrap needs the plist path")
        return ["launchctl", "bootstrap", domain, plist_path]
    if verb == "kickstart":
        return ["launchctl", "kickstart", "-k", f"{domain}/{label}"]
    return ["launchctl", verb, f"{domain}/{label}"]
