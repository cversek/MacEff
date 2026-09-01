"""What a source, a detector and a sink must provide -- stated, and checked.

Phase 5 asks that adding an event source be a DECLARATION rather than a code
change. Registration hooks already existed; what did not exist was a statement of
what a registered object has to be, or any check that it is one.

WHY VALIDATE AT REGISTRATION RATHER THAN AT USE. A source is polled inside a
`try` that treats failure as non-fatal, deliberately: an optional input must not
stop the monitor observing the transcript, which is its primary job. That guard is
right, and it means a source registered with the wrong shape raises once per poll
into a log nobody is reading, and otherwise LOOKS REGISTERED FOREVER. The failure
is a source that never fires, which is indistinguishable from a source with
nothing to report -- the silence this whole subsystem exists to make impossible.

So the shape is checked when it is handed over, at a moment with a caller to blame
and a stack that names the registration site.

WHAT IS DELIBERATELY NOT CHECKED. Nothing here verifies that a source RETURNS the
right thing, because that cannot be known without polling it, and polling at
registration would give a source side effects at import time. Structural checks
answer "could this ever work"; they do not answer "does this work", and a check
that implied the second would be worse than none.
"""
from typing import Any

# The three roles, each stated as the question it answers:
#
#   DETECTOR -- is FED a transcript entry and says whether it means something.
#               Signature: (entry: dict) -> Detection | None
#
#   SOURCE   -- is ASKED what is new. Owns its own cursor or ledger, because only
#               it knows what "new" means for the thing it watches.
#               Interface: .poll() -> list[Detection]; .name -> str
#
#   SINK     -- is HANDED a detection that a source produced, and does something
#               outward with it. Transcript detectors do not reach sinks: they
#               already terminate in the event log, and routing them here would
#               silently widen what gets delivered to an agent.
#               Interface: callable(detection) -> None


class ContractError(TypeError):
    """A registered object cannot fulfil the role it was registered for."""


def _describe(obj: Any) -> str:
    name = getattr(obj, "__name__", None) or type(obj).__name__
    return f"{name!r}"


def validate_source(obj: Any) -> Any:
    """Return obj if it can be polled as a source; raise ContractError if not."""
    if not hasattr(obj, "poll") or not callable(obj.poll):
        raise ContractError(
            f"source {_describe(obj)} has no callable .poll(). A source is ASKED "
            f"what is new -- without poll() it would be registered, never fire, "
            f"and be indistinguishable from a source with nothing to report."
        )
    # `.name` IS NOT REQUIRED, AND THE FIRST VERSION OF THIS FUNCTION REQUIRED IT
    # ON A RATIONALE THAT WAS FALSE. It claimed the name is how a coalesced notice
    # says which stores to consult -- but coalescing reads `detection.data
    # ["source"]`, which a source puts there itself, and NOTHING in the daemon
    # reads `source.name` at all. A pre-existing test registering a deliberately
    # broken source, to prove a failing source cannot stop the monitor, is what
    # exposed it: the validator rejected a fixture that had every property the
    # daemon actually uses.
    #
    # The requirement was invented and then given a reason, which is worse than
    # inventing it plainly -- the reason is what stops the next reader checking.
    # A contract must demand exactly what its consumer exercises: more than that
    # is a barrier to the extensibility this phase exists to provide.
    return obj


def validate_sink(obj: Any) -> Any:
    """Return obj if it can receive detections; raise ContractError if not."""
    if not callable(obj):
        raise ContractError(
            f"sink {_describe(obj)} is not callable. A sink is HANDED a detection; "
            f"registering a non-callable yields a sink that fails once per "
            f"detection into stderr while appearing installed."
        )
    return obj


def validate_detector(obj: Any) -> Any:
    """Return obj if it can be fed transcript entries; raise ContractError if not."""
    if not callable(obj):
        raise ContractError(
            f"detector {_describe(obj)} is not callable. A detector is FED an "
            f"entry and returns a Detection or None."
        )
    return obj


__all__ = [
    "ContractError",
    "validate_detector",
    "validate_sink",
    "validate_source",
]
