---
name: maceff-autonomous-sprint
description: "Invoke when the user authorizes an autonomous sprint (time-bounded AUTO_MODE work). Activates AUTO_MODE via the auto-mode skill, gates on session restart, reads sprint policy, sets scope with mandatory timer, and prepares the agent for self-directed work with Markov-guided mode transitions."
allowed-tools: Bash, Read, Grep, Glob
---

Launch and sustain an autonomous sprint — time-bounded self-directed work with Markov-guided mode transitions.

---

## When to Invoke

- User authorizes an autonomous sprint ("ride the tsunami", "work for N hours", "GO!")
- User says AUTO_MODE with a time allotment
- Post-compaction recovery when a sprint timer is still active

---

## Step 1: Activate AUTO_MODE

Invoke the auto-mode skill to handle authorization, permissions, and mode switch:

```
Skill(skill: "maceff-auto-mode")
```

Follow its protocol for authorization and activation. AUTO_MODE now auto-starts the Transcript Monitor for idle detection.

---

## Step 2: Session Restart Gate (MANDATORY)

AUTO_MODE permissions only take effect after a CC session restart. You MUST negotiate this with the user before proceeding.

**Print this message and STOP:**

> Permissions require session restart. Please restart (`Ctrl-D` then `claude -c`) and say GO to resume the sprint.

**DO NOT** proceed to Step 3 until the user has restarted and returned. Creating tasks is OK, but do not start work.

---

## Step 3: Read Sprint Policy

```bash
macf_tools policy navigate autonomous_sprint
macf_tools policy read autonomous_sprint
```

Extract requirements by answering:
- What does the policy specify about gate point behavior?
- What interaction protocol does the policy define for recommendations?
- What timer discipline does the policy specify?
- What CL thresholds does the policy define?
- What anti-patterns does the policy name?

---

## Step 4: Set Up Sprint Infrastructure

1. **Scope the sprint task with timer** (MANDATORY for timed sprints):
   ```bash
   macf_tools task scope set <task_id> --timer <minutes>
   ```
   The timer is the wind-down mechanism. Without it, wind-down becomes arbitrary.

2. **Verify TM is running** (should be auto-started from Step 1):
   ```bash
   macf_tools transcript-monitor status
   ```

3. **Document sprint start** in task notes:
   ```bash
   macf_tools task note <id> "Sprint launched at <time>. Timer: <N> min. Goal: <description>."
   ```

---

## Step 5: Begin Work

Work within the scoped task. The two-gate stop mechanism governs the sprint lifecycle:

**Scope gate + Timer gate**: Both must clear before stopping.

- **Timer active, scope active**: Scope gate blocks with Markov recommender. Follow the recommendation to continue productive work.
- **Timer expired, scope active**: Complete the task with a report to clear scope gate.
- **Both cleared**: Stop is allowed. AUTO_MODE persists until user returns.

**Task note discipline** (REQUIRED):
- Prefix all notes with work mode: `DISCOVER: analyzed v2.1.109 strings`
- Document ideas as task notes, not formal idea CAs: `DISCOVER: idea — REPL registerTool for dynamic tools`
- After sprint, curate ideas from notes with user guidance

**NO new task creation** in AUTO_MODE unless the user directs it. Activity goes in task notes on the scoped task.

**Complete tasks immediately as work finishes** — call `macf_tools task complete <id> --report "..."` the moment each task's work is done, not in a batch at the end. The timer gate may show "deferred" but the completion intent is registered. Completed tasks auto-clear from scope. When all scoped tasks are completed, the scope gate clears.

**Trust the deferral**: When the timer gate says "task completion deferred until timer expires", this is the designed behavior — the Markov recommender fires to suggest productive continuation work. Follow the recommendation. Do NOT use `scope clear` to bypass the gate.

**The natural flow**: Work → complete task immediately → Markov fires → follow recommendation → work on next thing → repeat until timer expires or all scope cleared.

---

## Anti-Patterns

- **No timer set**: Inventing arbitrary wind-down timing instead of using `--timer`
- **Emergency de-escalation as wind-down**: Using `macf_tools mode set MANUAL_MODE` to stop — that's for emergencies only
- **Scope stretching**: Padding work to avoid hitting the timer gate — complete honestly, let Markov guide the next activity
- **Idea CA creation during sprint**: Creating formal idea JSON files — use task notes instead, curate with user later
- **Using `scope clear` to bypass timer**: `scope clear` triggers a permissions prompt (halts sprint in AUTO_MODE when user is away) and destroys tracking without completion reports. ALWAYS use `task complete` per-task instead — completions are deferred by the timer gate but properly registered
- **Batching completions**: Waiting until all work is done to complete tasks in bulk. Complete each task the moment its work finishes — this clears scope incrementally and feeds the Markov recommender at each gate point

---

**This skill chains**: `maceff-auto-mode` (authorization + TM start) → session restart → `autonomous_sprint` policy (sustainability) + `mode_system` policy (recommender). All needed for a well-governed sprint.
