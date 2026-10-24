"""Tests for the tmux-backed named session + `auto-restart send-keys`.

Covers session-id pinning, tmux session naming/sanitization, the tmux-wrap
command form, registry-based target resolution, and the send-keys tmux
invocation (literal text + separate Enter).
"""

import json
import re

import pytest

from macf import supervisor as sup

SUP_CMD = ["python3", "-m", "macf.supervisor", "_run_loop",
           "--name", "humphry_blackbox", "--delay", "5",
           "--session-id", "59ae6fca-58d3-4812-92fa-27932564b231",
           "--", "/home/u/launch.sh"]


# --- session id + tmux naming ---------------------------------------------

def test_new_session_id_is_uuid():
    sid = sup._new_session_id()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sid)


def test_short_id_matches_breadcrumb_convention():
    # The tmux suffix and the breadcrumb s_<id> both take the first 8 hex.
    sid = "59ae6fca-58d3-4812-92fa-27932564b231"
    assert sid[:8] == "59ae6fca"


@pytest.mark.parametrize("raw,expected", [
    ("humphry_blackbox_59ae6fca", "humphry_blackbox_59ae6fca"),
    ("launch_x.sh_59ae6fca", "launch_x_sh_59ae6fca"),   # '.' -> '_'
    ("a:b 59ae6fca", "a_b_59ae6fca"),                   # ':' and ' ' -> '_'
])
def test_sanitize_tmux_name(raw, expected):
    assert sup._sanitize_tmux_name(raw) == expected


def test_sanitize_tmux_name_empty():
    assert sup._sanitize_tmux_name("") == "session"
    assert sup._sanitize_tmux_name("...") == "___"  # not empty -> kept as underscores


# --- tmux wrap form -------------------------------------------------------

def test_tmux_wrap_passes_single_shell_string():
    argv = sup._tmux_wrap("humphry_blackbox_59ae6fca", SUP_CMD)
    assert argv[:5] == ["tmux", "new-session", "-A", "-s", "humphry_blackbox_59ae6fca"]
    # The supervisor command collapses into exactly ONE shell-safe arg.
    assert len(argv) == 6
    assert argv[5] == sup._shell_command_string(SUP_CMD)
    # round-trips: shlex.split of that arg reproduces the original argv
    import shlex
    assert shlex.split(argv[5]) == SUP_CMD


# --- registry resolution --------------------------------------------------

def _seed_registry(tmp_path, monkeypatch, entries):
    monkeypatch.setattr(sup, "REGISTRY_DIR", tmp_path)
    for data in entries:
        data = {"status": "running", **data}
        (tmp_path / f"{data['supervisor_pid']}.json").write_text(json.dumps(data))
    # treat every seeded supervisor pid as alive unless overridden
    alive = {e["supervisor_pid"] for e in entries if e.get("_alive", True)}
    monkeypatch.setattr(sup, "_is_alive", lambda pid: pid in alive)
    # A registry entry describes a live supervisor only if it SAYS it is
    # running, its pid is alive, AND that pid is still a supervisor. The first
    # and third were added after a stopped entry with a recycled pid could be
    # matched; seeding them here keeps the fixture modelling a live supervisor
    # rather than a file that merely exists.
    monkeypatch.setattr(sup, "_is_supervisor_process", lambda pid: pid in alive)


def test_find_supervisor_by_name(tmp_path, monkeypatch):
    _seed_registry(tmp_path, monkeypatch, [
        {"supervisor_pid": 100, "name": "humphry_blackbox",
         "tmux_session": "humphry_blackbox_59ae6fca", "created": 1.0},
    ])
    found = sup._find_supervisor("humphry_blackbox")
    assert found and found["supervisor_pid"] == 100


def test_find_supervisor_by_pid(tmp_path, monkeypatch):
    _seed_registry(tmp_path, monkeypatch, [
        {"supervisor_pid": 100, "name": "humphry_blackbox", "created": 1.0},
    ])
    assert sup._find_supervisor("100")["supervisor_pid"] == 100


def test_find_supervisor_skips_dead(tmp_path, monkeypatch):
    _seed_registry(tmp_path, monkeypatch, [
        {"supervisor_pid": 100, "name": "x", "created": 1.0, "_alive": False},
    ])
    assert sup._find_supervisor("x") is None


def test_find_supervisor_prefers_most_recent_name_match(tmp_path, monkeypatch):
    _seed_registry(tmp_path, monkeypatch, [
        {"supervisor_pid": 100, "name": "dup", "created": 1.0, "tmux_session": "old"},
        {"supervisor_pid": 200, "name": "dup", "created": 5.0, "tmux_session": "new"},
    ])
    assert sup._find_supervisor("dup")["tmux_session"] == "new"


# --- send_keys ------------------------------------------------------------

def test_send_keys_requires_tmux(monkeypatch, capsys):
    monkeypatch.setattr(sup, "_tmux_available", lambda: False)
    assert sup.send_keys("x", ["/compact"]) == 1
    assert "tmux not found" in capsys.readouterr().err


def test_send_keys_no_match(monkeypatch, capsys):
    monkeypatch.setattr(sup, "_tmux_available", lambda: True)
    monkeypatch.setattr(sup, "_find_supervisor", lambda t: None)
    assert sup.send_keys("nope", ["/compact"]) == 1
    assert "No running supervised process" in capsys.readouterr().err


def test_send_keys_no_tmux_session_recorded(monkeypatch, capsys):
    monkeypatch.setattr(sup, "_tmux_available", lambda: True)
    monkeypatch.setattr(sup, "_find_supervisor",
                        lambda t: {"name": "x", "tmux_session": None})
    assert sup.send_keys("x", ["/compact"]) == 1
    assert "without a tmux session" in capsys.readouterr().err


def test_send_keys_happy_path_literal_then_enter(monkeypatch):
    monkeypatch.setattr(sup, "_tmux_available", lambda: True)
    monkeypatch.setattr(sup, "_find_supervisor",
                        lambda t: {"name": "x", "tmux_session": "x_59ae6fca"})
    calls = []

    class _R:
        returncode = 0

    def fake_run(argv, *a, **k):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(sup.subprocess, "run", fake_run)
    rc = sup.send_keys("x", ["/compact"])
    assert rc == 0
    # The patch catches every subprocess call, the breadcrumb helper's git fallback
    # included, so only tmux's are the behavior under test (#793).
    tmux = [c for c in calls if c[:1] == ["tmux"]]
    # First call: literal text with -l and -- guard; second: a bare Enter.
    assert tmux == [["tmux", "send-keys", "-t", "x_59ae6fca", "-l", "--", "/compact"],
                    ["tmux", "send-keys", "-t", "x_59ae6fca", "Enter"]]


def test_send_keys_no_enter(monkeypatch):
    monkeypatch.setattr(sup, "_tmux_available", lambda: True)
    monkeypatch.setattr(sup, "_find_supervisor",
                        lambda t: {"name": "x", "tmux_session": "x_59ae6fca"})
    calls = []
    monkeypatch.setattr(sup.subprocess, "run",
                        lambda argv, *a, **k: calls.append(argv) or type("R", (), {"returncode": 0})())
    rc = sup.send_keys("x", ["hello world"], enter=False)
    assert rc == 0
    tmux = [c for c in calls if c[:1] == ["tmux"]]   # as above (#793)
    assert len(tmux) == 1  # no Enter press
    assert tmux[0][-3:] == ["-l", "--", "hello world"]


def _tmux_server(tmp_path, monkeypatch):
    """A private tmux server for one test: its own TMUX_TMPDIR, killed afterwards. The
    socket directory is a short one under /tmp, since pytest's tmp_path makes a socket path
    longer than macOS allows (104 characters), and tmux would not start there."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")
    sock = tempfile.mkdtemp(prefix="tmux-", dir="/tmp")
    monkeypatch.setenv("TMUX_TMPDIR", sock)
    import atexit
    atexit.register(shutil.rmtree, sock, True)
    monkeypatch.delenv("TMUX", raising=False)
    return subprocess


def test_send_keys_reaches_the_supervisor_pane_after_a_split(tmp_path, monkeypatch):
    """A split beside the agent takes focus, and -t <session> would type into it. The keys
    must still reach the pane whose process is the supervisor (an inject into a watch pane
    left an agent unable to compact)."""
    import time
    sp = _tmux_server(tmp_path, monkeypatch)
    out0, out1 = tmp_path / "agent.txt", tmp_path / "watch.txt"
    try:
        r = sp.run(["tmux", "new-session", "-d", "-P", "-F", "#{pane_pid}", "-s", "agent",
                    f"cat > {out0}"], capture_output=True, text=True, check=True)
        supervisor_pid = int(r.stdout.strip())
        sp.run(["tmux", "split-window", "-t", "agent", f"cat > {out1}"], check=True)
        sp.run(["tmux", "select-pane", "-t", "agent:0.1"], check=True)
        monkeypatch.setattr(sup, "_find_supervisor", lambda t: {
            "name": "agent", "tmux_session": "agent", "supervisor_pid": supervisor_pid})
        assert sup.send_keys("agent", ["/compact"]) == 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "/compact" not in (out0.read_text() if out0.exists() else ""):
            time.sleep(0.05)
        assert out0.read_text().strip() == "/compact"
        assert (out1.read_text() if out1.exists() else "") == ""
        assert "/compact" in sup.capture_pane("agent")
        # press_enter is what the compaction follow-up uses after typing its prompt.
        assert sup.press_enter("agent") == 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and out0.read_text().count("\n") < 2:
            time.sleep(0.05)
        assert out0.read_text() == "/compact\n\n", "the Enter lands in the supervisor's pane"
        assert (out1.read_text() if out1.exists() else "") == ""
    finally:
        sp.run(["tmux", "kill-server"], capture_output=True)


def test_pane_of_falls_back_to_the_session_when_no_pane_is_the_supervisor(tmp_path, monkeypatch):
    sp = _tmux_server(tmp_path, monkeypatch)
    try:
        sp.run(["tmux", "new-session", "-d", "-s", "agent", "sleep 30"], check=True)
        data = {"name": "agent", "tmux_session": "agent", "supervisor_pid": 999999999}
        assert sup._pane_of(data) == "agent"
        assert sup._pane_of({"tmux_session": "%7"}) == "%7"
    finally:
        sp.run(["tmux", "kill-server"], capture_output=True)


# --- session spec resolution (the resume-latest continuity fix) -----------

def test_resolve_spec_none_does_not_pin():
    assert sup._resolve_session_spec(None) is None
    assert sup._resolve_session_spec("") is None


def test_resolve_spec_new_mints_uuid():
    sid = sup._resolve_session_spec("new")
    assert sup._UUID_RE.match(sid)


def test_resolve_spec_explicit_uuid_passthrough():
    u = "59ae6fca-58d3-4812-92fa-27932564b231"
    assert sup._resolve_session_spec(u) == u


def test_resolve_spec_latest_resumes_existing(monkeypatch):
    # 'latest' must return the most-recent transcript id (so the launch RESUMES
    # the user's current conversation instead of starting fresh).
    monkeypatch.setattr(sup, "_latest_session_id",
                        lambda: "59ae6fca-58d3-4812-92fa-27932564b231")
    assert sup._resolve_session_spec("latest") == "59ae6fca-58d3-4812-92fa-27932564b231"


def test_resolve_spec_latest_falls_back_to_new(monkeypatch):
    monkeypatch.setattr(sup, "_latest_session_id", lambda: None)
    sid = sup._resolve_session_spec("latest")
    assert sup._UUID_RE.match(sid)  # minted fresh when no transcript exists


def test_latest_session_id_picks_newest(tmp_path, monkeypatch):
    import os
    proj = tmp_path / ".claude" / "projects" / "encoded-proj"
    proj.mkdir(parents=True)
    older = proj / "11111111-1111-1111-1111-111111111111.jsonl"
    newer = proj / "22222222-2222-2222-2222-222222222222.jsonl"
    older.write_text("{}")
    newer.write_text("{}")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    # a non-uuid file must be ignored
    (proj / "notes.jsonl").write_text("{}")
    os.utime(proj / "notes.jsonl", (3000, 3000))
    monkeypatch.setattr(sup.Path, "home", staticmethod(lambda: tmp_path))
    assert sup._latest_session_id() == "22222222-2222-2222-2222-222222222222"


def test_latest_session_id_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(sup.Path, "home", staticmethod(lambda: tmp_path))
    assert sup._latest_session_id() is None
