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

#: Verdicts. UNKNOWN is never collapsed toward pass or fail (spec 5i): a test
#: claiming authentication MUST report an inconclusive run as inconclusive.
AUTHENTICATED = "AUTHENTICATED"
NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
UNTRUSTED_AUTHORITY = "UNTRUSTED_AUTHORITY"
NO_AUTHSERV_ID = "NO_AUTHSERV_ID"
ABSENT = "ABSENT"

#: The verdicts that are NOT a pass and NOT a failure of the mail: the
#: instrument could not read. The gate treats them as failure (spec 11c X5 --
#: a gate is a decision, not a reading, and declines to open on evidence it
#: does not have) while a REPORT must keep them distinct from a real failure.
INCONCLUSIVE = (ABSENT, NO_AUTHSERV_ID, UNTRUSTED_AUTHORITY)


def read_criterion(raw: bytes, authority: str, identity: str) -> Dict[str, Any]:
    """Read the criterion from a received copy's raw bytes.

    `authority`  the authserv-id the receiving boundary is expected to stamp.
    `identity`   the domain `header.from` must carry for this to be OUR mail.

    THE FIRST INSTANCE ONLY (O5i.2). A later instance is sender-suppliable, so
    reading any but the outermost builds a gate whose reading the attacker
    writes. `ARC-Authentication-Results` is a DIFFERENT header field and is
    never collected here -- an intermediary's claim about a hop we did not
    observe, meaningful only if the chain validates AND the sealer is trusted,
    and this spec establishes neither.
    """
    headers = BytesHeaderParser(policy=compat32).parsebytes(raw)
    instances = headers.get_all("Authentication-Results") or []

    out: Dict[str, Any] = {
        "instances_present": len(instances),
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

    first = " ".join(instances[0].split())

    # THE AUTHSERV-ID IS DETECTED, NOT ASSUMED. RFC 8601 makes it the mandatory
    # first token, and a major provider omits it, so the field can begin with a
    # method-result. A first token containing "=" is a method-result, which
    # means there is no authserv-id to verify against -- report that, rather
    # than treating `spf=pass` as the name of an authority.
    tok = _FIRST_TOKEN_RE.match(first)
    candidate = tok.group(1) if tok else None
    if candidate is not None and "=" not in candidate:
        out["authserv_id"] = candidate
        out["authority_ok"] = candidate == authority

    for meth, rx in _METHOD_RE.items():
        hit = rx.search(first)
        out["results"][meth] = hit.group(1).lower() if hit else None
    fm = _FROM_RE.search(first)
    out["header_from"] = fm.group(1).lower() if fm else None
    out["identity_ok"] = out["header_from"] == (identity or "").strip().lower()

    if out["authserv_id"] is None:
        out["verdict"] = NO_AUTHSERV_ID
    elif not out["authority_ok"]:
        out["verdict"] = UNTRUSTED_AUTHORITY
    elif out["results"]["dmarc"] != "pass":
        out["verdict"] = NOT_AUTHENTICATED
    elif not out["identity_ok"]:
        # dmarc=pass for somebody else's domain is a pass ABOUT SOMEBODY ELSE.
        out["verdict"] = IDENTITY_MISMATCH
    else:
        out["verdict"] = AUTHENTICATED
    return out


def is_pass(result: Dict[str, Any]) -> bool:
    """Exactly one verdict is a pass. Stated as a function so no caller has to
    remember which of the five non-pass verdicts exist."""
    return result.get("verdict") == AUTHENTICATED
