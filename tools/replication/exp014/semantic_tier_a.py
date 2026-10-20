"""Step 4: Tier A at every trigger, on the development split. H2 to H5, and the destroyed-trace control.

A query is linear in its parts, q = c_x * x + sum_k b_k * unit(s_k), so each moment's candidate
scores are cached once per part and any weighting is a cheap combination. Parts: the moment's own
text x, and for one gain (gated or constant) and one span (whole or reset) the six (source, rate)
states: conv, task and kg, each fast and slow. c_x is the moment's depth d when the gain is gated
(the null increment: a contentless prompt adds nothing), and 1 when it is constant.

Mixture weights are chosen by coordinate ascent on L1 MRR over the grid {0, 0.25, 0.5, 1, 2}, with
2-fold cross-validation by time inside the development split: tuned on one half, scored on the other,
so the development numbers are not fit to themselves. Weights tuned on all of dev are written for
Step 7. Rankings collapse to documents (semantic_labels.collapse); L1 per document.

Arms:
  prompt                 q = x
  single:<src>:<rate>    q = c_x x + unit(s), one state                         (H3)
  mix:<gain>:<span>      tuned mixture of the six states                        (H2 gain, H4 span)
  mix1:<rate>            tuned mixture of the three sources at one rate only    (H5)
  destroyed              mix:gated:whole's weights, states from a shuffled stream (the control)
Writes data/step4_tier_a.json.
"""
import hashlib
import json
from collections import defaultdict
from itertools import product
from pathlib import Path

import numpy as np

from semantic_arms import IDX, RATES, SOURCES, destroyed_order, setup, unit, walk
from semantic_labels import Resolver, collapse, doc_of

from kit_config import DATA
GRID = (0.0, 0.25, 0.5, 1.0, 2.0)
PARTS = [(s, r) for s in SOURCES for r in RATES]


def cache(moments, states, E, C, depth, cand_t, gain, span):
    """Per moment: candidate scores for x and each part, float32, and the allowed mask."""
    out = {}
    for m in moments:
        S, start, in_ctx = states[m["i"]]
        Q = np.stack([E[m["i"]].astype(np.float64)] + [unit(S[IDX[(s, r, gain, span)]]).astype(np.float64) for s, r in PARTS])
        sc = (C @ Q.T).astype(np.float32)
        ok = cand_t < start
        if in_ctx:
            ok[list(in_ctx)] = False
        out[m["i"]] = (sc, ok, float(depth[m["i"]]) if gain == "gated" else 1.0)
    return out


def rank_docs(sc, ok, w, docs, k=10):
    s = np.round(sc.astype(np.float64) @ w, 9)
    s[~ok] = -np.inf
    top = np.argpartition(-s, 200)[:200]
    top = top[np.lexsort((top, -s[top]))]
    return collapse([int(c) for c in top if np.isfinite(s[c])], docs, k)


def mrr(rank, rel):
    return next((1 / (j + 1) for j, d in enumerate(rank) if d in rel), 0.0)


def evaluate(moments, cached, weights, docs):
    """Per moment MRR, P@3 and nDCG@10 for one weight vector over [x, *PARTS]."""
    out = {}
    for m in moments:
        sc, ok, cx = cached[m["i"]]
        w = np.array([cx] + list(weights), dtype=np.float64)
        r, rel = rank_docs(sc, ok, w, docs), set(m["docs"])
        dcg = sum(1 / np.log2(j + 2) for j, d in enumerate(r) if d in rel)
        idcg = sum(1 / np.log2(j + 2) for j in range(min(len(rel), 10)))
        out[m["i"]] = (mrr(r, rel), sum(d in rel for d in r[:3]) / 3, dcg / idcg if idcg else 0.0)
    return out


def tune(moments, cached, docs, allowed_parts):
    """Coordinate ascent on mean MRR over the grid, only the allowed parts free, the rest at 0."""
    w = [1.0 if p in allowed_parts and p[1] == "fast" and p[0] == "conv" else 0.0 for p in PARTS]
    if not any(w):
        w[PARTS.index(allowed_parts[0])] = 1.0
    best = np.mean([v[0] for v in evaluate(moments, cached, w, docs).values()])
    for _ in range(3):
        moved = False
        for j, p in enumerate(PARTS):
            if p not in allowed_parts:
                continue
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
    return w, best


def cv(moments, cached, docs, allowed_parts):
    """2-fold by time: per moment metrics, each scored with weights tuned on the other half."""
    ordered = sorted(moments, key=lambda m: m["t"])
    halves = [ordered[: len(ordered) // 2], ordered[len(ordered) // 2:]]
    per, fold_w = {}, []
    for a, b in ((0, 1), (1, 0)):
        w, _ = tune(halves[a], cached, docs, allowed_parts)
        fold_w.append(w)
        per.update(evaluate(halves[b], cached, w, docs))
    return per, fold_w


def boot(diffs, seed, n=2000):
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    d = np.asarray(diffs)
    b = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1)
    return {"diff": round(float(d.mean()), 4), "ci95": [round(float(np.percentile(b, 2.5)), 4), round(float(np.percentile(b, 97.5)), 4)],
            "share_above_0": round(float((b > 0).mean()), 3), "n": len(d)}


def main():
    events, cands, E, C, depth, dev, cand_t = setup()
    docs = [doc_of(c, events) for c in cands]
    moments = [m for m in dev if m["docs"]]
    resolve = Resolver(events, cands)
    at = [m["i"] for m in moments]
    real = walk(events, cands, E, C, depth, at, resolve)
    shuffled = walk(events, cands, E, C, depth, at, resolve, order=destroyed_order(events))
    per, weights = {}, {}
    zero = [0.0] * len(PARTS)
    base = cache(moments, real, E, C, depth, cand_t, "gated", "whole")
    per["prompt"] = evaluate(moments, {i: (sc, ok, 1.0) for i, (sc, ok, _) in base.items()}, zero, docs)
    for gain, span in product(("gated", "const"), ("whole", "reset")):
        c = base if (gain, span) == ("gated", "whole") else cache(moments, real, E, C, depth, cand_t, gain, span)
        name = f"mix:{gain}:{span}"
        per[name], weights[name] = cv(moments, c, docs, PARTS)
        weights[name + ":all_dev"] = tune(moments, c, docs, PARTS)[0]
        if (gain, span) == ("gated", "whole"):
            for p in PARTS:
                per[f"single:{p[0]}:{p[1]}"] = evaluate(moments, c, [1.0 if q == p else 0.0 for q in PARTS], docs)
            for rate in RATES:
                per[f"mix1:{rate}"], weights[f"mix1:{rate}"] = cv(moments, c, docs, [p for p in PARTS if p[1] == rate])
            # the destroyed-trace control compares like with like: the same weights over the real
            # states and over states from a shuffled stream (an earlier version compared the
            # cross-validated mixture with all-dev weights on shuffled states, which is not)
            d_cache = cache(moments, shuffled, E, C, depth, cand_t, "gated", "whole")
            dw = weights[name + ":all_dev"]
            per["mix:gated:whole:in_sample"] = evaluate(moments, c, dw, docs)
            per["destroyed"] = evaluate(moments, d_cache, dw, docs)
            for p in PARTS:
                per[f"destroyed:single:{p[0]}:{p[1]}"] = evaluate(moments, d_cache, [1.0 if q == p else 0.0 for q in PARTS], docs)
    strata = defaultdict(list)
    t1 = sorted((m for m in moments if m["kind"] == "T1"), key=lambda m: (float(depth[m["i"]]), m["i"]))
    for j, m in enumerate(t1):
        strata[f"T1/depth{1 + 3 * j // len(t1)}"].append(m["i"])
    for m in moments:
        strata[m["kind"]].append(m["i"])
        strata["all"].append(m["i"])
        if m["kind"] == "T2":                 # H4: late in a long stretch of autonomous work
            strata["T2/n20" if m["n"] == 20 else "T2/n40" if m["n"] == 40 else "T2/n60+"].append(m["i"])
    table ={s: {arm: {k: round(float(np.mean([per[arm][i][j] for i in ids])), 4) for j, k in enumerate(("mrr", "p3", "ndcg10"))}
                 for arm in per} for s, ids in strata.items()}
    for s in table:
        table[s]["moments"] = len(strata[s])
    comparisons = {}
    pairs = [("prompt", "mix:gated:whole"), ("mix:const:whole", "mix:gated:whole"), ("mix:gated:reset", "mix:gated:whole"),
             ("destroyed", "mix:gated:whole:in_sample"), ("mix1:fast", "mix:gated:whole"), ("mix1:slow", "mix:gated:whole"),
             ("prompt", "single:task:fast"), ("prompt", "single:kg:fast")]
    pairs += [(f"destroyed:single:{s}:{r}", f"single:{s}:{r}") for s, r in PARTS]
    for s, ids in strata.items():
        comparisons[s] = {f"{b} minus {a}": boot([per[b][i][0] - per[a][i][0] for i in ids], f"{s}|{a}|{b}") for a, b in pairs}
    out = {"moments": len(moments), "parts": [f"{s}:{r}" for s, r in PARTS], "grid": GRID,
           "weights": weights, "table_L1": table, "comparisons_L1_mrr": comparisons}
    (DATA / "step4_tier_a.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    arms = ["prompt", "mix:gated:whole", "mix:const:whole", "mix:gated:reset", "mix1:fast", "mix1:slow", "destroyed"] + [f"single:{s}:{r}" for s, r in PARTS]
    for s in ["all", "T1", "T1/depth1", "T1/depth2", "T1/depth3", "T2", "T2/n20", "T2/n40", "T2/n60+", "T3", "T4", "T5"]:
        if s in table:
            print(f"{s:10s} n={table[s]['moments']:3d} " + " ".join(f"{a.replace('mix:', 'm:').replace('single:', 's:')}={table[s][a]['mrr']:.3f}" for a in arms))
    for s in ("all", "T1/depth1", "T1/depth3", "T2", "T3", "T5"):
        if s in comparisons:
            print(s)
            for k, v in comparisons[s].items():
                print(f"    {k:55s} {v['diff']:+.4f} {v['ci95']}")
    print("weights (all dev):", {k: v for k, v in out["weights"].items() if k.endswith("all_dev")})


if __name__ == "__main__":
    main()
