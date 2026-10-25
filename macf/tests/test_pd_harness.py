"""The Claude Code harness adapter: the client's own compactions and its own supervisor.

MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction): where the harness can
compact an idle session on its own, the adapter turns that off unless the declaration
keeps it. Claude Code compacts a session about 54 minutes after its last request once
the context passes a threshold, and from 2.1.290 the settings key ``idleCompaction``
set to false stops that alone, leaving compaction at the context limit on.

MIS-0002-R66 (pd_MUST_adopt_harness_supervisor): a session the client's background
daemon already hosts is adopted, never supervised a second time, and acted on through
the client's own verbs.

MIS-0002-R104 (adapter_MUST_deliver_through_channel): where the session has the MacEff
channel, each wake and each notice goes through it, and nothing is typed.
"""
import json
from dataclasses import dataclass

import pytest

from macf.utils.claude_settings import idle_compaction_status, set_idle_compaction
from macf.utils.client_daemon import ADOPT, REFUSE, START, client_command, decide, unit_state


def _settings(root):
    return json.loads((root / ".claude" / "settings.local.json").read_text())


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(json.dumps({"env": {"A": "1"}, "hooks": {}}))
    return tmp_path


def test_idle_compaction_off(project):
    """The adapter writes idleCompaction false and leaves every other key alone."""
    result = set_idle_compaction(False, client_version="2.1.296", project_root=project)
    settings = _settings(project)
    assert settings["idleCompaction"] is False
    assert settings["env"] == {"A": "1"} and "hooks" in settings
    assert result["changed"] is True
    assert idle_compaction_status(project)["state"] == "off"


def test_refuses_on_client_without_the_setting(project):
    """Before 2.1.290 the client ignores the key, so writing it would claim a protection that is not there."""
    with pytest.raises(ValueError, match="2.1.289"):
        set_idle_compaction(False, client_version="2.1.289", project_root=project)
    assert "idleCompaction" not in _settings(project)


def test_declaration_can_keep_idle_compaction(project):
    """When the declaration keeps idle compaction, the adapter writes nothing."""
    result = set_idle_compaction(False, client_version="2.1.296", project_root=project, keep=True)
    assert result["changed"] is False
    assert "idleCompaction" not in _settings(project)


def _start_session_unit(tmp_path, project, monkeypatch, keep):
    """Run the harness adapter's own entry point (``macf_tools harness unit``) with the client
    launch stubbed out, for a home whose declaration keeps idle compaction or not, a client
    new enough to have the setting, and the session's project at *project*. Returns the
    sessions the stub was asked to start."""
    from types import SimpleNamespace

    import macf.cli as cli
    from macf.pd import names as pd_names
    from macf.pd import session_unit
    from macf.utils import harness
    from macf.utils.paths import find_project_root

    home = tmp_path / "home"
    (home / ".maceff" / "pd").mkdir(parents=True)
    card = "Resident@1a2b3c"
    (home / ".maceff" / "pd" / "declaration.json").write_text(json.dumps(
        {"version": 1, "agent": card, "keep_harness_idle_compaction": keep}))
    monkeypatch.setattr(pd_names, "RENDERED_DECLARATIONS", tmp_path / "rendered")   # none rendered
    monkeypatch.setattr(pd_names, "agent_card", lambda h: card)
    monkeypatch.setattr(cli, "_claude_launcher", lambda: ("/usr/bin/claude", "2.1.296 (Claude Code)"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    find_project_root.cache_clear()
    params = SimpleNamespace(agent="resident", home=home, project_dir=project,
                             child_path=home / "child", context_window=200000,
                             term="xterm-256color", proxy_port=0)
    monkeypatch.setattr(harness, "default_params", lambda agent=None, home=None: params)
    monkeypatch.setattr(harness, "load_settings", lambda p: p)
    started = []
    monkeypatch.setattr(session_unit, "run", lambda agent, child, **kw: started.append(agent) or 0)
    try:
        assert session_unit.main(["--no-proxy"]) == 0
    finally:
        find_project_root.cache_clear()
    return started


def test_the_adapter_turns_idle_compaction_off_when_it_starts_the_session(tmp_path, project, monkeypatch):
    """R126 at the place it names: starting the session through the adapter's own entry point
    leaves the project's settings with idle compaction off, every other key untouched."""
    started = _start_session_unit(tmp_path, project, monkeypatch, keep=False)
    assert started == ["resident"]
    settings = _settings(project)
    assert settings.get("idleCompaction") is False
    assert settings["env"] == {"A": "1"} and "hooks" in settings


def test_an_unreadable_declaration_keeps_nothing_so_idle_compaction_goes_off(tmp_path, project, monkeypatch):
    """The protection holds when the keep can't be read: a declaration that doesn't parse turns
    idle compaction off and says so, and the session still starts."""
    import macf.pd.core as core
    monkeypatch.setattr(core, "load_declaration", lambda home, card: (_ for _ in ()).throw(
        core.DeclarationRefused("not a valid declaration")))
    started = _start_session_unit(tmp_path, project, monkeypatch, keep=True)
    assert started == ["resident"] and _settings(project).get("idleCompaction") is False


def test_the_adapter_leaves_idle_compaction_alone_when_the_declaration_keeps_it(
        tmp_path, project, monkeypatch):
    """R126's keep clause, through the adapter: a declaration with keep_harness_idle_compaction
    true starts the session and writes nothing to the project's settings."""
    before = _settings(project)
    started = _start_session_unit(tmp_path, project, monkeypatch, keep=True)
    assert started == ["resident"]
    assert _settings(project) == before


def test_turning_it_back_on_removes_the_key(project):
    """`true` does not turn idle compaction on in the client, so on means the key is gone."""
    set_idle_compaction(False, client_version="2.1.296", project_root=project)
    set_idle_compaction(True, client_version="2.1.296", project_root=project)
    assert "idleCompaction" not in _settings(project)
    assert idle_compaction_status(project)["state"] == "client default"


def test_the_sessions_project_is_read_wherever_the_command_runs(tmp_path, monkeypatch):
    """#722: run from inside another checkout with its own .claude/, the status and the switch
    use the project the session starts in, from its unit's --project-dir, and say so. Without a
    session unit naming one, the lookup by working directory is used, and named as such."""
    from macf.pd.interface import declaration_path
    from macf.utils.claude_settings import session_project_root
    from macf.utils.paths import find_project_root
    home, work, checkout = tmp_path / "home", tmp_path / "work", tmp_path / "checkout"
    for d in (work / ".claude", checkout / ".claude", checkout / ".git"):
        d.mkdir(parents=True)
    path = declaration_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "agent": "Resident@1a2b3c", "units": [{
        "name": "session", "kind": "session", "account": "resident",
        "command": ["python", "-m", "macf.cli", "harness", "unit", "--home", "{agent_home}",
                    "--project-dir", str(work), "--no-proxy"]}]}))
    monkeypatch.chdir(checkout)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    root, source = session_project_root(home)
    assert root == work and "session unit" in source
    set_idle_compaction(False, client_version="2.1.296", project_root=root)
    assert idle_compaction_status(root)["state"] == "off"
    assert idle_compaction_status(checkout)["state"] == "client default"   # the checkout is untouched
    path.unlink()
    find_project_root.cache_clear()   # cached per process; an earlier test may have filled it
    root, source = session_project_root(home)
    assert root == checkout and "current directory" in source



def _declare(home, units):
    from macf.pd.interface import declaration_path
    path = declaration_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "agent": "Resident@1a2b3c", "units": units}))


def test_the_equals_form_and_a_malformed_unit(tmp_path, monkeypatch):
    """--project-dir=PATH is read as argparse reads it, and a units entry that isn't an object is
    passed over rather than crashing the command (both found in review)."""
    from macf.utils.claude_settings import session_project_root
    home, work = tmp_path / "home", tmp_path / "work"
    _declare(home, ["not a unit", {"name": "session", "kind": "session", "account": "resident",
                                   "command": ["claude", f"--project-dir={work}"]}])
    monkeypatch.chdir(tmp_path)
    assert session_project_root(home) == (work, "the session unit's --project-dir")


def test_the_harness_installed_project_comes_second(tmp_path, monkeypatch):
    """With no session unit naming a project, the harness's installed project is used, and named."""
    from types import SimpleNamespace

    from macf.utils import harness
    from macf.utils.claude_settings import session_project_root
    home, installed = tmp_path / "home", tmp_path / "installed"
    _declare(home, [{"name": "broker", "kind": "service", "account": "resident", "command": ["broker"]}])
    monkeypatch.setattr(harness, "load_settings", lambda params: SimpleNamespace(project_dir=str(installed)))
    monkeypatch.chdir(tmp_path)
    assert session_project_root(home) == (installed, "the harness's installed project")

def test_status_without_settings_file(tmp_path):
    """No settings file is the client default, reported plainly rather than raised."""
    status = idle_compaction_status(tmp_path)
    assert status["state"] == "client default"
    assert status["settings_path"].endswith("settings.local.json")


@dataclass
class _Unit:
    name: str
    kind: str


@dataclass
class _Hosted:
    pid: int
    session_id: str
    cwd: str
    status: str = "idle"


class _Client:
    """Claude Code's own daemon, played by real sleep processes: ``hosted`` is what the
    readout would list, and the client's verbs are recorded and acted out."""

    def __init__(self, home):
        self.home, self.calls, self.procs, self.sessions = home, [], [], {}

    def host(self, session_id):
        import subprocess
        proc = subprocess.Popen(["/bin/sleep", "300"])
        self.procs.append(proc)
        self.sessions[session_id] = proc
        return proc

    def hosted(self):
        return [_Hosted(p.pid, sid, str(self.home)) for sid, p in self.sessions.items() if p.poll() is None]

    def __call__(self, argv):
        import subprocess
        self.calls.append(argv)
        verb, job = argv[1], argv[2]
        if len(job) != 8:            # the client takes its job id, never the full session id
            return subprocess.CompletedProcess(argv, 1, "", f"No job matching '{job}'")
        sid = next(s for s in self.sessions if s.startswith(job))
        if verb == "stop":
            self.sessions[sid].terminate()
            self.sessions[sid].wait()
        elif verb == "respawn":
            self.host(sid)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def close(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait()


def _core(home, client, marker, path=None, **options):
    """A core whose session unit declares a PATH holding a stub ``claude``, as an installed
    daemon must: its own PATH is the service manager's (#636 review)."""
    import os
    import pwd
    from macf.pd.core import Core
    from macf.pd.interface import Declaration, Unit
    if path is None:
        bindir = home.parent / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "claude"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        path = str(bindir)
    me = pwd.getpwuid(os.getuid()).pw_name
    unit = Unit(name="session", kind="session", command=["/usr/bin/touch", str(marker)], account=me,
                restart="always", liveness_interval_s=60, memory_limit_mb=64, environment={"PATH": path})
    return Core(Declaration(version=1, agent="Tester@abc123", units=[unit]), "Tester@abc123",
                placeholders={"agent_home": str(home)}, hosted=client.hosted, client=client,
                backoff_base_s=0.01, backoff_cap_s=0.05, **options)


def _settle(core, until, timeout=5.0):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        core.tick()
        if until():
            return True
        time.sleep(0.02)
    return False


def test_adopts_harness_supervisor(tmp_path):
    """MIS-0002-R66: the daemon adopts the session Claude Code's own daemon hosts in the agent
    home instead of starting a second one, and acts on it only through the client's verbs."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _Client(home)
    try:
        hosted = client.host("3d52b89a-bbbb")
        core = _core(home, client, marker)
        core.boot()
        assert core.state("session") == "running" and core.pid("session") == hosted.pid
        assert not marker.exists()                                   # no second session started
        core.restart("session", _policy(), "test restart")
        assert _settle(core, lambda: core.pid("session") not in (None, hosted.pid))
        assert [c[1] for c in client.calls] == ["stop", "respawn"]   # client verbs, never a signal
        assert core.state("session") == "running" and not marker.exists()
        core.stop("session", _policy(), "test stop")
        assert _settle(core, lambda: core.state("session") == "stopped")
        assert client.calls[-1][:2] == [str(tmp_path / "bin" / "claude"), "stop"]   # found on the declared PATH
    finally:
        client.close()


def test_two_hosted_sessions_leave_the_session_unit_unstarted(tmp_path):
    """Two hosted sessions in the home: the daemon refuses to guess, and starts nothing."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _Client(home)
    try:
        client.host("aaaa1111-x")
        client.host("bbbb2222-y")
        core = _core(home, client, marker)
        core.boot()
        assert core.state("session") == "failed" and not marker.exists() and client.calls == []
    finally:
        client.close()


def test_with_nothing_hosted_the_daemon_starts_the_session_itself(tmp_path):
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _Client(home)
    core = _core(home, client, marker)
    core.boot()
    assert _settle(core, marker.exists)
    core.shutdown("the test is over")


def _policy():
    from macf.pd.interface import Asker
    return Asker(kind="policy")


def test_decide_adopts_the_hosted_session_in_the_home(tmp_path):
    """One hosted session in the agent home is adopted, and its control acts are client verbs."""
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    hosted = [_Hosted(101, "8d48008b-aaaa", str(other)), _Hosted(202, "3d52b89a-bbbb", str(home))]

    d = decide(_Unit("session", "session"), hosted, home)

    assert (d.action, d.session_id, d.pid) == (ADOPT, "3d52b89a-bbbb", 202)
    assert client_command("restart", d.session_id) == ["claude", "respawn", "3d52b89a"]
    assert client_command("stop", d.session_id) == ["claude", "stop", "3d52b89a"]


def test_two_hosted_sessions_in_the_home_are_refused_not_guessed(tmp_path):
    hosted = [_Hosted(1, "aaaaaaaa-1", str(tmp_path)), _Hosted(2, "bbbbbbbb-2", str(tmp_path))]
    d = decide(_Unit("session", "session"), hosted, tmp_path)
    assert d.action == REFUSE and d.session_id is None
    assert "aaaaaaaa" in d.reason and "bbbbbbbb" in d.reason


def test_no_hosted_session_and_service_units_are_started(tmp_path):
    hosted = [_Hosted(1, "aaaaaaaa-1", str(tmp_path))]
    assert decide(_Unit("session", "session"), [], tmp_path).action == START
    assert decide(_Unit("broker", "service"), hosted, tmp_path).action == START


def test_a_control_act_is_never_a_signal():
    with pytest.raises(ValueError):
        client_command("kill", "aaaaaaaa-1")
    with pytest.raises(ValueError):
        client_command("stop", "")


def test_turn_state_never_claims_a_person_is_awaited():
    state, reason = unit_state("busy")
    assert state == "running" and "busy" in reason


def test_a_session_in_a_project_under_the_home_is_adopted(tmp_path):
    """Agents run sessions in project directories below their home; that is still the agent's session."""
    home = tmp_path / "agent"
    (home / "workspace" / "proj").mkdir(parents=True)
    d = decide(_Unit("session", "session"), [_Hosted(7, "abcdef12-x", str(home / "workspace" / "proj"))], home)
    assert d.action == ADOPT and d.pid == 7


def test_a_neighbouring_home_is_not_inside_this_one(tmp_path):
    """Containment is by path component: /x/agent2 is not under /x/agent, so it is never adopted."""
    home, neighbour = tmp_path / "agent", tmp_path / "agent2"
    home.mkdir()
    (neighbour / "proj").mkdir(parents=True)
    d = decide(_Unit("session", "session"), [_Hosted(8, "abcdef12-y", str(neighbour / "proj"))], home)
    assert d.action == START


def test_home_and_project_sessions_together_are_refused(tmp_path):
    home = tmp_path / "agent"
    (home / "proj").mkdir(parents=True)
    hosted = [_Hosted(1, "aaaaaaaa-1", str(home)), _Hosted(2, "bbbbbbbb-2", str(home / "proj"))]
    assert decide(_Unit("session", "session"), hosted, home).action == REFUSE


def test_attach_is_not_a_daemon_act():
    """Attaching needs a terminal; the operator's command runs it, the daemon never does."""
    with pytest.raises(ValueError):
        client_command("attach", "aaaaaaaa-1")


class _LazyStopClient(_Client):
    """Answers a stop with 0 and leaves the worker running."""

    def __call__(self, argv):
        import subprocess
        if argv[1] == "stop":
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        return super().__call__(argv)


class _SlowRespawnClient(_Client):
    """Accepts a respawn at once, but its worker is listed only one readout later."""

    def __init__(self, home):
        super().__init__(home)
        self.pending = None

    def __call__(self, argv):
        if argv[1] == "respawn":
            import subprocess
            self.calls.append(argv)
            self.pending = next(s for s in self.sessions if s.startswith(argv[2]))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return super().__call__(argv)

    def hosted(self):
        listed = super().hosted()
        if self.pending:
            self.host(self.pending)   # listed from the next readout on
            self.pending = None
        return listed


def test_a_stop_the_client_accepts_but_ignores_still_stops(tmp_path):
    """R48: an outside stop succeeds; a client that acknowledges and does nothing cannot hold it."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _LazyStopClient(home)
    try:
        hosted = client.host("3d52b89a-bbbb")
        core = _core(home, client, marker)
        core._units["session"].spec = core._units["session"].spec.model_copy(update={"stop_grace_s": 0.2})
        core.boot()
        core.stop("session", _policy(), "test stop")
        # The worker's parent reaps it, as the client's daemon reaps its own workers; until
        # then a signalled child is a zombie the probe still sees.
        assert _settle(core, lambda: hosted.poll() is not None and core.state("session") == "stopped")
    finally:
        client.close()


def test_a_respawned_worker_listed_late_is_waited_for_not_doubled(tmp_path):
    """A respawn the client accepted is waited for; the unit's own command never runs beside it."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _SlowRespawnClient(home)
    try:
        hosted = client.host("3d52b89a-bbbb")
        core = _core(home, client, marker)
        core.boot()
        core.restart("session", _policy(), "test restart")
        assert _settle(core, lambda: core.state("session") == "running" and core.pid("session") not in (None, hosted.pid))
        assert not marker.exists()
    finally:
        client.close()


def test_a_stop_during_the_respawn_wait_holds(tmp_path):
    """R48 again, in a narrower window: a stop that lands while a respawn is awaited ends
    with the unit stopped and the client's worker gone, not adopted and running (#636 review)."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _SlowRespawnClient(home)
    try:
        hosted = client.host("3d52b89a-bbbb")
        core = _core(home, client, marker)
        core.boot()
        core.restart("session", _policy(), "test restart")
        assert _settle(core, lambda: core._units["session"].awaiting_respawn is not None)
        core.stop("session", _policy(), "stopped mid-respawn")
        workers = lambda: [p for p in client.procs if p is not hosted and p.poll() is None]
        assert _settle(core, lambda: core.state("session") == "stopped" and not workers()
                       and core._units["session"].awaiting_respawn is None)
        assert not marker.exists()
    finally:
        client.close()


def test_a_client_not_on_the_declared_path_is_named_and_nothing_is_touched(tmp_path):
    """Under a service manager's PATH the client may not be found. That is not a refused
    stop: the unit fails with the binary and the PATH named, and the hosted session is left
    alone, neither signalled nor doubled (#636 review)."""
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    client = _Client(home)
    try:
        hosted = client.host("3d52b89a-bbbb")
        core = _core(home, client, marker, path=str(empty))
        core.boot()
        assert core.state("session") == "failed"
        assert client.calls == [] and hosted.poll() is None and not marker.exists()
        from macf.agent_events_log import read_events
        reason = next(e["data"]["reason"] for e in read_events(reverse=True) if e["event"] == "pd_unit_state")
        assert "claude is not on the session unit's declared PATH" in reason and str(empty) in reason
    finally:
        client.close()


def test_channel_first(tmp_path, isolated_events_log, monkeypatch, capsys):
    """MIS-0002-R104: with the MacEff channel attached, mail that arrives (a wake) and the
    daemon's own notice both go out on the channel as records naming their sources, each
    delivery is recorded as by channel, and the keystroke fallback types nothing into an
    idle, empty box, however long past its grace both have been owed. A notice the channel's
    record would refuse is never recorded as delivered."""
    import socket

    from macf.agent_events_log import read_events
    from macf.channels.maceff_channel import TAKES, parse_record
    from macf.pd import notifier as nt
    from macf.pd import wake as wk

    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)     # the box comes from the home
    monkeypatch.delenv("MACF_AMAIL_HANDOFF", raising=False)
    home = tmp_path / "agent"
    box = home / "amail" / "pickup"
    box.mkdir(parents=True)
    clock = [1000.0]
    n = nt.Notifier(home, {"amail": "agent", "pd_limit_exceeded": "agent"}, clock=lambda: clock[0])
    n.boot()
    typed = []

    class IdlePane:
        def capture(self):
            return "\n".join(["─" * 60, "❯ ", "─" * 60, "  ? for shortcuts"])

        def type(self, text):
            typed.append(text)
            return True

        def enter(self):
            return True

    n.waker = wk.Waker(IdlePane(), record_keys=lambda text, kind: None, append=lambda e, d: True)
    ours, theirs = socket.socketpair()
    theirs.settimeout(2)
    n.attach(ours, takes=TAKES)
    (box / "1791990000-msg-1791990000-aaaaaaaaaaaa.amsg").write_text("never read by the notifier")
    n.poll()                                                    # the wake
    assert n.raise_notice("pd_limit_exceeded", "limit-worker-1")   # the notice
    clock[0] += nt.CHANNEL_GRACE_S + 3600
    assert not n.wake() and typed == [], "a wake was typed while the channel was attached"
    assert n.flush() == 2 and not n.owed

    data = b""
    while data.count(b"\n") < 2:
        chunk = theirs.recv(65536)
        assert chunk, "the channel closed before both records arrived"
        data += chunk
    records = [parse_record(line) for line in data.decode().splitlines()]
    assert sorted(r.source for r in records) == ["amail", "pd_limit_exceeded"]
    delivered = [e["data"] for e in read_events(reverse=False, scope="all") if e.get("event") == nt.EVENT_DELIVERED]
    assert sorted(d["source"] for d in delivered) == ["amail", "pd_limit_exceeded"]
    assert {d["via"] for d in delivered} == {"channel"}

    # A notice the channel would refuse, such as one whose id holds a "+", is refused where
    # it's raised, and said. Owed, it would be written, logged delivered, and dropped by the
    # channel, so the log would hold a delivery that never happened (#734).
    assert not n.raise_notice("pd_limit_exceeded", "worker:2026-10-14T13:00:00+00:00")
    assert not n.owed and n.flush() == 0
    assert "pd_limit_exceeded" in capsys.readouterr().err
    refused = [e for e in read_events(reverse=False, scope="all")
               if (e.get("data") or {}).get("arrival_id") == "worker:2026-10-14T13:00:00+00:00"]
    assert refused == []
    n.detach(ours)
    theirs.close()


def test_waiting_reported(tmp_path, monkeypatch):
    """MIS-0002-R21 (pd_MUST_report_waiting_on_person) for Claude Code's session unit, on the
    path the session takes: from the session's environment the transcript monitor starts the
    unit's beat, and each beat says when the event log shows that the monitor's own session's
    newest deciding event is a permission request. Any progress after the request ends the
    wait: the tool running, or a prompt, which is how a denial with a reply arrives."""
    import os
    import time as _time
    from macf import permission_watch as pw
    from macf.agent_events_log import append_event
    from macf.pd import liveness as lv
    from macf.transcript_monitor import daemon

    # The reading rule.
    log = []

    def ev(name, t, sid, **data):
        return {"event": name, "timestamp": t, "data": data, "hook_input": {"session_id": sid,
                "tool_input": {"command": "gh pr merge 1 --token s3cret"}}}

    read = lambda: pw.waiting(sorted(log, key=lambda e: e["timestamp"], reverse=True))
    dialogs = pw.SessionDialogs("s1", read=read)
    assert dialogs() is None                                         # nothing asked yet
    log.append(ev("permission_requested", 100.0, "s2", tool_name="Bash", timestamp=100.0))
    assert dialogs() is None                                         # another session's dialog
    log.append(ev("permission_requested", 200.0, "s1", tool_name="Bash", timestamp=200.0))
    said = dialogs()
    assert said.startswith("a permission dialog for Bash, open since ")
    assert _time.strftime("%H:%M", _time.localtime(200.0)) in said and "s3cret" not in said

    def broken():
        raise OSError("log unreadable")
    dialogs._read = broken
    assert dialogs() == said                                         # a read error keeps the wait
    dialogs._read = read
    log.append(ev("tool_call_started", 260.0, "s1"))
    assert dialogs() is None                                         # answered: the tool ran
    log.append(ev("permission_requested", 300.0, "s1", tool_name="Edit", timestamp=300.0))
    assert dialogs().startswith("a permission dialog for Edit")
    log.append(ev("dev_drv_started", 310.0, "s1"))
    assert dialogs() is None                                         # a prompt: denied with a reply

    # The beat, as the monitor starts it from the session's environment, reading the log the
    # hooks write, for its own transcript's session.
    home = tmp_path / "agent"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000\n")
    for k, v in {lv.ENV_HOME: str(home), lv.ENV_SESSION_UNIT: "session",
                 lv.ENV_SESSION_INTERVAL: "0.05", lv.ENV_SESSION_PID: str(os.getppid())}.items():
        monkeypatch.setenv(k, v)
    beats = []
    monkeypatch.setattr(lv, "append_event", lambda n, d: beats.append(d) or True)
    monkeypatch.setattr(daemon, "append_event", lambda *a, **k: True)
    monkeypatch.setattr(daemon, "find_monitors", list)               # no older monitor
    monkeypatch.setattr(daemon.signal, "signal", lambda *a: None)    # the suite keeps its handlers

    def dialog(sid, tool):                                           # as the PermissionRequest hook records it
        append_event("permission_requested", {"session_id": sid, "tool_name": tool, "timestamp": _time.time()},
                     hook_input={"session_id": sid, "tool_name": tool})

    def waiting_on(n):
        deadline = _time.monotonic() + 2
        while len(beats) <= n and _time.monotonic() < deadline:
            _time.sleep(0.01)
        return beats[n].get("waiting_on") if len(beats) > n else "no beat"

    beat_said = []

    def fake_run(self, start_from_end=True):
        dialog("s1", "Bash")                                         # this session's dialog,
        dialog("s2", "Edit")                                         # and a newer one elsewhere
        self.on_pass()
        beat_said.append(waiting_on(0))
        append_event("tool_call_started", {"session_id": "s1"})      # answered: the tool ran
        self.on_pass()
        beat_said.append(waiting_on(1))

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    transcript = tmp_path / "s1.jsonl"                               # named for its session
    transcript.write_text("")
    daemon.run_monitor(transcript, 0.01, owner=0)
    assert beat_said[0].startswith("a permission dialog for Bash, open since "), beat_said
    assert beat_said[1] is None, beat_said
    assert all(b["pid"] == os.getppid() and b["unit"] == "session" for b in beats)

    # And for a session the daemon adopted from the client's own daemon (R66), which writes no
    # liveness: the core reads its dialogs from the event log by its session id itself.
    _adopted_session_waiting_is_reported(tmp_path, monkeypatch)


def _adopted_session_waiting_is_reported(tmp_path, monkeypatch):
    from macf.pd import core as core_module
    monkeypatch.setattr(core_module, "DIALOG_POLL_S", 0.0)
    home, marker = tmp_path / "adopted_home", tmp_path / "adopted_started_by_pd"
    home.mkdir()
    client = _Client(home)
    asked, open_dialog = [], {"now": None}

    def dialogs(session_id):
        asked.append(session_id)
        return lambda: open_dialog["now"]
    try:
        client.host("7a1c22d0-cccc")
        core = _core(home, client, marker)
        core._dialogs = dialogs
        core.boot()
        assert core.state("session") == "running"
        open_dialog["now"] = "a permission dialog for Bash, open since 21:07"
        assert _settle(core, lambda: core.state("session") == "waiting_on_a_person")
        assert asked == ["7a1c22d0-cccc"]                   # read by the adopted session's own id
        open_dialog["now"] = None
        assert _settle(core, lambda: core.state("session") == "running")
        assert not marker.exists()                          # still the adopted session, never a second
    finally:
        client.close()



def test_a_failed_login_reaches_the_beat(tmp_path, monkeypatch):
    """MIS-0002-R19 (auth_failure_MUST_read_failed) on the session's own path: the monitor run_monitor
    starts reads each transcript line through its detectors, and the beat it starts from the
    session's environment says the login failed until a reply shows a request went through."""
    import os
    import time as _time
    from macf.pd import liveness as lv
    from macf.transcript_monitor import daemon

    home = tmp_path / "agent"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000\n")
    for k, v in {lv.ENV_HOME: str(home), lv.ENV_SESSION_UNIT: "session",
                 lv.ENV_SESSION_INTERVAL: "0.05", lv.ENV_SESSION_PID: str(os.getppid())}.items():
        monkeypatch.setenv(k, v)
    beats = []
    monkeypatch.setattr(lv, "append_event", lambda n, d: beats.append(d) or True)
    monkeypatch.setattr(daemon, "append_event", lambda *a, **k: True)
    monkeypatch.setattr(daemon, "find_monitors", list)
    monkeypatch.setattr(daemon.signal, "signal", lambda *a: None)

    def beat(n):
        deadline = _time.monotonic() + 2
        while len(beats) <= n and _time.monotonic() < deadline:
            _time.sleep(0.01)
        return beats[n].get("auth_failed") if len(beats) > n else "no beat"

    expired = {"type": "assistant", "isApiErrorMessage": True, "error": "authentication_failed",
               "message": {"role": "assistant", "model": "<synthetic>",
                           "content": [{"type": "text", "text": "Login expired"}]}}
    reply = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}}
    said = []

    def fake_run(self, start_from_end=True):
        self._process_line(json.dumps(expired))
        self.on_pass()
        said.append(beat(0))
        self._process_line(json.dumps(reply))
        self.on_pass()
        said.append(beat(1))

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    daemon.run_monitor(transcript, 0.01, owner=0)
    assert said == ["Login expired", None], said


# ---------------------------------------------------------------------------
# A hand-started client: the core never starts a session unit beside one (persistent_layer 6.2)
# ---------------------------------------------------------------------------

def _unit_reasons(unit="session"):
    from macf.agent_events_log import get_log_path
    rows = [json.loads(line) for line in get_log_path().read_text().splitlines() if line.strip()]
    return [r["data"].get("reason", "") for r in rows
            if r.get("event") == "pd_unit_state" and r["data"].get("unit") == unit]


class _Terminal:
    """Claude Code clients started by hand: pid -> working directory, none below the daemon."""

    def __init__(self, clients):
        self.clients = dict(clients)
        self.asked = []

    def __call__(self, directory):
        from pathlib import Path
        self.asked.append(Path(directory))
        return sorted(p for p, cwd in self.clients.items() if Path(cwd).resolve() == Path(directory).resolve())


def test_the_core_holds_the_session_unit_beside_a_hand_started_client_and_starts_it_after(tmp_path, monkeypatch):
    """No start, no restart and no daemon start puts a session unit beside a plain claude -c
    in the project directory; once that client has gone, the next look starts it."""
    monkeypatch.delenv("MACEFF_PROJECT_DIR", raising=False)
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    terminal = _Terminal({4242: home, 5151: tmp_path})       # one here, one elsewhere
    now = [0.0]
    core = _core(home, _Client(home), marker, clients=terminal, ancestors=lambda pid: {pid, 1},
                 clock=lambda: now[0])
    core.boot()
    assert core.state("session") == "failed" and core.pid("session") is None and not marker.exists()
    reason = _unit_reasons()[-1]
    assert "pid 4242" in reason and "5151" not in reason and "harness cutover" in reason
    assert terminal.asked[-1] == home
    now[0] += 1.0
    core.tick()
    assert not marker.exists(), "still held while the client runs"
    del terminal.clients[4242]                                 # the person quit it
    now[0] += 5.0
    assert _settle(core, marker.exists), "started on the next look once the client is gone"
    core.shutdown("the test is over")


def test_the_units_own_adopted_process_is_not_a_hand_started_client(tmp_path, monkeypatch):
    """A client below a process this unit ran or adopted, still the one recorded, is the unit's
    own: a restart is not held by it. One below a recorded process whose start no longer
    matches is someone else's."""
    monkeypatch.delenv("MACEFF_PROJECT_DIR", raising=False)
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    terminal = _Terminal({4242: home})
    live = {(777, "s777")}
    core = _core(home, _Client(home), marker, clients=terminal,
                 ancestors=lambda pid: {pid, 777, 1} if pid == 4242 else {pid, 1},
                 probe=lambda pid, start: (pid, start) in live)
    core._units["session"].own.append((777, "s777"))         # adopted earlier, by pid and start
    core.boot()
    assert _settle(core, marker.exists), "its own adopted process doesn't hold it"
    core.shutdown("the test is over")
    marker.unlink()
    live.clear()                                               # 777 is now another process
    core = _core(home, _Client(home), marker, clients=terminal,
                 ancestors=lambda pid: {pid, 777, 1} if pid == 4242 else {pid, 1},
                 probe=lambda pid, start: (pid, start) in live)
    core._units["session"].own.append((777, "s777"))
    core.boot()
    assert core.state("session") == "failed" and not marker.exists()


def test_a_hosted_session_the_core_adopts_is_recorded_as_its_own(tmp_path):
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    client = _Client(home)
    try:
        hosted = client.host("3d52b89a-cccc")
        core = _core(home, client, marker)
        core.boot()
        assert [pid for pid, _ in core._units["session"].own] == [hosted.pid]
    finally:
        client.close()


def test_a_stop_ends_the_hold(tmp_path, monkeypatch):
    monkeypatch.delenv("MACEFF_PROJECT_DIR", raising=False)
    home, marker = tmp_path / "home", tmp_path / "started_by_pd"
    home.mkdir()
    terminal = _Terminal({4242: home})
    core = _core(home, _Client(home), marker, clients=terminal, ancestors=lambda pid: {pid, 1})
    core.boot()
    core.stop("session", _policy(), "test stop")
    del terminal.clients[4242]
    core.tick()
    assert core.state("session") == "stopped" and not marker.exists()
