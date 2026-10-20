"""Step 5, Tier B: a learned semantic convolution (H6). s(t) = sum over lags of w_l x_(t-l), per source,
with the kernel learned on the development split; the leaky integrator's exponential decay is one
fixed shape in this family.

Each source (conv, task, kg) feeds the same sequence Tier A integrates (semantic_arms.walk). Its
kernel is piecewise over geometric lag bins counted in that source's own feeds: 1, 2-3, 4-7, ...,
128-255. Each bin contributes the unit mean of its feeds; q = c_x x + sum of w_(source, bin) times
that, c_x the gated depth. Bin sums come from prefix sums, so every moment costs O(1) per bin.
Weights by coordinate ascent on L1 MRR over the grid {0, 0.25, 0.5, 1, 2}, with the same 2-fold
time cross-validation as Tier A; all-dev weights are kept for Step 7, where H6 is judged.
Writes data/step5_tier_b.json.
"""
import json
from pathlib import Path

import numpy as np

import semantic_trace as st
from semantic_arms import SOURCES, setup, unit
from semantic_labels import Resolver, doc_of
from semantic_tier_a import GRID, evaluate

from kit_config import DATA
BINS = 8
COMPONENTS = [(s, b) for s in SOURCES for b in range(BINS)]


def feeds(events, cands, E, C, resolve):
    """Per source: the stream position and vector of every feed, in Tier A's order."""
    pos, vec = {s: [] for s in SOURCES}, {s: [] for s in SOURCES}
    for i, e in enumerate(events):
        if e["kind"] == "boundary":
            continue
        src = "conv" if e["scope"] == "conv" else "task"
        pos[src].append(i)
        vec[src].append(E[i])
        if e["kind"] == "tool":
            for key in sorted(st.consult_keys(e)):
                for cid in resolve(key):
                    s = "kg" if cands[cid]["source"] == "kg" else "task"
                    pos[s].append(i + 0.5)            # after the call itself, before the next event
                    vec[s].append(C[cid])
    out = {}
    for s in SOURCES:
        X = np.asarray(vec[s], dtype=np.float64)
        cs = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(X, axis=0)])
        out[s] = (np.asarray(pos[s]), cs)
    return out


def bin_vectors(fd, i):
    """The unit mean of each lag bin of each source, over feeds strictly before stream index i."""
    rows = []
    for s, b in COMPONENTS:
        p_, cs = fd[s]
        p = int(np.searchsorted(p_, i))
        hi, lo = p - (2 ** b) + 1, max(0, p - 2 ** (b + 1) + 1)
        rows.append(unit(cs[hi] - cs[lo]) if hi > lo else np.zeros(cs.shape[1]))
    return np.stack(rows)


def tune(moments, cached, docs):
    w = [1.0 if c == ("task", 0) else 0.0 for c in COMPONENTS]
    best = np.mean([v[0] for v in evaluate(moments, cached, w, docs).values()])
    for _ in range(3):
        moved = False
        for j in range(len(COMPONENTS)):
            for g in GRID:
                if g == w[j]:
                    continue
                trial = w[:j] + [g] + w[j + 1:]
                if not any(trial):
                    continue
                v = np.mean([x[0] for x in evaluate(moments, cached, trial, docs).values()])
                if v > best + 1e-9:
                    best, w, moved = v, trial, True
        if not moved:
            break
    return w


def main():
    events, cands, E, C, depth, dev, cand_t = setup()
    docs = [doc_of(c, events) for c in cands]
    moments = [m for m in dev if m["docs"]]
    resolve = Resolver(events, cands)
    fd = feeds(events, cands, E, C, resolve)
    bounds, t0 = st.boundaries(events), events[0]["t"]
    cached, at = {}, {m["i"] for m in moments}
    seen_last = {}                                    # candidate -> when it was last consulted
    for i, e in enumerate(events):
        if i in at:
            start = st.context_start(e["t"], bounds, t0)
            Q = np.vstack([E[i][None, :].astype(np.float64), bin_vectors(fd, i)])
            sc = (C @ Q.T).astype(np.float32)
            ok = cand_t < start
            in_ctx = [cid for cid, tc in seen_last.items() if tc >= start]
            if in_ctx:
                ok[in_ctx] = False
            cached[i] = (sc, ok, float(depth[i]))
        if e["kind"] == "tool":
            for key in st.consult_keys(e):
                for cid in resolve(key):
                    seen_last[cid] = e["t"]
    ordered = sorted(moments, key=lambda m: m["t"])
    halves = [ordered[: len(ordered) // 2], ordered[len(ordered) // 2:]]
    per, fold_w = {}, []
    for a, b in ((0, 1), (1, 0)):
        w = tune(halves[a], cached, docs)
        fold_w.append(w)
        per.update(evaluate(halves[b], cached, w, docs))
    all_w = tune(moments, cached, docs)
    tier_a = json.loads((DATA / "step4_tier_a.json").read_text())["table_L1"]
    strata = {"all": [m["i"] for m in moments]}
    for m in moments:
        strata.setdefault(m["kind"], []).append(m["i"])
    out = {"components": [f"{s}:lag{2 ** b}-{2 ** (b + 1) - 1}" for s, b in COMPONENTS], "fold_weights": fold_w, "all_dev_weights": all_w,
           "mrr_cv": {s: round(float(np.mean([per[i][0] for i in ids])), 4) for s, ids in strata.items()},
           "tier_a_for_comparison": {s: {a: tier_a[s][a]["mrr"] for a in ("prompt", "mix:gated:whole", "single:task:fast", "single:task:slow")}
                                     for s in strata if s in tier_a}}
    (DATA / "step5_tier_b.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("mrr_cv", "tier_a_for_comparison")}, indent=1))
    print("all-dev kernel (nonzero):", {c: w for c, w in zip(out["components"], all_w) if w})


if __name__ == "__main__":
    main()
