"""E17, does speech ask about the past more often: back-reference rate per thousand words, dictated vs typed on the
same days (cleaned text), the precision sample, and the round-2 query set with routine reads and recovery moments
removed, with lexical recall@10 as description. Text stays private; figures print.
usage: e17.py DRIVES_JSON PRIVATE_OUT_DIR"""
import sys, json, re, random, collections, os, sqlite3, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEED, B = 20261123, 10000
d = json.load(open(sys.argv[1])); out = sys.argv[2]
drives, calls = d["drives"], d["calls"]
PHRASES = ["last time", "last session", "last week", "yesterday", "the other day", "earlier", "a while ago", "long time ago",
           "before the", "like you did", "like we did", "remember", "we promised", "we talked about", "we discussed",
           "as before", "used to", "previously"]
AGAIN = "again"
CAVEAT = re.compile(r"\s*This came from another Claude session.*$", re.S)
import e16  # noqa: E402  (the flag, reused; importing runs nothing heavy beyond its module code)


def clean(x):
    t = x["text"]
    if x["cls"] == "dictated_socket": t = CAVEAT.sub("", t)
    if x["cls"] == "typed": t = re.sub(r"<pasted_content[^>]*>.*?</pasted_content>", " ", t, flags=re.S)
    return t


def matches(t, with_again=False):
    low = t.lower(); n = sum(len(re.findall(r"\b" + re.escape(p) + r"\b", low)) for p in PHRASES)
    return n + (len(re.findall(r"\bagain\b", low)) if with_again else 0)


turns = []
for x in drives:
    if x["day"] < "2026-11-18" or x["cls"] not in ("typed", "dictated", "dictated_socket"): continue
    t = clean(x)
    if x["cls"] != "typed" and e16.flag_and_trim(x["text"])[0]: continue      # E16-flagged utterances left out (its trim was not safe)
    if x["cls"] == "typed" and t.lstrip().startswith(("<command", "<bash", "/")): continue
    w = len(t.split())
    if w == 0: continue
    turns.append({**x, "clean": t, "words": w, "kind": "typed" if x["cls"] == "typed" else "dictated", "m": matches(t), "m_again": matches(t, True)})
days = sorted({t["day"] for t in turns if t["kind"] == "dictated"} & {t["day"] for t in turns if t["kind"] == "typed"})
same = [t for t in turns if t["day"] in days]


def rate(ts, key="m"): return 1000 * sum(t[key] for t in ts) / max(1, sum(t["words"] for t in ts))


def diff_boot(key):
    by = collections.defaultdict(list)
    for t in same: by[t["day"]].append(t)
    rnd = random.Random(SEED); bs = []
    for _ in range(B):
        pick = [x for _ in days for x in by[rnd.choice(days)]]
        bs.append(rate([t for t in pick if t["kind"] == "dictated"], key) - rate([t for t in pick if t["kind"] == "typed"], key))
    bs.sort(); return bs[int(0.025 * B)], bs[int(0.975 * B) - 1]


dd = [t for t in same if t["kind"] == "dictated"]; tt = [t for t in same if t["kind"] == "typed"]
lo, hi = diff_boot("m")
print(f"Days with both kinds: {len(days)} ({', '.join(days)}); dictated turns {len(dd)} ({sum(t['words'] for t in dd)} words), typed turns {len(tt)} ({sum(t['words'] for t in tt)} words)")
print(f"Matches per thousand words, without 'again': dictated {rate(dd):.2f}, typed {rate(tt):.2f}; difference {rate(dd)-rate(tt):+.2f}, 95% interval by day [{lo:+.2f}, {hi:+.2f}]")
lo2, hi2 = diff_boot("m_again")
print(f"  with 'again': dictated {rate(dd,'m_again'):.2f}, typed {rate(tt,'m_again'):.2f}; difference [{lo2:+.2f}, {hi2:+.2f}]")
print(f"Per turn: dictated {sum(1 for t in dd if t['m'])}/{len(dd)} = {sum(1 for t in dd if t['m'])/max(1,len(dd)):.3f}; typed {sum(1 for t in tt if t['m'])}/{len(tt)} = {sum(1 for t in tt if t['m'])/max(1,len(tt)):.3f}")
v = "NOT REACHED (fewer than ten days)" if len(days) < 10 else ("VALIDATED" if lo > 0 else "CONTRADICTED" if hi < 0 else "NOT REACHED")
print(f"H17.1: {v}")
print("Beside: the container-management maintainer's 9 verified back-references in 4,046 turns (found and checked by hand) is not comparable with a phrase-match rate; the like-for-like comparison is the one above.")

# precision sample, for a blind reader: matched turns of both kinds mixed, kind hidden
rnd = random.Random(SEED)
md = [t for t in dd if t["m"]]; mt = [t for t in tt if t["m"]]
sd, st = rnd.sample(md, min(30, len(md))), rnd.sample(mt, min(30, len(mt)))
items = [{"kind": "dictated", "t": t} for t in sd] + [{"kind": "typed", "t": t} for t in st]
rnd.shuffle(items)
json.dump([{"n": i + 1, "text": it["t"]["clean"][:1200]} for i, it in enumerate(items)], open(f"{out}/e17_precision_turns.json", "w"), ensure_ascii=False, indent=1)
json.dump([{"n": i + 1, "kind": it["kind"]} for i, it in enumerate(items)], open(f"{out}/e17_precision_key.json", "w"))
print(f"Precision sample written privately: {len(sd)} dictated + {len(st)} typed matched turns, shuffled")

# query set: every matched turn on any voice-era day
real = [c for c in calls if c["name"] != "_compaction"]
n_turns = len([x for x in drives if x["day"] >= "2026-11-18"])
seen_in = collections.Counter()
for x in drives:
    if x["day"] < "2026-11-18": continue
    nxt = [c for c in calls if c["i"] >= x["call_index"]][:10]
    for it in {i for c in nxt for i in c["items"]}: seen_in[it] += 1
routine = {it for it, k in seen_in.items() if k > 0.2 * n_turns}
recov_starts = [c["i"] for c in calls if c["name"] == "_compaction"] + [0]
queries, recov, nolabel, removed = [], 0, 0, 0
for t in [t for t in turns if t["m"]]:
    ci = t["call_index"]
    if any(0 <= ci - s < 25 for s in recov_starts): recov += 1; continue
    before = {i for c in calls if ci - 10 <= c["i"] < ci for i in c["items"]}
    after = [i for c in calls if ci <= c["i"] < ci + 10 for i in c["items"]]
    lab = [i for i in dict.fromkeys(after) if i not in before]
    removed += sum(1 for i in lab if i in routine)
    lab = [i for i in lab if i not in routine]
    if not lab: nolabel += 1
    queries.append({"q": t["clean"][:2000], "kind": t["kind"], "day": t["day"], "labels": lab})
print(f"Query set: {len(queries)} back-reference turns ({sum(q['kind']=='dictated' for q in queries)} dictated); left out as recovery moments {recov}; "
      f"routine items (opened after more than 20% of {n_turns} turns): {len(routine)}, removing {removed} labels; queries with at least one label {len(queries)-nolabel} ({(len(queries)-nolabel)/max(1,len(queries)):.2f})")
json.dump(queries, open(f"{out}/e17_query_set.json", "w"), ensure_ascii=False, indent=1)

# lexical recall@10, description only: corpus = text files this seat opened in the window
labelled = [q for q in queries if q["labels"]]
files = sorted({i for c in real for i in c["items"] if i.startswith("/") and os.path.isfile(i) and os.path.getsize(i) < 2_000_000})
docs = {}
for f in files:
    try: docs[f] = open(f, encoding="utf8", errors="ignore").read()[:200_000]
    except OSError: pass
db = sqlite3.connect(":memory:"); db.execute("CREATE VIRTUAL TABLE t USING fts5(path UNINDEXED, body)")
db.executemany("INSERT INTO t VALUES (?,?)", [(p, os.path.basename(p) + " " + b) for p, b in docs.items()])
STOP = set("the a an and or to of in on for it is that this we you i be with as at by from was are have has do did not but so if then just like what can will".split())
def terms(q): return [w for w in dict.fromkeys(re.findall(r"[a-z0-9]{3,}", q.lower())) if w not in STOP][:24]
def bm25(q):
    ts = terms(q)
    if not ts: return []
    return [r[0] for r in db.execute("SELECT path FROM t WHERE t MATCH ? ORDER BY bm25(t) LIMIT 10", (" OR ".join(f'"{w}"' for w in ts),))]
def grep(q):
    ts = terms(q); sc = sorted(((sum(1 for w in ts if w in b.lower()), p) for p, b in docs.items()), reverse=True)
    return [p for s, p in sc[:10] if s > 0]
for name, fn in (("grep (distinct query terms present)", grep), ("BM25 over FTS5", bm25)):
    hits = [len(set(fn(q["q"])) & set(q["labels"])) / len([l for l in q["labels"] if l in docs] or [None]) if any(l in docs for l in q["labels"]) else None for q in labelled]
    hits = [h for h in hits if h is not None]
    print(f"  recall@10, {name}: {sum(hits)/max(1,len(hits)):.3f} over {len(hits)} queries whose labels include a file in the corpus ({len(docs)} files)")
if len(queries) < 20: print("Fewer than 20 queries: the set decides nothing.")
