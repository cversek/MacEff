"""Step 7: the sealed future split, run once.

Before anything is scored, the held prompt ids are recomputed from the snapshot and must hash to the
value sealed in data/split_manifest.json; the script refuses to run if data/step7_heldout.json exists.
Only arms and weights frozen on the development split are scored, on L1, per document:
  prompt                 q = x
  task_fast, kg_fast     single-source traces (gated), untuned
  mixture                Tier A, gated gain, whole span, all-dev weights (Step 4)
  context                the same weights, reset span: the in-context turns only (H4's control)
  mixture_const          Tier A, constant gain, whole span, its own all-dev weights (H2's gating)
  tier_b                 the learned convolution, all-dev kernel (Step 5, H6)
  destroyed              the mixture's weights over states from a shuffled stream (the control)
Paired bootstrap intervals (2,000 resamples) over held moments, and the development value of each
arm beside its held value.
Writes data/step7_heldout.json.
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from semantic_arms import destroyed_order, setup, walk
from semantic_labels import Resolver, doc_of
from semantic_tier_a import PARTS, boot, cache, evaluate
from semantic_tier_b import bin_vectors, feeds

from kit_config import DATA
OUT = DATA / "step7_heldout.json"


def check_seal(events):
    split = json.loads((DATA / "split_manifest.json").read_text())
    held = [e["id"] for e in sorted((e for e in events if e["kind"] == "prompt" and e["origin"] in ("operator", "telegram")),
                                    key=lambda e: e["t"]) if e["t"] >= split["cutoff_epoch"]]
    digest = hashlib.sha256("\n".join(map(str, held)).encode()).hexdigest()
    assert digest == split["held_ids_sha256"], "the held split does not match its seal"
    return split


def tier_b_cache(moments, events, cands, E, C, depth, cand_t, resolve, states):
    fd = feeds(events, cands, E, C, resolve)
    out = {}
    for m in moments:
        _, start, in_ctx = states[m["i"]]
        Q = np.vstack([E[m["i"]][None, :].astype(np.float64), bin_vectors(fd, m["i"])])
        sc = (C @ Q.T).astype(np.float32)
        ok = cand_t < start
        if in_ctx:
            ok[list(in_ctx)] = False
        out[m["i"]] = (sc, ok, float(depth[m["i"]]))
    return out


def main():
    dry = "--dry-dev" in sys.argv          # the same code path over development moments; writes nothing
    if OUT.exists() and not dry:
        sys.exit(f"refusing: {OUT.name} exists, and the sealed split is run once")
    events, cands, E, C, depth, dev, cand_t = setup()
    check_seal(events)
    labels = json.loads((DATA / "l1_labels.json").read_text())["moments"]
    held = [m for m in labels if m["split"] == ("dev" if dry else "held") and m["docs"]]
    docs = [doc_of(c, events) for c in cands]
    tier_a_weights = json.loads((DATA / "step4_tier_a.json").read_text())["weights"]
    tier_b_weights = json.loads((DATA / "step5_tier_b.json").read_text())["all_dev_weights"]
    resolve = Resolver(events, cands)
    at = [m["i"] for m in held]
    real = walk(events, cands, E, C, depth, at, resolve)
    shuffled = walk(events, cands, E, C, depth, at, resolve, order=destroyed_order(events))
    whole = cache(held, real, E, C, depth, cand_t, "gated", "whole")
    one = lambda p: [1.0 if q == p else 0.0 for q in PARTS]
    per = {"prompt": evaluate(held, {i: (sc, ok, 1.0) for i, (sc, ok, _) in whole.items()}, [0.0] * len(PARTS), docs),
           "task_fast": evaluate(held, whole, one(("task", "fast")), docs),
           "kg_fast": evaluate(held, whole, one(("kg", "fast")), docs),
           "mixture": evaluate(held, whole, tier_a_weights["mix:gated:whole:all_dev"], docs),
           "context": evaluate(held, cache(held, real, E, C, depth, cand_t, "gated", "reset"), tier_a_weights["mix:gated:whole:all_dev"], docs),
           "mixture_const": evaluate(held, cache(held, real, E, C, depth, cand_t, "const", "whole"), tier_a_weights["mix:const:whole:all_dev"], docs),
           "tier_b": evaluate(held, tier_b_cache(held, events, cands, E, C, depth, cand_t, resolve, real), tier_b_weights, docs),
           "destroyed": evaluate(held, cache(held, shuffled, E, C, depth, cand_t, "gated", "whole"), tier_a_weights["mix:gated:whole:all_dev"], docs)}
    strata = defaultdict(list)
    t1 = sorted((m for m in held if m["kind"] == "T1"), key=lambda m: (float(depth[m["i"]]), m["i"]))
    for j, m in enumerate(t1):
        strata[f"T1/depth{1 + 3 * j // len(t1)}"].append(m["i"])
    for m in held:
        strata[m["kind"]].append(m["i"])
        strata["all"].append(m["i"])
    table = {s: {a: {k: round(float(np.mean([per[a][i][j] for i in ids])), 4) for j, k in enumerate(("mrr", "p3", "ndcg10"))}
                 for a in per} for s, ids in strata.items()}
    for s in table:
        table[s]["moments"] = len(strata[s])
    pairs = [("prompt", "mixture"), ("prompt", "task_fast"), ("destroyed", "mixture"), ("context", "mixture"),
             ("mixture_const", "mixture"), ("task_fast", "tier_b"), ("mixture", "tier_b")]
    comparisons = {s: {f"{b} minus {a}": boot([per[b][i][0] - per[a][i][0] for i in ids], f"held|{s}|{a}|{b}") for a, b in pairs}
                   for s, ids in strata.items()}
    dev_a = json.loads((DATA / "step4_tier_a.json").read_text())["table_L1"]
    dev_b = json.loads((DATA / "step5_tier_b.json").read_text())["mrr_cv"]
    beside = {s: {"prompt": dev_a[s]["prompt"]["mrr"], "task_fast": dev_a[s]["single:task:fast"]["mrr"],
                  "mixture_cv": dev_a[s]["mix:gated:whole"]["mrr"], "mixture_in_sample": dev_a[s].get("mix:gated:whole:in_sample", {}).get("mrr"),
                  "tier_b_cv": dev_b.get(s)} for s in table if s in dev_a}
    out = {"held_moments": len(held), "table_L1": table, "comparisons_mrr": comparisons, "dev_beside": beside,
           "frozen": {"mixture_weights": tier_a_weights["mix:gated:whole:all_dev"], "tier_b_weights": tier_b_weights}}
    if not dry:
        OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    for s in ("all", "T1", "T1/depth1", "T1/depth2", "T1/depth3", "T2", "T3", "T4", "T5"):
        if s in table:
            print(f"{s:10s} n={table[s]['moments']:3d} " + " ".join(f"{a}={table[s][a]['mrr']:.3f}" for a in per))
    for s in ("all", "T1/depth1", "T1/depth3", "T2", "T5"):
        if s in comparisons:
            print(s, {k: (v["diff"], v["ci95"]) for k, v in comparisons[s].items()})


if __name__ == "__main__":
    main()
