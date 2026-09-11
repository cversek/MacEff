"""Addressing a session, and refusing to address a number.

The incarnation check is the AUTHORIZATION control in this subsystem, so every
test here ships with both polarities: the case it must catch and the case it
must pass. A check that refuses everything is not a check.
"""
import json
import os
import sys

import pytest

from macf.notify import session


@pytest.fixture
def live_pid():
    """This process. Real, running, with a real /proc entry."""
    return os.getpid()


@pytest.fixture
def real_start(live_pid):
    """The stored form on this platform (ticks string on Linux, UTC asctime on macOS)."""
    start = session.proc_start(live_pid)
    assert start is not None, "positive control: this process must have a readable start"
    return start


def _shifted(start, delta):
    """The same platform form, ``delta`` units later: a different incarnation."""
    return session.proc_start_from_key(session.proc_start_key(start) + delta)


def test_proc_start_is_readable_and_absent_for_a_dead_pid(real_start):
    """Positive control first, then the negative one."""
    assert isinstance(real_start, str) and session.proc_start_key(real_start) is not None
    # pid 0 is never a normal userspace process; neither /proc/0 nor `ps -p 0` reports one.
    assert session.proc_start(0) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc is Linux-only")
def test_proc_start_ticks_is_the_linux_reader(live_pid):
    assert isinstance(session.proc_start_ticks(live_pid), int)
    assert session.proc_start_ticks(0) is None


def test_linux_reader_parses_a_stat_line_with_parens_in_comm(monkeypatch, tmp_path):
    """The Linux branch is what CI exercises for real; here it is fed a synthetic
    /proc so a macOS run still checks the parse, including a `comm` that contains
    a space and a parenthesis, which is why the line is split from its LAST ')'."""
    import builtins
    stat = tmp_path / "stat"
    # fields 3.. follow the ')' -- state, ppid, ... -- and starttime is field 22, so index 19 here
    fields = [str(n) for n in range(3, 30)]
    fields[19] = "424242"
    stat.write_text("4242 (my (odd) name) " + " ".join(fields) + "\n")
    real_open = builtins.open

    def fake_open(path, *a, **k):
        if str(path) == "/proc/4242/stat":
            return real_open(stat, *a, **k)
        if str(path).startswith("/proc/"):
            raise FileNotFoundError(path)
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", fake_open)
    assert session.proc_start_ticks(4242) == 424242
    assert session.proc_start_ticks(4243) is None
    monkeypatch.setattr(session.sys, "platform", "linux")
    assert session.proc_start(4242) == "424242"
    assert session.verify_incarnation(4242, " 424242 ") is True
    assert session.verify_incarnation(4242, "424243") is False


def test_proc_start_key_canonicalises_both_stored_forms():
    """A ticks string and a UTC asctime string both reduce to an int; junk does not."""
    assert session.proc_start_key("9") == 9 and session.proc_start_key("  9 ") == 9
    assert session.proc_start_key("Thu Sep 10 23:12:40 2026") == 1789081960
    assert session.proc_start_from_key(session.proc_start_key("9")) in ("9", "Thu Jan  1 00:00:09 1970")
    for junk in (None, "", "   ", "nine", "2026-09-10"):
        assert session.proc_start_key(junk) is None


def test_incarnation_accepts_the_STRING_form_the_credential_actually_stores(live_pid, real_start):
    """The regression guard for the defect that kept this check unwritten.

    The credential stores procStart as a string; /proc yields an int. A naive
    equality is False for every well-formed credential, which refuses every
    legitimate wake and makes deleting the check look like the fix.
    """
    assert session.verify_incarnation(live_pid, str(real_start)) is True
    assert session.verify_incarnation(live_pid, session.proc_start_key(real_start)) is True
    assert session.verify_incarnation(live_pid, f"  {real_start}  ") is True


def test_incarnation_refuses_a_stale_value_against_a_live_pid(live_pid, real_start):
    """The case it exists for: a recycled pid addressed with a stale credential."""
    assert session.verify_incarnation(live_pid, _shifted(real_start, +1)) is False
    assert session.verify_incarnation(live_pid, _shifted(real_start, -1)) is False


@pytest.mark.parametrize("declared", [None, "", "not-a-number", "12.5.3", []])
def test_incarnation_fails_CLOSED_on_an_unusable_declaration(live_pid, declared):
    """Absence is not permission. This is an authorization check."""
    assert session.verify_incarnation(live_pid, declared) is False


def test_credential_repr_redacts_the_token():
    """The dataclass default would render the token into any traceback."""
    cred = session.PeerCredential(token="tok_SUPERSECRET_abcdef", declared_start="123")
    assert "SUPERSECRET" not in repr(cred)
    assert "SUPERSECRET" not in str(cred)
    assert "redacted" in repr(cred)
    # and the token is still usable by the code that needs it
    assert cred.token == "tok_SUPERSECRET_abcdef"


def test_read_credential_yields_None_rather_than_a_partial_credential(tmp_path):
    good = tmp_path / "1.k.key"
    good.write_text(json.dumps({"peerToken": "t", "procStart": "9"}))
    assert session.read_credential(good).token == "t"

    no_token = tmp_path / "2.k.key"
    no_token.write_text(json.dumps({"procStart": "9"}))
    assert session.read_credential(no_token) is None

    malformed = tmp_path / "3.k.key"
    malformed.write_text("{not json")
    assert session.read_credential(malformed) is None

    assert session.read_credential(tmp_path / "absent.key") is None
