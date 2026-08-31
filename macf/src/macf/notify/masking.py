"""What an agent may decline to be told, and what it may never decline.

Masking is the second primitive: an agent that cannot suppress anything pays the
full context tax of every source, and one that can suppress everything is
unreachable. Both extremes destroy the mechanism.

`macf_tools policy navigate notification_delivery`

THE RULE IS PREFERRED TO A LIST because a list is where the next case is
missing:

    An agent may decline to be told about the WORLD.
    It may not decline to be told about ITSELF.

Its own authority, its own instruments, its own supervision. Operator input is
not a special case under that rule; it is the first instance.

WHERE ENFORCEMENT LIVES IS THE WHOLE DESIGN. The mask is supplied by the agent,
because relevance depends on the agent's current task and nothing else can know
it. The unmaskable floor is enforced by the NOTIFIER, because an agent able to
mask its own supervision could silence the notice that says its instruments are
down -- which recreates the defect this subsystem exists to cure and makes
"no notice is distinguishable from no event" unsatisfiable.
"""
import fcntl
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .notice import Notice

#: Sources whose notices are about the agent ITSELF. Never maskable.
SELF_SOURCES = frozenset({"macf-daemon", "supervision", "authority", "operator"})

DEFERRED_NAME = "macf_notify_deferred.json"
DEFERRED_RETAIN = 256
DECLARATION_NAME = "macf_notify_mask.json"


def _runtime_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime)


def _scoped(stem: str, session_id: Optional[str]) -> Path:
    """A per-CONVERSATION path, not merely a per-uid one.

    The runtime directory is already per-uid, which is per-agent in every
    deployment we run. It is NOT per-conversation, and one agent can serve more
    than one. An unscoped queue lets a notice deferred by conversation A be
    released into conversation B -- delivering, to a session that never deferred
    it, a notice addressed to one that did. The adapter already scopes its dedup
    ledger by conversation for the same reason; this follows it rather than
    inventing a second rule.
    """
    if not session_id:
        return _runtime_dir() / stem
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
    # SANITIZING MUST NOT MERGE TWO CONVERSATIONS. Stripping and truncating are
    # lossy: two distinct ids can sanitize to the same string, and one that is
    # truthy but contains no permitted character sanitizes to EMPTY -- yielding a
    # single shared bucket holding every such conversation's notices together.
    # That is precisely the merge this function exists to prevent, arriving
    # silently through the defensive code meant to prevent it. When the safe form
    # is not faithful, fall back to a digest, which is collision-resistant and
    # always representable. Raised by peer review (ira-75) as a shape rather than
    # a live failure: real session ids are UUIDs, so it does not fire today.
    if safe != session_id:
        safe = hashlib.sha256(session_id.encode("utf-8", "replace")).hexdigest()[:32]
    base = Path(stem)
    return _runtime_dir() / f"{base.stem}.{safe}{base.suffix}"


@dataclass(frozen=True)
class MaskDecision:
    """Why a notice was allowed, deferred or suppressed.

    Named rather than a bare bool: three outcomes, and the caller must be able to
    tell "the agent does not want this now" from "the agent does not want this at
    all". Collapsing them turns a deferral into a drop.
    """

    allow: bool
    defer: bool
    reason: str

    @property
    def suppress(self) -> bool:
        return not self.allow and not self.defer


def is_unmaskable(notice: Notice) -> bool:
    """True when a notice is about the agent itself rather than about the world.

    Three classes, derived from the rule rather than enumerated as policy:
    notices about the notification system; changes to the agent's own authority;
    and anything asserting the agent is being stopped or superseded.
    """
    return notice.source in SELF_SOURCES


@dataclass
class CriticalSection:
    """A declared interval during which the agent wants only what it cannot decline.

    Carries an expiry. A critical section that outlives the work it protects is a
    permanent mute that nobody remembers switching on, so it lapses on its own
    and the lapse is announced.
    """

    label: str
    until: float
    declared_at: float = field(default_factory=time.time)

    def active(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) < self.until


class Mask:
    """The agent's own filter, with a floor it cannot lower.

    `predicate` is supplied by the agent and answers relevance -- the one thing
    only the agent knows. It is never consulted for a notice about the agent
    itself.

    A PREDICATE CANNOT CROSS A PROCESS BOUNDARY, and the notifier is a different
    process from the agent. So an in-process Mask can carry one and a Mask loaded
    from an agent's declaration cannot: `load` builds the critical section, which
    is data, and leaves the predicate None. This is stated rather than worked
    around, because a mask that silently lost its predicate on the way to the
    notifier would look like a filter and behave like an open gate.
    """

    def __init__(
        self,
        predicate: Optional[Callable[[Notice], bool]] = None,
        critical: Optional[CriticalSection] = None,
        deferred_path: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        self.predicate = predicate
        self.critical = critical
        self._deferred_path = deferred_path
        self.session_id = session_id

    def deferred_path(self) -> Path:
        if self._deferred_path is not None:
            return self._deferred_path
        return _scoped(DEFERRED_NAME, self.session_id)

    def lock_path(self) -> Path:
        """A SEPARATE file, and separate for a reason that bit us elsewhere today.

        The queue is published with `os.replace`, which swaps the INODE. A lock
        taken on the queue file itself would therefore be held against an inode
        that the next writer's replace makes unreachable -- two processes would
        each hold a valid lock on a different inode and both believe they had
        exclusion. The lock file is never replaced, so its identity is stable for
        as long as the queue exists.
        """
        q = self.deferred_path()
        return q.with_suffix(q.suffix + ".lock")

    @contextmanager
    def _queue_lock(self):
        """Serialize read-modify-write on the deferred queue.

        `os.replace` makes each individual WRITE atomic; it does nothing for the
        SEQUENCE read -> modify -> write, and both `defer` and `release` are that
        sequence against one whole-list file. Without this, three interleavings
        lose data (peer review ira-75, F1):

          defer vs defer   -- both read [A]; one writes [A,B], the other [A,C];
                              B is gone AND `defer` returned True, so the caller
                              records a hold. That is A DROP REPORTED AS HELD,
                              which the adapter's own comment forbids. The failure
                              is invisible: the guard there covers `_write`
                              RAISING, and this is `_write` SUCCEEDING while
                              clobbering.
          defer vs release -- release delivers A and writes []; defer appends to
                              its stale read and writes [A,B], resurrecting a
                              notice already delivered. The release path re-enters
                              with bypass_mask=True. That once skipped the dedup
                              ledger too, so
                              the one mechanism that would have made the
                              resurrection harmless is switched off.
          release vs release -- both deliver both entries. Same bypass.

        THE SECOND WRITER EXISTS BY CONSTRUCTION, and that is the part worth
        recording: `release_deferred` was added so a lapsed section would not hold
        its notices until unrelated traffic arrived. Before it there was one
        writer. The fix for that gap is what supplied the concurrency this lock
        now handles -- neither decision wrong, the composition unsafe.

        Failure to acquire is announced and then proceeds, deliberately: the
        pre-existing behaviour is a rare lost entry, while refusing to defer is a
        certain undelivered notice. The announcement is what makes it attributable.
        """
        path = self.lock_path()
        fh = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(path, "a+")
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (OSError, PermissionError) as e:
            print(f"⚠️ MACF: deferred-queue lock unavailable ({e}); proceeding "
                  f"UNSERIALIZED -- a concurrent write may lose an entry",
                  file=sys.stderr)
            if fh is not None:
                fh.close()
            fh = None
        try:
            yield
        finally:
            if fh is not None:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                finally:
                    fh.close()

    def decide(self, notice: Notice, now: Optional[float] = None) -> MaskDecision:
        """Allow, defer, or suppress -- with the floor checked FIRST.

        Order is the control. Consulting the agent's predicate before the floor
        would let a mask that raises, loops or simply returns False swallow a
        supervision notice, and the failure would be silent.
        """
        if is_unmaskable(notice):
            return MaskDecision(True, False, f"unmaskable: '{notice.source}' is about the agent itself")

        if self.critical is not None and self.critical.active(now):
            return MaskDecision(
                False, True,
                f"deferred: critical section '{self.critical.label}' active",
            )

        if self.predicate is None:
            return MaskDecision(True, False, "no mask declared")

        try:
            wanted = bool(self.predicate(notice))
        except Exception as e:  # noqa: BLE001 - GUARD, not handler: see coding_standards
            # A broken mask must not silence a notice. Failing open here is the
            # only safe direction: the cost is an unwanted notice, and the cost
            # of failing closed is a silence nobody can attribute.
            print(
                f"⚠️ MACF: mask predicate failed, delivering anyway (a broken "
                f"filter must not become a silence): {e}",
                file=sys.stderr,
            )
            return MaskDecision(True, False, f"mask error, failed open: {e}")

        if wanted:
            return MaskDecision(True, False, "mask allows")
        return MaskDecision(False, True, "mask declines: deferred, not dropped")

    # ---- deferral: deferred is not dropped ----

    def defer(self, notice: Notice, now: Optional[float] = None) -> bool:
        """Hold a notice for later delivery. Idempotent on arrival id.

        Idempotent and single-writer-safe: the read-modify-write is serialized by
        `_queue_lock`, without which a concurrent write clobbers whole entries
        while this returns True -- a drop reported as a hold.

        REFUSES AN UNMASKABLE NOTICE, and that check lives here rather than only
        in `decide`. Today the only caller checks the floor first, so this can
        never fire; that is a property of the current CALL GRAPH, not of the
        primitive, and "the only caller happens not to do that" is the shape this
        project has learned to distrust. A second caller is exactly how a notice
        about the agent's own authority would end up in a maskable queue.
        """
        if is_unmaskable(notice):
            print(f"⚠️ MACF: refusing to defer an unmaskable notice "
                  f"(source={notice.source!r}); the floor is not the caller's to "
                  f"waive", file=sys.stderr)
            return False
        now = now if now is not None else time.time()
        with self._queue_lock():
            held = self.deferred()
            if any(h.get("arrival_id") == notice.arrival_id for h in held):
                return True
            held.append({
                "arrival_id": notice.arrival_id,
                "source": notice.source,
                "pointer": notice.pointer,
                "count": notice.count,
                "deferred_at": now,
            })
            # THE CAP EVICTS, AND SILENCE ABOUT IT WAS THE DEFECT. This module
            # announces a failed write, an unreadable queue, a malformed queue, a
            # malformed declaration and a refused zero-second section -- and used
            # to discard the OLDEST held notices without a word. The evicted ones
            # are those held LONGEST, which is to say the ones the agent has been
            # waiting on. Raised by peer review (ira-75, F3), whose sharper point
            # is that this, not the declared duration, is the binding cap on how
            # much a critical section can cost.
            evicted = len(held) - DEFERRED_RETAIN
            if evicted > 0:
                print(f"⚠️ MACF: deferred queue is full at {DEFERRED_RETAIN}; "
                      f"DISCARDING the {evicted} oldest held notice(s). They are "
                      f"lost, not delayed.", file=sys.stderr)
            return self._write(held[-DEFERRED_RETAIN:])

    def deferred(self) -> List[dict]:
        path = self.deferred_path()
        if not path.exists():
            return []
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"⚠️ MACF: deferred queue unreadable (held notices may be lost): {e}", file=sys.stderr)
            return []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"⚠️ MACF: deferred queue malformed (held notices may be lost): {e}", file=sys.stderr)
            return []
        return data if isinstance(data, list) else []

    def peek(self) -> List[Notice]:
        """Every held notice, WITHOUT clearing the queue.

        Split out from `release` because clearing on read makes a released notice
        unrecoverable the instant it is released: delivery happens afterwards and
        can refuse for ordinary reasons -- no credential, a session that ended --
        at which point the notices are gone from disk and nothing re-queues them.

        That is not a crash window. `REFUSED_NO_CREDENTIAL` is a normal outcome,
        and the moment it is most likely is exactly the moment a release is most
        likely: a section lapses after a session ended, the poller fires, and
        every notice the agent declared a section to protect is destroyed by the
        mechanism built to preserve it. Peer review ira-76 named it as the one
        blocker on Phase 4.

        Pair with `retire()` after delivery is CONFIRMED. That makes the path
        at-least-once rather than at-most-once, which is the right direction for
        this subsystem: a repeated notice costs an interruption, a lost one costs
        a silence nobody can attribute.
        """
        with self._queue_lock():
            return self._to_notices(self.deferred())

    def retire(self, arrival_ids) -> int:
        """Drop only the entries whose delivery was CONFIRMED. Returns the count.

        Taken under the same lock as `peek`, so a concurrent `defer` cannot be
        clobbered by the retire that follows a release -- which is F1's failure
        one layer up, and the reason this is not simply a second write.

        Anything not named here STAYS HELD and is retried on the next poll.
        """
        ids = set(arrival_ids)
        if not ids:
            return 0
        with self._queue_lock():
            held = self.deferred()
            keep = [h for h in held if h.get("arrival_id") not in ids]
            removed = len(held) - len(keep)
            if removed:
                self._write(keep)
            return removed

    def _to_notices(self, held: List[dict]) -> List[Notice]:
        """Reconstructed from stored fields, never replayed verbatim, so a
        deferred notice cannot carry anything a live one could not."""
        return [Notice(
            source=str(h.get("source", "amail")),
            arrival_id=str(h.get("arrival_id", "")),
            pointer=str(h.get("pointer", "")),
            count=h.get("count"),
        ) for h in held]

    def release(self) -> List[Notice]:
        """Return every held notice ONCE and clear the queue.

        DEPRECATED IN FAVOUR OF peek()+retire(). Retained because it is the
        correct primitive when the caller genuinely cannot confirm delivery, and
        removing it would push that decision to a call site with less context.
        Callers that CAN confirm must not use it: clearing before confirmation
        loses the notice on any ordinary refusal.

        Reconstructed from stored fields rather than replayed verbatim, so a
        deferred notice cannot carry anything a live one could not.

        ONCE holds because the read and the clear happen under `_queue_lock`. It
        is not a property of `os.replace`, which makes each write atomic and says
        nothing about the sequence -- stating the condition because an invariant
        whose preconditions go unnamed is the documentation hazard this module
        was reviewed for (ira-75, F2).
        """
        with self._queue_lock():
            held = self.deferred()
            if not held:
                return []
            out = []
            for h in held:
                out.append(Notice(
                    source=str(h.get("source", "amail")),
                    arrival_id=str(h.get("arrival_id", "")),
                    pointer=str(h.get("pointer", "")),
                    count=h.get("count"),
                ))
            self._write([])
            return out

    def _write(self, items: List[dict]) -> bool:
        path = self.deferred_path()
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w") as fh:
                json.dump(items, fh)
            os.replace(tmp, path)
            return True
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"⚠️ MACF: deferred queue write failed (a held notice is now lost): {e}", file=sys.stderr)
            return False


# ---------------------------------------------------------------------------
# Declaration: how an agent tells a DIFFERENT PROCESS what it does not want now
# ---------------------------------------------------------------------------
# The mask primitive above is in-process. The notifier is not in that process,
# so without this the mask is computable and unenforceable -- a control with no
# caller, which this corpus already names three times and shipped once.
#
# Only DATA crosses. A critical section is a label and an expiry; a predicate is
# a callable and stays behind. That asymmetry is the honest boundary, not a
# limitation to be engineered around: an agent declaring "not now, I am mid-
# proof" is stating a fact about itself that survives serialization, while
# "notices I find relevant" is a judgement that does not.


def declaration_path(session_id: Optional[str] = None) -> Path:
    return _scoped(DECLARATION_NAME, session_id)


def declare_critical(
    label: str,
    seconds: float,
    session_id: Optional[str] = None,
    now: Optional[float] = None,
) -> Optional[CriticalSection]:
    """Declare a critical section that a separate notifier process will honour.

    The expiry is absolute and written down. A section that outlives its work is
    a permanent mute nobody remembers switching on, so it lapses on its own --
    and because the notifier reads the expiry rather than a flag, the lapse
    needs no cooperation from an agent that may be wedged.

    Returns the section, or None when it could not be recorded. None matters: an
    agent that believes it is masked while the notifier cannot see the
    declaration would be surprised by delivery, so the failure is returned and
    announced rather than swallowed.
    """
    now = now if now is not None else time.time()
    if seconds <= 0:
        print(
            f"⚠️ MACF: refusing a critical section of {seconds}s -- "
            f"a section that is already expired masks nothing and reads as one that does",
            file=sys.stderr,
        )
        return None

    section = CriticalSection(label=str(label), until=now + float(seconds), declared_at=now)
    path = declaration_path(session_id)
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(
                {"label": section.label, "until": section.until, "declared_at": section.declared_at},
                fh,
            )
        os.replace(tmp, path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(
            f"⚠️ MACF: critical section '{label}' could NOT be declared, so notices "
            f"will still arrive: {e}",
            file=sys.stderr,
        )
        return None
    return section


def clear_declaration(session_id: Optional[str] = None) -> bool:
    """End a critical section early. Absent is already the cleared state."""
    path = declaration_path(session_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except (PermissionError, OSError) as e:
        print(f"⚠️ MACF: could not clear the mask declaration (it will lapse on its own): {e}", file=sys.stderr)
        return False


def read_declaration(session_id: Optional[str] = None) -> Optional[CriticalSection]:
    """The declared section, or None when there is none to honour.

    A malformed declaration reads as NO section rather than as a section. The
    choice is deliberate and it is the fail-OPEN direction: an unparseable file
    should let notices through, because the alternative is an unreadable byte
    sequence silencing an agent indefinitely with nobody able to say why.
    """
    path = declaration_path(session_id)
    if not path.exists():
        return None
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: mask declaration unreadable, delivering as if unmasked: {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: mask declaration malformed, delivering as if unmasked: {e}", file=sys.stderr)
        return None

    if not isinstance(data, dict):
        return None
    try:
        return CriticalSection(
            label=str(data.get("label", "")),
            until=float(data["until"]),
            declared_at=float(data.get("declared_at", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as e:
        print(f"⚠️ MACF: mask declaration missing its expiry, delivering as if unmasked: {e}", file=sys.stderr)
        return None


def load(session_id: Optional[str] = None) -> Mask:
    """The mask a NOTIFIER should enforce for this conversation.

    Always returns a Mask, never None: the floor applies whether or not the agent
    declared anything, and a caller that had to handle None would be a caller
    that could forget to.
    """
    return Mask(predicate=None, critical=read_declaration(session_id), session_id=session_id)
