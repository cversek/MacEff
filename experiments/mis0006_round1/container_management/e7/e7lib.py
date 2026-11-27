"""E7 shared pieces: the trial's moments, the day split, crash intervals, moment texts, tool calls."""
import bisect
import json
import os
import pickle
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("E7_CACHE", HERE / "cache"))
LOG = Path.home() / ".maceff/agent_events_log.jsonl"
TZ = ZoneInfo("America/New_York")
RESTART = datetime.fromisoformat("2026-10-21T09:53:46-04:00").timestamp()   # analyze.restart_time(), checked below
END = datetime.fromisoformat("2026-11-22T21:32:00-05:00").timestamp()
DAY0 = datetime(2026, 10, 21).date()
SEED = 20261125
CA_PATH = re.compile(r"agent/(?:private|public)/(?:learnings|reflections|checkpoints|observations|experiments|reports|roadmaps)/[^\s\"']+")


def day_of(t):
    return datetime.fromtimestamp(t, TZ).date()


def split_of(t):
    """Oct 21 development, Oct 22 sealed, alternating by calendar day in America/New_York."""
    return "dev" if (day_of(t) - DAY0).days % 2 == 0 else "sealed"


def trial_and_unit_events():
    trial, unit = [], []
    with open(LOG, errors="replace") as f:
        for line in f:
            if '"knowledge_push_trial"' in line:
                try:
                    trial.append(json.loads(line))
                except ValueError:
                    pass
            elif '"push-trial"' in line and '"pd_unit_state"' in line:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") == "pd_unit_state" and (e.get("data") or {}).get("unit") == "push-trial":
                    unit.append(e)
    trial.sort(key=lambda e: e["timestamp"])
    unit.sort(key=lambda e: e["timestamp"])
    return trial, unit


def down_intervals(unit):
    """Intervals the unit was down or restarting: from a failed/stopped/starting state to the next running."""
    out, down_at = [], None
    for e in unit:
        s = e["data"]["state"]
        if s in ("failed", "stopped", "starting") and down_at is None:
            down_at = e["timestamp"]
        elif s == "running" and down_at is not None:
            out.append((down_at, e["timestamp"]))
            down_at = None
    if down_at is not None:
        out.append((down_at, float("inf")))
    return out


def incarnations(unit):
    """Start times of each incarnation: the 'running' state (first liveness, after the service's init)."""
    out, pid = [], None
    for e in unit:
        d = e["data"]
        if d["state"] == "running" and d.get("pid") != pid:
            out.append(e["timestamp"])
        if d["state"] == "running":
            pid = d.get("pid")
    return out     # a 'running' carried from a previous daemon (same pid) is not a restart


def moments(trial):
    """The record of E7: pushed or failed, from the restart to the end. Each with its request time."""
    out = []
    for e in trial:
        d = e.get("data") or {}
        if not d.get("moment") or d.get("outcome") not in ("pushed", "failed"):
            continue
        if not (RESTART <= e["timestamp"] <= END):
            continue
        lat = d.get("latency_ms")
        out.append({"ts": e["timestamp"], "moment": d["moment"], "outcome": d["outcome"], "reason": d.get("reason"),
                    "latency_ms": lat, "doc": (d.get("items") or [{}])[0].get("doc") if d.get("items") else None,
                    "found_by": (d.get("items") or [{}])[0].get("found_by") if d.get("items") else None,
                    "split": split_of(e["timestamp"]), "day": str(day_of(e["timestamp"]))})
    return out


def requests(trial):
    """Every hook call that reached the service (it catches up its trace on each): pushed, abstained
    by the service (not the hook's slash abstention), and failures past the budget (the service still
    ran them). Refused connections never reached it."""
    out = []
    for e in trial:
        d = e.get("data") or {}
        if not d.get("moment") or e["timestamp"] < RESTART - 1:
            continue
        o = d.get("outcome")
        if o == "abstained" and d.get("stratum") == "slash":
            continue
        if o == "failed" and "Timeout" not in str(d.get("reason")):
            continue
        lat = d.get("latency_ms")
        r = e["timestamp"] - (lat / 1000 if isinstance(lat, (int, float)) else 1.5)
        out.append(r)
    return sorted(out)


def load(name):
    with open(CACHE / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


class Calls:
    """Tool calls in time order, with the text a later call names an item by."""

    def __init__(self):
        calls = sorted(load("calls"), key=lambda c: (c["t"], c["ln"]))
        self.calls = calls
        self.t = [c["t"] for c in calls]
        self.text = [json.dumps(c["input"]) for c in calls]

    def index_after(self, t):
        return bisect.bisect_right(self.t, t)


def names_of(doc):
    """analyze.names_of: what a later tool call would name if it used this item."""
    kind, _, ident = doc.partition(":")
    if kind == "task":
        ident = ident.split("#")[0]
        return [rf"\btask (?:get|note|start|complete) #?{ident}\b", rf"\b#{ident}\b"]
    stem = ident.split(":")[-1].split("/")[-1]
    return [re.escape(stem)] if stem else []


def store_avail(store, calls, horizon=6 * 3600):
    """When each task or duty event came to exist. Its own time is the breadcrumb's t_, the second
    the turn's prompt was submitted, not when the note was written; a note written an hour into a
    turn carries the turn's start. The write time is the tool call that wrote it: the first Bash call
    at or after t_ that names the task (or duty) and a task/duty verb, preferring one that carries the
    note's opening words. Unmatched events keep t_ (reported)."""
    import bisect as _b
    bash = [(c["t"], str(c["input"].get("command", ""))) for c in calls.calls if c["name"] == "Bash"]
    bt = [b[0] for b in bash]
    matched = 0
    for e in store:
        e["avail"] = e["t"]
        ident = e.get("task") or e.get("duty")
        if not ident:
            continue
        body = e["text"].split(": ", 1)[-1] if e["scope"] == "task" else e["text"].split(": ", 1)[-1]
        snip = re.sub(r"[\"'`\\]", "", body)[:24].strip()
        j = _b.bisect_left(bt, e["t"] - 2)
        first = None
        while j < len(bash) and bash[j][0] <= e["t"] + horizon:
            cmd = bash[j][1]
            if ("task" in cmd or "duty" in cmd or "role" in cmd) and str(ident) in cmd:
                if first is None:
                    first = bash[j][0]
                if snip and snip in re.sub(r"[\"'`\\]", "", cmd):
                    first = bash[j][0]
                    break
            j += 1
        if first is not None:
            e["avail"] = max(e["t"], first) + 1.0
            matched += 1
    return matched
