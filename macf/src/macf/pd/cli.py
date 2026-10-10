"""``macf_tools pd``: the agent's primal daemon, from the command line.

Only ``status`` for now: it reads, and acts on nothing. Starting, stopping and restarting a
unit over the control socket must name who asks (MIS-0002-R52
(control_act_MUST_name_who_asked)), and which asker a command line typed in a session
claims is still an open question.
"""
import argparse
import json
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
        if "liveness" in unit:
            line += f"; liveness {unit['liveness']}: {unit['detail']}"
        print(line)
    return 0
