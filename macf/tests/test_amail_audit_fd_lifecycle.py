"""AuditLog must not leak a descriptor per instance.

`_reserve_spare` opens a descriptor on /dev/null so a critical write can still
complete when the process is out of them. Nothing released it, so every
instance kept one for the life of the process -- and the mechanism that exists
to survive descriptor exhaustion became the cause of it.

Observed on a live deployment before the fix. The contrast is what identified
it: the broker builds ONE AuditLog on `self` and held 5 descriptors after three
days; the inbound path builds one per call and held 1024 of 1024. At the
ceiling the daemon could not open its own heartbeat file, so it stayed alive,
reported `failures_total: 0`, and simply stopped publishing liveness. Its log
carried `[Errno 24] Too many open files` 2,851 times and nobody read it,
because the process looked healthy from every local angle.

These tests count REAL descriptors under /proc/self/fd rather than asserting
that close() was called. The defect was never about intent; it was about
whether the descriptor survived the object.
"""

import os

import pytest

from macf.amail.audit import AuditLog

pytestmark = pytest.mark.skipif(
    not os.path.isdir("/proc/self/fd"), reason="needs /proc to count descriptors"
)


def _nfd() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_dropping_the_reference_does_not_leak(tmp_path):
    """The exact shape that wedged the deployment: construct, drop, repeat.

    Ten iterations rather than one -- a single construction leaked one
    descriptor and looked like noise, which is why this survived review. The
    signal is that the count does not GROW.
    """
    path = tmp_path / "audit.jsonl"
    AuditLog(path)          # warm any one-time allocation
    base = _nfd()
    for _ in range(10):
        AuditLog(path)
    assert _nfd() <= base, f"leaked {_nfd() - base} descriptor(s) over 10 constructions"


def test_close_is_idempotent(tmp_path):
    """Called twice must not raise, and must not close a descriptor twice.

    Double-close is worse than a leak: the number can be reissued to an
    unrelated open file, so the second close corrupts a stranger.
    """
    a = AuditLog(tmp_path / "audit.jsonl")
    a.close()
    a.close()


def test_context_manager_releases_on_exit(tmp_path):
    """The intended call shape for a per-call construction."""
    path = tmp_path / "audit.jsonl"
    with AuditLog(path):
        pass
    base = _nfd()
    for _ in range(10):
        with AuditLog(path):
            pass
    assert _nfd() <= base


def test_the_spare_is_still_reserved_while_open(tmp_path):
    """The fix must not delete the feature.

    The reservation has a purpose -- releasing it under pressure is what lets a
    critical write proceed at the ceiling. A "fix" that simply stopped
    reserving would pass the leak tests above and remove the guarantee.
    """
    a = AuditLog(tmp_path / "audit.jsonl")
    try:
        assert a._spare_fd is not None, "no spare reserved; the guarantee is gone"
        os.fstat(a._spare_fd)          # it is a real, open descriptor
    finally:
        a.close()
    assert a._spare_fd is None
