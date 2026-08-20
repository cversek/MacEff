"""Internet-inbound processing — the broker's consumption of the ingest spool.

Implements the inbound-system specification (agent design record; merging
into the amail policy after review): the transport layer authenticates and
spools; THIS module is where the broker verifies, authorizes, delivers or
quarantines, and accounts for every spooled message. One owner per gate:
upstream authenticates transport identity, the broker alone authorizes
senders.

The trust chain this module completes:

    spool (single-writer: the receiver's uid; no agent path to it)
      -> hash re-verified against the sidecar    (corruption check ONLY --
         the same uid writes both files, so forgery is excluded by the
         spool's permissions, never by this comparison)
      -> provenance extracted FROM THE RAW BYTES (the sidecar's copy is
         advisory: authorization must not rest on a summary one component
         away from the evidence)
      -> authorization at the contacts file      (deny / deliver / deliver
         with push-wake)
      -> delivery BEFORE spool deletion, quarantine never silent deletion
      -> one terminal audit record per spooled message (the conservation
         property: a drop becomes a number that does not balance)

Push-wake eligibility is DERIVED, never declared: a grant on an address in
the agent namespace is a fatal configuration error (checked at startup and
re-checked per decision, since both inputs can change at runtime), and the
audit-history backstop FAILS CLOSED when its evidence is missing.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .broker import BrokerConfig
from .contacts import ContactBook, ContactListError
from .audit import AuditLog
from . import store


class SpoolError(ValueError):
    """A spool entry that cannot be processed as spooled mail."""


class PushEligibilityError(ContactListError):
    """A push-wake grant that the derivation forbids. FATAL at startup and at
    decision time alike: a violation discovered while running is the same
    violation, later."""


#: Terminal dispositions — the exhaustive set the conservation check balances.
#: The broker's terminal for accepted mail is HANDOFF, not delivery: under
#: the pickup-box model the broker places authorized mail in a per-recipient
#: box it owns, and the RECIPIENT executes the custody transfer by ingesting
#: into its own store as itself. No component ever writes across a uid
#: boundary, so nothing on the mail path needs privilege.
HANDED_OFF = "handed-off"
QUARANTINED = "quarantined"
#: Non-terminal: recorded when an entry is first seen, paired by one terminal.
SEEN = "spool_seen"

#: Delivery classes the authorization step can produce.
DELIVER_PULL = "deliver-pull"
DELIVER_PUSH_WAKE = "deliver-push-wake"
DENY = "deny"


@dataclass
class InboundConfig:
    """Wiring for the spool consumer. Paths and the verdict authority; the
    broker's own config supplies domain, homes, contacts, and audit."""

    broker_config: BrokerConfig
    spool_dir: Path
    quarantine_dir: Path
    #: The pickup boxes: handoff_dir/<agent>/ is broker-owned, group-readable
    #: (and group-deletable) by exactly that agent. Deployment provisions the
    #: per-agent group and setgid bit; this code only ever writes 0640 files.
    handoff_dir: Path = Path("/var/lib/amail/handoff")
    #: The authserv-id this deployment trusts in Authentication-Results
    #: headers (a binding fact — e.g. the MX operator's identifier). A
    #: verdict stamped by anyone else is treated as absent.
    verdict_authority: str = ""
    #: While the wake mechanism is unbuilt, no path may produce the
    #: push-wake outcome: a granted, eligible sender delivers as pull with
    #: the degradation visible. Default OFF is itself the control —
    #: enabling push-wake is a deliberate deployment act, never a side
    #: effect of granting a contact.
    push_wake_enabled: bool = False

    #: Orphan-sweep age bounds, in seconds. A spool entry older than this
    #: was never processed (a dead consumer, or one that crashed mid-run); a
    #: pickup-box entry older than this is a recipient that has stopped
    #: draining. Both
    #: are facts the operator must learn FROM THE SYSTEM rather than from
    #: silence, which is the whole point of the sweep.
    spool_age_bound_s: int = 3600
    pickup_age_bound_s: int = 86400


# --------------------------------------------------------------- provenance

# Authentication-Results result extraction: "method=result" pairs, per the
# header's registered grammar. Parsed leniently on purpose — the header is
# evidence to weigh, and a parse failure must read as "no verdict", never
# crash authorization.
_METHOD_RESULT = re.compile(r"\b(dmarc|spf|dkim|arc)\s*=\s*([a-zA-Z0-9]+)")
#: The domain DMARC evaluation aligned, as the authority reported it. Anchored
#: to `header.from=` so it reads the authority's own statement about which
#: domain passed, not a domain appearing anywhere in the header.
_DMARC_FROM = re.compile(r"\bheader\.from\s*=\s*([A-Za-z0-9.\-_]+)")


def first_verdict(raw: bytes, authority: str) -> Optional[Dict[str, str]]:
    """The FIRST Authentication-Results instance, iff stamped by `authority`.

    First instance, from the raw bytes: a sender can hand their MTA a message
    that already CONTAINS a forged verdict header, and every hop prepends —
    so the outermost (first) instance is the one our edge stamped, and any
    later instance is unvetted input. A verdict whose authserv-id is not the
    declared authority is treated as absent rather than believed.

    Returns {"authserv_id": ..., "dmarc": ..., "spf": ..., ...} for the
    methods present, or None when no trustworthy verdict exists. Never
    raises on malformed mail: unparseable evidence IS "no verdict".
    """
    if not authority:
        return None
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        header = msg.get("Authentication-Results")
    except (ValueError, LookupError, UnicodeError) as e:
        print(f"⚠️ MACF: Authentication-Results parse failed (treating as "
              f"absent): {e}", file=sys.stderr)
        return None
    if not header:
        return None
    value = str(header)
    authserv = value.split(";", 1)[0].strip()
    if authserv.split()[0].lower() != authority.lower():
        return None
    verdict: Dict[str, str] = {"authserv_id": authserv}
    for method, result in _METHOD_RESULT.findall(value):
        # First occurrence of each method wins within the one header.
        verdict.setdefault(method.lower(), result.lower())
    # The domain the authority actually ALIGNED, extracted so authorize() can
    # bind the verdict to the sender instead of trusting that two independent
    # parsers agree about which From header this message has. Without it a
    # dmarc=pass is only "somebody's mail passed", not "this sender's did".
    m = _DMARC_FROM.search(value)
    if m:
        verdict["dmarc_from"] = m.group(1).lower()
    return verdict


def sender_identity(raw: bytes) -> Tuple[str, str]:
    """(envelope-ish sender, from-domain) as claimed by the message.

    The CLAIM, not the fact — pairing it with a dmarc=pass verdict from the
    trusted authority is what upgrades it to an authenticated identity, and
    that pairing is authorize()'s job, kept out of here so parsing and
    trust cannot blur.
    """
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        froms = msg.get_all("From") or []
        # RFC 5322 permits exactly one From. Accepting more means picking one,
        # and "which one" is exactly where our parser and the authority's can
        # disagree — the differential that lets a message be aligned as one
        # domain and read as a contact at another. Refused rather than
        # resolved: there is no correct way to choose, and choosing quietly is
        # how the choice stops being visible.
        if len(froms) > 1:
            raise SpoolError(f"message carries {len(froms)} From headers; "
                             "RFC 5322 permits one and choosing among them is "
                             "a parser differential, not a repair")
        _, addr = email.utils.parseaddr(str(msg.get("From", "")))
    except (ValueError, LookupError, UnicodeError) as e:
        print(f"⚠️ MACF: From-header parse failed: {e}", file=sys.stderr)
        raise SpoolError(f"unparseable From header: {e}") from e
    addr = addr.strip().lower()
    if "@" not in addr:
        raise SpoolError(f"message From yields no usable address: {addr!r}")
    return addr, addr.rsplit("@", 1)[1]


# --------------------------------------------------------- push eligibility

def assert_push_grants_eligible(contacts: ContactBook,
                                broker_config: BrokerConfig) -> None:
    """Every push grant in the contacts file, checked against the agent
    namespace. A grant on an agent's own address is the two-edge loop the
    pull-only property exists to prevent, configured into existence — so it
    is FATAL, not a warning: a warning in a log is another silent nothing.

    Called at broker startup AND per authorization decision. The contacts
    file is re-read per decision by design, and an address can ENTER the
    agent namespace while the broker runs; a boot-only check goes stale the
    moment either input changes.
    """
    for (agent, address), granted in contacts.push_grants().items():
        if granted and broker_config.agent_for(address) is not None:
            raise PushEligibilityError(
                f"contacts grant push-wake to '{address}' (for '{agent}'), "
                f"but that address is in the agent namespace. Turn-opening "
                f"privilege is human-only BY DERIVATION; refusing to run "
                f"with this configuration."
            )


def push_denied_by_history(audit: Optional[AuditLog], address: str) -> Optional[str]:
    """The audit-history backstop: an address that has EVER originated an
    agent-bundle submission is push-denied, whatever the contacts say.

    FAILS CLOSED: missing or unreadable history returns a denial reason
    rather than "no history found" — the security answer and the
    broken-instrument answer must never share a value. Returns None only
    when readable history affirmatively shows no bundle from this address.
    """
    if audit is None:
        return "no audit log configured; push denied (backstop fails closed)"
    addr = address.strip().lower()
    try:
        for rec in audit.records():
            if rec.get("direction") == "inbound":
                continue
            if str(rec.get("sender", "")).strip().lower() == addr:
                return (f"'{address}' has originated agent-bundle traffic "
                        f"(audit {rec.get('ts', '?')}); push denied")
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: audit history unreadable (push denied, fails "
              f"closed): {e}", file=sys.stderr)
        return f"audit history unreadable ({e}); push denied (fails closed)"
    return None


# ------------------------------------------------------------ authorization

def authentication_status(cfg: InboundConfig, raw: bytes) -> Tuple[bool, str, str]:
    """Was the sending identity AUTHENTICATED and ALIGNED? (ok, sender, why).

    EXTRACTED SO TWO DECISIONS CANNOT DRIFT. `authorize()` needs it to refuse;
    the non-delivery notice needs it to decide whether replying is safe at all
    (spec O5g.1 "never-notify-an-unauthenticated-sender"). The alternative was
    for the notice path to re-derive the same conclusion, or worse to read it
    out of `authorize()`'s prose reason -- deciding whether to send outbound
    mail by string-matching an error message.

    THE STAKES ON THE NOTICE SIDE ARE HIGHER THAN ON THE REFUSAL SIDE. A wrong
    refusal drops one message. A wrong notice sends OUR bounce to whoever the
    forger named, making this system an amplifier aimed at someone who did
    nothing -- so the two readers must be the same code, not two readings that
    agree today.
    """
    sender, from_domain = sender_identity(raw)
    verdict = first_verdict(raw, cfg.verdict_authority)
    if verdict is None:
        return False, sender, ("no trustworthy authentication verdict (absent, "
                               "or stamped by an authserv-id this deployment "
                               "does not trust)")
    if verdict.get("dmarc") != "pass":
        return False, sender, (f"sender '{sender}' not authenticated: dmarc="
                               f"{verdict.get('dmarc', 'absent')}")

    # BIND the verdict to the sender. A dmarc=pass says SOME domain aligned;
    # without this it was never checked to be the domain we then look up in
    # the contact list. The two facts came from two different parsers of the
    # same message — our authority's DMARC From-extraction and Python's
    # parseaddr — and the code merely placed them next to each other, which
    # made "they cannot disagree" an assumption about parser agreement rather
    # than something asserted. Parser differentials are precisely the bug
    # class that lives in that gap (multiple From headers, RFC 2047
    # encoded-words), so the agreement is now checked, not presumed.
    aligned = verdict.get("dmarc_from")
    if aligned is None:
        return False, sender, ("verdict carries dmarc=pass but names no "
                               "aligned domain (header.from absent); cannot "
                               "bind the pass to a sender")
    if aligned != from_domain:
        return False, sender, (f"authentication does not cover this sender: "
                               f"the authority aligned '{aligned}' but the "
                               f"message's From resolves to '{from_domain}'")
    return True, sender, f"authenticated and aligned as '{sender}'"


def authorize(cfg: InboundConfig, recipient_agent: str, raw: bytes) -> Tuple[str, str]:
    """(outcome, reason). Outcome ∈ {DENY, DELIVER_PULL, DELIVER_PUSH_WAKE}.

    Authentication upstream, authorization here, in that order:
    1. A trustworthy verdict must exist (first instance, our authority) and
       carry dmarc=pass — otherwise the sender identity is a claim nobody
       vouched for, and the outcome is DENY, stated as such.
    2. The authenticated address must be in the recipient's contacts.
    3. Push-wake requires: the grant in the contacts file, AND the
       derivation (agent-namespace check re-asserted), AND a clean
       audit-history backstop. Any miss degrades to DELIVER_PULL — a
       degraded wake is mail that arrives quietly, not mail that vanishes.
    """
    contacts = ContactBook(cfg.broker_config.contacts_path)
    assert_push_grants_eligible(contacts, cfg.broker_config)

    authenticated, sender, why = authentication_status(cfg, raw)
    if not authenticated:
        return DENY, why

    if not contacts.permits(recipient_agent, sender):
        return DENY, (contacts.refuse_reason(recipient_agent, sender)
                      or f"'{sender}' is not a contact of '{recipient_agent}'")

    if contacts.push_granted(recipient_agent, sender):
        if not cfg.push_wake_enabled:
            # The wake mechanism is not built yet; the grant is real and
            # the mail still arrives — quietly, and visibly so.
            return DELIVER_PULL, (f"contact of '{recipient_agent}'; push "
                                  f"granted but push-wake is disabled "
                                  f"(mechanism not yet built)")
        history_denial = push_denied_by_history(
            AuditLog(cfg.broker_config.audit_path)
            if cfg.broker_config.audit_path else None, sender)
        if history_denial is None:
            return DELIVER_PUSH_WAKE, f"contact of '{recipient_agent}', push granted"
        # Degraded, visibly: the mail still arrives; only the wake is lost.
        print(f"⚠️ MACF: push-wake degraded to pull for '{sender}': "
              f"{history_denial}", file=sys.stderr)
        return DELIVER_PULL, (f"contact of '{recipient_agent}'; push degraded: "
                              f"{history_denial}")
    return DELIVER_PULL, f"contact of '{recipient_agent}'"


# ------------------------------------------------------------- the consumer

def _spool_entries(spool_dir: Path) -> Iterator[Tuple[Path, Path]]:
    """(eml, sidecar) pairs. A half-pair is a SpoolError surfaced to the
    caller per entry, not a skip — a .eml without its sidecar is evidence of
    an interrupted write, and skipping evidence is how gaps go unexplained."""
    for eml in sorted(spool_dir.glob("*.eml")):
        yield eml, eml.with_suffix(".json")


def _notify_refusal(cfg: InboundConfig, raw: bytes, sender: str) -> Dict[str, Any]:
    """Emit a non-delivery notice for a refused message, if it is safe to.

    Returns the decision either way. Silence is this path's most common and
    most CORRECT outcome, so it has to stay accountable: a function that
    returned nothing for "not sent" would make a deliberate silence
    indistinguishable from a step that never ran.

    The composed notice is returned rather than transmitted. The outbound
    transport is Phase 4 and does not exist; handing this a live sender now
    would be the one thing this module must never do by accident.
    """
    from . import notices

    bc = cfg.broker_config
    authenticated, auth_sender, _why = authentication_status(cfg, raw)
    decision = notices.decide(
        authenticated=authenticated,
        sender=auth_sender or sender,
        # A refused NOTICE is never answered (spec O5g.4). Read from the
        # message's own broker-set marker, never inferred from its subject:
        # a subject is sender-controlled, so inferring would let a
        # correspondent suppress its own notices by naming a message well.
        refused_was_notice=notices.NOTICE_HEADER.lower() in raw.decode(
            "utf-8", errors="replace").lower(),
    )
    decision = notices.emit(
        decision,
        to_address=auth_sender or sender,
        sender_address=f"postmaster@{bc.domain}",
        scrub=getattr(bc, "opsec_scan", None),
        rate_limiter=getattr(bc, "rate_limiter", None),
        principal=notices.BROKER_PRINCIPAL,
    )
    if decision.alert:
        print(f"🚨 MACF: notice for a refused message was NOT emitted and this "
              f"needs a human: {decision.reason}", file=sys.stderr)
    return {"emitted": decision.emitted, "reason": decision.reason,
            "alert": decision.alert}


def _quarantine(cfg: InboundConfig, eml: Path, sidecar: Path, reason: str) -> Path:
    """MOVE to quarantine with the reason attached. Never deletes content:
    quarantine expiry is the system's only content-deletion path, and it is
    the watched one."""
    qdir = cfg.quarantine_dir
    qdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    dest = qdir / eml.name
    os.rename(eml, dest)  # same filesystem by deployment contract
    side_dest = qdir / sidecar.name
    if sidecar.exists():
        os.rename(sidecar, side_dest)
    (qdir / f"{eml.stem}.reason").write_text(reason + "\n")
    return dest


def process_entry(cfg: InboundConfig, eml: Path, sidecar: Path) -> Dict[str, Any]:
    """One spool entry to exactly one terminal disposition. Returns the
    audit-shaped summary; raises nothing in the normal course — every
    anticipated failure is a QUARANTINED disposition with its reason, and
    an unanticipated one propagates loudly rather than becoming a guess."""
    audit = (AuditLog(cfg.broker_config.audit_path)
             if cfg.broker_config.audit_path else None)
    raw = eml.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    def terminal(decision: str, reason: str, recipient: str = "") -> Dict[str, Any]:
        if audit is not None:
            audit.inbound(sender=summary.get("sender", "unknown"),
                          recipient=recipient or summary.get("recipient", "unknown"),
                          message_id=sha, decision=decision, reason=reason)
        summary.update({"disposition": decision, "reason": reason})
        return summary

    summary: Dict[str, Any] = {"sha256": sha, "entry": eml.name}
    if audit is not None:
        audit.inbound(sender="unknown", recipient="unknown", message_id=sha,
                      decision=SEEN, reason=f"spool entry {eml.name}")

    # Corruption check — NOT a forgery check; the spool's single-writer
    # permission is the forgery exclusion.
    try:
        meta = json.loads(sidecar.read_text())
    except (OSError, json.JSONDecodeError) as e:
        _quarantine(cfg, eml, sidecar, f"sidecar unreadable: {e}")
        return terminal(QUARANTINED, f"sidecar unreadable: {e}")
    if meta.get("raw_sha256") != sha:
        _quarantine(cfg, eml, sidecar,
                    f"stored bytes hash {sha[:16]} != sidecar claim "
                    f"{str(meta.get('raw_sha256'))[:16]} (storage corruption)")
        return terminal(QUARANTINED, "hash mismatch against sidecar")

    # Recipient: the envelope the transport recorded, resolved to a local
    # agent. Mail for nobody-we-host is quarantined, visibly.
    envelope_to = str(meta.get("observed", {}).get("envelope_to", "")).strip().lower()
    recipient_agent = cfg.broker_config.agent_for(envelope_to)
    summary["recipient"] = envelope_to
    if recipient_agent is None:
        _quarantine(cfg, eml, sidecar, f"no local agent for '{envelope_to}'")
        return terminal(QUARANTINED, f"no local agent for '{envelope_to}'")

    try:
        sender, _ = sender_identity(raw)
        summary["sender"] = sender
        outcome, reason = authorize(cfg, recipient_agent, raw)
    except SpoolError as e:
        _quarantine(cfg, eml, sidecar, str(e))
        return terminal(QUARANTINED, str(e))
    # PushEligibilityError deliberately NOT caught: a forbidden grant is a
    # deployment configuration failure, and processing mail under it would
    # be running with the property this module exists to hold, absent.

    if outcome == DENY:
        _quarantine(cfg, eml, sidecar, reason)
        # THE AFFIRMATIVE HALF (spec O5g.3). The refusal is recorded either
        # way; what varies is whether the correspondent learns of it, and that
        # turns on whether we can prove who they are. Emitting is attempted
        # here rather than left to a later sweep because the decision needs the
        # authentication status of THIS message, which the quarantine does not
        # preserve in a form the gate could re-derive safely.
        summary["notice"] = _notify_refusal(cfg, raw, sender)
        return terminal(QUARANTINED, reason, recipient_agent)

    box = cfg.handoff_dir / recipient_agent
    box.mkdir(mode=0o2770, parents=True, exist_ok=True)
    sidecar_out = dict(meta)
    sidecar_out["authorization"] = {"outcome": outcome, "reason": reason}
    base = box / eml.stem
    # Sidecar first, message second, both 0640 so the recipient's group can
    # read; the recipient may REMOVE from the box (dir group-write) but the
    # files themselves are not group-writable — content re-verified by hash
    # at ingest regardless.
    base.with_suffix(".json").write_text(json.dumps(sidecar_out, indent=1))
    base.with_suffix(".json").chmod(0o640)
    base.with_suffix(".eml").write_bytes(raw)
    base.with_suffix(".eml").chmod(0o640)
    summary["handed_off_to"] = str(base.with_suffix(".eml"))
    summary["delivery_class"] = outcome

    # Handoff COMPLETED; only now may the spool entry go.
    os.unlink(eml)
    os.unlink(sidecar)
    return terminal(HANDED_OFF, f"{outcome}: {reason}", recipient_agent)


def process_spool(cfg: InboundConfig) -> List[Dict[str, Any]]:
    """Drain the spool. Startup gate first: a forbidden push grant refuses
    the whole run before any mail moves."""
    assert_push_grants_eligible(ContactBook(cfg.broker_config.contacts_path),
                                cfg.broker_config)
    results = []
    for eml, sidecar in _spool_entries(cfg.spool_dir):
        results.append(process_entry(cfg, eml, sidecar))
    return results


# ------------------------------------------------------------- conservation


# --------------------------------------------------------------- aged sweep

def sweep_aged(cfg: InboundConfig, now: Optional[float] = None) -> Dict[str, Any]:
    """THE ORPHAN SWEEP: find entries nobody has moved, and SAY SO.

    Never deletes content — that is the whole discipline. Mail that could not
    be processed becomes an inspectable artifact; it does not evaporate.

    Two populations, two different failures wearing the same shape:

      spool entries past the bound  -> the CONSUMER is not running, or died
                                       mid-run. Under manual operation that is
                                       expected between runs; under a watcher
                                       it means the watcher is dead.
      pickup entries past the bound -> the RECIPIENT has stopped draining, or
                                       (the case that actually bit this
                                       deployment) its box carries the wrong
                                       group and it never could.

    Aged SPOOL entries move to quarantine -- authorized-but-
    unprocessed mail becomes an inspectable artifact rather than an alert
    someone read once. Aged PICKUP entries are REPORTED AND LEFT WHERE THEY
    ARE: custody was handed to the recipient, and pulling mail back out of its
    box would undo the transfer the whole model rests on. The alert is the
    remedy, not a repair.

    Written because the spec asserted this sweep for four drafts while nothing
    implemented it, and a later design then leaned on it as the backstop for an
    unattended watcher. A specified-but-absent alarm is worse than a missing
    one: the design above it assumes cover that does not exist.
    """
    now = time.time() if now is None else now
    report: Dict[str, Any] = {
        "swept_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "aged_spool": [], "aged_pickup": [], "alerts": 0}
    audit = (AuditLog(cfg.broker_config.audit_path)
             if cfg.broker_config.audit_path else None)

    if cfg.spool_dir.is_dir():
        for eml in sorted(cfg.spool_dir.glob("*.eml")):
            try:
                age = now - eml.stat().st_mtime
            except OSError as e:
                print(f"⚠️ MACF: cannot stat spool entry {eml.name}: {e}",
                      file=sys.stderr)
                report["alerts"] += 1
                continue
            if age < cfg.spool_age_bound_s:
                continue
            sidecar = eml.with_suffix(".json")
            reason = (f"aged out of the spool after {int(age)}s "
                      f"(bound {cfg.spool_age_bound_s}s): never processed")
            try:
                _quarantine(cfg, eml, sidecar, reason)
            except OSError as e:
                print(f"⚠️ MACF: aged spool entry {eml.name} could NOT be "
                      f"quarantined ({e}); it remains in the spool",
                      file=sys.stderr)
                report["alerts"] += 1
                continue
            print(f"⚠️ MACF: {reason} -- {eml.name} moved to quarantine",
                  file=sys.stderr)
            if audit:
                audit.inbound(sender="unknown", recipient="unknown",
                              message_id=eml.stem, decision=QUARANTINED,
                              reason=reason)
            report["aged_spool"].append(eml.name)
            report["alerts"] += 1

    hdir = Path(cfg.handoff_dir) if cfg.handoff_dir else None
    if hdir and hdir.is_dir():
        for box in sorted(hdir.iterdir()):
            if not box.is_dir():
                continue
            entries = sorted(list(box.glob("*.eml")) + list(box.glob("*.amsg")))
            for entry in entries:
                try:
                    age = now - entry.stat().st_mtime
                except OSError:
                    continue
                if age < cfg.pickup_age_bound_s:
                    continue
                print(f"⚠️ MACF: pickup entry {entry.name} in box "
                      f"'{box.name}' un-ingested after {int(age)}s (bound "
                      f"{cfg.pickup_age_bound_s}s): the recipient has stopped "
                      f"draining, or cannot read its own box",
                      file=sys.stderr)
                report["aged_pickup"].append(f"{box.name}/{entry.name}")
                report["alerts"] += 1
    return report


def reconcile(cfg: InboundConfig) -> Dict[str, Any]:
    """The conservation property, checkable: every SEEN sha reaches exactly
    one terminal disposition, or is still physically in the spool (in
    flight). Anything else is a shortfall — a drop that became a number.

    The report never lies by omission: an unreadable audit log is an ERROR
    result, not an empty-and-balanced one.
    """
    audit = (AuditLog(cfg.broker_config.audit_path)
             if cfg.broker_config.audit_path else None)
    if audit is None:
        return {"balanced": False,
                "error": "no audit log configured; conservation unprovable"}
    seen: Dict[str, int] = {}
    terminals: Dict[str, int] = {}
    try:
        for rec in audit.records():
            if rec.get("direction") != "inbound":
                continue
            sha = str(rec.get("message_id", ""))
            decision = rec.get("decision")
            if decision == SEEN:
                seen[sha] = seen.get(sha, 0) + 1
            elif decision in (HANDED_OFF, QUARANTINED):
                terminals[sha] = terminals.get(sha, 0) + 1
    except (OSError, ValueError) as e:
        return {"balanced": False, "error": f"audit unreadable: {e}"}

    in_flight = {hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cfg.spool_dir.glob("*.eml")} if cfg.spool_dir.exists() else set()
    missing = [s for s in seen
               if s not in terminals and s not in in_flight]
    surplus = [s for s in terminals if s not in seen]
    report = {
        "seen": len(seen), "terminal": len(terminals),
        "in_flight": len(in_flight),
        "missing_terminal": missing, "terminal_without_seen": surplus,
        "balanced": not missing and not surplus,
    }
    if not report["balanced"]:
        print(f"⚠️ MACF: inbound conservation SHORTFALL: {len(missing)} seen "
              f"without terminal, {len(surplus)} terminal without seen",
              file=sys.stderr)
    return report
