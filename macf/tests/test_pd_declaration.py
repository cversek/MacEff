"""The declaration's checks: the shared view of a container and its budget (MIS-0002-R62,
MIS-0002-R103), and the outer tier's boundary, one adapter per supported platform (MIS-0002-R10).

The cgroup numbers are a live shared container's, Oct 10: a 64 GiB limit, 24 CPUs, 44.2 GB
of process memory and 1 GB of kernel memory held, 13.7 GB of page cache besides.
"""
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf.pd import adapter as adapters
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


class _Fake:
    def __init__(self, platform):
        self.platform = platform

    def render(self, card, agent_home):
        return f"run python -m macf.pd {agent_home}"

    def install(self, card, agent_home):
        return Path("/nonexistent")

    def uninstall(self, card):
        return None

    def status(self, card):
        return "inactive"


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(adapters, "_ADAPTERS", {})
    return adapters


def test_one_adapter_per_platform(registry):
    registry.register(_Fake("linux"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_Fake("linux"))
    with pytest.raises(ValueError, match="not a supported platform"):
        registry.register(_Fake("plan9"))
    with pytest.raises(TypeError):
        registry.register(object())
    assert registry.adapter_for("linux").platform == "linux"
    assert registry.missing_renderings() == ["darwin"]


def test_renderings_exist():
    """Every supported platform has an outer tier (R10): the LaunchAgent and the systemd user unit."""
    assert adapters.missing_renderings() == []


CARD_T = "Tester@abc123"


class _Ran:
    """A stand-in for running a command: records each argv and answers success."""

    def __init__(self):
        self.argvs = []

    def __call__(self, argv):
        from types import SimpleNamespace
        self.argvs.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_renderings_hold_only_the_agent_home(tmp_path):
    """Each outer tier runs ``python -m macf.pd <agent home>`` and carries no agent configuration (R04)."""
    home = tmp_path / "agent"
    launch = adapters.LaunchdAdapter(user_home=tmp_path, uid=501).render(CARD_T, home)
    unit = adapters.SystemdAdapter(user_home=tmp_path).render(CARD_T, home)
    for text in (launch, unit):
        assert "macf.pd" in text and str(home) in text
    assert "EnvironmentVariables" not in launch
    assert not any(line.startswith("Environment=") for line in unit.splitlines())


def test_systemd_install_writes_the_unit_then_enables_it(tmp_path):
    ran = _Ran()
    path = adapters.SystemdAdapter(user_home=tmp_path, run=ran).install(CARD_T, tmp_path / "agent")
    assert path.exists() and path.parent == tmp_path / ".config" / "systemd" / "user"
    assert ran.argvs == [["systemctl", "--user", "daemon-reload"],
                         ["systemctl", "--user", "enable", "--now", path.name]]


def test_launchd_install_writes_the_plist_then_bootstraps_it(tmp_path):
    ran = _Ran()
    path = adapters.LaunchdAdapter(user_home=tmp_path, uid=501, run=ran).install(CARD_T, tmp_path / "agent")
    assert path.exists() and path.parent == tmp_path / "Library" / "LaunchAgents"
    assert any("bootstrap" in argv for argv in ran.argvs)


@pytest.mark.parametrize("code, said", [(113, "not loaded"), (112, "no GUI session for uid 501"),
                                        (5, "unknown: launchctl says why")])
def test_launchd_status_tells_its_failures_apart(tmp_path, code, said):
    """launchctl print answers 113 for a service the user's domain doesn't have and 112 when
    the user has no GUI domain, as over SSH. Anything else is unknown, in launchctl's words."""
    from types import SimpleNamespace

    def run(argv):
        return SimpleNamespace(returncode=code, stdout="", stderr="launchctl says why")
    assert adapters.LaunchdAdapter(user_home=tmp_path, uid=501, run=run).status(CARD_T).startswith(said)



def test_schedule_without_policy_fails():
    """A schedule with no missed-run policy is refused, never given a default (R109): a
    default would decide, for every schedule nobody thought about, what a downtime does."""
    schedule = {"name": "nightly", "cron": "0 3 * * *", "target": "isolated",
                "run": {"command": ["true"], "wake_when": "exit_code"}, "timeout_s": 60}
    with pytest.raises(ValidationError, match="missed_run"):
        interface.Schedule.model_validate(schedule)
    interface.Schedule.model_validate({**schedule, "missed_run": {"kind": "skip"}})
