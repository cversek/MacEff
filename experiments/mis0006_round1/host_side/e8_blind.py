# E8 H8.2 second half: matched fire/non-fire pairs, shuffled, excerpts written for blind reading. Key kept apart.
import json, glob, os, random, re, time, collections
D = os.path.expanduser(os.environ.get("KIT_DATA", "~/mis0006_r1_data"))
OUT = D + "/blind"; os.makedirs(OUT, exist_ok=True)
fires = json.load(open(D + "/e8_fires_2026-10-25.json"))
rng = random.Random(20261124)
cache = {}
def calls_of(fn):
    if fn not in cache:
        rows = [json.loads(l) for l in open(os.path.join(D, fn))]
        cache[fn] = [r for r in rows if not r.get("side") and r["kind"] in ("call", "compact")]
    return cache[fn]
def hour(r):
    return r["ts"][11:13] if r.get("ts") else None
def excerpt(fn, i, n=20):
    lines = []
    for r in calls_of(fn)[i + 1:i + 1 + n]:
        if r["kind"] == "compact":
            lines.append("[compaction]")
            continue
        t = r.get("tool")
        body = r.get("cmd") or r.get("path") or r.get("skill") or ""
        lines.append("%s: %s" % (t, re.sub(r"\s+", " ", body)[:220]))
    return "\n".join(lines)
cue_idx = collections.defaultdict(set)
for f in fires:
    cue_idx[f["file"]].add(f["i"])
pairs = []
by_cls = collections.defaultdict(list)
for f in fires:
    by_cls[f["cls"]].append(f)
for cls, fs in sorted(by_cls.items()):
    rng.shuffle(fs)
    for f in fs[:30]:
        calls = calls_of(f["file"]); h = hour(calls[f["i"]])
        cand = [j for j in range(len(calls)) if calls[j]["kind"] == "call" and hour(calls[j]) == h
                and all(abs(j - k) >= 10 for k in cue_idx[f["file"]]) and j < len(calls) - 30]
        if not cand:
            continue
        j = rng.choice(cand)
        pairs.append({"cls": cls, "fire": (f["file"], f["i"]), "ctrl": (f["file"], j)})
items = []
for p in pairs:
    for role in ("fire", "ctrl"):
        items.append({"cls": p["cls"], "role": role, "file": p[role][0], "i": p[role][1], "pair": id(p)})
rng.shuffle(items)
key = []
for n, it in enumerate(items):
    ex_id = "X%04d" % n
    key.append({"ex": ex_id, **{k: it[k] for k in ("cls", "role", "file", "i")}, "pair": pairs.index(next(p for p in pairs if id(p) == it["pair"]))})
    with open(OUT + "/excerpts_%s.txt" % it["cls"], "a") as fh:
        fh.write("=== %s (class %s): the 20 tool calls after the moment (the moment itself is withheld) ===\n%s\n\n" % (ex_id, it["cls"], excerpt(it["file"], it["i"])))
json.dump(key, open(D + "/blind_key.json", "w"))
print("pairs", len(pairs), "excerpts", len(items), collections.Counter(p["cls"] for p in pairs))
