"""``macf_tools observe``: take an observation act through the agent's own primal daemon.

Each verb is one request to the daemon, which reads who is asking from the socket and takes
the act through ``observe.record`` (persistent_layer 5.4). The agent invites, pauses and
resumes from its live session. The operator fetches an invitation's secret once, from outside
the session, and relays it to the onlooker: the session is never shown it. Either side may
end an observation, and anyone with the uid may list them.
"""
import argparse
import sys
import time


def add_observe_parser(sub) -> None:
    obs = sub.add_parser("observe", help="let another agent watch this session, and stop it "
                                         "(policy: persistent_layer)")
    obs_sub = obs.add_subparsers(dest="observe_cmd")
    inv = obs_sub.add_parser("invite", help="invite an onlooker, from your live session; the operator "
                                            "fetches its secret and relays it")
    inv.add_argument("onlooker", help="the onlooker's calling card, Name@abc123")
    inv.add_argument("--lease", default=None, metavar="DURATION",
                     help="end the invitation on its own after this long: seconds, or 90s, 5m, 2h")
    inv.set_defaults(func=cmd_observe, op="observe_invite")
    sec = obs_sub.add_parser("secret", help="the operator, outside the session: print an invitation's secret, "
                                            "once, to relay to the onlooker")
    sec.add_argument("onlooker", help="the onlooker's calling card")
    sec.set_defaults(func=cmd_observe, op="observe_secret")
    for verb, op, text in (("pause", "observe_pause", "withhold what the session writes from now on, from your session"),
                           ("resume", "observe_resume", "let the stream go on from now, from your session"),
                           ("end", "observe_end", "end an observation: from the session as the observed agent, "
                                                  "from outside it as the operator")):
        p = obs_sub.add_parser(verb, help=text)
        p.add_argument("onlooker", help="the onlooker's calling card")
        p.set_defaults(func=cmd_observe, op=op)
    lst = obs_sub.add_parser("list", help="each onlooker's observation, as the event log says it stands")
    lst.set_defaults(func=cmd_observe, op="observe_list", onlooker=None)


def cmd_observe(args: argparse.Namespace) -> int:
    """0 when the daemon took the act (or listed); 1 when it refused or couldn't be reached."""
    from macf.pd.cli import _seconds, _this_agent
    from macf.pd.client import DaemonUnavailable, ask
    from macf.utils.session import get_current_session_id
    request = {"op": args.op}
    if args.onlooker is not None:
        request["onlooker"] = args.onlooker
    if args.op in ("observe_invite", "observe_pause", "observe_resume"):
        request["session_id"] = get_current_session_id()
    if getattr(args, "lease", None):
        try:
            request["lease_s"] = _seconds(args.lease)
        except ValueError as e:
            print(f"⚠️ MACF: observe: {e}", file=sys.stderr)
            return 1
    _, card = _this_agent()
    try:
        reply = ask(card, request)
    except DaemonUnavailable as e:
        print(f"⚠️ MACF: observe: no daemon answered ({e}); observation acts are taken by your primal daemon",
              file=sys.stderr)
        return 1
    if not reply.ok:
        print(f"⚠️ MACF: observe: refused: {reply.error}", file=sys.stderr)
        return 1
    if reply.secret is not None:
        print(reply.secret)
        print(f"The secret for {args.onlooker}, given once. Relay it to the onlooker yourself; "
              f"it is not shown again.", file=sys.stderr)
        return 0
    if args.op == "observe_invite":
        print(f"{args.onlooker} invited. Its secret is held by the daemon for the operator, who fetches it "
              f"from outside this session (macf_tools observe secret {args.onlooker}) and relays it.")
    _print_observations(reply.observations or [])
    return 0


def _print_observations(rows) -> None:
    if not rows:
        print("no observations")
        return
    for r in rows:
        line = f"{r['onlooker']}: {r['status']}"
        if r.get("lease_until"):
            line += f", lease until {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['lease_until']))}"
        if r.get("ended_by"):
            line += f", ended by {r['ended_by']}" + (" (advisory: not the live session)" if r.get("ended_by_advisory") else "")
        if r.get("secret_held"):
            line += ", secret not yet fetched"
        print(line)
