"""Step 0b: the historical index (the trace tooling's prototype), embeddings, and the sealed split.

Candidates, the retrieval domain, each with the time it came into existence:
  span   a transcript span: one operator-issued turn (typed, Telegram, or a skill invoked by slash
         command) with the agent's reply and tool calls until the next such turn, anchored by its
         cycle (compactions before it) and time
  task   a task-tree event (creation, start, note, completion)
  duty   a duty event
  kg     a knowledge-web artifact or policy from EXP 010's snapshot, as EXP 010's best arm reads
         it (the clean summary with concepts in the keyword slot); its time comes from its file
         name, an idea's provenance, or 0 for a policy (they predate the record)
Every event and candidate is embedded with all-MiniLM-L6-v2, normalized, stored as float16.
The future split: the last 20% of operator and Telegram prompts by time, sealed by a hash of
their event ids; every moment at or after the cutoff is held out until Step 7.

Usage: python3 semantic_index.py                 (build)
       python3 semantic_index.py --candidates    (rebuild candidates and their embeddings only)
       python3 semantic_index.py --search "text" [--as-of EPOCH] [--k 8]   (interpretable search)
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

os.environ.setdefault("HF_HUB_OFFLINE", "1")
from kit_config import DATA, HOME, SNAPSHOT

sys.path.insert(0, str(Path(__file__).resolve().parent / "exp010"))
KNOWLEDGE = {"learnings", "reflections", "checkpoints", "observations", "experiments", "reports", "roadmaps", "ideas", "policies"}
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:_(\d{2})(\d{2})(\d{2}))?")
WORD = re.compile(r"[a-z][a-z0-9_\-]{2,}")


def load_events():
    return [json.loads(line) for line in (DATA / "events.jsonl").read_text().splitlines()]


def created_at(node_id, v):
    if v["type"] == "policies":
        return 0.0
    if v["type"] == "ideas":
        p = HOME / "agent/public/ideas"
        for f in p.glob(f"{int(node_id):03d}_*.json") if node_id.isdigit() else []:
            c = (json.loads(f.read_text()).get("provenance") or {}).get("created")
            if c:
                return datetime.fromisoformat(c).timestamp()
        return 0.0
    m = DATE.search(Path(v["path"]).name) or DATE.search(v["path"])
    if not m:
        return 0.0
    y, mo, d, hh, mm, ss = (int(x) if x else 12 for x in m.groups())
    return datetime(y, mo, d, hh if m.group(4) else 12, mm if m.group(4) else 0, ss if m.group(4) else 0).timestamp()


def build_candidates(events):
    cands, cycle, span = [], 0, None
    for e in events:
        if e["kind"] == "boundary":
            cycle += 1
            if span:              # a span never crosses a boundary: half of it would be in context
                cands.append(span)
            span = None
            continue
        if e["scope"] == "conv" and e["kind"] != "summary":
            opens = e["kind"] == "prompt" and e["origin"] in ("operator", "telegram", "slash")
            if opens or span is None:      # every transcript event belongs to some span
                if span:
                    cands.append(span)
                # "cycle" counts boundaries in this transcript (the judges saw it); "bc" is the
                # opening prompt's own breadcrumb, which names the agent's cycle and prompt exactly
                span = {"source": "span", "t": e["t"], "cycle": cycle, "start_event": e["id"], "parts": [], "tools": []}
                if e.get("bc"):
                    span["bc"] = e["bc"]
            if e["kind"] == "prompt":      # a machine's prompt is shown by origin: it says why the agent acted
                span["parts"].append(e["text"][:400] if opens else f"[{e['origin']}] {e['text'][:150]}")
            elif e["kind"] == "agent":
                span["parts"].append(e["text"][:300])
            elif e["kind"] == "tool":
                span["tools"].append(e["text"][:80])
        elif e["scope"] in ("task", "duty"):
            cands.append({"source": e["scope"], "t": e["t"], "cycle": cycle, "event": e["id"], "text": e["text"][:1200]})
    if span:
        cands.append(span)
    for c in cands:
        if c["source"] == "span":
            c["text"] = (" | ".join(c.pop("parts"))[:1100] + " || " + "; ".join(c.pop("tools"))[:300]).strip()
    from lib import Corpus
    from kw_extractor import KWExtractor
    corpus = Corpus(SNAPSHOT)
    ex = KWExtractor(corpus, with_concepts=True, tier="clean")
    for nid, v in corpus.nodes.items():
        if v["type"] in KNOWLEDGE and v["in_web"] and ex.should_index(nid):
            cands.append({"source": "kg", "t": created_at(nid, v), "cycle": None, "node": nid, "kg_type": v["type"],
                          "text": ex.generate_embedding_text(ex.extract_document(nid))[:1500]})
    for i, c in enumerate(cands):
        c["id"] = i
    return cands


def embed(texts):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return m.encode(texts, batch_size=256, normalize_embeddings=True, show_progress_bar=False).astype(np.float16)


def build(candidates_only=False):
    events = load_events()
    cands = build_candidates(events)
    (DATA / "candidates.jsonl").write_text("\n".join(json.dumps(c, sort_keys=True, ensure_ascii=False) for c in cands) + "\n")
    if not candidates_only:        # the event embeddings depend on events.jsonl alone
        np.save(DATA / "emb_events.npy", embed([e["text"] or " " for e in events]))
    np.save(DATA / "emb_candidates.npy", embed([c["text"] or " " for c in cands]))
    prompts = sorted((e for e in events if e["kind"] == "prompt" and e["origin"] in ("operator", "telegram")), key=lambda e: e["t"])
    if len(prompts) < 10:
        raise SystemExit(f"only {len(prompts)} operator or Telegram prompts were found in the transcripts; "
                         "check the --transcripts paths and --end")
    cut = prompts[int(len(prompts) * 0.8)]["t"]
    held = [e["id"] for e in prompts if e["t"] >= cut]
    split = {"cutoff_epoch": cut, "cutoff": datetime.fromtimestamp(cut).isoformat(), "prompts": len(prompts),
             "held_prompts": len(held), "held_ids_sha256": hashlib.sha256("\n".join(map(str, held)).encode()).hexdigest()}
    (DATA / "split_manifest.json").write_text(json.dumps(split, indent=2) + "\n")
    from collections import Counter
    print(json.dumps({"candidates": len(cands), "by_source": dict(Counter(c["source"] for c in cands)), "split": split}, indent=1))


def search(text, as_of=None, k=8):
    """Interpretable search over the record: each hit says where it is from, when, and why it matched."""
    cands = [json.loads(l) for l in (DATA / "candidates.jsonl").read_text().splitlines()]
    C = np.load(DATA / "emb_candidates.npy").astype(np.float32)
    q = embed([text])[0].astype(np.float32)
    s = C @ q
    qw = set(WORD.findall(text.lower()))
    order = [i for i in np.argsort(-s) if as_of is None or cands[i]["t"] < as_of][:k]
    for i in order:
        c = cands[i]
        shared = sorted(qw & set(WORD.findall(c["text"].lower())))[:8]
        when = datetime.fromtimestamp(c["t"]).strftime("%Y-%m-%d %H:%M") if c["t"] else "always"
        where = c.get("node") or c.get("bc") or (f"after boundary {c['cycle']}" if c["cycle"] is not None else "")
        print(f"{s[i]:.3f}  {c['source']:5s} {when}  {where}\n       shared terms: {', '.join(shared) or '(none: a match of meaning, not words)'}\n       {c['text'][:160]}")


if __name__ == "__main__":
    if "--search" in sys.argv:
        a = sys.argv
        search(a[a.index("--search") + 1], as_of=float(a[a.index("--as-of") + 1]) if "--as-of" in a else None,
               k=int(a[a.index("--k") + 1]) if "--k" in a else 8)
    else:
        build(candidates_only="--candidates" in sys.argv)
