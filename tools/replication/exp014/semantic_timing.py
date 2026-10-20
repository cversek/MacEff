"""Step 6a: when do consults happen (H8), and how often should a mid-stretch push fire (the N sweep)?

H8 predicts that most consults fall in the first few tool calls after an operator's prompt, that a
measurable share comes mid-stretch (where a push every N tool calls would catch it), and that some come
just before an artifact is written (where T5 would). Its null is that consults are spread evenly, so
every share is set beside the same share among all tool calls (the base rate) and reported as a ratio.
A consult here is a tool call that reads something in the record that resolves to a candidate.
Only the development period (before the sealed split's cutoff) is used.

The N sweep: T2 moments at N = 10, 20 and 40, each labeled exactly as Step 2 labels moments, and
scored on L1 with prompt-only, the single task trace (task, fast) and Step 4's all-dev mixture.
Writes data/step6_timing.json.
"""
import json
from collections import Counter
from pathlib import Path

import numpy as np

import semantic_trace as st
from semantic_arms import setup, walk
from semantic_labels import Resolver, doc_of, label_moments, load
from semantic_tier_a import PARTS, cache, evaluate

from kit_config import DATA


def positions(events, resolve, cutoff):
    """For each tool call before the cutoff: calls since the operator's last prompt, calls until the
    next artifact write, and whether it consults the record."""
    rows, since, last_prompt_ok = [], None, False
    writes = [i for i, e in enumerate(events) if e.get("writes_ca")]
    tools = [i for i, e in enumerate(events) if e["kind"] == "tool"]
    tool_rank = {i: r for r, i in enumerate(tools)}
    wpos = np.array([tool_rank[i] for i in writes])
    for i, e in enumerate(events):
        if e["t"] >= cutoff:
            break
        if e["kind"] == "boundary":
            since = None
        elif e["kind"] == "prompt" and e["origin"] in ("operator", "telegram", "slash"):
            since = 0
        elif e["kind"] == "tool":
            if since is not None:
                since += 1
            r = tool_rank[i]
            j = np.searchsorted(wpos, r)
            to_write = int(wpos[j] - r) if j < len(wpos) else None
            consults = any(resolve(k) for k in st.consult_keys(e))
            rows.append({"since_prompt": since, "to_write": to_write, "consults": consults})
    return rows


def main():
    events, cands, split = load()
    cutoff = split["cutoff_epoch"]
    resolve = Resolver(events, cands)
    rows = [r for r in positions(events, resolve, cutoff) if r["since_prompt"] is not None]
    cons = [r for r in rows if r["consults"]]
    share = lambda xs, f: sum(1 for r in xs if f(r)) / len(xs)
    bands = {"first_3": lambda r: r["since_prompt"] <= 3, "4_to_20": lambda r: 3 < r["since_prompt"] <= 20,
             "after_20": lambda r: r["since_prompt"] > 20,
             "within_3_before_a_write": lambda r: r["to_write"] is not None and 0 < r["to_write"] <= 3}
    timing = {b: {"consults": round(share(cons, f), 3), "all_tool_calls": round(share(rows, f), 3),
                  "ratio": round(share(cons, f) / share(rows, f), 2) if share(rows, f) else None} for b, f in bands.items()}
    timing["n"] = {"tool_calls": len(rows), "consults": len(cons)}
    # the N sweep
    ev, cd, E, C, depth, dev, cand_t = setup()
    docs = [doc_of(c, ev) for c in cd]
    w = json.loads((DATA / "step4_tier_a.json").read_text())["weights"]["mix:gated:whole:all_dev"]
    sweep = {}
    for n in (10, 20, 40):
        ms = [m for m in st.moments(ev, n_tool=n) if m["kind"] == "T2"]
        lab, _, _ = label_moments(ev, cd, split, ms, Resolver(ev, cd))
        lab = [m for m in lab if m["split"] == "dev"]
        scored = [m for m in lab if m["docs"]]
        if not scored:               # a record with no stretch this long, or none labeled
            sweep[n] = {"moments": len(lab), "labeled": 0, "labeled_share": None, "mrr": None}
            continue
        states = walk(ev, cd, E, C, depth, [m["i"] for m in scored], Resolver(ev, cd))
        c = cache(scored, states, E, C, depth, cand_t, "gated", "whole")
        arms = {"prompt": evaluate(scored, {i: (sc, ok, 1.0) for i, (sc, ok, _) in c.items()}, [0.0] * len(PARTS), docs),
                "task_fast": evaluate(scored, c, [1.0 if p == ("task", "fast") else 0.0 for p in PARTS], docs),
                "mixture": evaluate(scored, c, w, docs)}
        sweep[n] = {"moments": len(lab), "labeled": len(scored), "labeled_share": round(len(scored) / len(lab), 3),
                    "mrr": {a: round(float(np.mean([v[0] for v in r.values()])), 4) for a, r in arms.items()}}
    out = {"timing_H8": timing, "n_sweep": sweep}
    (DATA / "step6_timing.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
