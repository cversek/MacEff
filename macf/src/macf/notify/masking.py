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
import json
import os
import sys
import time
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
        """Hold a notice for later delivery. Idempotent on arrival id."""
        now = now if now is not None else time.time()
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

    def release(self) -> List[Notice]:
        """Return every held notice ONCE and clear the queue.

        Reconstructed from stored fields rather than replayed verbatim, so a
        deferred notice cannot carry anything a live one could not.
        """
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
