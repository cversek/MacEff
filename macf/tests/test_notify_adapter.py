"""Delivery: edge-triggered on arrival, and refusing before it sends.

The level-triggered form of this is not a lesser version -- it turns one fact
into unbounded noise. This project shipped that defect in a health gate one cycle
before writing the rule against it, and was paged 36 times in nine hours.
"""
import json
import os

import pytest

from macf.notify import adapter, liveness
from macf.notify.notice import amail_notice


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A session directory containing no credential, unless a test writes one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    sessions = tmp_path / ".claude" / "sessions"
    sessions.mkdir(parents=True)
    return sessions


def test_refuses_when_no_credential_exists(runtime, home):
    """A pid with no credential is not addressable, and says so."""
    result = adapter.deliver(os.getpid(), amail_notice("arr-a", count=1))
    assert result.outcome == adapter.REFUSED_NO_CREDENTIAL
    assert result.ok is False


def test_refuses_a_stale_credential_before_reaching_the_transport(runtime, home):
    """The incarnation check runs BEFORE a socket is looked up, let alone opened.

    Ordering is the property under test: no credential is put on a wire for a
    session the check would have refused. There is no socket in this fixture, so
    a refusal for the socket's absence would mean the check never ran.
    """
    pid = os.getpid()
    (home / f"{pid}.deadbeef.key").write_text(
        json.dumps({"peerToken": "tok", "procStart": "1"})
    )
    result = adapter.deliver(pid, amail_notice("arr-b", count=1))
    assert result.outcome == adapter.REFUSED_INCARNATION


def test_one_arrival_delivers_once_even_when_offered_repeatedly(runtime, home):
    """Edge-triggered. The dedup store is consulted before anything else."""
    notice = amail_notice("arr-c", count=1)
    assert adapter.already_delivered("arr-c") is False
    adapter._record_seen("arr-c")
    assert adapter.already_delivered("arr-c") is True

    result = adapter.deliver(os.getpid(), notice)
    assert result.outcome == adapter.SUPPRESSED_DUPLICATE
    # and a DIFFERENT arrival is not suppressed by it
    other = adapter.deliver(os.getpid(), amail_notice("arr-d", count=1))
    assert other.outcome != adapter.SUPPRESSED_DUPLICATE


def test_dedup_store_is_bounded(runtime, home):
    """An unbounded dedup store is a slow leak that surfaces months later."""
    for i in range(adapter.DEDUP_RETAIN + 25):
        adapter._record_seen(f"arr-{i}")
    stored = json.loads(adapter.dedup_path().read_text())
    assert len(stored) == adapter.DEDUP_RETAIN
    # the most recent survive; the oldest are evicted
    assert f"arr-{adapter.DEDUP_RETAIN + 24}" in stored
    assert "arr-0" not in stored


@pytest.mark.parametrize("body", ["{corrupt", json.dumps({"not": "a list"})])
def test_a_corrupt_dedup_store_fails_OPEN_and_says_so(runtime, home, body, capsys):
    """Dedup is ADVISORY. Its failure must not stall a wake.

    The cost is an admitted redelivery, which is why the warning is mandatory --
    failing open quietly is how a suppression bug becomes invisible.
    """
    adapter.dedup_path().write_text(body)
    assert adapter.already_delivered("anything") is False
    assert "MACF" in capsys.readouterr().err


def test_deliver_and_publish_refreshes_liveness_even_when_delivery_fails(runtime, home):
    """Liveness ships in the same change as the capability, not after it.

    A component that can speak to an agent but cannot say whether it is there
    reproduces the silence it was built to end.
    """
    assert liveness.read().verdict == liveness.ABSENT
    result = adapter.deliver_and_publish(os.getpid(), amail_notice("arr-e", count=1))
    assert result.ok is False
    after = liveness.read()
    assert after.verdict == liveness.ALIVE
