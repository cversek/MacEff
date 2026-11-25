# E12: breakpoints vs matched controls vs every-20th call. Novel consult rate in the next 10 calls. Figures only.
import json, glob, os, sys, time, collections
import numpy as np
D = os.path.expanduser(os.environ.get("KIT_DATA", "~/mis0006_r1_data"))
SEED = 20261124
sys.path.insert(0, os.path.dirname(__file__))
import corpus

def ts(s):
    return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone if s else None

def norm(c):
    return set(corpus.norm_item(x) for x in c.get("reads", []))

rng = np.random.default_rng(SEED)
rows_out = []
for f in sorted(glob.glob(D + "/calls_*.jsonl")):
    rows = [json.loads(l) for l in open(f) if not json.loads(l).get("side")]
    calls = []; recovery = set(); since = 999
    for r in rows:
        if r["kind"] == "compact":
            since = 0
        elif r["kind"] == "call":
            if since < 25:
                recovery.add(len(calls))
            calls.append(r); since += 1
    n = len(calls)
    if n < 40:
        continue
    for i in range(25):
        recovery.add(i)
    kinds = {}
    for i, c in enumerate(calls):
        k = None
        if c.get("commit"): k = "commit"
        elif c.get("pr_open"): k = "pr_open"
        elif c.get("send"): k = "send"
        elif c.get("tool") == "Bash" and c.get("pytest"): k = "test_run"
        elif c.get("tool") == "Bash" and "task complete" in json.dumps(c): k = "task_completed"
        if k: kinds[i] = k
    cadence = {i for i in range(19, n, 20)}
    marked = set(kinds) | cadence
    def window_after(i):
        return set().union(*[norm(c) for c in calls[i + 1:i + 11]]) if i + 1 < n else set()
    def window_before(i):
        return set().union(*[norm(c) for c in calls[max(0, i - 10):i]]) if i else set()
    def nreads_before(i):
        return sum(1 for c in calls[max(0, i - 10):i] if c.get("reads"))
    eligible = [i for i in range(n) if all(abs(i - j) >= 10 for j in marked if j != i) and i < n - 10]
    def measure(i):
        a, b = window_after(i), window_before(i)
        return int(bool(a - b)), int(bool(a))
    for i, k in list(kinds.items()) + [(i, "cadence") for i in cadence]:
        if i >= n - 10:
            continue
        nov, plain = measure(i)
        rec = {"file": os.path.basename(f), "i": i, "kind": k, "day": time.strftime("%Y-%m-%d", time.localtime(ts(calls[i]["ts"]))),
               "recovery": i in recovery, "novel": nov, "plain": plain}
        if k != "cadence":
            q = i / n; nb = nreads_before(i)
            cand = [j for j in eligible if abs(nreads_before(j) - nb) <= 1]
            matched_reads = bool(cand)
            cand = cand or eligible
            if cand:
                j = min(cand, key=lambda j: (abs(j / n - q), rng.random()))
                cn, cp = measure(j)
                rec.update(ctrl_novel=cn, ctrl_plain=cp, ctrl_matched_reads=matched_reads)
            else:
                rec.update(ctrl_novel=None)
        rows_out.append(rec)
    with open(D + "/e12_progress.log", "a") as fh:
        fh.write("%s %s calls=%d breakpoints=%d\n" % (time.strftime("%H:%M:%S"), os.path.basename(f), n, len(kinds)))

json.dump(rows_out, open(D + "/e12_rows.json", "w"))
R = [r for r in rows_out if not r["recovery"]]
print("moments (recovery excluded):", collections.Counter(r["kind"] for r in R), "| recovery moments set apart:", sum(r["recovery"] for r in rows_out))
for k in ("commit", "pr_open", "test_run", "send", "task_completed", "cadence"):
    x = [r for r in R if r["kind"] == k]
    if x:
        print("%-15s n=%4d novel %.3f plain %.3f%s" % (k, len(x), np.mean([r["novel"] for r in x]), np.mean([r["plain"] for r in x]),
              (" | ctrl novel %.3f (no control %d, unmatched on reads %d)" % (np.mean([r["ctrl_novel"] for r in x if r.get("ctrl_novel") is not None]),
               sum(r.get("ctrl_novel") is None for r in x), sum(not r.get("ctrl_matched_reads", True) for r in x))) if k != "cadence" else ""))
def boot(per):
    dd = np.array([np.mean(v) for v in per.values()]); g = np.random.default_rng(SEED)
    b = [np.mean(g.choice(dd, len(dd))) for _ in range(10000)]
    return len(dd), dd.mean(), np.percentile(b, 2.5), np.percentile(b, 97.5)
bp = [r for r in R if r["kind"] != "cadence" and r.get("ctrl_novel") is not None]
per = collections.defaultdict(list)
for r in bp: per[r["day"]].append(r["novel"] - r["ctrl_novel"])
per = {d: v for d, v in per.items() if len(v) >= 5}
n, m, lo, hi = boot(per)
print("H12.1 breakpoint minus control, novel: days with >=5 breakpoints=%d, mean %+.3f, 95%% [%+.3f, %+.3f]" % (n, m, lo, hi))
# H12.2: cadence vs control: compare cadence day-mean to control day-mean
cad = collections.defaultdict(list); ctl = collections.defaultdict(list)
for r in R:
    if r["kind"] == "cadence": cad[r["day"]].append(r["novel"])
    elif r.get("ctrl_novel") is not None: ctl[r["day"]].append(r["ctrl_novel"])
per2 = {d: [np.mean(cad[d]) - np.mean(ctl[d])] for d in cad if d in ctl and len(cad[d]) >= 5 and len(ctl[d]) >= 5}
n2, m2, lo2, hi2 = boot(per2)
print("H12.2 cadence minus control, novel: days=%d, mean %+.3f, 95%% [%+.3f, %+.3f]" % (n2, m2, lo2, hi2))
