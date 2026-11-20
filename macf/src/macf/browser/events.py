"""One event per browser command in the agent's event log, with nothing of the page in it (MIS-0009 6.5)."""
import sys

# The only fields an event may carry. Page text, message content and typed values have no key here, so they
# can't be recorded by accident; the operator's own words for an act can (R17).
ALLOWED = {"backend", "plugin", "host", "tab", "reason", "count", "changed", "sha256", "bytes", "operator_said",
           "elapsed_s"}


def _append(name: str, data: dict) -> bool:
    from macf.agent_events_log import append_event
    return append_event(name, data)


def record(verb: str, decision: str, **fields) -> None:
    """Record one browser act: its verb, decision (allowed, refused, failed) and the allowed fields."""
    unknown = set(fields) - ALLOWED
    if unknown:
        raise ValueError(f"browser events carry no {sorted(unknown)}: page content stays out of the log "
                         f"(MIS-0009-R26)")
    data = {"verb": verb, "decision": decision}
    data.update({k: v for k, v in fields.items() if v is not None})
    if not _append("browser_act", data):
        print(f"⚠️ MACF: browser event for {verb} not recorded (continuing): the event log refused the append",
              file=sys.stderr)
