"""Contact direction, and the controls that make its rules fail rather than drift.

Every test here pins a rule that would otherwise rest on someone remembering it.
The rules are cheap to state and each has been violated in this codebase by the
person who wrote it, so they are encoded as controls that run.
"""
import pytest
import yaml

from conftest import _addressing
from macf.amail.contacts import (ContactBook, ContactListError, ParsedContacts,
                                 normalise_address)


def _book(tmp_path, flat):
    p = tmp_path / "addressing.yaml"
    p.write_text(_addressing(flat))
    return ContactBook(p)


class TestDirectionIsRequired:
    """An authorisation field must not have a default, permissive or otherwise."""

    def test_an_entry_without_a_direction_is_refused(self, tmp_path):
        """The migration cost IS the control. An entry that does not say which
        way it authorises correspondence is not a policy, and admitting it would
        mean inventing an authority nobody granted."""
        p = tmp_path / "addressing.yaml"
        p.write_text(yaml.safe_dump({
            "domain": "agents.test",
            "agents": {"alpha": {"uid": 9000, "home": "/home/alpha",
                                 "contacts": [{"address": "x@y.test"}]}},
        }))
        with pytest.raises(ContactListError):
            ContactBook(p).contacts_for("alpha", direction="outbound")

    def test_a_bare_address_is_refused_and_says_what_to_write_instead(self, tmp_path):
        """The string shorthand cannot state a direction, so it cannot survive.
        The message names the fix: a generic 'invalid entry' would leave the
        deployer guessing at a shape."""
        p = tmp_path / "addressing.yaml"
        p.write_text(yaml.safe_dump({
            "domain": "agents.test",
            "agents": {"alpha": {"uid": 9000, "home": "/home/alpha",
                                 "contacts": ["bare@y.test"]}},
        }))
        with pytest.raises(ContactListError, match="bare address"):
            ContactBook(p).contacts_for("alpha", direction="outbound")

    @pytest.mark.parametrize("bad", ["in", "out", "BOTH", "any", "", None])
    def test_an_unrecognised_direction_is_refused(self, tmp_path, bad):
        """Refusing the near-misses is the point: 'out' and 'BOTH' are what a
        deployer actually types, and silently ignoring them would grant or deny
        authority by typo."""
        book = _book(tmp_path, {"alpha": [{"address": "x@y.test", "direction": bad}]})
        with pytest.raises(ContactListError):
            book.contacts_for("alpha", direction="outbound")


class TestDirectionSeparatesTwoQuestions:
    """permits() was UNDIRECTED — one membership test answering two questions."""

    @pytest.mark.parametrize("declared,out_ok,in_ok", [
        ("outbound", True, False),
        ("inbound", False, True),
        ("both", True, True),
        ("neither", False, False),
    ])
    def test_each_direction_authorises_exactly_its_own_way(
            self, tmp_path, declared, out_ok, in_ok):
        """BOTH POLARITIES for every value. A test that only checked the
        permitted cases would pass against a book that permits everything, and
        one that only checked refusals would pass against a book that permits
        nothing."""
        book = _book(tmp_path, {
            "alpha": [{"address": "x@y.test", "direction": declared}]})
        assert ("x@y.test" in book.contacts_for("alpha", direction="outbound")) is out_ok
        assert ("x@y.test" in book.contacts_for("alpha", direction="inbound")) is in_ok

    def test_the_caller_must_say_which_question_it_is_asking(self, tmp_path):
        """No default direction at the call site either — the undirected form is
        what let one list answer two questions."""
        book = _book(tmp_path, {"alpha": [{"address": "x@y.test", "direction": "both"}]})
        with pytest.raises(TypeError):
            book.contacts_for("alpha")


class TestRevocationIsRecordedNotDeleted:
    """`neither` is the reason this is four-valued rather than two booleans."""

    def test_a_withdrawn_contact_is_distinguishable_from_an_absent_one(self, tmp_path):
        """The whole value of the fourth state. Both are refused; only one is a
        SIGNAL, and collapsing them discards the signal before any caller can
        act on it."""
        book = _book(tmp_path, {
            "alpha": [{"address": "gone@y.test", "direction": "neither"}]})
        assert book.is_revoked("alpha", "gone@y.test") is True
        assert book.declared_direction("alpha", "gone@y.test") == "neither"

        assert book.is_revoked("alpha", "never@y.test") is False
        assert book.declared_direction("alpha", "never@y.test") is None

    def test_revocation_survives_a_differently_cased_address(self, tmp_path):
        """*** THE FAIL-OPEN CASE, PINNED. ***

        A lookup miss is not neutral: it inherits the polarity of its CONSUMER.
        A miss makes `permits` refuse (fail-closed, merely wrong) and makes
        `is_revoked` answer False — which retires the alert on precisely the
        correspondent the deployment withdrew, while authorisation keeps working
        and nobody investigates.

        So a normalisation drift between the parse side and the lookup side
        would silently disable the compromise detector. This is the test that
        fails if those two ever stop agreeing.
        """
        book = _book(tmp_path, {
            "alpha": [{"address": "Gone@Y.test", "direction": "neither"}]})
        for spelling in ("gone@y.test", "GONE@Y.TEST", "  Gone@Y.test  "):
            assert book.is_revoked("alpha", spelling) is True, spelling

    def test_a_revoked_contact_is_refused_in_both_directions(self, tmp_path):
        book = _book(tmp_path, {
            "alpha": [{"address": "gone@y.test", "direction": "neither"}]})
        assert book.contacts_for("alpha", direction="outbound") == []
        assert book.contacts_for("alpha", direction="inbound") == []


class TestNormalisationHasOneSource:
    """Parse side and lookup side must agree, and disagreement returns a VALUE."""

    @pytest.mark.parametrize("written,looked_up", [
        ("Peer@Example.test", "peer@example.test"),
        ("peer@example.test", "PEER@EXAMPLE.TEST"),
        ("  peer@example.test  ", "peer@example.test"),
        ("PeEr@ExAmPlE.TeSt", "  peer@EXAMPLE.test  "),
    ])
    def test_every_accessor_agrees_across_spellings(self, tmp_path, written, looked_up):
        """Adversarial spellings against EVERY accessor at once.

        Each of these reconstructs a (agent, address) key that the parse side
        built. If any one of them normalises differently the dict simply reports
        no such key — a well-formed answer to a question nobody meant to ask,
        with nothing raised anywhere.
        """
        book = _book(tmp_path, {"alpha": [{
            "address": written, "direction": "both", "push": True,
            "key": "ed25519:3QEofL6wmew5FQL0Gtmd8yRDRrtKZkOQIWs3+uQ0mEY="}]})
        assert book.declared_direction("alpha", looked_up) == "both"
        assert book.push_granted("alpha", looked_up) is True
        assert looked_up.strip().lower() in book.contacts_for("alpha", direction="outbound")

    def test_the_normaliser_is_total(self):
        """None and empty are addresses too, as far as a lookup is concerned —
        an accessor handed None must not raise where its siblings return a
        miss."""
        assert normalise_address(None) == ""
        assert normalise_address("  ") == ""
        assert normalise_address("A@B") == "a@b"


class TestParsedContactsCannotBeBuiltPositionally:
    """Tier-1 enforcement: the violation is not discouraged, it is unspeakable."""

    def test_positional_construction_raises(self):
        """Without kw_only this class is a tuple wearing field names: positional
        construction would still run, dataclasses do not check types at runtime,
        and two same-shaped fields could be swapped at the one site that builds
        it — leaving every reader downstream confidently wrong.

        Enforcing names on ACCESS while merely expressing them on CONSTRUCTION
        leaves the hole open at the only place it can be introduced.
        """
        with pytest.raises(TypeError):
            ParsedContacts({}, {}, {}, {})

    def test_keyword_construction_is_the_supported_form(self):
        """Negative control: the refusal above must be about POSITION, not about
        the class being unconstructible."""
        p = ParsedContacts(by_agent={}, keys={}, push={}, direction={})
        assert p.by_agent == {}
        assert p.direction_for("alpha", "x@y.test") is None
