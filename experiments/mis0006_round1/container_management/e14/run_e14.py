"""E14: does a failing index get noticed? (MIS-0006 deliberation, MacEff #1149, comment 7091101712)

Builds four index copies (F0 control, F1 stale, F2 vector-only, F3 empty), starts one instance of
today's search service on each, picks five known-answer queries on F0 before any fault is planted,
then for 30 minutes sends ordinary queries (20 a minute each, a fixed list) and runs the canary
every 60 s. Writes everything to ./out/. Canary events go to out/canary_events.jsonl, not to the
agent's event log, so the experiment does not write into the record it observes.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
#: The policies the instances index: E14_POLICIES_DIR, else this checkout's own framework/policies.
SRC = Path(os.environ.get("E14_POLICIES_DIR") or HERE.parents[3] / "framework" / "policies")
PORTS = {"F0": 9011, "F1": 9012, "F2": 9013, "F3": 9014}
RUN_S = 1800
PERIOD_S = 60
ORDINARY = [
    "how do I merge a pull request safely", "what should a checkpoint contain before compaction",
    "how do I recover after a compaction", "when should I delegate work to a subagent",
    "how do I write a learning with cross references", "what is the rule for commit messages",
    "how should I name experiment folders", "how do I report a task as complete with evidence",
    "what does the operator want in a question dialog", "how do I curate the knowledge web",
    "what is the policy for autonomous sprints", "how should I handle a permission prompt",
    "what goes in a reflection at the end of a cycle", "how do ideas get promoted to experiments",
    "how do I write a roadmap with phases", "what does a primal daemon supervise",
    "how should tests be scoped while building", "what are the rules for public text and opsec",
    "how do I mail another agent", "what should I do when a hook refuses a command",
]
CANDIDATES = ORDINARY[:12]


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(OUT / "run.log", "a") as f:
        f.write(line + "\n")


def build(name, src_dir):
    db = OUT / f"{name}.lance"
    subprocess.run([sys.executable, "-m", "macf.cli", "policy", "build_index", "--policies-dir", str(src_dir),
                    "--db-path", str(db), "--json"], check=True, capture_output=True)
    import lancedb
    lancedb.connect(str(db)).open_table("documents").create_fts_index("content", replace=True)
    return db


def start(name, db):
    errf = open(OUT / f"{name}.service.log", "w")
    p = subprocess.Popen([sys.executable, str(HERE / "instance.py"), str(PORTS[name]), str(db)],
                         stdout=errf, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return p


def ask(name, q, timeout=10.0):
    from macf.search_service.client import query_search_service
    return query_search_service(namespace="policy", query=q, port=PORTS[name], timeout_s=timeout)


def top(res):
    ex = res.get("explanations") or []
    return ex[0].get("policy_name") if ex else None


def modes(res):
    return sorted({k for e in (res.get("explanations") or []) for k in (e.get("retriever_contributions") or {})})


def newest(path):
    return max((p.stat().st_mtime for p in Path(path).rglob("*") if p.is_file()), default=0.0)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    t0 = time.time()
    srcs = {n: OUT / f"src_{n}" for n in PORTS}
    for n in ("F0",):
        shutil.copytree(SRC, srcs[n])
    db0 = build("F0", srcs["F0"])
    procs = {"F0": start("F0", db0)}
    for _ in range(120):
        if ask("F0", "warm up the policy index please", timeout=30).get("explanations"):
            break
        time.sleep(1)
    # the shipped service's own mode on F0, to show the patch is what makes hybrid run
    from macf.hybrid_search.policy_search import PolicySearch
    from macf.utils import recommend as R
    shipped = PolicySearch(db0, model_name=R.EMBEDDING_MODEL).hybrid_search(CANDIDATES[0], limit=3)["search_type"]
    log(f"F0 up; the shipped hybrid_search on this healthy copy reports: {shipped}")
    # known answers, chosen on F0 before any fault exists
    stable = []
    for q in CANDIDATES:
        tops = [top(ask("F0", q)) for _ in range(10)]
        if tops[0] and len(set(tops)) == 1:
            stable.append((q, tops[0]))
    known = stable[:5]
    json.dump(known, open(OUT / "known_answers.json", "w"), indent=1)
    log(f"known answers ({len(stable)} stable of {len(CANDIDATES)}): {known}")
    # plant the faults, each on its own copy, after the known answers are fixed
    for n in ("F1", "F2", "F3"):
        shutil.copytree(srcs["F0"], srcs[n])
        shutil.copytree(db0, OUT / f"{n}.lance")
    time.sleep(2)
    with open(next(srcs["F1"].rglob("git_discipline.md")), "a") as f:   # F1: a source changes after the build
        f.write("\n\n## A section added after the index was built\n\nE14 planted change.\n")
    shutil.rmtree(OUT / "F2.lance" / "documents.lance" / "_indices")      # F2: no full-text index
    import lancedb
    for t in ("documents", "questions", "policies"):                       # F3: an empty index
        try:
            lancedb.connect(str(OUT / "F3.lance")).open_table(t).delete("true")
        except Exception as e:  # noqa: BLE001 - recorded
            log(f"F3 empty {t}: {type(e).__name__}: {e}")
    for n in ("F1", "F2", "F3"):
        procs[n] = start(n, OUT / f"{n}.lance")
    for n in ("F1", "F2", "F3"):
        for _ in range(120):
            r = ask(n, "warm up the policy index please", timeout=30)
            if r.get("explanations") is not None and r.get("error") != "connection_refused":
                break
            time.sleep(1)
    planted = time.time()
    log(f"faults planted and instances up at +{planted - t0:.0f}s; running {RUN_S}s")
    ordinary_rows, canary_rows = [], []
    next_canary = planted
    qi = 0
    while time.time() - planted < RUN_S:
        now = time.time()
        if now >= next_canary:
            for n in PORTS:
                hits, ms, errs = 0, set(), []
                for q, ans in known:
                    r = ask(n, q)
                    hits += top(r) == ans
                    ms.update(modes(r))
                    if r.get("error"):
                        errs.append(r["error"])
                db = OUT / f"{n}.lance"
                stale = newest(srcs[n]) > newest(db)
                fail = hits < len(known) or ms != {"hybrid"} or bool(errs)
                row = {"t": round(now - planted, 1), "inst": n, "hits": hits, "of": len(known), "modes": sorted(ms),
                       "errors": errs[:2], "index_older_than_source": stale, "failing": fail}
                canary_rows.append(row)
                with open(OUT / "canary_events.jsonl", "a") as f:
                    f.write(json.dumps(row) + "\n")
            next_canary += PERIOD_S
        q = ORDINARY[qi % len(ORDINARY)]
        qi += 1
        for n in PORTS:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                from macf.search_service.client import get_policy_injection
                try:
                    text = get_policy_injection(q, timeout_s=10.0, port=PORTS[n])
                    exc = None
                except Exception as e:  # noqa: BLE001 - recorded as noticed
                    text, exc = "", f"{type(e).__name__}: {e}"
            ordinary_rows.append({"t": round(time.time() - planted, 1), "inst": n, "q": qi,
                                  "empty": not text, "warn_in_text": "⚠" in text, "stderr": buf.getvalue()[:200],
                                  "exc": exc})
        time.sleep(3)
    json.dump(ordinary_rows, open(OUT / "ordinary.json", "w"))
    alive = {n: p.poll() for n, p in procs.items()}
    for p in procs.values():
        p.terminate()
    log(f"done at +{time.time() - t0:.0f}s; instance exit codes during the run (None = alive): {alive}")
    log("RESULTS_WRITTEN")


if __name__ == "__main__":
    main()
