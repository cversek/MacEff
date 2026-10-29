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
import sys
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


# ============================================================================
# The install-time probe (MIS-0002-R64 (adapter_MUST_test_grants_at_install))
# ============================================================================

#: What a probe says of one grant. ``untested`` carries its reason: a grant with no probe
#: that can't raise a dialog or change the machine is said so, never reported as held.
HELD, DENIED = "held", "denied"

#: The probes here raise no permission dialog: they read whether the grant is held.
#: Keychain and Automation have no read that doesn't risk one, so they stay untested.
UNTESTED_REASONS = {
    "keychain": "untested: no keychain read is free of a permission dialog",
}


def _default_gateway() -> Optional[str]:
    import subprocess
    try:
        out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"⚠️ MACF: grants: the default route can't be read: {e}", file=sys.stderr)
        return None
    for line in out.stdout.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key == "gateway" and value.strip():
            return value.strip()
    return None


def probe_local_network(host: Optional[str] = None, port: int = 80) -> str:
    """One TCP connect to a LAN host (the default gateway), read by ``classify_lan_connect``."""
    import socket
    import subprocess
    import time
    host = host or _default_gateway()
    if not host:
        return "untested: no default gateway to try"
    start = time.monotonic()
    err = None
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError as e:
        err = e.errno if e.errno is not None else errno.ETIMEDOUT
    elapsed = time.monotonic() - start
    if err in (None, errno.ECONNREFUSED):
        return HELD                    # the host answered, so the grant let the connect through
    ping = subprocess.run(["ping", "-c", "1", "-t", "2", host], capture_output=True).returncode == 0
    verdict = classify_lan_connect(err, elapsed, ping)
    return DENIED if verdict == "grant_denied:local_network" else f"untested: the gateway {host} gave {verdict}"


def probe_full_disk_access(path: Optional[str] = None) -> str:
    """Read a file only Full Disk Access opens: the user's privacy database."""
    import os
    path = path or os.path.expanduser("~/Library/Application Support/com.apple.TCC/TCC.db")
    try:
        with open(path, "rb") as f:
            f.read(16)
    except PermissionError:
        return DENIED
    except OSError as e:
        return f"untested: {path} can't be read ({e.strerror})"
    return HELD


def probe_accessibility() -> str:
    """``AXIsProcessTrusted``, which asks without prompting."""
    import ctypes
    import ctypes.util
    lib = ctypes.util.find_library("ApplicationServices")
    if not lib:
        return "untested: ApplicationServices isn't here"
    ax = ctypes.cdll.LoadLibrary(lib)
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    return HELD if ax.AXIsProcessTrusted() else DENIED


PROBES = {"local_network": probe_local_network, "full_disk_access": probe_full_disk_access,
          "accessibility": probe_accessibility}


def probe(grants) -> dict:
    """Each declared grant's verdict, as this process holds it."""
    out = {}
    for grant in grants:
        if grant in PROBES:
            try:
                out[grant] = PROBES[grant]()
            except Exception as e:      # a probe that breaks says so; it is never read as held
                out[grant] = f"untested: the probe failed ({type(e).__name__}: {e})"
        elif grant.startswith("automation:"):
            out[grant] = "untested: an Automation check would raise its permission dialog"
        else:
            out[grant] = UNTESTED_REASONS.get(grant, "untested: no probe for this grant")
    return out


def main(argv=None) -> int:
    """``python -m macf.platform.grants OUT GRANT...``: write the verdicts to OUT as JSON."""
    import json
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m macf.platform.grants OUT GRANT...", file=sys.stderr)
        return 2
    out, grants = args[0], args[1:]
    with open(out + ".tmp", "w") as f:
        json.dump(probe(grants), f)
    import os
    os.replace(out + ".tmp", out)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
