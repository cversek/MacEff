"""Socket-owner cross-check in proxy status (cversek/MacEff#161).

`proxy start --daemon` and a systemd unit are two independent start paths for
one singleton service. When both exist, the unit crash-loops on EADDRINUSE
while the ad-hoc instance keeps answering — so the service looks healthy while
being entirely unsupervised. Status reported the pidfile's PID, which is
exactly the field that cannot see this.
"""
import os
import socket

import pytest

from macf.proxy.server import _socket_owner_pid, get_proxy_status


def test_detects_pid_actually_holding_the_port():
    """A live listener is attributed to the process that owns it."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        owner = _socket_owner_pid(port)
        if owner is None:
            pytest.skip("no ss/lsof available to inspect sockets")
        assert owner == os.getpid()
    finally:
        s.close()


def test_no_listener_yields_none():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # port now free
    assert _socket_owner_pid(port) is None


def test_status_exposes_socket_owner_fields():
    """Status carries the cross-check fields even when nothing is running."""
    status = get_proxy_status()
    assert "socket_owner_pid" in status
    assert "socket_owner_mismatch" in status
    # No proxy of ours running and no owner → nothing to flag.
    if not status["running"] and status["socket_owner_pid"] is None:
        assert status["socket_owner_mismatch"] is False
