---
name: maceff-sprint
description: "USE when launching workload-defined autonomous work. Wraps `task create sprint` with policy-mandated discipline (no timer, scope completion gate, locked SPRINT work mode, scope-completion nag from Stop hook)."
allowed-tools: Bash, Read, Grep, Glob
---

Launch a 🏃 SPRINT — workload-defined autonomous work scoped to a predefined task set.

---

## When to Invoke

- User says "finish this MISSION", "run this pipeline on these N tasks", or names a defined workload
- Work is scope-completion defined, not time-bounded
- Post-compaction recovery when a SPRINT task is still active

**NOT when the user specifies a time allotment** ("work for 2 hours", "explore for an hour") — use `maceff-play-time` instead.

---

## SPRINT vs PLAY_TIME — Decision Heuristic

| Signal | Use |
|--------|-----|
| "Finish these N tasks" / defined workload | 🏃 SPRINT |
| "Work for N hours" / time allotment | ⏲️ PLAY_TIME |
| "Explore X for an hour" / open-ended | ⏲️ PLAY_TIME |
| Mode rotation desired | ⏲️ PLAY_TIME |
| Stay focused on completing a known plan | 🏃 SPRINT |

SPRINT locks the work mode at SPRINT and disables the Markov recommender. If mode rotation or Markov guidance is needed, use `maceff-play-time`.

---

## Prerequisite — User Authorization in the Same Message

Step 1 chains `maceff-auto-mode`, which requires AUTO_MODE authorization keywords in the user's message: the safety phrase plus the literal `AUTO_MODE` keyword. If the `/maceff-sprint` invocation does not include these, the auth gate fires immediately and the sprint stalls until the user re-issues the command with the keywords appended.

**Example invocation that proceeds straight through Step 1**:

> /maceff-sprint <goal description>; YOLO BOZO! AUTO_MODE

If AUTO_MODE is already active in the session (e.g., post-compaction recovery, or a sprint resumed after restart), Step 1 is a no-op verification rather than a fresh authorization — keywords are not required again.

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

> Permissions require session restart. Please restart (`Ctrl-D` then `claude -c`) and say GO to resume the sprint.

Do NOT proceed to Step 3 until the user has restarted and returned. Creating the sprint task is OK, but do not start work.

---

## Step 3: Read Sprint Policy

```bash
macf_tools policy navigate autonomous_sprint
macf_tools policy read autonomous_sprint
```

Extract requirements by answering:
- What defines the scoped task set and how should it be declared?
- How does the scope gate work at task completion?
- What does mode-locking mean for the Markov recommender?
- What does the Stop hook emit when scoped tasks remain?
- What are the named anti-patterns and their remedies?

**Substrate / Gate / Discipline questions** (added after a c_513 force-complete-bypass discipline failure — required reading):

- What is the **Substrate Principle**? Why is sprint discipline framed as substrate, not friction?
- When does `task complete --force` require **`--justification`**? What justifications are acceptable vs unacceptable?
- What is the **carry-through-compaction** pattern? When pinned MISSIONs are in scope, what is the proper end-of-cycle transition — and why is force-complete the wrong exit?
- What note-taking triggers does the policy mark **MANDATORY** (not optional summary)? When the user asks "where are the task notes?" — what does that signal?
- What **dogfooding obligation** does the policy specify when invoking pipeline-style tools? What does shortcutting after stage 1 violate?
- What activation procedures must complete before sprint work begins? What does **formal skill activation** accomplish that policy reading alone cannot?
- What is the **Force-Complete Bypass** anti-pattern? Its relationship to **Discipline-as-Friction**?
- What is **Tool-Use Shortcutting**? When you invoke the first stage of a multi-stage pipeline tool, are you obligated to run the rest of the chain?
- What is **Activation Skipping**? Knowledge vs state — what's the distinction the anti-pattern names?

**Edge / JUMP / Compaction-Trigger questions** (added after a c_513 Edge-Shrinking discipline failure — required reading):

- What is the **Edge Shrinking** anti-pattern? When the dashboard signals an imminent compaction edge, what response does the policy mark as wrong vs right?
- What does **JUMP** mean operationally? How does the policy frame single-emoji output at the edge?
- What does the policy say survives compaction — character count or wisdom-density?
- What does the policy say about auto-compaction firing reliability at low context budget?
- How does the policy relate compaction-trigger mechanics to force-complete-justification discipline?

**Scope Pause / Autonomy / Idle-Loop questions** (added after a c_514 Idle-Loop Shrinking discipline failure — BUG #1067 — required reading):

- What does the policy define as **`scope pause`**? What pause justifications does the policy mark as acceptable vs unacceptable?
- How does the policy treat cycle-spanning work — pause or gate-blocking? Why?
- What pre-conditions does the policy specify for carry-through-compaction to work?
- What does the policy say about scoping as authorization? When the user scopes a task, what does that imply about the agent's autonomy for executing it?
- How does the policy specify the autonomy contract for different scoped task types? What pause appropriateness does it document for each?
- What does the policy mean by **substrate maintenance** during carry-through? What activities does it list as always available?
- How does the policy frame **ULTRATHINK idea generation/curation** at edge?
- What is the **Idle-Loop Shrinking** anti-pattern? What does the policy say the idle-stop counter visibility provides?
- What remedies does the policy specify when the idle-stop counter shows a low count? When is each appropriate?
- How does the policy distinguish pausing a task, completing a task, and de-escalating mode? What structural meaning does each carry?
- What scoped task types does the policy mark as almost never pause-appropriate? Why?
- What does the policy say about the agent's default response when autonomous-friendly new-deliverable work feels exhausted?
- What does the policy say to do when the ONLY items keeping the gate blocking are MISSION or phase parent umbrellas whose children are all done-or-paused? When does ending the sprint cleanly become the right move vs continuing to hold the gate?
- How does the policy distinguish 'cycle-spanning is unacceptable as pause justification' (when concrete work remains) from 'cycle-spanning is acceptable as pause justification' (when only umbrella parents remain)?
- What completes the sprint cleanly after umbrella parents are paused at end-of-sprint?

---

## Step 4: Create the Sprint Task

Pass the full scoped task set at creation time. The scope gate only protects work it knows about — scope the complete workload upfront.

**Scope existing tasks:**

```bash
macf_tools task create sprint "Goal description" \
    --scoped TASK_ID1 TASK_ID2 TASK_ID3 \
    [--parent TASK_ID]
```

**Create new child tasks under the sprint:**

```bash
macf_tools task create sprint "Goal description" \
    --children "Title one" "Title two" "Title three" \
    [--parent TASK_ID]
```

**CRITICAL — no timer:** SPRINT does not accept `--timer`. If `--timer` is passed, the CLI hard-fails with:

```
Error: SPRINT does not accept --timer.
For time-bounded autonomous work, use 'task create play_time'.
```

Do NOT invent a timer for workload-defined work.

**Mid-sprint additions:** If a task must be added during the sprint, re-invoke `scope set` with the full updated list (the command replaces scope, so include everything).

---

## Step 5: Document Sprint Start

```bash
macf_tools task note <sprint_id> "SPRINT: Launched at <time>. Goal: <description>. Scoped tasks: #N, #M, ..."
```

---

## Step 6: Execute — Work Through Scoped Tasks

**Mode is locked at SPRINT 🏃.** The dashboard shows `🏗️ MACF 🤖 🏃 | …` for the duration. The Markov recommender is disabled — no mode-change suggestions fire.

Work through scoped tasks systematically. Complete each task the moment its work finishes:

```bash
macf_tools task complete <id> --report "..."
```

Completed tasks auto-clear from scope. When all scoped tasks are completed, the scope gate clears and stop is allowed. AUTO_MODE persists until the user returns.

**The natural flow:** Work → complete task immediately → next task → complete → ... → all scope cleared → stop allowed.

---

## Task Note Discipline (REQUIRED)

Prefix all notes with `SPRINT:`:

- `SPRINT: completed v2.1.109 pipeline run, 42 modules extracted`
- `SPRINT: blocked on missing dependency, continuing to next task`
- `SPRINT: 💡 new module matching signal found — defer to post-sprint curation`

Capture ideas as `💡` task notes, not formal idea CAs. After sprint completion, curate `💡` notes with user guidance.

**NEVER use `scope clear`** to exit a sprint — it triggers a permissions prompt and destroys tracking without completion reports. Always use `task complete` per-task.

---

## Stop Hook Behavior

When the Stop hook fires during an active SPRINT scope:

- **Scoped tasks remain:** hook emits a nag listing open tasks and blocks the stop (`continue: false`)
- **All scoped tasks complete:** scope gate clears, stop is allowed

The hook does NOT invoke the Markov recommender or suggest self-motivation skills during a SPRINT.

---

## Anti-Patterns

- **Inventing a timer:** user said "finish this MISSION" (workload) but agent set `--timer`. Only PLAY_TIME uses timers.
- **Batching completions:** waiting until all work is done to complete tasks in bulk. Complete each task the moment its work finishes.
- **Scope Gate Fatigue:** completing tasks minimally just to clear the gate. If a task cannot be completed, add a note and move to the next.
- **ASCII Duck (scope rotation outside scope):** doing tangential work when scoped tasks remain. Rotation within scope is fine; rotation outside scope is not.
- **Using `scope clear` to bypass:** destroys tracking without completion reports. Always `task complete` per-task.
- **Idea CA creation during sprint:** use `💡` task notes instead, curate formally after sprint.

---

**Policy reference:** `autonomous_sprint.md` (full behavioral specification)
**Sibling skill:** `maceff-play-time` (time-bounded exploration with Markov rotation)
**This skill chains:** `maceff-auto-mode` (authorization + TM start) → session restart → sprint execution
