"""E2b: write a short model-made context for every artifact in the web, owner-only.

Each artifact is shown to Claude Haiku as its kind, date and title and the first MAX_WORDS words
of its indexed body (label-bearing text already removed, so the model never sees a citation or a
file name), with a fixed instruction. Headless `claude -p` with no tools and no MCP servers.
Resumable: contexts already written are kept. Stops when the list-price cost reaches CAP_USD.

usage: e2b_contexts.py SNAPSHOT OUT.json [workers]
"""

import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from macf.knowledge_eval import Corpus, load_snapshot
from macf.knowledge_eval_text import _kind, body_text

MAX_WORDS = 3000
CAP_USD = 25.0
MODEL = "haiku"
SYSTEM = ("You will see one document from an AI agent's private record of its work (its checkpoints, "
          "reflections, learnings, ideas, policies, tasks and reports). Write one or two sentences, at most "
          "60 words, that situate this document within that record: what kind of artifact it is, what work or "
          "question it belongs to, and what it is about, so that a search over the whole record can find it. "
          "Reply with the sentences only.")
HERE = Path(__file__).resolve().parent
NOMCP = HERE / "nomcp.json"


def prompt(node):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(node.get("path", "")).name)
    words = body_text(node).split()
    head = f"kind: {_kind(node)}\ndate: {m.group(1) if m else 'unknown'}\ntitle: {node.get('title') or ''}"
    return f"{head}\n\n<document>\n{' '.join(words[:MAX_WORDS])}\n</document>"


def call(text):
    r = subprocess.run(["claude", "-p", "--model", MODEL, "--output-format", "json", "--no-session-persistence",
                        "--strict-mcp-config", "--mcp-config", str(NOMCP), "--tools", "", "--system-prompt", SYSTEM],
                       input=text, capture_output=True, text=True, timeout=180, cwd=str(HERE))
    events = json.loads(r.stdout)
    res = [e for e in events if e.get("type") == "result"][-1]
    if res.get("is_error"):
        raise RuntimeError(str(res.get("result"))[:200])
    return res["result"].strip(), float(res.get("total_cost_usd") or 0.0)


def main(snap_path, out, workers=6):
    NOMCP.write_text('{"mcpServers": {}}')
    snap, digest = load_snapshot(Path(snap_path))
    corpus = Corpus(snap, digest)
    done = json.load(open(out)) if os.path.exists(out) else {"contexts": {}, "cost_usd": 0.0, "failed": {}}
    todo = [nid for nid in corpus.web if nid not in done["contexts"]]
    lock = threading.Lock()
    print(f"{len(corpus.web)} artifacts, {len(todo)} to write, cost so far ${done['cost_usd']:.3f}", flush=True)

    def save():
        tmp = out + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(done, fh)
        os.replace(tmp, out)

    stop = threading.Event()

    def one(nid):
        if stop.is_set():
            return
        try:
            ctx, cost = call(prompt(corpus.nodes[nid]))
        except (subprocess.SubprocessError, ValueError, KeyError, IndexError, RuntimeError, OSError) as e:
            with lock:
                done["failed"][nid] = f"{type(e).__name__}: {e}"[:200]
            print(f"warning: {nid}: {type(e).__name__}", file=sys.stderr, flush=True)
            return
        with lock:
            done["contexts"][nid] = ctx
            done["failed"].pop(nid, None)
            done["cost_usd"] += cost
            if done["cost_usd"] >= CAP_USD:
                stop.set()
            n = len(done["contexts"])
            if n % 50 == 0:
                save()
                print(f"{n} written, ${done['cost_usd']:.3f}", flush=True)

    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        for f in as_completed([ex.submit(one, nid) for nid in todo]):
            f.result()
    save()
    print(f"done: {len(done['contexts'])} written, {len(done['failed'])} failed, ${done['cost_usd']:.3f}"
          f"{', STOPPED AT THE CAP' if stop.is_set() else ''}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
