"""The shared view of a container and its budget (MIS-0002-R62, MIS-0002-R103).

The cgroup numbers are a live shared container's, Oct 10: a 64 GiB limit, 24 CPUs, 44.2 GB
of process memory and 1 GB of kernel memory held, 13.7 GB of page cache besides.
"""
import json
import os

import pytest
from pydantic import ValidationError

from macf.pd import interface, shared_view as sv

GIB = 2 ** 30


def _unit(name, kind="service", memory=256, env=None):
    return {"name": name, "kind": kind, "command": ["/usr/bin/true"], "account": "pa_x",
            "restart": "always", "liveness_interval_s": 15, "memory_limit_mb": memory,
            "environment": env or {}}


def _declaration(agent="Manny2@78e0aa", units=None):
    return interface.Declaration.model_validate(
        {"version": 1, "agent": agent, "units": units if units is not None else [_unit("broker")]})


def _cgroup(tmp_path, limit="68719476736", cpu="2400000 100000",
            stat="anon 44235186176\nfile 13708660736\nkernel 957566976\n"):
    cg = tmp_path / "cgroup"
    cg.mkdir()
    (cg / "memory.max").write_text(limit + "\n")
    (cg / "cpu.max").write_text(cpu + "\n")
    (cg / "memory.stat").write_text(stat)
    for f in cg.iterdir():
        f.chmod(0o444)      # as inside a container: readable, not writable
    return cg


def test_shared_budget_operator_only(tmp_path):
    """MIS-0002-R103: no declaration can carry the container's budget, and the view only reads it."""
    for field in ("shared_budget", "container_memory_mb", "cpus"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            interface.Declaration.model_validate({"version": 1, "agent": "A@1a2b3c", field: 1})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        interface.Unit.model_validate({**_unit("x"), "container_memory_mb": 1})
    # A unit's limit is its own share, never the container's: the budget is read from files the
    # agent cannot write, and reading needs nothing more than read access.
    b = sv.read_budget(_cgroup(tmp_path))
    assert (b.memory_max_bytes, b.cpus, b.unreadable) == (64 * GIB, 24.0, [])
    assert not hasattr(sv, "write_budget")


def test_the_budget_counts_what_cannot_be_reclaimed(tmp_path):
    b = sv.read_budget(_cgroup(tmp_path))
    assert b.memory_held_bytes == 44235186176 + 957566976      # not the 13.7 GB of page cache


def test_an_unlimited_container_reads_no_limit_and_an_unreadable_file_reads_unknown(tmp_path):
    cg = _cgroup(tmp_path, limit="max", cpu="max 100000")
    (cg / "memory.stat").chmod(0o000)
    b = sv.read_budget(cg)
    assert (b.memory_max_bytes, b.cpus) == (0, 0.0)
    if os.geteuid() != 0:   # root reads a 000 file anyway
        assert b.memory_held_bytes is None and b.unreadable == ["memory.stat"]


def test_a_summary_carries_no_command_and_no_environment(tmp_path):
    home = tmp_path / "pa_manny2"
    decl = _declaration(units=[_unit("broker", env={"API_KEY": "s3cret"}), _unit("session", kind="session")])
    path = sv.publish(home, decl, now=1.0)
    text = path.read_text()
    assert "s3cret" not in text and "API_KEY" not in text and "/usr/bin/true" not in text
    assert oct(path.stat().st_mode & 0o777) == "0o644"
    assert [u["name"] for u in json.loads(text)["units"]] == ["broker", "session"]


def test_every_agents_units_are_seen_and_none_controlled(tmp_path):
    """MIS-0002-R62: each agent's units appear in the view; the view offers no act."""
    homes = tmp_path / "home"
    for user, card in (("pa_manny", "Manny@b82044"), ("pa_manny2", "Manny2@78e0aa")):
        (homes / user / "agent" / "public").mkdir(parents=True)
        sv.publish(homes / user, _declaration(agent=card, units=[_unit("broker", memory=512)]), now=1.0)
    (homes / "student" / "agent" / "public").mkdir(parents=True)        # a home that published nothing
    views = sv.read_agents(homes)
    assert [v.status for v in views] == ["PUBLISHED", "PUBLISHED", "UNPUBLISHED"]
    text = sv.render(views, sv.read_budget(_cgroup(tmp_path)))
    assert "Manny@b82044 broker (service, 512 MB" in text and "Manny2@78e0aa broker" in text
    assert "UNPUBLISHED" in text and "held 42.1 GiB (66%)" in text
    assert "Declared unit limits sum to 1024 MB of the container's 65536 MB." in text
    assert not any(hasattr(sv, act) for act in ("stop", "start", "restart", "act", "control"))


def test_a_summary_that_does_not_parse_is_unreadable_never_empty(tmp_path):
    home = tmp_path / "pa_x"
    path = sv.published_path(home)
    path.parent.mkdir(parents=True)
    path.write_text("")
    v = sv.read_agent(home)
    assert v.status == "UNREADABLE" and v.units is None


def test_a_summary_another_account_owns_is_not_believed(tmp_path, monkeypatch):
    """Only the owner writes its public tree; a reader still checks, so a file planted by
    another account (a misprovisioned tree, a copy) never speaks for this home's agent."""
    home = tmp_path / "pa_manny2"
    path = sv.publish(home, _declaration(), now=1.0)
    real_stat = type(path).stat

    def stat(self, *a, **k):
        st = real_stat(self, *a, **k)
        if self == path:
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid + 1,
                                   st.st_gid, st.st_size, st.st_atime, st.st_mtime, st.st_ctime))
        return st
    monkeypatch.setattr(type(path), "stat", stat)
    v = sv.read_agent(home)
    assert v.status == "UNREADABLE" and "not owned by the account" in v.detail


def test_every_agent_gets_its_publishing_point_at_init():
    """agent/public is 550 after init, so the pd directory must be made there, beside the mailbox."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py").read_text()
    calls = [n.func.id for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "create_pd_view_dir" in calls


def test_grants_declared():
    """MIS-0002-R63 (unit_MUST_declare_privacy_grants): each unit carries the grants it states,
    a unit that states none needs none, and a grant outside the closed list refuses the
    declaration when it is read, not as a missing grant at run time."""
    bot = dict(_unit("bot"), privacy_grants=["local_network", "automation:com.apple.Terminal"])
    decl = _declaration(units=[bot, _unit("broker")])
    assert [u.privacy_grants for u in decl.units] == [
        ["local_network", "automation:com.apple.Terminal"], []]
    with pytest.raises(ValidationError, match="unknown privacy grant"):
        _declaration(units=[dict(_unit("bot"), privacy_grants=["local-network"])])
