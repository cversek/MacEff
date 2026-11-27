"""E7 arms A1 to A6 and AR: the as-of index, walked with the live service's integrators and weights.

    python3 arms.py           development days (reads out/a0_picks.json, writes out/arms_dev.pkl)
    python3 arms.py --sealed  sealed days (reads out/a0_picks_sealed.json): NOT run in the development phase

The trace: the Experiment 014 kit's event stream over the whole record (transcript, task and duty
stores), fed through the live service's integrators (Trace's feed rule) with its Step 4 weights
(task fast 2.0, kg fast 1.0, prompt d). A consult feeds only candidates that existed at the call.
The index: candidates created before the moment (spans, task and duty events, knowledge-web
artifacts), artifact text with Cross-References, Wiki-Links, citations and concept keywords stripped
(the kit's clean tier, keywords slot empty), task events dated after the moment never exist.
Retrieval: candidates created before the context began and not consulted since, as in the trial.
Each moment stores its top 400 candidates (and top 200 without tasks, for A5); the arms are formed
from these in score.py.
"""
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
def _need(name):
    """A path the kit can't guess, from the environment, or a refusal that names it."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"E7 needs {name}: see the kit's README (it runs only on a seat that ran the push trial)")
    return value


KIT = Path(_need("E7_PUSH_TRIAL_DIR")) / "kit"
os.environ["MACF_KIT_OUT"] = str(CACHE / "kit_out")
os.environ["MACF_KIT_HOME"] = str(Path.home())
os.environ["MACF_KIT_TRANSCRIPTS"] = _need("E7_TRANSCRIPT")
os.environ["MACF_KIT_SNAPSHOT"] = str(CACHE / "snapshot.json")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "exp010"))
sys.path.insert(0, str(HERE))
import e7lib as L  # noqa: E402
import semantic_trace as st  # noqa: E402
from semantic_arms import embedder, unit  # noqa: E402
from semantic_index import KNOWLEDGE, created_at  # noqa: E402
from semantic_labels import Resolver, doc_of  # noqa: E402

SEALED = "--sealed" in sys.argv
W_TASK, W_KG, RATE = 2.0, 1.0, 0.3      # the live service's weights: mix:gated:whole:all_dev, fast rate


def build_events():
    kit = L.load("kit_events")
    ev = [e for e in kit["transcript"] + kit["task"] + kit["duty"]]
    ev.sort(key=lambda e: (e["t"], e["scope"], e["kind"], e["text"]))
    for i, e in enumerate(ev):
        e["id"] = i
    return ev


def build_candidates(events):
    """semantic_index.build_candidates, with the knowledge-web text in the clean tier and no concepts."""
    cands, cycle, span = [], 0, None
    for e in events:
        if e["kind"] == "boundary":
            cycle += 1
            if span:
                cands.append(span)
            span = None
            continue
        if e["scope"] == "conv" and e["kind"] != "summary":
            opens = e["kind"] == "prompt" and e["origin"] in ("operator", "telegram", "slash")
            if opens or span is None:
                if span:
                    cands.append(span)
                span = {"source": "span", "t": e["t"], "cycle": cycle, "start_event": e["id"], "parts": [], "tools": []}
                if e.get("bc"):
                    span["bc"] = e["bc"]
            if e["kind"] == "prompt":
                span["parts"].append(e["text"][:400] if opens else f"[{e['origin']}] {e['text'][:150]}")
            elif e["kind"] == "agent":
                span["parts"].append(e["text"][:300])
            elif e["kind"] == "tool":
                span["tools"].append(e["text"][:80])
            span["end"] = e["t"]
        elif e["scope"] in ("task", "duty"):
            cands.append({"source": e["scope"], "t": e["t"], "cycle": cycle, "event": e["id"], "text": e["text"][:1200]})
    if span:
        cands.append(span)
    for c in cands:
        if c["source"] == "span":
            c["text"] = (" | ".join(c.pop("parts"))[:1100] + " || " + "; ".join(c.pop("tools"))[:300]).strip()
            # a span exists once it is complete: it is retrievable only before a boundary after its end
            c["t_exists"] = c.get("end", c["t"])
    from lib import Corpus
    from kw_extractor import KWExtractor
    corpus = Corpus(L.CACHE / "snapshot.json")
    ex = KWExtractor(corpus, with_concepts=False, tier="clean")
    for nid, v in corpus.nodes.items():
        if v["type"] in KNOWLEDGE and v["in_web"] and ex.should_index(nid):
            cands.append({"source": "kg", "t": created_at(nid, v), "cycle": None, "node": nid, "kg_type": v["type"],
                          "path": v["path"], "text": ex.generate_embedding_text(ex.extract_document(nid))[:1500]})
    for i, c in enumerate(cands):
        c["id"] = i
    return cands


def embed_cached(texts, emb_fn):
    path = CACHE / "emb_live.pkl"
    cached = pickle.load(open(path, "rb")) if path.exists() else {}
    todo = sorted({t for t in texts if t not in cached})
    if todo:
        print(f"embedding {len(todo)} new texts", flush=True)
        X = emb_fn(todo)
        cached.update({t: X[i] for i, t in enumerate(todo)})
        pickle.dump(cached, open(path, "wb"))
    return cached


def main():
    t0 = time.time()
    moms = json.loads((HERE / "out" / ("a0_picks_sealed.json" if SEALED else "a0_picks.json")).read_text())
    split = "sealed" if SEALED else "dev"
    moms = sorted([m for m in moms if m["split"] == split and m.get("text")], key=lambda m: m["r"])
    events = build_events()
    cands = build_candidates(events)
    print(f"events {len(events)}, candidates {len(cands)}, moments {len(moms)}", flush=True)
    embed = embedder()
    null_dir = st.null_direction(embed)
    r0 = st.null_radius(embed(st.NULL_SEEDS), null_dir)
    feed_texts = [e["text"] or " " for e in events if e["scope"] in ("task", "duty")]
    cache = embed_cached([c["text"] or " " for c in cands] + feed_texts + [m["text"] or " " for m in moms], embed)
    C = np.stack([cache[c["text"] or " "] for c in cands]).astype(np.float64)
    Cf = C.astype(np.float32)

    def depth(x):
        return float(st.gate_depth(np.clip(1.0 - np.asarray(x, dtype=np.float32) @ null_dir, 0.0, 1.0), r0))

    cand_t = np.array([c.get("t_exists", c["t"]) for c in cands])
    is_task = np.array([c["source"] == "task" for c in cands])
    resolve = Resolver(events, cands)
    bounds = st.boundaries(events)
    tstart = events[0]["t"]
    S_task = np.zeros(C.shape[1], dtype=np.float32)
    S_kg = np.zeros(C.shape[1], dtype=np.float32)
    last = {}
    out = []
    ei = 0
    for m in moms:
        r = m["r"]
        while ei < len(events) and events[ei]["t"] < r:
            e = events[ei]
            ei += 1
            if e["kind"] == "boundary":
                continue                       # resets only the reset rows, which the weights do not use
            if e["scope"] in ("task", "duty"):
                x = cache[e["text"] or " "]
                g = RATE * depth(x)
                S_task = (1.0 - g) * S_task + g * x
            if e["kind"] == "tool":
                for key in sorted(st.consult_keys(e)):
                    for cid in resolve(key):
                        if cand_t[cid] >= e["t"]:
                            continue           # it did not exist yet
                        if cands[cid]["source"] == "kg":
                            S_kg = (1.0 - RATE) * S_kg + RATE * Cf[cid]
                        else:
                            S_task = (1.0 - RATE) * S_task + RATE * Cf[cid]
                        last[cid] = e["t"]
        x = cache[m["text"] or " "]
        d = depth(x)
        q = d * x.astype(np.float64) + W_TASK * unit(S_task).astype(np.float64) + W_KG * unit(S_kg).astype(np.float64)
        start = st.context_start(r, bounds, tstart)
        s = np.round(C @ q, 9)
        s[cand_t >= start] = -np.inf
        ctx = [cid for cid, tc in last.items() if tc >= start]
        if ctx:
            s[ctx] = -np.inf
        order = np.lexsort((np.arange(len(s)), -s))
        top = [int(c) for c in order[:400] if np.isfinite(s[c])]
        nt = [int(c) for c in order[:6000] if np.isfinite(s[c]) and not is_task[c]][:200]
        out.append({"ts": m["ts"], "r": r, "ctx_start": start, "top": top, "top_s": [float(s[c]) for c in top],
                    "notask": nt, "notask_s": [float(s[c]) for c in nt], "d": d})
    meta = {"cands": [{k: c.get(k) for k in ("source", "t", "t_exists", "node", "path", "event", "bc", "id")} for c in cands],
            "task_of": {c["id"]: events[c["event"]].get("task") for c in cands if c["source"] == "task"},
            "duty_of": {c["id"]: events[c["event"]].get("duty") for c in cands if c["source"] == "duty"},
            "task_events": [{"t": e["t"], "kind": e["kind"], "task": e.get("task")} for e in events if e["scope"] == "task"]}
    pickle.dump({"moments": out, "meta": meta}, open(HERE / "out" / f"arms_{split}.pkl", "wb"))
    print(f"arms ranked {len(out)} moments in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
