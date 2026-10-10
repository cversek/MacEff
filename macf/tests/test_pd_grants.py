"""Privacy grants a unit declares, and telling a denied grant from a network fault.

MIS-0002-R63 (unit_MUST_declare_privacy_grants) and R64/R65. On macOS a grant attaches
to the responsible process, and a denial looks like an ordinary error: a socket to a LAN
host refused by the Local Network grant fails at once with EHOSTUNREACH while ping (which
the grant does not cover) still answers. Measured on this framework's hosts with a bench
instrument in 2026-07.
"""
import errno

import pytest

from macf.platform.grants import classify_lan_connect, parse_grants


def test_closed_vocabulary_accepts_the_known_grants():
    assert parse_grants(["local_network", "accessibility", "full_disk_access", "keychain",
                         "automation:com.googlecode.iterm2"]) == [
        "local_network", "accessibility", "full_disk_access", "keychain", "automation:com.googlecode.iterm2"]


def test_a_misspelt_grant_fails_at_declaration():
    with pytest.raises(ValueError, match="local_netwrok"):
        parse_grants(["local_netwrok"])


def test_automation_needs_a_target_bundle():
    with pytest.raises(ValueError):
        parse_grants(["automation:"])


def test_instant_unreachable_with_ping_answering_is_a_denied_grant():
    assert classify_lan_connect(errno.EHOSTUNREACH, elapsed_s=0.01, ping_ok=True) == "grant_denied:local_network"


def test_other_failures_stay_network_failures():
    assert classify_lan_connect(errno.EHOSTUNREACH, elapsed_s=0.01, ping_ok=False) == "host_unreachable"
    assert classify_lan_connect(errno.ECONNREFUSED, elapsed_s=0.01, ping_ok=True) == "nothing_listening"
    assert classify_lan_connect(errno.ETIMEDOUT, elapsed_s=5.0, ping_ok=True) == "timeout"
    assert classify_lan_connect(None, elapsed_s=0.01, ping_ok=True) == "connected"
