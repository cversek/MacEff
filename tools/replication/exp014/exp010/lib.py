"""Shared harness pieces: the snapshot, label sources, metrics and the first arms.

The query unit for S1 is query-by-artifact: a learning that cross-references others is a query,
its relevant set is what it cross-references, and an arm sees only the query's CONCEPTS (never
its text or its links). No arm may return the query itself (leave-one-out).
"""
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SNAP = HERE / "data" / "corpus_snapshot.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "macf/src"))


def stable_key(seed, nid):
    """A deterministic pseudo-random tie-break, so two runs give byte-identical results."""
    return hashlib.sha256(f"{seed}:{nid}".encode()).hexdigest()


class Corpus:
    def __init__(self, path=SNAP):
        self.snap = json.loads(Path(path).read_bytes())
        self.nodes = self.snap["nodes"]
        self.web = sorted(k for k, v in self.nodes.items() if v["in_web"])
        self.everything = sorted(self.nodes)
        self.members = defaultdict(set)
        for k, v in self.nodes.items():
            for c in v["concepts"]:
                self.members[c].add(k)
        N = len(self.web)
        self.idf = {c: math.log(N / len(m)) for c, m in self.members.items()}
        self.neigh = None

    def neighbours(self):
        if self.neigh is None:
            self.neigh = defaultdict(set)
            for m in self.members.values():
                for a in m:
                    self.neigh[a] |= m
            for a in self.neigh:
                self.neigh[a].discard(a)
        return self.neigh


def s1_labels(corpus):
    """S1: learning cross-references that resolve to a learning in the snapshot."""
    by_file = {Path(v["path"]).name: k for k, v in corpus.nodes.items() if v["type"] == "learnings"}
    rel = defaultdict(set)
    for k, v in corpus.nodes.items():
        if v["type"] != "learnings":
            continue
        m = re.search(r"^## Cross-References\s*$(.*?)(?=^## |\Z)", v["text"], re.M | re.S)
        if not m:
            continue
        for fn in re.findall(r"([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[A-Za-z0-9_\-]+?_learning\.md)", m.group(1)):
            t = by_file.get(fn)
            if t and t != k:
                rel[k].add(t)
    return dict(rel)


# ---- metrics: each takes a ranked list and the relevant set ----------------------------------

def mrr(ranked, relevant):
    for i, x in enumerate(ranked, 1):
        if x in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at(ranked, relevant, k=10):
    dcg = sum(1.0 / math.log2(i + 1) for i, x in enumerate(ranked[:k], 1) if x in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def precision_at(ranked, relevant, k=10):
    return sum(1 for x in ranked[:k] if x in relevant) / k


def recall_at(ranked, relevant, k=50):
    return sum(1 for x in ranked[:k] if x in relevant) / len(relevant) if relevant else 0.0


METRICS = {"MRR": mrr, "nDCG@10": ndcg_at, "P@10": precision_at, "R@50": recall_at}


def score(arm, queries, labels, corpus):
    """Mean of each metric over the queries, plus the mean returned-set fraction (subweb)."""
    totals, sub = Counter(), 0.0
    for q in queries:
        ranked = arm(q, corpus)
        assert q not in ranked, f"leave-one-out violated: {q} returned itself"
        for name, f in METRICS.items():
            totals[name] += f(ranked, labels[q])
        sub += len(ranked) / len(corpus.web)
    n = len(queries)
    out = {name: round(totals[name] / n, 4) for name in METRICS}
    out["subweb"] = round(sub / n, 4)
    return out


# ---- arms --------------------------------------------------------------------------------------

def arm_random(q, corpus, seed="random"):
    """Every web node except the query, in a seeded random order: the floor."""
    return sorted((x for x in corpus.web if x != q), key=lambda x: stable_key(f"{seed}:{q}", x))


def arm_baseline(q, corpus):
    """What an agent gets today: the shipping query on each of the query's concepts, in turn,
    matched then neighbours, concatenated without repeats."""
    from macf.knowledge_web import query_knowledge_web
    kg = corpus_kg(corpus)
    seen, out = {q}, []
    for c in corpus.nodes[q]["concepts"]:
        r = query_knowledge_web(c, kg)
        for n in list(r["nodes"]) + list(r["neighbors"]):
            nid = str(n["id"]) if isinstance(n, dict) else str(n)
            if nid not in seen and nid in corpus.nodes:
                seen.add(nid)
                out.append(nid)
    return out


def arm_idf_match(q, corpus):
    """H1: candidates sharing a concept with the query, by summed IDF of the shared concepts."""
    qc = set(corpus.nodes[q]["concepts"])
    scores = Counter()
    for c in qc:
        for x in corpus.members.get(c, ()):
            if x != q:
                scores[x] += corpus.idf[c]
    return sorted(scores, key=lambda x: (-scores[x], stable_key("idf", x)))


def shuffled(arm, seed="destroy"):
    """The same returned set as *arm*, in a seeded random order: the destroyed-ranking control."""
    def run(q, corpus):
        return sorted(arm(q, corpus), key=lambda x: stable_key(f"{seed}:{q}", x))
    return run


_KG = {}


def corpus_kg(corpus):
    """The shipping builder's web, rebuilt from the snapshot's nodes so the baseline can't see
    anything the snapshot doesn't hold."""
    key = id(corpus)
    if key not in _KG:
        wiki = {c: set(int(x) if x.isdigit() else x for x in m) for c, m in corpus.members.items()}
        edges = defaultdict(set)
        for m in wiki.values():
            for a in m:
                edges[a] |= m
        for a in edges:
            edges[a].discard(a)
        ideas = {int(k): {"title": v["title"]} for k, v in corpus.nodes.items() if v["type"] == "ideas" and v["in_web"]}
        ca = {k: {"type": v["type"], "title": v["title"], "path": v["path"], "node_class": v["class"]}
              for k, v in corpus.nodes.items() if v["type"] != "ideas" and v["in_web"]}
        _KG[key] = {"ideas": ideas, "ca_nodes": ca, "edges": dict(edges), "wiki_index": wiki,
                    "stats": {}}
    return _KG[key]
