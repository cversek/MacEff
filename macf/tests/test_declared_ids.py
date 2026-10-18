"""Container accounts and groups take declared numbers from the deployment's id block.

A container without user-namespace remapping shares the host's id space, so a number
assigned by creation order lands on whatever the host already gave out. The schema holds
the block and each agent's uid; start.py creates every account and group at its number,
and refuses to start when a live account, group or persisted home holds another one.
"""
import grp
import importlib.util
import pwd
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import AgentsConfig, AgentSpec, IdBlock

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


def config(base=21000, uids=(21100, 21101)):
    return {
        "ids": {"base": base},
        "agents": {f"a{i}": {"username": f"pa_a{i}", "uid": u, "personality": "p.md"}
                   for i, u in enumerate(uids)},
        "subagents": {},
    }


# --- the schema -----------------------------------------------------------------------------


def test_the_block_fixes_its_slots():
    ids = IdBlock(base=21000)
    assert ids.slot("admin") == 21000
    assert [ids.slot(g) for g in ("agents_all", "sa_all", "policyeditors")] == [21001, 21002, 21003]
    assert (ids.slot("amail_broker"), ids.slot("amail_ingest")) == (21998, 21999)
    assert (ids.agent_range().start, ids.agent_range().stop - 1) == (21100, 21899)


@pytest.mark.parametrize("base", [1000, 19000, 21500, 0, 65000])
def test_a_block_clashing_with_host_ids_or_unaligned_is_refused(base):
    with pytest.raises(ValidationError):
        IdBlock(base=base)


def test_the_block_is_required():
    raw = config()
    del raw["ids"]
    with pytest.raises(ValidationError, match="ids"):
        AgentsConfig(**raw)


def test_an_agent_uid_is_required():
    with pytest.raises(ValidationError, match="uid"):
        AgentSpec(username="pa_x", personality="p.md")


@pytest.mark.parametrize("uid", [21000, 21003, 21099, 21900, 21998, 22100, 1002])
def test_an_agent_uid_outside_the_agent_slots_is_refused(uid):
    with pytest.raises(ValidationError, match="outside the agent slots"):
        AgentsConfig(**config(uids=(uid,)))


def test_two_agents_on_one_uid_are_refused():
    with pytest.raises(ValidationError, match="both declare uid 21100"):
        AgentsConfig(**config(uids=(21100, 21100)))


def test_a_valid_config_loads():
    cfg = AgentsConfig(**config())
    assert {s.uid for s in cfg.agents.values()} == {21100, 21101}


# --- start.py -------------------------------------------------------------------------------


@pytest.fixture
def start(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("maceff_start_declared_ids", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.calls = []
    monkeypatch.setattr(module, "run_command", lambda argv, **kw: module.calls.append(list(argv)) or "")
    monkeypatch.setattr(module, "log", lambda msg: None)
    monkeypatch.setattr(module, "HOME_ROOT", tmp_path)
    return module


def no_such(name):
    raise KeyError(name)


class Stop(Exception):
    pass


def agent(uid=21100):
    return AgentSpec(username="pa_a0", uid=uid, personality="p.md")


def test_a_new_agent_is_created_at_its_declared_uid_and_gid(start, monkeypatch):
    monkeypatch.setattr(start.pwd, "getpwnam", no_such)
    monkeypatch.setattr(start.grp, "getgrnam", no_such)

    def record(argv, **kw):
        start.calls.append(list(argv))
        if argv[0] == "usermod":
            raise Stop()  # everything after creation is out of this test's scope
        return ""
    monkeypatch.setattr(start, "run_command", record)
    with pytest.raises(Stop):
        start.create_pa_user("a0", agent())
    assert ["groupadd", "-g", "21100", "pa_a0"] in start.calls
    assert ["useradd", "-m", "-s", "/bin/bash", "-u", "21100", "-g", "21100", "pa_a0"] in start.calls


def test_an_existing_account_on_another_uid_stops_start_up(start, monkeypatch):
    monkeypatch.setattr(start.pwd, "getpwnam", lambda n: SimpleNamespace(pw_uid=1002, pw_gid=1004))
    with pytest.raises(start.DeclaredIdMismatch, match="uid 1002 gid 1004.*declares 21100"):
        start.create_pa_user("a0", agent())
    assert not start.calls, "nothing may be changed before the refusal"


def test_a_persisted_home_owned_by_another_uid_stops_start_up(start, monkeypatch, tmp_path):
    """After a recreate /etc/passwd is fresh but /home is not: creating the account at the
    new number would lock the agent out of its own files."""
    (tmp_path / "pa_a0").mkdir()
    import os
    mine = os.stat(tmp_path / "pa_a0").st_uid
    monkeypatch.setattr(start.pwd, "getpwnam", no_such)
    with pytest.raises(start.DeclaredIdMismatch, match=f"owned by uid {mine}.*renumber"):
        start.create_pa_user("a0", agent(uid=21100 if mine != 21100 else 21101))
    assert not start.calls


def test_a_group_on_another_gid_stops_start_up(start, monkeypatch):
    monkeypatch.setattr(start.grp, "getgrnam", lambda n: SimpleNamespace(gr_gid=1002))
    with pytest.raises(start.DeclaredIdMismatch, match="agents_all has gid 1002.*declares 21001"):
        start.ensure_group("agents_all", 21001)


def test_a_missing_group_is_created_at_its_gid(start, monkeypatch):
    monkeypatch.setattr(start.grp, "getgrnam", no_such)
    start.ensure_group("sa_all", 21002)
    assert start.calls == [["groupadd", "-g", "21002", "sa_all"]]


def test_an_image_built_for_another_block_stops_start_up(start, monkeypatch):
    accounts = {"admin": SimpleNamespace(pw_uid=1001, pw_gid=1001)}
    monkeypatch.setattr(start.pwd, "getpwnam", lambda n: accounts[n] if n in accounts else no_such(n))
    with pytest.raises(start.DeclaredIdMismatch, match="admin as uid 1001.*MACEFF_ID_BASE=21000"):
        start.check_image_ids(IdBlock(base=21000))


def test_an_image_that_kept_the_ubuntu_account_stops_start_up(start, monkeypatch):
    accounts = {"admin": SimpleNamespace(pw_uid=21000, pw_gid=21000),
                "amail_broker": SimpleNamespace(pw_uid=21998, pw_gid=21998),
                "amail_ingest": SimpleNamespace(pw_uid=21999, pw_gid=21999),
                "ubuntu": SimpleNamespace(pw_uid=1000, pw_gid=1000)}
    monkeypatch.setattr(start.pwd, "getpwnam", lambda n: accounts[n] if n in accounts else no_such(n))
    with pytest.raises(start.DeclaredIdMismatch, match="ubuntu"):
        start.check_image_ids(IdBlock(base=21000))
    del accounts["ubuntu"]
    start.check_image_ids(IdBlock(base=21000))


def test_a_service_directory_left_at_its_old_owner_stops_start_up(start, monkeypatch, tmp_path):
    """Review of #696: the image puts admin and the amail accounts at the block's slots, but their
    persisted directories keep the owners they had before a rebuild."""
    import os
    mine = os.stat(tmp_path).st_uid
    paths = {name: tmp_path / name for name in ("admin", "amail_broker", "amail_ingest")}
    paths["amail_broker"].mkdir()
    monkeypatch.setattr(start, "SERVICE_PATHS", paths)
    block = IdBlock(base=21000)
    with pytest.raises(start.DeclaredIdMismatch, match=f"amail_broker is owned by uid {mine}.*21998.*renumber"):
        start.check_service_paths(block)
    assert "check_image_ids(ids)\n        check_service_paths(ids)\n" in START_PY.read_text()
    paths["amail_broker"].rmdir()                     # missing directories are left to the image
    start.check_service_paths(block)


def test_start_up_refuses_with_a_message_not_a_traceback():
    """main catches the mismatch by name and logs it as a refusal."""
    src = START_PY.read_text()
    assert "except DeclaredIdMismatch as e:" in src and 'log(f"REFUSED: {e}")' in src
