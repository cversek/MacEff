"""The subscription's rate limits as a budget the agent can see: sample, status, log, mode.

The same endpoint Claude Code's ``/usage`` screen calls returns a ``limits`` list:
``{kind: session | weekly_all | weekly_scoped, percent, severity, resets_at,
scope: {model: {display_name}}}``. That list is the general, stable form; every
other field of the reply is a named variant that churns, and none of it is read.

Credential custody (policy: credit_budget): the CLI's OAuth token is read for one
request and is never printed, logged, written or placed in an event. A sample
holds the kind, the scope's display name, the percent, the severity and the reset
time, nothing else. Where no credential is reachable the operator pastes what
``/usage`` shows (``sample --manual``).

State is derived from the events log (``budget_sampled``, ``budget_mode_set``),
never stored beside it. Reads are bounded by meaning: the longest window is a
week, so nothing older than ``HISTORY`` can bear on a current answer.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from macf.agent_events_log import append_event, read_events

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_BETA = "oauth-2025-04-20"
KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIAL_FILE = Path.home() / ".claude" / ".credentials.json"
HISTORY = dt.timedelta(days=8)
MIN_FETCH_INTERVAL = 180  # seconds between endpoint fetches unless --fresh
MODES = ("conserve", "normal", "burn")
SHORT = {"session": "session", "weekly_all": "week"}
RESET_GRAIN = 300  # seconds: reset times are compared rounded to this; see _reset_key
RATE_TAU_MIN = 120  # minutes: the burn-rate EWMA's time constant (MACEFF_BUDGET_RATE_TAU_MIN)
MIN_RATE_SPAN = 1800  # seconds of samples in one window before a rate is shown at all
BACKOFF_CAP_MIN = 120  # minutes: the longest wait between failed hook refreshes (MACEFF_BUDGET_BACKOFF_CAP_MIN)


class BudgetError(Exception):
    """A budget operation that cannot proceed; the message says what to do instead.

    ``short`` is the reason in a few words, for a hook line. A failed fetch also carries the HTTP ``status`` and the
    ``retry_after`` the reply asked for, in seconds, so the hooks can wait it out (#852).
    """

    def __init__(self, message: str, short: Optional[str] = None, status: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message)
        self.short, self.status, self.retry_after = short or message, status, retry_after


# ── credential ────────────────────────────────────────────────────────────────

def keychain_accounts() -> list[str]:
    """The accounts of the Keychain items named KEYCHAIN_SERVICE, most recently written first. Attributes only: no
    secret is read here.

    There can be more than one. Claude Code names the item's account after the login it runs as, and a session started
    without USER files its refreshed token under "unknown". The item it was first given is then never written again,
    and its token expires while it is still the first match for the service name (#852). The newest is the one in use.
    """
    try:
        r = subprocess.run(["security", "dump-keychain"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []  # noqa: MACEFF003 - no listing: read_token falls back to the first match for the service
    items, cur = [], {}
    for line in r.stdout.splitlines() + ["keychain: end"]:
        if line.startswith("keychain: "):
            if cur.get("svce") == KEYCHAIN_SERVICE and "acct" in cur:
                items.append((cur.get("mdat", ""), cur["acct"]))
            cur = {}
            continue
        m = re.search(r'"(acct|svce)"<blob>="(.*)"\s*$', line)
        if m:
            cur[m.group(1)] = m.group(2)
        m = re.search(r'"mdat"<timedate>=\S+\s+"(\d{14}Z)', line)
        if m:
            cur["mdat"] = m.group(1)
    return [acct for _, acct in sorted(items, reverse=True)]


def read_token() -> str:
    """The CLI's OAuth access token, for one request. Raises BudgetError when none is reachable."""
    raw = None
    if sys.platform == "darwin":
        for acct in keychain_accounts() or [None]:
            try:
                r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE]
                                   + (["-a", acct] if acct else []) + ["-w"],
                                   capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise BudgetError(f"Keychain read failed ({type(e).__name__}); use `budget sample --manual`",
                                  short="credential unreadable")
            if r.returncode == 0:
                raw = r.stdout
                break
    if raw is None and CREDENTIAL_FILE.exists():
        try:
            raw = CREDENTIAL_FILE.read_text()
        except OSError as e:
            raise BudgetError(f"credential file unreadable ({e.strerror}); use `budget sample --manual`",
                              short="credential unreadable")
    if raw is None:
        raise BudgetError("no Claude Code credential reachable (Keychain or ~/.claude/.credentials.json); "
                          "paste the /usage screen with `budget sample --manual`", short="no credential")
    try:
        tok = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken")
    except (json.JSONDecodeError, AttributeError):
        tok = None
    if not tok:
        raise BudgetError("the credential holds no OAuth access token; use `budget sample --manual`",
                          short="no token in the credential")
    return tok


def _retry_after_s(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """A Retry-After header in seconds. The header is a number of seconds or an HTTP date; None when absent or
    unreadable."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - (now or time.time()))
    except (TypeError, ValueError):
        return None  # noqa: MACEFF003 - an unreadable header is no header: the caller falls back to its backoff


def fetch_reply(token_source: Optional[Callable[[], str]] = None, timeout: float = 20) -> dict:
    """One request to the usage endpoint. The token lives only in this frame. The token source is looked up at call
    time, not bound as a default, so whatever replaces read_token (a test, a container reader) is the one used."""
    token_source = token_source or read_token
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token_source()}", "anthropic-beta": USAGE_BETA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise BudgetError(f"usage endpoint answered HTTP {e.code}; use `budget sample --manual`",
                          short=f"endpoint {e.code}", status=e.code,
                          retry_after=_retry_after_s(e.headers.get("Retry-After") if e.headers else None))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise BudgetError(f"usage endpoint unreachable or unreadable ({type(e).__name__}); use `budget sample --manual`",
                          short="endpoint unreachable")


# ── the limits list ──────────────────────────────────────────────────────────

def parse_limits(reply: dict) -> list[dict]:
    """Keep only the limits list, and only its declared fields."""
    out = []
    for l in reply.get("limits") or []:
        kind = l.get("kind")
        if kind not in ("session", "weekly_all", "weekly_scoped"):
            continue
        scope = ((l.get("scope") or {}).get("model") or {}).get("display_name") if kind == "weekly_scoped" else None
        pct = l.get("percent")
        out.append({"kind": kind, "scope": scope, "percent": float(pct) if pct is not None else None,
                    "severity": l.get("severity"), "resets_at": l.get("resets_at")})
    return out


def label(limit: dict) -> str:
    return limit["scope"] or SHORT.get(limit["kind"], limit["kind"])


def _next_clock(hhmm: str, now: dt.datetime) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now else t + dt.timedelta(days=1)


def parse_manual(text: str, now: Optional[dt.datetime] = None) -> list[dict]:
    """Parse a pasted summary: ``NAME PCT[%] [@RESET]`` repeated; NAME is session, week or a model name;
    RESET is HH:MM (next occurrence) or an ISO time. Example: ``session 24 @18:50 week 3% Fable 4``."""
    now = now or dt.datetime.now().astimezone()
    out = []
    for name, pct, reset in re.findall(r"([A-Za-z][\w.\- ]*?)\s+(\d+(?:\.\d+)?)%?(?:\s*@(\S+))?(?=\s|$|[,;·])", text):
        name = name.strip()
        low = name.lower()
        kind = "session" if low == "session" else "weekly_all" if low in ("week", "weekly", "all") else "weekly_scoped"
        resets = None
        if reset:
            resets = (_next_clock(reset, now) if re.fullmatch(r"\d{1,2}:\d{2}", reset)
                      else dt.datetime.fromisoformat(reset)).isoformat()
        out.append({"kind": kind, "scope": name if kind == "weekly_scoped" else None, "percent": float(pct),
                    "severity": None, "resets_at": resets})
    if not out:
        raise BudgetError("nothing parseable; write e.g. `session 24 @18:50 week 3 Fable 4`")
    return out


# ── samples ──────────────────────────────────────────────────────────────────

def _recent(event: str, now: float) -> Iterable[dict]:
    """Events of one type, newest first, no older than HISTORY."""
    floor = now - HISTORY.total_seconds()
    for e in read_events(reverse=True, scope="all"):
        if e.get("timestamp", 0) < floor:
            return
        if e.get("event") == event:
            yield e


def samples(since: Optional[float] = None, now: Optional[float] = None) -> list[dict]:
    """Samples, oldest first: ``{t, source, limits}``."""
    now = now or time.time()
    out = [{"t": e["timestamp"], "source": e["data"].get("source"), "limits": e["data"].get("limits", [])}
           for e in _recent("budget_sampled", now) if since is None or e["timestamp"] >= since]
    return list(reversed(out))


def sample(fresh: bool = False, manual: Optional[str] = None,
           fetch: Optional[Callable[[], dict]] = None, now: Optional[float] = None) -> dict:
    """Take a sample and append ``budget_sampled``. An endpoint fetch within MIN_FETCH_INTERVAL of the
    last one returns that one instead unless ``fresh``."""
    now = now or time.time()
    if manual is not None:
        lim, source = parse_manual(manual), "manual"
    else:
        last = next(iter(s for s in reversed(samples(now=now)) if s["source"] == "endpoint"), None)
        if last and not fresh and now - last["t"] < MIN_FETCH_INTERVAL:
            return dict(last, reused=True)
        try:
            lim, source = parse_limits((fetch or fetch_reply)()), "endpoint"
            if not lim:
                raise BudgetError("the reply carried no limits list; the endpoint may have changed. Use --manual",
                                  short="reply without limits")
        except Exception as e:  # noqa: BLE001 - recorded and re-raised, not handled
            # A failed fetch leaves a record, so the hooks wait from it instead of asking again on every call (#852)
            append_event("budget_sample_failed", _failure(e))
            raise
    append_event("budget_sampled", {"source": source, "limits": lim})
    return {"t": now, "source": source, "limits": lim, "reused": False}


def _failure(e: Exception) -> dict:
    """What a failed fetch leaves in the log: a short reason, the HTTP status and the Retry-After seconds. Nothing
    from the reply and nothing from the credential, as for a sample."""
    if isinstance(e, BudgetError):
        return {"reason": e.short, "status": e.status, "retry_after": e.retry_after}
    return {"reason": type(e).__name__, "status": None, "retry_after": None}


def failures_since(t: float, now: Optional[float] = None) -> Iterable[dict]:
    """The recorded failed fetches after time ``t``, newest first: ``{t, reason, status, retry_after}``."""
    now = now or time.time()
    for e in _recent("budget_sample_failed", now):
        if e["timestamp"] <= t:
            return
        yield {"t": e["timestamp"], **e["data"]}


def next_autosample(now: Optional[float] = None) -> Optional[float]:
    """When the hooks may next ask the endpoint; None for an agent with no sample this week, which they never ask for.

    The interval runs from the last attempt, not the last success (#852). Measured from a success it never closed once
    a fetch failed, so every hook call asked again, and on a busy session that kept the endpoint answering 429 for
    days. Each failure in a row since the newest sample doubles the wait, up to MACEFF_BUDGET_BACKOFF_CAP_MIN, and a
    reply that said how long to wait is waited out even past the cap.
    """
    now = now or time.time()
    hist = samples(now=now)
    if not hist:
        return None
    base = 60 * _env_float("MACEFF_BUDGET_AUTOSAMPLE_MIN", 10)
    fails = list(failures_since(hist[-1]["t"], now))
    if not fails:
        return hist[-1]["t"] + base
    wait = min(60 * _env_float("MACEFF_BUDGET_BACKOFF_CAP_MIN", BACKOFF_CAP_MIN), base * 2 ** min(len(fails) - 1, 16))
    if fails[0].get("retry_after"):
        wait = max(wait, float(fails[0]["retry_after"]))
    return fails[0]["t"] + wait


# ── mode ─────────────────────────────────────────────────────────────────────

def set_mode(mode: str, target: Optional[float] = None, by: Optional[str] = None,
             scope: Optional[str] = None) -> dict:
    if mode not in MODES:
        raise BudgetError(f"mode must be one of {', '.join(MODES)}")
    if mode != "burn" and (target is not None or by):
        raise BudgetError("--target and --by belong to burn")
    rec = {"mode": mode, "target": (target if target is not None else 100.0) if mode == "burn" else None,
           "by": by, "scope": scope}
    append_event("budget_mode_set", rec)
    return rec


def current_mode(now: Optional[float] = None) -> dict:
    """The operator's latest intent; a mode older than the weekly window has lapsed to normal."""
    e = next(iter(_recent("budget_mode_set", now or time.time())), None)
    return dict(e["data"], set_at=e["timestamp"]) if e else {"mode": "normal", "target": None, "by": None, "scope": None}


# ── status ───────────────────────────────────────────────────────────────────

def _reset_key(iso: Optional[str]) -> Optional[str]:
    """A limit's reset time as a window identity: rounded to RESET_GRAIN, in UTC.

    The endpoint's ``resets_at`` jitters by about a second from one reply to the next
    (``19:59:59.56``, ``20:00:00.25`` for the same reset), so an exact match splits one window
    into as many windows as there are samples (#497). Real windows are five hours or a week
    apart, so rounding to five minutes cannot merge two of them.
    """
    if not iso:
        return iso
    try:
        t = dt.datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return iso  # unparseable: fall back to the exact string rather than guess
    return dt.datetime.fromtimestamp(round(t / RESET_GRAIN) * RESET_GRAIN, dt.timezone.utc).isoformat()


def _window(limit: dict) -> str:
    """One window's identity, for comparison only: the limit, and its reset rounded to RESET_GRAIN."""
    return f"{limit['kind']}|{limit['scope']}|{_reset_key(limit['resets_at'])}"


def _hours_to(iso: Optional[str], now: float) -> Optional[float]:
    if not iso:
        return None
    return (dt.datetime.fromisoformat(iso).timestamp() - now) / 3600


def _rate(series: list[tuple[float, float]]) -> Optional[float]:
    """Percent per hour between the first and last point of a series."""
    if len(series) < 2 or series[-1][0] - series[0][0] < 60:
        return None
    return (series[-1][1] - series[0][1]) / ((series[-1][0] - series[0][0]) / 3600)


def _tau_hours() -> float:
    tau = _env_float("MACEFF_BUDGET_RATE_TAU_MIN", RATE_TAU_MIN)
    return (tau if tau > 0 else RATE_TAU_MIN) / 60


def ewma_rate(series: list[tuple[float, float]], tau_h: Optional[float] = None) -> Optional[float]:
    """Smoothed burn rate, percent per hour, of one window's ``[(t, percent)]``, oldest first.

    Percentages arrive as whole numbers from samples about ten minutes apart, so the rate between
    neighbours jumps between 0 and several percent an hour. Between two samples the rate is taken
    as constant, and the result is its exponentially weighted mean over time: each interval's rate
    weighs the integral of ``exp(-age / tau)`` across the interval, age measured from the newest
    sample. Integrating matters for uneven gaps: an overnight interval is mostly old, and weighting
    it by its end alone would let one long, stale interval outvote the recent hours. No seed value
    is needed. None until the window's samples span MIN_RATE_SPAN, because one sample is a
    position, not a speed.
    """
    if len(series) < 2 or series[-1][0] - series[0][0] < MIN_RATE_SPAN:
        return None
    tau_s = (tau_h or _tau_hours()) * 3600
    newest = series[-1][0]
    num = den = 0.0
    for (t0, p0), (t1, p1) in zip(series, series[1:]):
        if t1 <= t0 or p1 < p0:
            continue  # a fall cannot happen inside one window; never count it as negative burn
        weight = math.exp(-(newest - t1) / tau_s) - math.exp(-(newest - t0) / tau_s)
        num += weight * (p1 - p0) / ((t1 - t0) / 3600)
        den += weight
    return num / den if den > 0 else None


def format_rate(rate: float) -> str:
    """A burn rate for a one-line display, to two significant figures.

    So 0.346 shows as 0.35, 2.43 as 2.4 and 12.4 as 12. Two figures, because even pace for a
    weekly cap is about 0.6%/hr: one figure rounded 0.55 to 0.94 all to "0.6" to "0.9", and 0.95 to
    1.49 all to "1", hiding the difference between on pace and half again over. Rounding happens
    first, so 0.996 shows as 1.0, and 9.96 as 10. Zero and anything below it show as 0.
    """
    if rate <= 0:
        return "0"
    def digits(x: float) -> int:  # decimal places that keep this many significant figures
        return 1 - math.floor(math.log10(x))
    v = round(rate, digits(rate))
    return f"{v:.{max(0, digits(v))}f}" if v > 0 else "0"


def status(now: Optional[float] = None) -> dict:
    now = now or time.time()
    hist = samples(now=now)
    if not hist:
        raise BudgetError("no samples yet; run `budget sample` (or `budget sample --manual`)")
    latest = hist[-1]
    mode = current_mode(now)
    rows = []
    for l in latest["limits"]:
        key = _window(l)  # one window: same limit, same reset (within RESET_GRAIN; see _reset_key)
        window = [(s["t"], x["percent"]) for s in hist for x in s["limits"]
                  if _window(x) == key and x["percent"] is not None]
        hour = [p for p in window if p[0] >= now - 3600]
        left = _hours_to(l["resets_at"], now)
        r_hour, r_window, r_ewma = _rate(hour), _rate(window), ewma_rate(window)
        # The projection runs the smoothed rate over every hour still to come. The last hour alone is
        # a reading, not a pace: one quiet hour after a busy night once projected zero growth over
        # the 79 hours left, and the number was quoted as if it were the week's outlook.
        pace = r_ewma if r_ewma is not None else r_window
        open_ = left is not None and left > 0  # False once the window has reset since this sample (#852)
        row = {"label": label(l), "kind": l["kind"], "percent": l["percent"], "resets_at": l["resets_at"],
               "hours_left": round(left, 2) if left is not None else None,
               "reset_since_sample": left is not None and left <= 0,
               "rate_last_hour": round(r_hour, 2) if r_hour is not None else None,
               "rate_window": round(r_window, 2) if r_window is not None else None,
               "rate_ewma": round(r_ewma, 3) if r_ewma is not None else None,
               "projected_at_reset": (round(min(100.0, l["percent"] + pace * left), 1)
                                      if pace is not None and open_ and l["percent"] is not None else None),
               # the even pace: the rate that lands exactly on 100% at the reset
               "pace_even": (round(max(0.0, 100.0 - l["percent"]) / left, 2)
                             if left and left > 0 and l["percent"] is not None else None)}
        burn_here = mode["mode"] == "burn" and (mode.get("scope") or "week") in (row["label"], l["scope"])
        if burn_here and left and left > 0 and l["percent"] is not None:
            by_h = _hours_to(mode["by"], now) if mode.get("by") else left
            if by_h and by_h > 0:
                row["pace_needed"] = round((mode["target"] - l["percent"]) / by_h, 2)
        rows.append(row)
    from macf.utils.environment import current_model
    model = current_model()
    family = model["display"].split(" ")[0].lower() if model["id"] != "unknown" else None
    for r in rows:  # the limits this agent's own work is filling right now
        r["spending"] = r["kind"] != "weekly_scoped" or (family is not None and r["label"].lower().startswith(family))
    failure = next(iter(failures_since(latest["t"], now)), None)
    return {"sampled_at": latest["t"], "age_min": round((now - latest["t"]) / 60, 1), "source": latest["source"],
            "model": model, "mode": mode, "limits": rows, "last_failure": failure, "next_try": next_autosample(now)}


def _clock(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%H:%M")


def format_status(st: dict, brief: bool = False) -> str:
    def one(r: dict) -> str:
        s = f"{r['label']} {r['percent']:g}%"
        if r.get("reset_since_sample"):
            s += f" (window reset {-r['hours_left']:g}h ago, after this sample)"
        elif r["hours_left"] is not None:
            s += f" ({r['hours_left']:g}h to reset)"
        return s
    if brief:
        model = (st.get("model") or {}).get("display", "unknown")
        return " · ".join(one(r) for r in st["limits"]) + f"  [{model}, {st['mode']['mode']}, sample {st['age_min']:g} min old]"
    m = st.get("model") or {}
    lines = [f"running on: {m.get('display', 'unknown')} ({m.get('id', '?')}, from {m.get('source', '?')})",
             f"budget mode: {st['mode']['mode']}" + (f" (target {st['mode']['target']:g}% of {st['mode'].get('scope') or 'week'}"
             f"{' by ' + st['mode']['by'] if st['mode'].get('by') else ' by its reset'})" if st['mode']['mode'] == 'burn' else ""),
             f"latest sample: {st['age_min']:g} min old ({st['source']})"]
    fail = st.get("last_failure")
    if fail:
        lines.append(f"last refresh failed at {_clock(fail['t'])}: {fail.get('reason')}"
                     + (f"; the hooks ask again after {_clock(st['next_try'])}" if st.get("next_try") else "")
                     + "; `budget sample --manual` takes the numbers from /usage meanwhile")
    for r in st["limits"]:
        lines.append(f"  {one(r)}" + ("" if r.get("spending", True) else "  (not this model)"))
        bits = []
        if r["rate_last_hour"] is not None:
            bits.append(f"{r['rate_last_hour']:+g}%/h last hour")
        if r["rate_window"] is not None:
            bits.append(f"{r['rate_window']:+g}%/h this window")
        if r.get("rate_ewma") is not None:
            bits.append(f"{format_rate(r['rate_ewma'])}%/h smoothed")
        if r["projected_at_reset"] is not None:
            bits.append(f"at the smoothed pace {r['projected_at_reset']:g}% at reset")
        if r.get("pace_even") is not None:
            bits.append(f"{r['pace_even']:g}%/h lands on 100% at reset")
        if "pace_needed" in r:
            bits.append(f"needs {r['pace_needed']:+g}%/h for the target")
        if bits:
            lines.append("    " + "; ".join(bits))
    return "\n".join(lines)


def format_log(hist: list[dict]) -> str:
    rows = []
    for s in hist:
        t = dt.datetime.fromtimestamp(s["t"]).strftime("%Y-%m-%d %H:%M")
        rows.append(f"{t}  {s['source']:<8} " + " · ".join(f"{label(l)} {l['percent']:g}%" for l in s["limits"]
                                                         if l["percent"] is not None))
    return "\n".join(rows) or "(no samples in the last week)"


# ── plan ─────────────────────────────────────────────────────────────────────

HEAVY_TYPES = ("MISSION", "PHASE", "EXPERIMENT", "DETOUR")


def open_work() -> list[dict]:
    """Open heavy work the allowance could buy: scoped tasks first, then open mission/phase/experiment/detour tasks."""
    from macf.task.reader import TaskReader
    from macf.task.scope import get_scope_state
    try:
        scope = get_scope_state()
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: scope read failed (plan lists unscoped work only): {e}", file=sys.stderr)
        scope = {}
    out = []
    for t in TaskReader().read_all_tasks():
        if t.status == "completed":
            continue
        in_scope = scope.get(str(t.id)) == "active"
        if in_scope or (t.task_type or "") in HEAVY_TYPES:
            subject = re.sub(r"\x1b\[[0-9;]*m", "", t.subject)
            subject = re.sub(r"^\s*#\d+\s*(\[\^#\d+\]\s*)?", "", subject).strip()
            out.append({"id": str(t.id), "type": t.task_type or "TASK", "status": t.status, "scoped": in_scope,
                        "subject": subject})
    out.sort(key=lambda w: (not w["scoped"], w["status"] != "in_progress", int(w["id"]) if w["id"].isdigit() else 0))
    return out


def plan(now: Optional[float] = None) -> dict:
    """The status arithmetic plus the open work it could be spent on."""
    st = status(now)
    return dict(st, work=open_work())


def format_plan(p: dict, limit: int = 12) -> str:
    lines = [format_status(p), "", "open work (scoped first):"]
    for w in p["work"][:limit]:
        lines.append(f"  #{w['id']:<5} {w['type']:<10} {'👀 ' if w['scoped'] else ''}{w['subject'][:90]}")
    if len(p["work"]) > limit:
        lines.append(f"  ... {len(p['work']) - limit} more (macf_tools task tree)")
    if not p["work"]:
        lines.append("  (none open: an allowance with nothing worth spending it on is not a reason to invent work)")
    return "\n".join(lines)


# ── hooks: threshold lines, never a line per prompt ─────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def bands() -> list[float]:
    raw = os.environ.get("MACEFF_BUDGET_BANDS", "50,75,90")
    try:
        return sorted(float(x) for x in raw.split(",") if x.strip())
    except ValueError:
        return [50.0, 75.0, 90.0]


def maybe_autosample(now: Optional[float] = None) -> Optional[dict]:
    """Refresh the sample from a hook, at most every MACEFF_BUDGET_AUTOSAMPLE_MIN minutes (default 10) and later after
    a failure (``next_autosample``), and only for an agent that has sampled in the last week: nothing reads a
    credential on an installation that never asked to."""
    now = now or time.time()
    due = next_autosample(now)
    if due is None or now < due:
        return None
    return sample(now=now, fetch=lambda: fetch_reply(timeout=5))  # a hook may not wait 20 s


def _last_notices(now: float) -> dict:
    seen = {}
    for e in _recent("budget_notice", now):
        seen.setdefault(e["data"].get("key"), e["data"])
    return seen


def _key(row: dict, what: str) -> str:
    return f"{what}:{row['kind']}:{row['label']}:{_reset_key(row['resets_at'])}"


def prompt_notice(now: Optional[float] = None) -> Optional[str]:
    """One line when a limit this model is spending enters a new band since the last line, or, in burn, when the pace
    still needed moves by more than a point. None otherwise. Records what it showed so it does not repeat."""
    now = now or time.time()
    if not samples(now=now):
        return None  # no budget in use here: nothing to report, not a failure
    st = status(now)
    seen = _last_notices(now)
    out = []
    for r in st["limits"]:
        if not r.get("spending", True) or r["percent"] is None or r.get("reset_since_sample"):
            continue
        band = max([b for b in bands() if r["percent"] >= b], default=None)
        k = _key(r, "band")
        if band is not None and (seen.get(k) or {}).get("value") != band:
            append_event("budget_notice", {"key": k, "value": band})
            out.append(f"{r['label']} {r['percent']:g}% (≥{band:g}%, resets in {r['hours_left']:g}h)")
        if "pace_needed" in r:
            k = _key(r, "pace")
            prev = (seen.get(k) or {}).get("value")
            if prev is None or abs(r["pace_needed"] - prev) > 1:
                append_event("budget_notice", {"key": k, "value": r["pace_needed"]})
                obs = r["rate_last_hour"] if r["rate_last_hour"] is not None else r["rate_window"]
                out.append(f"burn {r['label']}: needs {r['pace_needed']:+g}%/h" + (f", running {obs:+g}%/h" if obs is not None else ""))
    if not out:
        return None
    return ("💳 budget: " + "; ".join(out) + f" [{st['model']['display']}, {st['mode']['mode']}{_stale(st)}]"
            " (details: macf_tools budget status)")


def _stale(st: dict) -> str:
    """A notice computed from a sample over an hour old says so: the refresh may be failing (#852)."""
    return f", sample {st['age_min'] / 60:.0f}h old" if st["age_min"] >= 60 else ""


def wall_warning(now: Optional[float] = None) -> Optional[str]:
    """Once per session window, when it reaches MACEFF_BUDGET_WALL percent (default 90): the window's exhaustion is a
    forced pause with no SessionStart after it, so the remedy is a checkpoint before the wall."""
    now = now or time.time()
    if not samples(now=now):
        return None  # no budget in use here: nothing to report, not a failure
    st = status(now)
    wall = _env_float("MACEFF_BUDGET_WALL", 90)
    for r in st["limits"]:
        if r["kind"] != "session" or r["percent"] is None or r["percent"] < wall or r.get("reset_since_sample"):
            continue
        k = _key(r, "wall")
        if k in _last_notices(now):
            return None
        append_event("budget_notice", {"key": k, "value": r["percent"]})
        return (f"💳 5-hour window at {r['percent']:g}% (resets in {r['hours_left']:g}h{_stale(st)}). Work stops at the "
                f"wall with no recovery hook: write a task note or checkpoint for the work in hand now.")
    return None


def hook_lines(which: str, now: Optional[float] = None) -> Optional[str]:
    """Entry point for hooks. Two GUARDS: budget reporting must never take a hook down, and a failed refresh must not
    take the notices with it (#852). They are computed from the newest sample either way, and say how old it is."""
    try:
        maybe_autosample(now)
    except Exception as e:
        # Deliberately broad: a GUARD, not a handler. sample() has already recorded the failure for the backoff.
        print(f"⚠️ MACF: budget refresh skipped: {type(e).__name__}: {e}", file=sys.stderr)
    try:
        return prompt_notice(now) if which == "prompt" else wall_warning(now)
    except Exception as e:
        # Deliberately broad: this is a GUARD, not a handler. The hook continues without the budget line.
        print(f"⚠️ MACF: budget {which} line skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return None



def weekly_usage(now: Optional[float] = None) -> Optional[str]:
    """The all-models weekly limit and its burn rate, "42% (2%/hr)", for the hooks' lines.

    The percent is the newest sample's, the same record ``budget status`` reports. The rate is
    ``ewma_rate`` over that window's samples, read back no further than four time constants (eight
    hours by default; older samples weigh under 2%), so a hook pays a few milliseconds and not the
    week's history. The rate is left out until the window's samples span half an hour. A sample
    more than an hour old says how old it is, and, when the refresh has failed since, why and what
    to run: "38% (57h old: endpoint 429; budget sample --manual)". Once the sample's week has reset,
    its percentage and rate describe a window that is over, so neither is shown (#852). None when
    there is no sample this week, or the newest carries no weekly limit. A GUARD, like hook_lines:
    the budget must never take a hook down.
    """
    try:
        now = now or time.time()
        floor = now - 4 * _tau_hours() * 3600
        points = []  # (t, percent, reset key), newest first
        for e in _recent("budget_sampled", now):
            w = next((l for l in e["data"].get("limits", []) if l.get("kind") == "weekly_all"), None)
            if w is not None and w.get("percent") is not None:
                points.append((e["timestamp"], w["percent"], _reset_key(w.get("resets_at"))))
            elif not points:
                return None  # noqa: MACEFF003 - the newest sample has no weekly limit to show
            if e["timestamp"] < floor:
                break
        if not points:
            return None  # noqa: MACEFF003 - no sample this week is the answer, not a failure to get one
        t_new, pct, key = points[0]
        age_h = (now - t_new) / 3600
        age = None
        if age_h >= 1:
            age = f"{age_h:.0f}h old"
            fail = next(iter(failures_since(t_new, now)), None)
            if fail:
                age += f": {fail.get('reason')}; budget sample --manual"
        try:
            left = _hours_to(key, now)
        except ValueError:
            left = None  # an unreadable reset time can't say the week is over
        if left is not None and left <= 0:
            return "reset since the last sample" + (f" ({age})" if age else "")
        rate = ewma_rate([(t, p) for t, p, k in reversed(points) if k == key])
        notes = [f"{format_rate(rate)}%/hr"] if rate is not None else []
        if age:
            notes.append(age)
        return f"{pct:g}%" + (f" ({', '.join(notes)})" if notes else "")
    except Exception as e:  # noqa: BLE001 - GUARD, not handler: see coding_standards
        # Deliberately broad: a GUARD, not a handler. The header goes out without it.
        print(f"⚠️ MACF: weekly usage skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return None

# ── the burn gate ─────────────────────────────────────────────────────────────

def burn_gate(auto_mode: bool, now: Optional[float] = None) -> dict:
    """Whether the Stop hook should hold the session to spend an expiring allowance: ``{"block": bool, "text": str}``.

    Holds only when every condition is true: AUTO_MODE; mode is burn; the burn's limit is below its target; its
    deadline and reset have not passed; and open work exists to spend it on. MANUAL_MODE never holds, and
    ``budget mode set normal`` always clears it. The hook applies the shared idle-stop failsafe.
    """
    now = now or time.time()
    off = {"block": False, "text": ""}
    if not auto_mode:
        return off
    mode = current_mode(now)
    if mode.get("mode") != "burn" or not samples(now=now):
        return off
    st = status(now)
    want = (mode.get("scope") or "week").lower()
    row = next((r for r in st["limits"] if r["label"].lower() == want or (r["kind"] == "weekly_all" and want == "week")), None)
    if row is None or row["percent"] is None:
        return off
    target = mode.get("target") or 100.0
    deadline_h = _hours_to(mode.get("by"), now) if mode.get("by") else row["hours_left"]
    if row["percent"] >= target or deadline_h is None or deadline_h <= 0:
        return off
    work = open_work()
    if not work:
        return off
    pace = f", needs {row['pace_needed']:+g}%/h" if "pace_needed" in row else ""
    lines = [f"💳 Burn mode: {row['label']} at {row['percent']:g}% of a {target:g}% target, {deadline_h:.1f} h to the "
             f"deadline{pace} [{st['model']['display']}]. Open work to spend it on:"]
    lines += [f"  #{w['id']} {w['subject'][:80]}" for w in work[:5]]
    lines.append("Continue with that work, or end the burn: macf_tools budget mode set normal")
    return {"block": True, "text": "\n".join(lines)}
