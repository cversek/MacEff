"""Unit-aware refusal when the proxy port is already held (cversek/MacEff#161).

`proxy start --daemon` and a systemd unit are two start paths for one singleton
service. When a unit owns the port, killing its PID just feeds Restart=always:
the unit respawns, loses the race, and crash-loops while the stale instance
keeps answering — supervision that looks healthy but isn't. The remedy is
`systemctl --user stop`, so the refusal has to name the unit, not say "kill".
"""
from unittest.mock import mock_open, patch

from macf.cli import _systemd_unit_for_pid


def _with_cgroup(content):
    return patch("builtins.open", mock_open(read_data=content))


def test_returns_leaf_unit_not_session_manager():
    """The nested user@NNNN.service ancestor is the session manager, not the unit.

    Naming it would send the operator to `systemctl status user@1000.service` —
    true, useless, and confusing.
    """
    with _with_cgroup(
        "0::/user.slice/user-1000.slice/user@1000.service/app.slice/macf-proxy.service\n"
    ):
        assert _systemd_unit_for_pid(4242) == "macf-proxy.service"


def test_returns_unit_for_simple_system_scope():
    with _with_cgroup("0::/system.slice/macf-proxy.service\n"):
        assert _systemd_unit_for_pid(1) == "macf-proxy.service"


def test_returns_none_when_no_unit_in_path():
    """An ad-hoc daemon has no .service component — that is the ad-hoc case."""
    with _with_cgroup("0::/user.slice/user-1000.slice/session-3.scope\n"):
        assert _systemd_unit_for_pid(1) is None


def test_returns_none_without_proc():
    """macOS and other non-systemd hosts have no /proc — clean 'not applicable'."""
    with patch("builtins.open", side_effect=FileNotFoundError):
        assert _systemd_unit_for_pid(1) is None


def test_returns_none_on_permission_error():
    """Another user's PID is unreadable; degrade rather than raise."""
    with patch("builtins.open", side_effect=PermissionError):
        assert _systemd_unit_for_pid(1) is None
