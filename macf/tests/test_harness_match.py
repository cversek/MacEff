"""Matching a name to an agent, and saying when it names several (roadmap Phase 2).

Tiers, the first with any hit deciding: exact card, identifier or uuid; exact moniker
ignoring case; unique prefix of a moniker or display name. A deployment key or account
alias never wins on its own while it is also a prefix of other agents.
"""
import io

import pytest

from macf.utils.roster import (EXIT_AMBIGUOUS, EXIT_NO_MATCH, NONE, ONE, SEVERAL, RosterEntry,
                               choose, match, resolve)
from roster_seats import seats


@pytest.fixture
def four():
    return seats()


def test_lumen_lists_all_four(four):
    """PLANT: letting an exact alias win before the prefix hits are counted (``lumen`` is
    Lumen1's agents.yaml key) resolves ``lumen`` to Lumen1 alone; this test fails."""
    r = match(four, "lumen")
    assert r.kind == SEVERAL and r.tier == 3
    assert sorted(e.moniker for e in r.entries) == ["Lumen2MacEff", "Lumen3MacEff", "Lumen4MacEff",
                                                    "LumenMacEff"]


def test_an_alias_resolves_when_nothing_else_starts_with_it():
    solo = RosterEntry(card="Keeper@5e6f7a", moniker="Keeper", uuid="5e6f7a",
                       account="kwarden", display_name=None, session_kind="daemon", state="running",
                       home="/home/kwarden", aliases=("kwarden",), reasons={"display_name": "none"})
    r = match(seats() + [solo], "kwarden")
    assert r.kind == ONE and r.entry is solo


@pytest.mark.parametrize("query", ["d4e5f6", "@d4e5f6", "Lumen2MacEff@d4e5f6", "Lumen2MacEff_d4e5f6"])
def test_tier_one_exact_card_identifier_or_uuid(four, query):
    r = match(four, query)
    assert (r.kind, r.tier, r.entry.moniker) == (ONE, 1, "Lumen2MacEff")


@pytest.mark.parametrize("query", ["Lumen2MacEff", "lumen2maceff", "LUMEN2MACEFF"])
def test_tier_two_exact_moniker_ignoring_case(four, query):
    r = match(four, query)
    assert (r.kind, r.tier, r.entry.moniker) == (ONE, 2, "Lumen2MacEff")


def test_tier_two_beats_a_longer_moniker_it_is_a_prefix_of():
    """``LumenMacEff`` is exact for Lumen1 and no prefix question arises."""
    r = match(seats(), "LumenMacEff")
    assert (r.kind, r.tier, r.entry.uuid) == (ONE, 2, "a1b2c3")


@pytest.mark.parametrize("query", ["Lumen2", "lumen2", "Lumen2 Mac"])
def test_tier_three_unique_prefix_of_moniker_or_display_name(four, query):
    r = match(four, query)
    assert (r.kind, r.tier, r.entry.moniker) == (ONE, 3, "Lumen2MacEff")


def test_a_short_uuid_prefix_is_not_exact(four):
    assert match(four, "d4e").kind == NONE


def test_one_moniker_on_two_endpoints_is_several_and_the_cards_tell_them_apart():
    r = match(seats("local") + seats("dolph"), "Lumen3MacEff")
    assert r.kind == SEVERAL and {e.endpoint for e in r.entries} == {"local", "dolph"}


def test_no_match_gives_the_nearest_candidates(four):
    r = match(four, "Many2MacEf")
    assert r.kind == NONE and r.entries
    assert r.entries[0].moniker == "Lumen2MacEff"


def test_an_unreadable_home_is_never_matched():
    locked = RosterEntry(account="pa_lumen9", aliases=("pa_lumen9", "lumen9"),
                         reasons=dict.fromkeys(("card", "moniker", "uuid", "display_name",
                                                 "session_kind", "home", "state"), "unreadable"))
    assert match(seats() + [locked], "lumen9").kind == NONE


def test_several_on_a_terminal_prompts_and_a_number_picks(four):
    out, err = io.StringIO(), io.StringIO()
    entry, rc = resolve("lumen", four, interactive=True, out=out, err=err, read=lambda _p: "2")
    listed = out.getvalue()
    assert rc == 0 and entry is match(four, "lumen").entries[1]
    for e in four:
        assert e.uuid in listed                # each listed with its uuid, so the next call is exact
    assert "1)" in listed and "4)" in listed


def test_several_on_a_terminal_a_typed_name_picks_among_the_listed(four):
    entry, rc = resolve("lumen", four, interactive=True, out=io.StringIO(), err=io.StringIO(),
                        read=lambda _p: "3c4d5e")
    assert rc == 0 and entry.moniker == "Lumen4MacEff"


def test_several_on_a_terminal_enter_cancels(four):
    entry, rc = resolve("lumen", four, interactive=True, out=io.StringIO(), err=io.StringIO(),
                        read=lambda _p: "")
    assert (entry, rc) == (None, EXIT_NO_MATCH)


def test_several_not_on_a_terminal_lists_then_exits_2(four):
    out = io.StringIO()
    entry, rc = resolve("lumen", four, interactive=False, out=out, err=io.StringIO(),
                        read=lambda _p: pytest.fail("must not prompt without a terminal"))
    assert (entry, rc) == (None, EXIT_AMBIGUOUS) and rc == 2
    assert all(e.card in out.getvalue() for e in four)


def test_no_match_lists_the_nearest_then_exits_1(four):
    out, err = io.StringIO(), io.StringIO()
    entry, rc = resolve("zzz", four, interactive=True, out=out, err=err, read=lambda _p: "1")
    assert (entry, rc) == (None, EXIT_NO_MATCH) and rc == 1
    assert "zzz" in err.getvalue() and "Lumen" in out.getvalue()


def test_one_match_needs_no_prompt(four):
    entry, rc = resolve("a1b2c3", four, interactive=True, out=io.StringIO(), err=io.StringIO(),
                        read=lambda _p: pytest.fail("one match must not prompt"))
    assert rc == 0 and entry.moniker == "LumenMacEff"


def test_the_roster_built_from_homes_resolves_the_same_way(tmp_path):
    """End to end over the fixture homes: aliases come from agents.yaml and the accounts."""
    from roster_seats import peer_roster
    entries = peer_roster(tmp_path).entries
    assert match(entries, "lumen").kind == SEVERAL and len(match(entries, "lumen").entries) == 4
    assert match(entries, "pa_lumen3").entry.moniker == "Lumen3MacEff"
    assert match(entries, "0a1b2c").entry.moniker == "Lumen3MacEff"
