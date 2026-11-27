"""E10 (a static-embedding tier) and E3 (rerank) on `knowledge eval`, MIS-0006 round 1 (MacEff #1149).

    python3 run_e10_e3.py dev     # tuning choices only: which static model, which reranker
    python3 run_e10_e3.py held    # the one held read, with the choices frozen in choices.json

Every ranker reads the query artifact's text with its Cross-References and Wiki-Links sections and
[[concept]] tokens removed (the leak audit checks it), and indexes candidates the same way.
Fusion is reciprocal rank fusion, k = 60, over full text (SQLite FTS5, BM25) and one embedder.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from macf import knowledge_eval as KE

HERE = Path(__file__).resolve().parent
#: The held split's seed. A new seed is a new seal; each seat uses its own (E10_SEED), fixed before `dev` runs.
SEED = os.environ.get("E10_SEED", "e10-e3-2026-11-25")
EMB = {"minilm": "sentence-transformers/all-MiniLM-L6-v2", "qwen3": "Qwen/Qwen3-Embedding-0.6B",
       "static": "sentence-transformers/static-retrieval-mrl-en-v1", "potion": "minishlab/potion-retrieval-32M"}
RER = {"msmarco": "cross-encoder/ms-marco-MiniLM-L-6-v2", "bge": "BAAI/bge-reranker-v2-m3"}
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


snap = KE.build_snapshot()
digest = KE.save_snapshot(snap, HERE / "snapshot.json")
corpus = KE.Corpus(snap, digest)
WEB = corpus.web
DOC = {n: (corpus.nodes[n]["title"] + "\n" + words_of(corpus.nodes[n]["text"]))[:4000] for n in WEB}
SHORT = {n: corpus.nodes[n]["title"] + "\n" + words_of(corpus.nodes[n]["text"], 400) for n in WEB}


def reads(q, c):
    return DOC.get(q) or words_of(c.nodes[q]["text"])[:4000]


# ---- full text ----
fts = sqlite3.connect(":memory:")
fts.execute("CREATE VIRTUAL TABLE d USING fts5(nid UNINDEXED, body)")
fts.executemany("INSERT INTO d VALUES (?, ?)", [(n, DOC[n]) for n in WEB])


def fts_rank(q, c, k=100):
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", reads(q, c).lower()) if t not in STOP]
    terms = [t for t, _ in Counter(toks).most_common(32)]
    if not terms:
        return []
    rows = fts.execute("SELECT nid FROM d WHERE d MATCH ? ORDER BY bm25(d) LIMIT ?",
                       (" OR ".join(f'"{t}"' for t in terms), k)).fetchall()
    return [r[0] for r in rows if r[0] != q]


# ---- dense ----
_mat = {}


def mat(name):
    if name not in _mat:
        cache = HERE / f"emb_{name}_{digest[:12]}.npy"
        if cache.exists():
            _mat[name] = np.load(cache)
        else:
            from sentence_transformers import SentenceTransformer
            m = SentenceTransformer(EMB[name], device="cuda" if name == "qwen3" else "cpu")
            v = m.encode([DOC[n] for n in WEB], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
            np.save(cache, v.astype(np.float32))
            _mat[name] = v.astype(np.float32)
    return _mat[name]


IDX = {n: i for i, n in enumerate(WEB)}


def dense_rank(name, q, k=100):
    M = mat(name)
    s = M @ M[IDX[q]] if q in IDX else None
    order = np.argsort(-s)
    return [WEB[i] for i in order[:k + 1] if WEB[i] != q][:k]


def rrf(*lists, k=60):
    sc = Counter()
    for L in lists:
        for r, x in enumerate(L):
            sc[x] += 1.0 / (k + r + 1)
    return [x for x, _ in sorted(sc.items(), key=lambda kv: (-kv[1], kv[0]))]


_cache = {}


def memo(name, fn):
    def rank(q, c):
        key = (name, q)
        if key not in _cache:
            _cache[key] = fn(q, c)
        return _cache[key]
    return rank


def hybrid(name):
    return memo(f"hyb_{name}", lambda q, c: rrf(fts_rank(q, c), dense_rank(name, q)))


_ce = {}


def rerank(rname, base):
    def fn(q, c):
        top = base(q, c)[:50]
        if rname not in _ce:
            from sentence_transformers import CrossEncoder
            _ce[rname] = CrossEncoder(RER[rname], device="cuda", max_length=512)
        qs = SHORT.get(q) or words_of(c.nodes[q]["text"], 400)
        s = _ce[rname].predict([(qs, SHORT[x]) for x in top], batch_size=16, show_progress_bar=False)
        return [top[i] for i in np.argsort(-np.asarray(s))]
    return fn


def rankers(first_stages):
    R = {"fts": KE.Ranker("fts", memo("fts", fts_rank), "full text, BM25", reads)}
    for n in EMB:
        R[f"hyb_{n}"] = KE.Ranker(f"hyb_{n}", hybrid(n), f"RRF of full text and {n}", reads)
    for fs in first_stages:
        for r in RER:
            name = f"rr_{r}_on_{fs}"
            R[name] = KE.Ranker(name, memo(name, rerank(r, R[fs].rank)), f"{r} over {fs} top 50", reads)
    return R


def rows_for(R, which):
    """Per-query metrics per source per ranker, on the split, from the same rankings evaluate() scored."""
    out = {}
    for s in KE.LABEL_SOURCES:
        rel, _ = KE.labels_for(corpus, s, corpus.snap.get("learnings_index"))
        rel = {q: v & corpus.web_set for q, v in rel.items() if q in corpus.web_set}
        rel = {q: v for q, v in rel.items() if v}
        dev, held = KE.split(rel, SEED)
        qs = dev if which == "dev" else held
        out[s] = {"n": len(qs), "rows": {}}
        for name, r in R.items():
            per = []
            for q in qs:
                ranked = [x for x in r.rank(q, corpus) if x in corpus.web_set and x != q]
                per.append(KE.per_query(ranked, rel[q], len(corpus.web)))
            out[s]["rows"][name] = per
    return out


def paired(rows, a, b, s):
    A, B = rows[s]["rows"][a], rows[s]["rows"][b]
    idx = KE.resamples(len(A), s)
    d = KE.interval([pb["MRR"] - pa["MRR"] for pa, pb in zip(A, B)], idx)
    base = float(np.mean([p["MRR"] for p in A])) if A else 0.0
    return {"diff": d, "base_mrr": base}


def audit_only():
    R = {"fts": KE.Ranker("fts", memo("fts", fts_rank), "full text", reads)}
    for s in KE.LABEL_SOURCES:
        rel, _ = KE.labels_for(corpus, s, corpus.snap.get("learnings_index"))
        rel = {q: v & corpus.web_set for q, v in rel.items() if q in corpus.web_set}
        rel = {q: v for q, v in rel.items() if v}
        dev, held = KE.split(rel, SEED)
        a = KE.leak_audit(R["fts"], dev, rel, corpus)
        print(s, "dev", len(dev), "held", len(held), "leak share", round(a.share, 3), a.leaks[:2])


def main(which):
    if which == "audit":
        return audit_only()
    choices_path = HERE / "choices.json"
    if which == "dev":
        R = rankers(["hyb_qwen3"])
        res = KE.evaluate(corpus, list(R), which="dev", seed=SEED, extra_rankers=R)
        rows = rows_for(R, "dev")
        mean = {n: {s: float(np.mean([p["MRR"] for p in rows[s]["rows"][n]])) for s in KE.LABEL_SOURCES} for n in R}
        static = max(("hyb_static", "hyb_potion"), key=lambda n: np.mean(list(mean[n].values())))
        rr = max(("rr_msmarco_on_hyb_qwen3", "rr_bge_on_hyb_qwen3"), key=lambda n: mean[n]["xref"])
        json.dump({"static": static, "reranker": rr.split("_")[1], "dev_mrr": mean,
                   "chart": res["chart"]}, open(choices_path, "w"), indent=1)
        print(json.dumps({"static": static, "reranker": rr, "dev_mrr": mean, "sources": res["chart"]["sources"]}, indent=1))
        return
    ch = json.load(open(choices_path))
    first = ["hyb_qwen3"] + ([ch["static"]] if ch["static"] != "hyb_qwen3" else [])
    R = rankers(first)
    res = KE.evaluate(corpus, list(R), which="held", seed=SEED, extra_rankers=R, compare=("hyb_minilm", ch["static"]))
    rows = rows_for(R, "held")
    rr = f"rr_{ch['reranker']}_on_hyb_qwen3"
    other = "rr_" + ("bge" if ch["reranker"] == "msmarco" else "msmarco") + "_on_hyb_qwen3"
    out = {"seed": SEED, "snapshot": digest, "chart": res["chart"], "choices": ch,
           "mean_mrr": {n: {s: float(np.mean([p["MRR"] for p in rows[s]["rows"][n]])) for s in KE.LABEL_SOURCES} for n in R},
           "n": {s: rows[s]["n"] for s in KE.LABEL_SOURCES}, "pairs": {}}
    for s in KE.LABEL_SOURCES:
        P = out["pairs"].setdefault(s, {})
        P["minilm_hybrid_vs_fts"] = paired(rows, "fts", "hyb_minilm", s)
        for st in ("hyb_static", "hyb_potion", "hyb_qwen3"):
            P[f"{st}_vs_minilm_hybrid"] = paired(rows, "hyb_minilm", st, s)
        for fs in first:
            for r in RER:
                P[f"rr_{r}_on_{fs}_vs_plain"] = paired(rows, fs, f"rr_{r}_on_{fs}", s)
    json.dump(out, open(HERE / "held_results.json", "w"), indent=1)
    print(json.dumps({s: {k: {"lo": v["diff"]["lo"] if "lo" in v["diff"] else v["diff"], "base": round(v["base_mrr"], 4)}
                          for k, v in P.items()} for s, P in out["pairs"].items()}, default=str)[:4000])
    print("DONE", other)


if __name__ == "__main__":
    main(sys.argv[1])
