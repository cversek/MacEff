"""The capture unit's disclaimed re-spawn on macOS (MIS-0008 R14): what it hands the child, and how it ends.

The spawn itself is faked, so these run anywhere."""
import os
import signal
import sys

import pytest

from macf.voice.capture import disclaim


@pytest.fixture
def fake_spawn(monkeypatch):
    seen = {}
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    for sig in saved:
        signal.signal(sig, signal.SIG_DFL)

    def spawn(argv, env):
        seen.update(argv=argv, env=env, sigterm=signal.getsignal(signal.SIGTERM))
        return 4242

    monkeypatch.setattr(disclaim, "_spawn_disclaimed", spawn)
    yield seen
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_the_child_is_told_it_is_the_child_and_whose_pid_it_speaks_for(fake_spawn, monkeypatch):
    monkeypatch.setattr(os, "waitpid", lambda pid, flags: (pid, 0))
    assert disclaim.run_disclaimed(["/bin/true"]) == 0
    env = fake_spawn["env"]
    assert env[disclaim.DISCLAIMED] == "1" and env[disclaim.UNIT_PID] == str(os.getpid())


def test_signals_are_forwarded_from_before_the_spawn(fake_spawn, monkeypatch):
    """A stop that arrives while the child is being started must reach it, not kill only the parent."""
    monkeypatch.setattr(os, "waitpid", lambda pid, flags: (pid, 0))
    disclaim.run_disclaimed(["/bin/true"])
    assert fake_spawn["sigterm"] not in (signal.SIG_DFL, signal.SIG_IGN, None)


def test_a_child_killed_by_a_signal_exits_as_a_shell_would_say(fake_spawn, monkeypatch):
    monkeypatch.setattr(os, "waitpid", lambda pid, flags: (pid, signal.SIGKILL))  # raw status: killed by 9
    assert disclaim.run_disclaimed(["/bin/true"]) == 128 + signal.SIGKILL


def test_unit_pid_is_read_only_from_a_number(monkeypatch):
    monkeypatch.setenv(disclaim.UNIT_PID, "123")
    assert disclaim.unit_pid() == 123
    monkeypatch.setenv(disclaim.UNIT_PID, "not-a-pid")
    assert disclaim.unit_pid() is None


def test_own_executable_falls_back_to_this_interpreter_and_says_so(monkeypatch, capsys):
    import psutil
    monkeypatch.setattr(psutil.Process, "exe", lambda self: (_ for _ in ()).throw(OSError("denied")))
    assert disclaim.own_executable() == sys.executable
    assert "can't read this process's own binary" in capsys.readouterr().err
