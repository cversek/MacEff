"""The Claude Code harness adapter: the client's own compactions and its own supervisor.

MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction): where the harness can
compact an idle session on its own, the adapter turns that off unless the declaration
keeps it. Claude Code compacts a session about 54 minutes after its last request once
the context passes a threshold, and from 2.1.290 the settings key ``idleCompaction``
set to false stops that alone, leaving compaction at the context limit on.

MIS-0002-R66 (pd_MUST_adopt_harness_supervisor): a session the client's background
daemon already hosts is adopted, never supervised a second time, and acted on through
the client's own verbs.
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


def test_turning_it_back_on_removes_the_key(project):
    """`true` does not turn idle compaction on in the client, so on means the key is gone."""
    set_idle_compaction(False, client_version="2.1.296", project_root=project)
    set_idle_compaction(True, client_version="2.1.296", project_root=project)
    assert "idleCompaction" not in _settings(project)
    assert idle_compaction_status(project)["state"] == "client default"


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


def _core(home, client, marker):
    import os
    import pwd
    from macf.pd.core import Core
    from macf.pd.interface import Declaration, Unit
    me = pwd.getpwuid(os.getuid()).pw_name
    unit = Unit(name="session", kind="session", command=["/usr/bin/touch", str(marker)], account=me,
                restart="always", liveness_interval_s=60, memory_limit_mb=64)
    return Core(Declaration(version=1, agent="Tester@abc123", units=[unit]), "Tester@abc123",
                placeholders={"agent_home": str(home)}, hosted=client.hosted, client=client,
                backoff_base_s=0.01, backoff_cap_s=0.05)


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
        assert client.calls[-1][:2] == ["claude", "stop"]
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
