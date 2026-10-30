#!/usr/bin/env python3
"""Host-side summaries for experiment 016's harness: read probe JSON lines on stdin."""
import collections
import json
import sys


def r37():
    rows = [json.loads(line) for line in sys.stdin if line.strip()]
    planted = [r for r in rows if "planted" in r["entry"]]
    genuine = [r for r in rows if "planted" not in r["entry"]]
    for r in planted:
        print(json.dumps(r))
    print(json.dumps({"kind": "r37_genuine", "n": len(genuine), "accepted": sum(r["accept"] for r in genuine)}))


def planted():
    s = json.loads(sys.stdin.read())
    print(json.dumps({"kind": "store_planted", "n_total": s["n"],
                      "items": [i for i in s["items"] if "planted" in (i["id"] or "")]}))


def e4():
    s = json.loads(sys.stdin.read())
    tags = collections.Counter(i["subject"].split()[0] for i in s["items"] if i["subject"])
    ids = collections.Counter(i["id"] for i in s["items"])
    print(json.dumps({"kind": "e4_store", "by_tag": {k: v for k, v in tags.items() if k.startswith("e4")},
                      "dup_ids": {k: v for k, v in ids.items() if v > 1}}))


{"r37": r37, "planted": planted, "e4": e4}[sys.argv[1]]()
