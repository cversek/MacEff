"""MIS-0002-R162: a new agent's account is its card lowercased, minted ahead, on a declared homes volume.

The schema derives a minted agent's account; start creates a home only for a minted agent on the
marked volume agents.yaml declares, writes the declared short id as its identity, and refuses a
home whose identity disagrees. Every refusal happens before start changes anything.
"""
import importlib.util
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf import calling_card, homes
from macf.models.agent_spec import AgentsConfig, AgentSpec

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
VOLUME = "0123456789abcdef"


def minted(**over):
    return AgentSpec(**{"calling_card": "WrenTuba", "short_id": "3c9d1e", "uid": 21100,
                        "personality": "p.md", **over})


# --- the schema -----------------------------------------------------------------------------


def test_a_new_account_is_the_card_lowercased():
    """R162: a minted agent's account is its card lowercased, and declares no username."""
    assert minted().username == "wrentuba_3c9d1e"


def test_a_username_other_than_the_card_is_refused_beside_a_short_id():
    with pytest.raises(ValidationError, match="'wrentuba_3c9d1e'.*leave username out"):
        minted(username="pa_wren")


def test_a_short_id_needs_the_card_name():
    with pytest.raises(ValidationError, match="without calling_card"):
        AgentSpec(short_id="3c9d1e", uid=21100, personality="p.md")


@pytest.mark.parametrize("bad", ["3C9D1E", "3c9d1", "3c9d1e0", "3c9d1g"])
def test_a_short_id_is_six_lowercase_hex(bad):
    with pytest.raises(ValidationError):
        minted(short_id=bad)


def test_an_existing_agent_keeps_its_declared_username():
    """R162's second sentence: an account that existed before keeps its name."""
    assert AgentSpec(username="pa_sparrow", uid=21100, personality="p.md").username == "pa_sparrow"


def test_the_homes_volume_is_sixteen_hex():
    raw = {"ids": {"base": 21000}, "agents": {}, "subagents": {}}
    assert AgentsConfig(**raw, homes_volume=VOLUME).homes_volume == VOLUME
    with pytest.raises(ValidationError):
        AgentsConfig(**raw, homes_volume="not-an-id")


# --- minting and the marker -----------------------------------------------------------------


def test_mint_draws_a_card_an_account_and_a_zone_token():
    m = homes.mint("WrenTuba")
    assert calling_card.split(m.card) == ("WrenTuba", m.short_id)
    assert m.account == m.card.lower()
    assert re.fullmatch(r"[0-9a-f]{24}", m.zone_token)


def test_mint_refuses_a_name_a_card_cant_take():
    with pytest.raises(calling_card.CardError):
        homes.mint("Wren_Tuba")


@pytest.mark.parametrize("short_id, token", [("873633", "123456789012345678901234"),
                                             ("0e1234", "0e0000000000000000000000")])
def test_what_mint_prints_loads_as_a_declaration(short_id, token):
    """Pasted as printed, both blocks parse to strings and the agent loads: YAML would read an
    unquoted 873633 as an integer and 0e1234 as the float 0.0."""
    import yaml
    m = homes.Minted(name="WrenTuba", short_id=short_id, zone_token=token)
    text = homes.render_minted(m, "wren")
    agents_block, addressing_block = text.split("agents.yaml, under agents")[1].split("The addressing file")
    declared = yaml.safe_load(agents_block.split("\n", 1)[1])["wren"]
    assert declared == {"calling_card": "WrenTuba", "short_id": short_id}
    address = yaml.safe_load(addressing_block.split("\n", 1)[1].split("\nThe zone token")[0])
    assert address[m.account] == {"account": m.account, "card": m.card, "zone_token": token}
    assert AgentSpec(**declared, uid=21100, personality="p.md").username == m.account


def test_homes_init_marks_once_and_keeps_its_id(tmp_path):
    first = homes.init_volume(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{16}", first)
    assert homes.init_volume(tmp_path) == first
    assert homes.read_volume(tmp_path) == first


def test_a_marker_that_holds_no_id_is_refused(tmp_path):
    (tmp_path / homes.MARKER).write_text("yes\n")
    with pytest.raises(homes.HomesRefused, match="not a homes volume id"):
        homes.read_volume(tmp_path)


def test_an_unmarked_root_is_refused_when_a_volume_is_declared(tmp_path):
    with pytest.raises(homes.HomesRefused, match="carries no marker"):
        homes.check_volume(tmp_path, VOLUME)


def test_another_volume_is_refused_naming_both(tmp_path):
    found = homes.init_volume(tmp_path)
    with pytest.raises(homes.HomesRefused, match=f"declares homes_volume {VOLUME}.*is volume {found}"):
        homes.check_volume(tmp_path, VOLUME)


def test_nothing_declared_checks_nothing(tmp_path):
    homes.check_volume(tmp_path, None)


# --- start.py -------------------------------------------------------------------------------


@pytest.fixture
def start(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("maceff_start_homes", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.calls = []
    monkeypatch.setattr(module, "run_command", lambda argv, **kw: module.calls.append(list(argv)) or "")
    monkeypatch.setattr(module, "log", lambda msg: None)
    monkeypatch.setattr(module, "HOME_ROOT", tmp_path)
    monkeypatch.setattr(module.pwd, "getpwnam", lambda n: (_ for _ in ()).throw(KeyError(n)))
    monkeypatch.setattr(module.grp, "getgrnam", lambda n: (_ for _ in ()).throw(KeyError(n)))
    return module


def marked(root: Path) -> str:
    volume = VOLUME
    (root / homes.MARKER).write_text(volume + "\n")
    return volume


class Stop(Exception):
    pass


def stop_after_useradd(start, monkeypatch):
    def record(argv, **kw):
        start.calls.append(list(argv))
        if argv[0] == "usermod":
            raise Stop()
        return ""
    monkeypatch.setattr(start, "run_command", record)


def test_a_minted_agent_on_the_declared_volume_gets_its_account(start, monkeypatch, tmp_path):
    stop_after_useradd(start, monkeypatch)
    with pytest.raises(Stop):
        start.create_pa_user("wren", minted(), homes_volume=marked(tmp_path))
    assert ["useradd", "-m", "-s", "/bin/bash", "-u", "21100", "-g", "21100", "wrentuba_3c9d1e"] in start.calls


def test_a_missing_home_on_an_unmarked_root_is_refused_not_created(start, tmp_path):
    """The host-side maintainer's case: a volume that failed to mount leaves an empty directory.
    Start must refuse it, not provision a fresh agent into it."""
    with pytest.raises(start.HomesRefused, match="carries no marker"):
        start.create_pa_user("wren", minted(), homes_volume=VOLUME)
    assert not start.calls, "nothing may be changed before the refusal"
    assert not (tmp_path / "wrentuba_3c9d1e").exists()


def test_a_missing_home_with_no_volume_declared_is_refused(start, tmp_path):
    marked(tmp_path)
    with pytest.raises(start.HomesRefused, match="declares no homes_volume"):
        start.create_pa_user("wren", minted(), homes_volume=None)
    assert not start.calls


def test_an_agent_not_minted_gets_no_new_home(start, tmp_path):
    """R162: start never draws an identity for a new account; the agent is minted ahead."""
    with pytest.raises(start.HomesRefused, match="agent mint"):
        start.create_pa_user("a0", AgentSpec(username="pa_a0", uid=21100, personality="p.md"),
                             homes_volume=marked(tmp_path))
    assert not start.calls


def test_a_home_whose_identity_disagrees_is_refused_before_any_change(start, tmp_path):
    home = tmp_path / "wrentuba_3c9d1e"
    home.mkdir()
    (home / homes.IDENTITY_FILE).write_text("ffffff")
    with pytest.raises(start.HomesRefused, match="declares short_id 3c9d1e.*holds ffffff"):
        start.create_pa_user("wren", minted(uid=home.stat().st_uid), homes_volume=marked(tmp_path))
    assert not start.calls


def test_the_declared_short_id_becomes_the_identity_file(start, tmp_path):
    home = tmp_path / "wrentuba_3c9d1e"
    home.mkdir()
    assert start.provision_agent_identity("wrentuba_3c9d1e", str(home), None, "wren",
                                          short_id="3c9d1e") == "3c9d1e"
    assert (home / homes.IDENTITY_FILE).read_text() == "3c9d1e"
