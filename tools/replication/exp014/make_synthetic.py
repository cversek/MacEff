"""A synthetic agent home, transcript and snapshot, seeded, so the kit can be run end to end on a
record that belongs to nobody: a smoke test before your own, and the kit's proof that it doesn't
depend on the host it was written on.

Usage: python3 tools/replication/exp014/make_synthetic.py OUT_DIR
Writes OUT_DIR/home (learnings and tasks), OUT_DIR/transcript.jsonl and OUT_DIR/snapshot.json,
then prints the replicate.py command to run on them.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOPICS = ["compaction", "scheduler", "delegation", "permissions", "notifications", "budget",
          "testing", "worktrees", "reviews", "channels"]
WORDS = ("the daemon restarted while a wake was owed and the notice was held until the channel attached "
         "a test that substitutes a fake receiver proves the sender not the delivery so run the real parser "
         "the budget gauge reads in whole percents and a fresh sample avoids an echo of an older fetch "
         "a worktree pinned to a commit keeps the trial apart from main and its hooks").split()
START = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main(out):
    rng = random.Random("exp014-synthetic")
    out = Path(out)
    home = out / "home"
    learn = home / "agent/private/learnings"
    tasks = home / "agent/public/tasks"
    learn.mkdir(parents=True, exist_ok=True)
    tasks.mkdir(parents=True, exist_ok=True)
    nodes, learnings = {}, []
    for i in range(60):
        topic = TOPICS[i % len(TOPICS)]
        when = START + timedelta(hours=6 * i)
        name = f"{when:%Y-%m-%d_%H%M%S}_{topic}_note_{i:02d}_learning.md"
        text = (f"# Learning: {topic} note {i}\n\n" + " ".join(rng.choice(WORDS) for _ in range(80))
                + f"\n\n## Wiki-Links\n\n[[{topic}]] [[{TOPICS[(i + 3) % len(TOPICS)]}]]\n")
        (learn / name).write_text(text)
        nid = f"learnings:{name[:-3]}"
        nodes[nid] = {"type": "learnings", "class": "conceptual_authority", "title": f"{topic} note {i}",
                      "path": str(learn / name), "concepts": sorted({topic, TOPICS[(i + 3) % len(TOPICS)]}),
                      "text": text, "in_web": True, "linked": True}
        learnings.append((when, learn / name, topic))
    for n in range(1, 41):
        t0 = START + timedelta(hours=7 * n)
        notes = [{"breadcrumb": f"s_00000000/c_1/p_00000000/t_{int((t0 + timedelta(hours=h)).timestamp())}",
                  "description": f"note on {TOPICS[n % len(TOPICS)]}: " + " ".join(rng.choice(WORDS) for _ in range(20)),
                  "agent": "PA"} for h in (1, 3)]
        meta = {"creation_breadcrumb": f"s_00000000/c_1/p_00000000/t_{int(t0.timestamp())}", "created_cycle": 1,
                "created_by": "PA", "task_type": "TASK", "plan": "synthetic", "parent_id": "000", "updates": notes}
        import yaml
        desc = '<macf_task_metadata version="1.0">\n' + yaml.safe_dump(meta, sort_keys=False) + "</macf_task_metadata>"
        (tasks / f"{n}.json").write_text(json.dumps({"id": str(n), "subject": f"#{n} work on {TOPICS[n % len(TOPICS)]}",
                                                     "description": desc, "status": "completed", "blocks": [], "blockedBy": []}))
    records, t = [], START
    for k in range(900):
        t += timedelta(minutes=rng.randint(4, 40))
        if k and k % 150 == 0:
            records.append({"type": "user", "timestamp": iso(t), "isCompactSummary": True,
                            "message": {"content": "This session is being continued from a previous conversation. Summary: "
                                        + " ".join(rng.choice(WORDS) for _ in range(40))}})
            continue
        topic = rng.choice(TOPICS)
        shallow = rng.random() < 0.35
        text = rng.choice(["continue", "ok", "go ahead", "yes"]) if shallow else \
            f"please look at the {topic} problem: " + " ".join(rng.choice(WORDS) for _ in range(rng.randint(6, 30)))
        rec = {"type": "user", "timestamp": iso(t), "message": {"content": text}}
        if rng.random() < 0.15:
            rec.update(isMeta=True, origin={"kind": "channel"})
            rec["message"]["content"] = f'<channel source="telegram" message_id="{k}">{text}</channel>'
        records.append(rec)
        for step in range(rng.randint(2, 8)):
            t += timedelta(seconds=20)
            past = [p for w, p, tp in learnings if w < t - timedelta(days=1) and (tp == topic or rng.random() < 0.1)]
            if past and rng.random() < 0.4:
                tool = {"type": "tool_use", "name": "Read", "input": {"file_path": str(rng.choice(past))}}
            elif rng.random() < 0.05:
                tool = {"type": "tool_use", "name": "Write",
                        "input": {"file_path": str(home / f"agent/private/reflections/{t:%Y-%m-%d_%H%M%S}_note.md"), "content": "x"}}
            elif rng.random() < 0.15:
                tool = {"type": "tool_use", "name": "Bash", "input": {"command": f"macf_tools task get #{rng.randint(1, 40)}"}}
            else:
                tool = {"type": "tool_use", "name": "Bash", "input": {"command": f"echo working on {topic}"}}
            records.append({"type": "assistant", "timestamp": iso(t),
                            "message": {"content": [{"type": "text", "text": f"Working on {topic}, step {step}."}, tool]}})
    # compact separators, as Claude Code writes its transcripts (step 0 prefilters on them)
    (out / "transcript.jsonl").write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n")
    (out / "snapshot.json").write_text(json.dumps({"taken_at": iso(t), "nodes": nodes, "learnings_index": None}))
    print(f"python3 {Path(__file__).resolve().parent / 'replicate.py'} --home {home} --transcripts {out / 'transcript.jsonl'} "
          f"--snapshot {out / 'snapshot.json'} --out {out / 'run'}")


if __name__ == "__main__":
    main(sys.argv[1])
