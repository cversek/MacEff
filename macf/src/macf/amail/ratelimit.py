"""Outbound rate limiting — a PRECONDITION of the live path, not tuning.

WHOSE ASSET THIS PROTECTS. Sending reputation aggregates at the ORGANISATIONAL
domain, not at the sending subdomain: one managed signing key, one feedback
identity keyed to the apex. There is no per-subdomain isolation on this path,
so the blast radius of one over-scoped sender is every agent under the domain
and every future project beneath it.

THE THREAT CASE IS NOT AN ATTACKER. It is the well-intentioned, under-scoped
agent — the one that decides the efficient path to a hard problem is to mail
every expert it can name. That is a reasonable plan and it destroys a shared
resource, which is why this is a control rather than a courtesy.

Two properties that follow, and neither is obvious:

  THE STATE IS ON DISK. A budget held in memory resets when the broker
  restarts, which turns "restart the broker" into a way to spend the budget
  twice. The state is broker-owned and agent-READABLE for the same reason the
  disposition store is: the agent must be able to see its own consumption
  without a socket call, and it must not be able to forge it.

  IT FAILS CLOSED. An unreadable or malformed state file REFUSES rather than
  permitting, following the house rule the push backstop already states: an
  unavailable history means DENY, never "no history found". A rate limiter
  that fails open is trivially defeated by corrupting the file it reads.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


#: The principal a broker-originated message is counted against. Notices are
#: composed by nobody, so they cannot be charged to an agent — spec O5g.5
#: "notices-count-against-the-broker-budget". Named rather than spelled inline
#: so the two places that use it cannot drift.
BROKER_PRINCIPAL = "__broker__"


class RateLimitError(RuntimeError):
    """The limiter could not determine consumption. Refuse; never assume zero."""


@dataclass
class RateLimit:
    """A declared budget. Both fields are required — spec O5b.6
    "outbound-submission-must-be-rate-limited" makes this a PRECONDITION, and a
    precondition with a default is a suggestion.
    """

    max_per_window: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_per_window < 1 or self.window_seconds < 1:
            raise ValueError(
                "a rate limit of zero refuses everything and a window of zero "
                "expires instantly; neither is a budget")


class RateLimiter:
    """Sliding-window consumption, broker-owned and agent-readable.

    SLIDING RATHER THAN FIXED, deliberately. A fixed window lets a sender spend
    the whole budget at the end of one window and the whole budget at the start
    of the next — twice the intended rate, at the moment a burst does the most
    reputational damage. The stored timestamps are bounded by the cap, so the
    sliding window costs nothing in space that the fixed one would have saved.
    """

    def __init__(self, state_dir: Path, limits: Dict[str, RateLimit]):
        self.state_dir = Path(state_dir)
        self.limits = limits
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ state

    def _path(self, principal: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in principal)
        return self.state_dir / f"{safe}.json"

    @contextlib.contextmanager
    def _exclusive(self):
        """Serialise read-modify-write across threads AND processes.

        The same pair the audit log and the disposition store settled on. This
        store has the identical shape — read, decide, write — and the identical
        exposure: the broker is multi-threaded by design, so no attacker is
        needed to produce a lost update.
        """
        self.state_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        with self._lock:
            if fcntl is None:  # pragma: no cover - non-POSIX
                yield
                return
            with open(self.state_dir / ".ratelimit.lock", "a+b") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def _read(self, principal: str) -> List[float]:
        p = self._path(principal)
        try:
            data = json.loads(p.read_text())
        except FileNotFoundError:
            # Expected: nothing sent yet in this deployment. Not a failure, so
            # not a warning — warning here would train readers to ignore the
            # one below, which is the case that matters.
            return []
        except (OSError, ValueError) as e:
            # FAIL CLOSED. An unreadable budget is not an empty budget, and
            # treating it as one hands an unlimited send to whoever can corrupt
            # a file the broker reads.
            print(f"⚠️ MACF: rate-limit state for {principal} is unreadable "
                  f"({e}); REFUSING rather than assuming no consumption",
                  file=sys.stderr)
            raise RateLimitError(f"rate-limit state unreadable: {e}") from e
        stamps = data.get("stamps")
        if not isinstance(stamps, list) or any(
                not isinstance(x, (int, float)) for x in stamps):
            print(f"⚠️ MACF: rate-limit state for {principal} is malformed; "
                  f"REFUSING rather than assuming no consumption",
                  file=sys.stderr)
            raise RateLimitError("rate-limit state malformed")
        return [float(x) for x in stamps]

    def _write(self, principal: str, stamps: List[float]) -> None:
        p = self._path(principal)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"principal": principal, "stamps": stamps},
                                  indent=1))
        # Agent-READABLE so a sender can see its own consumption with no broker
        # call (spec O5b.6b); never agent-writable, or the budget is advisory.
        tmp.chmod(0o644)
        os.replace(tmp, p)

    # ----------------------------------------------------------------- public

    def budget(self, principal: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Window, cap and current consumption — what the agent may READ.

        Spec O5b.6b "the-rate-limit-must-be-observable-to-the-sending-agent".
        The threat case here is good faith, and a control aimed at good faith
        that good faith cannot see is discoverable only by tripping it — which
        teaches the sender the system is unreliable rather than that the
        resource is shared. An attacker learns the limit by hitting it either
        way, so concealment buys nothing against the party it is usually for.
        """
        limit = self.limits.get(principal)
        if limit is None:
            return {"principal": principal, "limited": False,
                    "reason": "no limit declared for this principal"}
        t = time.time() if now is None else now
        try:
            live = [s for s in self._read(principal) if s > t - limit.window_seconds]
        except RateLimitError as e:
            # Reporting is not enforcing: a caller ASKING about its budget gets
            # the error surfaced, not silently rendered as zero used.
            return {"principal": principal, "limited": True,
                    "window_seconds": limit.window_seconds,
                    "max_per_window": limit.max_per_window,
                    "used": None, "remaining": None, "error": str(e)}
        return {"principal": principal, "limited": True,
                "window_seconds": limit.window_seconds,
                "max_per_window": limit.max_per_window,
                "used": len(live),
                "remaining": max(0, limit.max_per_window - len(live))}

    def check_and_consume(self, principal: str, *,
                          now: Optional[float] = None) -> Optional[str]:
        """Charge one send. Returns a refusal reason, or None when permitted.

        CHECK AND CONSUME ARE ONE OPERATION under one lock. Splitting them
        leaves the window every concurrent limiter has: two submissions read
        the same count, both find room, both send, and the cap is exceeded by
        exactly the number of threads that raced.
        """
        limit = self.limits.get(principal)
        if limit is None:
            return None  # unlimited by declaration; the caller decides if that is legal
        t = time.time() if now is None else now
        with self._exclusive():
            stamps = self._read(principal)
            live = [s for s in stamps if s > t - limit.window_seconds]
            if len(live) >= limit.max_per_window:
                # Keep the pruned list: the refusal is a decision point and the
                # window should not silently re-widen because nothing was written.
                self._write(principal, live)
                return (f"rate limit reached: {len(live)}/{limit.max_per_window} "
                        f"in the last {limit.window_seconds}s")
            live.append(t)
            self._write(principal, live)
            return None
