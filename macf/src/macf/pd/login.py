"""The agent's Claude login, checked without a model turn (#884).

An expired login is found today only when the session next needs to work: the client answers
"Login expired" and the core records the session unit failed (MIS-0002-R19). An idle agent can
sit expired for days. One container agent's refresh grant had lapsed twelve days before anyone
looked.

The client's stored credential carries the expiry of its refresh grant. This module reads that
date and the access token's, and nothing else: no token leaves the read, and none is written
anywhere. The daemon records the verdict as ``pd_login_state`` at start and on every change, and
at least once a day. The outside watch reads that event like any other the agent wrote, and
alerts on a login that has expired or will within ``EXPIRING_S``. ``macf_tools pd login`` prints
the same verdict, for a deployment checking a seat from outside it.

A grant can also be revoked before its date, which no date shows. That case still surfaces as
the session's own authentication failure.
"""
import json
import sys
import time
from typing import Callable, Dict, Optional

#: The event the daemon records.
EVENT = "pd_login_state"
#: A grant this close to its end reads ``expiring``: three days leaves a weekend to log in again.
EXPIRING_S = 3 * 86400
#: How often the daemon reads the credential.
POLL_S = 3600.0
#: The longest the daemon goes without recording the verdict, changed or not.
RECORD_EVERY_S = 86400.0

#: ``unknown``: no date to judge (an API key, a credential without the field, none reachable, or
#: one of several on a shared macOS login). ``error``: the check itself raised.
STATES = ("ok", "expiring", "expired", "unknown", "error")


def _seconds(value) -> Optional[float]:
    """An expiry as the client stores it (milliseconds since the epoch), in seconds; None if absent."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value / 1000.0


def assess(raw: Optional[str], now: float, why_unread: str = "no credential reachable") -> Dict[str, object]:
    """The login verdict from the stored credential's text: its state, the refresh grant's end in
    seconds since the epoch, the hours left (negative once past), and a line saying why. Only the two
    expiry dates are read."""
    if raw is None:
        return {"state": "unknown", "refresh_expires_at": None, "hours_left": None, "detail": why_unread}
    try:
        oauth = json.loads(raw).get("claudeAiOauth") or {}
        ends = _seconds(oauth.get("refreshTokenExpiresAt"))
    except (json.JSONDecodeError, AttributeError):
        return {"state": "unknown", "refresh_expires_at": None, "hours_left": None,
                "detail": "the credential is not the client's JSON"}
    if ends is None:
        return {"state": "unknown", "refresh_expires_at": None, "hours_left": None,
                "detail": "the credential states no refresh expiry"}
    left = ends - now
    hours = round(left / 3600.0, 1)
    if left <= 0:
        state, detail = "expired", f"the login's refresh grant ended {-hours} h ago"
    elif left <= EXPIRING_S:
        state, detail = "expiring", f"the login's refresh grant ends in {hours} h"
    else:
        state, detail = "ok", f"the login's refresh grant ends in {round(left / 86400.0, 1)} days"
    return {"state": state, "refresh_expires_at": ends, "hours_left": hours, "detail": detail}


def read_assessment(now: Optional[float] = None,
                    reader: Optional[Callable[[], str]] = None) -> Dict[str, object]:
    """Read the agent's own stored credential and assess it.

    On macOS the credential is in the Keychain, under one service, and there can be more than one
    entry: a session started without USER files its refreshed token under "unknown", and the
    original entry is never written again (#852). ``read_credential`` takes the newest, which is
    the login in use. Agents that share one macOS login share that one Claude login, so the newest
    entry is every such agent's own (#936)."""
    from macf.budget import BudgetError, read_credential
    now = time.time() if now is None else now
    try:
        raw = (reader or read_credential)()
    except BudgetError as e:
        return assess(None, now, why_unread=getattr(e, "short", None) or "no credential reachable")
    return assess(raw, now)


def daemon_assessment() -> Dict[str, object]:
    """What the daemon's check reads: ``read_assessment``, behind a name a test suite can stand in
    for, so no test daemon reads the developer's own credential."""
    return read_assessment()


class HostedLoginCheck:
    """The daemon's login check: read at start, then every ``POLL_S``; recorded when the state
    changes and at least every ``RECORD_EVERY_S``, so the log always holds a verdict under a day old."""

    def __init__(self, card: str, append: Callable[[str, dict], object],
                 assess_now: Optional[Callable[[], Dict[str, object]]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.card, self.append, self.assess_now, self.clock = card, append, assess_now, clock
        self.last_poll: Optional[float] = None
        self.last_record: Optional[float] = None
        self.last_state: Optional[str] = None

    def tick(self) -> None:
        now = self.clock()
        if self.last_poll is not None and now - self.last_poll < POLL_S:
            return
        self.last_poll = now
        try:
            verdict = (self.assess_now or daemon_assessment)()   # looked up here, so a test can stand in
        except Exception as e:  # noqa: BLE001 - a credential that won't read must not end the daemon
            # "error", not "unknown": the check itself broke, which the watch reports. "unknown" is
            # a login with no date to judge (an API key, an older credential), which it doesn't.
            verdict = {"state": "error", "refresh_expires_at": None, "hours_left": None,
                       "detail": f"the check failed: {type(e).__name__}"}
            print(f"⚠️ MACF: pd: the login check failed ({type(e).__name__})", file=sys.stderr)
        due = self.last_record is None or now - self.last_record >= RECORD_EVERY_S
        if verdict.get("state") != self.last_state or due:
            self.append(EVENT, {**verdict, "agent": self.card})
            self.last_state, self.last_record = verdict.get("state"), now
