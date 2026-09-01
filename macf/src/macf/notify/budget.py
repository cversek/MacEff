"""What notices may cost, stated as a fraction of REMAINING context.

The obvious form is a fraction of the context WINDOW, and it is the wrong one.
A window-relative budget is position-independent: it permits the same spend at
5% used as at 95%, which is exactly backwards, because the cost of an
interruption is not what it consumes but what it DISPLACES. Late in a cycle the
same bytes displace the work the agent is trying to finish before compaction.

A remainder-relative budget tightens on its own as the window fills. Nobody has
to remember to tighten it, there is no threshold to tune, and it degrades
smoothly rather than switching at a cliff. The peer proposed this framing and it
is more honest for a second reason: remaining context is DIRECTLY MEASURABLE from
the transcript, while "fraction of window" quietly assumes the window is what
someone configured rather than what is actually left.

THE BUDGET DOES NOT SILENCE ANYTHING BY ITSELF. It is consulted, and exceeding it
is REPORTED. An interrupt budget that suppressed notices without saying so would
be a silence the agent could not attribute -- the defect this whole subsystem
exists to cure, arriving through the mechanism meant to be considerate.
"""
import sys
from dataclasses import dataclass
from typing import Optional

# A notice is a few hundred bytes of fixed text. This fraction is deliberately
# small: the question is not "can we afford one notice" -- we always can -- but
# "how many interruptions may a cycle absorb before they are the work". At 200k
# remaining, 0.5% is roughly a thousand tokens, which is a couple of dozen
# notices; at 20k remaining it is a hundred tokens, which is two or three.
DEFAULT_FRACTION = 0.005

# Rough and stated as rough: a token is about four bytes of English prose. Used
# only to convert a rendered notice into the unit the budget is denominated in.
BYTES_PER_TOKEN = 4


@dataclass
class Budget:
    """An allowance derived from what is LEFT, and the spend against it."""

    fraction: float = DEFAULT_FRACTION
    spent_tokens: int = 0

    def allowance(self, tokens_remaining: int) -> int:
        """Tokens this cycle may spend on notices, given what is left.

        Returns 0 for a non-positive remainder rather than raising: a caller
        asking the budget at the very end of a window should be told there is
        nothing, not handed an exception to interpret.
        """
        if tokens_remaining is None or tokens_remaining <= 0:
            return 0
        return int(tokens_remaining * self.fraction)

    def cost(self, rendered: str) -> int:
        """What delivering this notice costs, in the budget's unit."""
        return max(1, len(rendered) // BYTES_PER_TOKEN)

    def would_exceed(self, rendered: str, tokens_remaining: int) -> bool:
        return self.spent_tokens + self.cost(rendered) > self.allowance(tokens_remaining)

    def charge(self, rendered: str) -> int:
        """Record a delivery against the allowance. Returns the new total."""
        self.spent_tokens += self.cost(rendered)
        return self.spent_tokens

    def check(self, rendered: str, tokens_remaining: int) -> bool:
        """True if this notice fits. ANNOUNCES when it does not.

        Announcing rather than returning quietly is the point: the caller decides
        what to do, and the operator can see that a budget -- not a fault -- is
        what changed the behaviour. A budget that suppressed silently would be
        indistinguishable from a broken notifier.
        """
        if not self.would_exceed(rendered, tokens_remaining):
            return True
        print(
            f"⚠️ MACF: notice budget exceeded -- spent {self.spent_tokens} of "
            f"{self.allowance(tokens_remaining)} token(s) allowed at "
            f"{tokens_remaining} remaining ({self.fraction:.1%} of what is left). "
            f"This notice is over budget; the store still holds it.",
            file=sys.stderr,
        )
        return False


def tokens_remaining(session_id: Optional[str] = None) -> Optional[int]:
    """Measured remaining context, or None when it cannot be measured.

    None is NOT zero and callers must not treat it as such. An unmeasurable
    remainder means the instrument is unavailable, and refusing every notice on
    that basis would convert a missing measurement into a silence -- an emptiness
    the caller created, read as a fact about the world.
    """
    try:
        from ..utils.tokens import get_token_info
        info = get_token_info(session_id) or {}
        value = info.get("tokens_remaining")
        return int(value) if value is not None else None
    except (ImportError, OSError, ValueError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: notice budget could not measure remaining context "
              f"({e}); proceeding UNBUDGETED", file=sys.stderr)
        return None


__all__ = ["Budget", "DEFAULT_FRACTION", "tokens_remaining"]
