"""The deferred queue under a second writer, and the cap that used to evict in silence.

From peer review ira-75 against the Phase 4 masking surface.

F1: `defer` and `release` are read-modify-write over one whole-list file.
`os.replace` makes each WRITE atomic and says nothing about the SEQUENCE, so a
concurrent write clobbers entries -- while `defer` returns True and the caller
records a hold. A drop reported as a hold, which is the one thing the adapter's
own comment forbids. The guard there covers `_write` RAISING; this is `_write`
SUCCEEDING while clobbering, which is indistinguishable from success at every
observation point that existed.

The second writer exists by construction: `release_deferred` was added so a
lapsed section would not hold its notices until unrelated traffic arrived. The
fix for that gap is what supplied the concurrency.

MOST OF THIS FILE IS DETERMINISTIC ON PURPOSE. A test that races and asserts
"nothing was lost" passes or fails on machine load, which is the defect this
project fixed in its supervisor tests the same day this was written. The lock is
therefore tested by its MECHANISM -- a separate stable-inode file, and mutual
exclusion probed with LOCK_NB -- and the contention test is included as
corroboration rather than as the proof.
"""
import fcntl
import multiprocessing as mp
import os

import pytest

from macf.notify.masking import DEFERRED_RETAIN, Mask
from macf.notify.notice import Notice


def _notice(i, source="amail"):
    return Notice(source=source, arrival_id=f"a{i}", pointer="see the store", count=None)


@pytest.fixture
def mask(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return Mask(session_id="conv-1")


# --------------------------------------------------------------------------
# The mechanism, asserted directly
# --------------------------------------------------------------------------

def test_the_lock_is_a_separate_file_from_the_queue(mask):
    """Because publishing the queue REPLACES it, which swaps the inode.

    A lock taken on the queue file would be held against an inode the next
    writer's `os.replace` makes unreachable: two processes each holding a valid
    lock on a different inode, both believing they had exclusion.
    """
    assert mask.lock_path() != mask.deferred_path()
    mask.defer(_notice(1))
    inode_before = os.stat(mask.lock_path()).st_ino
    mask.defer(_notice(2))          # publishes the queue again
    assert os.stat(mask.lock_path()).st_ino == inode_before, (
        "the lock file's identity changed; exclusion cannot survive that"
    )


def test_holding_the_lock_actually_excludes_another_acquirer(mask):
    """Deterministic: probe with LOCK_NB rather than racing two writers."""
    with mask._queue_lock():
        with open(mask.lock_path(), "a+") as rival:
            with pytest.raises(BlockingIOError):
                fcntl.flock(rival.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    # released on exit
    with open(mask.lock_path(), "a+") as rival:
        fcntl.flock(rival.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(rival.fileno(), fcntl.LOCK_UN)


# --------------------------------------------------------------------------
# The floor, which defer must enforce for itself
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source", ["macf-daemon", "supervision", "authority", "operator"])
def test_defer_REFUSES_an_unmaskable_notice(mask, source, capsys):
    """A property of the primitive, not of who happens to call it.

    `decide` checks the floor first, so today this cannot fire. That is a fact
    about the current call graph; a second caller is exactly how a notice about
    the agent's own authority reaches a maskable queue.
    """
    assert mask.defer(_notice(1, source=source)) is False
    assert mask.deferred() == []
    assert "refusing to defer an unmaskable notice" in capsys.readouterr().err


def test_an_ordinary_world_notice_is_still_deferred(mask):
    """Control: the refusal above must not be refusing everything."""
    assert mask.defer(_notice(1)) is True
    assert len(mask.deferred()) == 1


# --------------------------------------------------------------------------
# The cap, which used to discard without a word
# --------------------------------------------------------------------------

def test_eviction_at_the_cap_is_ANNOUNCED(mask, capsys):
    for i in range(DEFERRED_RETAIN + 3):
        mask.defer(_notice(i))
    err = capsys.readouterr().err
    assert "deferred queue is full" in err
    assert "DISCARDING" in err
    assert "lost, not delayed" in err
    assert len(mask.deferred()) == DEFERRED_RETAIN


def test_below_the_cap_nothing_is_announced(mask, capsys):
    """Control: an eviction warning that always fires is not a warning."""
    for i in range(5):
        mask.defer(_notice(i))
    assert "deferred queue is full" not in capsys.readouterr().err


# --------------------------------------------------------------------------
# Scoping must not merge two conversations
# --------------------------------------------------------------------------

def test_two_ids_that_sanitize_alike_do_not_share_a_queue(tmp_path, monkeypatch):
    """Stripping is lossy; two distinct ids must not land in one bucket."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    a, b = Mask(session_id="!!!"), Mask(session_id="###")
    assert a.deferred_path() != b.deferred_path()
    a.defer(_notice(1))
    assert b.deferred() == [], "conversation B sees A's notices"


# --------------------------------------------------------------------------
# Corroboration under real contention (not the proof -- see the module docstring)
# --------------------------------------------------------------------------

def _worker(runtime, i, barrier):
    os.environ["XDG_RUNTIME_DIR"] = runtime
    m = Mask(session_id="conv-1")
    barrier.wait()
    m.defer(_notice(i))


def test_concurrent_defers_do_not_lose_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    n = 12
    ctx = mp.get_context("fork")
    barrier = ctx.Barrier(n)
    procs = [ctx.Process(target=_worker, args=(str(tmp_path), i, barrier)) for i in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    held = {h["arrival_id"] for h in Mask(session_id="conv-1").deferred()}
    assert held == {f"a{i}" for i in range(n)}, (
        f"lost {n - len(held)} of {n} concurrently deferred notices"
    )


# --------------------------------------------------------------------------
# ira-76's blocker: clearing on read destroyed a notice on an ORDINARY refusal
# --------------------------------------------------------------------------

def test_a_refused_delivery_leaves_the_notice_HELD(tmp_path, monkeypatch):
    """The blocker. `release` cleared the queue and delivery happened after.

    `REFUSED_NO_CREDENTIAL` is a normal outcome, not a crash -- and the moment it
    is most likely is exactly the moment a release is most likely: a section
    lapses after a session ended, the poller fires, the credential is gone. Every
    notice the agent declared a section to protect was destroyed by the mechanism
    built to preserve it.

    peek + retire-only-what-was-confirmed makes the path at-least-once instead.
    """
    from macf.notify import adapter, masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(adapter, "find_credential_path", lambda pid: None)

    mask = masking.load(None)
    assert mask.defer(_notice(1)) is True

    results = adapter._flush_deferred(os.getpid(), masking.load(None))

    assert results and not results[0].ok, "expected the delivery to refuse"
    assert len(masking.load(None).deferred()) == 1, (
        "the notice was cleared on read and is unrecoverable -- this is the "
        "at-most-once failure ira-76 blocked Phase 4 on"
    )


def test_a_CONFIRMED_delivery_retires_the_notice(tmp_path, monkeypatch):
    """CONTROL: retention must not become 'never retires'.

    Without this, the fix above is satisfied by a queue that simply never drains,
    which converts a lost notice into an eternally repeated one.
    """
    from macf.notify import adapter, masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    mask = masking.load(None)
    assert mask.defer(_notice(7)) is True

    class _Ok:
        def __init__(self, aid):
            self.ok, self.arrival_id = True, aid

    monkeypatch.setattr(adapter, "deliver", lambda pid, n, **kw: _Ok(n.arrival_id))
    adapter._flush_deferred(os.getpid(), masking.load(None))

    assert masking.load(None).deferred() == [], (
        "a confirmed delivery must retire its entry, or the queue never drains"
    )


def test_retire_removes_ONLY_what_is_named(tmp_path, monkeypatch):
    """Partial success is the realistic case: some deliver, some refuse."""
    from macf.notify import masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    mask = masking.load(None)
    for i in range(4):
        mask.defer(_notice(i))
    assert mask.retire(["a1", "a3"]) == 2
    left = {h["arrival_id"] for h in masking.load(None).deferred()}
    assert left == {"a0", "a2"}


def test_peek_does_not_clear(tmp_path, monkeypatch):
    from macf.notify import masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    mask = masking.load(None)
    mask.defer(_notice(1))
    assert len(mask.peek()) == 1
    assert len(mask.peek()) == 1, "peek cleared the queue; that is release's job"


def test_a_RETRIED_notice_suppresses_as_a_duplicate(tmp_path, monkeypatch):
    """The other half of the fix, and the half a mutation sweep found untested.

    peek+retire makes the release path AT-LEAST-ONCE: a delivery that refuses is
    retried on the next poll. That is only safe because the dedup ledger is
    consulted on this path too -- which it was not, because one flag meant both
    "do not re-apply the mask" (right) and "do not consult the ledger" (not
    needed, and exactly what made a retry unsafe).

    Without this test, the flag split is unverified: a mutant restoring the old
    coupling passes the entire notify suite.
    """
    from macf.notify import adapter, masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    n = _notice(42)
    adapter._record_seen(adapter.dedup_key(n.arrival_id, None))

    masking.load(None).defer(n)
    results = adapter._flush_deferred(os.getpid(), masking.load(None))

    assert results and results[0].outcome == adapter.SUPPRESSED_DUPLICATE, (
        f"a retried notice was re-delivered instead of suppressed "
        f"(outcome={results[0].outcome if results else 'none'}); the release "
        f"path is at-least-once, so the ledger is what makes it exactly-once"
    )


def test_the_mask_is_still_bypassed_on_the_release_path(tmp_path, monkeypatch):
    """CONTROL: consulting the ledger must not re-apply the MASK.

    Restoring the ledger check by removing the whole bypass would satisfy the
    test above and reintroduce the defect it replaced -- the section that held a
    notice holding it again, so "deferred" quietly means "never".
    """
    from macf.notify import adapter, masking
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(adapter, "find_credential_path", lambda pid: None)

    masking.declare_critical("mid-proof", 60)
    masking.load(None).defer(_notice(9))
    results = adapter._flush_deferred(os.getpid(), masking.load(None))

    assert results and results[0].outcome != adapter.DEFERRED, (
        "the still-active section re-held the notice; bypass_mask was lost"
    )
