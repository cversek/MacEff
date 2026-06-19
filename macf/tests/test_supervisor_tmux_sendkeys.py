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
        (tmp_path / f"{data['supervisor_pid']}.json").write_text(json.dumps(data))
    # treat every seeded supervisor pid as alive unless overridden
    alive = {e["supervisor_pid"] for e in entries if e.get("_alive", True)}
    monkeypatch.setattr(sup, "_is_alive", lambda pid: pid in alive)


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
    # First call: literal text with -l and -- guard; second: a bare Enter.
    assert calls[0] == ["tmux", "send-keys", "-t", "x_59ae6fca", "-l", "--", "/compact"]
    assert calls[1] == ["tmux", "send-keys", "-t", "x_59ae6fca", "Enter"]


def test_send_keys_no_enter(monkeypatch):
    monkeypatch.setattr(sup, "_tmux_available", lambda: True)
    monkeypatch.setattr(sup, "_find_supervisor",
                        lambda t: {"name": "x", "tmux_session": "x_59ae6fca"})
    calls = []
    monkeypatch.setattr(sup.subprocess, "run",
                        lambda argv, *a, **k: calls.append(argv) or type("R", (), {"returncode": 0})())
    rc = sup.send_keys("x", ["hello world"], enter=False)
    assert rc == 0
    assert len(calls) == 1  # no Enter press
    assert calls[0][-3:] == ["-l", "--", "hello world"]
