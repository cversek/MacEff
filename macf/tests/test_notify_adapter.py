"""Delivery: edge-triggered on arrival, and refusing before it sends.

The level-triggered form of this is not a lesser version -- it turns one fact
into unbounded noise. This project shipped that defect in a health gate one cycle
before writing the rule against it, and was paged 36 times in nine hours.
"""
import json
import os

import pytest

from macf.notify import adapter, liveness
from macf.notify.notice import Notice, amail_notice


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
    adapter._record_seen(adapter.dedup_key("arr-c", None))
    assert adapter.already_delivered("arr-c") is True

    result = adapter.deliver(os.getpid(), notice)
    assert result.outcome == adapter.SUPPRESSED_DUPLICATE
    # and a DIFFERENT arrival is not suppressed by it
    other = adapter.deliver(os.getpid(), amail_notice("arr-d", count=1))
    assert other.outcome != adapter.SUPPRESSED_DUPLICATE


def test_dedup_is_keyed_on_the_CONVERSATION_not_the_arrival_alone(runtime, home):
    """Two processes serving one conversation must not both be told.

    Keyed on the arrival alone, the first delivery suppresses the second and the
    target is chosen by directory order -- an invisible choice. Keyed per-pid,
    both are told and the agent acts twice on one arrival. The conversation is
    the agent, so that is the key.
    """
    a = adapter.dedup_key("arr-x", "conv-1")
    b = adapter.dedup_key("arr-x", "conv-2")
    assert a != b, "the same arrival to two different agents is two deliveries"

    adapter._record_seen(a)
    assert adapter.already_delivered("arr-x", "conv-1") is True
    assert adapter.already_delivered("arr-x", "conv-2") is False, (
        "suppressing a different conversation would silently drop its notice"
    )


def test_a_missing_conversation_is_recorded_in_the_key_not_papered_over(runtime, home):
    """Addressing a process rather than an agent is a distinguishable state."""
    k = adapter.dedup_key("arr-y", None)
    assert "unknown-conversation" in k
    assert k != adapter.dedup_key("arr-y", "conv-1")


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


def test_transport_failure_FAILS_OPEN_and_never_raises(runtime, home, monkeypatch, capsys):
    """A notifier's death must never become the agent's stall.

    The socket path exists but is not a socket, so connect() raises. The adapter
    must convert that into an OUTCOME, not propagate it: anything that can be
    called from near an agent's working path must not throw.

    SCOPE, stated so this is not read as more than it is: this exercises fail-open
    on a transport ERROR. It does not exercise a HANG. The bounded timeout below
    is asserted as configuration, not demonstrated against a stalled peer -- that
    needs a socket that accepts and never reads, and is owed.
    """
    pid = os.getpid()
    (home / f"{pid}.deadbeef.key").write_text(json.dumps({
        "peerToken": "tok",
        "procStart": str(__import__("macf.notify.session", fromlist=["x"]).proc_start_ticks(pid)),
    }))
    sockdir = runtime / "cc-socks"
    sockdir.mkdir(parents=True, exist_ok=True)
    (sockdir / f"{pid}.sock").write_text("not a socket")

    result = adapter.deliver(pid, amail_notice("arr-open", count=1))
    assert result.outcome == adapter.FAILED_TRANSPORT
    assert result.ok is False
    assert "MACF" in capsys.readouterr().err

    # a failed delivery must NOT be recorded as delivered, or the retry is lost
    assert adapter.already_delivered("arr-open") is False


def test_the_connect_timeout_is_bounded():
    """An unbounded timeout is a synchronous path wearing a disguise."""
    assert 0 < adapter.CONNECT_TIMEOUT_S <= 5.0


@pytest.mark.integration
def test_a_STALLED_peer_times_out_instead_of_hanging_the_caller(runtime, home):
    """The control owed since the fail-open test was first written.

    That test exercised a transport ERROR -- a path that raises immediately. This
    exercises a HANG, which is the case the timeout exists for and the only one
    that can actually stall an agent. A peer that accepts the connection and then
    never reads is indistinguishable from a healthy one until the buffers fill.

    The listener accepts, sets a tiny receive buffer, and reads nothing. The
    payload is sized past that buffer so sendall must block. The assertion is
    twofold: the call RETURNS (an outcome, not an exception), and it returns
    within the configured bound rather than whenever the peer feels like it.
    """
    import socket as _socket
    import threading
    import time as _time
    from macf.notify import session as _session

    pid = os.getpid()
    (home / f"{pid}.deadbeef.key").write_text(json.dumps({
        "peerToken": "tok",
        "procStart": str(_session.proc_start_ticks(pid)),
    }))

    sockdir = runtime / "cc-socks"
    sockdir.mkdir(parents=True, exist_ok=True)
    sock_path = str(sockdir / f"{pid}.sock")

    listener = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVBUF, 1024)
    listener.bind(sock_path)
    listener.listen(1)
    accepted = []

    def accept_and_stall():
        try:
            conn, _ = listener.accept()
            conn.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVBUF, 1024)
            accepted.append(conn)
            # Read NOTHING. This is the whole point.
            _time.sleep(30)
        except OSError:
            pass

    t = threading.Thread(target=accept_and_stall, daemon=True)
    t.start()
    _time.sleep(0.2)

    # Large enough that it cannot fit in the peer's receive buffer.
    fat = Notice(source="amail", arrival_id="arr-stall",
                 pointer="x" * 4_000_000, count=1)

    started = _time.monotonic()
    try:
        result = adapter.deliver(pid, fat)
    finally:
        for c in accepted:
            c.close()
        listener.close()
    elapsed = _time.monotonic() - started

    assert result.outcome == adapter.FAILED_TRANSPORT, (
        f"a stalled peer must yield an outcome, not a hang (got {result.outcome})")
    assert elapsed < adapter.CONNECT_TIMEOUT_S * 4, (
        f"returned in {elapsed:.1f}s -- the bound must actually bind")
    # and a stalled delivery is NOT recorded as delivered
    assert adapter.already_delivered("arr-stall") is False
