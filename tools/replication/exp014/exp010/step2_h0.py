"""Step 2, H0: do the label sources measure one relation or several?

Sources (each a set of directed pairs over snapshot nodes):
  S1  learning cross-references (lib.s1_labels)
  S2  enhanced citations in reflections and checkpoints, resolved to a snapshot node by title
  S3  co-membership in a cluster of the learnings index (undirected, both directions)
  IL  idea links: an idea's related_ideas, and "pull idea N" in a task's text (added Oct 17)
Agreement is computed only where two sources label the same kind of pair; where their node sets
don't overlap, the overlap itself is the finding (different relations over different node types).

Writes data/step2_h0.json. Model-graded and Ira/CTB labels join later, on pooled results.
"""
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from lib import Corpus, HERE, s1_labels

CITE = re.compile(r'\[(OBSERVATION|LEARNING|REFLECTION|JOTEWR|CCP|CHECKPOINT|EXPERIMENT|REPORT|ROADMAP|MISSION|IDEA)\s+'
                  r'(\d{4}-\d{2}-\d{2})[^"\]]*"([^"]+)"', re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


KIND_TYPES = {"observation": {"observations"}, "learning": {"learnings"}, "reflection": {"reflections"},
              "jotewr": {"reflections"}, "ccp": {"checkpoints"}, "checkpoint": {"checkpoints"},
              "experiment": {"experiments"}, "report": {"reports"}, "roadmap": {"roadmaps"},
              "mission": {"roadmaps"}, "idea": {"ideas"}}


def s2_labels(corpus):
    """Resolve a citation by its date and kind first (the file name carries the date), then by
    token overlap between the cited title and the node's title and file name. A first version
    matched exact titles only and resolved 2 of 156; a citation's title is rarely the heading."""
    by_date = defaultdict(list)
    for k, v in corpus.nodes.items():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(v["path"]).name)
        if m:
            by_date[m.group(1)].append(k)
    rel, unresolved = defaultdict(set), 0
    for k, v in corpus.nodes.items():
        if v["type"] not in ("reflections", "checkpoints"):
            continue
        for kind, date, title in CITE.findall(v["text"]):
            want = set(norm(title).split())
            types = KIND_TYPES.get(kind.lower(), set())
            best, best_score = None, 0.0
            for h in by_date.get(date, []):
                if h == k or (types and corpus.nodes[h]["type"] not in types):
                    continue
                have = set(norm(corpus.nodes[h]["title"] + " " + Path(corpus.nodes[h]["path"]).stem).split())
                s = len(want & have) / len(want) if want else 0.0
                if s > best_score:
                    best, best_score = h, s
            if best and best_score >= 0.5:
                rel[k].add(best)
            else:
                unresolved += 1
    return dict(rel), unresolved


def s3_labels(corpus):
    from kit_config import HOME
    index = (HOME / "agent/private/learnings/INDEX.md").read_text()
    by_file = {Path(v["path"]).name: k for k, v in corpus.nodes.items() if v["type"] == "learnings"}
    clusters, current = defaultdict(set), None
    for line in index.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        for fn in re.findall(r"([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[A-Za-z0-9_\-]+?_learning\.md)", line):
            if current and fn in by_file:
                clusters[current].add(by_file[fn])
    rel = defaultdict(set)
    for members in clusters.values():
        for a, b in combinations(sorted(members), 2):
            rel[a].add(b)
            rel[b].add(a)
    return dict(rel), {c: len(m) for c, m in clusters.items()}


def il_labels(corpus):
    rel = defaultdict(set)
    for k, v in corpus.nodes.items():
        for t in v.get("related_ideas") or []:
            if t in corpus.nodes and t != k:
                rel[k].add(t)
        if v["type"] == "tasks":
            for n in re.findall(r"[Pp]ull idea (\d+)", v["text"]):
                if n in corpus.nodes:
                    rel[k].add(n)
    return dict(rel)


def pairs(rel):
    return {(a, b) for a, bs in rel.items() for b in bs}


def main():
    corpus = Corpus()
    s1 = s1_labels(corpus)
    s2, s2_unresolved = s2_labels(corpus)
    s3, clusters = s3_labels(corpus)
    il = il_labels(corpus)
    sources = {"S1": s1, "S2": s2, "S3": s3, "IL": il}
    P = {k: pairs(v) for k, v in sources.items()}
    types = {k: Counter(corpus.nodes[a]["type"] + ">" + corpus.nodes[b]["type"] for a, b in P[k]).most_common(4)
             for k in P}
    agreement = {}
    for x, y in combinations(P, 2):
        # Where can both say something? Pairs whose endpoints both appear in y's node set.
        y_nodes = {n for p in P[y] for n in p}
        comparable = {p for p in P[x] if p[0] in y_nodes and p[1] in y_nodes}
        agree = len(comparable & P[y])
        agreement[f"{x} vs {y}"] = {"x_pairs": len(P[x]), "comparable": len(comparable), "agree": agree,
                                    "agreement": round(agree / len(comparable), 3) if comparable else None}
    out = {"volumes": {k: {"queries": len(v), "pairs": len(P[k])} for k, v in sources.items()},
           "s2_unresolved_citations": s2_unresolved, "s3_cluster_sizes": clusters,
           "pair_types": types, "agreement": agreement}
    (HERE / "data/step2_h0.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
