"""The arms: queries built from the live trace at each trigger moment, retrieving only what was
outside the context window then. Step 2 pools three of them for the judges; Step 4 evaluates the set.

The trace is COMPUTED over every event before the moment, in three sources:
  conv  transcript events: prompts, compaction summaries, the agent's messages, its tool calls
  task  task-tree and duty events, and old task events the agent re-read (`task get`)
  kg    knowledge-web artifacts, entered when the agent reads, queries or writes one
Each source keeps one integrator for every combination of
  rate  fast 0.3 or slow 0.03
  gain  gated (rate times the event's depth d, the null-direction residual) or constant (rate)
  span  whole (decays over all history) or reset (emptied at each boundary: the in-context turns
        alone, H4's control)
The moment's own text x enters the query as d*x, never its trace. The arm RETRIEVES over the
candidates created before the moment's context began and not consulted since (semantic_trace.allowed).

Arms for pooling, fixed before any weight is chosen on the development split:
  prompt    q = x
  context   q = d*x + mean of unit states (conv fast, task slow, kg slow; gated, reset)
  trace     the same with whole states: the in-context turns plus decayed history

Only development moments are ever scored here; the held split is Step 7's, run once.

Usage: python3 semantic_arms.py    (development metrics against L1 for the pooling arms)
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault("HF_HUB_OFFLINE", "1")      # the model comes from the local cache, never the network

import semantic_trace as st
from semantic_labels import Resolver, collapse, doc_of, load

from kit_config import DATA
SOURCES = ("conv", "task", "kg")
RATES = {"fast": 0.3, "slow": 0.03}
COMBOS = [(s, r, g, sp) for s in SOURCES for r in RATES for g in ("gated", "const") for sp in ("whole", "reset")]
IDX = {c: i for i, c in enumerate(COMBOS)}
POOL_ARMS = ("prompt", "context", "trace")
MIX = (("conv", "fast"), ("task", "slow"), ("kg", "slow"))


def embedder():
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return lambda texts: m.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)


def unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, n, out=np.zeros_like(v), where=n > 0)


def walk(events, cands, E, C, depth, at, resolve, order=None):
    """One pass over the stream. For each event index in `at`, the integrator states just before
    it (the computing domain at t) and the candidates consulted since its context began.
    `order`, the destroyed-trace control: feed position i the content of event order[i] instead,
    while boundaries, moments and what was consulted keep their real places."""
    S = np.zeros((len(COMBOS), E.shape[1]), dtype=np.float32)
    rate = np.array([RATES[c[1]] for c in COMBOS], dtype=np.float32)
    gated = np.array([c[2] == "gated" for c in COMBOS])
    reset = np.array([c[3] == "reset" for c in COMBOS])
    rows = {s: np.array([c[0] == s for c in COMBOS]) for s in SOURCES}
    bounds, t0 = st.boundaries(events), events[0]["t"]
    last, out, want = {}, {}, set(at)

    def feed(src, x, d):
        r = rows[src]
        g = rate[r] * np.where(gated[r], d, 1.0)
        S[r] = (1.0 - g)[:, None] * S[r] + g[:, None] * x

    for i, e in enumerate(events):
        if i in want:
            start = st.context_start(e["t"], bounds, t0)
            out[i] = (S.copy(), start, {cid for cid, tc in last.items() if tc >= start})
        if e["kind"] == "boundary":
            S[reset] = 0.0
            continue
        f = i if order is None else order[i]
        fed = events[f]
        feed("conv" if fed["scope"] == "conv" else "task", E[f], depth[f])
        if fed["kind"] == "tool":
            # sorted: a set of strings iterates in a per-process hash order, and leaky integration
            # does not commute, so feeding in set order made the trace differ run to run (15:04)
            for key in sorted(st.consult_keys(fed)):
                for cid in resolve(key):
                    feed("kg" if cands[cid]["source"] == "kg" else "task", C[cid], 1.0)
        if e["kind"] == "tool":
            for key in st.consult_keys(e):
                for cid in resolve(key):
                    last[cid] = e["t"]
    return out


def destroyed_order(events, seed="exp014-destroyed"):
    """A permutation of the non-boundary events among the non-boundary positions."""
    pos = [i for i, e in enumerate(events) if e["kind"] != "boundary"]
    rng = np.random.default_rng(int(__import__("hashlib").sha256(seed.encode()).hexdigest()[:8], 16))
    order = list(range(len(events)))
    for p, q in zip(pos, rng.permutation(pos)):
        order[p] = int(q)
    return order


def query(arm, x, d, S, mix=MIX, gain="gated"):
    if arm == "prompt":
        return x
    span = "reset" if arm == "context" else "whole"
    return d * x + unit(np.stack([S[IDX[(s, r, gain, span)]] for s, r in mix])).mean(axis=0)


def scores(M, q):
    """Cosines rounded to 1e-9 in float64, so the last bits of a BLAS sum, which vary from run to
    run, cannot reorder a near-tie (found 15:03: the trace arm's 5th document flipped between runs)."""
    return np.round(M.astype(np.float64, copy=False) @ np.asarray(q, dtype=np.float64), 9)


def ranked(q, C, cand_t, start, in_ctx, k):
    """The top k candidates for q among those allowed at the moment, best first, ties by id."""
    s = scores(C, q)
    s[cand_t >= start] = -np.inf
    if in_ctx:
        s[list(in_ctx)] = -np.inf
    order = np.lexsort((np.arange(len(s)), -s))[:k]
    return [int(c) for c in order if np.isfinite(s[c])]


def metrics(rank, rel):
    """MRR, P@3 and binary nDCG@10 of one ranking against a set of relevant ids."""
    first = next((j for j, c in enumerate(rank) if c in rel), None)
    dcg = sum(1 / np.log2(j + 2) for j, c in enumerate(rank[:10]) if c in rel)
    idcg = sum(1 / np.log2(j + 2) for j in range(min(len(rel), 10)))
    return {"mrr": 0.0 if first is None else 1 / (first + 1), "p3": sum(c in rel for c in rank[:3]) / 3,
            "ndcg10": dcg / idcg if idcg else 0.0}


def setup(with_raw=False):
    events, cands, split = load()
    E = np.load(DATA / "emb_events.npy").astype(np.float32)
    C = np.load(DATA / "emb_candidates.npy").astype(np.float32)
    assert len(E) == len(events) and len(C) == len(cands), "embeddings and snapshot disagree: rebuild the index"
    emb = embedder()
    null_dir = st.null_direction(emb)
    r0 = st.null_radius(emb(st.NULL_SEEDS), null_dir)
    print(f"null radius r0 = {r0:.4f} (expected 0.4217)")   # stated every run: a stale build ran another r0 once
    raw = np.clip(1.0 - np.concatenate([scores(E[j:j + 8192], null_dir) for j in range(0, len(E), 8192)]), 0.0, 1.0)  # H1's measure
    depth = st.gate_depth(raw, r0)                       # what gates the integrators and weights x
    labels = json.loads((DATA / "l1_labels.json").read_text())["moments"]
    dev = [m for m in labels if m["split"] == "dev"]
    cand_t = np.array([c["t"] for c in cands])
    if with_raw:
        return events, cands, E, C.astype(np.float64), depth, dev, cand_t, raw
    return events, cands, E, C.astype(np.float64), depth, dev, cand_t


def main(k=10):
    events, cands, E, C, depth, dev, cand_t = setup()
    docs = [doc_of(c, events) for c in cands]
    scored = [m for m in dev if m["docs"]]
    states = walk(events, cands, E, C, depth, [m["i"] for m in scored], Resolver(events, cands))
    acc = defaultdict(lambda: defaultdict(list))
    for m in scored:
        S, start, in_ctx = states[m["i"]]
        x, d = E[m["i"]], float(depth[m["i"]])
        for arm in POOL_ARMS:
            r = collapse(ranked(query(arm, x, d, S), C, cand_t, start, in_ctx, 6 * k), docs, k)
            for name, v in metrics(r, set(m["docs"])).items():
                acc[(arm, m["kind"])][name].append(v)
                acc[(arm, "all")][name].append(v)
    for (arm, kind), vals in sorted(acc.items(), key=lambda x: (x[0][1], x[0][0])):
        print(f"{kind:4s} {arm:8s} n={len(vals['mrr']):4d}  " + "  ".join(f"{n} {np.mean(v):.3f}" for n, v in vals.items()))


if __name__ == "__main__":
    main()
