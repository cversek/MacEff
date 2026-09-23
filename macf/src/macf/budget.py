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
        lim, source = parse_limits((fetch or fetch_reply)()), "endpoint"
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
    from macf.utils.environment import current_model
    model = current_model()
    family = model["display"].split(" ")[0].lower() if model["id"] != "unknown" else None
    for r in rows:  # the limits this agent's own work is filling right now
        r["spending"] = r["kind"] != "weekly_scoped" or (family is not None and r["label"].lower().startswith(family))
    return {"sampled_at": latest["t"], "age_min": round((now - latest["t"]) / 60, 1), "source": latest["source"],
            "model": model, "mode": mode, "limits": rows}


def format_status(st: dict, brief: bool = False) -> str:
    def one(r: dict) -> str:
        s = f"{r['label']} {r['percent']:g}%"
        if r["hours_left"] is not None:
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
    for r in st["limits"]:
        lines.append(f"  {one(r)}" + ("" if r.get("spending", True) else "  (not this model)"))
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
    """Refresh the sample from a hook, at most every MACEFF_BUDGET_AUTOSAMPLE_MIN minutes (default 10), and only for
    an agent that has sampled in the last week: nothing reads a credential on an installation that never asked to."""
    now = now or time.time()
    hist = samples(now=now)
    if not hist or now - hist[-1]["t"] < 60 * _env_float("MACEFF_BUDGET_AUTOSAMPLE_MIN", 10):
        return None
    return sample(now=now, fetch=lambda: fetch_reply(timeout=5))  # a hook may not wait 20 s


def _last_notices(now: float) -> dict:
    seen = {}
    for e in _recent("budget_notice", now):
        seen.setdefault(e["data"].get("key"), e["data"])
    return seen


def _key(row: dict, what: str) -> str:
    return f"{what}:{row['kind']}:{row['label']}:{row['resets_at']}"


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
        if not r.get("spending", True) or r["percent"] is None:
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
    return "💳 budget: " + "; ".join(out) + f" [{st['model']['display']}, {st['mode']['mode']}] (details: macf_tools budget status)"


def wall_warning(now: Optional[float] = None) -> Optional[str]:
    """Once per session window, when it reaches MACEFF_BUDGET_WALL percent (default 90): the window's exhaustion is a
    forced pause with no SessionStart after it, so the remedy is a checkpoint before the wall."""
    now = now or time.time()
    if not samples(now=now):
        return None  # no budget in use here: nothing to report, not a failure
    st = status(now)
    wall = _env_float("MACEFF_BUDGET_WALL", 90)
    for r in st["limits"]:
        if r["kind"] != "session" or r["percent"] is None or r["percent"] < wall:
            continue
        k = _key(r, "wall")
        if k in _last_notices(now):
            return None
        append_event("budget_notice", {"key": k, "value": r["percent"]})
        return (f"💳 5-hour window at {r['percent']:g}% (resets in {r['hours_left']:g}h). Work stops at the wall with no "
                f"recovery hook: write a task note or checkpoint for the work in hand now.")
    return None


def hook_lines(which: str, now: Optional[float] = None) -> Optional[str]:
    """Entry point for hooks. A GUARD: budget reporting must never take a hook down."""
    try:
        maybe_autosample(now)
        return prompt_notice(now) if which == "prompt" else wall_warning(now)
    except Exception as e:
        # Deliberately broad: this is a GUARD, not a handler. The hook continues without the budget line.
        print(f"⚠️ MACF: budget {which} line skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return None
