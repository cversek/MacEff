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


GAPS_NAME = "macf_notify_gaps.json"
GAPS_RETAIN = 64


def gaps_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / GAPS_NAME


def note_start(cadence_s: float = DEFAULT_CADENCE_S, now: Optional[float] = None) -> Optional[dict]:
    """Called when the notifier starts. Records a GAP if it was away.

    THE POINT IS RECOVERABILITY OF THE SILENCE, not of the notices. A notifier
    that dies and restarts leaves an interval during which arrivals were real and
    nobody was told. Restarting quietly makes that interval indistinguishable
    from an interval in which nothing happened -- which is the exact confusion
    this whole subsystem exists to end, reappearing in the tool built to end it.

    What is LOST across a restart: notices for arrivals that occurred while down.
    They are not replayed, deliberately -- replaying them would deliver a burst of
    stale wakes and, worse, would re-notify arrivals the agent may already have
    seen by consulting the store on its own. The GAP is published instead, so the
    agent can decide for itself whether to go and look.

    Returns the gap record if one was written, else None.
    """
    current = now if now is not None else time.time()
    previous = read(now=current)
    gap = None
    if previous.verdict == STALE and previous.stamped_at is not None:
        gap = {
            "down_from": previous.stamped_at,
            "down_until": current,
            "duration_s": current - previous.stamped_at,
            "prior_cadence_s": previous.cadence_s,
            "note": "arrivals during this interval were NOT notified and are NOT replayed",
        }
        _append_gap(gap)
    elif previous.verdict == UNREADABLE:
        gap = {
            "down_from": None,
            "down_until": current,
            "duration_s": None,
            "prior_cadence_s": None,
            "note": "previous liveness record was unreadable -- downtime is UNKNOWN, not zero",
        }
        _append_gap(gap)
    publish(cadence_s=cadence_s, now=current)
    return gap


def _append_gap(gap: dict) -> None:
    existing = gaps()
    existing.append(gap)
    existing = existing[-GAPS_RETAIN:]
    path = gaps_path()
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(existing, fh)
        os.replace(tmp, path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: gap record write failed (a silence just became unrecoverable): {e}", file=sys.stderr)


def gaps() -> list:
    """Every recorded interval during which the notifier was not running.

    This is what an agent's recovery path reads to answer "was I not told, or was
    there nothing to tell?" -- two different facts that are otherwise identical
    from the inside.
    """
    path = gaps_path()
    if not path.exists():
        return []
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: gap record unreadable (downtime history unknown): {e}", file=sys.stderr)
        return []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: gap record malformed (downtime history unknown): {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        print("⚠️ MACF: gap record is not a list (downtime history unknown)", file=sys.stderr)
        return []
    return data


@dataclass(frozen=True)
class WatchdogResult:
    """Named rather than positional, because two of these fields are both strings.

    Returned as a tuple, `verdict` and `message` could be reordered without
    breaking a single caller loudly -- every unpacking site would keep working
    and silently swap the two. An exit code derived from the wrong field is a
    monitor that reports the wrong state in a way nothing detects.
    """

    exit_code: int
    verdict: str
    message: str


def watchdog_check(now: Optional[float] = None) -> "WatchdogResult":
    """The EXTERNAL check. Must be run by something that is not the notifier.

    A component that reports another component's death must run in a separate
    process from it -- putting this inside the notifier's own loop produces a
    checker that stops checking at the exact instant checking becomes necessary.
    This function is therefore deliberately a pure read with no daemon state: it
    is designed to be invoked by a scheduler that outlives the thing it watches.

    Returns a WatchdogResult. Four outcomes, not two, because "I could not
    measure it" is not "it is fine":
        0  ALIVE
        1  STALE           -- it ran, then stopped
        2  ABSENT          -- never ran; this deployment may not run it at all
        3  UNREADABLE      -- the instrument cannot tell; state is UNKNOWN
    """
    lv = read(now=now)
    codes = {ALIVE: 0, STALE: 1, ABSENT: 2, UNREADABLE: 3}
    if lv.verdict == ALIVE:
        msg = f"notifier ALIVE (last stamp {lv.age_s:.0f}s ago, cadence {lv.cadence_s}s, deliveries {lv.deliveries})"
    elif lv.verdict == STALE:
        msg = (f"notifier STALE -- last stamp {lv.age_s:.0f}s ago against a bound of "
               f"{lv.cadence_s * STALENESS_MULTIPLIER:.0f}s. Arrivals are not being announced.")
    elif lv.verdict == ABSENT:
        msg = "notifier ABSENT -- no record was ever written. This deployment may not run it."
    else:
        msg = f"notifier UNREADABLE -- {lv.detail}. State is UNKNOWN, which is not healthy."
    return WatchdogResult(exit_code=codes[lv.verdict], verdict=lv.verdict, message=msg)


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
