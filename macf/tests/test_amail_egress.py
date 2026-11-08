"""MIS-0004 R33 on macOS: an owner-matched pf allow-list for the mail ports, rendered without root.

pf's ``user`` matches the socket's owner, so the rule holds on any network the host joins. It is an
allow-list: the broker's account and the human accounts the operator declares may open the mail
ports, and every other account is blocked. Loading it is the operator's root step; the effect probe
reports enforced, not enforced, or unknown, and never claims more than it could read.
"""
import pytest

from macf.amail import egress as eg


def test_rule_allows_only_declared_accounts():
    rules = eg.render_pf_anchor("_amail_broker", ["alice"])
    lines = [l for l in rules.splitlines() if l and not l.startswith("#")]
    passes = [l for l in lines if l.startswith("pass out quick")]
    assert {l.split(" user ")[1] for l in passes} == {"_amail_broker", "alice"}
    assert lines[-1].startswith("block return out quick"), "the block comes after every pass"
    assert all("port { 25 465 587 993 }" in l for l in passes + lines[-1:])
    # Owner matching, never a destination list: the rule holds on any network.
    assert "to any" in lines[-1]


@pytest.mark.parametrize("bad", ["", "a b", "root;pass", "x" * 40])
def test_an_account_that_is_not_a_plain_name_is_refused(bad):
    with pytest.raises(ValueError):
        eg.render_pf_anchor(bad, [])


def test_the_anchor_lives_under_the_default_ruleset_hook():
    assert eg.ANCHOR.startswith("com.apple/"), "macOS's pf.conf loads com.apple/* without editing it"


def test_install_steps_load_test_and_flush_in_one_step():
    steps = eg.install_steps("/etc/maceff/amail-egress.pf")
    assert "pfctl -a " + eg.ANCHOR + " -f /etc/maceff/amail-egress.pf" in steps
    assert "pfctl -E" in steps and "-F all" in eg.uninstall_steps()


@pytest.mark.parametrize("info, rules, expected", [
    ("Status: Enabled for 0 days", "block return out quick proto tcp", "enforced"),
    ("Status: Disabled", "block return out quick proto tcp", "not enforced"),
    ("Status: Enabled for 0 days", "", "not enforced"),
    (None, None, "unknown"),
])
def test_the_effect_probe_never_claims_more_than_it_read(info, rules, expected):
    def run(args):
        if info is None:
            raise PermissionError("pfctl needs root")
        return info if "info" in args else rules
    state = eg.probe(run)
    assert state["state"] == expected and "at" in state
