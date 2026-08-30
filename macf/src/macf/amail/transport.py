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
#:
#: `ACCEPTED` IS NOT `delivered`, AND THIS IS THE CORRECTION THAT MATTERS.
#: The endpoint answers 202 "accepted for sending", which is the platform
#: taking CUSTODY -- not the message arriving. Measured at the peer's endpoint:
#: the 202 returned while the message was not yet visible at the receiving
#: mailbox; it appeared seconds later. So the send call reports success while
#: the message exists nowhere the receiver can see, and nothing downstream of
#: that acceptance is observable to the endpoint at all -- no bounce, no
#: deferral, no delivery.
#:
#: A transport that mapped 2xx to `delivered` would therefore record a delivery
#: nobody had witnessed, on the happy path, for every message it ever sent.
#: That is the silent success this ledger exists to prevent.
#: The User-Agent the transport identifies itself with. NOT COSMETIC, and the
#: default is actively harmful: urllib sends `Python-urllib/x.y`, which the
#: edge's Browser Integrity Check refuses with a 403 carrying `error code:
#: 1010` -- BEFORE the access layer evaluates the credential at all. Measured
#: against the live endpoint: identical request, default agent 403/1010, named
#: agent 400 with the Worker's own JSON. So without this line every real send
#: fails at the edge while the classifier reports a credential that was never
#: examined.
USER_AGENT = "amail-broker/0.5 (+macf)"

ACCEPTED = "submitted"        # NON-TERMINAL. Custody accepted, arrival unknown.
DEFERRED = "deferred"         # non-terminal: the far side said "not now"
BOUNCED = "bounced"           # terminal: the far side said "not this message"

#: `delivered` is DELIBERATELY ABSENT from this module. On this binding it is
#: unreachable: no signal the endpoint can send means "it arrived". If the
#: ledger ever shows `delivered` for an internet send, it came from a source
#: that is not the transport -- a receiver-side observation, or a defect.
#:
#: `bounced` IS ALSO UNREACHABLE ON THIS BINDING, and saying so is the same
#: honesty applied to the other end of the enum. Two facts compound:
#:   - the envelope return path is PROVIDER-OWNED and its local part reads as
#:     a bounce-drop, so a refusal made by a RECEIVER never reaches us; and
#:   - every destination must be verified at the sending provider before we
#:     may send to it at all (measured: `422 DEST_NOT_VERIFIED`), so the
#:     ordinary way to provoke a hard bounce -- mail a nonexistent mailbox --
#:     is closed by the same gate that protects the path.
#: So it is unreachable AND the experiment that would confirm it is out of
#: reach, which is a weaker epistemic position than the `delivered` case and
#: is stated as such rather than rounded up.
#:
#: WHAT THIS MODULE STILL PRODUCES is `bounced` for a refusal THE ENDPOINT
#: ITSELF makes (a 4xx), which is a different fact from a receiver's bounce
#: and is the only one observable here.
#:
#: THE CONSEQUENCE BELONGS TO THE LEDGER, not here: if no positive terminal
#: disposition is observable, a correctly submitted message ages from
#: `submitted` to `abandoned`, and a conservation check treating `abandoned`
#: as an anomaly reports a shortfall for entirely correct behaviour. The
#: failure mode that follows is somebody widening the tolerance until the
#: alarm stops complaining, after which it never complains. `abandoned` is
#: therefore declared a NORMAL terminal state for this binding, in the
#: deployment's binding notes rather than in the normative text -- the
#: normative enum is unchanged, and what changed is what this transport can
#: observe.


class TransportError(RuntimeError):
    """The transport could not be used at all. Distinct from a refusal.

    A transport that is broken and a message that was rejected are different
    facts: one should be retried and the other never should, and a caller that
    conflates them retries a permanent rejection forever.
    """


def _one_recipient(message: Any, recipient: Optional[str]) -> str:
    """The single recipient this submission is for.

    REFUSES rather than joining. An earlier version comma-joined the message's
    recipient list, which the endpoint answers with MISSING_FIELD because it
    requires a non-empty STRING -- so every multi-recipient send failed with a
    message that named the wrong problem. Joining was never measured to work,
    and a transport that quietly does the unmeasured thing when handed more
    than it can carry is how an untested path stays in a live system.
    """
    if recipient:
        return recipient
    to = list(getattr(message, "to", None) or [])
    if len(to) == 1:
        return to[0]
    raise TransportError(
        f"this transport carries ONE recipient per submission and was given "
        f"{len(to)}. The caller must make one call per recipient; joining an "
        f"address list is unmeasured against this endpoint and is not done "
        f"silently. Authorization is unaffected -- it is decided once, "
        f"upstream, for the whole submission.")


@dataclass
class TransportResult:
    """What the transport reports. `state` is a disposition value, not prose."""

    state: str
    detail: str = ""
    recipients: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        if self.state not in (ACCEPTED, DEFERRED, BOUNCED):
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

    def send(self, message: Any, credential: str,
             recipient: Optional[str] = None) -> TransportResult:
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

    def send(self, message: Any, credential: str,
             recipient: Optional[str] = None) -> TransportResult:
        """Submit ONE message to ONE recipient.

        ONE RECIPIENT PER SUBMISSION, and this is the transport CONTRACT rather
        than a convenience. The endpoint requires `to` to be a non-empty
        STRING; comma-joining an address list is the obvious reading of that
        and it has never been measured, so it stays out of the live system.

        It is also the better shape independently of the endpoint. The ledger's
        unit is the message-recipient PAIR and transport outcomes are
        per-recipient by nature -- one delivered, another bounced. A
        per-recipient transport call makes each disposition a DIRECT
        OBSERVATION instead of a decomposition of a joint result, which is what
        an undefined derivation would otherwise have to invent.

        THIS DOES NOT SPLIT AN AUTHORIZATION. Multi-recipient submissions are
        all-or-nothing (spec O5b.7): if any destination is refused the whole
        submission is refused, and that decision is made ONCE, upstream, before
        anything reaches here. The broker then makes N transport calls having
        already decided. Nothing is silently split -- the split is downstream
        of the decision and visible in the ledger as N records.
        """
        import json as _json
        import urllib.error
        import urllib.request

        if not credential or not getattr(credential, "complete", False):
            # The credential arrives from the caller, which read it from disk
            # at send time. An absent or PARTIAL one means custody failed
            # upstream and the send must not proceed -- reaching the network
            # without it produces an edge refusal that reads as a network
            # problem rather than as a custody failure.
            #
            # Partial matters now that the credential has two halves: an id
            # with no secret would sail past a truthiness check and fail at the
            # edge, where the diagnosis is someone else's log.
            raise TransportError(
                "no complete submission credential was supplied to the "
                "transport; refusing to reach the network without one")

        payload = _json.dumps({
            "from": getattr(message, "sender", None),
            # A STRING, NOT A LIST. The endpoint requires all four fields to
            # be non-empty STRINGS and answers a JSON array with
            # `{"status":"rejected","reason":"MISSING_FIELD","field":"to"}` --
            # measured, after both sides read the schema and agreed it matched.
            # Neither of us saw it by reading; the running endpoint said so.
            #
            "to": _one_recipient(message, recipient),
            "subject": getattr(message, "subject", None),
            "body": getattr(message, "body", None),
        }).encode("utf-8")
        # TWO HEADERS, NOT A BEARER TOKEN. Corrected against the deployed
        # endpoint: it sits behind a platform access layer that evaluates a
        # SERVICE TOKEN -- an id and a secret -- at the edge, before the
        # receiving code runs at all. There is no bearer scheme here, and the
        # credential is not something the far side's code checks: it is
        # something the platform checks before that code exists.
        #
        # This was my assumption and it was wrong. It is corrected here rather
        # than accommodated on both sides, because a transport that sent both
        # shapes "to be safe" would put the secret on a header nobody reads.
        headers = {"Content-Type": "application/json",
                   "User-Agent": USER_AGENT}
        headers.update(credential.as_headers())
        req = urllib.request.Request(
            self.endpoint, data=payload, method="POST", headers=headers)
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
        """HTTP status -> disposition. Three splits, each for its own reason.

        2xx IS NOT DELIVERY. It is acceptance of custody, and it maps to the
        NON-TERMINAL `submitted`. See the ACCEPTED constant: the measurement
        behind it is a 202 returning before the message was visible anywhere
        the receiver could see.

        THE 4xx/5xx SPLIT: a 5xx is the far side saying "not now"; a 4xx is it
        saying "not this message". Collapsing them makes a caller retry a
        permanent rejection forever, or abandon a message the far side would
        have accepted a minute later.

        403 IS NEITHER, and raises. An edge refusal is the platform rejecting
        OUR CREDENTIAL before the far side ever saw the message -- nobody made
        a decision about this message, so recording a disposition for it would
        blame the message for a custody failure. It is the same class as
        unreachable: a condition of ours, not a verdict on the mail.
        """
        detail = (body or "")[:200]
        if 200 <= code < 300:
            return TransportResult(ACCEPTED, f"accepted for sending ({code})")
        if code == 403 and "1010" in detail:
            # THE WAF, NOT THE ACCESS LAYER, and the difference is the whole
            # diagnosis. Error 1010 is a Browser Integrity Check refusing the
            # USER-AGENT before the credential is evaluated, so reporting it as
            # a custody failure sends whoever is on call to the credential --
            # which is correct, present and never looked at. A wrong refusal
            # message is worse than none: it is a confident pointer at an
            # innocent component.
            raise TransportError(
                "the edge's integrity check refused this request (403, error "
                "code 1010) before the access layer evaluated anything. This "
                "measures the WAF, NOT the credential: the submission "
                "credential was never examined. Check the User-Agent, not the "
                "token.")
        if code == 403:
            raise TransportError(
                "the edge refused this request (403): the submission credential "
                "was not accepted, so the message was never offered to anyone. "
                "This is a custody failure, not a rejection of the mail.")
        if code in (408, 429) or 500 <= code < 600:
            return TransportResult(DEFERRED, f"temporary failure ({code}): {detail}")
        return TransportResult(BOUNCED, f"rejected ({code}): {detail}")


@dataclass
class AccessCredential:
    """A service-token credential: an id and a secret, both required.

    TWO HALVES, AND `complete` EXISTS BECAUSE ONE HALF IS THE DANGEROUS STATE.
    A credential holding an id and no secret is truthy, non-empty, and passes
    every naive check -- and then fails at the edge, where the diagnosis lives
    in somebody else's logs and reads as a network problem. The partial state
    has to be nameable here, on our side of the boundary.
    """

    client_id: str = ""
    client_secret: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def as_headers(self) -> Dict[str, str]:
        return {"CF-Access-Client-Id": self.client_id,
                "CF-Access-Client-Secret": self.client_secret}

    def __repr__(self) -> str:
        # NEVER the values. This object ends up in tracebacks and error
        # reports, which is exactly where a secret should not be, and a
        # dataclass would print both halves by default.
        return (f"AccessCredential(client_id=<{len(self.client_id)} chars>, "
                f"client_secret=<{len(self.client_secret)} chars>, "
                f"complete={self.complete})")


def read_credential(path: Optional[Path]) -> "AccessCredential":
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
        text = Path(path).read_text()
    except OSError as e:
        print(f"⚠️ MACF: the submission credential could not be read ({e}); "
              f"mail is NOT being sent", file=sys.stderr)
        raise TransportError(f"credential unreadable: {e}") from e

    # SELF-LABELLING LINES, not positional values. Order is the thing that gets
    # misremembered, and a swapped id and secret produce an edge refusal whose
    # cause is invisible from here.
    fields: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")  # noqa: MACEFF005 - str.partition's (before, sep, after) contract is fixed by the stdlib; there is no callee whose order can change
        fields[k.strip().upper()] = v.strip().strip("\"'")

    cred = AccessCredential(fields.get("CF_ACCESS_CLIENT_ID", ""),
                            fields.get("CF_ACCESS_CLIENT_SECRET", ""))
    if not cred.complete:
        # NAMED, not counted. Which half is missing is the whole diagnostic,
        # and reporting "invalid credential" would send the reader to the
        # wrong file.
        missing = [n for n, v in (("CF_ACCESS_CLIENT_ID", cred.client_id),
                                  ("CF_ACCESS_CLIENT_SECRET", cred.client_secret))
                   if not v]
        raise TransportError(
            f"the submission credential is INCOMPLETE: {', '.join(missing)} "
            f"absent or empty. A partial credential fails at the edge, where "
            f"the failure reads as a network problem rather than as ours.")
    return cred
