"""Addressing a session, and refusing to address a number.

The incarnation check is the AUTHORIZATION control in this subsystem, so every
test here ships with both polarities: the case it must catch and the case it
must pass. A check that refuses everything is not a check.
"""
import json
import os

import pytest

from macf.notify import session


@pytest.fixture
def live_pid():
    """This process. Real, running, with a real /proc entry."""
    return os.getpid()


@pytest.fixture
def real_start(live_pid):
    ticks = session.proc_start_ticks(live_pid)
    assert ticks is not None, "positive control: this process must be readable in /proc"
    return ticks


def test_proc_start_is_readable_and_absent_for_a_dead_pid(real_start):
    """Positive control first, then the negative one."""
    assert isinstance(real_start, int)
    # pid 0 is never a normal userspace process; /proc/0 does not exist.
    assert session.proc_start_ticks(0) is None


def test_incarnation_accepts_the_STRING_form_the_credential_actually_stores(live_pid, real_start):
    """The regression guard for the defect that kept this check unwritten.

    The credential stores procStart as a string; /proc yields an int. A naive
    equality is False for every well-formed credential, which refuses every
    legitimate wake and makes deleting the check look like the fix.
    """
    assert session.verify_incarnation(live_pid, str(real_start)) is True
    assert session.verify_incarnation(live_pid, real_start) is True
    assert session.verify_incarnation(live_pid, f"  {real_start}  ") is True


def test_incarnation_refuses_a_stale_value_against_a_live_pid(live_pid, real_start):
    """The case it exists for: a recycled pid addressed with a stale credential."""
    assert session.verify_incarnation(live_pid, str(real_start + 1)) is False
    assert session.verify_incarnation(live_pid, str(real_start - 1)) is False


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
