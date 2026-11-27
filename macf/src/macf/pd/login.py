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
from typing import Callable, Dict, Iterable, Optional

#: The event the daemon records.
EVENT = "pd_login_state"
#: A grant this close to its end reads ``expiring``: three days leaves a weekend to log in again.
from macf.pd.interface import EXPIRING_DAYS  # noqa: E402 -- the declaration's default, kept as one number
EXPIRING_S = EXPIRING_DAYS * 86400.0
#: How often the daemon reads the credential.
POLL_S = 3600.0
#: The longest the daemon goes without recording the verdict, changed or not.
RECORD_EVERY_S = 86400.0
#: The notice that tells the agent its login is near its end, or past it (#1161).
NOTICE = "pd_login_expiring"
#: Each warning, recorded before its notice is raised, so a restarted daemon doesn't warn twice.
EVENT_WARNED = "pd_login_warned"
#: The second warning's time before the end; the first is the warning window, the last the end itself.
LAST_DAY_S = 86400.0


def warn_steps(expiring_s: float = EXPIRING_S) -> list:
    """The times before a grant's end at which the agent is warned, earliest first: the warning
    window, one day, and the end. A window of a day or less leaves out the one-day step."""
    if expiring_s > LAST_DAY_S:
        return [expiring_s, LAST_DAY_S, 0.0]
    if expiring_s > 0:
        return [expiring_s, 0.0]
    return [0.0]


def warn_step(seconds_left: float, expiring_s: float = EXPIRING_S) -> int:
    """How many of the warning steps a grant with *seconds_left* has reached: 0 outside the window,
    the number of steps once it has ended."""
    return sum(1 for t in warn_steps(expiring_s) if seconds_left <= t)

#: ``unknown``: no date to judge (an API key, a credential without the field, none reachable, or
#: one of several on a shared macOS login). ``error``: the check itself raised.
STATES = ("ok", "expiring", "expired", "unknown", "error")


def _seconds(value) -> Optional[float]:
    """An expiry as the client stores it (milliseconds since the epoch), in seconds; None if absent."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value / 1000.0


def assess(raw: Optional[str], now: float, why_unread: str = "no credential reachable",
           expiring_s: float = EXPIRING_S) -> Dict[str, object]:
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
    elif left <= expiring_s:
        state, detail = "expiring", f"the login's refresh grant ends in {hours} h"
    else:
        state, detail = "ok", f"the login's refresh grant ends in {round(left / 86400.0, 1)} days"
    return {"state": state, "refresh_expires_at": ends, "hours_left": hours, "detail": detail}


def read_assessment(now: Optional[float] = None,
                    reader: Optional[Callable[[], str]] = None,
                    expiring_s: float = EXPIRING_S) -> Dict[str, object]:
    """Read the agent's own stored credential and assess it.

    On macOS the credential is in the Keychain, under one service, and there can be more than one
    entry: a session started without USER files its refreshed token under "unknown", and the
    original entry is never written again (#852). ``read_credential`` takes the newest entry that
    holds a token, which is the login in use; the "unknown" entry can be newer and empty, so newest
    alone is not enough (#1090). Agents that share one macOS login share that one Claude login, so
    that entry is every such agent's own (#936)."""
    from macf.budget import BudgetError, read_credential
    now = time.time() if now is None else now
    try:
        raw = (reader or read_credential)()
    except BudgetError as e:
        return assess(None, now, why_unread=getattr(e, "short", None) or "no credential reachable",
                      expiring_s=expiring_s)
    return assess(raw, now, expiring_s=expiring_s)


def warn_seconds(declaration) -> float:
    """The login warning window in seconds: the declaration's ``reports.warn_days``, else the default. One
    reading at every site that judges a login's expiry, so none of them can ignore the declaration (#1027)."""
    reports = getattr(declaration, "reports", None)
    return reports.warn_days * 86400.0 if reports else EXPIRING_S


def missing_login_env(unit) -> str:
    """Why a unit that can't log in probably can't: its declared environment lacks ``USER`` or ``LOGNAME``
    (on macOS the stored login is looked up by them), and what to add; empty when both are declared (#1073).
    *unit* is a declared unit, or None when no declaration read. Empty off macOS, where the stored login is a
    file and not looked up by them, so naming them would label a genuine expiry with a cause that isn't one."""
    from macf.pd.default_declaration import LOGIN_ENV_EFFECT, LOGIN_VARIABLES
    if unit is None or sys.platform != "darwin":
        return ""
    declared = unit.environment or {}
    lacking = [k for k in LOGIN_VARIABLES if k not in declared]
    if not lacking:
        return ""
    return (f"its declared environment lacks {', '.join(lacking)}, and {LOGIN_ENV_EFFECT}: add them to every "
            f"unit's environment, restart the daemon, then the unit (macf_tools policy read persistent_layer)")


def daemon_assessment(expiring_s: float = EXPIRING_S) -> Dict[str, object]:
    """What the daemon's check reads: ``read_assessment``, behind a name a test suite can stand in
    for, so no test daemon reads the developer's own credential."""
    return read_assessment(expiring_s=expiring_s)


class HostedLoginCheck:
    """The daemon's login check: read at start, then every ``POLL_S``; recorded when the state
    changes and at least every ``RECORD_EVERY_S``, so the log always holds a verdict under a day old."""

    def __init__(self, card: str, append: Callable[[str, dict], object],
                 assess_now: Optional[Callable[[], Dict[str, object]]] = None,
                 clock: Callable[[], float] = time.monotonic, expiring_s: float = EXPIRING_S,
                 raise_notice: Optional[Callable[[str, str], object]] = None,
                 warned_before: Optional[Callable[[], Iterable[dict]]] = None):
        self.card, self.append, self.assess_now, self.clock = card, append, assess_now, clock
        self.expiring_s = expiring_s
        #: Raises the agent's notice; None where no agent is served, and then nothing warns.
        self.raise_notice = raise_notice
        #: This log's ``pd_login_warned`` records, newest first.
        self.warned_before = warned_before
        #: (end date warned of, step reached); None until read back from the log.
        self._warned: Optional[tuple] = None
        self.last_poll: Optional[float] = None
        self.last_record: Optional[float] = None
        self.last_state: Optional[str] = None

    def tick(self) -> None:
        now = self.clock()
        if self.last_poll is not None and now - self.last_poll < POLL_S:
            return
        self.last_poll = now
        try:
            if self.assess_now:
                verdict = self.assess_now()
            elif self.expiring_s == EXPIRING_S:
                verdict = daemon_assessment()    # looked up here, with no argument, so a test can stand in
            else:
                verdict = daemon_assessment(self.expiring_s)   # looked up here, so a test can stand in
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
        self._warn(verdict)

    def _read_back(self) -> None:
        """The newest warning this agent's log holds, read once, so a restart doesn't repeat it."""
        self._warned = (None, 0)
        if self.warned_before is None:
            return
        try:
            for record in self.warned_before():
                data = record.get("data") or {}
                if data.get("agent") == self.card:
                    self._warned = (data.get("refresh_expires_at"), int(data.get("step") or 0))
                    return
        except Exception as e:  # noqa: BLE001 - an unreadable log costs at most one repeated warning
            print(f"⚠️ MACF: pd: earlier login warnings couldn't be read ({type(e).__name__}); "
                  f"one may be repeated", file=sys.stderr)

    def _warn(self, verdict: Dict[str, object]) -> None:
        """Warn the agent once at each step its login reaches: the warning window, a day, the end
        (#1161). A renewed login has a new end date, so its steps start again. A verdict with no
        date ("unknown", "error") warns of nothing: no date shows how near an end is."""
        if self.raise_notice is None:
            return
        ends, hours = verdict.get("refresh_expires_at"), verdict.get("hours_left")
        if not isinstance(ends, (int, float)) or not isinstance(hours, (int, float)):
            return
        if self._warned is None:
            self._read_back()
        warned_ends, warned_step = self._warned
        if warned_ends != ends:
            warned_step = 0
        step = warn_step(hours * 3600.0, self.expiring_s)
        if step <= warned_step:
            self._warned = (ends, warned_step)
            return
        self.append(EVENT_WARNED, {"agent": self.card, "step": step, "of": len(warn_steps(self.expiring_s)),
                                   "refresh_expires_at": ends, "hours_left": hours,
                                   "state": verdict.get("state"), "detail": verdict.get("detail")})
        self._warned = (ends, step)
        self.raise_notice(NOTICE, f"login:{step}:{int(ends)}")
