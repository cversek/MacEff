"""E7 development-phase report: prints the figures of out/score_dev.json and the per-day counts.
Sealed days are COUNTED only (moments per stratum per day); nothing on them is ranked or scored."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e7lib as L  # noqa: E402

OUT = L.HERE / "out"
r = json.loads((OUT / "score_dev.json").read_text())
trial, unit = L.trial_and_unit_events()
downs = L.down_intervals(unit)
moms = L.moments(trial)
print("== counts per day (pushed = placed; failed split crash/timeout by the unit's down intervals) ==")
cnt = defaultdict(Counter)
for m in moms:
    s = "placed" if m["outcome"] == "pushed" else ("crash" if any(a <= m["ts"] <= b for a, b in downs) else "timeout")
    cnt[(m["day"], m["split"])][(m["moment"], s)] += 1
for (day, sp) in sorted(cnt):
    c = cnt[(day, sp)]
    row = " ".join(f"{t}:{c[(t, 'placed')]}/{c[(t, 'crash')]}/{c[(t, 'timeout')]}" for t in ("T1", "T2", "T5"))
    print(f"{day} {sp:6s} total {sum(c.values()):4d}  (placed/crash/timeout) {row}")
for sp in ("dev", "sealed"):
    tot = Counter()
    for (day, s2), c in cnt.items():
        if s2 == sp:
            tot.update(c)
    print(sp, "totals", {f"{k[0]}-{k[1]}": v for k, v in sorted(tot.items())},
          "days", sum(1 for (d, s2) in cnt if s2 == sp),
          "crash days", sum(1 for (d, s2), c in cnt.items() if s2 == sp and any(k[1] == "crash" for k in c if c[k])))

print("\n== w tuning (A3 novel consult rate, reads only, on A3's decision set, all dev moments) ==")
for t in r["tuning"]:
    print(f"  w={t['w']}: {t['novel']:.4f} (n={t['n']})")
print("w* =", r["w_star"], "| moments without a reconstructed text:", r["dropped_no_text"], r["dropped_by_type"])
print("before-window gaps:", r["gaps"])
print("A0 index age, median days, by type:", {k: round(v, 1) for k, v in r["a0_index_age_days_median"].items()})

print("\n== H7.3: A3 minus A1 novel consult rate, paired by day resampling, 10,000 resamples ==")
for h in r["h73"]:
    print(f"  {h['type']:3s} {h['set']:30s} n3={h['n3']} n1={h['n1']} days={h['days']} diff={h['diff']:+.4f} "
          f"95% [{h['ci'][0]:+.4f}, {h['ci'][1]:+.4f}] half-width {h['half_width']:.4f}")

print("\n== table: arm type stratum set | n days | top3 [ci] | rep1h | novel [ci] | read [ci] | read+write | write ==")
for x in r["table"]:
    if x["n"] == 0:
        print(f"{x['arm']} {x['type']} {x['stratum']} {x['set']} | n 0")
        continue
    f = lambda k: f"{x[k]:.3f} [{x[k + '_ci'][0]:.3f},{x[k + '_ci'][1]:.3f}]"  # noqa: E731
    print(f"{x['arm']} {x['type']} {x['stratum']:7s} {x['set']:8s} | {x['n']:4d} {x['days']:2d}d | {f('top3')} | {x['repeat_1h']:.3f} | "
          f"{f('novel')} | {f('read')} | {f('rw')} | {f('write')}")
print("\n== files changed after their moment (decision set): share, novel with / without ==")
for c in r["changed"]:
    print(f"  {c['arm']} {c['type']}: n {c['n']}, changed {c['share_changed']:.3f}, novel {c['novel_with']:.4f} / {c['novel_without']:.4f} (n {c['n_without']})")
