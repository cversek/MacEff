"""Step 1: seal the held-out split, then prove the metrics can fail.

1. Split S1's queries 80/20 by a deterministic hash and record the held-out ids' hash BEFORE any
   arm runs (the seal Step 2 relies on). Only development queries are used until Step 6.
2. Score the random floor, the baseline, H1 (IDF match), and the destroyed versions of the
   baseline and H1 (same returned set, shuffled). Every ranking metric must collapse to the floor
   when the ranking is destroyed; a metric that doesn't move isn't measuring ranking.

Writes data/labels_manifest.json and data/step1_control.json.
"""
import hashlib
import json
import time

from lib import Corpus, HERE, arm_baseline, arm_idf_match, arm_random, s1_labels, score, shuffled, stable_key

SPLIT_SEED = "exp010-s1-heldout"


def split(queries):
    held = sorted(q for q in queries if int(stable_key(SPLIT_SEED, q)[:8], 16) / 0xFFFFFFFF < 0.20)
    dev = sorted(q for q in queries if q not in set(held))
    return dev, held


def main():
    t0 = time.time()
    corpus = Corpus()
    labels = s1_labels(corpus)
    dev, held = split(sorted(labels))
    manifest = {"source": "S1 learning cross-references", "queries": len(labels),
                "pairs": sum(len(v) for v in labels.values()), "dev_queries": len(dev),
                "heldout_queries": len(held), "split_seed": SPLIT_SEED,
                "heldout_ids_sha256": hashlib.sha256("\n".join(held).encode()).hexdigest(),
                "snapshot_sha256": hashlib.sha256((HERE / "data/corpus_snapshot.json").read_bytes()).hexdigest()}
    (HERE / "data/labels_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    arms = {"random": arm_random, "baseline": arm_baseline, "H1_idf_match": arm_idf_match,
            "baseline_destroyed": shuffled(arm_baseline), "H1_destroyed": shuffled(arm_idf_match)}
    results = {name: score(arm, dev, labels, corpus) for name, arm in arms.items()}
    out = {"split": "dev", "manifest": manifest, "results": results, "seconds": round(time.time() - t0, 1)}
    (HERE / "data/step1_control.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
