"""E7 scoring: arms from the stored rankings, the measures, day-resampled intervals.

    python3 score.py            development days: tunes A3's w, prints every figure, writes out/score_dev.json
    python3 score.py --sealed   sealed days with the w fixed on development days (NOT run in development)
"""
import bisect
import json
import math
import os
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e7lib as L  # noqa: E402

SEALED = "--sealed" in sys.argv
SPLIT = "sealed" if SEALED else "dev"
OUT = HERE / "out"
B = 10_000
AFTER = 10
W_GRID = [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0]
ARMS = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "AR"]
WRITE_BASH = re.compile(r"sed -i|>\s*\S|\btee\b|\bmv\b|\bcp\b|\brm\b|git (?:add|mv|rm|commit)")
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}")


def base(doc):
    return doc.split("#")[0] if doc else doc


# ---------------------------------------------------------------- naming an item in a tool call
class Namer:
    """Classifies each tool call that names an item: read, write, or other mention (fourth amendment:
    reads are opening or showing it; a note, edit, start or complete is a write)."""

    def __init__(self, calls, meta):
        self.calls = calls
        self.meta = meta
        self.cache = {}
        self.node_path = {f"kg:{c['node']}": c.get("path") for c in meta["cands"] if c["source"] == "kg"}
        self.span_bc = {f"span:{c['id']}": c.get("bc") for c in meta["cands"] if c["source"] == "span"}

    def spec(self, doc):
        kind, _, ident = doc.partition(":")
        if kind == "task":
            n = ident
            return ("task", n, re.compile(rf"task\s+(?:get|show|view|tree)\s+#?{n}\b"),
                    re.compile(rf"task\s+(?:note|start|complete|edit|update|pause|resume|archive|metadata|create)\b[^\n]{{0,40}}?#?\b{n}\b"),
                    re.compile(rf"#{n}\b|task\s+\w+\s+#?{n}\b"))
        if kind == "kg" and ident.isdigit():
            n = ident
            return ("idea", n, re.compile(rf"idea\s+(?:get|show)\s+#?{n}\b"),
                    re.compile(rf"idea\s+(?:update|edit|note|status|promote|link)\s+#?{n}\b"), re.compile(rf"idea[ #:]+{n}\b"))
        if kind == "kg":
            typ, _, rest = ident.partition(":")
            parts = rest.split("/")
            stem = next((p for p in parts if DATED.match(p)), parts[-1])
            if typ == "policies":
                stem = rest
            return ("file", stem, None, None, None)
        if kind == "span":
            bc = self.span_bc.get(doc)
            m = re.search(r"p_[0-9a-f]{8}", bc or "")
            return ("text", m.group(0), None, None, None) if m else ("none", None, None, None, None)
        if kind == "duty":
            return ("text", ident, None, None, None)
        return ("none", None, None, None, None)

    def marks(self, doc):
        """Per call index: 'r' read, 'w' write, 'm' other mention."""
        doc = base(doc)
        if doc in self.cache:
            return self.cache[doc]
        kind, key, rd, wr, mn = self.spec(doc)
        out = {}
        if key:
            for i, (c, tx) in enumerate(zip(self.calls.calls, self.calls.text)):
                if key not in tx:
                    continue
                if kind in ("task", "idea"):
                    if rd.search(tx):
                        out[i] = "r"
                    elif wr.search(tx):
                        out[i] = "w"
                    elif mn.search(tx):
                        out[i] = "m"
                elif kind == "file":
                    name = c["name"]
                    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        out[i] = "w"
                    elif name == "Bash" and WRITE_BASH.search(str(c["input"].get("command", ""))):
                        out[i] = "w"
                    else:
                        out[i] = "r"
                else:
                    out[i] = "r"
        self.cache[doc] = out
        return out


# ---------------------------------------------------------------- the arms
def form_arms(moms, ranks, meta, w, w6=None):
    cands = meta["cands"]

    def d1(c):
        s = cands[c]["source"]
        if s == "kg":
            return f"kg:{cands[c]['node']}"
        if s == "task":
            return f"task:{meta['task_of'][c]}"
        if s == "duty":
            return f"duty:{meta['duty_of'][c]}"
        return f"span:{c}"

    def d4(c):
        return f"task:{meta['task_of'][c]}#{c}" if cands[c]["source"] == "task" else d1(c)

    w6 = w if w6 is None else w6
    hist1, hist4 = [], []            # A1's and A4's uncorrected top items, previous moments
    picks2, picks6 = [], []          # (r, item) of A2's and A6's own picks
    for m, rk in zip(moms, ranks):
        top, ts = rk["top"], rk["top_s"]
        start = rk["ctx_start"]
        a1 = d1(top[0]) if top else None
        a4 = d4(top[0]) if top else None
        m["A1"], m["A4"] = a1, a4
        m["A5"] = d1(rk["notask"][0]) if rk["notask"] else None
        seen2 = {it for t, it in picks2 if t >= start}
        m["A2"] = next((d1(c) for c in top if d1(c) not in seen2), None)
        if m["A2"]:
            picks2.append((rk["r"], m["A2"]))
        n1 = Counter(hist1[-200:])
        best, bs = None, -math.inf
        for c, s in zip(top, ts):
            v = s - w * math.log1p(n1.get(d1(c), 0))
            if v > bs:
                best, bs = d1(c), v
        m["A3"] = best
        n4 = Counter(hist4[-200:])
        seen6 = {it for t, it in picks6 if t >= start}
        best, bs = None, -math.inf
        for c, s in zip(top, ts):
            it = d4(c)
            if it in seen6:
                continue
            v = s - w6 * math.log1p(n4.get(it, 0))
            if v > bs:
                best, bs = it, v
        m["A6"] = best
        if best:
            picks6.append((rk["r"], best))
        hist1.append(a1)
        hist4.append(a4)


def form_ar(moms, meta, calls, namer):
    """AR: the newest note of the task in progress; failing that, the most recently created artifact
    not named in the last 10 calls."""
    tev = sorted(meta["task_events"], key=lambda e: e["t"])
    tt = [e["t"] for e in tev]
    kg = sorted([c for c in meta["cands"] if c["source"] == "kg" and c["t"]], key=lambda c: -c["t"])
    for m in moms:
        j = bisect.bisect_left(tt, m["r"])
        state, latest = {}, {}
        for e in tev[:j]:
            if e["kind"] == "task_start":
                state[e["task"]] = "in"
            elif e["kind"] == "task_complete":
                state[e["task"]] = "done"
            if e["kind"] in ("task_note", "task_start"):
                latest[e["task"]] = e["t"]
        live = [(latest.get(k, 0), k) for k, v in state.items() if v == "in" and k in latest]
        if live:
            m["AR"] = f"task:{max(live)[1]}"
            continue
        k = calls.index_after(m["r"])
        m["AR"] = None
        for c in kg:
            if c["t"] >= m["r"]:
                continue
            doc = f"kg:{c['node']}"
            mk = namer.marks(doc)
            if not any(i in mk for i in range(max(0, k - 10), k)):
                m["AR"] = doc
                break


# ---------------------------------------------------------------- measures
def outcome(m, item, calls, namer, window):
    if not item:
        return None
    mk = namer.marks(item)
    k = calls.index_after(m["r"])
    after = [mk.get(i) for i in range(k, k + AFTER)]
    bw = window.get(base(item), 10)
    before = [mk.get(i) for i in range(max(0, k - bw), k)]
    read = "r" in after
    write = "w" in after
    return {"novel": read and not any(before), "read": read, "rw": read or write, "write": write}


def windows(calls, namer, items):
    """Per item: the larger of 10 calls and twice the median gap in calls between its consecutive
    mentions, the mentions taken on development days only."""
    dev = [L.split_of(t) == "dev" for t in calls.t]
    out, gaps_all = {}, []
    for it in items:
        idx = sorted(i for i in namer.marks(it) if dev[i])
        gaps = [b - a for a, b in zip(idx, idx[1:])]
        if gaps:
            g = median(gaps)
            gaps_all.append(g)
            out[it] = max(10, int(math.ceil(2 * g)))
        else:
            out[it] = 10
    return out, gaps_all


def boot_ratio(days_num_den, rng_w):
    num = rng_w @ days_num_den[:, 0]
    den = rng_w @ days_num_den[:, 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def interval(vals):
    v = vals[np.isfinite(vals)]
    if len(v) == 0:
        return (float("nan"), float("nan"))
    return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))


def summarize(sub, arm, rng_w_for):
    """Point figures and day-resampled intervals for one arm on one set of moments."""
    days = sorted({m["day"] for m in sub})
    res = {"n": len(sub), "days": len(days)}
    if not sub:
        return res
    items = [m[arm] for m in sub]
    cnt = Counter(items)
    res["top3"] = sum(n for _, n in cnt.most_common(3)) / len(sub)
    res["repeat_1h"] = sum(m[f"{arm}_rep"] for m in sub) / len(sub)
    W = rng_w_for(len(days))
    di = {d: i for i, d in enumerate(days)}
    for key in ("novel", "read", "rw", "write"):
        arr = np.zeros((len(days), 2))
        for m in sub:
            o = m[f"{arm}_o"]
            arr[di[m["day"]], 1] += 1
            arr[di[m["day"]], 0] += bool(o and o[key])
        res[key] = arr[:, 0].sum() / arr[:, 1].sum()
        res[key + "_ci"] = interval(boot_ratio(arr, W))
    # top-three share, resampled by day
    its = sorted(cnt)
    ii = {it: j for j, it in enumerate(its)}
    M = np.zeros((len(days), len(its)))
    for m in sub:
        M[di[m["day"]], ii[m[arm]]] += 1
    R = W @ M
    top3 = np.sort(R, axis=1)[:, -3:].sum(axis=1) / R.sum(axis=1)
    res["top3_ci"] = interval(top3)
    return res


def main():
    meta_pk = pickle.load(open(OUT / f"arms_{SPLIT}.pkl", "rb"))
    a0 = json.loads((OUT / ("a0_picks_sealed.json" if SEALED else "a0_picks.json")).read_text())
    a0 = [m for m in a0 if m["split"] == SPLIT]
    ranks = {round(r["ts"], 6): r for r in meta_pk["moments"]}
    meta = meta_pk["meta"]
    moms = sorted([m for m in a0 if round(m["ts"], 6) in ranks], key=lambda m: m["r"])
    dropped = [m for m in a0 if round(m["ts"], 6) not in ranks]
    rk = [ranks[round(m["ts"], 6)] for m in moms]
    calls = L.Calls()
    namer = Namer(calls, meta)
    for m in moms:
        # the Oct 20 index numbers its spans differently: its span ids are kept apart from the as-of index's
        old = lambda d: ("span0:" + d[5:]) if d and d.startswith("span:") else d  # noqa: E731
        m["A0"] = old(m.get("a0"))
        m["shown"] = old(m["doc"]) if m["outcome"] == "pushed" else None
        m["stratum"] = "placed" if m["outcome"] == "pushed" else ("crash" if m["crash"] else "timeout")

    def finish(w, w6=None):
        form_arms(moms, rk, meta, w, w6)
        items = {base(m[a]) for m in moms for a in ARMS if m.get(a)} | {m["shown"] for m in moms if m["shown"]}
        return items

    rng = np.random.default_rng(L.SEED)
    Wcache = {}

    def rng_w_for(nd):
        if nd not in Wcache:
            Wcache[nd] = np.random.default_rng(L.SEED).multinomial(nd, [1 / nd] * nd, size=B).astype(float)
        return Wcache[nd]

    form_ar(moms, meta, calls, namer)
    # ---- tune w (development only): A3's novel consult rate on its decision set, all moments pooled
    tuning = []
    if not SEALED:
        for w in W_GRID:
            items = finish(w)
            win, _ = windows(calls, namer, items)
            sub = [m for m in moms if m["A3"] and base(m["A3"]) != m["shown"]]
            rate = sum(bool((o := outcome(m, m["A3"], calls, namer, win)) and o["novel"]) for m in sub) / max(1, len(sub))
            tuning.append({"w": w, "n": len(sub), "novel": rate})
            print(f"tune w={w}: A3 novel {rate:.4f} on {len(sub)}", flush=True)
        best = max(tuning, key=lambda x: (round(x["novel"], 12), -x["w"]))
        w_star = best["w"]
    else:
        w_star = json.loads((OUT / "score_dev.json").read_text())["w_star"]
    items = finish(w_star)
    win, gaps = windows(calls, namer, items)
    for m in moms:
        for a in ARMS:
            m[f"{a}_o"] = outcome(m, m.get(a), calls, namer, win)
    by_t = sorted(moms, key=lambda m: m["r"])
    for a in ARMS:
        hist = []
        for m in by_t:
            m[f"{a}_rep"] = bool(m.get(a)) and any(m["r"] - t <= 3600 and it == m[a] for t, it in hist)
            if m.get(a):
                hist.append((m["r"], m[a]))
            hist = [(t, it) for t, it in hist if m["r"] - t <= 3600]
        # files changed after their moment
        for m in moms:
            it = m.get(a)
            p = namer.node_path.get(base(it)) if it else None
            m[f"{a}_changed"] = bool(p and os.path.exists(p) and os.path.getmtime(p) > m["r"])

    results = {"w_star": w_star, "tuning": tuning, "split": SPLIT, "dropped_no_text": len(dropped),
               "dropped_by_type": dict(Counter(m["moment"] for m in dropped)),
               "gaps": {"items_with_gaps": len(gaps), "median_of_medians": median(gaps) if gaps else None,
                        "windows_over_10": sum(1 for v in win.values() if v > 10), "items": len(win),
                        "window_quartiles": [float(np.percentile(list(win.values()), q)) for q in (25, 50, 75, 90, 100)]},
               "table": [], "h73": [], "changed": []}
    types = ["T1", "T2", "T5", "all"]
    strata = ["placed", "nothing", "crash", "timeout", "all"]
    for a in ARMS:
        for ty in types:
            for stt in strata:
                base_set = [m for m in moms if m.get(a) and (ty == "all" or m["moment"] == ty)
                            and (stt == "all" or m["stratum"] == stt or (stt == "nothing" and m["outcome"] == "failed"))]
                for setname, sub in (("all", base_set), ("decision", [m for m in base_set if base(m[a]) != m["shown"]])):
                    r = summarize(sub, a, rng_w_for)
                    r.update({"arm": a, "type": ty, "stratum": stt, "set": setname})
                    results["table"].append(r)
    # H7.3: paired A3 minus A1 novel consult rate on the decision set, per moment type, days resampled
    for ty in types:
        sub = [m for m in moms if ty == "all" or m["moment"] == ty]
        days = sorted({m["day"] for m in sub})
        di = {d: i for i, d in enumerate(days)}
        W = rng_w_for(len(days))
        arr3, arr1, arrI3, arrI1 = (np.zeros((len(days), 2)) for _ in range(4))
        for m in sub:
            i = di[m["day"]]
            in3 = m["A3"] and base(m["A3"]) != m["shown"]
            in1 = m["A1"] and base(m["A1"]) != m["shown"]
            if in3:
                arr3[i] += (m["A3_o"]["novel"], 1)
            if in1:
                arr1[i] += (m["A1_o"]["novel"], 1)
            if in3 and in1:
                arrI3[i] += (m["A3_o"]["novel"], 1)
                arrI1[i] += (m["A1_o"]["novel"], 1)
        for name, x3, x1 in (("each arm's decision set", arr3, arr1), ("both arms off the shown item", arrI3, arrI1)):
            diff = boot_ratio(x3, W) - boot_ratio(x1, W)
            lo, hi = interval(diff)
            pt = x3[:, 0].sum() / max(1, x3[:, 1].sum()) - x1[:, 0].sum() / max(1, x1[:, 1].sum())
            results["h73"].append({"type": ty, "set": name, "n3": int(x3[:, 1].sum()), "n1": int(x1[:, 1].sum()),
                                   "days": len(days), "diff": pt, "ci": (lo, hi), "half_width": (hi - lo) / 2})
    for a in ARMS:
        for ty in types:
            sub = [m for m in moms if m.get(a) and base(m[a]) != m["shown"] and (ty == "all" or m["moment"] == ty)]
            kept = [m for m in sub if not m[f"{a}_changed"]]
            results["changed"].append({"arm": a, "type": ty, "n": len(sub), "share_changed": sum(m[f"{a}_changed"] for m in sub) / max(1, len(sub)),
                                       "novel_with": sum(m[f"{a}_o"]["novel"] for m in sub) / max(1, len(sub)),
                                       "novel_without": sum(m[f"{a}_o"]["novel"] for m in kept) / max(1, len(kept)), "n_without": len(kept)})
    ages = defaultdict(list)
    for m in moms:
        ages[m["moment"]].append((m["r"] - 1792534620) / 86400)
    results["a0_index_age_days_median"] = {k: median(v) for k, v in ages.items()}
    (OUT / f"score_{SPLIT}.json").write_text(json.dumps(results, indent=1, default=float))
    keep = ["day", "moment", "stratum", "outcome", "shown"] + [k for a in ARMS for k in (a, f"{a}_o", f"{a}_rep")]
    pickle.dump([{k: m.get(k) for k in keep} for m in moms], open(OUT / f"moms_{SPLIT}.pkl", "wb"))
    print(f"w* = {w_star}; written out/score_{SPLIT}.json", flush=True)


if __name__ == "__main__":
    main()
