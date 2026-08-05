"""What has actually been proven about a message's origin.

The outbound path classifies every Message field by how far it is trusted —
minted by the broker, checked against the kernel, bound to a decision, or passed
through untouched. This is that idea extended to mail the broker did NOT mint,
where the question is not "who may I trust to set this field" but "what did I
manage to establish about where this came from".

The four classes are ordered, and the ordering is the point. A message is never
promoted to a class stronger than what was proven, and the distinction between
ATTESTED and DOMAIN_AUTH is the one everything else rests on:

    ATTESTED     a signature verified against THIS CORRESPONDENT'S public key.
                 The person is proven.
    DOMAIN_AUTH  DMARC passed with alignment, evaluated at our own boundary.
                 The DOMAIN is proven. The person is NOT.
    UNVERIFIED   it arrived. Nothing about its origin was established.
    SUSPECT      authentication was attempted and FAILED, or the message
                 resembles a contact it is not from.

DOMAIN_AUTH is the class people mistake for authenticity, so it is worth being
explicit: a message reading `"Some Trusted Person" <attacker@attacker.test>`
passes DMARC cleanly, because the attacker's domain genuinely is the attacker's
domain. Domain authentication says the envelope was not forged. It says nothing
whatever about who wrote the message.

SUSPECT IS NOT A WORSE UNVERIFIED. A failed check is evidence; an absent check
is not. Collapsing them loses the only signal that distinguishes "we could not
tell" from "we looked, and it did not add up" — and a system that renders those
identically has discarded the more valuable of the two.
"""
from __future__ import annotations

from enum import Enum


class TrustClass(str, Enum):
    ATTESTED = "attested"
    DOMAIN_AUTH = "domain_auth"
    UNVERIFIED = "unverified"
    SUSPECT = "suspect"

    @property
    def proves_correspondent(self) -> bool:
        """True only for ATTESTED.

        Exposed as a property so callers ask a question with one answer rather
        than each writing their own comparison — which is how DOMAIN_AUTH ends
        up quietly treated as authenticity somewhere downstream.
        """
        return self is TrustClass.ATTESTED

    @property
    def label(self) -> str:
        """Short human-facing text. Rendered FROM METADATA, never from the body."""
        return {
            TrustClass.ATTESTED: "signed by this correspondent",
            TrustClass.DOMAIN_AUTH: "domain authenticated — sender NOT proven",
            TrustClass.UNVERIFIED: "unverified origin",
            TrustClass.SUSPECT: "SUSPECT — authentication failed",
        }[self]


#: Locally-submitted mail. The broker took the submitter's identity from the
#: kernel via SO_PEERCRED before it accepted the message, so authorship is
#: established by something stronger than a signature — the sender could not
#: have been anyone else. Classifying it ATTESTED is a statement of what was
#: proven, not a courtesy extended to our own agents.
LOCAL_SUBMISSION = TrustClass.ATTESTED
