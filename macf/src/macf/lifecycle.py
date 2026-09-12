"""One state-machine check, shared by every lifecycle the framework drives.

A lifecycle here is a flat dict mapping each state to the states it may move
to. ``task advance`` has driven plugin tasks through such a table since the
custom-models work; roles and duties use the same shape. The check lives in one
place so a second copy cannot drift from the first, which is the whole reason
the roles store reuses the task system's patterns as code rather than as rows.
"""
from typing import Dict, Iterable, Optional


class IllegalTransition(ValueError):
    """Raised when *current* → *new* is not in the machine."""

    def __init__(self, current: Optional[str], new: str, legal: Iterable[str]):
        self.current, self.new, self.legal = current, new, sorted(legal)
        super().__init__(f"Illegal transition: {current} → {new}. Legal: {set(self.legal)}")


def check_transition(machine: Dict[str, list], current: Optional[str], new: str) -> str:
    """Return *new* if the machine allows *current* → *new*; raise otherwise.

    A missing *current* means the machine's initial state, its first key. A
    *current* that is not a key at all is a corrupt record, and says so rather
    than being silently treated as initial.
    """
    if not isinstance(machine, dict) or not machine:
        raise ValueError("lifecycle machine must be a non-empty dict mapping state → [legal_next_states]")
    if current is None:
        current = next(iter(machine))
    if current not in machine:
        raise ValueError(f"Current state {current!r} is not a key in the lifecycle machine")
    legal = machine[current]
    if new not in legal:
        raise IllegalTransition(current, new, legal)
    return new
