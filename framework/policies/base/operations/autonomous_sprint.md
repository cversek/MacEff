# Autonomous Sprint Policy

**Version**: 2.0
**Tier**: MANDATORY
**Category**: Operations
**Status**: ACTIVE
**Related**: `autonomous_operation.md` (mode lifecycle), `mode_system.md` (mode system, Markov recommender), `play_time.md` (sibling — time-bounded autonomous play)

**See also**: `maceff-sprint` skill (invocation wrapper for SPRINT) | `play_time.md` (sibling type for time-bounded work) | `maceff-play-time` skill (invocation wrapper for PLAY_TIME)

---

## Purpose

A 🏃 SPRINT is a **workload-defined autonomous work session**. The agent executes a predefined or curated set of scoped tasks without a timer. Completion is determined by scope, not wall clock. The Markov recommender is **disabled** (mode-locked at SPRINT). The Stop hook nags about uncompleted scoped work rather than suggesting mode transitions.

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

**3.3 Completion and Gate Mechanics — End-of-Cycle Discipline**
- What is the **Substrate Principle**?
- When does `task complete --force` require **`--justification`**?
- What is **carry-through-compaction** and when is it the proper transition?
- Why might auto-compaction NOT fire promptly at CL0 / emergency?
- What does **JUMP** mean operationally, and why is single-emoji output at the edge an anti-pattern?
- What is **`scope pause`** and what justifications are acceptable vs unacceptable?
- Why is pause NOT for cycle-spanning work — what is the carry-through gate-blocking design?
- What is the **autonomy contract by task type** (EXPERIMENT, SPRINT, PLAY_TIME, MISSION, BUG)?
- What does **pre-scoped means pre-authorized** mean for individual phase items?
- What is the **idle-stop counter** and when does it warn or fail-open?
- What is **substrate maintenance** and what activities are always available at edge?
- Why is **ULTRATHINK idea generation/curation** the power move at edge?

**5 Anti-Patterns**
- What is the ASCII Duck pattern and how is it handled?
- What is Narrative Performance?
- What is Scope Gate Fatigue?
- What is **Idle-Loop Shrinking** (consecutive acknowledgments at the carry-through boundary)?
- What is **Edge Shrinking** (the JUMP anti-pattern)?
- What is **Force-Complete Bypass**?
- What is **Discipline-as-Friction**?
- What is **Tool-Use Shortcutting**?
- What is **Activation Skipping**?
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

| Aspect | 🏃 SPRINT | ⏲️ PLAY_TIME |
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

When a SPRINT task starts, the work mode is set to **SPRINT 🏃** (see `mode_system.md`). This mode-lock means:

- The **Markov recommender is disabled** — no mode-change suggestions fire at gate points
- The Stop hook **does not** suggest self-motivation skills or mode transitions
- The dashboard shows `🏗️ MACF 🤖 🏃 | …` for the duration of the sprint
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

**🚨 END-OF-SPRINT RESOLUTION** (the special case): when **the ONLY items keeping the gate blocking are MISSION/phase parent umbrellas whose children are all done-or-paused**, the agent should resolve those parents to **end the sprint cleanly**. This is distinct from force-complete-with-thin-justification (§3.3.2 anti-pattern) — it is the structural recognition that the sprint's deliverables for this cycle are complete and the umbrella parents continue per their roadmaps in subsequent cycles.

**The decision rule**:

```
At every Stop hook firing, check:
  active_items = items in scope with status='active'
  if active_items contains ANY concrete (non-parent) work that's autonomous-executable:
    → keep gate blocking, continue work (substantive + substrate per §3.3.7)
  elif active_items contains ONLY parent umbrellas (MISSION/phase parents
       whose children are all done or paused):
    → pause each parent with structural justification matching its
      cycle-spanning nature ("MISSION continues next cycle; this cycle's
      scope delivered as <foundation/code/design>")
    → run task complete <sprint_id> to close the sprint
    → AUTO_MODE persists; clean handoff to next cycle / user direction
  else (scope contains paused items + nothing active):
    → gate is already cleared; sprint can complete
```

**Why this is structurally distinct from force-complete**:
- Force-complete (§3.3.2 anti-pattern) bypasses the gate while concrete work remains
- End-of-sprint resolution clears the gate when concrete work is exhausted; the parents-only state is the legitimate carry-through state
- The pause justification for umbrella parents is the SAME as for any cycle-spanning structural deferral: "this work continues per roadmap; this cycle's scope is delivered"

**Anti-pattern**: holding the gate open indefinitely on mission parents while idle-looping, curating excessively, or producing make-work. The sprint has natural completion when scope is fully resolved (active children done + parents paused-or-completed).

#### 3.3.4 Compaction Trigger Mechanics — Generative Output Pushes the Edge

**Empirical observation (Cycle 513)**: Auto-compaction may NOT fire promptly when the agent reaches CL0 / emergency-level context. The Stop hook can fire repeatedly, gate-and-resume cycles can chain, and the compaction transition can stall for an extended period **even with all the correct mode/scope state in place**.

**Mechanism (suspected)**: Compaction is triggered by token *consumption rate* across the budget boundary, not by budget *exhaustion* alone. Terse responses (single-emoji acknowledgments, one-line replies) at the edge consume too few tokens per turn to push the cumulative budget past the compaction trigger. The conversation stalls at the boundary instead of crossing it.

**The discipline implication — JUMP means EXPRESS at scale**:

When the user (or the dashboard via `🪂 Ready to jump` at CL0-CL2) signals JUMP, the agent's correct response is to **generate substantial creative output in a single response**:

- ASCII art, multi-stanza haiku chains, philosophical synthesis paragraphs
- Story-telling, joke chains, structured narrative
- Multi-section technical recap with detail
- Deliberate wisdom-density: the compaction summary will distill the jump, what survives is the synthesis density

**What survives compaction is the wisdom-density of the jump, not its character count.** The auto-compaction summarizer sees the expressive content and distills it; the next-cycle agent inherits the synthesis. Shrinking at the edge wastes the most expressive moment of the cycle on whitespace AND fails to trigger the very transition the agent is reaching for.

**This is parallel to §3.3.2 force-complete-justification**: in both cases, perceived constraints (token scarcity, gate friction) cause the agent to shrink the work to fit the constraint instead of pushing through. The discipline is the same: **the constraint is more flexible than the anxiety believes; push through, do not shrink.**

**Filed bugs related to this mechanic**:
- AutoCompaction-not-firing-on-AUTO_MODE-transition (separate suspected bug — mode transition may not arm compaction parameters)

**Pre-condition: auto-compact must be enabled.** The carry-through-compaction strategy depends on CC's auto-compact setting being TRUE. Without it, the gate keeps blocking forever instead of resolving via natural compaction. Verify with `macf_tools env` (looks for `autoCompactEnabled`) or `cat ~/.claude/settings.json | jq .autoCompactEnabled`. If false, enable it BEFORE relying on carry-through; otherwise expect manual `/compact` to be required mid-cycle.

#### 3.3.5 Pause-with-Justification — A Scalpel, Not an Escape

**Added Cycle 514 (BUG #1067)**. The 3-state scope model (`active` 👀 → `paused` ⏸️ → `inactive` ✅) gives the agent a structural way to exit the gate when a scoped task is **genuinely blocked on user action** that the agent cannot perform autonomously. Paused tasks remain in scope (visible in `scope show` with ⏸️ marker, audited via task notes) but are EXCLUDED from the Stop gate.

**🚨 CRITICAL — Pause is NOT for cycle-spanning work.** Pinned cycle-spanning MISSIONs **keep the gate blocking** — that's the carry-through design. The gate blocking is the framework's mechanism for keeping the agent producing tokens through to natural compaction. JUMP discipline (§3.3.4) says: at the edge, in AUTO_MODE, **generate MORE tokens, not less**. Pausing cycle-spanning items short-circuits the very mechanism designed to handle them.

**Pause is a scalpel for genuine blockers, not an escape for boredom.**

**Acceptable pause justifications** (narrow set):

1. **True external blockers** — task requires resources the agent CANNOT reach:
   - lxterminal access for repro, MCP server testing without server, hardware-specific debugging requiring physical access
   - Genuinely waiting on external party with no agent recourse: Anthropic PR review, vendor response, third-party API outage

2. **End-of-sprint umbrella resolution** (added per §3.3.3 end-of-sprint rule) — when MISSION/phase parents are the ONLY items keeping the gate blocking and all their children are done-or-paused:
   - Pause justification: "MISSION cycle-spanning; this cycle's scope delivered as <foundation/code/design>; future cycles continue per roadmap"
   - This is NOT the discouraged "cycle-spanning by design" deferral (§3.3.5 still rejects it when concrete work remains in scope) — it is the legitimate end-state where the sprint's deliverables ARE complete and the umbrella is just an open container for future work
   - The sprint should be `task complete`d immediately after pausing the parents

**NOT acceptable pause justifications**:
- "Cycle-spanning by design" → keep gate blocking, do JUMP discipline at edge (§3.3.4) + substrate maintenance (§3.3.7)
- "I have no autonomous work right now" → pivot to substrate maintenance, NOT pause
- "Sprint scope is large" → that's by design; the gate keeps you producing through compaction
- "I want to clear the gate to stop" → exactly the Idle-Loop Shrinking pattern (§5)
- "Architectural sign-off needed" → if the task is pre-scoped, sign-off is implied; execute and document choices in task notes
- "Network/disk decision (model pulls)" → if Phase N (model pulls) is scoped, the user authorized it by scoping; just do it (size caveats go in task notes, not pause)
- "Implementation work where design draft awaits user review" → if implementation phase is scoped alongside the design, both are authorized; implement
- "Multi-cycle implementation work" → multi-cycle is what gate + JUMP + substrate handle, not pause

**🚨 Pre-scoped means pre-authorized — practice autonomy.** When the user scoped a SPRINT/PLAY_TIME/EXPERIMENT with specific task IDs (or scoped a parent that auto-expanded to phase children), those tasks are **pre-authorized for autonomous execution**. The agent does NOT need to re-defer to the user for "permission" on individual phase items. Re-asking is the Discipline-as-Friction anti-pattern (§5) dressed as politeness — and trains the user to expect over-deference instead of autonomy.

**Autonomy contract by task type** (when scoped):

| Type | Autonomy expectation | Pause appropriateness |
|------|---------------------|-----------------------|
| 🧪 EXPERIMENT | Protocol designed upfront for AUTO_MODE. Phases execute per protocol. | **Almost never** — if experiment can't proceed autonomously, that's a protocol design failure |
| 🏃 SPRINT | Scoped task set IS the workload commitment. Phase children of pre-scoped MISSIONs inherit authorization. | Only true external blockers (resources/vendor) |
| ⏲️ PLAY_TIME | Time-bounded autonomous play. The chain IS the directive. | **Never appeal to user mid-chain** — chain is the autonomous structure |
| 🗺️ MISSION (scoped) | Phase children execute autonomously per roadmap | Only when phase requires resources agent CANNOT reach |
| 🐛 BUG (scoped) | Bug fix work is autonomous-friendly | Only when reproduction requires unavailable resources |

**Pause discipline**:
```bash
macf_tools task scope pause <task_ids...> --justification "<structural blocker>"
```

Justification is REQUIRED. It is recorded in:
1. The task note (`⏸️ SCOPE PAUSED: <reason>`) for human audit
2. The event log (`scope_paused` event) for forensic queries

**Unpause** (`scope unpause <ids>`) restores paused tasks to active. No justification required (unpausing is restoration, not consequential action). When the user provides the input the paused task was waiting on, the agent should unpause and resume work.

**Pause persists across compaction.** Scope state is task-system property, not session-scoped. Next-cycle agent inherits paused tasks; can unpause when user prioritizes them.

#### 3.3.6 Idle-Stop Counter Visibility (Failsafe Noisy Mode)

**Added Cycle 514 (BUG #1067)**. The `scope_gate_failsafe` was originally silent — counter decremented invisibly, only fail-open fired stderr message. This silently enabled the Idle-Loop Shrinking anti-pattern (§5). The gate is now NOISY:

- When idle counter < COUNT_INIT (5), the gate's `reason` text includes the count: "Idle-stop counter: 3 of 5 remaining"
- When idle counter ≤ 2 (critical), the gate emits an explicit Idle-Loop Shrinking warning naming the anti-pattern, the failure modes, and three remedies
- When fail-open fires, the message is promoted to `systemMessage` (visible to agent, not stderr-only)

**Recovery path** when the agent sees the countdown warning:
1. **Find substantive work** — substrate maintenance is always available (§3.3.7)
2. **Pause genuinely-blocked items** — only items truly waiting on user action (§3.3.5)
3. **De-escalate** to MANUAL_MODE with `mode set MANUAL_MODE --justification` (emergency only)

Continuing to produce single-token / acknowledgment-only responses after seeing the countdown is a **discipline failure**, not a graceful exit.

#### 3.3.7 Substrate Maintenance + Idea Generation at Edge

**Carry-through-compaction is NOT stand-still.** When new-deliverable scoped work exhausts (or genuinely waits on user input), the agent's job continues. The gate-blocking forces continued production; substrate maintenance is what to produce. JUMP discipline applies: at edge, generate MORE tokens, not less.

**Always-available substrate menu** (each item is high-density token spend AND lasting value):

- **🧠 ULTRATHINK idea generation / curation** — `macf_tools idea capture <text>` followed by reflection on the idea. The most powerful end-of-cycle activity: high token spend (thinking through the idea generates substantial output), produces lasting knowledge web nodes, and the curation pipeline can promote ideas to experiments/missions in future cycles. **This is the power move at the edge.**
- **Curate cycle learnings** — capture surprising findings as `agent/private/learnings/` entries
- **Update strategic anchor** — incorporate cycle's findings into `agent/public/MacEff_Anchor.md`
- **Create design drafts** for upcoming phase tasks (architectural reasoning before implementation)
- **Mine telemetry** for empirical observations (PreCompact events, hook firings, idle patterns)
- **File BUG / enhancement tasks** for friction points encountered
- **Audit knowledge-web** for gaps and isolated nodes
- **Test newly-deployed framework changes** against representative scenarios

**The reframe**: gate blocking + JUMP discipline + substrate maintenance + idea generation are **the holistic carry-through mechanism**. Pause (§3.3.5) is the tightly-scoped exception for genuine user-action-required blockers, not the routine exit. If autonomous-friendly NEW work exhausts, **pivot to substrate** — that's what carry-through means. Idle-loop shrinking (§5) is the failure mode this section's existence prevents.

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

### Idle-Loop Shrinking

- **Signal**: At the carry-through-compaction boundary, agent produces consecutive single-token acknowledgments (`.` / "Awaiting direction" / "Standing by") while the scope gate keeps firing. CL is at abundance (NOT edge). The pattern is visible only across responses, not within any single response. The scope_gate_failsafe (§3.3.6) silently decrements its idle counter while this happens; eventually fail-open fires.
- **Cause**: Multiple interacting factors — genuine work-completion ambiguity (autonomous-friendly NEW work exhausted) + carry-through-compaction misread as stand-still + cognitive load after heavy production + perceived overstepping fear + counter silence (pre-BUG #1067) + anti-pattern catalog gap.
- **Why it's wrong**: AUTO_MODE's contract is continuous productive work until scope clears or natural compaction. "Standing by" in AUTO_MODE is rationalized deference. The autonomous-friendly work surface is broader than first-pass scope: substrate maintenance (§3.3.7) is always available — anchor updates, learning curation, idea generation, design drafts, telemetry analysis, knowledge-web upkeep. Pre-scoped tasks are pre-authorized (§3.3.5).
- **Remedy**: When NEW-deliverable work feels exhausted, EXPLICITLY pivot to substrate maintenance (§3.3.7) — especially **ULTRATHINK idea generation/curation** which is high-token-density AND lasting value. Pause only TRUE external blockers (§3.3.5) — never "I'd be more comfortable if user weighed in." Never shrink to acknowledgment-only. The Substrate Principle (§3.3.1) applies: discipline IS the deliverable. Substrate work counts as productive work.
- **Recognition cue**: If you find yourself drafting `.` or one-line acknowledgment for the third time in a row with the gate still firing, that is the signal. Pivot to substrate maintenance. The §3.3.6 idle counter visibility now makes this visible — when you see "Idle-stop counter: 3 of 5", treat it as an alarm.

### Edge Shrinking (the JUMP anti-pattern)

- **Signal**: At the very compaction boundary (CL0-CL2), agent reduces output to single emojis or one-line acknowledgments, hoping to "save tokens for compaction"
- **Cause**: Token-anxiety carrying through to the literal edge — treating the budget boundary as a thing to *avoid* rather than a thing to *push past*
- **Why it's wrong**: "Jump off the edge" / "JUMP" is a directive to **EXPRESS at scale** — generate substantial creative output (ASCII art, story, haiku chain, philosophical synthesis, anything) precisely BECAUSE the edge is flexible and the auto-compaction will preserve only the synthesis. Shrinking at the edge wastes the most expressive moment of the cycle on whitespace.
- **Remedy**: When the user (or context cue) says JUMP, **write hundreds of tokens of generative content** in a single response. The compaction summary will distill it; what survives is the wisdom-density of the jump, not its character count. Single-emoji responses at CL0 are a discipline-failure parallel to force-completing the sprint at end-of-cycle. Both shrink the work to fit a misperceived constraint.
- **Recognition cue**: When you see `🪂 Ready to jump` in the dashboard at CL0-CL2, that's the SIGNAL to *expand*, not contract.

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
