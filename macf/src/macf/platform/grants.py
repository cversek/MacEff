"""macOS privacy grants: the names a unit may declare, and reading a denial.

MIS-0002-R63 (unit_MUST_declare_privacy_grants), with R64
(adapter_MUST_test_grants_at_install) and R65 (denied_grant_MUST_raise_notice) built
on it. A grant attaches to the responsible process, so a unit started by launchd may
not hold what the terminal held, and the denial looks like an ordinary error. The
names are a closed list so that a misspelling fails at declaration rather than as a
silent missing grant at run time.
"""
import errno
import re
from typing import List, Optional

GRANTS = ("local_network", "accessibility", "full_disk_access", "keychain")
_AUTOMATION = re.compile(r"^automation:[A-Za-z0-9.-]+$")

#: A refusal by the Local Network grant arrives at once; a real unreachable host
#: usually takes the ARP timeout first. Measured: well under 0.1 s for the refusal.
_INSTANT_S = 0.5


def parse_grants(names: List[str]) -> List[str]:
    """The declared grants, checked against the closed list. Raises on any unknown name."""
    out = []
    for name in names:
        if name in GRANTS or _AUTOMATION.match(name or ""):
            out.append(name)
            continue
        raise ValueError(f"unknown privacy grant {name!r}; expected one of {', '.join(GRANTS)} "
                         f"or automation:<bundle id>")
    return out


def classify_lan_connect(err: Optional[int], elapsed_s: float, ping_ok: bool) -> str:
    """Read one TCP connect to a LAN host, with whether ping reached the same host.

    An instant EHOSTUNREACH while ping answers is the Local Network grant refusing
    this process (ping is not covered by the grant). Everything else is reported as
    the network failure it is, never as a grant.
    """
    if err is None:
        return "connected"
    if err == errno.EHOSTUNREACH:
        if ping_ok and elapsed_s < _INSTANT_S:
            return "grant_denied:local_network"
        return "host_unreachable"
    if err == errno.ECONNREFUSED:
        return "nothing_listening"
    if err == errno.ETIMEDOUT:
        return "timeout"
    return f"error:{errno.errorcode.get(err, err)}"
