"""Liveness for the notifier, so that NO NOTICE is distinguishable from NO EVENT.

An agent that cannot tell those apart must treat silence as unknown rather than
as quiet, and the correct response is to check the notifier -- not to assume the
world is calm. Publishing this is what makes that check possible.

Two rules from `macf_tools policy navigate service_supervision` are structural
here rather than described:

  * THE RECORD CARRIES ITS OWN CADENCE. If the reader hard-codes a staleness
    bound, two places configure one interval, they drift, and the drift is
    invisible in the direction that matters -- a bound that is too generous
    reports a dead component as healthy and nothing about that looks wrong.
  * FOUR VERDICTS, NOT TWO. Collapsing ABSENT into STALE reports every
    deployment that does not run this component as an outage. Treating
    UNREADABLE as ALIVE is how a supervisor reports green over a corpse, and it
    is the tempting default because "I could not read it" feels like "no news".

A heartbeat nobody ages out is a file, not a liveness signal, so the reader
ships in this module beside the writer.
"""
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

RECORD_NAME = "macf_notify_liveness.json"
DEFAULT_CADENCE_S = 30.0
STALENESS_MULTIPLIER = 3.0

ALIVE = "ALIVE"
STALE = "STALE"
ABSENT = "ABSENT"
UNREADABLE = "UNREADABLE"


def record_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / RECORD_NAME


@dataclass(frozen=True)
class Liveness:
    verdict: str
    stamped_at: Optional[float] = None
    cadence_s: Optional[float] = None
    age_s: Optional[float] = None
    last_delivery_at: Optional[float] = None
    deliveries: int = 0
    suppressions: int = 0
    failures: int = 0
    detail: str = ""

    @property
    def is_alive(self) -> bool:
        return self.verdict == ALIVE


def publish(
    cadence_s: float = DEFAULT_CADENCE_S,
    last_delivery_at: Optional[float] = None,
    deliveries: int = 0,
    suppressions: int = 0,
    failures: int = 0,
    now: Optional[float] = None,
) -> bool:
    """Write the liveness record. Returns False with a stated reason, never silently."""
    payload = {
        "stamped_at": now if now is not None else time.time(),
        "cadence_s": float(cadence_s),
        "pid": os.getpid(),
        "last_delivery_at": last_delivery_at,
        "deliveries": int(deliveries),
        "suppressions": int(suppressions),
        "failures": int(failures),
    }
    path = record_path()
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        # Atomic replace: a reader must never see a half-written record and
        # report UNREADABLE for a component that is perfectly healthy.
        os.replace(tmp, path)
        return True
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: liveness publish failed (notifier silence becomes ambiguous): {e}", file=sys.stderr)
        return False


def read(now: Optional[float] = None) -> Liveness:
    """Age the record out. Unknown is never healthy."""
    path = record_path()
    if not path.exists():
        return Liveness(
            verdict=ABSENT,
            detail="no liveness record -- this deployment may not run the notifier at all",
        )
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        return Liveness(verdict=UNREADABLE, detail=f"record unreadable: {e}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return Liveness(verdict=UNREADABLE, detail=f"record malformed: {e}")

    stamped = data.get("stamped_at")
    cadence = data.get("cadence_s")
    if not isinstance(stamped, (int, float)) or not isinstance(cadence, (int, float)) or cadence <= 0:
        return Liveness(
            verdict=UNREADABLE,
            detail="record lacks a usable timestamp or cadence -- liveness is UNKNOWN, which is not healthy",
        )

    current = now if now is not None else time.time()
    age = current - float(stamped)
    bound = float(cadence) * STALENESS_MULTIPLIER
    verdict = ALIVE if age <= bound else STALE
    return Liveness(
        verdict=verdict,
        stamped_at=float(stamped),
        cadence_s=float(cadence),
        age_s=age,
        last_delivery_at=data.get("last_delivery_at"),
        deliveries=int(data.get("deliveries") or 0),
        suppressions=int(data.get("suppressions") or 0),
        failures=int(data.get("failures") or 0),
        detail=f"aged against the record's OWN cadence ({cadence}s x {STALENESS_MULTIPLIER})",
    )
