"""Who gets told, and how often -- the two defects behind a nine-hour alert storm.

A health gate paged the operator every fifteen minutes for nine hours about two
messages sitting in the mailboxes of agents that have never run a session. EVERY
COMPONENT BEHAVED AS BUILT: watcher alive, watchdog alive, delivery correct,
custody correct, and the gate detected exactly the condition it was designed to
detect. **The defects were entirely in what the condition MEANT and WHO was told.**

Two rules, both the operator's, both from that incident. See
`macf_tools policy navigate notification_delivery`.

ROUTE BY WHO CAN ACT, NOT BY SEVERITY. A dead watcher and an undrained mailbox
are not differently severe; they are differently ADDRESSABLE. Paging a human for
a condition they cannot act on trains them to ignore the channel, which disarms
it for the case that matters. An alarm's value is not its accuracy -- it is the
recipient's remaining willingness to read it.

A BOUND ON ANOTHER PARTY'S ACTION IS MEASURED IN THAT PARTY'S OWN ACTIVE TIME.
"Un-ingested after N seconds during which the recipient was ALIVE." A party that
never ran has accrued zero. **Raising the threshold does not fix a wrong clock;
the condition simply arrives later, which is how a wrong clock disguises itself
as a tuning problem** -- and every tuning round makes the disguise better.
"""
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

# Who can remedy it. This is the routing axis; severity is not.
OPERATOR = "operator"
AGENT = "agent"
NOBODY = "nobody"

# What kind of thing it is.
SYSTEM_FAULT = "system_fault"
RECIPIENT_FAULT = "recipient_fault"
EXPECTED_STATE = "expected_state"
INSTRUMENT_GAP = "instrument_gap"

# Recipient liveness, as three states rather than two.
ALIVE = "alive"
INACTIVE = "inactive"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """One observation, carrying WHO CAN ACT rather than how bad it is."""

    key: str
    kind: str
    route: str
    message: str
    detail: dict = field(default_factory=dict)

    @property
    def pages(self) -> bool:
        """Does this wake a human RIGHT NOW?

        Only a system fault does, and only because no other party can remedy it
        and the agent may not be running to be told. Everything else either
        belongs to the agent or belongs in a status line.
        """
        return self.route == OPERATOR and self.kind == SYSTEM_FAULT


def classify_aged_pickup(
    box: str,
    entry: str,
    age_s: float,
    bound_s: float,
    liveness: str,
    active_s: Optional[float] = None,
) -> Finding:
    """An aged pickup entry means three completely different things.

    Wall-clock age alone cannot tell them apart, which is why the original check
    reported the passage of time as a fault.
    """
    key = f"pickup:{box}/{entry}"
    base = {"box": box, "entry": entry, "age_s": int(age_s), "bound_s": int(bound_s),
            "liveness": liveness}

    if liveness == INACTIVE:
        # NOT A FAULT. It is the normal state of a mailbox belonging to someone
        # who is not home. Kept as an observation rather than deleted, because it
        # is how you discover an agent nobody ever started -- which is exactly
        # what the incident revealed. Demote the alarm; keep the signal.
        return Finding(
            key=key, kind=EXPECTED_STATE, route=NOBODY,
            message=(f"box '{box}': {entry} un-ingested for {int(age_s)}s, but the "
                     f"recipient has not been active. Expected state, not a fault "
                     f"-- and it is how an agent nobody started becomes visible."),
            detail=base)

    if liveness == UNKNOWN:
        # Unknown accrual is not a fault of the mail system, and paging on it is
        # the incident. But it must not vanish either: the INSTRUMENT gap is
        # reported separately, so an unmeasurable recipient is a known unknown
        # rather than a silent pass.
        return Finding(
            key=f"liveness-unmeasurable:{box}", kind=INSTRUMENT_GAP, route=OPERATOR,
            message=(f"box '{box}': cannot measure whether the recipient has been "
                     f"active, so its {int(age_s)}s-old mail can be neither excused "
                     f"nor faulted. The instrument is missing, not the recipient."),
            detail=base)

    accrued = active_s if active_s is not None else age_s
    if accrued < bound_s:
        return Finding(
            key=key, kind=EXPECTED_STATE, route=NOBODY,
            message=(f"box '{box}': {entry} un-ingested {int(age_s)}s wall-clock but "
                     f"only {int(accrued)}s of recipient active time (bound "
                     f"{int(bound_s)}s). Within bound on the clock that matters."),
            detail={**base, "active_s": int(accrued)})

    # The real fault, and the only one of the four that is the recipient's:
    # it has been alive, past the bound, and has not drained.
    return Finding(
        key=key, kind=RECIPIENT_FAULT, route=AGENT,
        message=(f"box '{box}': {entry} un-ingested after {int(accrued)}s of "
                 f"recipient ACTIVE time (bound {int(bound_s)}s). The recipient has "
                 f"been running and has not drained its box."),
        detail={**base, "active_s": int(accrued)})


EVENT_LOG_RELPATH = Path(".maceff") / "agent_events_log.jsonl"


def event_log_liveness_probe(homes_root):
    """Build the liveness probe the sweep needs, from a marker that already exists.

    An agent's event log is this framework's canonical record that an agent DID
    SOMETHING. It is already the marker used to locate an agent's root, so it is
    a first-class fact rather than something invented for this check.

    THE ANSWER IS RELATIVE TO THE MAIL, not absolute. "Has this agent ever run?"
    is the wrong question -- an agent that ran for months and then stopped before
    the mail arrived has still accrued nothing against THIS delivery. So the
    probe compares the agent's last activity against the arrival it is judging.

    **THE PROBE IS THEREFORE PER-ENTRY, NOT PER-BOX**, and the first wiring of it
    got this wrong: it asked the question once per mailbox. Two messages in one
    box can land hours apart, and an agent that ran between them has accrued time
    against the older and none against the newer. A box-level answer silently
    applies the oldest entry's verdict to every entry beside it.

    Three outcomes, and the third is the one that matters most:

      log absent                  -> INACTIVE, zero accrued. The agent has never
                                     run. This is the incident's exact case.
      last activity <= arrival    -> INACTIVE for this entry. It has not run
                                     since the mail landed, so it has had no
                                     opportunity to drain it.
      last activity  > arrival    -> ALIVE, accruing from arrival to last
                                     activity.
      CANNOT STAT                 -> UNKNOWN, never INACTIVE. "I could not see
                                     it" is not "it never ran", and silently
                                     converting the first into the second would
                                     excuse a real fault on the strength of a
                                     permissions error.

    **This is a PROXY and is labelled as one.** The accrued figure spans arrival
    to last activity, which INCLUDES idle gaps in between -- so it OVER-counts
    active time and will call a fault slightly earlier than a true activity
    ledger would. That direction is deliberate: over-counting risks telling an
    agent about mail it is already handling, while under-counting risks the
    silence this subsystem exists to end. A real ledger would replace it without
    changing any caller.
    """
    root = Path(homes_root)

    def probe(box: str, arrived: Optional[float] = None):
        log = root / box / EVENT_LOG_RELPATH
        try:
            last_active = log.stat().st_mtime
        except FileNotFoundError:
            # Never ran. The one case the wall-clock check could not see.
            return (INACTIVE, 0.0)
        except (PermissionError, OSError) as e:
            print(f"⚠️ MACF: cannot stat activity marker for '{box}' "
                  f"(liveness UNKNOWN, not assumed): {e}", file=sys.stderr)
            return (UNKNOWN, None)
        if arrived is None:
            return (ALIVE, None)
        if last_active <= arrived:
            return (INACTIVE, 0.0)
        return (ALIVE, last_active - arrived)

    return probe


LIVENESS_MARKER = ".last-seen"


def box_marker_liveness_probe(handoff_root):
    """Liveness from a marker the recipient writes into its OWN pickup box.

    The event-log probe cannot be used where the broker is properly isolated: a
    deployment that separates broker and agent uids denies the broker any read
    into an agent home, which is the custody boundary doing its job. Measured in
    a real deployment: every stat of an agent's event log returns EACCES, and
    granting the broker that access to obtain a liveness signal would trade the
    boundary for a timestamp.

    The pickup box is the one surface both principals already share. It is
    broker-owned and setgid to the recipient's group, so the recipient can
    already create and remove entries there -- draining requires it -- and the
    broker can already stat it. A marker costs no new grant to either side.

    The marker is a DOTFILE and both readers ignore dotfiles: the sweep globs
    message suffixes and the store source filters on them, so a marker is not
    mail and cannot be mistaken for it.

    Outcomes match the event-log probe exactly, so the two are interchangeable
    at the call site:

      marker absent                -> INACTIVE, zero accrued.
      last touch <= arrival        -> INACTIVE for this entry.
      last touch  > arrival        -> ALIVE, accruing from arrival.
      cannot stat the box          -> UNKNOWN, never INACTIVE.

    DEPLOYMENT REQUIREMENT, stated because the probe is inert without it: some
    agent-side act must touch the marker when the agent runs. Nothing here does
    that, and until something does, this probe reports every recipient INACTIVE
    -- which suppresses alerts rather than raising false ones, so it fails in
    the quiet direction and must not be mistaken for a working signal.
    """
    root = Path(handoff_root)

    def probe(box: str, arrived: Optional[float] = None):
        marker = root / box / LIVENESS_MARKER
        try:
            last_active = marker.stat().st_mtime
        except FileNotFoundError:
            return (INACTIVE, 0.0)
        except (PermissionError, OSError) as e:
            print(f"⚠️ MACF: cannot stat liveness marker for '{box}' "
                  f"(liveness UNKNOWN, not assumed): {e}", file=sys.stderr)
            return (UNKNOWN, None)
        if arrived is None:
            return (ALIVE, None)
        if last_active <= arrived:
            return (INACTIVE, 0.0)
        return (ALIVE, last_active - arrived)

    return probe


def touch_liveness_marker(handoff_root, box: str) -> bool:
    """Record that this recipient is running. Called BY the recipient.

    Writes into the recipient's own pickup box, which it already has rights to
    modify. Returns False with a stated reason rather than raising: a liveness
    marker that cannot be written must not stop an agent working.
    """
    marker = Path(handoff_root) / box / LIVENESS_MARKER
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return True
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: could not touch liveness marker for '{box}' -- this agent "
              f"will be reported as INACTIVE and its undrained mail will not "
              f"alert: {e}", file=sys.stderr)
        return False


def classify_system(key: str, message: str, **detail) -> Finding:
    """A fault only the operator can remedy -- including every fault whose nature
    means the agent may not be running to be told about it."""
    return Finding(key=key, kind=SYSTEM_FAULT, route=OPERATOR, message=message, detail=detail)


@dataclass(frozen=True)
class Transitions:
    """Named rather than positional, because all three members are LISTS.

    Returned as a tuple, `new` and `ongoing` could be swapped without a single
    caller breaking loudly -- and the consequence of that swap is a notifier that
    stays silent on every genuinely new condition while re-notifying the ones it
    has already reported. That is the level-triggered defect restored by a
    refactor, undetectably.
    """

    new: List[Finding] = field(default_factory=list)
    ongoing: List[Finding] = field(default_factory=list)
    recovered: List[str] = field(default_factory=list)


class EdgeState:
    """Edge-triggered on ARRIVAL, never level-triggered on STATE.

    A condition that is true and remains true must produce ONE notice, not one
    per interval. The level-triggered form is not a lesser version of this: it
    converts a single fact into unbounded noise and is indistinguishable, to its
    recipient, from a broken notifier.

    **This project shipped the level-triggered version one cycle before writing
    the rule against it**, and nothing re-derived what already existed under the
    old rule. Writing a rule and sweeping what you already shipped against it are
    two separate acts, and only the first feels like work.

    Recovery is a notice too. A recipient told when something breaks and never
    when it heals has no way to learn the current state except by asking.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._prev: Dict[str, float] = self._load()

    def _load(self) -> Dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as fh:
                data = json.load(fh)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"⚠️ MACF: alert edge-state unreadable (treating as empty -- "
                  f"expect one repeat notice): {e}", file=sys.stderr)
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"⚠️ MACF: alert edge-state malformed (treating as empty -- "
                  f"expect one repeat notice): {e}", file=sys.stderr)
            return {}
        return data if isinstance(data, dict) else {}

    def transitions(self, findings: List[Finding], now: Optional[float] = None) -> "Transitions":
        """What changed since the last run, without writing anything.

        Separated from `commit` so a caller can decide to notify FIRST and record
        SECOND. Recording before delivering would lose a notice on a crash, and
        losing it silently is the failure this subsystem exists to end.
        """
        now = time.time() if now is None else now
        actionable = {f.key: f for f in findings if f.kind != EXPECTED_STATE}
        new = [f for k, f in actionable.items() if k not in self._prev]
        ongoing = [f for k, f in actionable.items() if k in self._prev]
        recovered = [k for k in self._prev if k not in actionable]
        return Transitions(new=new, ongoing=ongoing, recovered=recovered)

    def commit(self, findings: List[Finding], now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        actionable = {f.key: f for f in findings if f.kind != EXPECTED_STATE}
        state = {k: self._prev.get(k, now) for k in actionable}
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp, self.path)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"⚠️ MACF: alert edge-state write failed (the next run will "
                  f"re-notify): {e}", file=sys.stderr)
            return False
        self._prev = state
        return True


def route(findings: List[Finding]) -> Dict[str, List[Finding]]:
    """Group by who can act. If everything lands on the operator, the
    classification has not been done."""
    out: Dict[str, List[Finding]] = {OPERATOR: [], AGENT: [], NOBODY: []}
    for f in findings:
        out.setdefault(f.route, []).append(f)
    return out


def escalation_due(
    finding: Finding,
    notified_at: Optional[float],
    grace_s: float,
    now: Optional[float] = None,
) -> bool:
    """The operator is the terminus of LAST resort, not the default one.

    Escalate only when the ACTOR was notified and the condition persisted -- and
    when you do, say so: "the agent was notified at T and has not acted."
    A finding whose actor was never told has no escalation case at all, because
    nobody has failed to do anything yet.
    """
    if finding.route != AGENT:
        return False
    if notified_at is None:
        return False
    now = time.time() if now is None else now
    return (now - notified_at) >= grace_s
