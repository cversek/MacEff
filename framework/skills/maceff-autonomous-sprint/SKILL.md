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

### Timed vs Untimed Sprints

**Timed sprint** — user specifies a time period ("work for 2 hours", "45 min sprint"):
- Exploratory, experimental, self-motivated
- Markov recommender guides mode transitions at gate points
- Timer enforces wind-down discipline
- Work may shift domains as curiosity guides

**Untimed sprint** — user specifies a workload ("finish MISSION #983", "complete these phases"):
- Defined deliverables, scope completion discipline
- Stop when all scoped work is done (scope gate clears naturally)
- Less self-motivation needed — work is predefined
- NO timer — only set `--timer` when the user explicitly gives a time

**CRITICAL**: Only use `--timer` when the user specifies a time period. NEVER invent a timer for workload-defined sprints.

### Scope Setup

```bash
# Timed sprint (user said "work for 2 hours"):
macf_tools task scope set <task_id> --timer 120

# Untimed sprint (user said "finish this MISSION"):
macf_tools task scope set <task_id>
```

**Verify TM is running** (should be auto-started from Step 1):
```bash
macf_tools transcript-monitor status
```

**Document sprint start** in task notes:
```bash
macf_tools task note <id> "Sprint launched at <time>. Goal: <description>."
```

---

## Step 5: Begin Work

### Untimed Sprint (Workload-Defined)

Work through scoped tasks systematically. Complete each task the moment its work finishes:

```bash
macf_tools task complete <id> --report "..."
```

Completed tasks auto-clear from scope. When all scoped tasks are completed, the scope gate clears and stop is allowed. AUTO_MODE persists until user returns.

**The natural flow**: Work → complete task immediately → next task → complete → ... → all scope cleared → stop allowed.

### Timed Sprint (Time-Bounded)

The two-gate stop mechanism governs the lifecycle:

**Scope gate + Timer gate**: Both must clear before stopping.

- **Timer active, last task remaining**: Timer gate blocks completion and fires Markov recommender for continuation guidance.
- **Timer expired, scope active**: Complete the task with a report to clear scope gate.
- **Both cleared**: Stop is allowed. AUTO_MODE persists until user returns.

**Non-last task completions proceed freely** — no Markov, no gate. The Markov recommender ONLY fires when attempting to complete the last scoped task while the timer is active.

**Detailed task notes throughout**: During the timed continuation period, document your activity with work mode prefix at each turn: `DISCOVER: explored X`, `CURATE: documented Y`. This creates the forensic trail of the sprint.

**When your current mode runs out of steam**: Attempt to complete the last scoped task. The timer gate fires the Markov recommender, suggesting a new work mode and self-motivation skill. Invoke the suggested skill to find fresh direction. This is the DESIGNED transition mechanism — don't power through exhausted curiosity, let the recommender redirect you.

### Common Discipline (Both Modes)

**Task note discipline** (REQUIRED):
- Prefix all notes with work mode: `DISCOVER: analyzed v2.1.109 strings`
- Document ideas as task notes, not formal idea CAs: `DISCOVER: idea — REPL registerTool for dynamic tools`
- After sprint, curate ideas from notes with user guidance

**NO new task creation** in AUTO_MODE unless the user directs it. Activity goes in task notes on the scoped task.

**NEVER use `scope clear`** to exit a sprint. It triggers a permissions prompt (halts sprint when user is away) and destroys tracking without completion reports. Always complete tasks individually.

---

## Anti-Patterns

- **Inventing a timer for workload sprints**: User said "finish this MISSION" (defined workload) but agent set `--timer 180`. Only use `--timer` when the user explicitly specifies a time period. Workload sprints end when scope clears naturally.
- **Emergency de-escalation as wind-down**: Using `macf_tools mode set MANUAL_MODE` to stop — that's for emergencies only
- **Scope stretching**: Padding work to avoid hitting the timer gate — complete honestly, let Markov guide the next activity
- **Idea CA creation during sprint**: Creating formal idea JSON files — use task notes instead, curate with user later
- **Using `scope clear` to bypass**: `scope clear` triggers a permissions prompt (halts sprint when user is away) and destroys tracking without completion reports. ALWAYS use `task complete` per-task.
- **Batching completions**: Waiting until all work is done to complete tasks in bulk. Complete each task the moment its work finishes.

---

**This skill chains**: `maceff-auto-mode` (authorization + TM start) → session restart → `autonomous_sprint` policy (sustainability) + `mode_system` policy (recommender). All needed for a well-governed sprint.
