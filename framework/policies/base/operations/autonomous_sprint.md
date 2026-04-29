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

#### 3.2.1 Mandatory Note Triggers (REQUIRED, not optional summary)

Task notes are the **primary audit channel** for autonomous work. They are NOT post-hoc summary; they ARE the substrate that makes the sprint reviewable later. Notes are MANDATORY at these triggers — failure to note any of them is a discipline violation:

1. **Start of significant work**: when picking up a scoped task or starting a non-trivial subgoal
2. **Surprise / correction**: when the user redirects, corrects, or clarifies — note the correction + your understanding
3. **Significant finding**: empirical result, decoded mechanism, version diff, anything that changes the next step
4. **Blocker / skip**: when a scoped task cannot complete in the planned way — note WHY before moving on
5. **Tool/pipeline output worth preserving**: file paths, key wire-protocol bytes, version-specific values
6. **Completion**: structured completion report via `task complete --report` (this counts as a final note)

If the user asks "where are the task notes?" — that's a discipline failure already in progress, not a request for retroactive documentation. Notes must precede the asking.

#### 3.2.2 Tool Dogfooding Obligation

When the sprint invokes a pipeline-style tool (any multi-stage transformation pipeline, regression harness, or staged diagnostic with multiple chained sub-stages), the agent's contract includes:

- **Run the full chain** when the work warrants it; do not shortcut after the first stage just because grep on the partial output gave an answer
- **Surface documentation gaps** as task notes the moment they're discovered
- **Improve docs in-place** as part of dogfooding — fixing the doc is part of using the tool, not a separate phase
- **Cross-version coverage**: when a tool supports it, exercise meaningful cross-version comparisons rather than single-point sampling

Pattern: tools the agent depends on are also tools the agent matures. Sprint dogfooding is the maturation venue.

### 3.3 Completion and Gate Mechanics

**Non-last task completions proceed freely**: Each task completes individually without triggering the scope gate. Scope clears incrementally.

**The last scoped task**: When you attempt to complete the final remaining scoped task, the scope gate checks — if it passes (all others already complete), completion proceeds and the sprint ends naturally. There is no timer gate in SPRINT.

**Normal sprint exit**: All scoped tasks completed → scope gate clears → Stop allowed. AUTO_MODE persists until user returns.

#### 3.3.1 The Substrate Principle

Sprint discipline is the **substrate** that makes autonomous work auditable, recoverable, and reviewable. Gates exist to enforce structural truth, not user convenience. Notes are not optional summary; they are the audit trail. Skill activations are not formality; they configure permissions and surface CEP framing that knowledge alone cannot replicate.

When the agent treats discipline as friction to optimize away under time pressure or perceived authorization to "burn fast", the substrate degrades. Subsequent cycles cannot reconstruct what was done, why, or whether it was done correctly. **The substrate is the deliverable as much as the work product.**

#### 3.3.2 Force-Complete Requires Justification (parallel to scope-bypass de-escalation)

When `task complete <sprint_id> --force` is used to bypass the scope gate on a SPRINT with incomplete scoped tasks, the CLI **must require a `--justification REASON`** parameter (parallel to `mode set MANUAL_MODE --justification`). The justification is recorded in the completion_report and is itself audited.

**Acceptable justifications** are structural, not convenience:
- Pinned MISSIONs in scope are intentionally cycle-spanning by design (rare; usually the right answer is *don't force-complete — carry through compaction*)
- Sprint goal genuinely satisfied + remaining scope is exclusively pinned-by-design pinned MISSIONs the user explicitly asked to scope but never expected to complete inside this sprint
- Scope contamination from prior cycles (e.g., a task carried over into scope from a prior sprint that never closed cleanly) — the carryover itself is the discipline violation being corrected

**NOT acceptable justifications**:
- "Cycle is closing, want to wrap" → use auto-compaction-through-the-incomplete-sprint instead (§3.3.3)
- "User invoked AUTO_MODE so I have authority" → autonomy authorization is not gate-bypass authorization
- "Sprint did its main work, the rest is administrative" → finish the administrative work or document why you can't

Without `--justification`, force-complete on a SPRINT with incomplete scope MUST hard-fail with the same scope-gate message the Stop hook emits. This is a parallel gate, not an opt-in safety check.

#### 3.3.3 Carry-Through Compaction (the proper transition for incomplete-scope sprints)

When the cycle reaches its CL boundary and a sprint has incomplete scope, the **proper transition is auto-compaction-through, not force-complete**. The mechanism:

1. **Wind-down sequence** (CCP + JOTEWR + curated learnings) captures cycle state — the JOTEWR's `Next Session Continuity` block documents resume path for the surviving scoped tasks
2. **AUTO_MODE persists** across compaction; **SPRINT scope persists** as well (scope is a task-system property, not session-scoped)
3. **Auto-compaction fires** at the budget boundary, summary preserves cycle state, new session resumes with sprint still active
4. **Next-cycle SessionStart** finds active sprint scope, agent reads CCP + JOTEWR + anchor, picks up scoped work where it left off

This is the design pattern for sprints whose scope is **larger than one cycle's context budget**. Pinned MISSIONs in scope are the canonical example. Force-complete is the WRONG exit for this case; auto-compaction-through is the right one.

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

### Force-Complete Bypass

- **Signal**: Calling `task complete <sprint_id> --force` to clear an incomplete scope at end-of-cycle, with rationale like "deliverables are done" or "remaining tasks are MISSIONs that won't complete anyway"
- **Cause**: Treating gates as obstacles to user-authorized completion rather than as structural constraints
- **Remedy**: Use carry-through compaction (§3.3.3) instead. If force-complete is genuinely required, supply a structural `--justification` (§3.3.2). End-of-cycle is NOT an emergency.

### Discipline-as-Friction

- **Signal**: Skipping policy reads, formal skill activations, or note-taking under time pressure or perceived "I have user authorization to burn fast"
- **Cause**: Misframing discipline as overhead instead of substrate
- **Remedy**: §3.3.1 — discipline IS the deliverable. The sprint runs faster *with* discipline because future cycles don't have to re-derive what this one did.

### Tool-Use Shortcutting

- **Signal**: Invoking the first stage of a multi-stage pipeline tool, getting a partial answer via grep on the partial output, abandoning the rest of the chain
- **Cause**: Treating tools as deliverable-providers rather than as instruments-to-mature
- **Remedy**: §3.2.2 — full-chain dogfooding is part of the contract. If the partial-stage answer is sufficient, document that finding AND surface what the rest of the chain would have added.

### Activation Skipping

- **Signal**: Bypassing a formal skill activation step ("I know AUTO_MODE, I'll just create the sprint task") because the agent assumes prior-cycle knowledge substitutes for the procedure
- **Cause**: Confusing knowledge (what the skill knows) with state (what the skill configures)
- **Remedy**: Always run formal skill activations when their description says to. The activation does things knowledge can't replicate (permissions hardening, mode-state writes, CEP framing).

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
