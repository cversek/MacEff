"""E7 prep: one read of the record into cached, private, local files (this scratch dir only).

Writes into OUT (default: ./cache):
  live_records.pkl   transcript records parsed exactly as push_service._records parses them, each
                     with its line number, from 2026-10-20 18:00 on (A0's live tail)
  calls.pkl          every tool call (line, t, name, input json) from 2026-10-01 on (measures, moment text)
  prompts.pkl        every user text record (line, t, text, origin fields) from 2026-10-20 on (T1 text)
  kit_events.pkl     the Experiment 014 kit's event stream over the whole transcript plus the task
                     and duty stores as they stand now (the as-of walk, A1 to A6 and AR)
  snapshot.json      the corpus as it stands now (macf.knowledge_eval.build_snapshot), for A1's kg candidates
Reads only; writes nothing outside OUT.
"""
import json
import os
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("E7_CACHE", HERE / "cache"))
OUT.mkdir(parents=True, exist_ok=True)
def _need(name):
    """A path the kit can't guess, from the environment, or a refusal that names it."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"E7 needs {name}: see the kit's README (it runs only on a seat that ran the push trial)")
    return value


TRANSCRIPT = Path(_need("E7_TRANSCRIPT"))
KIT = Path(_need("E7_PUSH_TRIAL_DIR")) / "kit"
os.environ["MACF_KIT_OUT"] = str(OUT / "kit_out")
os.environ["MACF_KIT_HOME"] = str(Path.home())
os.environ["MACF_KIT_TRANSCRIPTS"] = str(TRANSCRIPT)
os.environ["MACF_KIT_SNAPSHOT"] = str(OUT / "snapshot.json")
os.environ["MACF_KIT_PATTERNS"] = str(KIT.parent / "patterns.json")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, str(KIT))
import semantic_events as se  # noqa: E402

LIVE_FROM = se.epoch("2026-10-20T22:00:00Z")    # 18:00 EDT Oct 20, before the first restart
CALLS_FROM = se.epoch("2026-10-01T04:00:00Z")


def pass_live():
    live, calls, prompts = [], [], []
    with open(TRANSCRIPT, "rb") as f:
        for ln, raw in enumerate(f):
            if b'"timestamp"' not in raw:
                continue
            if b'"type":"user"' not in raw and b'"type":"assistant"' not in raw:
                continue
            try:
                d = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            ts, kind = d.get("timestamp"), d.get("type")
            if not ts or kind not in ("user", "assistant"):
                continue
            t = se.epoch(ts)
            if t < CALLS_FROM:
                continue
            content = (d.get("message") or {}).get("content")
            if kind == "assistant" and isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        calls.append({"ln": ln, "t": t, "name": b.get("name", ""), "input": b.get("input") or {},
                                      "id": b.get("id")})
            if t < LIVE_FROM:
                continue
            # push_service._records, verbatim in logic (seen_tg is applied later, per incarnation)
            if kind == "user":
                if isinstance(content, list):
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                        continue
                    content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                if not isinstance(content, str) or not content.strip():
                    continue
                prompts.append({"ln": ln, "t": t, "text": content, "origin": d.get("origin"), "turnOrigin": d.get("turnOrigin"),
                                "sched": d.get("scheduledTaskId"), "isMeta": d.get("isMeta"), "compact": bool(d.get("isCompactSummary"))})
                if d.get("isCompactSummary") or se.origin_of(content) == "compaction":
                    live.append({"ln": ln, "rec": {"t": t, "scope": "conv", "kind": "boundary", "origin": "compaction", "text": ""}})
                    continue
                live.append({"ln": ln, "user": (t, content, se.origin_from(d.get("origin"), d.get("turnOrigin"), d.get("scheduledTaskId"), content))})
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                        live.append({"ln": ln, "rec": {"t": t, "scope": "conv", "kind": "agent", "origin": "agent", "text": b["text"].strip()[:1200]}})
                    elif isinstance(b, dict) and b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        ev = {"t": t, "scope": "conv", "kind": "tool", "origin": "agent", "text": se.tool_summary(b.get("name", ""), inp)}
                        c = se.consults(json.dumps(inp))
                        if c:
                            ev["consults"] = c
                        live.append({"ln": ln, "rec": ev})
    return live, calls, prompts


def main():
    what = sys.argv[1:] or ["live", "kit", "snapshot"]
    if "live" in what:
        live, calls, prompts = pass_live()
        for name, obj in (("live_records", live), ("calls", calls), ("prompts", prompts)):
            with open(OUT / f"{name}.pkl", "wb") as f:
                pickle.dump(obj, f)
        print(f"live records {len(live)}, calls {len(calls)}, prompts {len(prompts)}", flush=True)
    if "snapshot" in what:
        from macf import knowledge_eval as ke
        snap = ke.build_snapshot()
        (OUT / "snapshot.json").write_text(json.dumps(snap))
        print(f"snapshot nodes {len(snap['nodes'])} taken {snap['taken_at']}", flush=True)
    if "kit" in what:
        ev = se.transcript_events()
        tasks, duties = se.task_events(), se.duty_events()
        with open(OUT / "kit_events.pkl", "wb") as f:
            pickle.dump({"transcript": ev, "task": tasks, "duty": duties}, f)
        print(f"kit transcript events {len(ev)}, task {len(tasks)}, duty {len(duties)}", flush=True)
    print("prep done", flush=True)


if __name__ == "__main__":
    main()
