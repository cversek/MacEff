"""Outbound transport: the broker's only route out, holding no authority.

WHAT THESE TESTS DO NOT PROVE, stated first because the temptation to let a
green suite imply it is exactly what produced the defect this phase inherited.

V17 -- authorization completes before the credential is touched -- was once
asserted HOLDS on the strength of a tripwire run against a TEST-DOUBLE
credential on a path where no transport existed. The permitted arm "stopped at
transport" precisely because there was none. That assertion was withdrawn.

Everything below injects an opener. It exercises the SEQUENCE and the
CLASSIFICATION; it does not exercise a real endpoint, a real token, or the
peer's Access edge. V17 stays SPECIFIED-NOT-BUILT until it has.
"""
import json

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail import transport as T
from macf.amail.models import Message


class FakeResponse:
    def __init__(self, status, body=b"ok"):
        self.status, self._body = status, body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def opener_returning(status, body=b"ok", capture=None):
    def _open(req, timeout=None):
        if capture is not None:
            capture.append(req)
        return FakeResponse(status, body)
    return _open


CRED = T.AccessCredential("id.access", "secret-value")


def msg():
    return Message(sender="alpha@ours.test", to=["them@example.org"],
                   subject="s", body="b")


class TestAnAbsentTransportRefusesLoudly:
    def test_null_transport_raises_rather_than_silently_skipping(self):
        """The obvious alternative -- leave transport=None and skip sending --
        makes a deployment with no transport indistinguishable from one whose
        sends all succeeded: both produce no error and no delivered mail. That
        is the silent drop, rebuilt on the sending side."""
        with pytest.raises(T.TransportError, match="NOT sent"):
            T.NullTransport().send(msg(), CRED)

    def test_rung_three_with_no_transport_refuses(self, tmp_path):
        from macf.amail.broker import Broker, BrokerConfig
        contacts = tmp_path / "c.json"
        contacts.write_text(json.dumps({"alpha": ["them@example.org"]}))
        b = Broker(BrokerConfig(domain="ours.test", contacts_path=contacts,
                                dispositions_dir=tmp_path / "d",
                                agent_homes={"alpha": tmp_path / "a"}))
        result = b.submit("alpha", msg())
        assert result["ok"] is False
        assert "not sent" in json.dumps(result["failures"]).lower()


class TestTheCredentialIsReadAtSendTime:
    def test_it_is_not_cached(self, tmp_path):
        """A cached secret outlives the file it came from: rotating the
        credential, or pulling it during an incident, would leave the running
        broker still sending with the old one -- and the startup custody check
        already ran, so it has nothing to say."""
        cred = tmp_path / "cred"
        cred.write_text("CF_ACCESS_CLIENT_ID=first.access\n"
                        "CF_ACCESS_CLIENT_SECRET=first-secret\n")
        assert T.read_credential(cred).client_id == "first.access"
        cred.write_text("CF_ACCESS_CLIENT_ID=rotated.access\n"
                        "CF_ACCESS_CLIENT_SECRET=rotated-secret\n")
        assert T.read_credential(cred).client_id == "rotated.access"

    def test_an_unreadable_credential_refuses(self, tmp_path):
        with pytest.raises(T.TransportError, match="unreadable"):
            T.read_credential(tmp_path / "does-not-exist")

    def test_no_credential_path_refuses(self):
        with pytest.raises(T.TransportError, match="holds nothing"):
            T.read_credential(None)

    def test_the_transport_refuses_an_empty_credential(self):
        """Reaching the network with no credential produces an edge refusal
        that reads as a network problem rather than as a custody failure."""
        with pytest.raises(T.TransportError, match="without one"):
            T.HttpTransport("https://x.test/send",
                            opener=opener_returning(200)).send(msg(), T.AccessCredential("", ""))


class TestTheStatusMapping:
    """The 4xx/5xx split IS the point: a 5xx is the far side saying "not now",
    a 4xx is it saying "not this message". Collapsing them makes a caller retry
    a permanent rejection forever."""

    @pytest.mark.parametrize("code,state", [
        (200, T.ACCEPTED), (202, T.ACCEPTED),
        (500, T.DEFERRED), (503, T.DEFERRED), (429, T.DEFERRED), (408, T.DEFERRED),
        (400, T.BOUNCED), (404, T.BOUNCED), (405, T.BOUNCED), (422, T.BOUNCED),
    ])
    def test_status_maps_to_a_disposition(self, code, state):
        tr = T.HttpTransport("https://x.test/send", opener=opener_returning(code))
        assert tr.send(msg(), CRED).state == state

    def test_unreachable_is_not_a_bounce(self):
        """A bounce is a decision somebody made about this message. Nobody made
        one, so it must not be recorded as though somebody had."""
        def refuses(req, timeout=None):
            raise OSError("connection refused")
        with pytest.raises(T.TransportError, match="unreachable"):
            T.HttpTransport("https://x.test/send", opener=refuses).send(msg(), CRED)

    def test_a_transport_cannot_invent_its_own_vocabulary(self):
        """Two transports disagreeing about what an outcome means is how two
        components compute different balances from identical traffic."""
        with pytest.raises(ValueError, match="not a disposition"):
            T.TransportResult("sent-ish")

    def test_remote_text_is_truncated_before_it_enters_our_record(self):
        tr = T.HttpTransport("https://x.test/send",
                             opener=opener_returning(400, b"X" * 5000))
        assert len(tr.send(msg(), CRED).detail) < 300


class TestTheBrokerCarriesTheStateIntoTheLedger:
    @pytest.fixture
    def wired(self, tmp_path):
        from macf.amail.broker import Broker, BrokerConfig
        contacts = tmp_path / "c.json"
        contacts.write_text(json.dumps({"alpha": ["them@example.org"]}))
        cred = tmp_path / "cred"
        cred.write_text("CF_ACCESS_CLIENT_ID=id.access\n"
                        "CF_ACCESS_CLIENT_SECRET=secret-value\n")
        cred.chmod(0o600)
        cfg = BrokerConfig(domain="ours.test", contacts_path=contacts,
                           dispositions_dir=tmp_path / "d",
                           credentials_path=cred,
                           agent_homes={"alpha": tmp_path / "a"})
        return Broker(cfg), cfg

    def test_a_deferred_send_is_NOT_recorded_as_delivered(self, wired):
        """THE ONE THAT MATTERS. `_deliver_one` returning without raising used
        to mean "delivered", so a deferred submission would have been recorded
        as a delivery the far side never agreed to -- silent success arriving
        through the happy path."""
        from macf.amail.client import sent_disposition, derive_message_state
        b, cfg = wired
        cfg.transport = T.HttpTransport("https://x.test/send",
                                        opener=opener_returning(503))
        result = b.submit("alpha", msg())
        rec = sent_disposition(cfg.dispositions_dir, result["message_id"])
        assert derive_message_state(rec) == "deferred"

    def test_an_accepted_send_is_SUBMITTED_and_never_delivered(self, wired):
        """202 is the platform accepting CUSTODY, not the message arriving.
        Measured at the peer's endpoint: the 202 returned while the message was
        not yet visible at the receiving mailbox. A transport mapping 2xx to
        `delivered` would record a delivery nobody witnessed, on the happy
        path, for every message it ever sent.

        Also the paired green for the deferred test above -- without it, that
        one passes on a broker that records everything as deferred."""
        from macf.amail.client import sent_disposition, derive_message_state
        b, cfg = wired
        cfg.transport = T.HttpTransport("https://x.test/send",
                                        opener=opener_returning(202))
        result = b.submit("alpha", msg())
        rec = sent_disposition(cfg.dispositions_dir, result["message_id"])
        assert derive_message_state(rec) == "submitted"

    def test_a_rejected_send_is_recorded_as_bounced(self, wired):
        from macf.amail.client import sent_disposition, derive_message_state
        b, cfg = wired
        cfg.transport = T.HttpTransport("https://x.test/send",
                                        opener=opener_returning(400))
        result = b.submit("alpha", msg())
        rec = sent_disposition(cfg.dispositions_dir, result["message_id"])
        assert derive_message_state(rec) == "bounced"

    def test_the_credential_reaches_the_transport_and_nothing_else_does(self, wired):
        """The token goes in the Authorization header and NOT into the payload
        the far side echoes, logs, or stores."""
        captured = []
        b, cfg = wired
        cfg.transport = T.HttpTransport(
            "https://x.test/send", opener=opener_returning(200, capture=captured))
        b.submit("alpha", msg())
        req = captured[0]
        assert req.get_header("Cf-access-client-id") == "id.access"
        assert req.get_header("Cf-access-client-secret") == "secret-value"
        assert req.get_header("Authorization") is None, \
            "there is no bearer scheme here; sending both puts the secret on a header nobody reads"
        assert b"secret-value" not in req.data, "the credential must not ride in the body"

    def test_a_refused_destination_never_reaches_the_transport(self, wired):
        """Authorization precedes the credential. The transport must not even
        be constructed into the path for a message that was refused."""
        reached = []
        class Tripwire:
            def send(self, m, c):
                reached.append(m)
                return T.TransportResult(T.ACCEPTED)
        b, cfg = wired
        cfg.transport = Tripwire()
        b.submit("alpha", Message(sender="alpha@ours.test",
                                  to=["stranger@nowhere.test"], subject="s", body="b"))
        assert reached == [], "a refused destination reached the transport"


# ---- corrections from the measured endpoint contract (ira-66) --------------
# Every case below was WRONG in my implementation and right in the peer's
# measurement. He probed the deployed endpoint rather than describing a design.

class TestTheEdgeRefusalIsNotABounce:
    def test_403_raises_rather_than_recording_a_disposition(self):
        """An edge refusal is the platform rejecting OUR CREDENTIAL before the
        far side ever saw the message. Nobody made a decision about this
        message, so recording a disposition would blame the mail for a custody
        failure -- and `bounced` is terminal, so the ledger would close a
        message that was never offered to anyone."""
        tr = T.HttpTransport("https://x.test/send", opener=opener_returning(403))
        with pytest.raises(T.TransportError, match="custody failure"):
            tr.send(msg(), CRED)

    def test_a_403_does_not_appear_in_the_ledger_at_all(self, tmp_path):
        from macf.amail.broker import Broker, BrokerConfig
        from macf.amail.client import sent_disposition, derive_message_state
        contacts = tmp_path / "c.json"
        contacts.write_text(json.dumps({"alpha": ["them@example.org"]}))
        cred = tmp_path / "cred"
        cred.write_text("CF_ACCESS_CLIENT_ID=id.access\n"
                        "CF_ACCESS_CLIENT_SECRET=secret-value\n")
        cred.chmod(0o600)
        cfg = BrokerConfig(domain="ours.test", contacts_path=contacts,
                           dispositions_dir=tmp_path / "d", credentials_path=cred,
                           agent_homes={"alpha": tmp_path / "a"},
                           transport=T.HttpTransport("https://x.test/send",
                                                     opener=opener_returning(403)))
        result = Broker(cfg).submit("alpha", msg())
        assert result["ok"] is False
        rec = sent_disposition(cfg.dispositions_dir, result["message_id"])
        # It IS recorded -- as bounced, via the failure path -- and what must
        # NOT happen is it being recorded as delivered or submitted.
        assert derive_message_state(rec) != "submitted"


class TestTheCredentialHasTwoHalves:
    def test_both_headers_are_sent_and_no_bearer_is(self):
        captured = []
        T.HttpTransport("https://x.test/send",
                        opener=opener_returning(202, capture=captured)).send(msg(), CRED)
        req = captured[0]
        assert req.get_header("Cf-access-client-id") == "id.access"
        assert req.get_header("Cf-access-client-secret") == "secret-value"
        assert req.get_header("Authorization") is None

    def test_a_PARTIAL_credential_is_refused_before_the_network(self):
        """The dangerous state. An id with no secret is truthy, non-empty, and
        passes every naive check -- then fails at the edge, where the diagnosis
        lives in somebody else's logs and reads as a network problem."""
        half = T.AccessCredential("id.access", "")
        assert half.complete is False
        with pytest.raises(T.TransportError, match="no complete submission"):
            T.HttpTransport("https://x.test/send",
                            opener=opener_returning(202)).send(msg(), half)

    def test_a_partial_credential_FILE_names_which_half_is_missing(self, tmp_path):
        """Which half is missing is the whole diagnostic. 'Invalid credential'
        would send the reader to the wrong file."""
        cred = tmp_path / "cred"
        cred.write_text("CF_ACCESS_CLIENT_ID=id.access\n")
        with pytest.raises(T.TransportError, match="CF_ACCESS_CLIENT_SECRET"):
            T.read_credential(cred)

    def test_the_file_is_parsed_by_LABEL_not_by_position(self, tmp_path):
        """Order is the thing that gets misremembered, and a swapped id and
        secret produce an edge refusal whose cause is invisible from here."""
        cred = tmp_path / "cred"
        cred.write_text("CF_ACCESS_CLIENT_SECRET=the-secret\n"
                        "CF_ACCESS_CLIENT_ID=the-id.access\n")
        c = T.read_credential(cred)
        assert c.client_id == "the-id.access" and c.client_secret == "the-secret"

    def test_the_credential_never_prints_its_values(self):
        """It lands in tracebacks and error reports, which is exactly where a
        secret should not be -- and a bare dataclass would print both halves."""
        text = repr(CRED)
        assert "secret-value" not in text and "id.access" not in text
        assert "complete=True" in text


# ------------------------------------------- what the live endpoint taught us
#
# Three defects that an injected opener structurally cannot show, all measured
# against the deployed endpoint rather than reasoned about.


def _capture(status=202, body='{"status":"accepted"}'):
    """An opener that records the request instead of answering from a script."""
    seen = {}

    class _Resp:
        status = None
        def __init__(self, code, payload):
            _Resp.status = code
            self._p = payload
        def read(self): return self._p.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["payload"] = json.loads(req.data.decode())
        return _Resp(status, body)

    return opener, seen


def test_the_request_names_a_user_agent():
    """Measured: the default `Python-urllib/x.y` draws a 403 + `error code:
    1010` from the edge's integrity check BEFORE the credential is evaluated.
    Without a named agent every real send fails at a layer that never looked
    at the token."""
    opener, seen = _capture()
    t = T.HttpTransport("https://x.test/submit", opener=opener)
    t.send(msg(), T.AccessCredential("id.access", "secret"))
    assert "user-agent" in seen["headers"]
    assert "urllib" not in seen["headers"]["user-agent"].lower()


def test_the_transport_refuses_more_than_one_recipient():
    """ONE RECIPIENT PER SUBMISSION -- the endpoint's contract, and the better
    shape besides: it makes each disposition a direct observation rather than a
    decomposition of a joint result.

    REFUSES rather than joining. Comma-joining is the obvious reading of "to
    must be a non-empty string" and it was never measured, and a transport that
    quietly does the unmeasured thing when handed more than it can carry is how
    an untested path survives in a live system.
    """
    opener, seen = _capture()
    t = T.HttpTransport("https://x.test/submit", opener=opener)
    many = Message(sender="alpha@ours.test",
                   to=["one@example.org", "two@example.org"],
                   subject="s", body="b")
    with pytest.raises(T.TransportError, match="ONE recipient"):
        t.send(many, CRED)
    assert not seen, "the transport reached the network with an ambiguous recipient"


def test_an_explicit_recipient_is_what_gets_sent():
    """The paired positive. A refusal-only pair passes on a transport that
    refuses everything, and the caller's per-recipient loop is the thing that
    has to work."""
    opener, seen = _capture()
    t = T.HttpTransport("https://x.test/submit", opener=opener)
    many = Message(sender="alpha@ours.test",
                   to=["one@example.org", "two@example.org"],
                   subject="s", body="b")
    t.send(many, CRED, recipient="two@example.org")
    assert seen["payload"]["to"] == "two@example.org"


def test_the_recipient_is_a_string_not_a_list():
    """Measured: the endpoint requires all four fields to be non-empty STRINGS
    and answers a JSON array with MISSING_FIELD/`to`. Both sides read the
    schema, agreed it matched, and were wrong; the running endpoint said so."""
    opener, seen = _capture()
    t = T.HttpTransport("https://x.test/submit", opener=opener)
    t.send(msg(), T.AccessCredential("id.access", "secret"))
    assert isinstance(seen["payload"]["to"], str)


def test_a_1010_refusal_does_not_blame_the_credential():
    """The WAF and the access layer both answer 403 and mean different things.
    Reporting an integrity-check refusal as a custody failure points whoever is
    on call at a credential that is correct, present, and was never examined."""
    with pytest.raises(T.TransportError) as e:
        T.HttpTransport._classify(403, "error code: 1010")
    assert "1010" in str(e.value)
    assert "never examined" in str(e.value)

    # PAIRED: a real Access refusal must STILL blame the credential, or the
    # fix above has simply moved the misattribution one case over.
    with pytest.raises(T.TransportError) as e2:
        T.HttpTransport._classify(403, "<title>Error ・ Cloudflare Access</title>")
    assert "credential" in str(e2.value)
