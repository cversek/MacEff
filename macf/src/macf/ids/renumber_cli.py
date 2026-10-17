"""``macf_tools ids renumber``: the one-time move of a running deployment onto its declared ids."""
import argparse
import os
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from macf.ids import renumber as rn
from macf.models.agent_spec import AgentsConfig


def add_renumber_parser(ids_sub) -> None:
    p = ids_sub.add_parser(
        "renumber", help="move this container's accounts, groups and files onto the ids agents.yaml "
                         "declares; run as root inside the container BEFORE recreating it, seats stopped; "
                         "plans by default, changes nothing without --apply (policy: container_operations)")
    p.add_argument("--config", default="/etc/maceff/agents.yaml",
                   help="the agents.yaml declaring the id block (default: %(default)s)")
    p.add_argument("--service", action="append", default=[], metavar="NAME=NUMBER",
                   help="a deployment service account and its declared number in the block (repeatable)")
    p.add_argument("--root", action="append", default=[], metavar="PATH",
                   help="a bind mount to re-own as well (repeatable); the framework's own volumes are always included")
    p.add_argument("--listing", metavar="FILE", help="write every planned change, one per line, here")
    p.add_argument("--apply", action="store_true", help="re-own the files; without it, only plan")
    p.set_defaults(func=cmd_ids_renumber)


def cmd_ids_renumber(args: argparse.Namespace) -> int:
    try:
        raw = yaml.safe_load(Path(args.config).read_text())
        config = AgentsConfig(**raw)
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as e:
        print(f"ids renumber: cannot read the declaration {args.config}: {e}", file=sys.stderr)
        return 2
    services = {}
    for item in args.service:
        name, number = item.split("=", 1) if "=" in item else (item, "")
        if not name or not number.isdigit():
            print(f"ids renumber: --service takes NAME=NUMBER, not {item!r}", file=sys.stderr)
            return 2
        services[name] = int(number)
    try:
        mapping = rn.derive(config, services)
    except rn.RenumberRefused as e:
        print(f"ids renumber: REFUSED: {e}", file=sys.stderr)
        return 1
    roots = list(rn.FRAMEWORK_ROOTS) + list(args.root)
    block = range(config.ids.base, config.ids.base + 1000)
    p = rn.plan(mapping, roots, block=block)
    print(rn.render(mapping, p, [str(Path(r)) for r in args.root]))
    if args.listing:
        with open(args.listing, "w") as f:
            for path, ou, og, nu, ng in p.changes:
                f.write(f"{ou}:{og} -> {nu}:{ng}\t{path}\n")
            for path, u, g in p.unmapped:
                f.write(f"UNMAPPED {u}:{g}\t{path}\n")
            for path in p.setid_files:
                f.write(f"SETID\t{path}\n")
        print(f"listing: {args.listing}")
    if not args.apply:
        print("planned only; nothing changed (rerun with --apply)")
        return 0
    if os.geteuid() != 0:
        print("ids renumber: --apply needs root", file=sys.stderr)
        return 2
    running = rn.processes_on(mapping.uid)
    if running:
        print("ids renumber: REFUSED: processes still run as numbers this moves, and would write as "
              "their old number while their files move. Stop them first (container_operations 6.2, step 3):",
              file=sys.stderr)
        for pid, uid, comm in running:
            print(f"  pid {pid}  uid {uid}  {comm}", file=sys.stderr)
        return 1
    done, failed = rn.apply(p)
    left = rn.plan(mapping, roots, block=block)
    print(f"re-owned {done} file(s); left on an old number: {len(left.changes)}; "
          f"still outside the block: {len(left.unmapped)}")
    for path, why in failed[:20]:
        print(f"  could not re-own {path}: {why}", file=sys.stderr)
    if failed:
        print(f"  {len(failed)} path(s) failed; fix the cause and run --apply again: it resumes "
              f"where this stopped", file=sys.stderr)
    return 0 if not left.changes and not failed else 1
