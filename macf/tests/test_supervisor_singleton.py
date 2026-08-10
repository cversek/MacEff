"""Singleton pre-flight — fork prevention for supervisor birth (cversek/MacEff#210).

The FORK INCIDENT: a restart kick + supervisor relaunch minted CONCURRENT
instances instead of rejoining — three `claude -c` clients under one calling
card, two of them unattended, all writing one task store. The fork mints through
whichever launch door is unguarded, and there are three (launch_in_terminal, a
systemd unit invoking the module directly, a manual launch). They converge at
run_loop, so run_loop is where the guard has to live.

The seams `_is_alive` (os.kill) and `_is_supervisor_process` (ps) are the two
places "the registry says running" meets "the process table agrees"; every test
here monkeypatches them so liveness is deterministic rather than dependent on
real pids.
"""
import importlib


def _reload_supervisor(monkeypatch, tmp_path):
    """Reload the module with a private, empty registry dir (REGISTRY_DIR is
    resolved at import time from XDG_RUNTIME_DIR)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    import macf.supervisor as s
    return importlib.reload(s)


def _make_live(monkeypatch, s):
    """Make every registered entry read as a genuinely live supervisor."""
    monkeypatch.setattr(s, "_is_alive", lambda pid: True)
    monkeypatch.setattr(s, "_is_supervisor_process", lambda pid: True)
    monkeypatch.setattr(s, "_notify_telegram", lambda *a, **k: None)


def _register(s, pid, name, **extra):
    data = {"supervisor_pid": pid, "name": name, "status": "running",
            "created": float(pid), "restart_count": 0}
    data.update(extra)
    s._write_registry(pid, data)


# ---- find_live_supervisor_by_name (the guard's eyes) ----------------------

def test_finds_live_supervisor_by_name(monkeypatch, tmp_path):
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 111, "claude")
    assert s.find_live_supervisor_by_name("claude")["supervisor_pid"] == 111


def test_name_scoped_distinct_names_never_collide(monkeypatch, tmp_path):
    """A different --name is a different service, not a fork."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 111, "claude")
    assert s.find_live_supervisor_by_name("manny") is None


def test_excludes_self(monkeypatch, tmp_path):
    """A supervisor checking for a *pre-existing* twin must not match itself."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 222, "claude")
    assert s.find_live_supervisor_by_name("claude", exclude_pid=222) is None


def test_ignores_dead_pid(monkeypatch, tmp_path):
    """A 'running' entry whose pid is dead is not a live supervisor."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    monkeypatch.setattr(s, "_is_alive", lambda pid: False)
    monkeypatch.setattr(s, "_is_supervisor_process", lambda pid: True)
    _register(s, 333, "claude")
    assert s.find_live_supervisor_by_name("claude") is None


def test_ignores_recycled_pid(monkeypatch, tmp_path):
    """Alive pid but no longer a supervisor (recycled) → not live."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    monkeypatch.setattr(s, "_is_alive", lambda pid: True)
    monkeypatch.setattr(s, "_is_supervisor_process", lambda pid: False)
    _register(s, 444, "claude")
    assert s.find_live_supervisor_by_name("claude") is None


def test_returns_most_recent_on_multiple(monkeypatch, tmp_path):
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 10, "claude", created=1.0)
    _register(s, 20, "claude", created=2.0)
    assert s.find_live_supervisor_by_name("claude")["supervisor_pid"] == 20


# ---- run_loop: the authoritative chokepoint -------------------------------

def test_run_loop_refuses_when_name_already_live(monkeypatch, tmp_path, capsys):
    """run_loop is the door systemd also passes through; it must refuse to
    become a second live supervisor and return non-zero WITHOUT registering."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 99999, "claude", restart_count=3, tmux_session="claude_abc")

    rc = s.run_loop(["true"], name="claude", force=False)

    assert rc == 1
    err = capsys.readouterr().err
    assert "REFUSING TO START" in err
    assert "99999" in err
    assert "auto-restart restart 99999" in err  # names the sanctioned rejoin
    assert "--force" in err                       # names the override
    # No second supervisor for the name was registered.
    assert s.find_live_supervisor_by_name("claude")["supervisor_pid"] == 99999


def test_run_loop_refusal_returns_nonzero_for_systemd(monkeypatch, tmp_path, capsys):
    """The non-zero return is what stops a systemd unit reporting active with a
    fork underneath — mirrors the _unlaunchable_reason contract."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 7777, "claude")
    assert s.run_loop(["true"], name="claude") == 1


# ---- launch_in_terminal: friendly early refusal ---------------------------

def test_launch_in_terminal_refuses_before_opening_terminal(monkeypatch, tmp_path, capsys):
    """The early copy of the guard must refuse before any terminal is opened,
    so the interactive user never gets an orphan window."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    opened = []
    monkeypatch.setattr(s.subprocess, "Popen", lambda *a, **k: opened.append(a))
    _register(s, 4242, "claude")

    rc = s.launch_in_terminal(["claude", "-c"], name="claude", force=False)

    assert rc == 1
    assert opened == []  # no terminal emulator was spawned
    assert "REFUSING TO START" in capsys.readouterr().err


# ---- registry hygiene: liveness-checked list output -----------------------

def test_list_processes_cleans_recycled_pid_entry(monkeypatch, tmp_path, capsys):
    """A 'running' entry whose pid is alive but no longer a supervisor must be
    treated as stale, not listed as running (GH#210 registry hygiene)."""
    s = _reload_supervisor(monkeypatch, tmp_path)
    monkeypatch.setattr(s, "_is_alive", lambda pid: True)
    monkeypatch.setattr(s, "_is_supervisor_process", lambda pid: False)
    _register(s, 5555, "claude")

    s.list_processes(show_all=False)

    out = capsys.readouterr().out
    assert "No running processes" in out
    assert not s._registry_file(5555).exists()  # cleaned


def test_list_processes_shows_genuine_live_supervisor(monkeypatch, tmp_path, capsys):
    s = _reload_supervisor(monkeypatch, tmp_path)
    _make_live(monkeypatch, s)
    _register(s, 6060, "claude", command=["claude", "-c"])

    s.list_processes(show_all=False)

    out = capsys.readouterr().out
    assert "6060" in out
    assert "claude" in out
