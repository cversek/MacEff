"""E4 shared parts: an index over units of text (BM25 by FTS5, dense by MiniLM), the fixed grep
baseline, the E1 fusions, metrics and paired intervals."""

import hashlib
import math
import os
import random
import re
import sqlite3
from collections import Counter

from macf.knowledge_eval_text import CHUNK_WORDS, MODEL, embedding_device, fuse_cc, fuse_rrf, words

TOP_N = 100
_STOP = set("""a an the and or of to in on for with at by from is are was were be been it its this that these those as
not no do does did what which who whom when where why how i you we he she they me my our your their his her them us
there here than then so if but about into over under up down out more most less least any all some each other such
can could should would will shall may might must have has had just also only very""".split())


def norm_quote(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


class Index:
    """Units of text, each belonging to an episode; BM25 and dense scores per unit."""

    def __init__(self, name, units, owners, cache_dir=None, embed=None):
        self.name, self.units, self.owners = name, units, owners
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        self.db.executemany("INSERT INTO t(rowid, body) VALUES (?, ?)", enumerate(units))
        self.df = Counter()
        for u in units:
            self.df.update(set(words(u)))
        self.cache_dir, self._embed, self._vec = cache_dir, embed, None

    def idf(self, w):
        return math.log((len(self.units) + 1) / (self.df.get(w, 0) + 1))

    def bm25(self, query, n=TOP_N):
        terms = sorted(set(words(query)))
        if not terms:
            return []
        rows = self.db.execute("SELECT rowid, bm25(t) FROM t WHERE t MATCH ? ORDER BY bm25(t), rowid LIMIT ?",
                               (" OR ".join(f'"{w}"' for w in terms), n)).fetchall()
        return [(r, -s) for r, s in rows]

    def embedder(self):
        if self._embed is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(MODEL, device=embedding_device())
            self._embed = lambda texts: model.encode(texts, batch_size=64, normalize_embeddings=True,
                                                     show_progress_bar=False)
        return self._embed

    def vectors(self):
        if self._vec is not None:
            return self._vec
        import numpy as np
        digest = hashlib.sha256("\x00".join(self.units).encode()).hexdigest()[:16]
        path = os.path.join(self.cache_dir, f"vec_{self.name}_{digest}.npy") if self.cache_dir else None
        if path and os.path.exists(path):
            self._vec = np.load(path)
            return self._vec
        chunks, owner = [], []
        for i, u in enumerate(self.units):
            w = u.split()
            for s in range(0, max(len(w), 1), CHUNK_WORDS):
                chunks.append(" ".join(w[s:s + CHUNK_WORDS]))
                owner.append(i)
        emb = np.asarray(self.embedder()(chunks), dtype="float32")
        vec = np.zeros((len(self.units), emb.shape[1]), dtype="float32")
        np.add.at(vec, np.asarray(owner), emb)
        norms = np.linalg.norm(vec, axis=1, keepdims=True)
        self._vec = vec / np.where(norms == 0, 1.0, norms)
        if path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                np.save(fh, self._vec)
        return self._vec

    def query_vector(self, query):
        """A query is embedded like a unit: the normalized mean of its windows."""
        import numpy as np
        w = query.split()
        chunks = [" ".join(w[s:s + CHUNK_WORDS]) for s in range(0, max(len(w), 1), CHUNK_WORDS)]
        v = np.asarray(self.embedder()(chunks), dtype="float32").sum(axis=0)
        return v / (np.linalg.norm(v) or 1.0)

    def dense(self, query, n=TOP_N):
        import numpy as np
        q = self.query_vector(query)
        sims = self.vectors() @ q
        k = min(n, len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        top = sorted(top, key=lambda i: (-float(sims[i]), int(i)))
        return [(int(i), float(sims[i])) for i in top]


def to_episodes(unit_pairs, owners, n=TOP_N):
    """Unit ranking -> episode ranking, an episode at its best unit's place."""
    out, seen = [], set()
    for u in unit_pairs:
        e = owners[u]
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:n]


def _keyed(pairs, owners):
    """Unit scores -> episode scores (best unit), as (episode, score) in rank order."""
    best = {}
    for u, s in pairs:
        e = owners[u]
        if e not in best:
            best[e] = s
    return list(best.items())


def rank(index, query, method, ts_of=None, n=TOP_N):
    """Episode ids for *query* by *method*: bm25, dense, cc:A, rrf:K. Returns (episodes, extra)."""
    owners = index.owners
    if method == "bm25":
        return [e for e, _ in _keyed(index.bm25(query, 4 * n), owners)][:n], {}
    if method == "dense":
        d = _keyed(index.dense(query, 4 * n), owners)
        return [e for e, _ in d][:n], {"top_cos": d[0][1] if d else 0.0}
    b = _keyed(index.bm25(query, 4 * n), owners)[:n]
    d = _keyed(index.dense(query, 4 * n), owners)[:n]
    kind, _, p = method.partition(":")
    fused = fuse_cc(b, d, float(p)) if kind == "cc" else fuse_rrf(b, d, float(p))
    cos = dict(d)
    top_cos = cos.get(fused[0]) if fused else None
    if top_cos is None and fused:
        # the top episode came from BM25 alone; its cosine is computed here
        units = [u for u, e in enumerate(owners) if e == fused[0]]
        top_cos = float(max(index.vectors()[units] @ index.query_vector(query)))
    return fused[:n], {"top_cos": top_cos if top_cos is not None else 0.0}


def grep_rank(index, query, ts_of, n=TOP_N):
    """The fixed baseline: the question's five highest-IDF terms (ties by order in the question);
    episodes by how many of the five they contain, then newest first."""
    seen, terms = set(), []
    for w in words(query):
        if w in _STOP or w in seen or index.df.get(w, 0) == 0:
            continue
        seen.add(w)
        terms.append(w)
    order = {w: i for i, w in enumerate(terms)}
    five = sorted(terms, key=lambda w: (-index.idf(w), order[w]))[:5]
    count = Counter()
    for u, text in enumerate(index.units):
        ws = set(words(text))
        hit = sum(1 for w in five if w in ws)
        if hit:
            e = index.owners[u]
            count[e] = max(count[e], hit)
    return sorted(count, key=lambda e: (-count[e], -ts_of[e]))[:n], {"terms": five}


def recall_all_at(ranked, relevant, k=10):
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


def stable_split(text, seed="mis0006-e4", held_share=0.2):
    return int(hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < held_share


def paired_interval(a, b, boot=10000, seed="mis0006-e4-boot"):
    """Mean of b - a over paired items, and its bootstrap 95% interval."""
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    if not n:
        return {"n": 0, "mean": None, "ci95": [None, None]}
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    lo, hi = means[int(0.025 * boot)], means[int(0.975 * boot) - 1]
    return {"n": n, "mean": round(sum(diffs) / n, 4), "ci95": [round(lo, 4), round(hi, 4)]}


def mean_interval(vals, boot=10000, seed="mis0006-e4-boot"):
    return paired_interval([0.0] * len(vals), vals, boot, seed)


def sign_test(wins, losses):
    """One-sided exact sign test: P(X >= wins) for X ~ Bin(wins + losses, 1/2)."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n
