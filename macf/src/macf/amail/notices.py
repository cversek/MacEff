"""Non-delivery notices — telling a refused correspondent, without becoming a weapon.

THE SECTION THAT WAS ALL PROHIBITIONS. Through draft 0.7 this behaviour was
specified only as things not to do, so an implementation that emitted NOTHING
under any circumstance was fully conformant — which is exactly the state that
generated the requirement: a well-meaning correspondent whose mail was refused
and who was told nothing. The safety half was written and the affirmative half
was missing.

Both halves live here, and they pull against each other:

  SAFETY (spec O5g.1 "never-notify-an-unauthenticated-sender"): a notice
  returned to a forged sender is delivered to the SPOOF VICTIM, who did
  nothing. Silence toward an unprovable sender is correct behaviour, not a gap.

  AFFIRMATIVE (spec O5g.3 "a-qualifying-refusal-produces-at-most-one-notice"):
  where the sender WAS authenticated and aligned, staying silent is the defect.

THE CONTENT RULE IS NOT COSMETIC (spec O5g.4a). The standard NDN quotes the
original, and for a REFUSED message that means echoing attacker-supplied bytes
back outward under our name, and disclosing which check failed to the party the
check refused — turning every refusal into a probe result. Every mail library
does the quoting by default, which is why this is a control and not a style.

A notice is BROKER-ORIGINATED, so it is outside the contacts check (spec
O5b.8) and inside everything else: the pre-send gate, the rate limit, credential
custody. Being outside ONE thing is not being outside all of them — the seam
that put notices under no outbound control at all.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import Message, _now_iso
# Re-exported, not re-spelled. The literal "__broker__" appearing in two
# modules is two constants that agree today; importing it is one constant.
from .ratelimit import BROKER_PRINCIPAL

#: STABLE REFUSAL CODES. A correspondent can quote one to a human and get an
#: answer; the notice itself carries no answer. Deliberately COARSE — a code
#: space fine enough to name the failed check would reintroduce the disclosure
#: the content rule removes, by another route (spec O13.11 records that the
#: vocabulary is not yet settled).
CODE_NOT_ACCEPTED = "AMAIL-001"   # refused by policy. Covers every reason.
CODE_UNDELIVERABLE = "AMAIL-002"  # accepted, then could not be delivered.

#: Marks a message as a notice so a receiving broker can recognise one.
#: Spec O5g.4 "a-notice-is-never-itself-notified-about": two conformant systems,
#: each refusing the other's notices as non-contacts and each notifying about
#: it, is an infinite loop built entirely out of correct behaviour.
NOTICE_HEADER = "X-Amail-Notice"
NOTICE_SUBJECT = "Delivery Status Notification"


@dataclass
class NoticeDecision:
    """Why a notice was or was not emitted. Every path returns one.

    An emitter that returns None for "not sent" makes silence indistinguishable
    from an unrecorded decision — and silence is this module's most common and
    most correct outcome, so it is exactly the one that must stay accountable.
    """

    emitted: bool
    reason: str
    message: Optional[Message] = None
    alert: bool = False
    #: WHETHER IT ACTUALLY LEFT. Separate from `emitted`, and the separation is
    #: a repair rather than a refinement: for one whole phase `emitted` was the
    #: only field, it meant "the decision was taken and a notice was composed",
    #: and every reader took it to mean SENT. A live battery run reported
    #: `emitted: true` for a notice that reached no transport, no audit record
    #: and no ledger — the operator would have checked an empty mailbox against
    #: a report saying one went out.
    #:
    #: A decision and its execution are different facts. One field cannot carry
    #: both without the more optimistic reading winning.
    sent: bool = False


def is_notice(message: Any) -> bool:
    """True when this message is itself a notice.

    Read from the broker-set header, never inferred from the subject: a subject
    is sender-controlled, so inferring from it would let any correspondent
    suppress its own notices by naming a message the right way.
    """
    trust = getattr(message, "trust", None) or ""
    subject = getattr(message, "subject", None) or ""
    return NOTICE_HEADER.lower() in str(trust).lower() or (
        subject == NOTICE_SUBJECT and getattr(message, "notice_code", None) is not None)


def compose_notice(to_address: str, code: str, *, sender_address: str,
                   at: Optional[str] = None) -> Message:
    """A notice, carrying NO bytes from the message it refuses.

    Spec O5g.4a "a-notice-carries-no-bytes-from-the-refused-message". What goes
    in: that a message was not delivered, when, and a stable code. What stays
    out: the original body, the original headers, and the specific check that
    failed.

    The recipient address is the only thing taken from the refused message, and
    it is taken from the AUTHENTICATED identity rather than from the From header
    — which is what makes it safe to write to at all.
    """
    body = (
        "Your message was not delivered.\n"
        f"\nReference: {code}"
        f"\nAt: {at or _now_iso()}\n"
        "\nNo further detail is available in this notice. If you believe this "
        "is an error, quote the reference above to your correspondent.\n"
    )
    m = Message(sender=sender_address, to=[to_address],
                subject=NOTICE_SUBJECT, body=body)
    # MINTED by the broker, like `trust`: it marks the message as a notice for
    # loop protection, and a sender cannot put it there.
    m.trust = NOTICE_HEADER
    return m


def decide(*, authenticated: bool, sender: str, refused_was_notice: bool,
           already_notified: bool = False) -> NoticeDecision:
    """Should a notice be emitted at all? The gate, separated from the sending.

    Split from emission deliberately: this is the decision the spec constrains,
    and keeping it free of I/O is what lets every branch be exercised without a
    transport. The branches ARE the specification:
    """
    if refused_was_notice:
        # Spec O5g.4. Recorded and dropped, never answered.
        return NoticeDecision(False, "the refused message was itself a notice; "
                                     "answering one would build a loop out of "
                                     "correct behaviour")
    if not authenticated:
        # Spec O5g.1/O5g.2. THE MOST IMPORTANT SILENCE IN THIS MODULE.
        return NoticeDecision(False, f"sender '{sender}' was not authenticated; "
                                     f"a notice would go to whoever was forged")
    if already_notified:
        # Spec O5g.3: one per REFUSAL, not one per retry.
        return NoticeDecision(False, "a notice was already emitted for this "
                                     "refusal")
    return NoticeDecision(True, f"'{sender}' was authenticated and aligned")


def emit(decision: NoticeDecision, *, to_address: str, sender_address: str,
         code: str = CODE_NOT_ACCEPTED,
         scrub: Optional[Any] = None,
         rate_limiter: Optional[Any] = None,
         principal: str = BROKER_PRINCIPAL) -> NoticeDecision:
    """Compose and gate a notice. Returns the decision, updated with the outcome.

    THE ORDER MATTERS AND IS THE SPEC'S. The rate limit is charged before the
    scrub so a burst of refusals cannot be paid for in scanning work; the scrub
    runs last because it is the irreversible-harm gate and gets the final word.

    FAIL-CLOSED BEATS EXACTLY-ONE (spec O5g.4c/O5g.4d). If the scrub refuses,
    the notice is NOT sent, the absence is recorded, and the case ALERTS —
    because a notice's content is broker-generated and carries no bytes from the
    refused message, so a scrub refusal means OUR OWN TEXT tripped OUR OWN gate.
    That is a defect in this system, invisible from every other vantage point.

    The subordination is legitimate under a stated rule rather than by
    preference: the two MUSTs protect DIFFERENT PARTIES and one guards against
    IRREVERSIBLE harm. The gate protects us and third parties from a disclosure
    that cannot be recalled; the notice protects a correspondent from silence,
    which is recoverable by other means.
    """
    if not decision.emitted:
        return decision

    if rate_limiter is not None:
        try:
            refusal = rate_limiter.check_and_consume(principal)
        except Exception as e:  # noqa: BLE001 - an unknown budget is not an empty one
            return NoticeDecision(False, f"notice budget could not be "
                                         f"determined ({type(e).__name__}); "
                                         f"not emitting", alert=True)
        if refusal:
            return NoticeDecision(False, f"notice suppressed by rate limit: {refusal}")

    notice = compose_notice(to_address, code, sender_address=sender_address)

    if scrub is not None:
        try:
            result = scrub(notice)
        except Exception as e:  # noqa: BLE001 - a gate that fails open is not a gate
            return NoticeDecision(False, f"the pre-send gate raised on a notice "
                                         f"({type(e).__name__}); not emitting",
                                  alert=True)
        if getattr(result, "findings", None) or getattr(result, "unscanned", None):
            print(f"⚠️ MACF: a NOTICE failed the pre-send gate ({result.reason()}). "
                  f"Its content is broker-generated, so this is our own text "
                  f"tripping our own gate — a defect here, not in the "
                  f"correspondent's message.", file=sys.stderr)
            return NoticeDecision(False, f"notice refused by the pre-send gate: "
                                         f"{result.reason()}", alert=True)

    return NoticeDecision(True, decision.reason, message=notice)


def transmit(decision: NoticeDecision, *, transport: Any = None,
             credential: Any = None) -> NoticeDecision:
    """Actually send a notice that `emit` decided on and composed.

    KEPT SEPARATE FROM `emit`, which stays free of I/O so every branch of the
    spec's decision tree can be exercised without a transport. That separation
    was correct and it is also what let the gap hide: `emit` returned a composed
    notice, its caller reported success, and nothing carried the notice
    outward.

    THIS WAS A DELIBERATE DEFERRAL THAT EXPIRED. The notice path was left
    unwired on purpose while no transport existed, because handing this path a
    live sender before there was one was the single thing this module must not
    do by accident. A transport exists now, so the deferral is spent and what
    remains is a missing wire.

    NO TRANSPORT IS NOT A FAILURE OF THE NOTICE, and the distinction is
    reported rather than flattened: a deployment with no outbound leg is
    legitimate, and its notices are composed-not-sent. What must never happen
    is that state being indistinguishable from a delivered one.
    """
    if not decision.emitted or decision.message is None:
        return decision
    if transport is None:
        return NoticeDecision(True, f"{decision.reason}; composed but NOT sent: "
                                    f"no outbound transport is configured",
                              message=decision.message, alert=decision.alert,
                              sent=False)
    try:
        recipients = list(getattr(decision.message, "to", None) or [])
        result = transport.send(decision.message, credential,
                                recipient=recipients[0] if recipients else None)
    except Exception as e:  # noqa: BLE001 - a notice must not break the refusal
        # The refusal it answers has ALREADY happened and is recorded. Letting a
        # transport failure propagate would make an undeliverable notice undo
        # the quarantine decision that produced it.
        return NoticeDecision(True, f"{decision.reason}; notice NOT sent "
                                    f"({type(e).__name__}: {e})",
                              message=decision.message, alert=True, sent=False)
    return NoticeDecision(True, f"{decision.reason}; sent ({result.state})",
                          message=decision.message, alert=decision.alert,
                          sent=True)
