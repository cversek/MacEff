"""E7 arm A0: the trial as it ran, replayed with the live service's own code and the Oct 20 index.

The live service (push_service.Service) is constructed as it was at each start: the index replayed
into the trace. Each incarnation (a 'running' state of unit push-trial) then tails the transcript
from where the file stood when it started, and at every request that reached the service catches up
(transcript records written since, task and duty events since the index), as Service.catch_up does.
Rankings are computed only at development-day moments unless --sealed is given.

    python3 a0.py [--sealed]       writes out/a0_picks[_sealed].json and prints the harness check
"""
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

import os
def _need(name):
    """A path the kit can't guess, from the environment, or a refusal that names it."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"E7 needs {name}: see the kit's README (it runs only on a seat that ran the push trial)")
    return value


os.environ.setdefault("PUSH_TRIAL_TRANSCRIPT", _need("E7_TRANSCRIPT"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, _need("E7_PUSH_TRIAL_DIR"))
import e7lib as L  # noqa: E402

SEALED = "--sealed" in sys.argv
DEBUG_DOC = {}
OUTDIR = L.HERE / "out"
OUTDIR.mkdir(exist_ok=True)
MACHINE = re.compile(r"^\s*(<task-notification|\[SYSTEM NOTIFICATION|<system-reminder|<channel source=\"plugin:maceff"
                     r"|This session is being continued|Another Claude session sent|<agent-message|<cross-session-message"
                     r"|MAIL CLOCK:|\[maceff:wake\]|<<autonomous-loop)")


def main():
    t_start = time.time()
    import push_service as ps
    from semantic_arms import IDX, ranked, scores, unit
    from semantic_labels import collapse
    from semantic_tier_a import PARTS
    import semantic_events as se

    svc = ps.Service()                     # loads the Oct 20 index and replays it, exactly as at each start
    base = (svc.trace.S.copy(), list(svc.trace.bounds), dict(svc.trace.last), svc.trace.t0)
    index_store_t = max((e["t"] for e in svc.events if e.get("scope") in ("task", "duty")), default=0.0)
    print(f"shallow cut {svc.shallow_cut:.4f}, index store_t {index_store_t}", flush=True)

    trial, unit_ev = L.trial_and_unit_events()
    starts = L.incarnations(unit_ev)
    downs = L.down_intervals(unit_ev)
    reqs = L.requests(trial)
    moms = L.moments(trial)
    print(f"moments {len(moms)}, requests {len(reqs)}, incarnations {len(starts)}", flush=True)

    # transcript records in file order, with the time each line was written (a running max)
    live = sorted(L.load("live_records"), key=lambda r: r["ln"])
    w = 0.0
    for r in live:
        t = r["rec"]["t"] if "rec" in r else r["user"][0]
        w = max(w, t)
        r["w"] = w
    kit = L.load("kit_events")
    store = sorted(kit["task"] + kit["duty"], key=lambda e: e["t"])
    store = [e for e in store if e["t"] >= index_store_t]

    # embeddings of every text the trace could be fed, once (batch padding moves the last bits only)
    texts = set()
    for r in live:
        if "rec" in r:
            if r["rec"]["kind"] != "boundary":
                texts.add(r["rec"]["text"] or " ")
        else:
            ev = se.prompt_event(r["user"][0], r["user"][1], r["user"][2], set())
            if ev and ev["kind"] != "boundary":
                texts.add(ev["text"] or " ")
    for e in store:
        texts.add(e["text"] or " ")
    calls = L.Calls()
    MODE = os.environ.get("E7_STORE", "t")
    if MODE == "avail":
        nm = L.store_avail(store, calls)
        print(f"store events since the index {len(store)}, write time matched {nm}", flush=True)
    else:
        for e in store:
            e["avail"] = e["t"]
    if MODE == "none":
        store = []
    elif MODE.startswith("skip:"):
        skip = set(MODE[5:].split(","))
        store = [e for e in store if str(e.get("task")) not in skip]
    store.sort(key=lambda e: e["avail"])
    print("store mode", MODE, len(store), flush=True)
    prompts = sorted(L.load("prompts"), key=lambda p: p["t"])
    ptimes = [p["t"] for p in prompts]
    qprompts = sorted([e for e in kit["transcript"] if e["kind"] == "prompt" and e.get("mid_turn")
                       and e["origin"] in ("operator", "telegram") and e["t"] >= L.RESTART - 3600], key=lambda e: e["t"])
    qtimes = [q["t"] for q in qprompts]

    def moment_text(m, r):
        if m["moment"] == "T1":
            import bisect
            j = bisect.bisect_left(ptimes, r - 3)
            for p in prompts[j:j + 40]:
                if p["t"] > r + 60:
                    break
                txt = p["text"]
                if MACHINE.search(txt[:400]) or p["compact"]:
                    continue
                return re.sub(r"<channel[^>]*>|</channel>", "", txt), p["t"]
            # a prompt delivered mid-turn is no user record: it is a queued_command attachment, which
            # the kit's stream delivers at its queue removal; take the first operator or Telegram one
            j = bisect.bisect_left(qtimes, r - 5)
            for q in qprompts[j:j + 5]:
                if q["t"] > r + 1800:
                    break
                return q["text"], q["t"]
            return None, None
        j = calls.index_after(r + 0.5) - 1
        while j >= 0 and calls.t[j] > r - 600:
            c = calls.calls[j]
            if m["moment"] == "T5":
                if c["name"] in ("Write", "Edit") and L.CA_PATH.search(str(c["input"].get("file_path", ""))):
                    body = c["input"].get("content") or c["input"].get("new_string") or ""
                    return f"{c['name']}: {c['input'].get('file_path')}\n{body[:1500]}", c["t"]
            else:
                return f"{c['name']}: {json.dumps(c['input'])[:400]}", c["t"]
            j -= 1
        return None, None

    want = [m for m in moms if SEALED or m["split"] == "dev"]
    for m in want:
        r = m["ts"] - (m["latency_ms"] / 1000 if isinstance(m["latency_ms"], (int, float)) else 1.5)
        m["r"] = r
        m["text"], m["text_t"] = moment_text(m, r)
        if m["text"]:
            texts.add(m["text"] or " ")
    texts = sorted(texts)
    print(f"embedding {len(texts)} texts", flush=True)
    import hashlib, pickle
    cpath = L.CACHE / "emb_live.pkl"
    cached = pickle.load(open(cpath, "rb")) if cpath.exists() else {}
    todo = [t for t in texts if t not in cached]
    if todo:
        Xn = svc.embed(todo)
        cached.update({t: Xn[i] for i, t in enumerate(todo)})
        pickle.dump(cached, open(cpath, "wb"))
    X = np.stack([cached[t] for t in texts])
    emb = {t: X[i] for i, t in enumerate(texts)}
    D = svc._depth(X)
    dep = {t: float(D[i]) for i, t in enumerate(texts)}
    print(f"embedded in {time.time() - t_start:.0f} s", flush=True)

    # walk: incarnations, requests, moments, in time order
    want_at = sorted(want, key=lambda m: m["r"])
    timeline = sorted([(r, "req", None) for r in reqs] + [(m["r"], "mom", k) for k, m in enumerate(want_at)],
                      key=lambda x: (x[0], x[1] == "req"))
    # a moment is ranked right after its own request's catch-up: put each moment after its request
    timeline = sorted([(r, 0, None) for r in reqs] + [(m["r"], 1, k) for k, m in enumerate(want_at)])
    inc = -1
    trace = None
    li = 0
    store_t, store_seen, seen_tg = index_store_t, set(), set()

    def begin(k):
        nonlocal trace, li, store_t, store_seen, seen_tg
        tr = ps.Trace(svc.trace.S.shape[1], svc.cands, svc.C, svc.resolve)
        tr.S = base[0].copy()
        tr.bounds, tr.last, tr.t0 = list(base[1]), dict(base[2]), base[3]
        trace = tr
        R = starts[k]
        li = next((i for i, r in enumerate(live) if r["w"] > R - 1.0), len(live))
        store_t, store_seen, seen_tg = index_store_t, set(), set()

    def catch_up(now):
        nonlocal li, store_t
        new = []
        while li < len(live) and live[li]["w"] <= now:
            r = live[li]
            li += 1
            if "rec" in r:
                new.append(r["rec"])
            else:
                ev = se.prompt_event(r["user"][0], r["user"][1], r["user"][2], seen_tg)
                if ev:
                    new.append(ev)
        snew = []
        for e in store:
            if e["avail"] > now:
                break
            key = (e["t"], e["kind"], e["text"])
            if e["t"] >= store_t and key not in store_seen:
                store_seen.add(key)
                snew.append(e)
        if snew:
            store_t = max(e["t"] for e in snew)
        for e in sorted(new + snew, key=lambda e: e["t"]):
            if e["kind"] == "boundary":
                trace.add(e, None, 0.0)
            else:
                tx = e["text"] or " "
                trace.add(e, emb[tx], dep[tx])

    def rank(text, now, moment):
        x = emb[text or " "]
        d = dep[text or " "]
        parts = {"prompt": d * x.astype(np.float64)}
        for (s, rr), wt in zip(PARTS, svc.w):
            if wt:
                parts[f"{s} trace ({rr})"] = wt * unit(trace.S[IDX[(s, rr, "gated", "whole")]]).astype(np.float64)
        q = sum(parts.values())
        start, in_ctx = trace.context(now)
        top = ranked(q, svc.C, svc.cand_t, start, in_ctx, 80)
        docs = collapse(top, svc.docs, 5)
        c = next((i for i in top if docs and svc.docs[i] == docs[0]), None)
        fb = None
        if c is not None:
            contrib = {n: float(scores(svc.C[c:c + 1], v)[0]) for n, v in parts.items()}
            tot = sum(contrib.values()) or 1.0
            fb = {n: round(v / tot, 2) for n, v in contrib.items()}
        dbg = None
        if DEBUG_DOC.get("doc"):
            ids = [i for i, dd in enumerate(svc.docs) if dd == DEBUG_DOC["doc"]]
            sc = scores(svc.C[ids], q)
            j = int(np.argmax(sc))
            best = ids[j]
            top_s = float(scores(svc.C[top[0]:top[0] + 1], q)[0]) if top else None
            dbg = {"logged_best": float(sc[j]), "top": top_s, "excluded_t": bool(svc.cand_t[best] >= start),
                   "excluded_ctx": sum(1 for i in ids if i in in_ctx), "n_ids": len(ids), "best_t": float(svc.cand_t[best])}
        DEBUG_DOC["dbg"] = dbg
        return docs, fb, d, start, len(in_ctx)

    for when, kind, k in timeline:
        while inc + 1 < len(starts) and starts[inc + 1] <= when:
            inc += 1
            begin(inc)
        if trace is None:
            continue
        if kind == 0:
            catch_up(when)
            continue
        m = want_at[k]
        if not m["text"]:
            m["a0"] = None
            continue
        catch_up(when)
        DEBUG_DOC["doc"] = m["doc"]
        docs, fb, d, start, nctx = rank(m["text"], when, m["moment"])
        m["dbg"] = DEBUG_DOC.get("dbg")
        m.update({"a0": docs[0] if docs else None, "a0_top5": docs, "a0_found_by": fb, "a0_depth": d,
                  "ctx_start": start, "n_in_ctx": nctx, "incarnation": inc})

    for m in want:
        m["crash"] = any(a <= m["ts"] <= b for a, b in downs) if m["outcome"] == "failed" else None
    out = OUTDIR / ("a0_picks_sealed.json" if SEALED else "a0_picks.json")
    out.write_text(json.dumps(want, default=float, indent=0))

    # the harness check: 200 logged pushes from development days, fixed seed
    dev_pushed = sorted([m for m in want if m["split"] == "dev" and m["outcome"] == "pushed"], key=lambda m: m["ts"])
    rng = random.Random(L.SEED)
    sample = rng.sample(dev_pushed, 200)
    hits = sum(m.get("a0") == m["doc"] for m in sample)
    allhits = sum(m.get("a0") == m["doc"] for m in dev_pushed)
    by = Counter((m["moment"], m.get("a0") == m["doc"]) for m in sample)
    print(f"HARNESS CHECK: A0 reproduces {hits}/200 of the seeded sample; all dev pushes {allhits}/{len(dev_pushed)}")
    print("by moment (match):", dict(by))
    print("no text reconstructed:", sum(1 for m in sample if not m["text"]))
    print(f"wall {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()
