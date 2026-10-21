"""The declaration's checks: the shared view of a container and its budget (MIS-0002-R62,
MIS-0002-R103), and the outer tier's boundary, one adapter per supported platform (MIS-0002-R10).

The cgroup numbers are a live shared container's, Oct 10: a 64 GiB limit, 24 CPUs, 44.2 GB
of process memory and 1 GB of kernel memory held, 13.7 GB of page cache besides.
"""
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from macf.pd import adapter as adapters
from macf.pd import interface, shared_view as sv

GIB = 2 ** 30


def _unit(name, kind="service", memory=256, env=None):
    return {"name": name, "kind": kind, "command": ["/usr/bin/true"], "account": "pa_x",
            "restart": "always", "liveness_interval_s": 15, "memory_limit_mb": memory,
            "environment": env or {}}


def _declaration(agent="B@4d5e6f", units=None):
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
    for user, card in (("pa_manny", "A@1a2b3c"), ("pa_manny2", "B@4d5e6f")):
        (homes / user / "agent" / "public").mkdir(parents=True)
        sv.publish(homes / user, _declaration(agent=card, units=[_unit("broker", memory=512)]), now=1.0)
    (homes / "student" / "agent" / "public").mkdir(parents=True)        # a home that published nothing
    views = sv.read_agents(homes)
    assert [v.status for v in views] == ["PUBLISHED", "PUBLISHED", "UNPUBLISHED"]
    text = sv.render(views, sv.read_budget(_cgroup(tmp_path)))
    assert "A@1a2b3c broker (service, 512 MB" in text and "B@4d5e6f broker" in text
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


class _Fake:
    def __init__(self, platform):
        self.platform = platform

    def render(self, card, agent_home):
        return f"run python -m macf.pd {agent_home}"

    def install(self, card, agent_home, force=False):
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


def test_every_unit_declared(tmp_path):
    """MIS-0002-R08 (unit_MUST_be_declared): the daemon manages exactly the units its
    agent declares. It holds one runner per declared unit, and a start, stop or restart
    asked for any other name is refused before anything is recorded or run, so a process
    nobody declared can't become a managed unit by being named on the socket."""
    from macf.pd.core import Core
    from macf.pd.interface import Asker
    operator = Asker(kind="operator", card="Operator@000000")
    core = Core(_declaration(units=[_unit("broker"), _unit("watcher")]), "B@4d5e6f",
                placeholders={"agent_home": str(tmp_path)})
    assert {name: core.state(name) for name in ("broker", "watcher")}
    for act in (core.start, core.stop, core.restart):
        with pytest.raises(KeyError, match="not a unit of this agent's declaration"):
            act("stray", operator, "a name the declaration lacks")
    assert core.pid("broker") is None and core.pid("watcher") is None


def test_schedules_hosted(tmp_path):
    """MIS-0002-R11 (CI_MUST_fail_unhosted_schedule): every declared schedule has a daemon to run
    it. A schedule can only be declared inside an agent's declaration, and that agent's daemon
    builds a scheduler for exactly those schedules. The one way to declare schedules no daemon
    runs, on an account that gets no MacEff footprint, is refused when agents.yaml loads: at
    container start, and in this test. A container agent whose declaration sits only in its home
    fails the start step (test_container_outer_tier.py)."""
    from macf.models.agent_spec import AgentSpec
    from macf.pd.daemon import Daemon
    schedule = {"name": "nightly", "cron": "0 3 * * *", "target": "isolated",
                "missed_run": {"kind": "skip"},
                "run": {"command": ["true"], "wake_when": "exit_code"}, "timeout_s": 60}
    home = tmp_path / "home"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text('{"agent_identity": {"moniker": "Tester"}}')
    interface.declaration_path(home).write_text(interface.Declaration(
        version=1, agent="Tester@abc123", timezone="UTC", schedules=[schedule]).model_dump_json())
    import shutil
    import tempfile
    base = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))     # a socket path short enough on macOS
    try:
        daemon = Daemon(home, base=base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert daemon.scheduler is not None
    assert [s.name for s in daemon.scheduler.declaration.schedules] == ["nightly"]
    # A declaration in the agent's home is checked against what pd install recorded (R33's host
    # half); a rendered one, out of the agent's reach, is not (test_pd_schedule.py).
    assert daemon.scheduler.check_installed
    with pytest.raises(ValueError, match="vanilla"):
        AgentSpec(username="pa_plain", uid=21100, flavor="vanilla",
                  primal_daemon={"timezone": "UTC", "schedules": [schedule]})
    AgentSpec(username="pa_plain", uid=21100, flavor="vanilla")          # vanilla, no daemon: fine



# ---- the organization allowlist (MIS-0002-R124) -----------------------------------------------

def _managed(tmp_path, entries):
    f = tmp_path / "managed-settings.json"
    f.write_text(json.dumps({"channelsEnabled": True, "allowedChannelPlugins": entries}))
    return f


TELEGRAM = {"plugin": "telegram", "marketplace": "claude-plugins-official"}
MACEFF = {"plugin": "maceff-channel", "marketplace": "maceff"}


def test_allowlist_lists_every_channel(tmp_path):
    """MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel): where managed settings set
    an allowlist, every channel it admits is in the declaration, and every channel the
    declaration lists is admitted. Each side's difference is named; agreement says nothing."""
    from macf.pd import allowlist

    def decl(channels):
        body = {"version": 1, "agent": "Ira@ee9a78"}
        if channels is not None:
            body["allowlisted_channels"] = channels
        return interface.Declaration.model_validate(body)

    admitted = allowlist.managed_allowlist([_managed(tmp_path, [TELEGRAM, "maceff-channel@maceff"])])
    assert admitted == {("telegram", "claude-plugins-official"), ("maceff-channel", "maceff")}

    assert allowlist.findings(decl([TELEGRAM, MACEFF]), admitted) == []
    assert allowlist.findings(decl([MACEFF, TELEGRAM]), admitted) == []         # order is not a difference

    (none,) = allowlist.findings(decl(None), admitted)
    assert "lists none" in none and "telegram@claude-plugins-official" in none

    (left_out,) = allowlist.findings(decl([MACEFF]), admitted)                # the operator's channel
    assert "telegram@claude-plugins-official" in left_out and "leaves out" in left_out

    other = {"plugin": "slack", "marketplace": "claude-plugins-official"}
    out = allowlist.findings(decl([TELEGRAM, MACEFF, other]), admitted)
    assert len(out) == 1 and "slack@claude-plugins-official" in out[0] and "won't load" in out[0]

    # No managed settings, or managed settings that set no allowlist: nothing to compare.
    assert allowlist.managed_allowlist([tmp_path / "absent.json"]) is None
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"channelsEnabled": True}))
    assert allowlist.managed_allowlist([plain]) is None
    assert allowlist.findings(decl(None), None) == []
    (empty,) = allowlist.findings(decl(None), set())                # a list that admits nothing
    assert "admits no channel plugin" in empty and "()" not in empty
    assert allowlist.findings(decl([]), set()) == []                 # declared as meant

    # A list that can't be read is not the same as no list.
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    with pytest.raises(ValueError):
        allowlist.managed_allowlist([broken])


def test_an_allowlisted_channel_names_plugin_and_marketplace():
    """The client admits a channel only when the plugin and its marketplace both match, so a
    declared entry with either missing would compare as nothing; it is refused at load."""
    body = {"version": 1, "agent": "Ira@ee9a78"}
    for bad in ({"plugin": "telegram"}, {"marketplace": "maceff"}, {"plugin": "", "marketplace": "x"},
                "telegram@claude-plugins-official"):
        with pytest.raises(ValidationError):
            interface.Declaration.model_validate({**body, "allowlisted_channels": [bad]})


def test_the_daemon_says_at_start_where_the_allowlist_and_declaration_differ(tmp_path, monkeypatch, capsys):
    """Managed settings can change after ``pd install`` compared them, so the daemon compares
    again at start: each difference goes to stderr and into one pd_allowlist_mismatch event,
    and agreement records nothing."""
    from types import SimpleNamespace

    import macf.agent_events_log as log
    from macf.pd.daemon import Daemon

    written = []
    monkeypatch.setattr(log, "append_event", lambda event, data: written.append((event, data)) or True)
    declaration = interface.Declaration.model_validate(
        {"version": 1, "agent": "Ira@ee9a78", "allowlisted_channels": [MACEFF]})
    stub = SimpleNamespace(core=SimpleNamespace(declaration=declaration), card="Ira@ee9a78",
                           _managed=[_managed(tmp_path, [TELEGRAM, MACEFF])])

    Daemon._compare_allowlist(stub)
    assert [e for e, _ in written] == [interface.EVENT_ALLOWLIST_MISMATCH]
    assert "telegram@claude-plugins-official" in written[0][1]["findings"][0]
    assert "telegram@claude-plugins-official" in capsys.readouterr().err

    written.clear()
    stub.core.declaration = interface.Declaration.model_validate(
        {"version": 1, "agent": "Ira@ee9a78", "allowlisted_channels": [TELEGRAM, MACEFF]})
    Daemon._compare_allowlist(stub)
    assert written == []


# ---- the mail processes, under the broker account's own daemon (MIS-0002-R53, R54) ------------

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
VENV_PY = "/opt/maceff-venv/bin/python"


def _mail_unit(name, *module_and_verb, account="amail_broker"):
    return {"name": name, "command": [VENV_PY, "-m", *module_and_verb], "account": account,
            "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 256}


#: The broker account's daemon, as a deployment declares it (persistent_layer section 8).
BROKER_DAEMON = {
    "units": [_mail_unit("broker", "macf.amail.daemons.broker"),
              _mail_unit("inbound-watcher", "macf.amail.daemons.inbound", "watch")],
    "schedules": [{"name": "inbound-sweep", "cron": "*/5 * * * *", "target": "isolated",
                   "missed_run": {"kind": "skip"}, "timeout_s": 120,
                   "run": {"command": [VENV_PY, "-m", "macf.amail.daemons.inbound", "sweep", "--quiet"],
                           "wake_when": "stdout"}}],
    "timezone": "UTC",
}


def _start():
    import importlib.util
    spec = importlib.util.spec_from_file_location("maceff_start_mail_units", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _agents_yaml(services):
    from macf.models.agent_spec import AgentsConfig
    return AgentsConfig.model_validate({"ids": {"base": 21000}, "agents": {}, "subagents": {},
                                        "services": services})


def _amail_step(start, tmp_path, monkeypatch):
    """Run the amail step against temporary paths, recording every process it launches itself
    and every start of the receiver. Provisioning that needs root fails and is logged, as on a
    host; that half is not what these tests are about."""
    launched = {"popen": [], "receiver": 0}
    for name, attr in (("broker_config.yaml", "AMAIL_BROKER_CONFIG"),
                       ("inbound_config.yaml", "AMAIL_INBOUND_CONFIG")):
        (tmp_path / name).write_text("{}")
        monkeypatch.setattr(start, attr, tmp_path / name)
    monkeypatch.setattr(start, "broker_cfg_handoff_root", lambda config: str(tmp_path / "handoff"))
    monkeypatch.setattr(start, "provision_pickup_boxes", lambda *a: None)
    monkeypatch.setattr(start.shutil, "chown", lambda *a, **k: None)
    monkeypatch.setattr(start, "_start_inbound_transport",
                        lambda interp: launched.__setitem__("receiver", launched["receiver"] + 1))
    monkeypatch.setattr(start.subprocess, "Popen", lambda *a, **k: launched["popen"].append(a))
    return launched


def test_mail_units(tmp_path, monkeypatch):
    """MIS-0002-R53 (mail_broker_MUST_be_managed): in a container, the mail broker and its inbound
    watcher are units of the broker account's own primal daemon. Start-up gives the account its
    identity, renders the declaration with both units, owned by root, and starts the daemon under
    the outer tier, and the amail step starts neither itself. A deployment that runs amail and
    declares no such daemon fails the step, by name, after starting the receiver."""
    from macf.pd import names as pd_names
    start = _start()
    home = tmp_path / "var" / "lib" / "amail_broker"
    monkeypatch.setattr(start, "SERVICE_PATHS", {"amail_broker": home})
    monkeypatch.setattr(start, "account_ids", lambda name: (os.getuid(), os.getgid()))
    monkeypatch.setattr(pd_names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    cfg = _agents_yaml({"amail_broker": {"calling_card": "AmailBroker", "primal_daemon": BROKER_DAEMON},
                        "amail_ingest": {}})
    owned = []
    rendered = start.render_pd_declarations(cfg, root=tmp_path / "etc",
                                            chown=lambda p, u, g: owned.append((Path(p).name, u, g)))
    assert rendered == ["amail_broker"]
    card = pd_names.agent_card(home)
    assert card == "AmailBroker@" + start.service_agent_id("amail_broker", cfg.ids)[:6]
    assert start.service_agent_id("amail_broker", cfg.ids) == start.service_agent_id("amail_broker", cfg.ids)
    declaration = json.loads((tmp_path / "etc" / "amail_broker" / "declaration.json").read_text())
    assert declaration["agent"] == card
    assert [u["name"] for u in declaration["units"]] == ["broker", "inbound-watcher"]
    who = {name: (u, g) for name, u, g in owned}
    assert who["config.json.tmp"] == who[".maceff_primary_agent.id.tmp"] == (0, 0)  # root's identity
    assert who[".maceff"] == (os.getuid(), os.getgid())         # the daemon writes its log there

    supervised = []
    monkeypatch.setattr(start, "supervise_primal_daemon", lambda user, where: supervised.append((user, where)))
    assert start.start_primal_daemons(cfg) == ["amail_broker"]
    for _ in range(50):
        if supervised:
            break
        time.sleep(0.01)
    assert supervised == [("amail_broker", home)]

    launched = _amail_step(start, tmp_path, monkeypatch)
    start.start_amail_services(cfg)
    assert launched == {"popen": [], "receiver": 1}

    bare = _agents_yaml({"amail_broker": {}, "amail_ingest": {}})
    launched = _amail_step(start, tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="R53"):
        start.start_amail_services(bare)
    assert launched == {"popen": [], "receiver": 1}

    with pytest.raises(ValidationError, match="only as the service account"):
        _agents_yaml({"amail_broker": {"calling_card": "AmailBroker", "primal_daemon": {
            "units": [_mail_unit("broker", "macf.amail.daemons.broker", account="pa_manny")]}}})
    with pytest.raises(ValidationError, match="together"):
        _agents_yaml({"amail_broker": {"calling_card": "AmailBroker"}})


def test_periodic_clock_is_schedule(tmp_path, monkeypatch):
    """MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule): a mail check that runs on a period is
    a schedule, with its missed-run policy declared, so each run, owed and done, is recorded. In a
    container that check is the aged sweep, a schedule of the broker account's daemon. The inbound
    watcher's 15 s drain is that unit's own loop, its health the unit's liveness, and it never
    sweeps (test_amail_watch_resilience.py). So a declaration that runs the sweep or the watchdog
    as a unit is refused when agents.yaml loads, the sweep declared as a schedule loads, and
    start-up launches no mail process of its own."""
    by_path = {"name": "inbound-sweep", "command": ["/opt/macf_tools/src/macf/amail/daemons/inbound.py", "sweep"],
               "account": "amail_broker", "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 64}
    for unit in [_mail_unit("inbound-" + verb, "macf.amail.daemons.inbound", verb)
                 for verb in ("sweep", "watchdog")] + [by_path]:
        looping = {**BROKER_DAEMON, "units": BROKER_DAEMON["units"] + [unit]}
        with pytest.raises(ValidationError, match="R54"):
            _agents_yaml({"amail_broker": {"calling_card": "AmailBroker", "primal_daemon": looping}})
    cfg = _agents_yaml({"amail_broker": {"calling_card": "AmailBroker", "primal_daemon": BROKER_DAEMON}})
    declaration = interface.Declaration(version=1, agent="AmailBroker@abc123",
                                        **cfg.services["amail_broker"].primal_daemon)
    (sweep,) = [s for s in declaration.schedules if "sweep" in s.run.command]
    assert sweep.missed_run.kind == "skip"
    assert sweep.run.wake_when == "stdout" and "--quiet" in sweep.run.command

    start = _start()
    launched = _amail_step(start, tmp_path, monkeypatch)
    start.start_amail_services(cfg)
    assert launched["popen"] == []

