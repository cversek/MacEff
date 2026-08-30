"""Local delivery obeys a DIRECTED EDGE, and a refusal outranks an implication.

`A --outbound--> B` asserts two things in ONE direction: A may send to B, and B
may receive from A. B->A is not implied and needs its own edge.

The implication is sound only because both endpoints are accounts the
deployment defines — it can speak for both. For an internet address there is
nobody to imply anything about, so the rule is local-only.

Before this, local handoff consulted ONLY the sender's outbound permission. The
contact book answered `is_revoked=True` and `permits(inbound)=False` for a
withdrawn correspondent while the message was delivered and read: the data was
right and the query was never made.
"""
import pytest

from macf.amail.broker import Broker


class _Contacts:
    """Answers exactly what the book answers, from a declared edge set."""

    def __init__(self, edges):
        # edges: {(agent, address): direction}
        self.edges = edges

    def declared_direction(self, agent, address):
        return self.edges.get((agent, address))

    def is_revoked(self, agent, address):
        return self.edges.get((agent, address)) == "neither"

    def permits(self, agent, address, *, direction):
        d = self.edges.get((agent, address))
        if d is None or d == "neither":
            return False
        return d == "both" or d == direction


class _Config:
    def __init__(self, addresses):
        self.addresses = addresses          # agent -> address

    def agent_for(self, address):
        for a, addr in self.addresses.items():
            if addr == address:
                return a
        return None

    def address_for(self, agent):
        return self.addresses[agent]


A_ADDR, B_ADDR = "a@x.test", "b@x.test"
OUTSIDE = "stranger@elsewhere.test"


def _broker(edges):
    b = Broker.__new__(Broker)
    b.contacts = _Contacts(edges)
    b.config = _Config({"a": A_ADDR, "b": B_ADDR})
    return b


class TestTheEdgeImpliesTheReceivingHalf:
    def test_an_outbound_edge_lets_the_recipient_receive(self):
        """A declares outbound to B and B declares nothing. B receives,
        because the edge asserted that half too."""
        b = _broker({("a", B_ADDR): "outbound"})
        assert b._local_acceptance_refusal("b", A_ADDR) == ""

    def test_both_also_implies_it(self):
        b = _broker({("a", B_ADDR): "both"})
        assert b._local_acceptance_refusal("b", A_ADDR) == ""

    def test_an_explicit_inbound_declaration_works_without_any_implication(self):
        """The recipient may declare it directly; the implication is an
        additional route, not the only one."""
        b = _broker({("b", A_ADDR): "inbound"})
        assert b._local_acceptance_refusal("b", A_ADDR) == ""


class TestTheReverseIsNotImplied:
    def test_a_forward_edge_does_not_let_the_recipient_send_back(self):
        """THE DIRECTED HALF. `A --outbound--> B` says nothing about B->A."""
        b = _broker({("a", B_ADDR): "outbound"})
        refusal = b._local_acceptance_refusal("a", B_ADDR)
        assert refusal and "does not accept mail from" in refusal

    def test_the_reverse_works_once_its_own_edge_exists(self):
        b = _broker({("a", B_ADDR): "outbound", ("b", A_ADDR): "outbound"})
        assert b._local_acceptance_refusal("a", B_ADDR) == ""
        assert b._local_acceptance_refusal("b", A_ADDR) == ""


class TestAnExplicitRefusalOutranksTheImplication:
    def test_neither_beats_the_senders_outbound_edge(self):
        """THE ONE THAT WAS BROKEN. The recipient withdrew the correspondent;
        the sender still declares an edge. The withdrawal must win, or a
        correspondent restores its own access by editing its own half — the
        one thing an allowlist exists to prevent."""
        b = _broker({("a", B_ADDR): "outbound", ("b", A_ADDR): "neither"})
        refusal = b._local_acceptance_refusal("b", A_ADDR)
        assert "WITHDRAWN" in refusal
        assert "outranks" in refusal

    def test_neither_beats_an_explicit_inbound_on_the_same_pair(self):
        """A contradictory file must fail closed rather than pick the
        permissive reading."""
        b = _broker({("b", A_ADDR): "neither", ("a", B_ADDR): "both"})
        assert "WITHDRAWN" in b._local_acceptance_refusal("b", A_ADDR)


class TestTheImplicationIsLocalOnly:
    def test_an_outside_sender_gets_no_implication(self):
        """There is nobody to imply anything about: the deployment does not
        define that account and cannot speak for it. The recipient must
        declare inbound itself."""
        b = _broker({})
        refusal = b._local_acceptance_refusal("b", OUTSIDE)
        assert refusal and "does not accept mail from" in refusal

    def test_an_outside_sender_is_accepted_only_by_explicit_declaration(self):
        b = _broker({("b", OUTSIDE): "inbound"})
        assert b._local_acceptance_refusal("b", OUTSIDE) == ""


class TestItFailsClosed:
    def test_no_contact_list_refuses_every_local_delivery(self):
        b = _broker({})
        b.contacts = None
        assert "refusing every local delivery" in b._local_acceptance_refusal("b", A_ADDR)

    def test_an_undeclared_pair_is_refused(self):
        b = _broker({})
        assert b._local_acceptance_refusal("b", A_ADDR) != ""


class TestAgainstTheRealContactBook:
    """The classes above assert the BROKER's logic against a stub of the book.

    That proves the rule and not the wiring: a stub agrees with whatever the
    test author believed the parser does. These run the same three arms through
    the real `ContactBook`, parsing a real addressing file, so a divergence
    between the parser's answer and the broker's expectation of it fails here
    rather than in a deployment.
    """

    def _broker_with_real_book(self, tmp_path, flat, domain="agents.test"):
        from conftest import _addressing
        from macf.amail.contacts import ContactBook
        p = tmp_path / "addressing.yaml"
        p.write_text(_addressing(flat, domain=domain))
        b = Broker.__new__(Broker)
        b.contacts = ContactBook(p)
        b.config = _Config({"alpha": f"alpha@{domain}", "beta": f"beta@{domain}"})
        return b

    def test_the_edge_implies_the_receiving_half(self, tmp_path):
        b = self._broker_with_real_book(tmp_path, {
            "alpha": [{"address": "beta@agents.test", "direction": "outbound"}],
            "beta": [],
        })
        assert b._local_acceptance_refusal("beta", "alpha@agents.test") == ""

    def test_the_reverse_is_not_implied(self, tmp_path):
        b = self._broker_with_real_book(tmp_path, {
            "alpha": [{"address": "beta@agents.test", "direction": "outbound"}],
            "beta": [],
        })
        assert b._local_acceptance_refusal("alpha", "beta@agents.test") != ""

    def test_an_explicit_refusal_outranks_the_implication(self, tmp_path):
        """THE ONE THAT WAS BROKEN IN PRODUCTION, through the real parser."""
        b = self._broker_with_real_book(tmp_path, {
            "alpha": [{"address": "beta@agents.test", "direction": "outbound"}],
            "beta": [{"address": "alpha@agents.test", "direction": "neither"}],
        })
        refusal = b._local_acceptance_refusal("beta", "alpha@agents.test")
        assert "WITHDRAWN" in refusal and "outranks" in refusal

    def test_a_differently_cased_address_is_still_the_same_edge(self, tmp_path):
        """Addresses are case-insensitive, so an edge declared in one casing
        must not be a different edge from the same one written in another —
        the normalisation and the implication have to agree."""
        b = self._broker_with_real_book(tmp_path, {
            "alpha": [{"address": "BETA@Agents.Test", "direction": "outbound"}],
            "beta": [],
        })
        assert b._local_acceptance_refusal("beta", "alpha@agents.test") == ""
