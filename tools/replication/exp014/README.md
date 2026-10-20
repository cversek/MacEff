# Replicating Experiment 014 from your own record

Experiment 014 asked **when the knowledge web is worth pushing into an agent's context, and with what query**. Its findings will shape a first-draft MIS for a push, and they come from one agent's record. Before anyone argues that draft, this kit lets each maintainer run the same steps on their own agent's record and say whether the findings hold there.

This is a measurement rig on its own branch. It isn't merged, and nothing in MacEff imports it.

## What you run, and what leaves your machine

The kit reads your agent's transcripts, task store and knowledge web **on your machine**. It writes a run folder that holds private text, so keep that folder local. It also writes `figures.json`, which holds **numbers, short result names and hashes only**: every other string is removed before it's written. Post `figures.json` and nothing else.

```bash
# 1. Pin your corpus (owner-only; it holds your artifacts' text)
macf_tools knowledge eval --save-snapshot /path/to/run/corpus_snapshot.json

# 2. Smoke-test the kit on a synthetic record that belongs to nobody
python3 tools/replication/exp014/make_synthetic.py /tmp/exp014-synth   # prints the command to run

# 3. Run it on yours
python3 tools/replication/exp014/replicate.py --home ~ \
    --transcripts '~/.claude/projects/<your project>/*.jsonl' \
    --snapshot /path/to/run/corpus_snapshot.json --out /path/to/run \
    [--patterns my_machine_prompts.json] [--end 2026-10-20T00:00:00-04:00]
```

Requirements: this MacEff checkout, Python 3.10 or later, `numpy`, and `sentence-transformers` with `all-MiniLM-L6-v2`, which the first run downloads. A record of about 60,000 events took 9 minutes on a 32-thread Linux machine, most of it embedding.

**`--patterns`** names the prompts your deployment types into the pane as if it were you, such as scheduled check-ins: a JSON object of `{"cron": "regex", "wake": "regex"}`. Without it, only the transcript's own origin fields classify prompts, and a machine that types like a human is counted as the operator.

## The steps

Each step reads only what the steps before it wrote, and none of their algorithms changed in the port.

| Step | Script | What it does |
|---|---|---|
| 0 | `semantic_events` | one event stream: prompts classified by origin, the agent's messages and tool calls, compactions and new sessions, task and duty updates |
| 0b | `semantic_index` | retrieval candidates (transcript spans, task and duty events, knowledge-web artifacts) embedded; the newest fifth of operator prompts sealed by a hash of their ids |
| 2a | `semantic_labels` | behavioral labels: what the agent consulted in the 20 tool calls after each moment, among what was outside its context then |
| 4 | `semantic_tier_a` | the trace against the prompt alone, by source, depth and moment, on the development split |
| 5 | `semantic_tier_b` | the learned convolution the sealed step compares with |
| 6a | `semantic_timing` | where in a stretch of work the agent consults the record |
| 7 | `semantic_sealed` | the sealed split, run once |

The moments: **T1**, an operator or Telegram prompt (split by depth, 1 shallow to 3 deep); **T2**, every 20th tool call since the last such prompt; **T3**, the first such prompt after a compaction; **T4**, a task start; **T5**, the call that writes an artifact.

## The predictions, so a replication can fail

These are the original record's figures: MRR per moment on the sealed split, the trace query minus the prompt alone, with 95% bootstrap intervals. In `figures.json`, look under `sealed.comparisons_mrr.<moment>["mixture minus prompt"]`.

| Finding | Original record | It fails if |
|---|---|---|
| **The null increment.** The trace helps when the prompt says little, not when it says enough | shallow (T1/depth1) +0.079 [0.017, 0.180]; deep (T1/depth3) +0.029 [−0.035, 0.123] | the deep interval excludes zero above the shallow one's |
| **Overall**, the trace beats the prompt | all moments +0.114 [0.067, 0.160] | the interval includes zero |
| **Moments.** It helps most just before an artifact write and mid-work, least at task starts and after compactions | T5 +0.265 [0.127, 0.399]; T2 +0.103 [0.030, 0.185]; T4 +0.028 [0.0, 0.083]; T3 +0.024 [0.0, 0.071] | T3 or T4 beat T5 |
| **Sources.** The task tree alone carries most of it | `task_fast minus prompt`, all moments, +0.114 [0.070, 0.161], level with the mixture | another single source beats the task tree |
| **Machine turns.** A large share of what reaches the agent as a "prompt" is machines | 44% (`machine_turns.share_not_human`) | the share is under 10% on a deployment with scheduled work |
| **Timing.** Consults are enriched just before writes and depleted deep into a stretch | ratio 2.59 within 3 calls before a write, 0.53 after 20 calls (`timing.timing_H8`) | the before-write ratio is at or under 1 |

Your figures will differ from these: different work, different amounts of it. A finding replicates if its direction holds and its interval agrees. Where your record is too small for an interval to say anything, say so; that's a result too.

## On this kit's own checks

- **It reproduces the original exactly.** Run on the original record with the original corpus and cutoff, the sealed table and every sealed comparison are identical to the experiment's, with the same 195 held moments and the same sealed id digest.
- **It runs on a record that isn't the original:** `make_synthetic.py`'s seeded home, as one session and as two.
- **Model judges are not part of it.** The experiment's depth grades and its hybrid-retrieval comparison used model judges calibrated on the operator's grades. Those steps aren't in the kit, so the depth and hybrid findings aren't predictions here.
