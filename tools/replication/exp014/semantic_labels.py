"""Step 2a: L1, the behavioral labels, mapped onto the candidate index.

For every trigger moment, the candidates the agent consulted in the 20 tool calls strictly after
it, restricted to what was retrievable at that moment: created before the in-context boundary and
not consulted since it (semantic_trace.allowed). A consult maps to candidates by kind:
  ('kg_path', path)  the knowledge-web node at that path. A third of the paths arrive messy, cut
                     from a JSON-escaped command line, so they are cleaned first; a glob counts if it
                     names at most 3 nodes, a folder if it holds at most 5 (an experiment's protocol
                     and analysis); a path truncated with "..." does not resolve
  ('idea', n)        the idea node n
  ('task', n)        every task-tree event of task n
Transcript searches (`transcripts search`, `dev_drv`) name a breadcrumb, not a span, and are
counted but not mapped; the count is reported so the gap stays visible, as are the unresolved
paths by reason.

Relevance is judged per DOCUMENT, the thing the agent consulted: one knowledge-web artifact, one
task (a `task get` reads all its events at once, so labeling each event would reward a ranking for
returning the same task many times), one duty, one span. doc_of() names it; rankings collapse to
documents before they are scored.

Writes data/l1_labels.json: per moment, its kind, time, split, labeled candidate ids and documents.
"""
import fnmatch
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import semantic_trace as st

from kit_config import DATA, HOME, SNAPSHOT

CUT = re.compile(r"[\\`)\]>,;|'\"]")
EXT = re.compile(r"^(.*?\.(?:md|json|py|bash|txt))")


def doc_of(c, events):
    """The document a candidate belongs to: the unit of relevance."""
    if c["source"] == "kg":
        return "kg:" + c["node"]
    if c["source"] in ("task", "duty"):
        e = events[c["event"]]
        return f"{c['source']}:{e.get('task') or e.get('duty')}"
    return f"span:{c['id']}"


def collapse(rank, docs, k):
    """A ranking of candidates as a ranking of documents: each at its best position, top k."""
    out, seen = [], set()
    for c in rank:
        if docs[c] not in seen:
            seen.add(docs[c])
            out.append(docs[c])
            if len(out) == k:
                break
    return out


def load():
    events = [json.loads(l) for l in (DATA / "events.jsonl").read_text().splitlines()]
    cands = [json.loads(l) for l in (DATA / "candidates.jsonl").read_text().splitlines()]
    split = json.loads((DATA / "split_manifest.json").read_text())
    return events, cands, split


class Resolver:
    """Consult keys (semantic_trace.consult_keys) to candidate ids, with the reason when none."""

    def __init__(self, events, cands):
        nodes = json.loads(SNAPSHOT.read_bytes())["nodes"]
        self.rel, self.idea, self.task = {}, {}, defaultdict(list)
        for c in cands:
            if c["source"] == "kg":
                self.rel[nodes[c["node"]]["path"].split(f"{HOME}/", 1)[-1]] = c["id"]
                if c["node"].isdigit():
                    self.idea[c["node"]] = c["id"]
            elif c["source"] == "task" and events[c["event"]].get("task"):
                self.task[events[c["event"]]["task"]].append(c["id"])
        self.cache, self.why = {}, Counter()

    def path(self, raw):
        if raw not in self.cache:
            self.cache[raw] = self._path(raw)
        out, why = self.cache[raw]
        self.why[why] += 1            # per occurrence: what a reason costs in labels
        return out

    def _path(self, raw):
        p = CUT.split(raw.replace("\\n", " ").split()[0])[0]
        m = EXT.match(p)
        p = m.group(1) if m else p.rstrip("./:")
        if "..." in p:
            out, why = [], "truncated"
        elif "*" in p or "?" in p:
            out = [cid for r, cid in self.rel.items() if fnmatch.fnmatch(r, p)]
            out, why = (out, "glob") if 0 < len(out) <= 3 else ([], "glob too broad" if out else "glob, no node")
        elif not m:
            out = [cid for r, cid in self.rel.items() if r.startswith(p + "/")]
            out, why = (out, "folder") if 0 < len(out) <= 5 else ([], "folder too broad" if out else "folder, no node")
        else:
            out = [self.rel[p]] if p in self.rel else []
            why = "exact" if out else "no node (not in the web, or after the snapshot)"
        return out, why

    def __call__(self, key):
        kind, val = key
        if kind == "kg_path":
            return self.path(val)
        if kind == "idea":
            return [self.idea[val]] if val in self.idea else []
        return list(self.task.get(val, []))


def main():
    events, cands, split = load()
    resolve = Resolver(events, cands)
    out, unmapped, transcript_consults = label_moments(events, cands, split, st.moments(events), resolve)
    (DATA / "l1_labels.json").write_text(json.dumps({"moments": out}, indent=0) + "\n")
    labeled = Counter((m["kind"], m["split"]) for m in out if m["labels"])
    total = Counter((m["kind"], m["split"]) for m in out)
    print("moments by trigger and split (labeled of total):",
          {f"{k}/{s}": f"{labeled[(k, s)]}/{total[(k, s)]}" for k, s in sorted(total)})
    print("labeled documents by source:", dict(Counter(d.split(":")[0] for m in out for d in m["docs"])),
          "| per labeled moment, mean:", round(sum(len(m["docs"]) for m in out) / max(1, sum(bool(m["docs"]) for m in out)), 2))
    print("consult keys unmapped:", unmapped, "| path resolutions by reason:", dict(resolve.why),
          "| transcript-search consults (not mapped):", transcript_consults)


def label_moments(events, cands, split, moments, resolve):
    """L1 for the given moments (semantic_trace.moments order): labels, documents and split."""
    bounds = st.boundaries(events)
    t0 = events[0]["t"]
    consulted_since = {}          # candidate id -> time it was last consulted
    out, unmapped, transcript_consults = [], 0, 0
    mi = 0
    for i, e in enumerate(events):
        while mi < len(moments) and moments[mi]["i"] == i:
            m = moments[mi]
            start = st.context_start(m["t"], bounds, t0)
            in_ctx = {cid for cid, tc in consulted_since.items() if tc >= start}
            labels = set()
            for key in st.l1_targets(events, i):
                ids = resolve(key)
                unmapped += not ids
                labels |= {cid for cid in ids if cands[cid]["t"] < start and cid not in in_ctx}
            out.append({"kind": m["kind"], "i": i, "t": m["t"], "split": "held" if m["t"] >= split["cutoff_epoch"] else "dev",
                        "labels": sorted(labels), "docs": sorted({doc_of(cands[c], events) for c in labels}),
                        **({"n": m["n"]} if "n" in m else {})})
            mi += 1
        if e["kind"] == "tool":
            for key in st.consult_keys(e):
                for cid in resolve(key):
                    consulted_since[cid] = e["t"]
            transcript_consults += any("transcripts search" in c or "dev_drv" in c for c in e.get("consults") or [])
    return out, unmapped, transcript_consults


if __name__ == "__main__":
    main()
