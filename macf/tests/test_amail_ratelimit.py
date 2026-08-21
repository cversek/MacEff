"""Outbound rate limiting, per-agent contacts authority, and binding enumeration.

BOTH POLARITIES. Every refusal here has its paired acceptance, because all of
them are refusal-shaped and a refusal-shaped test passes when its instrument is
dead.

Time is INJECTED, never slept. A test that sleeps to cross a window is slow and
flaky, and flaky tests get disabled -- which removes the control rather than
the flake.
"""
from conftest import _addressing

import json

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail.ratelimit import (RateLimit, RateLimiter, RateLimitError,
                                  BROKER_PRINCIPAL)


def limiter(tmp_path, cap=3, window=60, principal="alpha"):
    return RateLimiter(tmp_path / "rl", {principal: RateLimit(cap, window)})


class TestTheBudget:
    def test_sends_are_permitted_up_to_the_cap(self, tmp_path):
        rl = limiter(tmp_path, cap=3)
        assert [rl.check_and_consume("alpha", now=100.0) for _ in range(3)] == [None] * 3

    def test_the_next_send_is_refused(self, tmp_path):
        rl = limiter(tmp_path, cap=3)
        for _ in range(3):
            rl.check_and_consume("alpha", now=100.0)
        refusal = rl.check_and_consume("alpha", now=100.0)
        assert refusal is not None and "rate limit reached" in refusal

    def test_the_window_SLIDES_rather_than_resetting(self, tmp_path):
        """A fixed window lets a sender spend the whole budget at the end of one
        window and the whole budget at the start of the next -- twice the rate,
        at the moment a burst does the most reputational damage."""
        rl = limiter(tmp_path, cap=2, window=60)
        rl.check_and_consume("alpha", now=100.0)
        rl.check_and_consume("alpha", now=150.0)
        # Still inside the window for both: refused.
        assert rl.check_and_consume("alpha", now=155.0) is not None
        # The first has aged out; exactly one slot frees, not the whole budget.
        assert rl.check_and_consume("alpha", now=161.0) is None
        assert rl.check_and_consume("alpha", now=161.0) is not None

    def test_an_undeclared_principal_is_unlimited_and_that_is_the_callers_problem(self, tmp_path):
        rl = limiter(tmp_path)
        assert rl.check_and_consume("nobody", now=100.0) is None

    def test_a_zero_budget_is_refused_at_construction(self):
        """A cap of zero refuses everything and a window of zero expires
        instantly. Neither is a budget, and accepting either would produce a
        limiter that looks configured and enforces nonsense."""
        with pytest.raises(ValueError):
            RateLimit(0, 60)
        with pytest.raises(ValueError):
            RateLimit(5, 0)


class TestItFailsClosed:
    def test_unreadable_state_refuses_rather_than_assuming_zero(self, tmp_path):
        """An unreadable budget is not an empty budget. Treating it as one
        hands unlimited sending to whoever can corrupt a file the broker
        reads -- the house rule the push backstop already states."""
        rl = limiter(tmp_path)
        rl.check_and_consume("alpha", now=100.0)
        (tmp_path / "rl" / "alpha.json").write_text("{ not json")
        with pytest.raises(RateLimitError):
            rl.check_and_consume("alpha", now=100.0)

    def test_malformed_stamps_refuse(self, tmp_path):
        rl = limiter(tmp_path)
        rl.check_and_consume("alpha", now=100.0)
        (tmp_path / "rl" / "alpha.json").write_text(
            json.dumps({"principal": "alpha", "stamps": ["not-a-number"]}))
        with pytest.raises(RateLimitError):
            rl.check_and_consume("alpha", now=100.0)

    def test_a_first_send_is_not_an_error(self, tmp_path):
        """The paired green: no state file yet is EXPECTED, not a failure, or
        the two rules above would refuse every deployment's first message."""
        assert limiter(tmp_path).check_and_consume("alpha", now=100.0) is None


class TestItSurvivesARestart:
    def test_consumption_is_on_disk_not_in_memory(self, tmp_path):
        """A budget held in memory resets when the broker restarts, which turns
        'restart the broker' into a way to spend the budget twice."""
        first = limiter(tmp_path, cap=2)
        first.check_and_consume("alpha", now=100.0)
        first.check_and_consume("alpha", now=100.0)
        # A brand-new limiter object over the same directory: the restart.
        second = limiter(tmp_path, cap=2)
        assert second.check_and_consume("alpha", now=100.0) is not None


class TestItIsObservable:
    def test_the_agent_can_see_window_cap_and_consumption(self, tmp_path):
        """amail spec O5b.6b "the-rate-limit-must-be-observable-to-the-sending-agent".
        The threat case is GOOD FAITH, and a control aimed at good faith that
        good faith cannot see is discoverable only by tripping it."""
        rl = limiter(tmp_path, cap=5, window=60)
        rl.check_and_consume("alpha", now=100.0)
        rl.check_and_consume("alpha", now=100.0)
        b = rl.budget("alpha", now=100.0)
        assert b == {"principal": "alpha", "limited": True, "window_seconds": 60,
                     "max_per_window": 5, "used": 2, "remaining": 3}

    def test_the_state_file_is_agent_readable_and_not_agent_writable(self, tmp_path):
        import stat as _stat
        rl = limiter(tmp_path)
        rl.check_and_consume("alpha", now=100.0)
        mode = (tmp_path / "rl" / "alpha.json").stat().st_mode
        assert mode & _stat.S_IROTH, "a sender must be able to see its own consumption"
        assert not (mode & _stat.S_IWOTH), "and must not be able to forge it"

    def test_asking_about_a_broken_budget_reports_the_error_not_zero(self, tmp_path):
        """Reporting is not enforcing. A caller ASKING must not be told it has
        used nothing when the truth is unknown."""
        rl = limiter(tmp_path)
        rl.check_and_consume("alpha", now=100.0)
        (tmp_path / "rl" / "alpha.json").write_text("{ not json")
        b = rl.budget("alpha", now=100.0)
        assert b["used"] is None and "error" in b


class TestTheBrokerEnforcesIt:
    @pytest.fixture
    def deployment(self, tmp_path):
        from macf.amail.broker import Broker, BrokerConfig
        from macf.amail.models import Message
        peer_home = tmp_path / "peer"
        (peer_home / "Maildir").mkdir(parents=True)
        contacts = tmp_path / "contacts.json"
        contacts.write_text(_addressing({"alpha": ["peer@agents.test"],
                                        "beta": ["other@example.org"]}))
        cfg = BrokerConfig(
            domain="agents.test", contacts_path=contacts,
            dispositions_dir=tmp_path / "disp",
            inbound_handoff=tmp_path / "handoff",
            agent_homes={"alpha": tmp_path / "alpha", "peer": peer_home},
            rate_limiter=RateLimiter(tmp_path / "rl",
                                     {"alpha": RateLimit(2, 3600)}))
        return {"broker": Broker(cfg), "cfg": cfg,
                "msg": lambda: Message(sender="alpha@agents.test",
                                       to=["peer@agents.test"],
                                       subject="s", body="b")}

    def test_the_cap_is_enforced_on_the_real_submission_path(self, deployment):
        b, msg = deployment["broker"], deployment["msg"]
        assert b.submit("alpha", msg())["ok"] is True
        assert b.submit("alpha", msg())["ok"] is True
        third = b.submit("alpha", msg())
        assert third["ok"] is False
        assert any("rate limit" in r for r in third["refused"])

    def test_a_rate_refusal_is_a_TERMINAL_fate_distinguishable_from_a_deny(self, deployment):
        """amail spec O5b.6: the refusal must be recorded as a RATE refusal,
        distinguishable in the record from an authorization DENY and from a
        transport failure. Three different facts, and a caller that conflates
        them retries one of them forever."""
        from macf.amail.client import sent_disposition, derive_message_state
        b, msg = deployment["broker"], deployment["msg"]
        for _ in range(2):
            b.submit("alpha", msg())
        refused = b.submit("alpha", msg())
        rec = sent_disposition(deployment["cfg"].dispositions_dir,
                               refused["message_id"])
        assert derive_message_state(rec) == "rate-refused"

    def test_a_denied_destination_does_not_spend_budget(self, deployment):
        """The limit sits AFTER the contacts check on purpose: a refused
        destination must not consume budget the agent is entitled to."""
        from macf.amail.models import Message
        b = deployment["broker"]
        b.submit("alpha", Message(sender="alpha@agents.test",
                                  to=["stranger@example.org"], subject="s", body="b"))
        assert deployment["broker"].rate_budget("alpha")["used"] == 0

    def test_an_absent_limiter_is_announced_on_every_send(self, deployment, capsys):
        deployment["cfg"].rate_limiter = None
        assert deployment["broker"].submit("alpha", deployment["msg"]())["ok"] is True
        assert "UNBOUNDED budget" in capsys.readouterr().err

    def test_a_limiter_that_cannot_answer_refuses(self, deployment):
        class Broken:
            def check_and_consume(self, principal, now=None):
                raise RateLimitError("state unreadable")
        deployment["cfg"].rate_limiter = Broken()
        result = deployment["broker"].submit("alpha", deployment["msg"]())
        assert result["ok"] is False
        assert any("budget could not be determined" in r for r in result["refused"])


class TestContactsAuthorityIsPerAgent:
    """amail spec O5b.1a "contacts-authority-is-per-agent".

    THE IMPLEMENTATION WAS ALREADY CORRECT; the SPEC and POLICY wording was
    the defect ("the same contacts file" vs "your contact list" describe
    different systems). So this phase owes a CONTROL rather than a change --
    and the control must be the SECURITY half, because a test showing an agent
    can write to its OWN contacts passes on an implementation that shares the
    whole file.
    """

    def test_an_agent_cannot_reach_another_agents_contact(self, tmp_path):
        from macf.amail.contacts import ContactBook
        p = tmp_path / "addressing.yaml"
        p.write_text(_addressing({"alpha": ["friend-of-alpha@example.org"],
                                  "beta": ["friend-of-beta@example.org"]}))
        book = ContactBook(p)
        # THE SECURITY HALF: beta's correspondent is not alpha's to write to.
        assert book.permits("alpha", "friend-of-beta@example.org") is False
        # THE PAIRED FUNCTIONAL HALF, which alone would prove nothing.
        assert book.permits("alpha", "friend-of-alpha@example.org") is True

    def test_keys_do_not_merge_across_agents(self, tmp_path):
        """Two agents may know the same correspondent under different keys, and
        merging them would let one agent's contact list decide what another
        agent is willing to believe."""
        from macf.amail.contacts import ContactBook
        from macf.amail.crypto import generate_keypair
        # Real key material: the contact book PARSES keys at load, deliberately,
        # so a deployment learns its config is wrong when it writes it rather
        # than mid-way through a security decision. Placeholder strings are
        # rejected there, which is the check working.
        key_a = generate_keypair(tmp_path / "a.key")
        key_b = generate_keypair(tmp_path / "b.key")
        assert key_a != key_b
        p = tmp_path / "addressing.yaml"
        p.write_text(_addressing({
            "alpha": [{"address": "shared@example.org", "keys": [key_a]}],
            "beta": [{"address": "shared@example.org", "keys": [key_b]}],
        }))
        book = ContactBook(p)
        assert book.keys_for("alpha", "shared@example.org") == [key_a]
        assert book.keys_for("beta", "shared@example.org") == [key_b]


def test_the_broker_status_op_carries_the_budget_to_the_agent(tmp_path):
    """amail spec O5b.6b "the-rate-limit-must-be-observable-to-the-sending-agent",
    THE ARM THAT WAS MISSING.

    The clause requires the budget to be readable THROUGH THE CLIENT'S STATUS
    SURFACE. The controls that existed showed the limiter could COMPUTE a
    budget and that its state file was agent-readable — both true, neither the
    property. Nothing carried it to the agent, so the status surface printed no
    budget at all and the one control aimed at good faith stayed discoverable
    only by tripping it. That is the easier-adjacent-property drift, in a row
    already marked as holding.
    """
    import json as _json
    from macf.amail.broker import Broker, BrokerConfig

    contacts = tmp_path / "contacts.json"
    contacts.write_text(_json.dumps({"alpha": ["peer@agents.test"]}))
    (tmp_path / "alpha" / "Maildir").mkdir(parents=True)
    rl = limiter(tmp_path, cap=5, window=60)
    b = Broker(BrokerConfig(
        domain="agents.test", contacts_path=contacts,
        inbound_handoff=tmp_path / "handoff",
        agent_homes={"alpha": tmp_path / "alpha"}, rate_limiter=rl))

    rl.check_and_consume("alpha")
    resp = b.status_counts("alpha")
    assert resp["ok"]
    assert resp["budget"]["max_per_window"] == 5
    assert resp["budget"]["used"] == 1
    assert resp["budget"]["remaining"] == 4


def test_a_deployment_with_no_limiter_reports_no_budget_rather_than_zero(tmp_path):
    """The paired negative. `no limit configured` and `you have used none of
    your limit` are different facts, and a surface that renders both as a
    comfortable number is the silent-empty one layer up."""
    import json as _json
    from macf.amail.broker import Broker, BrokerConfig

    contacts = tmp_path / "contacts.json"
    contacts.write_text(_json.dumps({"alpha": []}))
    (tmp_path / "alpha" / "Maildir").mkdir(parents=True)
    b = Broker(BrokerConfig(
        domain="agents.test", contacts_path=contacts,
        inbound_handoff=tmp_path / "handoff",
        agent_homes={"alpha": tmp_path / "alpha"}))
    assert b.status_counts("alpha")["budget"] is None
