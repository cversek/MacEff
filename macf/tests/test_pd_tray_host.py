"""Whether a host can show the tray (MIS-0002-R73 (readout_MUST_say_tray_unavailable)).

The readout's own test, ``test_pd_readout.py::test_tray_unavailable_said``, lands with
``pd status``, which calls ``tray_host``. These pin what it will be told.
"""
import os
import sys

import pytest

from macf.platform.tray_host import TrayHost, tray_host


ME = 501


def _found(name):
    return object()


def _missing(name):
    return None


def test_off_macos_it_says_the_tray_is_macos_only():
    host = tray_host(platform="linux", find_spec=_found, owner=lambda: ME, uid=ME)
    assert not host.available
    assert host.said() == "tray: unavailable (the tray runs only on macOS so far)"


def test_without_the_extra_it_names_the_install():
    host = tray_host(platform="darwin", find_spec=_missing, owner=lambda: ME, uid=ME)
    assert not host.available and "pip install 'macf[tray]'" in host.reason


@pytest.mark.parametrize("owner, reason", [
    (0, "nobody is logged in to the GUI"),                  # root owns it at the login window
    (ME + 1, "the GUI belongs to another user"),
])
def test_without_this_users_gui_it_says_why(owner, reason):
    host = tray_host(platform="darwin", find_spec=_found, owner=lambda: owner, uid=ME)
    assert host == TrayHost(False, reason)


def test_an_unreadable_console_is_said_with_its_error():
    def unreadable():
        raise PermissionError("[Errno 1] Operation not permitted: '/dev/console'")
    host = tray_host(platform="darwin", find_spec=_found, owner=unreadable, uid=ME)
    assert not host.available
    assert host.reason.startswith("the GUI console's owner cannot be read: ")
    assert "Operation not permitted" in host.reason


def test_this_users_gui_with_the_extra_is_available():
    host = tray_host(platform="darwin", find_spec=_found, owner=lambda: ME, uid=ME)
    assert host.available and host.said() == "tray: available"


def test_the_environment_cannot_name_the_user(monkeypatch):
    """The owner is compared by uid: LOGNAME and USER naming someone else change nothing."""
    monkeypatch.setenv("LOGNAME", "someone-else")
    monkeypatch.setenv("USER", "someone-else")
    assert tray_host(platform="darwin", find_spec=_found, owner=os.getuid).available
    assert not tray_host(platform="darwin", find_spec=_found, owner=lambda: os.getuid() + 1).available


def test_the_extra_is_looked_up_never_imported():
    """Asking must not run rumps or the tray package (R68)."""
    asked = []
    before = {m for m in sys.modules if m == "rumps" or m.startswith("macf.tray")}
    tray_host(platform="darwin", find_spec=lambda name: asked.append(name) or None)
    after = {m for m in sys.modules if m == "rumps" or m.startswith("macf.tray")}
    assert asked == ["rumps"] and after == before


@pytest.mark.live
@pytest.mark.skipif(sys.platform != "darwin", reason="reads this Mac's console")
def test_on_this_mac_the_answer_is_definite():
    """Live: a real answer, either available or with a reason, never an exception."""
    host = tray_host()
    assert host.available or host.reason
