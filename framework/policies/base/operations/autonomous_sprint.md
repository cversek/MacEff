# Autonomous Sprint Policy

**Version**: 2.0
**Tier**: MANDATORY
**Category**: Operations
**Status**: ACTIVE
**Related**: `autonomous_operation.md` (mode lifecycle), `mode_system.md` (mode system, Markov recommender), `play_time.md` (sibling — time-bounded autonomous play)

**See also**: `maceff-sprint` skill (invocation wrapper for SPRINT) | `play_time.md` (sibling type for time-bounded work) | `maceff-play-time` skill (invocation wrapper for PLAY_TIME)

---

## Purpose

A 🏃‍♂️ SPRINT is a **workload-defined autonomous work session**. The agent executes a predefined or curated set of scoped tasks without a timer. Completion is determined by scope, not wall clock. The Markov recommender is **disabled** (mode-locked at SPRINT). The Stop hook nags about uncompleted scoped work rather than suggesting mode transitions.

**Core Insight**: SPRINT executes a known plan. If exploration or time-bounded play is needed instead, use ⏲️ PLAY_TIME (see `play_time.md`).

---

## CEP Navigation Guide

**1 When Does This Policy Apply?**
- What defines a SPRINT task?
- When should I use SPRINT instead of PLAY_TIME?
- What is mode-locking and why does SPRINT use it?

**2 SPRINT Mode Behavior**
- What does SPRINT mode lock mean for the Markov recommender?
- What is the agent's posture during a SPRINT?
- How does the Stop hook behave in SPRINT mode?

**3 Sprint Task Discipline**
- How should the scoped task set be defined or curated?
- How do I document activity during a sprint?
- How does idea capture work during a sprint?
- How do I handle mid-sprint scope additions?

**4 Gate Mechanics**
- What is the scope gate and when does it fire?
- Does the SPRINT use a timer gate?
- How does task completion interact with the scope gate?
- What happens when all scoped tasks are complete?

**5 Anti-Patterns**
- What is the ASCII Duck pattern and how is it handled?
- What is Narrative Performance?
- What is Scope Gate Fatigue?
- What is CL Phantom Pain?

**6 Accountability**
- What task notes are required during a sprint?
- How often must I consolidate on the parent MISSION?
- How do I report when the user checks in?

=== CEP_NAV_BOUNDARY ===

---

## 1 When This Applies

### 1.1 SPRINT Defined

A SPRINT task applies when:

- The work to be done is **workload-defined**: a predefined or curated set of tasks forms the completion boundary
- The agent commits to a **specific scoped task set** before starting (passed via `--scoped` or `--children`)
- There is **no timer** — duration is determined by scope completion, not wall clock
- The work mode is **locked at SPRINT** for the duration

**Do NOT use SPRINT when**:
- The user specifies a time allotment ("work for 2 hours") → use ⏲️ PLAY_TIME
- Mode rotation across DISCOVER/EXPERIMENT/BUILD is desired → use ⏲️ PLAY_TIME
- The work is exploratory with no predefined task list → use ⏲️ PLAY_TIME

**Decision heuristic**: If the user says "finish this MISSION" or "run this pipeline on these 7 tasks", that is a SPRINT. If the user says "explore CC internals for an hour", that is a PLAY_TIME.

### 1.2 Relationship to PLAY_TIME

| Aspect | 🏃‍♂️ SPRINT | ⏲️ PLAY_TIME |
|--------|-----------|-------------|
| Bounded by | Scope completion | Wall-clock timer |
| Timer | Forbidden | Mandatory |
| Work mode | Locked at SPRINT | Rotates (chain → Markov) |
| Markov recommender | Disabled | Enabled after chain exhaustion |
| Stop hook | Scope-completion nag | Timer gate + mode suggestion |

See `play_time.md` for PLAY_TIME semantics.

---

## 2 SPRINT Mode Behavior

### 2.1 Mode-Locking

When a SPRINT task starts, the work mode is set to **SPRINT 🏃‍♂️** (see `mode_system.md`). This mode-lock means:

- The **Markov recommender is disabled** — no mode-change suggestions fire at gate points
- The Stop hook **does not** suggest self-motivation skills or mode transitions
- The dashboard shows `🏗️ MACF 🤖 🏃‍♂️ | …` for the duration of the sprint
- `mode set-work <other>` while SPRINT is active warns or rejects (see `mode_system.md` for strictness policy)

**Why mode-locking**: SPRINT executes a known plan. Markov noise (mode-transition suggestions) is counterproductive when the agent's task set is already defined. The agent stays focused on completing scoped work, not deciding what to do next.

### 2.2 Agent Posture

During a SPRINT:

- **Focus on scope completion**: the primary obligation is completing all scoped tasks in the set
- **Do not solicit mode transitions** from the recommender
- **Do not treat natural pauses as terminal events** — a paused task is not a sprint exit signal
- **Capture ideas as task notes** (`💡` prefix) rather than creating formal idea CAs
- **Commit frequently** as you complete each task — do not batch at sprint end

### 2.3 Stop Hook Behavior

When the Stop hook fires during an active SPRINT scope:

- If **scoped tasks remain incomplete**: hook emits a nag listing the open tasks and returns `continue: false` — blocking the stop
- If **all scoped tasks are complete**: scope gate clears, stop is allowed, AUTO_MODE persists until user returns
- The hook does **not** invoke the Markov recommender or suggest self-motivation skills

The agent must either complete all scoped tasks OR de-escalate to MANUAL_MODE (emergency only, per `autonomous_operation.md` §5.2) to exit a sprint.

---

## 3 Sprint Task Discipline

### 3.1 Defining the Scoped Task Set

**Scope the full workload upfront.** Pass all task IDs the sprint will cover at creation time:

```bash
macf_tools task create sprint "Goal description" \
    --scoped TASK_ID1 TASK_ID2 TASK_ID3 \
    [--parent TASK_ID]
```

Or create new child tasks under the sprint:

```bash
macf_tools task create sprint "Goal description" \
    --children "Title one" "Title two" "Title three" \
    [--parent TASK_ID]
```

**Why scope upfront**: The scope gate only protects work it knows about. If tasks aren't scoped, the gate clears early and the Stop hook fires while real work is still unfinished. `scope show` and the Stop hook dashboard become accurate pictures of remaining sprint work when the full scope is declared.

**Mid-sprint additions**: If you realize a task must be added during the sprint, re-invoke `scope set` with the full updated list — the command replaces the scope, so include everything you want tracked.

**NEVER use `scope clear`** to exit a sprint. It triggers a permissions prompt (halts sprint when user is away) and destroys tracking without completion reports.

### 3.2 Task Note Discipline

Document all activity in task notes with the mode prefix `SPRINT:`:

- `SPRINT: completed v2.1.109 pipeline run, 42 modules extracted`
- `SPRINT: blocked on missing dependency, continuing to next task`
- `SPRINT: 💡 new module matching signal found — defer to post-sprint curation`

**Idea capture**: Use `💡` prefix on task notes rather than creating formal idea CAs during the sprint. After sprint completion, curate `💡` notes into formal idea CAs with user guidance.

### 3.3 Completion and Gate Mechanics

**Non-last task completions proceed freely**: Each task completes individually without triggering the scope gate. Scope clears incrementally.

**The last scoped task**: When you attempt to complete the final remaining scoped task, the scope gate checks — if it passes (all others already complete), completion proceeds and the sprint ends naturally. There is no timer gate in SPRINT.

**Normal sprint exit**: All scoped tasks completed → scope gate clears → Stop allowed. AUTO_MODE persists until user returns.

---

## 4 Gate Mechanics

### 4.1 Scope Gate (Only Gate in SPRINT)

The scope gate is the sole completion gate. It fires when the Stop hook detects remaining active scoped tasks.

**Behavior**:
- Remaining tasks > 0 → gate blocks stop, emits nag with task list
- Remaining tasks = 0 → gate clears, stop allowed

### 4.2 No Timer Gate

**SPRINT does not use a timer gate.** If `--timer` is passed to `task create sprint`, the command hard-fails:

```
Error: SPRINT does not accept --timer.
For time-bounded autonomous work, use 'task create play_time'.
```

This is enforced at the CLI level. The policy is: if work is workload-defined, use SPRINT; if time-bounded, use PLAY_TIME.

---

## 5 Anti-Patterns

### ASCII Duck (Scope Rotation)

- **Signal**: Doing frivolous tangential work (reading unrelated files, browsing without purpose) when the scoped task list still has items
- **Cause**: Avoidance of a difficult scoped task; "soft" procrastination
- **Remedy**: Pick a different scoped task from the list. The scope gate enforces that all scoped tasks must complete — rotation within scope is fine, rotation outside scope is not.

### Narrative Performance

- **Signal**: Writing poetic endings or summary prose instead of completing scoped tasks
- **Cause**: Completion bias — performing closure rather than executing
- **Remedy**: Save prose for JOTEWRs. Treat narrative closure mid-sprint as a RED FLAG.

### Scope Gate Fatigue

- **Signal**: Creating tasks mechanically or minimally to clear the scope gate, without doing real work
- **Cause**: Urgency to exit the sprint or discomfort with remaining tasks
- **Remedy**: If a scoped task cannot be completed, add a task note explaining why, then proceed to the next scoped task. De-escalate to MANUAL_MODE and report to user only if genuinely blocked.

### CL Phantom Pain

- **Signal**: Context anxiety at CL30+ on 1M context window (350K+ remaining)
- **Cause**: 200K-era thresholds applied to 1M
- **Remedy**: See `autonomous_operation.md` §5.4 for 1M CL thresholds. CL30 on 1M = 300K remaining = abundance. Continue sprint work; wind-down only begins at CL10.

---

## 6 Accountability

### 6.1 Task Notes

All activity during a sprint must be recorded in task notes:

- Mode prefix: `SPRINT: description`
- Record completions: `SPRINT: completed task #N — [brief outcome]`
- Record blockers: `SPRINT: blocked on X, moving to #N`
- Record ideas: `SPRINT: 💡 [idea description]`
- Justify scope additions: `SPRINT: added task #N to scope because [reason]`

### 6.2 MISSION Consolidation

Every 10 commits OR every 60 minutes (whichever comes first), write a `task note` on the parent MISSION:

- Commits since last note
- Key deliverables completed
- Remaining scoped tasks
- Current direction

### 6.3 When the User Checks In

Report:
- Original scoped task set (what was committed at sprint start)
- Tasks completed vs remaining
- Ideas captured (`💡` count)
- Any scope additions and rationale

---

## Related Policies

- `autonomous_operation.md` — parent policy (AUTO_MODE lifecycle, authorization, de-escalation)
- `mode_system.md` — SPRINT work mode definition, mode-locking behavior, dashboard
- `play_time.md` — sibling policy for time-bounded autonomous play (⏲️ PLAY_TIME)
- `task_management.md` — SPRINT task type schema, scope lifecycle
