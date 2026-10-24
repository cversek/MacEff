"""The roster: every agent this endpoint can attach to (roadmap Phase 1, harness list).

Read only, and unknown is never empty: an unreadable home is listed with the reason, and
every field left unknown carries why.
"""
import json
import os
from pathlib import Path

import pytest

from macf.utils import roster
from macf.utils.roster import Probed, RosterEntry, local_roster
from roster_seats import SEATS, build, by_dirname, peer_roster


def test_a_peer_lists_all_four_seats_with_cards_accounts_and_display_names(tmp_path):
    r = peer_roster(tmp_path)
    assert r.complete
    cards = [e.card for e in r.entries]
    assert cards == sorted(f"{m}@{u}" for _a, _k, m, u in SEATS)
    m2 = next(e for e in r.entries if e.moniker == "Lumen2MacEff")
    assert (m2.uuid, m2.account, m2.display_name, m2.endpoint) == ("d4e5f6", "pa_lumen2", "Lumen2 MacEff", "local")
    assert m2.session_kind == "daemon"           # its published units declare a session unit
    assert "lumen2" in m2.aliases and "pa_lumen2" in m2.aliases


def test_a_peers_state_is_unknown_with_the_shared_container_reason(tmp_path):
    """persistent_layer 8: a peer's state lives with the peer's daemon; it isn't guessed."""
    r = peer_roster(tmp_path)
    for e in r.entries:
        assert e.state == "unknown"
        assert "persistent_layer 8" in e.reasons["state"]


def test_an_unreadable_home_is_listed_with_its_reason(tmp_path, monkeypatch):
    """PLANT: _agent_home_markers answering False (not an agent) on an OSError omits the
    home silently; this test fails. A fake stat stands in for chmod, which root ignores."""
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    locked = homes / "pa_locked"
    locked.mkdir()
    real_stat = os.stat

    def stat(path, *a, **kw):
        if Path(path).parent == locked or locked in Path(path).parents:
            raise PermissionError(13, "Permission denied", str(path))
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(roster.os, "stat", stat)
    r = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
                     uid=os.getuid() + 100000, account_of=by_dirname)
    found = [e for e in r.entries if e.account == "pa_locked"]
    assert len(found) == 1, "an unreadable home must be listed, never left out"
    e = found[0]
    assert e.card is None and "cannot be read" in e.reasons["card"]
    assert e.state == "unknown" and e.reasons["state"]
    assert len(r.entries) == 5


def test_a_home_without_a_summary_takes_its_card_from_agent_card(tmp_path):
    f = build(tmp_path, published=False)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    r = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
                     uid=os.getuid() + 100000, account_of=by_dirname)
    assert {e.card for e in r.entries} == {f"{m}@{u}" for _a, _k, m, u in SEATS}
    for e in r.entries:
        assert e.session_kind is None and "no published units summary" in e.reasons["session_kind"]


def test_a_plain_directory_beside_the_homes_is_not_an_agent(tmp_path):
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    (homes / "someone").mkdir()
    r = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
                     uid=os.getuid() + 100000, account_of=by_dirname)
    assert all(e.account != "someone" for e in r.entries)


def test_own_agents_are_probed_and_daemon_records_merge_with_the_home(tmp_path):
    """This account's agent: its daemon record and its home are one entry, and its state
    comes from the probe, never from the published file."""
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    (runtime / "Lumen3MacEff_0a1b2c.json").write_text('{"pid": 999999, "proc_start": "1"}')
    asked = []

    def probe(ident, has_legacy):
        asked.append((ident, has_legacy))
        if ident == "Lumen3MacEff_0a1b2c":
            return Probed(kind="daemon", state="running")
        return Probed(kind="legacy", state="stopped")

    r = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
                     uid=os.getuid(), account_of=by_dirname, probe=probe)
    m3 = [e for e in r.entries if e.moniker == "Lumen3MacEff"]
    assert len(m3) == 1
    assert (m3[0].state, m3[0].session_kind, m3[0].home) == ("running", "daemon", str(homes / "pa_lumen3"))
    assert "no longer that daemon" in m3[0].detail
    assert ("Lumen3MacEff_0a1b2c", False) in asked


def test_a_legacy_unit_is_listed_as_legacy(tmp_path):
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    (units / "cc-harness-Solo_abcdef.service").write_text("")
    (units / "cc-harness-Solo_abcdef-watch.service").write_text("")
    r = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
                     uid=os.getuid() + 100000, account_of=by_dirname,
                     probe=lambda ident, legacy: Probed(kind="legacy", state="stopped"))
    solo = [e for e in r.entries if e.card == "Solo@abcdef"]
    assert len(solo) == 1 and solo[0].session_kind == "legacy" and solo[0].state == "stopped"
    assert all("watch" not in (e.card or "") for e in r.entries)


def test_without_agents_yaml_the_display_name_says_why(tmp_path):
    f = build(tmp_path)
    r = f.roster(uid=os.getuid(), agents_yaml=tmp_path / "absent.yaml",
                 probe=lambda ident, legacy: Probed(kind="daemon", state="running"))
    assert len(r.entries) == 4
    for e in r.entries:
        assert e.display_name is None and "absent.yaml" in e.reasons["display_name"]


def test_on_a_host_other_accounts_homes_are_not_listed(tmp_path, monkeypatch):
    """A host declares no agents.yaml; its other homes are other people's logins. One that
    can't be read, and one that can, owned by another uid: neither is listed.
    PLANT: dropping the not-peers guard in _home_entry lists them; this test fails."""
    f = build(tmp_path)
    locked = f.homes / "someone_else"
    locked.mkdir()
    real_stat = os.stat

    def stat(path, *a, **kw):
        if locked in Path(path).parents:
            raise PermissionError(13, "Permission denied", str(path))
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(roster.os, "stat", stat)
    r = f.roster(agents_yaml=tmp_path / "absent.yaml")      # every home is another uid's
    assert r.entries == [] and r.complete
    # The same homes, as this account's own, are listed.
    mine = f.roster(uid=os.getuid(), agents_yaml=tmp_path / "absent.yaml",
                    probe=lambda ident, legacy: Probed(kind="daemon", state="running"))
    assert len([e for e in mine.entries if e.card]) == 4

def test_every_unknown_field_in_the_listing_carries_a_reason(tmp_path):
    f = build(tmp_path)
    homes, runtime, units = f.homes, f.runtime, f.units
    (runtime / "Ghost_123456.json").write_text("not json")
    (units / "cc-harness-slug.service").write_text("")
    own = local_roster(homes=homes, runtime=runtime, unit_dir=units, agents_yaml=tmp_path / "x.yaml",
                       uid=os.getuid(), account_of=by_dirname,
                       probe=lambda ident, legacy: Probed(kind=None, state="unknown",
                                                          reason="tmux could not be asked"))
    assert len(own.entries) == 6
    for e in own.entries:
        for f in ("card", "moniker", "uuid", "account", "display_name", "session_kind", "home"):
            if getattr(e, f) is None:
                assert e.reasons.get(f), (e.card, f)


def test_the_model_refuses_an_unknown_without_a_reason():
    with pytest.raises(ValueError, match="unknown without a reason"):
        RosterEntry(card="A@abcdef", moniker="A", uuid="abcdef", account="a", display_name="A",
                    session_kind="daemon", home="/home/a")         # state unknown, no reason


def test_an_unlistable_homes_directory_makes_the_listing_incomplete(tmp_path):
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("")
    r = local_roster(homes=not_a_dir, runtime=tmp_path / "rt", unit_dir=tmp_path / "u",
                     agents_yaml=tmp_path / "x.yaml")
    assert not r.complete and "cannot be listed" in r.problems[0]


def test_harness_list_json_prints_a_list_of_objects_with_the_fields(tmp_path, monkeypatch, capsys):
    from macf import cli
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    real = roster.local_roster
    monkeypatch.setattr(roster, "local_roster", lambda **kw: real(
        homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
        uid=os.getuid() + 100000, account_of=by_dirname))
    rc = cli.cmd_harness_list(cli._build_parser().parse_args(["harness", "list", "--json"]))
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 4
    assert set(data[0]) >= {"card", "moniker", "uuid", "account", "display_name", "session_kind",
                            "state", "endpoint", "reasons"}
    assert RosterEntry(**data[0]).card == data[0]["card"]    # round-trips for Phase 4


def test_harness_list_table_names_each_reason(tmp_path, monkeypatch, capsys):
    from macf import cli
    f = build(tmp_path)
    homes, runtime, units, agents_yaml = f.homes, f.runtime, f.units, f.agents_yaml
    real = roster.local_roster
    monkeypatch.setattr(roster, "local_roster", lambda **kw: real(
        homes=homes, runtime=runtime, unit_dir=units, agents_yaml=agents_yaml,
        uid=os.getuid() + 100000, account_of=by_dirname))
    rc = cli.cmd_harness_list(cli._build_parser().parse_args(["harness", "list", "--verbose", "--local"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split()[:5] == ["CARD", "ENDPOINT", "ACCOUNT", "KIND", "STATE"]
    assert "Lumen2MacEff@d4e5f6" in out
    assert out.count("state unknown: another account's agent") == 4


def test_harness_list_by_default_is_one_line_per_agent(tmp_path, monkeypatch, capsys):
    """Every reason under every row read as noise on the operator's laptop; by default the
    table is the rows, and only an unknown card, which can't be attached to, says why."""
    from macf import cli
    f = build(tmp_path)
    real = roster.local_roster
    monkeypatch.setattr(roster, "local_roster", lambda **kw: real(
        homes=f.homes, runtime=f.runtime, unit_dir=f.units, agents_yaml=f.agents_yaml,
        uid=os.getuid() + 100000, account_of=by_dirname))
    cli.cmd_harness_list(cli._build_parser().parse_args(["harness", "list", "--local"]))
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 + len(SEATS) + 1 and out[-1].startswith("(--verbose")
    assert not any("unknown:" in line for line in out)


def test_a_private_seat_takes_its_card_from_the_deployment(tmp_path):
    """A peer can't read a seat's config, and a legacy seat publishes no summary; the card
    comes from agents.yaml's calling_card and the world-readable identity file."""
    f = build(tmp_path, published=False)
    (f.homes / "pa_lumen3" / ".maceff" / "config.json").unlink()
    f.agents_yaml.write_text(f.agents_yaml.read_text().replace(
        "    username: pa_lumen3\n", "    username: pa_lumen3\n    calling_card: Lumen3MacEff\n"))
    seat = next(e for e in f.roster().entries if e.account == "pa_lumen3")
    assert (seat.card, seat.moniker, seat.uuid) == ("Lumen3MacEff@0a1b2c", "Lumen3MacEff", "0a1b2c")
    assert "card" not in seat.reasons


def test_on_a_host_a_home_that_names_no_agent_is_not_listed(tmp_path):
    """The login's own home on a laptop has a public tree and no card: not an agent."""
    homes = tmp_path / "home"
    (homes / "me" / "agent" / "public").mkdir(parents=True)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "units").mkdir()
    r = local_roster(homes=homes, runtime=tmp_path / "runtime", unit_dir=tmp_path / "units",
                     agents_yaml=tmp_path / "absent.yaml", probe=None, account_of=by_dirname)
    assert [e.account for e in r.entries] == []


def test_harness_list_on_an_empty_endpoint_says_so(tmp_path, monkeypatch, capsys):
    from macf import cli
    (tmp_path / "h").mkdir()
    real = roster.local_roster
    monkeypatch.setattr(roster, "local_roster", lambda **kw: real(
        homes=tmp_path / "h", runtime=tmp_path / "r", unit_dir=tmp_path / "u",
        agents_yaml=tmp_path / "x.yaml"))
    rc = cli.cmd_harness_list(cli._build_parser().parse_args(["harness", "list"]))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "No agents on this endpoint."
