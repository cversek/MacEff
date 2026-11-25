# E13: this seat's real knowledge queries. Shipping (logged output) vs fixed grep vs BM25. Prints figures only.
import json, glob, os, re, sys, time, collections, random
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import corpus

D = os.path.expanduser(os.environ.get("KIT_DATA", "~/mis0006_r1_data"))
SEED = 20261124
SINCE = os.environ.get("E13_SINCE", "2026-10-25")

def ts(s):
    return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone if s else None

def sessions():
    for f in sorted(glob.glob(D + "/calls_*.jsonl")):
        rows = [json.loads(l) for l in open(f)]
        yield os.path.basename(f), [r for r in rows if not r.get("side")]

docs, idf, avg = corpus.load()
TITLES = [(re.sub(r"[^a-z0-9]+", " ", v["title"].lower()).strip(), k) for k, v in docs.items()]

def shipping_list(text):
    out = []
    for line in (text or "").splitlines():
        m = re.search(r"#0*(\d+)\b", line)
        if m and ("💡" in line or "idea" in line.lower()):
            it = "idea:%d" % int(m.group(1))
            if it not in out:
                out.append(it)
            continue
        m0 = re.match(r"\s+\S+\s+(\d{4}-\d{2}-\d{2}_\S+)", line)
        if m0 and "(deg" in line:
            pre = m0.group(1)
            hit = sorted(k for k, v in docs.items() if os.path.basename(v["path"]).startswith(pre))
            for k in hit[:1]:
                if k not in out:
                    out.append(k)
            if hit:
                continue
        m = re.match(r"\s+\S+\s+(.+?)\s*(\[|\(deg|$)", line)
        if m and "(deg" in line:
            t = re.sub(r"[^a-z0-9]+", " ", m.group(1).lower()).strip()[:30]
            for title, k in TITLES:
                if t and title.startswith(t) and k not in out:
                    out.append(k)
                    break
    return out

def qtext(raw):
    q = re.sub(r"--like\s+\S+", " ", raw)
    q = re.sub(r"--\S+(\s+\d+)?", " ", q)
    q = re.split(r"[|;&>]", q)[0]
    return q.replace('"', " ").replace("'", " ").replace("_", " ").strip()

# routine items: read after more than 20% of turns
turn_hits = collections.Counter(); n_turns = 0
for name, rows in sessions():
    calls = [r for r in rows if r["kind"] == "call"]
    pos = {id(r): i for i, r in enumerate(calls)}
    ci = 0
    for r in rows:
        if r["kind"] == "call":
            ci = pos[id(r)] + 1
        elif r["kind"] == "prompt":
            n_turns += 1
            seen = set()
            for c in calls[ci:ci + 10]:
                seen.update(corpus.norm_item(x) for x in c.get("reads", []))
            turn_hits.update(seen)
routine = {k for k, v in turn_hits.items() if v > 0.2 * n_turns}

res = []; drop = collections.Counter(); removed_routine = 0; removed_offcorpus = 0
for name, rows in sessions():
    calls = [r for r in rows if r["kind"] == "call"]
    for i, c in enumerate(calls):
        if "kq" not in c:
            continue
        q = qtext(c["kq"])
        if not q:
            drop["flag-only or empty"] += 1
            continue
        before = set(corpus.norm_item(x) for r in calls[max(0, i - 10):i] for x in r.get("reads", []))
        after = set(corpus.norm_item(x) for r in calls[i + 1:i + 11] for x in r.get("reads", []))
        lab = after - before
        removed_routine += len(lab & routine); lab -= routine
        n0 = len(lab); lab = {x for x in lab if x in docs}; removed_offcorpus += n0 - len(lab)
        if not lab:
            drop["no label"] += 1
            continue
        t = ts(c["ts"])
        if time.strftime("%Y-%m-%d", time.localtime(t)) < SINCE:
            drop["before window"] += 1
            continue
        elig = [k for k, v in docs.items() if (v["created"] or v["mtime"]) < t]
        changed = sum(1 for k in elig if docs[k]["mtime"] > t) / max(len(elig), 1)
        qt = corpus.TOKEN.findall(q.lower())
        ship = shipping_list(c.get("kq_text"))
        arms = {"shipping": ship, "grep": corpus.grep5(qt, docs, idf, elig), "bm25": corpus.bm25(qt, docs, idf, avg, elig)}
        rec = {}
        for a, lst in arms.items():
            for k in (3, 10):
                rec["%s@%d" % (a, k)] = len(lab & set(lst[:k])) / len(lab)
            nl = lab - set(ship)
            rec["%s@10_notship" % a] = (len(nl & set(lst[:10])) / len(nl)) if nl else None
        rec.update(day=time.strftime("%Y-%m-%d", time.localtime(t)), n_lab=len(lab), changed=changed, ship_len=len(ship))
        res.append(rec)
        with open(D + "/e13_rows_%s.jsonl" % SINCE, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

print("queries with a label:", len(res), "| dropped:", dict(drop), "| label items removed as routine:", removed_routine,
      "off-corpus:", removed_offcorpus, "| routine items:", len(routine), "of turns", n_turns)
days = sorted(set(r["day"] for r in res)); print("days:", len(days))
print("mean share of eligible candidates changed after the query: %.2f" % np.mean([r["changed"] for r in res]))
print("shipping list parsed, mean length %.1f, empty in %d" % (np.mean([r["ship_len"] for r in res]), sum(r["ship_len"] == 0 for r in res)))
for key in ("@3", "@10", "@10_notship"):
    print(key, {a: round(float(np.mean([r[a + key] for r in res if r[a + key] is not None])), 3) for a in ("shipping", "grep", "bm25")},
          "n=%d" % sum(r["shipping" + key] is not None for r in res))
def byday(key):
    per = {}
    for r in res:
        if r["bm25" + key] is None:
            continue
        per.setdefault(r["day"], []).append(r["bm25" + key] - r["shipping" + key])
    dd = np.array([np.mean(v) for v in per.values()])
    rng = np.random.default_rng(SEED)
    boots = [np.mean(rng.choice(dd, len(dd))) for _ in range(10000)]
    return len(dd), dd.mean(), np.percentile(boots, 2.5), np.percentile(boots, 97.5)
for key in ("@10", "@10_notship"):
    n, m, lo, hi = byday(key)
    print("H13 BM25 minus shipping, recall%s: days=%d, mean of day means %+.3f, 95%% [%+.3f, %+.3f]" % (key, n, m, lo, hi))
