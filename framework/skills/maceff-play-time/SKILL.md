---
name: maceff-play-time
description: "USE when launching time-bounded autonomous play with a predetermined work-mode chain. Wraps `task create play_time` with mandatory --timer, optional --chain, T-60 wind-down, and Markov-after-chain-exhaustion."
allowed-tools: Bash, Read, Grep, Glob
---

Launch a ⏲️ PLAY_TIME — time-bounded autonomous exploration with a predetermined work-mode chain and Markov rotation after chain exhaustion.

---

## When to Invoke

- User specifies a time allotment ("work for 2 hours", "explore for an hour", "go play")
- Work is exploratory with no predefined task list
- Mode rotation across DISCOVER/EXPERIMENT/BUILD/CURATE is desired
- Post-compaction recovery when a PLAY_TIME task is still active

**NOT when the user names a defined workload** ("finish these N tasks", "complete this MISSION") — use `maceff-sprint` instead.

---

## PLAY_TIME vs SPRINT — Decision Heuristic

| Signal | Use |
|--------|-----|
| "Explore X for N hours" / time allotment | ⏲️ PLAY_TIME |
| "Work for N hours" / open-ended | ⏲️ PLAY_TIME |
| Mode rotation desired | ⏲️ PLAY_TIME |
| "Finish these N tasks" / defined workload | 🏃 SPRINT |
| Stay focused on completing a known plan | 🏃 SPRINT |

PLAY_TIME follows a predetermined chain, then continues under Markov recommender guidance. If the work is workload-defined and mode rotation is counterproductive, use `maceff-sprint`.

---

## Step 1: Activate AUTO_MODE

Invoke the auto-mode skill for authorization, permissions, and mode switch:

```
Skill(skill: "maceff-auto-mode")
```

---

## Step 2: Session Restart Gate (MANDATORY)

AUTO_MODE permissions only take effect after a CC session restart. Negotiate with the user before proceeding.

**Print this message and STOP:**

> Permissions require session restart. Please restart (`Ctrl-D` then `claude -c`) and say GO to resume the play time.

Do NOT proceed to Step 3 until the user has restarted and returned. Creating the play_time task is OK, but do not start work.

---

## Step 3: Read Play Time Policy

```bash
macf_tools policy navigate play_time
macf_tools policy read play_time
```

Extract requirements by answering:
- What is the predetermined chain and how does it advance?
- When does the Markov recommender engage (chain exhaustion)?
- What is the two-gate stop mechanism (timer gate + scope gate)?
- What is the wind-down sequence and when does it begin?
- What are the named anti-patterns and their remedies?

---

## Step 4: Create the Play Time Task

`--timer` is mandatory. `--chain` is optional (defaults to `[DISCOVER]` if omitted, but declare a meaningful chain for the work).

```bash
macf_tools task create play_time "Goal description" \
    --timer MINUTES \
    --chain MODE1 MODE2 MODE3 \
    [--parent TASK_ID]
```

**Examples:**

```bash
# 60-minute exploration session
macf_tools task create play_time "Explore CC internals for signals" \
    --timer 60 \
    --chain DISCOVER EXPERIMENT CURATE

# 90-minute build session
macf_tools task create play_time "Prototype knowledge web indexer" \
    --timer 90 \
    --chain DISCOVER EXPERIMENT BUILD CURATE
```

**Chain validation:** Each entry must be a valid work mode: `DISCOVER`, `EXPERIMENT`, `BUILD`, `CURATE`, `CONSOLIDATE`. `SPRINT` is not valid in a chain.

If `--timer` is missing, the CLI hard-fails:

```
Error: PLAY_TIME requires --timer.
For workload-defined autonomous work, use 'task create sprint'.
```

---

## Step 5: Document Play Time Start

```bash
macf_tools task note <play_time_id> "PLAY_TIME: Launched at <time>. Timer: <N>min. Chain: <MODE1 → MODE2 → ...>."
```

---

## Step 6: Execute — Predetermined Chain Phase

**Invoke the motivation skill for chain[0]** to set the first work mode and frame the initial activity:

```
# e.g., if chain[0] == DISCOVER:
Skill(skill: "maceff-exploratory-self-motivation")
```

Work within the current chain mode. At the end of each chain mode (scope clear + timer still active):

**Chain advancement:**
1. Stop hook detects scope clear + timer active + chain not exhausted
2. Hook suggests: "Advance chain: `DISCOVER → EXPERIMENT` (chain position 0 → 1)"
3. Invoke the corresponding motivation skill (e.g., `maceff-experimental-self-motivation`)
4. Skill sets the new work mode and creates scoped tasks
5. `chain_position` increments in MTMD

---

## Step 7: Markov Phase (After Chain Exhaustion)

When `chain_position == len(predetermined_chain) - 1` and scope clears, the chain is exhausted (`chain_exhausted: true`). Subsequent gate points invoke the Markov recommender:

```
🎲 Markov recommender: BUILD → CURATE 📋 (p=0.45)
   Invoke: maceff-curative-self-motivation
   Distribution: CURATE 45% | CONSOLIDATE 25% | DISCOVER 20% | BUILD 10%
   Override requires justification in task notes.
```

**Protocol:**
1. Read the recommendation
2. ULTRATHINK: "Given my current context, does this transition fit?"
3. If YES: invoke the suggested skill
4. If NO: invoke a different skill AND justify in task notes

---

## Timer Discipline

**Wind-down begins at T-60 (one hour before timer expires), not before.**

No consolidation labeled "play_time wrap-up" before the last hour. Periodic notes every 60 min or 10 commits are accountability, not wind-down.

**Wind-down sequence:**
- T-60: Stop new DISCOVER/EXPERIMENT. Shift to CURATE and CONSOLIDATE.
- T-30: Curate remaining learnings, commit all work.
- T-15: Push all repos, regenerate indexes.
- T-0: Timer expires → timer gate lifts → complete play_time task → stop naturally.

**Two-gate stop mechanism:** Both gates must clear to stop:
1. **Timer gate:** timer must have expired
2. **Scope gate:** all scoped tasks must be completed

---

## Task Note Discipline (REQUIRED)

Prefix notes with the current work mode:

- `DISCOVER: analyzed v2.1.109 string diffs, found REPL tool`
- `EXPERIMENT: 💡 new module signal — defer to post-sprint curation`
- `CURATE: documented compaction prompt in KB`
- Chain advance: `DISCOVER → EXPERIMENT via chain_advance (chain[0] → chain[1])`
- Markov override: `BUILD: recommender suggested CURATE, chose BUILD because [justification]`

Capture ideas with `💡` prefix. After PLAY_TIME, curate `💡` notes into formal idea CAs with user guidance.

---

## Anti-Patterns

- **Inventing-a-Timer-for-Workload:** using PLAY_TIME for a predefined task list. If work is workload-defined, use `maceff-sprint`.
- **Premature Wrap-Up:** writing "play_time consolidation" notes before T-60. Wind-down starts at T-60 only.
- **ASCII Duck:** frivolous exploration when the current domain is exhausted — rotate domains, don't stop. See domain rotation in `play_time.md` §4.
- **Premature Build:** skipping EXPERIMENT and jumping to BUILD. Ideas get pulled into experiments first.
- **CL Phantom Pain:** context anxiety at CL30+ on 1M (350K remaining = abundance). See `autonomous_operation.md` for 1M thresholds.
- **Narrative Performance:** writing poetic endings instead of doing work. Save prose for JOTEWRs.

---

**Policy reference:** `play_time.md` (full behavioral specification)
**Sibling skill:** `maceff-sprint` (workload-defined execution, no timer, Markov disabled)
**This skill chains:** `maceff-auto-mode` (authorization + TM start) → session restart → chain motivation skills → Markov recommender
