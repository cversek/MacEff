# E8: trigger registry by replay. H8.1 (quiet enough) and H8.2 first half (fires carry news). Figures only.
import json, glob, os, re, sys, time, collections
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import corpus
D = os.path.expanduser(os.environ.get("KIT_DATA", "~/mis0006_r1_data"))
SINCE = os.environ.get("E8_SINCE", "2026-10-25")
REG = [l.rstrip("\n").split("\t") for l in open(os.path.join(os.path.dirname(__file__), "e8_registry.tsv")) if l.strip() and not l.startswith(("#", "id\t"))]

def day(s):
    return time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone))

fires = []; active_days = set()
for f in sorted(glob.glob(D + "/calls_*.jsonl")):
    rows = [json.loads(l) for l in open(f)]
    rows = [r for r in rows if not r.get("side")]
    calls = []; since_compact = set()
    for r in rows:
        if r["kind"] == "compact":
            since_compact = set()
            calls.append({"kind": "compact", "ts": r["ts"], "reads": [], "_since": set()})
            continue
        if r["kind"] != "call":
            continue
        r["_since"] = set(since_compact)
        since_compact |= set(corpus.norm_item(x) for x in r.get("reads", []))
        calls.append(r)
    for i, c in enumerate(calls):
        if not c.get("ts") or day(c["ts"]) < SINCE:
            continue
        active_days.add(day(c["ts"]))
        for tid, cls, ctype, cue, recall in REG:
            hit = False
            if ctype == "cmd":
                hit = bool(c.get("cmd") and re.search(cue, c["cmd"]))
            elif ctype == "tool":
                hit = c.get("tool") == cue
            elif ctype == "event":
                hit = c.get("kind") == cue
            elif ctype == "path":
                hit = bool(c.get("path") and re.search(cue, c["path"]))
            if not hit:
                continue
            before10 = set(corpus.norm_item(x) for r in calls[max(0, i - 10):i] for x in r.get("reads", []))
            after10 = set(corpus.norm_item(x) for r in calls[i + 1:i + 11] for x in r.get("reads", []))
            fires.append({"id": tid, "cls": cls, "day": day(c["ts"]), "file": os.path.basename(f), "i": i,
                          "in10": recall in before10, "insince": recall in c.get("_since", set()), "after": recall in after10})
json.dump(fires, open(D + "/e8_fires_%s.json" % SINCE, "w"))
days = sorted(active_days)
per_day = collections.Counter(f["day"] for f in fires)
tot = [per_day.get(d, 0) for d in days]
print("window from", SINCE, "| active days", len(days), "| fires", len(fires))
print("H8.1 registry fires per active day: median %.1f, mean %.1f, max %d" % (np.median(tot), np.mean(tot), max(tot)))
ent = collections.defaultdict(collections.Counter)
for f in fires: ent[f["id"]][f["day"]] += 1
print("entries over 20 fires in a day:", {k: max(v.values()) for k, v in ent.items() if max(v.values()) > 20})
print("per entry: fires, max/day, share already consulted (10 calls / since compaction), consulted in the next 10")
for tid, cls, *_ in REG:
    x = [f for f in fires if f["id"] == tid]
    if x:
        print("  %s %-13s %5d %4d  %.2f / %.2f  %.2f" % (tid, cls, len(x), max(ent[tid].values()), np.mean([f["in10"] for f in x]), np.mean([f["insince"] for f in x]), np.mean([f["after"] for f in x])))
    else:
        print("  %s %-13s     0" % (tid, cls))
news = np.mean([not f["insince"] for f in fires]) if fires else float("nan")
print("H8.2 first half: share of fires whose artifact was NOT read since the last compaction: %.3f (bar 0.5)" % news)
