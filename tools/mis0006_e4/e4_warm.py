"""Embed the three E4 indexes once, into the owner-only cache. Prints sizes and seconds only."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from e4_lib import Index
eps = json.load(open(sys.argv[1])); cache = sys.argv[2]
n = len(eps)
units, owners = [], []
for i, e in enumerate(eps):
    for t in [e["operator"]] + list(e.get("agent_turns") or []):
        if t.strip():
            units.append(t); owners.append(i)
for name, us, ow in (("op", [e["operator_unpasted"] for e in eps], list(range(n))),
                     ("both", [e["operator"] + "\n\n" + e["agent"] for e in eps], list(range(n))),
                     ("turns", units, owners)):
    t = time.time(); ix = Index(name, us, ow, cache); v = ix.vectors()
    print(name, len(us), "units", v.shape, f"{time.time() - t:.0f}s", flush=True)
