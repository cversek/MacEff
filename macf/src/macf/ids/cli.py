"""``macf_tools ids``: account and group numbers across the host and its containers."""
import argparse

from macf.ids import audit as ids_audit


def add_ids_parser(sub) -> None:
    ids = sub.add_parser("ids", help="uid and gid numbers across the host and its containers "
                                     "(policy: container_operations)")
    ids_sub = ids.add_subparsers(dest="ids_cmd")
    a = ids_sub.add_parser(
        "audit", help="name every uid or gid held by more than one identity across the host and "
                      "its running containers; exit 1 on an overlap, 2 when a place can't be read or nothing "
                      "was compared")
    a.add_argument("--container", action="append", dest="containers", metavar="NAME",
                   help="read only this container (repeatable); default: every running one")
    a.add_argument("--json", action="store_true", help="one JSON object")
    a.set_defaults(func=cmd_ids_audit)


def cmd_ids_audit(args: argparse.Namespace) -> int:
    report = ids_audit.audit(containers=args.containers)
    print(ids_audit.render_json(report) if args.json else ids_audit.render(report))
    return report.exit_code()
