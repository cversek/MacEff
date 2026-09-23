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
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


class BudgetError(Exception):
    """A budget operation that cannot proceed; the message says what to do instead."""


# ── credential ────────────────────────────────────────────────────────────────

def read_token() -> str:
    """The CLI's OAuth access token, for one request. Raises BudgetError when none is reachable."""
    raw = None
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise BudgetError(f"Keychain read failed ({type(e).__name__}); use `budget sample --manual`")
        if r.returncode == 0:
            raw = r.stdout
    if raw is None and CREDENTIAL_FILE.exists():
        try:
            raw = CREDENTIAL_FILE.read_text()
        except OSError as e:
            raise BudgetError(f"credential file unreadable ({e.strerror}); use `budget sample --manual`")
    if raw is None:
        raise BudgetError("no Claude Code credential reachable (Keychain or ~/.claude/.credentials.json); "
                          "paste the /usage screen with `budget sample --manual`")
    try:
        tok = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken")
    except (json.JSONDecodeError, AttributeError):
        tok = None
    if not tok:
        raise BudgetError("the credential holds no OAuth access token; use `budget sample --manual`")
    return tok


def fetch_reply(token_source: Callable[[], str] = read_token) -> dict:
    """One request to the usage endpoint. The token lives only in this frame."""
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token_source()}", "anthropic-beta": USAGE_BETA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise BudgetError(f"usage endpoint answered HTTP {e.code}; use `budget sample --manual`")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise BudgetError(f"usage endpoint unreachable or unreadable ({type(e).__name__}); use `budget sample --manual`")


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
           fetch: Callable[[], dict] = fetch_reply, now: Optional[float] = None) -> dict:
    """Take a sample and append ``budget_sampled``. An endpoint fetch within MIN_FETCH_INTERVAL of the
    last one returns that one instead unless ``fresh``."""
    now = now or time.time()
    if manual is not None:
        lim, source = parse_manual(manual), "manual"
    else:
        last = next(iter(s for s in reversed(samples(now=now)) if s["source"] == "endpoint"), None)
        if last and not fresh and now - last["t"] < MIN_FETCH_INTERVAL:
            return dict(last, reused=True)
        lim, source = parse_limits(fetch()), "endpoint"
        if not lim:
            raise BudgetError("the reply carried no limits list; the endpoint may have changed. Use --manual")
    append_event("budget_sampled", {"source": source, "limits": lim})
    return {"t": now, "source": source, "limits": lim, "reused": False}


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

def _hours_to(iso: Optional[str], now: float) -> Optional[float]:
    if not iso:
        return None
    return (dt.datetime.fromisoformat(iso).timestamp() - now) / 3600


def _rate(series: list[tuple[float, float]]) -> Optional[float]:
    """Percent per hour between the first and last point of a series."""
    if len(series) < 2 or series[-1][0] - series[0][0] < 60:
        return None
    return (series[-1][1] - series[0][1]) / ((series[-1][0] - series[0][0]) / 3600)


def status(now: Optional[float] = None) -> dict:
    now = now or time.time()
    hist = samples(now=now)
    if not hist:
        raise BudgetError("no samples yet; run `budget sample` (or `budget sample --manual`)")
    latest = hist[-1]
    mode = current_mode(now)
    rows = []
    for l in latest["limits"]:
        key = (l["kind"], l["scope"], l["resets_at"])  # one window: same limit, same reset
        window = [(s["t"], x["percent"]) for s in hist for x in s["limits"]
                  if (x["kind"], x["scope"], x["resets_at"]) == key and x["percent"] is not None]
        hour = [p for p in window if p[0] >= now - 3600]
        left = _hours_to(l["resets_at"], now)
        r_hour, r_window = _rate(hour), _rate(window)
        pace = r_hour if r_hour is not None else r_window
        row = {"label": label(l), "kind": l["kind"], "percent": l["percent"], "resets_at": l["resets_at"],
               "hours_left": round(left, 2) if left is not None else None,
               "rate_last_hour": round(r_hour, 2) if r_hour is not None else None,
               "rate_window": round(r_window, 2) if r_window is not None else None,
               "projected_at_reset": (round(min(100.0, l["percent"] + pace * left), 1)
                                      if pace is not None and left is not None and l["percent"] is not None else None)}
        burn_here = mode["mode"] == "burn" and (mode.get("scope") or "week") in (row["label"], l["scope"])
        if burn_here and left and left > 0 and l["percent"] is not None:
            by_h = _hours_to(mode["by"], now) if mode.get("by") else left
            if by_h and by_h > 0:
                row["pace_needed"] = round((mode["target"] - l["percent"]) / by_h, 2)
        rows.append(row)
    return {"sampled_at": latest["t"], "age_min": round((now - latest["t"]) / 60, 1), "source": latest["source"],
            "mode": mode, "limits": rows}


def format_status(st: dict, brief: bool = False) -> str:
    def one(r: dict) -> str:
        s = f"{r['label']} {r['percent']:g}%"
        if r["hours_left"] is not None:
            s += f" ({r['hours_left']:g}h to reset)"
        return s
    if brief:
        return " · ".join(one(r) for r in st["limits"]) + f"  [{st['mode']['mode']}, sample {st['age_min']:g} min old]"
    lines = [f"budget mode: {st['mode']['mode']}" + (f" (target {st['mode']['target']:g}% of {st['mode'].get('scope') or 'week'}"
             f"{' by ' + st['mode']['by'] if st['mode'].get('by') else ' by its reset'})" if st['mode']['mode'] == 'burn' else ""),
             f"latest sample: {st['age_min']:g} min old ({st['source']})"]
    for r in st["limits"]:
        lines.append(f"  {one(r)}")
        bits = []
        if r["rate_last_hour"] is not None:
            bits.append(f"{r['rate_last_hour']:+g}%/h last hour")
        if r["rate_window"] is not None:
            bits.append(f"{r['rate_window']:+g}%/h this window")
        if r["projected_at_reset"] is not None:
            bits.append(f"at this pace {r['projected_at_reset']:g}% at reset")
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
