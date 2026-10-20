"""Replicate Experiment 014's key findings from your own agent's record.

Experiment 014 asked when the knowledge web is worth pushing into an agent's context, and with
what query. Its findings come from one agent's record. This kit runs the same steps, unchanged,
on yours, and writes FIGURES ONLY: numbers and manifest hashes. Your transcripts, tasks and
artifacts are read on your machine and never leave it; post figures.json, nothing else.

The steps, in order, each reading what the one before wrote:
  0   semantic_events   one event stream: prompts (classified by origin), the agent's messages and
                        tool calls, compactions, task and duty updates
  0b  semantic_index    retrieval candidates (transcript spans, task and duty events, knowledge-web
                        artifacts), embedded with all-MiniLM-L6-v2; the newest fifth of operator
                        prompts sealed by a hash of their ids
  2a  semantic_labels   behavioral labels: what the agent consulted in the 20 tool calls after each
                        moment, among what was outside its context then
  4   semantic_tier_a   the trace against the prompt alone, by source, depth and moment (dev split)
  5   semantic_tier_b   the learned convolution the sealed step compares with
  6a  semantic_timing   where in a stretch of work the agent consults the record
  7   semantic_sealed   the sealed split, run once

Requirements: a MacEff checkout (this kit lives in it), Python 3.10+, numpy, and
sentence-transformers with all-MiniLM-L6-v2 available (the first run downloads it).

Usage:
  macf_tools knowledge eval --save-snapshot /path/to/out/corpus_snapshot.json
  python3 tools/replication/exp014/replicate.py --home ~ \\
      --transcripts '~/.claude/projects/<project>/*.jsonl' --snapshot /path/to/out/corpus_snapshot.json \\
      --out /path/to/out [--patterns my_machine_prompts.json] [--end 2026-10-20T00:00:00-04:00]

--patterns names prompts your deployment types into the pane as if it were the operator, such as
scheduled check-ins: {"cron": "regex", "wake": "regex"}. Without it, only the record's own
origin fields classify, and a machine that types like a human counts as the operator.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parent
STEPS = ("semantic_events", "semantic_index", "semantic_labels", "semantic_tier_a", "semantic_tier_b",
         "semantic_timing", "semantic_sealed")
HUMAN = ("operator", "telegram", "slash")


def transcripts(patterns):
    """Every transcript the patterns match, ordered by each file's first timestamp."""
    paths = sorted({Path(p) for pat in patterns for p in glob.glob(os.path.expanduser(pat))})

    def first(p):
        with open(p, errors="replace") as f:
            for line in f:
                try:
                    ts = json.loads(line).get("timestamp")
                except ValueError:
                    continue
                if ts:
                    return ts
        return "9999"
    return sorted((p for p in paths if p.suffix == ".jsonl"), key=first)


HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


def _plain(s, limit):
    return len(s) <= limit and all(c.isalnum() or c in " ._:/+-=<>" for c in s)


def scrub(value):
    """Numbers, booleans, hex digests and short identifiers pass; any other string is dropped, so no
    text from the record can reach the figures. A key that isn't plain is refused outright, since
    dropping it would merge two results."""
    if isinstance(value, dict):
        for k in value:
            if not _plain(str(k), 80):
                raise SystemExit(f"a result key is not a plain identifier, so figures.json is not written: {str(k)[:20]}...")
        return {str(k): scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and not HEX_DIGEST.fullmatch(value) and not _plain(value, 40):
        return "<removed>"
    return value


def figures(out: Path) -> dict:
    """The findings as numbers, with the hashes that identify the run."""
    events = json.loads((out / "events_manifest.json").read_text())
    split = json.loads((out / "split_manifest.json").read_text())
    prompts = events["prompts_by_origin"]
    total = sum(prompts.values())
    tier_a = json.loads((out / "step4_tier_a.json").read_text())
    sealed = json.loads((out / "step7_heldout.json").read_text())
    timing = json.loads((out / "step6_timing.json").read_text())
    return scrub({
        "kit": "exp014-replication/1",
        "manifests": {"events_sha256": events["sha256"], "events": events["events"],
                      "split": {k: v for k, v in split.items() if not isinstance(v, (list, dict))}},
        "machine_turns": {"prompts": total, "by_origin": prompts,
                          "share_not_human": round(1 - sum(prompts.get(o, 0) for o in HUMAN) / total, 4) if total else None},
        "boundaries": events.get("boundaries"),
        "dev": {"table_L1": tier_a["table_L1"], "comparisons_L1_mrr": tier_a["comparisons_L1_mrr"]},
        "sealed": {"held_moments": sealed["held_moments"], "table_L1": sealed["table_L1"],
                   "comparisons_mrr": sealed["comparisons_mrr"]},
        "timing": timing,
    })


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--home", required=True, help="the agent's home (holds agent/public/tasks, roles, ideas)")
    ap.add_argument("--transcripts", required=True, action="append", help="a transcript path or glob; repeat for several")
    ap.add_argument("--snapshot", required=True, help="written by: macf_tools knowledge eval --save-snapshot PATH")
    ap.add_argument("--out", required=True, help="a local folder for the run; it will hold private text")
    ap.add_argument("--patterns", help="JSON file of {origin: regex} for machine prompts typed into the pane")
    ap.add_argument("--end", help="leave out events at or after this time (ISO 8601 or epoch)")
    ap.add_argument("--from-step", choices=STEPS, help="resume at this step, keeping what earlier steps wrote")
    a = ap.parse_args(argv)
    found = transcripts(a.transcripts)
    if not found:
        sys.exit(f"no transcripts match {a.transcripts}")
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    end = ""
    if a.end:
        end = a.end if a.end.replace(".", "", 1).isdigit() else str(datetime.fromisoformat(a.end).timestamp())
    env = {**os.environ, "MACF_KIT_OUT": str(out), "MACF_KIT_HOME": str(Path(a.home).expanduser().resolve()),
           "MACF_KIT_TRANSCRIPTS": os.pathsep.join(map(str, found)),
           "MACF_KIT_SNAPSHOT": str(Path(a.snapshot).expanduser().resolve()), "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", "0")}
    if end:
        env["MACF_KIT_END"] = end
    if a.patterns:
        env["MACF_KIT_PATTERNS"] = str(Path(a.patterns).expanduser().resolve())
    print(f"{len(found)} transcript(s); writing to {out}", file=sys.stderr)
    steps = STEPS[STEPS.index(a.from_step):] if a.from_step else STEPS
    for step in steps:
        t0 = time.time()
        r = subprocess.run([sys.executable, str(KIT / f"{step}.py")], cwd=KIT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if r.returncode:
            sys.exit(f"{step} failed:\n{r.stderr[-3000:]}")
        print(f"  {step}: {time.time() - t0:.0f} s", file=sys.stderr)
    figs = figures(out)
    blob = json.dumps(figs, indent=2, sort_keys=True) + "\n"
    (out / "figures.json").write_text(blob)
    print(f"figures: {out / 'figures.json'} (sha256 {hashlib.sha256(blob.encode()).hexdigest()[:12]}); post this file only")


if __name__ == "__main__":
    main()
