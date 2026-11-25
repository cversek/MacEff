"""E4, H4e: the static checklist against retrieval of at most three obligations, at session starts
where at least one obligation was dropped. Compaction starts and restarts are scored apart.

usage: e4_h4e.py OBLIGATIONS WINNER CACHE_DIR
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from e4_lib import Index, paired_interval, rank  # noqa: E402


def main(path, winner, cache):
    rows = json.load(open(path))
    shared = Index("probe", ["x"], [0])
    embed = shared.embedder()
    out = {"winner": winner}
    for kind in ("compaction", "restart"):
        rec_ret, rec_list, tok_ret, tok_list = [], [], [], []
        for r in rows:
            if r["kind"] != kind:
                continue
            obs = r["obligations"]
            dropped = {i for i, o in enumerate(obs) if not o["done"]}
            if not dropped:
                continue
            idx = Index(f"obl{len(obs)}", [o["item"] for o in obs], list(range(len(obs))), None, embed)
            top = rank(idx, r["prompt"] or " ", winner, n=3)[0]
            rec_ret.append(len(dropped & set(top)) / len(dropped))
            rec_list.append(1.0)
            tok_ret.append(sum(len(obs[i]["item"]) for i in top) / 4)
            tok_list.append(sum(len(o["item"]) for o in obs) / 4)
        iv = paired_interval(rec_list, rec_ret)
        res = {"starts_scored": len(rec_ret),
               "recall_retrieval": round(sum(rec_ret) / len(rec_ret), 4) if rec_ret else None,
               "recall_checklist": 1.0 if rec_ret else None,
               "retrieval_minus_checklist": iv,
               "tokens_retrieval_mean": round(sum(tok_ret) / len(tok_ret), 1) if tok_ret else None,
               "tokens_checklist_mean": round(sum(tok_list) / len(tok_list), 1) if tok_list else None}
        if kind == "compaction" and rec_ret:
            cheaper = res["tokens_retrieval_mean"] < res["tokens_checklist_mean"]
            res["verdict"] = ("validated" if iv["ci95"][0] > -0.10 and cheaper else
                              "contradicted" if iv["ci95"][1] < 0 else "not reached")
        out[kind] = res
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
