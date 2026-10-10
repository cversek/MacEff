"""macOS privacy grants: the names a unit may declare, and reading a denial.

MIS-0002-R63 (unit_MUST_declare_privacy_grants), with R64
(adapter_MUST_test_grants_at_install) and R65 (denied_grant_MUST_raise_notice) built
on it. A grant attaches to the responsible process, so a unit started by launchd may
not hold what the terminal held, and the denial looks like an ordinary error. The
closed list of names a unit may declare, and its check, are the step-1 interface's
(``macf.pd.interface.PRIVACY_GRANTS``, validated on ``Unit.privacy_grants``); this
module reads a denial.
"""
import errno
from typing import Optional

#: A refusal by the Local Network grant arrives at once; a real unreachable host
#: usually takes the ARP timeout first. Measured: well under 0.1 s for the refusal.
_INSTANT_S = 0.5


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
