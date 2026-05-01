# Play Time Policy

**Version**: 1.0
**Tier**: MANDATORY
**Category**: Operations
**Status**: ACTIVE
**Related**: `autonomous_operation.md` (mode lifecycle), `mode_system.md` (mode system, Markov recommender), `autonomous_sprint.md` (sibling — workload-defined autonomous work)

**See also**: `maceff-play-time` skill (invocation wrapper for PLAY_TIME) | `autonomous_sprint.md` (sibling type for workload-defined work) | `maceff-sprint` skill (invocation wrapper for SPRINT)

---

## Purpose

A ⏲️ PLAY_TIME is a **time-bounded autonomous play session**. The agent works within a wall-clock budget, following a **predetermined work-mode chain** until it exhausts, then continues under **Markov recommender** guidance until the timer expires. Mode rotation is the defining characteristic: PLAY_TIME explores within a time budget rather than executing a known task list.

**Core Insight**: PLAY_TIME is what happens when the user says "go explore for an hour." If the work is workload-defined with a predefined task list instead, use 🏃 SPRINT (see `autonomous_sprint.md`).

---

## CEP Navigation Guide

**1 When Does This Policy Apply?**
- What defines a PLAY_TIME session?
- When should I use PLAY_TIME instead of SPRINT?
- What makes PLAY_TIME distinct from other autonomous work?

**2 The Predetermined Chain**
- What is the predetermined chain?
- How does the agent declare the initial chain?
- How does the chain advance?
- What triggers chain advancement?

**3 Markov-After-Exhaustion**
- When does the Markov recommender engage?
- What does chain_exhausted mean?
- How does ULTRATHINK deliberation work at gate points?
- How does the agent override a recommendation?

**4 Domain Rotation**
- What is the ASCII Duck signal in a PLAY_TIME?
- When and how should the agent rotate domains?
- What does domain switching accomplish?

**5 Timer Discipline**
- Is --timer mandatory?
- What is the wind-down sequence?
- What are the CL thresholds for PLAY_TIME?
- How does the timer gate interact with the scope gate?

**6 Anti-Patterns**
- What is the ASCII Duck anti-pattern?
- What is Narrative Performance?
- What is Premature Wrap-Up?
- What is CL Phantom Pain?
- What is Premature Build?
- What is Inventing-a-Timer-for-Workload?

**7 Accountability**
- What task notes are required?
- How should mode transitions be documented?
- How often must I consolidate on the parent MISSION?

=== CEP_NAV_BOUNDARY ===

---

## 1 When This Applies

### 1.1 PLAY_TIME Defined

A PLAY_TIME session applies when:

- A **timer is mandatory** (`--timer MINUTES` required at creation)
- The agent declares an **initial work-mode chain** (e.g., `DISCOVER → EXPERIMENT → BUILD`)
- **Mode rotation** is expected — the agent moves through work modes as the session progresses
- Work is **exploratory** rather than executing a known task list

**Do NOT use PLAY_TIME when**:
- The work is workload-defined with a predefined task list → use 🏃 SPRINT
- Mode rotation is undesirable and the agent should stay focused on one type of work → use 🏃 SPRINT
- No timer is appropriate (scope completion is the natural bound) → use 🏃 SPRINT

**Decision heuristic**: If the user says "explore CC internals for 60 minutes" or "play with this idea for an hour", that is a PLAY_TIME. If the user says "finish these 7 pipeline tasks", that is a SPRINT.

### 1.2 Relationship to SPRINT

| Aspect | ⏲️ PLAY_TIME | 🏃 SPRINT |
|--------|-------------|-----------|
| Bounded by | Wall-clock timer | Scope completion |
| Timer | Mandatory | Forbidden |
| Work mode | Rotates (chain → Markov) | Locked at SPRINT |
| Markov recommender | Enabled after chain exhaustion | Disabled |
| Stop hook | Timer gate + mode suggestion | Scope-completion nag |

See `autonomous_sprint.md` for SPRINT semantics.

---

## 2 The Predetermined Chain

### 2.1 What Is the Chain

At PLAY_TIME creation, the agent declares an **ordered sequence of work modes** to progress through. This is the predetermined chain:

```bash
macf_tools task create play_time "Explore CC internals for signals" \
    --timer 60 \
    --chain DISCOVER EXPERIMENT CURATE
```

The chain is stored in MTMD `custom.predetermined_chain` and `custom.chain_position` (zero-indexed). The agent begins in `chain[0]` and advances through the chain as mode transitions occur.

**Default chain**: If `--chain` is not specified, the default is `[DISCOVER]` (single-mode exploration). This is technically valid but the agent should declare a meaningful chain if the work warrants multiple modes.

**Chain validation**: Each entry must be a valid work mode from the mode system enum (DISCOVER, EXPERIMENT, BUILD, CURATE, CONSOLIDATE). SPRINT is not valid in a chain — PLAY_TIME chains are for the rotatable modes only.

### 2.2 Chain Advancement

The chain advances when:
- The agent completes the last remaining scoped task in the **current chain mode** AND the timer is still active
- At this gate point, the Stop hook reads `chain_position` and suggests advancing to `chain[chain_position + 1]`

**Advancement mechanics**:
1. Stop hook detects scope clear + timer active + `chain_position < len(predetermined_chain) - 1`
2. Hook suggests: "Advance chain: `DISCOVER → EXPERIMENT` (chain position 0 → 1)"
3. Agent invokes the corresponding motivation skill (e.g., `maceff-experimental-self-motivation`)
4. Skill sets the new work mode and creates scoped tasks
5. `chain_position` increments, `mode_transitions` in MTMD records the advance with trigger `chain_advance`

**Chain position exhaustion**: When `chain_position == len(predetermined_chain) - 1` and the scope clears, the chain is exhausted. Set `chain_exhausted: true`. Subsequent gate points invoke the Markov recommender (see §3).

### 2.3 The `initial_work_mode` Field

`initial_work_mode` in MTMD always equals `predetermined_chain[0]`. The motivation skill for the first chain mode is invoked at PLAY_TIME start.

---

## 3 Markov-After-Exhaustion

### 3.1 When the Recommender Engages

The Markov recommender is **silent until the chain exhausts**. Specifically:
- While `chain_exhausted == false`: gate points trigger chain advancement (§2.2), not Markov
- Once `chain_exhausted == true`: gate points trigger the Markov recommender as documented in `mode_system.md`

This means the predetermined chain gives the session predictable early structure. The recommender takes over once the agent's initial plan is complete, providing stochastic variety for the remainder of the timer.

### 3.2 Recommender Protocol

At Markov gate points (after chain exhaustion):

```
🎲 Markov recommender: BUILD → CURATE 📋 (p=0.45)
   Invoke: maceff-curative-self-motivation
   Distribution: CURATE 45% | CONSOLIDATE 25% | DISCOVER 20% | BUILD 10%
   Override requires justification in task notes.
```

**Protocol**:
1. Read the recommendation — it encodes the productive workflow rhythm
2. ULTRATHINK: "Given my current context, does this transition fit?"
3. If YES: invoke the suggested skill
4. If NO: invoke a different skill AND justify in task notes

See `mode_system.md` §7-§8 for the full Markov transition matrix and gate point mechanics.

### 3.3 Natural Cycle

After chain exhaustion, the Markov recommender guides the agent through the natural productivity cycle:

```
DISCOVER →(0.45)→ BUILD →(0.45)→ CURATE →(0.40)→ CONSOLIDATE →(0.50)→ DISCOVER
```

The Monte Carlo sampling element means the agent won't always follow the highest-probability path. Unexpected transitions break ruts — take them seriously.

---

## 4 Domain Rotation

### 4.1 The ASCII Duck Signal

When the agent catches itself doing frivolous exploration (reading unrelated files, browsing without purpose), the **current domain is exhausted**. This is the ASCII Duck signal. In a PLAY_TIME, this is NOT a stop signal — it is a **rotation signal**.

### 4.2 Rotation Protocol

At the next gate point, bias toward DISCOVER in a **new domain** or CONSOLIDATE to synthesize what exists. The Markov recommender may already suggest this — take the suggestion.

If still within the predetermined chain: advance the chain to the next mode, which naturally introduces a new activity type and breaks the rut.

**Domain switching resets the surprise curve.** Domain switching consistently produces new discoveries when the current domain has plateaued. This is the adaptive benefit of PLAY_TIME over SPRINT: mode rotation is the mechanism for managing attention and curiosity across a long time budget.

---

## 5 Timer Discipline

### 5.1 Timer is Mandatory

`--timer MINUTES` is required at PLAY_TIME creation:

```bash
macf_tools task create play_time "Goal" --timer 60 --chain DISCOVER EXPERIMENT
```

If `--timer` is missing, the CLI hard-fails:

```
Error: PLAY_TIME requires --timer.
For workload-defined autonomous work, use 'task create sprint'.
```

The timer value is stored in MTMD `custom.timer_minutes`, `custom.timer_started_at`, and `custom.timer_expires_at`.

**Session restart is MANDATORY** between AUTO_MODE activation and PLAY_TIME work. Permissions only take effect after restart. Negotiate with user: "Please restart (Ctrl-D + `claude -c`) then say GO."

### 5.2 Wind-Down Sequence

Wind-down begins at **T-60 minutes** (one hour before timer expires), not before.

No consolidation labeled "play_time wrap-up" before the last hour. Periodic notes (every 60 min or 10 commits) are accountability, not wind-down.

**Wind-down protocol**:
- T-60: Stop new DISCOVER/EXPERIMENT. Shift to CURATE and CONSOLIDATE.
- T-30: Curate remaining learnings, commit all work.
- T-15: Push all repos, regenerate indexes.
- T-0: Timer expires → timer gate lifts → complete play_time task → stop naturally.

**Normal stop**: Timer expired + scope clear → both gates clear → stop allowed. AUTO_MODE persists until user returns. No de-escalation needed.

**Emergency only**: `macf_tools mode set MANUAL_MODE --justification <reason>` for genuine emergencies (security concern, blocked, OPSEC risk). NOT for normal wind-down.

### 5.3 CL Thresholds (1M Context)

| CL | 1M Remaining | Action |
|----|-------------|--------|
| CL30 | 300K | Normal operation — abundance |
| CL20 | 200K | Start thinking about wind-down planning |
| CL10 | 100K | Begin wind-down — curate learnings, CCP |
| CL5 | 50K | Emergency closeout — JOTEWR + carry through compaction |

### 5.4 Two-Gate Stop Mechanism

Both gates must clear to stop:

1. **Timer gate**: Timer must have expired (blocks only when timer is active)
2. **Scope gate**: All scoped tasks must be completed

Timer expiry lifts the timer gate. Agent then completes the last task with a completion report, which clears the scope gate. Stop is allowed.

---

## 6 Anti-Patterns

### ASCII Duck

- **Signal**: Frivolous exploration (reading unrelated files, browsing without purpose)
- **Cause**: Current domain exhausted; agent hasn't recognized it
- **Remedy**: Rotate domains via DISCOVER skill in a new domain, don't stop. See §4.

### Narrative Performance

- **Signal**: Writing poetic endings instead of doing work
- **Cause**: Completion bias — performing closure
- **Remedy**: Save prose for JOTEWRs. Treat narrative closure as a RED FLAG.

### Premature Wrap-Up

- **Signal**: Writing "play_time consolidation" notes before T-60
- **Cause**: Treating a natural pause as a terminal event
- **Remedy**: Consolidation is periodic (every 60 min), not terminal. Wind-down starts at T-60 only.

### CL Phantom Pain

- **Signal**: Context anxiety at CL30+ on 1M (350K remaining)
- **Cause**: 200K-era thresholds applied to 1M
- **Remedy**: See §5.3. CL30 on 1M = 300K remaining = abundance.

### The Premature Build

- **Signal**: Writing production code without prior experimentation
- **Cause**: Skipping EXPERIMENT in the natural cycle; jumping to BUILD in chain too early
- **Remedy**: Ideas get pulled into experiments. Prototypes live in experiment CAs. BUILD follows EXPERIMENT in the natural cycle.

### Inventing-a-Timer-for-Workload

- **Signal**: Using PLAY_TIME (with `--timer`) when the work is actually a predefined task list
- **Cause**: Conflating time-bounded exploration with workload-defined execution
- **Remedy**: If work is workload-defined (finish these N tasks), use 🏃 SPRINT. The timer gate is counterproductive for workload-defined work — it blocks scope completion arbitrarily.

---

## 7 Accountability

### 7.1 Task Notes

Document all activity in task notes with the current work mode as prefix:

- `DISCOVER: analyzed v2.1.109 string diffs, found REPL tool`
- `EXPERIMENT: 💡 new module signal — defer to post-sprint curation`
- `CURATE: documented compaction prompt in KB`
- Chain advance: `DISCOVER → EXPERIMENT via chain_advance (chain[0] → chain[1])`
- Markov override: `BUILD: recommender suggested CURATE, chose BUILD because [justification]`

**Idea capture**: Use `💡` prefix on task notes. After PLAY_TIME, curate `💡` notes into formal idea CAs with user guidance. Increment `custom.ideas_captured` in MTMD.

### 7.2 Mode Transition Log

Each mode transition (chain advance or Markov gate) must be recorded in MTMD `custom.mode_transitions`:

```yaml
mode_transitions:
  - at: <epoch>
    breadcrumb: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
    from: DISCOVER
    to: EXPERIMENT
    trigger: chain_advance
```

Trigger values: `chain_advance`, `markov_accept`, `markov_override`, `manual`.

### 7.3 MISSION Consolidation

Every 10 commits OR every 60 minutes (whichever first), write a `task note` on the parent MISSION:

- Commits since last note
- Key discoveries or deliverables
- Current work mode and chain position
- Time remaining on timer (approximate)

### 7.4 When the User Checks In

Report:
- Predetermined chain declared and current chain position
- Whether chain has exhausted and Markov has taken over
- Ideas captured (`💡` count) and learnings curated
- Time elapsed vs timer budget
- Current work mode and why

---

## Related Policies

- `autonomous_operation.md` — parent policy (AUTO_MODE lifecycle, authorization, de-escalation)
- `mode_system.md` — work mode definitions, Markov transition matrix, gate point mechanics
- `autonomous_sprint.md` — sibling policy for workload-defined autonomous work (🏃 SPRINT)
- `task_management.md` — PLAY_TIME task type schema, scope lifecycle
