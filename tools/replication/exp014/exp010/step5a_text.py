"""Step 5a: the falsifiers. H4 BM25 and H5 MiniLM over artifact text.

Fairness rules, fixed before running:
  - Labels are stripped from EVERY text the text arms see: a learning's Cross-References section
    is its S1 labels and a citation bracket is an S2 label. Left in, BM25 would read the answers.
  - Text arms search the full corpus (the operator's choice), and are also scored over web nodes
    only, for a like-for-like ranking comparison; reachability is reported apart.
  - A planted query whose answer is lexically obvious must be retrieved by BM25 first.
Query unit: as Step 1, query-by-artifact, the query being the artifact's stripped text.

Tiers (argument; default strict): strict, the run of Oct 17 11:15; clean, which also strips what a
second audit found strict leaves (strip_clean); clean_nolineage, clean without dates, times and
breadcrumbs. Writes data/step5a_text.json (strict) or data/step5a_text_<tier>.json, each with a
leak audit, and caches embeddings in data/minilm_<tier>_<snapshot>.npy.
"""
import json
import math
import re
from collections import Counter, defaultdict

import numpy as np

from lib import Corpus, HERE, METRICS, s1_labels, stable_key
from step1_control import split
from step2_h0 import CITE, s2_labels, s3_labels

STOP = set("the a an and or of to in is it that this for on with as be are was by not at from but if so do no "
           "we i you they he she its our their what when which who how all any can will would should could".split())


def strip_labels(text):
    """Strict: no label tokens and no concept tokens. Cross-References are S1 and citation
    brackets S2; a learning's Category line names its index cluster, which IS S3 (found after the
    first run, which kept it); and the Wiki-Links section is the graph arms' own input, so a
    text arm that read it would not be testing text against concepts."""
    text = re.sub(r"^## (Cross-References|Wiki-Links)\s*$.*?(?=^## |\Z)", "", text, flags=re.M | re.S)
    text = re.sub(r"^\*\*Category\*\*:.*$", "", text, flags=re.M)
    text = re.sub(r"\[\[[^\]]+\]\]", "", text)
    return CITE.sub("", text)


CITE_WHOLE = re.compile(r"\[(?:OBSERVATION|LEARNING|REFLECTION|JOTEWR|CCP|CHECKPOINT|EXPERIMENT|REPORT|ROADMAP|MISSION|"
                        r"IDEA)\s+\d{4}-\d{2}-\d{2}[^\]]*\](?:\([^)]*\))?", re.I)
LINK_KEYS = re.compile(r"^\s*\*\*(?:Related|Cluster|Keywords|Provenance)\*\*:.*$", re.M)
DATED_FILE = re.compile(r"\b\d{4}-\d{2}-\d{2}_[0-9A-Za-z_\-]+(?:/[0-9A-Za-z_.\-]+)*(?:\.md|\.json)?")


def strip_clean(text):
    """strip_labels, then what a second audit found it leaves:
    CITE stops at the title's closing quote, so a citation's breadcrumb and link survive, an
    exact match to the cited artifact's header; a learning's Related line lists learning file
    names, 239 of them S1 targets of the same query; Cluster names the S3 cluster; Keywords is
    concept vocabulary; Provenance marks the inherited cluster. So: whole citations first, before
    CITE can cut them short, then those four lines, then every dated artifact file or folder name,
    since a file name in a text is an explicit link and not prose."""
    text = strip_labels(CITE_WHOLE.sub("", text))
    return DATED_FILE.sub("", LINK_KEYS.sub("", text))


LINEAGE = [re.compile(p, re.M) for p in (
    r"^\s*\*\*[^*\n]+\*\*:.*$",                         # **Created**: ..., **Source**: ..., **Date**: ...
    r"\bs_[0-9a-f]{6,}(?:/[a-z]_[0-9A-Za-z]+)*",        # a breadcrumb, whole
    r"\b(?:c_\d+|p_[0-9a-f]{6,}|t_\d{9,})\b",           # or in pieces
    r"\b\d{4}-\d{2}-\d{2}\b",                           # dates
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b",                    # clock times
)]


def strip_lineage(text):
    """When and in which session a text was written: metadata lines, breadcrumbs, dates, times."""
    for p in LINEAGE:
        text = p.sub("", text)
    return text


TIERS = {"strict": strip_labels, "clean": strip_clean, "clean_nolineage": lambda t: strip_lineage(strip_clean(t))}


def leak_audit(texts, sources, corpus):
    """For each label pair, does the query's text still name its target? A target is named by its
    dated file or folder name, or by a prompt id from its own header breadcrumb that the query's
    own header doesn't share (a shared one is lineage, not a link). Reported per source; anything
    above zero is an answer key a text arm can read."""
    from pathlib import Path
    names, prompts = {}, {}
    for k, v in corpus.nodes.items():
        p = Path(v["path"])
        names[k] = [n for n in (p.stem, p.parent.name) if re.match(r"\d{4}-\d{2}-\d{2}_.{6,}", n)]
        prompts[k] = set(re.findall(r"\bp_[0-9a-f]{8}\b", "\n".join(v["text"].splitlines()[:15])))
    out = {}
    for s, labels in sources.items():
        pairs = [(q, t) for q, ts in labels.items() for t in ts]
        named = sum(1 for q, t in pairs
                    if any(n in texts[q] for n in names[t]) or any(p in texts[q] for p in prompts[t] - prompts[q]))
        out[s] = {"pairs": len(pairs), "target_named_in_query": named, "share": round(named / max(1, len(pairs)), 4)}
    return out


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9_\-]+", text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.ids = list(docs)
        self.tf = {d: Counter(tokens(t)) for d, t in docs.items()}
        self.len = {d: sum(c.values()) for d, c in self.tf.items()}
        self.avg = sum(self.len.values()) / max(1, len(self.len))
        df = Counter(t for c in self.tf.values() for t in c)
        N = len(self.ids)
        self.idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.post = defaultdict(list)
        for d, c in self.tf.items():
            for t, f in c.items():
                self.post[t].append((d, f))
        self.k1, self.b = k1, b

    def rank(self, qtext, exclude=None, allowed=None):
        qt = Counter(tokens(qtext))
        s = Counter()
        for t in qt:
            idf = self.idf.get(t)
            if idf is None:
                continue
            for d, f in self.post[t]:
                s[d] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[d] / self.avg))
        return [d for d in sorted(s, key=lambda d: (-s[d], stable_key("bm25", d)))
                if d != exclude and (allowed is None or d in allowed)]


def evaluate(rank_fn, queries, labels, corpus, allowed):
    tot, setrec, sub = Counter(), 0.0, 0.0
    for q in queries:
        ranked = rank_fn(q, allowed)
        assert q not in ranked
        for name, f in METRICS.items():
            tot[name] += f(ranked, labels[q])
        setrec += len(set(ranked) & labels[q]) / len(labels[q])
        sub += len(ranked) / len(allowed)
    n = len(queries)
    out = {k: round(v / n, 4) for k, v in tot.items()}
    out.update({"set_recall": round(setrec / n, 4), "returned_share": round(sub / n, 4)})
    return out


def main(tier="strict"):
    corpus = Corpus()
    texts = {k: TIERS[tier](v["text"]) for k, v in corpus.nodes.items()}
    bm = BM25(texts)
    # Planted query: a distinctive phrase from one learning must bring that learning back first.
    target = sorted(k for k, v in corpus.nodes.items() if v["type"] == "learnings")[7]
    words = [w for w in tokens(texts[target]) if bm.idf.get(w, 0) > 5][:6]
    planted_ok = bool(words) and bm.rank(" ".join(words))[:1] == [target]
    # MiniLM embeddings over the full corpus, cached by snapshot hash.
    import hashlib
    snap_hash = hashlib.sha256((HERE / "data/corpus_snapshot.json").read_bytes()).hexdigest()[:12]
    cache = HERE / f"data/minilm_{tier}_{snap_hash}.npy"
    ids = sorted(texts)
    if cache.exists():
        E = np.load(cache)
    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        E = model.encode([texts[i][:4000] for i in ids], batch_size=64, normalize_embeddings=True,
                         show_progress_bar=False)
        np.save(cache, E)
    pos = {k: i for i, k in enumerate(ids)}

    def minilm(q, allowed):
        sims = E @ E[pos[q]]
        order = np.argsort(-sims, kind="stable")
        return [ids[i] for i in order if ids[i] != q and ids[i] in allowed]

    def bm25(q, allowed):
        return bm.rank(texts[q], exclude=q, allowed=allowed)

    sources = {"S1": s1_labels(corpus), "S2": s2_labels(corpus)[0], "S3": s3_labels(corpus)[0]}
    scopes = {"full_corpus": set(corpus.everything), "web_only": set(corpus.web)}
    results = {}
    for s, labels in sources.items():
        dev = split(sorted(labels))[0]
        for scope, allowed in scopes.items():
            for name, fn in (("H4_bm25", bm25), ("H5_minilm", minilm)):
                results.setdefault(s, {})[f"{name}@{scope}"] = evaluate(fn, dev, labels, corpus, allowed)
    out = {"split": "dev", "planted_query_retrieved": planted_ok, "planted": {"target": target, "words": words},
           "embedding_cache": cache.name, "tier": tier, "leak_audit": leak_audit(texts, sources, corpus),
           "results": results}
    name = "step5a_text.json" if tier == "strict" else f"step5a_text_{tier}.json"
    (HERE / "data" / name).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("leak audit:", json.dumps(out["leak_audit"]))
    print("planted query retrieved:", planted_ok, words)
    for s in results:
        print("==", s)
        for a, r in results[s].items():
            print(f"  {a:24s}", "  ".join(f"{k}={v}" for k, v in r.items()))


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "strict")
