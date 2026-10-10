"""The macOS rendering of a primal daemon: a per-user LaunchAgent.

MIS-0002-R05 (macos_MUST_render_LaunchAgent). A LaunchDaemon would run as root,
without the user's keychain or privacy grants, and its failures look like ordinary
network or authentication errors. A LaunchAgent in the user's GUI session holds what
the user holds. On macOS launchd is the outer tier: KeepAlive restarts the daemon
whenever it exits (MIS-0002-R03 (outer_tier_MUST_restart_pd)).

Rendering only. Nothing here runs launchctl; the argv it builds is for the installer.
"""
import plistlib
from typing import List, Optional, Tuple

PD_IDENTIFIER = "maceff_pd"
_VERBS = ("bootstrap", "bootout", "kickstart", "print")


def pd_label(card: str) -> str:
    """The launchd label for one agent's primal daemon: ``maceff_pd.<session identifier>``.

    MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd) names the identifier, and the
    calling card from the identity file makes it one per agent, never the environment
    (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)). The card maps to a name the
    same way every other surface of the daemon names it (the step-1 interface's
    ``session_identifier``), so ``IraMacEff@ee9a78`` becomes ``maceff_pd.IraMacEff_ee9a78``.
    """
    from macf.utils.identity import session_identifier
    if not card or "@" not in card:
        raise ValueError(f"not a calling card: {card!r} (expected Name@hexid)")
    ident = session_identifier(card)
    if not ident or "/" in ident:
        raise ValueError(f"not a calling card: {card!r}")
    return f"{PD_IDENTIFIER}.{ident}"


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
