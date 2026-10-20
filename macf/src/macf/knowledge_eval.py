"""Score the knowledge query against relevance the agent's past selves wrote.

An instrument judged only by its author's reading is judged by the party least able to see its
faults. ``knowledge eval`` asks someone else: the agent's own earlier artifacts, which name what
they bear on in three ways the query never reads.

- **xref**: a learning's Cross-References section names the learnings it bears on.
- **citations**: an enhanced citation in a reflection or checkpoint names the artifact it
  continues, resolved by its date and title.
- **same_subject**: two learnings filed under one cluster of the learnings index.

Each artifact with labels is a query. A ranker sees the query artifact, never its labels, and
returns the web's other nodes in its order; the labels say which of them were relevant.

**The seal.** A fifth of the queries, chosen by a stable hash, are held out. Development runs
use the rest as often as they like. A seed is sealed on its first use, and each held run is
recorded, both as events in the agent's event log, so the count of held runs before this one is
a fold over the log like every other count in MacEff, and a reset shows as a gap rather than a
quiet zero.
A configuration tuned on the split that judges it measures the tuning, so the count is the
evidence of how far the held figures can be trusted.

**The leak audit.** A ranker that reads text can be handed the answer: a learning's
Cross-References section names its targets. Before such a ranker is scored, the audit checks
by content whether each query's input names its target, and refuses to score above a small
share, naming the pairs. A target with no name long enough to search for can't be audited, so
it is counted apart and left out of the share, never counted as clean.

The method, the figures it must reproduce and the defects it guards against are Experiment
010's; see the corpus_integrity policy, section 6.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_SEED = "knowledge-eval-heldout"
HELD_SHARE = 0.20
BOOTSTRAP = 2000
BOOT_SEED = "knowledge-eval-boot"
LEAK_LIMIT = 0.05
LABEL_SOURCES = ("xref", "citations", "same_subject")
EVENT_SEALED = "knowledge_eval_sealed"
EVENT_HELD_RUN = "knowledge_eval_held_run"

_LEARNING_FILE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[A-Za-z0-9_\-]+?_learning\.md)")
_CITE = re.compile(r'\[(OBSERVATION|LEARNING|REFLECTION|JOTEWR|CCP|CHECKPOINT|EXPERIMENT|REPORT|ROADMAP|MISSION|IDEA)\s+'
                   r'(\d{4}-\d{2}-\d{2})[^"\]]*"([^"]+)"', re.I)
_KIND_TYPES = {"observation": {"observations"}, "learning": {"learnings"}, "reflection": {"reflections"},
               "jotewr": {"reflections"}, "ccp": {"checkpoints"}, "checkpoint": {"checkpoints"},
               "experiment": {"experiments"}, "report": {"reports"}, "roadmap": {"roadmaps"},
               "mission": {"roadmaps"}, "idea": {"ideas"}}


class EvalRefused(Exception):
    """The eval will not score this run, and says why."""


def stable_key(seed: str, nid: str) -> str:
    """A deterministic tie-break, so two runs on one snapshot give identical results."""
    return hashlib.sha256(f"{seed}:{nid}".encode()).hexdigest()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ---- the snapshot ------------------------------------------------------------------------------

def _node_id(ca_type: str, type_root: Path, path: Path) -> str:
    """The builder's node id scheme (knowledge_web.build_knowledge_web)."""
    stem = f"{path.parent.name}/{path.stem}" if path.parent != type_root else path.stem
    return f"{ca_type}:{stem}"


def build_snapshot(agent_home: Optional[Path] = None, exclude: Sequence[str] = ()) -> dict:
    """Every file the web examines, linked or not, with its concepts and text as read now.

    Paths containing any of *exclude* are left out, so an experiment can keep its own artifacts
    out of the corpus that measures it.
    """
    from .knowledge_web import build_knowledge_web, iter_web_files
    from .utils.paths import find_agent_home

    home = agent_home or find_agent_home()
    kg = build_knowledge_web()
    concepts_of: Dict[str, List[str]] = {}
    for concept, members in kg["wiki_index"].items():
        for nid in members:
            concepts_of.setdefault(str(nid), []).append(concept)
    nodes: Dict[str, dict] = {}
    for nid, d in kg["ideas"].items():
        text = "\n\n".join(str(d.get(k) or "") for k in ("title", "description", "reasoning", "hypothesis"))
        nodes[str(nid)] = {"type": "ideas", "class": "conceptual_authority", "title": d.get("title", ""),
                           "path": f"ideas:{nid}", "concepts": sorted(concepts_of.get(str(nid), [])), "text": text}
    for ca_type, type_root, path in iter_web_files(home):
        if any(x in str(path) for x in exclude):
            continue
        try:
            raw = path.read_text(errors="replace")
        except OSError:
            continue
        if ca_type in ("tasks", "duties"):
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if ca_type == "tasks":
                nid, text = f"tasks:#{rec.get('id')}", f"{rec.get('subject', '')}\n\n{rec.get('description') or ''}"
            else:
                nid = f"duties:{rec.get('id', path.stem)}"
                text = "\n\n".join(str(rec.get(k) or "") for k in ("title", "body", "why"))
        else:
            nid, text = _node_id(ca_type, type_root, path), raw
        if nid in nodes and nodes[nid]["concepts"] and not concepts_of.get(nid):
            continue    # a duplicate id (an archived copy) never replaces the linked record
        info = kg["ca_nodes"].get(nid, {})
        nodes[nid] = {"type": ca_type, "class": info.get("node_class", ""), "title": info.get("title", path.stem[:50]),
                      "path": str(path), "concepts": sorted(concepts_of.get(nid, [])), "text": text}
    web_nodes = set(map(str, kg["ideas"])) | set(kg["ca_nodes"])
    for nid, n in nodes.items():
        n["sha256"] = hashlib.sha256(n["text"].encode()).hexdigest()
        n["linked"] = bool(n["concepts"])
        n["in_web"] = nid in web_nodes
    index = home / "agent" / "private" / "learnings" / "INDEX.md"
    return {"taken_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "nodes": nodes,
            "learnings_index": index.read_text(errors="replace") if index.is_file() else None}


def snapshot_bytes(snap: dict) -> bytes:
    return json.dumps(snap, sort_keys=True, ensure_ascii=False).encode()


def save_snapshot(snap: dict, path: Path) -> str:
    """Write *snap* owner-only (it holds the agent's private text) and return its digest. The
    file is created 0600, and an existing one is narrowed before a byte is written, so the text
    is never readable by others, even briefly."""
    blob = snapshot_bytes(snap)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(fd, 0o600)
        f.write(blob)
    return hashlib.sha256(blob).hexdigest()


def load_snapshot(path: Path) -> Tuple[dict, str]:
    blob = Path(path).read_bytes()
    return json.loads(blob), hashlib.sha256(blob).hexdigest()


# ---- the corpus and its labels -----------------------------------------------------------------

class Corpus:
    """A snapshot's nodes, the web's members per concept, and each concept's IDF over the web."""

    def __init__(self, snap: dict, digest: str):
        self.snap, self.digest = snap, digest
        self.nodes: Dict[str, dict] = snap["nodes"]
        self.web = sorted(k for k, v in self.nodes.items() if v["in_web"])
        self.web_set = set(self.web)
        self.members: Dict[str, Set[str]] = defaultdict(set)
        for k, v in self.nodes.items():
            for c in v["concepts"]:
                self.members[c].add(k)
        n = len(self.web)
        self.idf = {c: math.log(n / len(m)) for c, m in self.members.items()}
        self._kg = None

    def kg(self) -> dict:
        """The shipping builder's web, rebuilt from the snapshot, so ``today`` sees only it."""
        if self._kg is None:
            wiki = {c: {int(x) if x.isdigit() else x for x in m} for c, m in self.members.items()}
            edges: Dict[object, set] = defaultdict(set)
            for m in wiki.values():
                for a in m:
                    edges[a] |= m
            for a in edges:
                edges[a].discard(a)
            ideas = {int(k): {"title": v["title"]} for k, v in self.nodes.items() if v["type"] == "ideas" and v["in_web"]}
            ca = {k: {"type": v["type"], "title": v["title"], "path": v["path"], "node_class": v["class"]}
                  for k, v in self.nodes.items() if v["type"] != "ideas" and v["in_web"]}
            self._kg = {"ideas": ideas, "ca_nodes": ca, "edges": dict(edges), "wiki_index": wiki, "stats": {}}
        return self._kg


def _cross_references(text: str) -> str:
    m = re.search(r"^## Cross-References\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def xref_labels(corpus: Corpus) -> Tuple[Dict[str, Set[str]], int]:
    by_file = {Path(v["path"]).name: k for k, v in corpus.nodes.items() if v["type"] == "learnings"}
    rel: Dict[str, Set[str]] = defaultdict(set)
    unresolved = 0
    for k, v in corpus.nodes.items():
        if v["type"] != "learnings":
            continue
        for fn in _LEARNING_FILE.findall(_cross_references(v["text"])):
            t = by_file.get(fn)
            if t and t != k:
                rel[k].add(t)
            elif not t:
                unresolved += 1
    return dict(rel), unresolved


def citation_labels(corpus: Corpus) -> Tuple[Dict[str, Set[str]], int]:
    """Resolve each citation by its date and kind, then by title overlap of at least half."""
    by_date: Dict[str, List[str]] = defaultdict(list)
    for k, v in corpus.nodes.items():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(v["path"]).name)
        if m:
            by_date[m.group(1)].append(k)
    rel: Dict[str, Set[str]] = defaultdict(set)
    unresolved = 0
    for k, v in corpus.nodes.items():
        if v["type"] not in ("reflections", "checkpoints"):
            continue
        for kind, date, title in _CITE.findall(v["text"]):
            want = set(_norm(title).split())
            types = _KIND_TYPES.get(kind.lower(), set())
            best, best_score = None, 0.0
            for h in by_date.get(date, []):
                if h == k or (types and corpus.nodes[h]["type"] not in types):
                    continue
                have = set(_norm(corpus.nodes[h]["title"] + " " + Path(corpus.nodes[h]["path"]).stem).split())
                s = len(want & have) / len(want) if want else 0.0
                if s > best_score:
                    best, best_score = h, s
            if best and best_score >= 0.5:
                rel[k].add(best)
            else:
                unresolved += 1
    return dict(rel), unresolved


def same_subject_labels(corpus: Corpus, index_text: Optional[str]) -> Tuple[Dict[str, Set[str]], int]:
    if not index_text:
        return {}, 0
    by_file = {Path(v["path"]).name: k for k, v in corpus.nodes.items() if v["type"] == "learnings"}
    clusters: Dict[str, Set[str]] = defaultdict(set)
    current, unresolved = None, 0
    for line in index_text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        for fn in _LEARNING_FILE.findall(line):
            if current and fn in by_file:
                clusters[current].add(by_file[fn])
            elif current:
                unresolved += 1
    rel: Dict[str, Set[str]] = defaultdict(set)
    for members in clusters.values():
        for a, b in combinations(sorted(members), 2):
            rel[a].add(b)
            rel[b].add(a)
    return dict(rel), unresolved


def labels_for(corpus: Corpus, source: str, index_text: Optional[str] = None) -> Tuple[Dict[str, Set[str]], int]:
    if source == "xref":
        return xref_labels(corpus)
    if source == "citations":
        return citation_labels(corpus)
    if source == "same_subject":
        return same_subject_labels(corpus, index_text)
    raise EvalRefused(f"unknown label source {source!r}; the sources are {', '.join(LABEL_SOURCES)}")


def split(queries: Iterable[str], seed: str) -> Tuple[List[str], List[str]]:
    """Dev and held queries, by a stable hash of each query's id, so membership never depends
    on what else is in the corpus."""
    qs = sorted(queries)
    held = [q for q in qs if int(stable_key(seed, q)[:8], 16) / 0xFFFFFFFF < HELD_SHARE]
    held_set = set(held)
    return [q for q in qs if q not in held_set], held


def ids_digest(ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


# ---- rankers -----------------------------------------------------------------------------------

@dataclass
class Ranker:
    """A configuration under test: *rank* orders the web for a query. *reads* returns the text
    the ranker sees for a query, or is None for a ranker that reads only concepts; the leak
    audit runs on every ranker that reads text."""
    name: str
    rank: Callable[[str, Corpus], List[str]]
    help: str
    reads: Optional[Callable[[str, Corpus], str]] = None


def _random(q: str, corpus: Corpus) -> List[str]:
    return sorted((x for x in corpus.web if x != q), key=lambda x: stable_key(f"random:{q}", x))


def _today(q: str, corpus: Corpus) -> List[str]:
    """What an agent gets today: the shipping query on each of the query's concepts, in turn,
    matches then neighbours, without repeats."""
    from .knowledge_web import query_knowledge_web
    kg = corpus.kg()
    seen, out = {q}, []
    for c in corpus.nodes[q]["concepts"]:
        r = query_knowledge_web(c, kg)
        for n in list(r["nodes"]) + list(r["neighbors"]):
            nid = str(n["id"]) if isinstance(n, dict) else str(n)
            if nid not in seen and nid in corpus.nodes:
                seen.add(nid)
                out.append(nid)
    return out


def _idf(q: str, corpus: Corpus) -> List[str]:
    scores: Counter = Counter()
    for c in set(corpus.nodes[q]["concepts"]):
        for x in corpus.members.get(c, ()):
            if x != q:
                scores[x] += corpus.idf[c]
    return sorted(scores, key=lambda x: (-scores[x], stable_key("idf", x)))


RANKERS: Dict[str, Ranker] = {r.name: r for r in (
    Ranker("random", _random, "the floor: every web node in a seeded random order"),
    Ranker("today", _today, "the shipping knowledge query, run on each of the query's concepts"),
    Ranker("idf", _idf, "reference: nodes sharing a concept, by the summed IDF of the shared concepts"),
)}


# ---- the leak audit ----------------------------------------------------------------------------

def _names(node: dict) -> List[str]:
    """The strings that identify a node to a reader: its file stem and its title, normalized.
    Short ones are skipped, since a common word names nothing."""
    out = []
    for s in (Path(node["path"]).stem, node.get("title") or ""):
        n = _norm(s)
        if len(n) >= 12:
            out.append(n)
    return out


@dataclass
class LeakAudit:
    """What the audit found: the leaking pairs, the pairs it could check, and the pairs whose
    target has no name long enough to search for, which are left out of the share."""
    leaks: List[Tuple[str, str]] = field(default_factory=list)
    audited: int = 0
    unauditable: int = 0

    @property
    def share(self) -> float:
        return len(self.leaks) / self.audited if self.audited else 0.0


def leak_audit(ranker: Ranker, queries: Sequence[str], labels: Dict[str, Set[str]],
               corpus: Corpus) -> LeakAudit:
    """Which (query, target) pairs have a ranker input that names the target."""
    audit = LeakAudit()
    if ranker.reads is None:
        return audit
    for q in queries:
        seen = _norm(ranker.reads(q, corpus))
        for t in sorted(labels[q]):
            names = _names(corpus.nodes[t])
            if not names:
                audit.unauditable += 1
                continue
            audit.audited += 1
            if any(n in seen for n in names):
                audit.leaks.append((q, t))
    return audit


# ---- metrics and intervals ---------------------------------------------------------------------

def mrr(ranked: Sequence[str], relevant: Set[str]) -> float:
    for i, x in enumerate(ranked, 1):
        if x in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at(ranked: Sequence[str], relevant: Set[str], k: int = 10) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, x in enumerate(ranked[:k], 1) if x in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def recall_at(ranked: Sequence[str], relevant: Set[str], k: int = 50) -> float:
    return sum(1 for x in ranked[:k] if x in relevant) / len(relevant) if relevant else 0.0


METRICS = ("MRR", "nDCG@10", "R@50", "set_recall", "returned_share")


def per_query(ranked: Sequence[str], relevant: Set[str], web_size: int) -> Dict[str, float]:
    return {"MRR": mrr(ranked, relevant), "nDCG@10": ndcg_at(ranked, relevant), "R@50": recall_at(ranked, relevant),
            "set_recall": len(set(ranked) & relevant) / len(relevant) if relevant else 0.0,
            "returned_share": len(ranked) / web_size if web_size else 0.0}


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Linear interpolation between closest ranks, as numpy's default."""
    if not sorted_vals:
        return 0.0
    pos = (len(sorted_vals) - 1) * p
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def resamples(n: int, source: str, boot: int = BOOTSTRAP) -> List[List[int]]:
    """The same resamples for every ranker on one source, so comparisons are paired."""
    rng = random.Random(stable_key(BOOT_SEED, source))
    return [[rng.randrange(n) for _ in range(n)] for _ in range(boot)] if n else []


def interval(values: List[float], idx: List[List[int]]) -> Dict[str, object]:
    mean = sum(values) / len(values) if values else 0.0
    boots = sorted(sum(values[i] for i in draw) / len(draw) for draw in idx) if values else []
    return {"mean": round(mean, 4), "ci95": [round(_percentile(boots, 0.025), 4), round(_percentile(boots, 0.975), 4)]}


# ---- the seal, as events ----------------------------------------------------------------------

def _default_events() -> Iterable[dict]:
    from .agent_events_log import read_events
    return read_events(reverse=False, scope="all", only=(EVENT_SEALED, EVENT_HELD_RUN))


def _default_append(event: str, data: dict) -> None:
    from .agent_events_log import append_event
    if not append_event(event, data):
        raise EvalRefused(f"could not record {event} in the event log, so this run would not be counted")


def seal_state(events: Iterable[dict], seed: str) -> Tuple[Optional[dict], int]:
    """The seal of *seed* (its event, or None if it was never used) and how many held runs it has
    had: a fold over the log."""
    sealed, runs = None, 0
    for e in events:
        data = e.get("data") or {}
        if data.get("seed") != seed:
            continue
        if e.get("event") == EVENT_SEALED and sealed is None:
            sealed = e
        elif e.get("event") == EVENT_HELD_RUN:
            runs += 1
    return sealed, runs


# ---- the run -----------------------------------------------------------------------------------

def evaluate(corpus: Corpus, rankers: Sequence[str], sources: Sequence[str] = LABEL_SOURCES,
             which: str = "dev", seed: str = DEFAULT_SEED,
             compare: Optional[Tuple[str, str]] = None, boot: int = BOOTSTRAP,
             extra_rankers: Optional[Dict[str, Ranker]] = None,
             append: Optional[Callable[[str, dict], None]] = None,
             events: Optional[Callable[[], Iterable[dict]]] = None) -> dict:
    """Score *rankers* on *sources* over the *which* split, and return the chart and results.

    Raises EvalRefused for an unknown ranker or source, and for a ranker whose input names its
    targets in more than LEAK_LIMIT of the pairs it can audit. The seal and each held run are
    written through *append* and counted from *events*, the agent's event log by default.
    """
    append, events = append or _default_append, events or _default_events
    if which not in ("dev", "held"):
        raise EvalRefused(f"--split is dev or held, not {which!r}")
    known = {**RANKERS, **(extra_rankers or {})}
    for name in rankers:
        if name not in known:
            raise EvalRefused(f"unknown ranker {name!r}; the rankers are {', '.join(sorted(known))}")
    if compare:
        for name in compare:
            if name not in rankers:
                raise EvalRefused(f"--compare names {name!r}, which is not among the rankers scored")
    index_text = corpus.snap.get("learnings_index")
    chart = {"snapshot_sha256": corpus.digest, "taken_at": corpus.snap.get("taken_at"),
             "nodes": len(corpus.nodes), "web": len(corpus.web), "split": which, "split_seed": seed,
             "sources": {}}
    labelled, split_ids = {}, {}
    for s in sources:
        rel, unresolved = labels_for(corpus, s, index_text)
        dev, held = split(rel, seed)
        labelled[s], split_ids[s] = rel, (dev, held)
        chart["sources"][s] = {"queries": len(rel), "pairs": sum(len(v) for v in rel.values()),
                               "unresolved": unresolved, "dev": len(dev), "held": len(held)}
        if s == "same_subject" and not index_text:
            chart["sources"][s]["note"] = "no learnings index in this snapshot"
    sealed, held_runs = seal_state(events(), seed)
    if sealed is None:                       # sealed on first use, before anything is scored
        append(EVENT_SEALED, {"seed": seed,
                              "held_ids_sha256": {s: ids_digest(split_ids[s][1]) for s in sources},
                              "held_counts": {s: len(split_ids[s][1]) for s in sources}})
        sealed, held_runs = seal_state(events(), seed)
        if sealed is None:
            raise EvalRefused("the seal was written but can't be read back from the event log")
    recorded = sealed["data"]["held_ids_sha256"]
    chart["seal"] = {"sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(sealed.get("timestamp", 0))),
                     "held_runs_before": held_runs,
                     "held_set_changed_since_sealing": sorted(s for s in sources if s in recorded
                                                              and recorded[s] != ids_digest(split_ids[s][1]))}
    # Audit every text-reading ranker before anything is scored.
    for name in rankers:
        r = known[name]
        for s in sources:
            qs = split_ids[s][0 if which == "dev" else 1]
            audit = leak_audit(r, qs, labelled[s], corpus)
            if audit.unauditable:
                chart.setdefault("unauditable", {}).setdefault(name, {})[s] = audit.unauditable
            if audit.share > LEAK_LIMIT:
                shown = "; ".join(f"{q} -> {t}" for q, t in audit.leaks[:5])
                raise EvalRefused(f"ranker {name!r} reads text that names its target in {len(audit.leaks)} of the "
                                  f"{audit.audited} {s} pairs it could audit ({audit.share:.0%}, limit "
                                  f"{LEAK_LIMIT:.0%}; {audit.unauditable} more have no name to search for), "
                                  f"e.g. {shown}. Remove the field that names the answer from what it reads.")
    if which == "held":
        append(EVENT_HELD_RUN, {"seed": seed, "snapshot": corpus.digest, "rankers": list(rankers),
                                "sources": list(sources)})
        chart["seal"]["this_held_run"] = held_runs + 1
    results: Dict[str, Dict[str, dict]] = {}
    rows: Dict[str, Dict[str, List[Dict[str, float]]]] = {}
    for s in sources:
        qs = split_ids[s][0 if which == "dev" else 1]
        idx = resamples(len(qs), s, boot)
        for name in rankers:
            per = []
            for q in qs:
                ranked = [x for x in known[name].rank(q, corpus) if x in corpus.web_set and x != q]
                per.append(per_query(ranked, labelled[s][q], len(corpus.web)))
            rows.setdefault(s, {})[name] = per
            results.setdefault(s, {})[name] = {m: interval([p[m] for p in per], idx) for m in METRICS}
    out = {"chart": chart, "results": results}
    if compare:
        a, b = compare
        out["comparison"] = {}
        for s in sources:
            idx = resamples(len(rows[s][a]), s, boot)
            out["comparison"][s] = {m: interval([pb[m] - pa[m] for pa, pb in zip(rows[s][a], rows[s][b], strict=True)], idx)
                                    for m in ("MRR", "nDCG@10", "R@50")}
        out["comparison_of"] = f"{b} minus {a}"
    return out


def format_report(out: dict) -> str:
    c = out["chart"]
    lines = [f"📏 knowledge eval, {c['split']} split",
             f"   snapshot {c['snapshot_sha256'][:12]} taken {c['taken_at']}: {c['nodes']} nodes, {c['web']} in the web",
             (f"   seal {c['split_seed']!r}, sealed {c['seal']['sealed_at']}, "
              f"{c['seal']['held_runs_before']} held run(s) before this one")]
    if c["seal"].get("this_held_run"):
        lines.append(f"   ⚠️  this is held run {c['seal']['this_held_run']}: its figures are spent once read")
    if c["seal"]["held_set_changed_since_sealing"]:
        lines.append(f"   note: the held set of {', '.join(c['seal']['held_set_changed_since_sealing'])} "
                     f"has changed since sealing, as the corpus grew")
    for name, by in c.get("unauditable", {}).items():
        lines.append(f"   leak audit, {name}: " + ", ".join(f"{n} {s} pairs unauditable (no name to search for)"
                                                      for s, n in by.items()))
    for s, info in c["sources"].items():
        extra = f", {info['note']}" if info.get("note") else ""
        lines.append(f"   {s}: {info['queries']} queries, {info['pairs']} pairs, {info['unresolved']} unresolved, "
                     f"{info['dev']} dev, {info['held']} held{extra}")
    for s, by in out["results"].items():
        lines.append(f"\n{s}")
        lines.append(f"   {'ranker':<10} {'MRR':>22} {'nDCG@10':>22} {'R@50':>22} {'returned':>9}")
        for name, m in by.items():
            def cell(k, m=m):
                return f"{m[k]['mean']:.3f} [{m[k]['ci95'][0]:.3f},{m[k]['ci95'][1]:.3f}]"
            lines.append(f"   {name:<10} {cell('MRR'):>22} {cell('nDCG@10'):>22} {cell('R@50'):>22} "
                         f"{m['returned_share']['mean']:>9.3f}")
    if "comparison" in out:
        lines.append(f"\npaired, {out['comparison_of']}")
        for s, m in out["comparison"].items():
            lines.append("   " + s + ": " + "  ".join(
                f"{k} {v['mean']:+.3f} [{v['ci95'][0]:+.3f},{v['ci95'][1]:+.3f}]" for k, v in m.items()))
    return "\n".join(lines)
