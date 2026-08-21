"""The outbound authentication criterion — read from a RECEIVED copy.

Normative source: the amail spec section 5i. Every rule here exists because a
measurement falsified the obvious alternative, and the comments carry the
measurement rather than the conclusion, because a conclusion without its
mechanism is easy to regress by restating it wrongly.

WHY THIS IS A MODULE AND NOT THE EXPERIMENT'S PROBE. The reader was written as
an experiment artifact, and the experiment is in a terminal state. Its probe is
the record of what was actually run to produce those findings, so it is left
untouched: editing it would retroactively change the instrument a completed
result claims to have used, which is the same offence as backfilling an
evidence store. This module is the operational reader, corrected, and the two
are allowed to differ — that difference is documented below.

TWO DEFECTS THE PROBE CARRIED, both found by pointing it at a second real
receiver rather than by review:

1. IT INVENTED AN AUTHSERV-ID RATHER THAN DETECTING ABSENCE. It took the first
   token of the header as the authserv-id unconditionally. A major provider
   emits `Authentication-Results:` with NO authserv-id at all -- the field
   begins directly with `spf=pass` -- so the reader reported the authserv-id as
   the literal string `spf=pass`. A caller who declared that string as its
   expected authority would have passed the authority check. An absence read as
   a value is worse than an absence read as an error.

2. IT REPORTED `header.from` WITHOUT TESTING IT. Spec O5i.4 makes the test the
   standalone `dmarc=` result token TOGETHER WITH `header.from` being our
   sending identity. The probe returned the value and compared nothing, so a
   message that authenticated for somebody ELSE'S domain read AUTHENTICATED.
   The identity is now a required argument: a caller must say whose mail it
   believes it is checking.
"""
from __future__ import annotations

import re
from email.parser import BytesHeaderParser
from email.policy import compat32
from typing import Any, Dict, Optional

#: Result fields the criterion may read. The DISPOSITION field is deliberately
#: absent (O5i.5): it was measured reading `none` in BOTH polarities under
#: `p=none`, so a reader consulting it is constant where it matters most.
METHODS = ("dkim", "spf", "dmarc")

#: The lookbehind is load-bearing rather than tidiness. `\b` matches INSIDE a
#: dotted token, so `\bdmarc=` matches the `dmarc=` in `policy.dmarc=none` --
#: and `policy.dmarc` IS the disposition, the one field this criterion is
#: forbidden to read. Both providers seen so far emit `dmarc=` before
#: `policy.dmarc=`, so an unguarded reader returns the right answer BY FIELD
#: ORDER, and RFC 8601 fixes no such order. Reordered, it degrades silently
#: into a constant-`none` instrument.
_METHOD_RE = {m: re.compile(r"(?<![.\w])%s\s*=\s*([a-z]+)" % m, re.I) for m in METHODS}
_FROM_RE = re.compile(r"header\.from\s*=\s*([^\s;,]+)", re.I)
_FIRST_TOKEN_RE = re.compile(r"^\s*([^\s;]+)")


def _in_boundary(observed: Optional[str], declared: Optional[str]) -> bool:
    """Does one observed authserv-id belong to the DECLARED boundary?

    Exact match, or a LABEL-BOUNDED subdomain of it. The label boundary is the
    load-bearing character: a bare `endswith` would accept `evil-icloud.com`
    for a declared `icloud.com`, which is a check that looks present and admits
    anything ending in the right letters. The leading dot is what makes it a
    statement about DNS structure rather than about string tails.

    A deployment declaring a broad parent is making a broad claim knowingly;
    declaring the exact authserv-id keeps the old strict behaviour unchanged,
    which is why every existing single-authority receiver is unaffected.
    """
    if observed is None or declared is None:
        return False
    observed = observed.lower().rstrip(".")
    declared = declared.lower().rstrip(".")
    return observed == declared or observed.endswith("." + declared)


def _same_boundary(this_id: Optional[str], expected: Optional[str],
                   declared: Optional[str]) -> bool:
    """Do two authserv-ids denote the SAME receiving boundary?

    The anti-misattribution question, and the only question the identity check
    is still asking once authorship scoping has dissolved the anti-forgery one.

    A receiver may stamp each verifier subsystem under its own sibling name --
    `dmarc.<parent>`, `spf.<parent>`, `dkim-verifier.<parent>` -- and those are
    one boundary's subsystems, not several boundaries. Equality is therefore too
    strict and reports a legitimate multi-subsystem receiver as a truncated run.

    THE SUFFIX IS ANCHORED TO THE DECLARED PARENT, NOT INFERRED FROM THE FIRST
    INSTANCE. Deriving the parent from what arrived would let the message decide
    what counts as its own receiver, which is the shape of every defect this
    module has had -- a gate whose reading its subject writes. With no
    declaration there is nothing to anchor to, so the rule falls back to
    equality, which is strict and wrong-in-the-safe-direction.

    A LABEL BOUNDARY IS REQUIRED. `evil-icloud.com` must not match a declared
    `icloud.com`, so the match is on a leading dot or exact equality and never
    on a bare string suffix. This is the one line where getting the comparison
    subtly wrong yields a check that looks present and accepts anything ending
    in the right letters.
    """
    if this_id is None or expected is None:
        return this_id == expected
    this_id = this_id.lower().rstrip(".")
    expected = expected.lower().rstrip(".")
    if this_id == expected:
        return True
    if not declared:
        return False
    parent = declared.lower().rstrip(".")
    return all(x == parent or x.endswith("." + parent) for x in (this_id, expected))

#: Verdicts. UNKNOWN is never collapsed toward pass or fail (spec 5i): a test
#: claiming authentication MUST report an inconclusive run as inconclusive.
AUTHENTICATED = "AUTHENTICATED"
NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
UNTRUSTED_AUTHORITY = "UNTRUSTED_AUTHORITY"
NO_AUTHSERV_ID = "NO_AUTHSERV_ID"
ABSENT = "ABSENT"

#: HOW THE COPY REACHED THE READER. The criterion's trustworthiness rests
#: entirely on this and it was carried as prose until it was mechanised here,
#: which is the difference between a rule and a control.
#:
#: FETCHED    the reader obtained the raw bytes itself from a mailbox under
#:            our control. The only provenance a gate may act on.
#: RELAYED    a human read it out of a mail client and passed the text on --
#:            pasted, forwarded, or copied from a rendering. NOT dishonest and
#:            NOT a pass: a client's "view source" is a RENDERING, and a
#:            rendering may fold, reorder or omit without saying so. Every
#:            receiver reading taken before this constant existed was RELAYED,
#:            including the two the gate would otherwise have rested on.
#: UNKNOWN    provenance not asserted. Treated as RELAYED, because a caller
#:            who did not think about how the bytes arrived is the caller this
#:            distinction exists for.
FETCHED = "fetched"
RELAYED = "relayed"
UNKNOWN_PROVENANCE = "unknown"

#: The verdicts that are NOT a pass and NOT a failure of the mail: the
#: instrument could not read. The gate treats them as failure (spec 11c X5 --
#: a gate is a decision, not a reading, and declines to open on evidence it
#: does not have) while a REPORT must keep them distinct from a real failure.
INCONCLUSIVE = (ABSENT, NO_AUTHSERV_ID, UNTRUSTED_AUTHORITY)


UNEXPECTED_AUTHSERV_ID = "UNEXPECTED_AUTHSERV_ID"
NOT_FETCHED = "NOT_FETCHED"


def read_criterion(raw: bytes, authority: Optional[str], identity: str, *,
                   self_authored: bool = False,
                   provenance: str = UNKNOWN_PROVENANCE) -> Dict[str, Any]:
    """Read the criterion from a received copy's raw bytes.

    `authority`     the authserv-id the receiving boundary is expected to
                    stamp, or None to DECLARE that this receiver stamps none.
    `identity`      the domain `header.from` must carry for this to be OUR mail.
    `self_authored` whether this system composed and submitted the message.
    `provenance`    how these bytes reached the reader (FETCHED / RELAYED).

    THE AUTHORITY CHECK IS SCOPED BY AUTHORSHIP, and the reason is that it was
    inherited from a context whose threat this one does not contain. The
    inbound rule verifies the authserv-id because THE SENDER IS AN ADVERSARY: a
    stranger appends a forged verdict and a reader consulting any instance but
    our own boundary's builds a gate whose reading the attacker writes.

    Here the sender is US. We compose the message, submit it through our own
    broker on our own credential to our own endpoint, it lands in a mailbox we
    control, and we read the raw source. **There is no forger anywhere in that
    loop.** So on self-authored mail the check is protection against a threat
    that is absent, and its only observable effect is to fail on mail that
    authenticated -- which is what it did at a receiver that omits the
    authserv-id entirely.

    THE SCOPE IS THE POINT, because the danger is migration. Waiving the check
    is safe ONLY for mail we wrote. `authority=None` therefore requires
    `self_authored=True`; asking to waive it on a stranger's mail is a
    programming error and raises rather than returning a lenient verdict.

    A DECLARATION THAT GOES STALE IS DETECTED. If `authority=None` declares
    that this receiver stamps no authserv-id and one turns up anyway, the
    receiver's behaviour changed under us and the result is
    UNEXPECTED_AUTHSERV_ID -- not a pass, and not silently ignored.

    THE FIRST INSTANCE ONLY (O5i.2). A later instance is sender-suppliable, so
    reading any but the outermost builds a gate whose reading the attacker
    writes. `ARC-Authentication-Results` is a DIFFERENT header field and is
    never collected here -- an intermediary's claim about a hop we did not
    observe, meaningful only if the chain validates AND the sealer is trusted,
    and this spec establishes neither.
    """
    if authority is None and not self_authored:
        raise ValueError(
            "the authority check may only be waived for mail THIS SYSTEM "
            "authored. On a message we did not write, the authserv-id is what "
            "separates our boundary's verdict from one the sender appended.")

    headers = BytesHeaderParser(policy=compat32).parsebytes(raw)
    instances = headers.get_all("Authentication-Results") or []

    # THE SHAPE IS RECORDED, NOT ONLY THE VERDICT.
    #
    # A verdict is a boolean, and the response to a boolean that says no is to
    # widen a rule until it says yes -- which is how the identity assumption
    # survived the last repair. A reading that reports "six authorities, sibling
    # suffixes, dmarc token at instance 3 of 6" is DIAGNOSTIC: the next reader
    # can tell a NEW shape from a KNOWN failure without re-deriving it from raw
    # bytes, and a shape nobody has seen announces itself instead of arriving as
    # an unexplained NOT_AUTHENTICATED.
    #
    # Same discipline, and the same reason, as the disposition being a HISTORY
    # rather than a last value: `bounced after three deferrals` and `bounced
    # immediately` are different facts, and collapsing them loses the one that
    # explains the other.
    out: Dict[str, Any] = {
        "provenance": provenance,
        "self_authored": self_authored,
        "instances_present": len(instances),
        "instances_in_run": 0,
        "run_authserv_ids": [],
        "authserv_id": None,
        "authority_ok": False,
        "results": {m: None for m in METHODS},
        "header_from": None,
        "identity_ok": False,
        "verdict": ABSENT,
    }
    if not instances:
        # Absent input must never read as clean.
        return out

    # THE RECEIVER'S OWN STAMPS ARE A CONTIGUOUS LEADING RUN, NOT ONE HEADER.
    #
    # O5i.2 says "first instance", and that rule was written against a receiver
    # that stamps ONE header carrying every method. A third provider stamps
    # FOUR -- one per method, all from its own authserv-id -- and reading only
    # the first returns whichever method happens to be listed first. Measured:
    # the dmarc token was in instance 1 and the verdict was right BY LUCK. Had
    # the provider ordered spf first, the same authenticated message would have
    # read NOT_AUTHENTICATED.
    #
    # THE SECURITY PROPERTY IS PRESERVED EXACTLY, because it was never about
    # the count. A sender-supplied header arrives BELOW the receiver's own
    # stamps, so the trustworthy set is the CONTIGUOUS LEADING RUN carrying the
    # declared authority -- and the run stops at the first instance that is not
    # ours, which is precisely where a forgery would begin. Reading further
    # would build a gate whose reading the attacker writes; reading less
    # reports a method the receiver did state as absent.
    # TWO CLAUSES, NOT ONE COMPOUND RULE, and the separation is the repair.
    #
    #   POSITION  bounds "was this stamped by the receiving boundary AT ALL"
    #   IDENTITY  bounds "by WHICH boundary"
    #
    # They were previously one rule -- "contiguous run carrying the SAME
    # authserv-id" -- and that compounding is exactly how the identity
    # assumption hid. A fourth receiver stamps SIX instances, each with a
    # DIFFERENT authserv-id, all siblings of one parent: `bimi.<p>`,
    # `arc.<p>`, `dmarc.<p>`, `dkim-verifier.<p>`, `spf.<p>`. Under the
    # compound rule the run stopped at instance 1, which carries `bimi=skipped`
    # and nothing else, so the reader reported on BIMI while answering a
    # question about DMARC.
    #
    # WHY IDENTITY IS STILL CHECKED AT ALL, now that the authorship scoping
    # dissolved the anti-forgery job. The check was doing TWO jobs and only one
    # of them was about adversaries:
    #
    #   ANTI-FORGERY        -- refuse to read a verdict the SENDER appended.
    #                          Dissolved for self-authored mail, at EVERY
    #                          receiver, because the sender is us.
    #   ANTI-MISATTRIBUTION -- WHICH boundary said this? Untouched, and it
    #                          NEEDS NO ADVERSARY. The six-authority receiver
    #                          is the existence proof: an honest receiver doing
    #                          ordinary things, and a reader bounded by
    #                          position alone misattributes a BIMI result as a
    #                          DMARC one.
    #
    # So identity is bounded by BOUNDARY SUFFIX under a declared parent, which
    # is the question anti-misattribution actually asks -- not by "no attacker
    # could have stamped this", which is an argument from failure of
    # imagination and was refused elsewhere in this same review.
    #
    # AXES VARIED AND AXES ASSUMED, stated because the last generalisation here
    # widened the axis that happened to vary and silently hardened the ones that
    # did not -- and an assumption that was never a decision is not even
    # locatable, let alone falsifiable. Three receivers have now each broken a
    # DIFFERENT axis: presence (no authserv-id), count (four instances),
    # identity-uniformity (six sibling authorities).
    #   VARIED over: count, identity-uniformity, presence.
    #   ASSUMED still: that the receiver's own stamps LEAD the field (position);
    #     that instances are not interleaved with sender-supplied ones; that a
    #     sibling suffix denotes one boundary rather than a delegated third
    #     party. SHAPE FOUR EXISTS and will break one of these.
    trusted = []
    for inst in instances:
        flat = " ".join(inst.split())
        tok = _FIRST_TOKEN_RE.match(flat)
        cand = tok.group(1) if tok else None
        this_id = cand if (cand is not None and "=" not in cand) else None
        # noqa justified, and the ordering is the whole argument: `expected` is
        # READ only when `trusted` is non-empty, and `trusted` becomes non-empty
        # only on the iteration AFTER `expected` is assigned below. A static
        # checker cannot prove that, so it reports an undefined name. Do not
        # "fix" it by hoisting an initial value -- a pre-seeded `expected` would
        # silently make the FIRST instance compare against a sentinel instead of
        # establishing the run's authority, which is the anti-misattribution
        # clause this loop exists to enforce.
        if trusted and not _same_boundary(this_id, expected, authority):  # noqa: F821
            break                          # no longer the receiver's own stamps
        if not trusted:
            expected = this_id            # the run's authority is the first's
        trusted.append(flat)
        out["run_authserv_ids"].append(this_id)
    first = " ".join(trusted)
    out["instances_in_run"] = len(trusted)

    # THE AUTHSERV-ID IS DETECTED, NOT ASSUMED. RFC 8601 makes it the mandatory
    # first token, and a major provider omits it, so the field can begin with a
    # method-result. A first token containing "=" is a method-result, which
    # means there is no authserv-id to verify against -- report that, rather
    # than treating `spf=pass` as the name of an authority.
    tok = _FIRST_TOKEN_RE.match(first)
    candidate = tok.group(1) if tok else None
    if candidate is not None and "=" not in candidate:
        out["authserv_id"] = candidate
        # THE SAME BOUNDARY QUESTION AS THE RUN, ASKED THE SAME WAY. Exact
        # equality here would accept the run's sibling instances and then reject
        # the run's own leading authserv-id whenever a deployment declares the
        # parent -- two comparisons answering one question in two different
        # ways, which is the compounding this repair exists to undo.
        out["authority_ok"] = _in_boundary(candidate, authority)

    for meth, rx in _METHOD_RE.items():
        hit = rx.search(first)
        out["results"][meth] = hit.group(1).lower() if hit else None
    fm = _FROM_RE.search(first)
    out["header_from"] = fm.group(1).lower() if fm else None
    out["identity_ok"] = out["header_from"] == (identity or "").strip().lower()

    # THE AUTHORITY QUESTION IS RESOLVED FIRST, then the verdict is evaluated.
    # Folding the waiver into the verdict ladder as one more branch let the
    # waived case fall straight out of the chain without ever reaching the
    # dmarc and identity tests, so it returned the initial verdict -- a
    # control skipped by control flow rather than by a wrong comparison.
    if authority is None:
        # Declared authority-less. Present-when-declared-absent is a changed
        # receiver, not a pass.
        if out["authserv_id"] is not None:
            out["verdict"] = UNEXPECTED_AUTHSERV_ID
            return out
        out["authority_ok"] = True
    elif out["authserv_id"] is None:
        out["verdict"] = NO_AUTHSERV_ID
        return out
    elif not out["authority_ok"]:
        out["verdict"] = UNTRUSTED_AUTHORITY
        return out

    if out["results"]["dmarc"] != "pass":
        out["verdict"] = NOT_AUTHENTICATED
    elif not out["identity_ok"]:
        # dmarc=pass for somebody else's domain is a pass ABOUT SOMEBODY ELSE.
        out["verdict"] = IDENTITY_MISMATCH
    else:
        out["verdict"] = AUTHENTICATED
    return out


def is_pass(result: Dict[str, Any]) -> bool:
    """Exactly one verdict is a pass, AND ONLY ON FETCHED BYTES.

    Stated as a function so no caller has to remember which non-pass verdicts
    exist, and so the PROVENANCE requirement cannot be forgotten at the moment
    of judgement -- which is exactly when a requirement carried as prose gets
    skipped. A relayed copy may be read, reported and reasoned about; it may
    not discharge a gate.
    """
    return (result.get("verdict") == AUTHENTICATED
            and result.get("provenance") == FETCHED)


def gate_reason(result: Dict[str, Any]) -> Optional[str]:
    """Why this reading cannot discharge a gate, or None if it can.

    Separate from `is_pass` because "the mail failed" and "the reading cannot
    be acted on" are different facts that a boolean flattens -- and flattening
    them is how a provenance problem gets reported as an authentication
    problem.
    """
    if result.get("provenance") != FETCHED:
        return NOT_FETCHED
    if result.get("verdict") != AUTHENTICATED:
        return result.get("verdict")
    return None
