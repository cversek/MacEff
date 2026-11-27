"""E7 decisions on the sealed days, by the plan as amended (comments 7090680152, 7091041684, 7091084578,
7091208177, 7115512993). Reads out/moms_sealed.pkl written by score.py --sealed. Days resampled, seed 20261125.
Pairing: a difference between two arms uses the moments where both arms' items differ from the shown item."""
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "out"
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "sealed"
SEED, B = 20261125, 10_000
moms = pickle.load(open(OUT / f"moms_{SPLIT}.pkl", "rb"))


def base(doc):
    return doc.split("#")[0] if doc else doc


def W(nd):
    return np.random.default_rng(SEED).multinomial(nd, [1 / nd] * nd, size=B).astype(float)


def pct(v, lo, hi):
    v = v[np.isfinite(v)]
    return (float(np.percentile(v, lo)), float(np.percentile(v, hi))) if len(v) else (float("nan"),) * 2


def off(m, a):
    return bool(m.get(a)) and base(m[a]) != m["shown"]


def diff_novel(sub, a, b, level=95):
    days = sorted({m["day"] for m in sub})
    di = {d: i for i, d in enumerate(days)}
    xa, xb = np.zeros((len(days), 2)), np.zeros((len(days), 2))
    for m in sub:
        if off(m, a) and off(m, b):
            i = di[m["day"]]
            xa[i] += (bool(m[f"{a}_o"]["novel"]), 1)
            xb[i] += (bool(m[f"{b}_o"]["novel"]), 1)
    w = W(len(days))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = (w @ xa[:, 0]) / (w @ xa[:, 1]) - (w @ xb[:, 0]) / (w @ xb[:, 1])
    t = (100 - level) / 2
    n = int(xa[:, 1].sum())
    pt = xa[:, 0].sum() / max(1, n) - xb[:, 0].sum() / max(1, n)
    return {"n": n, "days": int((xa[:, 1] > 0).sum()), "diff": pt, "ci": pct(d, t, 100 - t),
            "rate_a": xa[:, 0].sum() / max(1, n), "rate_b": xb[:, 0].sum() / max(1, n)}


def top3_diff(sub, a, b):
    days = sorted({m["day"] for m in sub})
    di = {d: i for i, d in enumerate(days)}
    w = W(len(days))
    out = []
    for arm in (a, b):
        s = [m for m in sub if m.get(arm)]
        its = sorted({m[arm] for m in s})
        ii = {it: j for j, it in enumerate(its)}
        M = np.zeros((len(days), len(its)))
        for m in s:
            M[di[m["day"]], ii[m[arm]]] += 1
        R = w @ M
        out.append(np.sort(R, axis=1)[:, -3:].sum(axis=1) / R.sum(axis=1))
    pts = []
    for arm in (a, b):
        c = Counter(m[arm] for m in sub if m.get(arm))
        pts.append(sum(n for _, n in c.most_common(3)) / max(1, sum(c.values())))
    return {"a": pts[0], "b": pts[1], "diff": pts[0] - pts[1], "ci": pct(out[0] - out[1], 2.5, 97.5), "days": len(days)}


def top3(sub, a):
    c = Counter(m[a] for m in sub if m.get(a))
    return sum(n for _, n in c.most_common(3)) / max(1, sum(c.values()))


def novel_ci(sub, a, level):
    days = sorted({m["day"] for m in sub})
    di = {d: i for i, d in enumerate(days)}
    x = np.zeros((len(days), 2))
    for m in sub:
        if off(m, a):
            x[di[m["day"]]] += (bool(m[f"{a}_o"]["novel"]), 1)
    w = W(len(days))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (w @ x[:, 0]) / (w @ x[:, 1])
    t = (100 - level) / 2
    return x[:, 0].sum() / max(1, x[:, 1].sum()), pct(r, t, 100 - t), int(x[:, 1].sum())


f = lambda x: f"{x:+.3f}"  # noqa: E731
print(f"split {SPLIT}: {len(moms)} moments over {len({m['day'] for m in moms})} days")
for ty in ("T1", "T2", "T5"):
    sub = [m for m in moms if m["moment"] == ty]
    nothing = [m for m in sub if m["outcome"] == "failed"]
    print(f"\n=== {ty}: {len(sub)} moments, {len({m['day'] for m in sub})} days; nothing placed {len(nothing)} on {len({m['day'] for m in nothing})} days")
    h1 = top3_diff(sub, "A1", "A0")
    print(f"H7.1 top3 A1 {h1['a']:.3f} vs A0 {h1['b']:.3f}: diff {f(h1['diff'])} [{f(h1['ci'][0])}, {f(h1['ci'][1])}] -> {'VALIDATED' if h1['ci'][1] < -0.10 else 'not validated'}")
    for hyp, arm in (("H7.2", "A2"), ("H7.4", "A4"), ("H7.5", "A5")):
        r = diff_novel(sub, arm, "A1")
        ok = r["ci"][0] > 0
        print(f"{hyp} novel {arm} {r['rate_a']:.4f} vs A1 {r['rate_b']:.4f} (n {r['n']}, {r['days']} d): {f(r['diff'])} [{f(r['ci'][0])}, {f(r['ci'][1])}] -> {'VALIDATED' if ok else 'not validated'}")
    r = diff_novel(sub, "A3", "A1")
    t3 = top3(sub, "A3")
    ok = t3 <= 0.30 and r["ci"][0] >= -0.01
    print(f"H7.3 A3 top3 {t3:.3f} (<=0.30 {t3 <= 0.30}); novel A3-A1 {f(r['diff'])} [{f(r['ci'][0])}, {f(r['ci'][1])}] (lower >= -0.01 {r['ci'][0] >= -0.01}) -> {'VALIDATED' if ok else 'not validated'}")
    rate, ci, n = novel_ci(sub, "A6", 98.3)
    t6 = top3(sub, "A6")
    vs = diff_novel(sub, "A6", "AR")
    gate = rate >= 0.10 and ci[0] >= 0.05 and t6 <= 0.30 and vs["ci"][0] > 0
    print(f"E9 gate A6: novel {rate:.4f} 98.3% [{ci[0]:.4f}, {ci[1]:.4f}] n {n}; top3 {t6:.3f}; A6-AR {f(vs['diff'])} [{f(vs['ci'][0])}, {f(vs['ci'][1])}] -> {'PASSED' if gate else 'not passed'}")
    rate_n, ci_n, n_n = novel_ci(nothing, "A6", 98.3) if nothing else (float('nan'), (float('nan'),) * 2, 0)
    print(f"   nothing-placed beside it (not the clean check): A6 novel {rate_n:.4f} [{ci_n[0]:.4f}, {ci_n[1]:.4f}] n {n_n}")
