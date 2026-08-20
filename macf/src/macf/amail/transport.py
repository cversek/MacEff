"""Outbound transport — the broker's only route to the internet.

WHAT THIS MODULE IS NOT. It holds no authorization logic. The destination
check, the rate limit and the pre-send gate all run before anything reaches
here (`Broker.submit`), because a transport that authorizes is a boundary
decision made by whatever runs the transport — and on the current binding that
is a script on someone else's edge.

THE CREDENTIAL IS READ AT SEND TIME, from disk, every time. Never held in a
config object: config objects get logged, serialised into error reports, and
repr'd into tracebacks. The path is configuration; the secret is not.

THE PROPERTY REDUCES ENTIRELY TO TOKEN CUSTODY, and this is the clause that
must travel with every description of this layer (spec O5f.5). Egress filtering
blocks agent uids on mail ports and NOT on 443, so an agent can reach the
transport's host. What stops it is that it holds no token. Nothing about the
network topology is doing the work, and a reader who believes otherwise will
weaken custody thinking the network still covers it.

STATUS: the local half is built and tested. THE REAL TRANSPORT IS NOT WIRED,
and this module deliberately does not pretend otherwise -- see NullTransport
and the note on V17 below.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

#: Transport outcomes, mapped onto the disposition vocabulary the ledger uses
#: (spec O5d.7 "terminal-dispositions-are-enumerated-and-closed"). The mapping
#: lives HERE rather than at each call site so two transports cannot disagree
#: about what "temporary failure" means to the ledger.
SENT = "delivered"
DEFERRED = "deferred"
BOUNCED = "bounced"


class TransportError(RuntimeError):
    """The transport could not be used at all. Distinct from a refusal.

    A transport that is broken and a message that was rejected are different
    facts: one should be retried and the other never should, and a caller that
    conflates them retries a permanent rejection forever.
    """


@dataclass
class TransportResult:
    """What the transport reports. `state` is a disposition value, not prose."""

    state: str
    detail: str = ""
    recipients: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        if self.state not in (SENT, DEFERRED, BOUNCED):
            raise ValueError(
                f"{self.state!r} is not a disposition this ledger can hold. A "
                f"transport inventing its own vocabulary is how two components "
                f"compute different balances from identical traffic.")


class NullTransport:
    """No transport. Refuses every send, loudly, and is the DEFAULT.

    THIS EXISTS SO THE ABSENCE CANNOT BE MISTAKEN FOR A WORKING PATH. The
    obvious alternative -- leave `transport=None` and skip sending -- makes a
    deployment with no transport indistinguishable from one whose sends all
    succeeded, because both produce no error and no delivered mail. That is the
    silent drop this subsystem exists to prevent, rebuilt on the sending side.

    It refuses rather than raising at construction because a broker with no
    outbound leg is a legitimate deployment today: inbound works, agent-to-agent
    works, and only internet sending is unavailable. The refusal says which.
    """

    name = "null"

    def send(self, message: Any, credential: str) -> TransportResult:
        raise TransportError(
            "no outbound transport is configured; this broker cannot reach the "
            "internet. Mail was NOT sent. Refusing rather than reporting a "
            "delivery that did not happen.")


class HttpTransport:
    """Submit over HTTPS to an endpoint that performs no authorization.

    NOT EXERCISED AGAINST A REAL ENDPOINT YET. The invariant that authorization
    completes before the credential is touched (V17) was once asserted HOLDS on
    the strength of a tripwire run against a TEST-DOUBLE credential on a path
    where no transport existed -- the permitted arm "stopped at transport"
    precisely because there was none. That assertion was withdrawn, and it will
    not be made again from a double: wiring a real credential inserts new code
    between authorization and the network, which is exactly where the ordering
    can regress.

    So this class is written, and V17 stays SPECIFIED-NOT-BUILT until it has
    run against the real endpoint with the real token.
    """

    name = "http"

    def __init__(self, endpoint: str, *, timeout: float = 30.0,
                 opener: Optional[Any] = None):
        if not endpoint:
            raise ValueError("an HTTP transport needs an endpoint")
        self.endpoint = endpoint
        self.timeout = timeout
        # Injected so the SEQUENCE can be tested without the network. The
        # injection is not a substitute for running it against the real
        # endpoint, and the docstring above says so rather than letting a green
        # suite imply it.
        self._opener = opener

    def send(self, message: Any, credential: str) -> TransportResult:
        import json as _json
        import urllib.error
        import urllib.request

        if not credential:
            # The credential arrives from the caller, which read it from disk
            # at send time. An empty one here means custody failed upstream and
            # the send must not proceed -- reaching the network with no
            # credential would produce an edge refusal that reads as a network
            # problem rather than as a custody failure.
            raise TransportError(
                "no submission credential was supplied to the transport; "
                "refusing to reach the network without one")

        payload = _json.dumps({
            "from": getattr(message, "sender", None),
            "to": list(getattr(message, "to", None) or []),
            "subject": getattr(message, "subject", None),
            "body": getattr(message, "body", None),
        }).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=payload, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {credential}"})
        opener = self._opener or urllib.request.urlopen
        try:
            with opener(req, timeout=self.timeout) as resp:
                code = getattr(resp, "status", None) or resp.getcode()
                return self._classify(code, resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            return self._classify(e.code, e.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            # Could not reach it at all. NOT a bounce: a bounce is a decision
            # somebody made about this message, and nobody made one.
            raise TransportError(f"transport unreachable: {e}") from e

    @staticmethod
    def _classify(code: int, body: str) -> TransportResult:
        """HTTP status -> disposition. The 4xx/5xx split is the whole point.

        A 5xx is the far side saying "not now"; a 4xx is it saying "not this
        message". Collapsing them makes a caller retry a permanent rejection
        forever, or abandon a message the far side would have accepted a minute
        later. The detail is truncated because it is remote-supplied text that
        ends up in a broker-owned record.
        """
        detail = (body or "")[:200]
        if 200 <= code < 300:
            return TransportResult(SENT, f"accepted ({code})")
        if code in (408, 429) or 500 <= code < 600:
            return TransportResult(DEFERRED, f"temporary failure ({code}): {detail}")
        return TransportResult(BOUNCED, f"rejected ({code}): {detail}")


def read_credential(path: Optional[Path]) -> str:
    """Read the submission credential from disk, at send time.

    Not cached, deliberately. A cached secret outlives the file it came from:
    rotating the credential, or removing it during an incident, would leave the
    running broker still sending with the old one -- and the custody check that
    runs at startup would have nothing to say about it, because it already ran.
    """
    if path is None:
        raise TransportError(
            "no credential path configured; the broker holds nothing to send with")
    try:
        return Path(path).read_text().strip()
    except OSError as e:
        print(f"⚠️ MACF: the submission credential could not be read ({e}); "
              f"mail is NOT being sent", file=sys.stderr)
        raise TransportError(f"credential unreadable: {e}") from e
