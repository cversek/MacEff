"""Whether the agent's primal daemon runs its transcript monitor as a declared unit.

The operator's ruling: the transcript monitor runs under each agent's primal daemon, as a
declared service unit running ``python -m macf.transcript_monitor --follow``, so that it is
supervised, restarted and watched like every other unit. Where it is declared, the places
that used to fork a monitor for one session (the SessionStart hook, task creation, AUTO_MODE
entry, ``transcript-monitor start``) must leave it to the daemon: a second, ad-hoc monitor
would write every event twice and escape the supervision the unit exists for.

The declaration read is the one the daemon reads (``load_declaration``: the rendered,
root-owned copy in a container, the home's own on a host), with the same refusals. A
declaration the daemon would refuse starts no unit, so it counts as declaring none, and the
ad-hoc start goes on exactly as before.
"""
import sys
from pathlib import Path
from typing import Optional

#: The module the unit's command must run. Equal to ``transcript_monitor.daemon.MONITOR_MODULE``
#: (pinned by a test); not imported from there, so that asking costs no monitor import.
MONITOR_MODULE = "macf.transcript_monitor"


def declared_monitor_unit(agent_home: Optional[Path] = None) -> Optional[str]:
    """The name of the unit that runs the transcript monitor in this agent's declaration, or
    None when there is none: no declaration, a declaration the daemon would refuse, or no unit
    whose command runs ``macf.transcript_monitor``."""
    from macf.pd.names import declaration_path

    if agent_home is None:
        from macf.utils.paths import find_agent_home
        agent_home = find_agent_home()
    if not declaration_path(agent_home).exists():
        return None   # the normal case on a host without a primal daemon: nothing to read
    from macf.pd.core import DeclarationRefused, load_declaration
    from macf.pd.names import IdentityError, agent_card
    try:
        declaration = load_declaration(Path(agent_home), agent_card(Path(agent_home)))
    except (DeclarationRefused, IdentityError, OSError, ValueError) as e:
        # Said, because it changes who starts the monitor: the daemon refuses this declaration
        # too, so no unit runs it, and the caller starts one for the session as before.
        print(f"⚠️ MACF: the primal daemon declaration can't be used ({e}); the transcript "
              f"monitor is started for this session instead of by a unit", file=sys.stderr)
        return None
    for unit in declaration.units:
        if any(MONITOR_MODULE in arg for arg in unit.command):
            return unit.name
    return None


def declared_refusal(unit: str) -> str:
    """What ``transcript-monitor start`` says when a unit runs the monitor: what runs it, and
    where to look instead."""
    return (f"❌ The transcript monitor runs as unit '{unit}' of this agent's primal daemon, which "
            f"starts and restarts it; a monitor started here would run beside it and write every "
            f"event twice. See its state with 'macf_tools pd status'.")
