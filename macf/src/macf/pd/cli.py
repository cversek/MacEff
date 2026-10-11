"""``macf_tools pd``: the agent's primal daemon, from the command line.

``status`` reads; ``install`` and ``uninstall`` put the daemon under this platform's service
manager and take it out. Starting, stopping and restarting a unit over the control socket
must name who asks (MIS-0002-R52 (control_act_MUST_name_who_asked)), and which asker a
command line typed in a session claims is still an open question, so no unit act is here.
"""
import argparse
import json
import os
import sys
import time
from typing import Optional


def add_pd_parser(sub) -> None:
    pd = sub.add_parser("pd", help="the agent's primal daemon and its units (policy: persistent_layer)")
    pd_sub = pd.add_subparsers(dest="pd_cmd")
    show = pd_sub.add_parser(
        "status", help="each declared unit's state: from the daemon when it checks out, "
                       "else from the event log, saying which")
    show.add_argument("--json", action="store_true", help="one JSON object")
    show.set_defaults(func=cmd_pd_status)
    inst = pd_sub.add_parser(
        "install", help="put this agent's primal daemon under the platform's service manager and "
                        "start it; a declaration that fails installs nothing")
    inst.add_argument("--plan", action="store_true", help="print the unit it would install, and change nothing")
    inst.add_argument("--force", action="store_true", help="replace an installed unit that differs")
    inst.set_defaults(func=cmd_pd_install)
    rm = pd_sub.add_parser(
        "uninstall", help="stop this agent's primal daemon and remove its unit; the units it "
                          "supervises keep running, for a later daemon to adopt")
    rm.set_defaults(func=cmd_pd_uninstall)
    alive = pd_sub.add_parser(
        "alive", help="write one liveness event for the unit this process runs as (for shell "
                      "units, once per pass); does nothing outside a primal daemon (MIS-0002-R14)")
    alive.add_argument("--in-flight", type=int, default=None, metavar="N",
                       help="work started and not finished, which the daemon checks before a restart")
    alive.set_defaults(func=cmd_pd_alive)


def cmd_pd_alive(args: argparse.Namespace) -> int:
    """0 when written, or when the environment names no unit (run outside a daemon); 1 when it
    names one unusably or the event log refused the write."""
    from macf.pd import liveness
    if not (os.environ.get(liveness.ENV_UNIT) or os.environ.get(liveness.ENV_INTERVAL)):
        return 0
    found = liveness.unit_from_env()
    if found is None:
        return 1
    return 0 if liveness.emit(found.card, found.unit, found.interval_s, args.in_flight) else 1


def _when(epoch: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch)) if epoch else "never"


def cmd_pd_status(args: argparse.Namespace) -> int:
    # Every macf_tools call builds the parser, so what only this command needs
    # (pydantic, through the interface) is imported when it runs.
    from dataclasses import asdict

    from macf.pd.client import status
    from macf.pd.core import POLICY_POINTER, DeclarationRefused
    from macf.pd.daemon import card_for_home
    from macf.utils.paths import find_agent_home

    home = find_agent_home()
    try:
        card = card_for_home(home)
    except DeclarationRefused as e:
        print(f"maceff_pd: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    report = status(home, card)
    if args.json:
        print(json.dumps(asdict(report), default=str))
        return 0
    if report.source == "none":
        print(f"{card}: {report.why}")
        return 0
    print(f"{card}: from the {report.source} ({report.why})")
    for unit in report.units:
        line = f"  {unit['unit']}: {unit.get('state') or 'no state recorded'}"
        if unit.get("pid"):
            line += f", pid {unit['pid']}"
        line += f", since {_when(unit.get('since'))}"
        if unit.get("restart_held_until"):
            line += f"; restart held until {unit['restart_held_until']} (quiet window)"
        if "liveness" in unit:
            line += f"; liveness {unit['liveness']}: {unit['detail']}"
        print(line)
    return 0


def _this_agent():
    """The agent home, resolved, and the card its own files name, or the refusal's reason."""
    from pathlib import Path

    from macf.pd.daemon import card_for_home
    from macf.utils.paths import find_agent_home

    home = Path(find_agent_home()).resolve()
    return home, card_for_home(home)


def cmd_pd_install(args: argparse.Namespace) -> int:
    from pathlib import Path

    from macf.pd import adapter as adapters
    from macf.pd.core import POLICY_POINTER, DeclarationRefused, load_declaration

    try:
        home, card = _this_agent()
        load_declaration(home, card)
        tier = adapters.adapter_for(sys.platform)
    except (DeclarationRefused, LookupError) as e:
        print(f"maceff_pd: nothing installed: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    import macf
    runs = f"it runs {sys.executable}, with macf from {Path(macf.__file__).resolve().parent}"
    if args.plan:
        print(f"# {card}: the outer tier for {home} on {sys.platform}, not installed (--plan); {runs}")
        print(tier.render(card, home))
        return 0
    try:
        where = tier.install(card, home, force=args.force)
    except (OSError, RuntimeError) as e:
        print(f"maceff_pd: install stopped: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    print(f"{card}: installed at {where}; {runs}; the service manager says: {tier.status(card)}")
    if sys.platform.startswith("linux"):
        import os
        import pwd

        from macf.platform.systemd import linger_enabled
        if linger_enabled(pwd.getpwuid(os.getuid()).pw_name) is False:
            print("note: linger is off, so the daemon stops at your last logout; "
                  "`loginctl enable-linger` keeps it running, and is the host operator's call")
    return 0


def cmd_pd_uninstall(args: argparse.Namespace) -> int:
    from macf.pd import adapter as adapters
    from macf.pd.core import POLICY_POINTER, DeclarationRefused

    try:
        _home, card = _this_agent()
        tier = adapters.adapter_for(sys.platform)
        tier.uninstall(card)
    except (DeclarationRefused, LookupError, OSError, RuntimeError) as e:
        print(f"maceff_pd: uninstall stopped: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    print(f"{card}: uninstalled; the service manager says: {tier.status(card)}")
    return 0
