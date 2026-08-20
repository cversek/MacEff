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
            T.NullTransport().send(msg(), "token")

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
        cred.write_text("first-token\n")
        assert T.read_credential(cred) == "first-token"
        cred.write_text("rotated-token\n")
        assert T.read_credential(cred) == "rotated-token"

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
                            opener=opener_returning(200)).send(msg(), "")


class TestTheStatusMapping:
    """The 4xx/5xx split IS the point: a 5xx is the far side saying "not now",
    a 4xx is it saying "not this message". Collapsing them makes a caller retry
    a permanent rejection forever."""

    @pytest.mark.parametrize("code,state", [
        (200, T.SENT), (202, T.SENT),
        (500, T.DEFERRED), (503, T.DEFERRED), (429, T.DEFERRED), (408, T.DEFERRED),
        (400, T.BOUNCED), (403, T.BOUNCED), (422, T.BOUNCED),
    ])
    def test_status_maps_to_a_disposition(self, code, state):
        tr = T.HttpTransport("https://x.test/send", opener=opener_returning(code))
        assert tr.send(msg(), "token").state == state

    def test_unreachable_is_not_a_bounce(self):
        """A bounce is a decision somebody made about this message. Nobody made
        one, so it must not be recorded as though somebody had."""
        def refuses(req, timeout=None):
            raise OSError("connection refused")
        with pytest.raises(T.TransportError, match="unreachable"):
            T.HttpTransport("https://x.test/send", opener=refuses).send(msg(), "t")

    def test_a_transport_cannot_invent_its_own_vocabulary(self):
        """Two transports disagreeing about what an outcome means is how two
        components compute different balances from identical traffic."""
        with pytest.raises(ValueError, match="not a disposition"):
            T.TransportResult("sent-ish")

    def test_remote_text_is_truncated_before_it_enters_our_record(self):
        tr = T.HttpTransport("https://x.test/send",
                             opener=opener_returning(400, b"X" * 5000))
        assert len(tr.send(msg(), "token").detail) < 300


class TestTheBrokerCarriesTheStateIntoTheLedger:
    @pytest.fixture
    def wired(self, tmp_path):
        from macf.amail.broker import Broker, BrokerConfig
        contacts = tmp_path / "c.json"
        contacts.write_text(json.dumps({"alpha": ["them@example.org"]}))
        cred = tmp_path / "cred"
        cred.write_text("token")
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

    def test_an_accepted_send_IS_recorded_as_delivered(self, wired):
        """The paired green: without it, the test above passes on a broker that
        records everything as deferred."""
        from macf.amail.client import sent_disposition, derive_message_state
        b, cfg = wired
        cfg.transport = T.HttpTransport("https://x.test/send",
                                        opener=opener_returning(200))
        result = b.submit("alpha", msg())
        rec = sent_disposition(cfg.dispositions_dir, result["message_id"])
        assert derive_message_state(rec) == "delivered"

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
        assert req.get_header("Authorization") == "Bearer token"
        assert b"token" not in req.data, "the credential must not ride in the body"

    def test_a_refused_destination_never_reaches_the_transport(self, wired):
        """Authorization precedes the credential. The transport must not even
        be constructed into the path for a message that was refused."""
        reached = []
        class Tripwire:
            def send(self, m, c):
                reached.append(m)
                return T.TransportResult(T.SENT)
        b, cfg = wired
        cfg.transport = Tripwire()
        b.submit("alpha", Message(sender="alpha@ours.test",
                                  to=["stranger@nowhere.test"], subject="s", body="b"))
        assert reached == [], "a refused destination reached the transport"
