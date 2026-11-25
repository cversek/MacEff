"""Rankers for ``knowledge eval`` that read the artifacts' text: BM25, dense, and two fusions.

The rankers in ``knowledge_eval`` read only the web's concepts. These read what the artifacts
say, so the same labels can judge whether text retrieval helps, and how two retrievers are best
combined.

- **bm25**: SQLite FTS5's Okapi BM25 over each artifact's indexed text; the query is every
  distinct word of the query artifact's indexed text.
- **dense**: all-MiniLM-L6-v2 cosine, on Apple's GPU when present. An artifact is embedded in windows of CHUNK_WORDS words and
  its vector is the normalized mean of its windows, so a long artifact is not cut at the model's
  input limit.
- **hybrid-cc:A**: a convex combination of the two, each list min-max normalized over its own top
  TOP_N: ``A * dense + (1 - A) * bm25``; an artifact missing from one list scores 0 there.
- **hybrid-rrf:K**: reciprocal rank fusion, the sum of ``1 / (K + rank)`` over the two lists.

Every ranker returns its top TOP_N.

**What is indexed.** The text that produced the labels is removed before anything is indexed or
read as a query: a learning's Cross-References section, enhanced citations, and dated artifact
file names of every kind wherever they appear (a checkpoint names the one it continues by its
file, which is the citations label's answer). Leaving them in would hand a ranker the answer, and
the leak audit would refuse it. The trailing Wiki-Links section is removed too, and the concepts are
put back exactly once, so the two contexts below differ only by what the header adds:

- ``plain``: the text, then the concepts as keywords.
- ``header``: a line naming the artifact's kind, date and title and its concepts, then the text.
- ``model``: a context a model wrote for the artifact (``--context-file``), then the plain text.
"""

from __future__ import annotations

import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .knowledge_eval import Corpus, EvalRefused, Ranker, stable_key

CONTEXTS = ("plain", "header", "model")
TOP_N = 100
CHUNK_WORDS = 200
MODEL = "all-MiniLM-L6-v2"
DEFAULT_ALPHA = 0.5
DEFAULT_K = 60
MODEL_COVERAGE_FLOOR = 0.9   # the share of the web that must have a written context

_CITATION = re.compile(r"\[(?:OBSERVATION|LEARNING|REFLECTION|JOTEWR|CCP|CHECKPOINT|EXPERIMENT|REPORT|ROADMAP|"
                       r"MISSION|IDEA)\s+\d{4}-\d{2}-\d{2}[^\]]*\]", re.I)
_DATED_FILE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[A-Za-z0-9_\-]+(?:\.[a-z]{2,4})?")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_WORD = re.compile(r"[^\W_]+")
_KINDS = {"policies": "policy", "personal_policies": "personal policy", "draft_policies": "draft policy",
          "ideas": "idea", "tasks": "task", "duties": "duty", "mis": "MIS", "play_time": "play time",
          "knowledge_bases": "knowledge base", "delegation_trails": "delegation trail"}

Embedder = Callable[[List[str]], "object"]   # texts -> an (n, d) array of unit vectors


def _drop_section(text: str, heading: str) -> str:
    return re.sub(rf"^## {heading}\s*$.*?(?=^## |\Z)", "", text, flags=re.M | re.S)


def body_text(node: dict) -> str:
    """The artifact's text with the label-bearing parts and the Wiki-Links section removed."""
    text = _drop_section(node.get("text") or "", "Cross-References")
    text = _drop_section(text, "Wiki-Links")
    text = _CITATION.sub(" ", text)
    return _DATED_FILE.sub(" ", text)


def _kind(node: dict) -> str:
    t = node.get("type", "")
    return _KINDS.get(t, t[:-1] if t.endswith("s") else t).replace("_", " ")


def indexed_text(node: dict, context: str = "plain", written: Optional[str] = None) -> str:
    """What is indexed for *node*, and what a ranker reads when *node* is the query. *written* is
    the model-written context the ``model`` context puts in front of the plain text."""
    if context not in CONTEXTS:
        raise EvalRefused(f"--context is one of {', '.join(CONTEXTS)}, not {context!r}")
    concepts = " ".join(c.replace("_", " ") for c in node.get("concepts", ()))
    body = body_text(node).strip()
    if context == "plain":
        return f"{body}\n\n{concepts}".strip()
    if context == "model":
        return f"{written or ''}\n\n{body}\n\n{concepts}".strip()
    m = _DATE.search(Path(node.get("path", "")).name)
    header = " ".join(x for x in (_kind(node), m.group(1) if m else "", (node.get("title") or "").strip()) if x)
    return f"{header}. Concepts: {concepts}.\n\n{body}".strip()


def words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def embedding_device() -> str:
    """Apple's GPU when there is one, else the CPU. On the host this was measured on, MPS ran
    28 times faster under load and its vectors matched the CPU's to 2e-7."""
    try:
        import torch
        return "mps" if torch.backends.mps.is_available() else "cpu"
    except (ImportError, AttributeError) as e:
        print(f"warning: no torch device query ({e}); embedding on the CPU", file=sys.stderr)
        return "cpu"


def _minilm() -> Embedder:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise EvalRefused(f"the dense ranker needs sentence-transformers ({e})") from e
    model = SentenceTransformer(MODEL, device=embedding_device())

    def embed(texts: List[str]):
        return model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    return embed


class TextIndex:
    """One context's BM25 table and dense vectors over the web, built once per corpus."""

    def __init__(self, corpus: Corpus, context: str, embedder: Optional[Embedder] = None):
        self.corpus, self.context = corpus, context
        self.ids = list(corpus.web)
        written = getattr(corpus, "model_contexts", None) or {}
        if context == "model":
            if not written:
                raise EvalRefused("the model context needs --context-file: no model-written contexts are loaded")
            covered = sum(1 for nid in self.ids if written.get(nid))
            if covered < MODEL_COVERAGE_FLOOR * len(self.ids):
                # A file keyed by something other than node ids would leave every artifact without its
                # context, and the model arm would silently score the plain text (review of #1155).
                raise EvalRefused(f"the context file covers {covered} of the {len(self.ids)} artifacts in the web, "
                                  f"under the floor of {MODEL_COVERAGE_FLOOR:.0%}; is it keyed by node id?")
        self.text = {nid: indexed_text(corpus.nodes[nid], context, written.get(nid)) for nid in self.ids}
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        self.db.executemany("INSERT INTO t(rowid, body) VALUES (?, ?)",
                            ((i, self.text[nid]) for i, nid in enumerate(self.ids)))
        self._embedder, self._vectors = embedder, None
        self._row = {nid: i for i, nid in enumerate(self.ids)}
        self._bm25: Dict[str, List[Tuple[str, float]]] = {}
        self._dense: Dict[str, List[Tuple[str, float]]] = {}

    def bm25(self, q: str) -> List[Tuple[str, float]]:
        """The top TOP_N other artifacts and their scores, higher better."""
        if q not in self._bm25:
            terms = sorted(set(words(self.text.get(q, ""))))
            rows = []
            if terms:
                match = " OR ".join(f'"{t}"' for t in terms)
                rows = self.db.execute("SELECT rowid, bm25(t) FROM t WHERE t MATCH ? ORDER BY bm25(t), rowid LIMIT ?",
                                       (match, TOP_N + 1)).fetchall()
            self._bm25[q] = [(self.ids[r], -s) for r, s in rows if self.ids[r] != q][:TOP_N]
        return self._bm25[q]

    def vectors(self):
        if self._vectors is None:
            import numpy as np
            embed = self._embedder or _minilm()
            chunks, owner = [], []
            for i, nid in enumerate(self.ids):
                w = self.text[nid].split()
                for start in range(0, max(len(w), 1), CHUNK_WORDS):
                    chunks.append(" ".join(w[start:start + CHUNK_WORDS]))
                    owner.append(i)
            emb = np.asarray(embed(chunks), dtype="float32")
            vec = np.zeros((len(self.ids), emb.shape[1]), dtype="float32")
            np.add.at(vec, np.asarray(owner), emb)
            norms = np.linalg.norm(vec, axis=1, keepdims=True)
            self._vectors = vec / np.where(norms == 0, 1.0, norms)
        return self._vectors

    def dense(self, q: str) -> List[Tuple[str, float]]:
        import numpy as np
        if q not in self._dense:
            qi = self._row.get(q)
            if qi is None:
                return []
            v = self.vectors()
            sims = v @ v[qi]
            sims[qi] = -np.inf
            n = min(TOP_N + 1, len(self.ids))
            top = np.argpartition(-sims, n - 1)[:n] if n < len(self.ids) else np.arange(len(self.ids))
            order = sorted((int(i) for i in top if i != qi),
                           key=lambda i: (-float(sims[i]), stable_key("dense", self.ids[i])))
            self._dense[q] = [(self.ids[i], float(sims[i])) for i in order[:TOP_N]]
        return self._dense[q]


def text_index(corpus: Corpus, context: Optional[str] = None) -> TextIndex:
    """The index for *context* (default the corpus's, ``corpus.context``, plain unless set),
    cached on the corpus so every ranker in a run shares it."""
    context = context or getattr(corpus, "context", "plain")
    cache = corpus.__dict__.setdefault("_text_index", {})
    if context not in cache:
        cache[context] = TextIndex(corpus, context, getattr(corpus, "embedder", None))
    return cache[context]


def _minmax(pairs: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    if not pairs:
        return {}
    lo, hi = min(s for _, s in pairs), max(s for _, s in pairs)
    return {n: (s - lo) / (hi - lo) if hi > lo else 1.0 for n, s in pairs}


def fuse_cc(bm25: Sequence[Tuple[str, float]], dense: Sequence[Tuple[str, float]], alpha: float) -> List[str]:
    b, d = _minmax(bm25), _minmax(dense)
    score = {n: alpha * d.get(n, 0.0) + (1 - alpha) * b.get(n, 0.0) for n in set(b) | set(d)}
    return sorted(score, key=lambda n: (-score[n], stable_key("cc", n)))[:TOP_N]


def fuse_rrf(bm25: Sequence[Tuple[str, float]], dense: Sequence[Tuple[str, float]], k: float) -> List[str]:
    score: Dict[str, float] = {}
    for pairs in (bm25, dense):
        for rank, (n, _) in enumerate(pairs, 1):
            score[n] = score.get(n, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda n: (-score[n], stable_key("rrf", n)))[:TOP_N]


def text_ranker(name: str) -> Optional[Ranker]:
    """The text ranker *name* names, or None if it names none. A parameter follows a colon
    (``hybrid-cc:0.3``, ``hybrid-rrf:30``) and a context an at sign (``bm25@header``), so the two
    arms of a context comparison can be scored, and paired, in one run."""
    spec, ctx = (name.split("@", 1) + [""])[:2]
    if ctx and ctx not in CONTEXTS:
        raise EvalRefused(f"{name!r}: the context after '@' is one of {', '.join(CONTEXTS)}")
    context = ctx or None
    base, param = (spec.split(":", 1) + [""])[:2]

    def idx(c: Corpus) -> TextIndex:
        return text_index(c, context)

    def reads(q: str, c: Corpus) -> str:
        if q in idx(c).text:
            return idx(c).text[q]
        return indexed_text(c.nodes[q], context or getattr(c, "context", "plain"),
                            (getattr(c, "model_contexts", None) or {}).get(q))

    if base == "bm25" and not param:
        return Ranker(name, lambda q, c: [n for n, _ in idx(c).bm25(q)], "FTS5 BM25 over the text", reads)
    if base == "dense" and not param:
        return Ranker(name, lambda q, c: [n for n, _ in idx(c).dense(q)], "MiniLM cosine", reads)
    if base not in ("hybrid-cc", "hybrid-rrf"):
        return None
    try:
        value = float(param) if param else (DEFAULT_ALPHA if base == "hybrid-cc" else DEFAULT_K)
    except ValueError:
        raise EvalRefused(f"{name!r}: the parameter after ':' must be a number") from None
    if base == "hybrid-cc":
        if not 0.0 <= value <= 1.0:
            raise EvalRefused(f"{name!r}: the weight on dense must lie in [0, 1]")
        return Ranker(name, lambda q, c: fuse_cc(idx(c).bm25(q), idx(c).dense(q), value),
                      f"convex combination, {value} on dense", reads)
    if not (math.isfinite(value) and value > 0):
        raise EvalRefused(f"{name!r}: the RRF constant must be a positive finite number")
    return Ranker(name, lambda q, c: fuse_rrf(idx(c).bm25(q), idx(c).dense(q), value),
                  f"reciprocal rank fusion, k = {value:g}", reads)
