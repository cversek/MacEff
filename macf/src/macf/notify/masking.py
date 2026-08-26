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
    """

    def __init__(
        self,
        predicate: Optional[Callable[[Notice], bool]] = None,
        critical: Optional[CriticalSection] = None,
        deferred_path: Optional[Path] = None,
    ):
        self.predicate = predicate
        self.critical = critical
        self._deferred_path = deferred_path

    def deferred_path(self) -> Path:
        if self._deferred_path is not None:
            return self._deferred_path
        runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        return Path(runtime) / DEFERRED_NAME

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
