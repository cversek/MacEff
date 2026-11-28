"""MIS-0006 round 2, the container-management maintainer's follow-up: ms-marco reranking on topical
queries (MacEff #1149). The rule was posted before any round 2 data was read: comment 7231398098.

    R1_SNAPSHOT=<round 1 snapshot.json> python3 run_r2_msmarco.py seal    # picks fresh queries, seals them; ranks nothing
    R1_SNAPSHOT=none python3 run_r2_msmarco.py seal   # a record that never ran knowledge eval in round 1: all are fresh
    python3 run_r2_msmarco.py run     # checks the seal, ranks, decides H3.3 and its guard
    python3 run_r2_msmarco.py cost    # added latency and memory of reranking 50 candidates

`seal` and `run` are separate on purpose: the query list is fixed, and its hash posted, before any
ranker sees a query. Fresh means the query artifact was a labeled query in neither round 1 split, which
is every labeled query in round 1's snapshot (its development and held splits together).

Arms, fixed in round 1 with no development choice: plain is today's MiniLM hybrid (RRF, k = 60, of
SQLite FTS5 BM25 and all-MiniLM-L6-v2); reranked is that hybrid's top 50 reordered by
cross-encoder/ms-marco-MiniLM-L-6-v2, reading each candidate's title and first 400 words. Every ranker
reads text with links, file stems, citation brackets and the two link sections removed, as in round 1.
MRR is computed over each arm's list exactly as round 1 computed it, so the figures compare.

H3.4 (the operator's prose questions) runs only on the record that holds a conversation store; it is
not in this kit.
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from macf import knowledge_eval as KE

HERE = Path(__file__).resolve().parent
#: The seed that orders fill-in queries if fewer than MIN_FRESH fresh ones exist. Fixed with the rule.
SEED = os.environ.get("R2_SEED", "r2-msmarco-2026-11-27")
MIN_FRESH = 60
BOOT = 10_000
PRIMARY, GUARD = "same_subject", "xref"
EMBEDDER = "sentence-transformers/all-MiniLM-L6-v2"
RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEVICE = os.environ.get("R2_DEVICE", "cpu")
STOP = set("the a an and or of to in on for is are was were be it this that with as by at from not no but if then so "
           "we i you he she they them his her its our their my me do does did done has have had can could will would "
           "should may might must what which who when where why how all any each more most other some such only own "
           "same than too very just about into over after before again there here out up down off also".split())
SECTION = re.compile(r"^## (Cross-References|Wiki-Links)\s*$.*?(?=^## |\Z)", re.M | re.S)
NAMEISH = [re.compile(x) for x in (r"\[\[[^\]]*\]\]", r"\[[^\]]*\]\([^)]*\)", r"\[[A-Z]+ [^\]]*\]",
                                     r"\S*\d{4}-\d{2}-\d{2}[_ ]\d{4,6}\S*", r"\S+\.md\b")]


def clean(text):
    t = SECTION.sub("", text or "")
    for rx in NAMEISH:
        t = rx.sub(" ", t)
    return t


def words_of(text, n=None):
    return " ".join(clean(text).split()[:n]) if n else clean(text)


def labels(corpus, source):
    rel, _ = KE.labels_for(corpus, source, corpus.snap.get("learnings_index"))
    rel = {q: v & corpus.web_set for q, v in rel.items() if q in corpus.web_set}
    return {q: v for q, v in rel.items() if v}


# ---- seal -------------------------------------------------------------------------------------------

def seal():
    r1_path = os.environ.get("R1_SNAPSHOT")
    if not r1_path:
        sys.exit("R1_SNAPSHOT must name round 1's snapshot.json, or be 'none' on a record that never ran "
                 "knowledge eval in round 1: fresh queries are those round 1 didn't label")
    if r1_path == "none":
        r1, r1_digest = None, None          # no round 1 run on this record: every labeled query is fresh
    else:
        r1_snap, r1_digest = KE.load_snapshot(Path(r1_path))
        r1 = KE.Corpus(r1_snap, r1_digest)
    snap = KE.build_snapshot()
    digest = KE.save_snapshot(snap, HERE / "snapshot.json")
    corpus = KE.Corpus(snap, digest)
    out = {"rule": "MacEff #1149 comment 7231398098", "seed": SEED, "snapshot": digest,
           "round1_snapshot": r1_digest, "sealed_at": time.time(), "sources": {}}
    for source in (PRIMARY, GUARD):
        now, before = labels(corpus, source), (labels(r1, source) if r1 is not None else {})
        fresh = sorted(q for q in now if q not in before)
        ids, filled = list(fresh), 0
        if len(ids) < MIN_FRESH:
            rest = sorted((q for q in now if q in before), key=lambda q: KE.stable_key(SEED, q))
            take = rest[:MIN_FRESH - len(ids)]
            ids, filled = sorted(ids + take), len(take)
        out["sources"][source] = {"ids": ids, "ids_digest": KE.ids_digest(ids), "fresh": len(fresh),
                                  "filled_from_round1": filled, "labeled_now": len(now)}
    json.dump(out, open(HERE / "seal.json", "w"), indent=1)
    blob = json.dumps({s: v["ids_digest"] for s, v in out["sources"].items()}, sort_keys=True)
    print(json.dumps({"snapshot": digest, "round1_snapshot": r1_digest,
                      "counts": {s: {k: v[k] for k in ("fresh", "filled_from_round1", "labeled_now")}
                                 for s, v in out["sources"].items()},
                      "seal_sha256": __import__("hashlib").sha256(blob.encode()).hexdigest()}, indent=1))


# ---- rankers ----------------------------------------------------------------------------------------

class Rankers:
    def __init__(self, corpus):
        self.c, self.web = corpus, corpus.web
        self.doc = {n: (corpus.nodes[n]["title"] + "\n" + words_of(corpus.nodes[n]["text"]))[:4000] for n in self.web}
        self.short = {n: corpus.nodes[n]["title"] + "\n" + words_of(corpus.nodes[n]["text"], 400) for n in self.web}
        self.cut = sum(len(clean(corpus.nodes[n]["text"]).split()) > 400 for n in self.web)
        self.fts = sqlite3.connect(":memory:")
        self.fts.execute("CREATE VIRTUAL TABLE d USING fts5(nid UNINDEXED, body)")
        self.fts.executemany("INSERT INTO d VALUES (?, ?)", [(n, self.doc[n]) for n in self.web])
        self.idx = {n: i for i, n in enumerate(self.web)}
        self._m = self._ce = None
        self._memo = {}

    def reads(self, q, c=None):
        return self.doc.get(q) or words_of(self.c.nodes[q]["text"])[:4000]

    def fts_rank(self, q, c=None, k=100):
        toks = [t for t in re.findall(r"[a-z0-9]{3,}", self.reads(q).lower()) if t not in STOP]
        terms = [t for t, _ in Counter(toks).most_common(32)]
        if not terms:
            return []
        rows = self.fts.execute("SELECT nid FROM d WHERE d MATCH ? ORDER BY bm25(d) LIMIT ?",
                                (" OR ".join(f'"{t}"' for t in terms), k)).fetchall()
        return [r[0] for r in rows if r[0] != q]

    def matrix(self):
        if self._m is None:
            cache = HERE / f"emb_minilm_{self.c.digest[:12]}.npy"
            if cache.exists():
                self._m = np.load(cache)
            else:
                from sentence_transformers import SentenceTransformer
                m = SentenceTransformer(EMBEDDER, device="cpu")
                v = m.encode([self.doc[n] for n in self.web], batch_size=16, normalize_embeddings=True,
                             show_progress_bar=False).astype(np.float32)
                np.save(cache, v)
                self._m = v
        return self._m

    def dense_rank(self, q, k=100):
        M = self.matrix()
        order = np.argsort(-(M @ M[self.idx[q]]))
        return [self.web[i] for i in order[:k + 1] if self.web[i] != q][:k]

    @staticmethod
    def rrf(*lists, k=60):
        sc = Counter()
        for L in lists:
            for r, x in enumerate(L):
                sc[x] += 1.0 / (k + r + 1)
        return [x for x, _ in sorted(sc.items(), key=lambda kv: (-kv[1], kv[0]))]

    def plain(self, q, c=None):
        key = ("plain", q)
        if key not in self._memo:
            self._memo[key] = self.rrf(self.fts_rank(q), self.dense_rank(q))
        return self._memo[key]

    def reranked(self, q, c=None):
        key = ("rr", q)
        if key not in self._memo:
            top = self.plain(q)[:50]
            if self._ce is None:
                from sentence_transformers import CrossEncoder
                self._ce = CrossEncoder(RERANKER, device=DEVICE, max_length=512)
            qs = self.short.get(q) or words_of(self.c.nodes[q]["text"], 400)
            s = self._ce.predict([(qs, self.short[x]) for x in top], batch_size=16, show_progress_bar=False)
            self._memo[key] = [top[i] for i in np.argsort(-np.asarray(s))]
        return self._memo[key]


# ---- run --------------------------------------------------------------------------------------------

def run():
    sealed = json.load(open(HERE / "seal.json"))
    snap, digest = KE.load_snapshot(HERE / "snapshot.json")
    if digest != sealed["snapshot"]:
        sys.exit(f"the snapshot changed since the seal ({digest} against {sealed['snapshot']}); refusing")
    corpus = KE.Corpus(snap, digest)
    R = Rankers(corpus)
    out = {"seal": {s: v["ids_digest"] for s, v in sealed["sources"].items()}, "snapshot": digest,
           "candidates_cut_at_400_words": R.cut, "web": len(corpus.web), "sources": {}}
    fts = KE.Ranker("fts", R.fts_rank, "full text", R.reads)
    for source, v in sealed["sources"].items():
        ids = v["ids"]
        if KE.ids_digest(ids) != v["ids_digest"]:
            sys.exit(f"{source}: the sealed query list doesn't match its digest; refusing")
        rel = labels(corpus, source)
        missing = [q for q in ids if q not in rel]
        ids = [q for q in ids if q in rel]
        audit = KE.leak_audit(fts, ids, rel, corpus)
        if audit.share > KE.LEAK_LIMIT:
            sys.exit(f"{source}: leak audit refused, share {audit.share:.3f}")
        rows = {}
        for name, rank in (("plain", R.plain), ("reranked", R.reranked)):
            rows[name] = [KE.per_query([x for x in rank(q) if x in corpus.web_set and x != q], rel[q],
                                       len(corpus.web)) for q in ids]
        base = float(np.mean([p["MRR"] for p in rows["plain"]])) if ids else 0.0
        diff = KE.interval([b["MRR"] - a["MRR"] for a, b in zip(rows["plain"], rows["reranked"])],
                           KE.resamples(len(ids), source, boot=BOOT))
        lo = diff["ci95"][0]
        out["sources"][source] = {"n": len(ids), "dropped": missing, "leak_share": audit.share,
                                  "plain_mrr": round(base, 4), "diff": diff, "margin": round(0.10 * base, 4)}
    p, g = out["sources"][PRIMARY], out["sources"][GUARD]
    gain = p["diff"]["ci95"][0] > p["margin"]
    guard = g["diff"]["ci95"][0] >= -g["margin"]
    out["H3.3"] = "validated" if gain else "not validated"
    out["guard"] = "holds" if guard else "fails"
    out["reading"] = ("rerank related-artifact queries" if gain and guard else
                      "route topical queries to the reranker" if gain else "nothing enters")
    json.dump(out, open(HERE / "results.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


# ---- cost -------------------------------------------------------------------------------------------

def cost():
    import resource
    import subprocess
    snap, digest = KE.load_snapshot(HERE / "snapshot.json")
    R = Rankers(KE.Corpus(snap, digest))
    sealed = json.load(open(HERE / "seal.json"))
    qs = sealed["sources"][PRIMARY]["ids"][:30]
    for q in qs[:3]:
        R.plain(q)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    R.reranked(qs[0])                                     # loads the model
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    added = []
    for q in qs[1:]:
        R.plain(q)
        t = time.perf_counter()
        R.reranked(q)
        added.append(time.perf_counter() - t)
    probe = ("import time; t=time.perf_counter(); from sentence_transformers import CrossEncoder; "
             f"m=CrossEncoder({RERANKER!r}, device={DEVICE!r}, max_length=512); "
             "m.predict([('a query','a candidate')]*50); print(time.perf_counter()-t)")
    starts = sorted(float(subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                                         env={**os.environ, "HF_HUB_OFFLINE": "1"}).stdout.strip() or "nan")
                    for _ in range(10))
    added.sort()
    out = {"device": DEVICE, "queries": len(added), "added_p50_s": round(added[len(added) // 2], 4),
           "added_p95_s": round(added[int(0.95 * (len(added) - 1))], 4),
           "resident_added_mb": round((after - before) / 1024, 1), "cold_start_median_s": round(starts[5], 3),
           "crossing_gate_p95_le_1s": added[int(0.95 * (len(added) - 1))] <= 1.0}
    json.dump(out, open(HERE / "cost.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"seal": seal, "run": run, "cost": cost}[sys.argv[1]]()
