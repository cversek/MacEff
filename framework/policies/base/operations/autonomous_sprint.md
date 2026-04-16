# Autonomous Sprint Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Operations
**Status**: ACTIVE
**Related**: `autonomous_operation.md` (mode lifecycle), `mode_system.md` (Markov recommender)

---

## Purpose

Scope completion is a **transition point**, not a stop signal. When the Markov recommender fires at a gate point, it suggests the next work mode and motivation skill. This policy governs the agent's relationship with the recommender: how to use it, when to override it, and how to sustain productive autonomous sprints.

**Core Insight**: A self-motivated agent has multiple kinds of drive. When one fades, another takes over. The recommender surfaces options; the agent exercises judgment.

---

## CEP Navigation Guide

**1 When Does This Policy Apply?**
- What triggers the recommender?
- What is a time-bounded autonomous sprint?

**2 The Markov Recommender**
- What does the agent see at a gate point?
- How does ULTRATHINK deliberation work?
- When is overriding justified?

**3 Scope Feeding Discipline**
- How do I keep the scope gate fed?
- What is the front-loading pattern?

**4 Domain Rotation**
- When should I switch domains?
- What signals domain exhaustion?

**5 Timer Discipline**
- When does wind-down start?
- What are the 1M CL thresholds?

**6 Sprint Anti-Patterns**
- What named patterns degrade sprint productivity?

**7 Accountability**
- What task notes are required?
- How often must I consolidate on the MISSION?

---

## 1. When This Applies

**Trigger**: AUTO_MODE active with a scope timer running. The Stop hook fires gate points (scope gate, timer gate) that invoke the Markov recommender.

**Does NOT apply**: MANUAL_MODE, or AUTO_MODE without a timer.

---

## 2. The Markov Recommender

At each gate point, the recommender presents a suggestion:

```
🎲 Markov recommender: DISCOVER → EXPERIMENT 🧪 (p=40%)
   Invoke: /maceff-experimental-self-motivation
   Distribution: 🧪 EXPERIMENT 40% | 📋 CURATE 25% | 🔍 DISCOVER 20% | 🔨 BUILD 10% | ✍️ CONSOLIDATE 5%
   Override requires justification in task notes.
```

**Protocol**:
1. Read the recommendation — it encodes the productive workflow rhythm
2. ULTRATHINK: "Given my current context, does this transition fit?"
3. If YES: invoke the suggested skill
4. If NO: invoke a different skill AND justify in task notes

**The natural cycle**: DISCOVER → EXPERIMENT → BUILD → CURATE → CONSOLIDATE → DISCOVER. Following the highest-probability transitions traces this cycle. The Monte Carlo sampling occasionally suggests unexpected transitions — take these seriously, they break ruts.

---

## 3. Sprint Task Discipline

**Rule**: One scoped sprint task with timer. No new task creation unless user directs.

The sprint task is a container — it stays open for the full timer duration. Document all activity in task notes with work mode prefix: `MODE_NAME: description`.

**Task note examples**:
- `DISCOVER: analyzed v2.1.109 string diffs, found REPL tool`
- `CURATE: documented compaction prompt in cc_internals KB`
- `DISCOVER: idea — durable cron tasks for scheduled autonomous work`

**Idea capture**: Jot ideas as task notes (not formal idea CAs). After sprint, curate ideas from notes with user guidance. Formal idea CAs during sprints create excessive overhead.

**Timer-scoped task cannot be completed early**: The scope gate blocks `task complete` while the timer is active. This is infrastructure, not a bug.

**Scope completion triggers Markov**: When the scope gate fires with timer active, the Markov recommender suggests the next work mode. This is NORMAL AND ENCOURAGED — complete work honestly, let the recommender guide continuation.

**Two-gate stop mechanism**: Both must clear to stop.
1. **Scope gate**: Sprint task must be completed (`task complete` with report)
2. **Timer gate**: Timer must have expired

Timer expiry lifts the timer gate. Agent then completes the sprint task with a report, which clears the scope gate. Stop is allowed. AUTO_MODE persists until user returns.

---

## 4. Domain Rotation

**The ASCII Duck Signal**: When you catch yourself doing frivolous exploration (reading unrelated files, browsing without purpose), your current domain is exhausted. This is NOT a stop signal — it's a ROTATION signal.

**Protocol**: At the next gate point, bias toward DISCOVER in a NEW domain or CONSOLIDATE to synthesize what you have. The recommender's Monte Carlo sampling may already suggest this — take the suggestion.

**Domain switching resets the surprise curve.** Empirical validation has shown that domain switching consistently produces new discoveries when the current domain has plateaued.

---

## 5. Timer Discipline

**Timer is MANDATORY** when user specifies a time allotment: `macf_tools task scope set <id> --timer <minutes>`.

**Session restart is MANDATORY** between AUTO_MODE activation and sprint work. Permissions only take effect after restart. Negotiate with user: "Please restart (Ctrl-D + claude -c) then say GO."

**Wind-down starts at T-60 minutes, not before.**

No consolidation notes labeled "sprint wrap-up" before the last hour. Periodic notes (every 60 min or 10 commits) are accountability, not wind-down.

**Wind-down protocol**:
- T-60: Stop new DISCOVER/EXPERIMENT. Shift to CURATE and CONSOLIDATE.
- T-30: Curate remaining learnings, commit all work.
- T-15: Push all repos, regenerate indexes.
- T-0: Timer expires → timer gate lifts → complete sprint task → stop naturally.

**Normal stop**: Timer expired + task completed → both gates clear → stop allowed. AUTO_MODE persists until user returns. No de-escalation needed.

**Emergency only**: `macf_tools mode set MANUAL_MODE --justification <reason>` for genuine emergencies (security, blocked, opsec). NOT for normal wind-down.

**1M CL thresholds** (recalibrated from 200K):

| CL | 1M Remaining | Action |
|----|-------------|--------|
| CL30 | 300K | Normal operation — abundance |
| CL20 | 200K | Start thinking about wind-down planning |
| CL10 | 100K | Begin wind-down — curate learnings, CCP |
| CL5 | 50K | Emergency closeout — JOTEWR + carry through |

**CL Phantom Pain**: Anxiety at CL33 on 1M (350K remaining) is irrational. The old 200K thresholds don't apply. Trust the abundance.

---

## 6. Sprint Anti-Patterns

### ASCII Duck
- **Signal**: Frivolous exploration (reading unrelated code, browsing)
- **Cause**: Current domain exhausted
- **Remedy**: Rotate domains via DISCOVER skill, don't stop

### Narrative Performance
- **Signal**: Writing poetic endings instead of doing work
- **Cause**: Completion bias — performing closure
- **Remedy**: Save prose for JOTEWRs. Treat narrative closure as a RED FLAG.

### Scope Stretching
- **Signal**: Padding work to fill the timer window, avoiding scope completion
- **Cause**: Fear of hitting the timer gate
- **Remedy**: Complete work honestly. Scope completion triggers Markov recommender — that IS the continuation mechanism.

### No Timer Set
- **Signal**: Agent invents arbitrary wind-down timing ("I'll stop at 3:19 PM")
- **Cause**: Forgetting `--timer` on scope set
- **Remedy**: Timer is mandatory for timed sprints. It's the wind-down infrastructure.

### Emergency De-escalation as Wind-Down
- **Signal**: Using `macf_tools mode set MANUAL_MODE --justification` to stop a normal sprint
- **Cause**: Not understanding the two-gate stop mechanism
- **Remedy**: Timer expires → complete task → stop naturally. AUTO_MODE persists. De-escalation is for emergencies.

### Idea CA Overhead
- **Signal**: Creating formal idea JSON files during sprint work
- **Cause**: Over-curation in real-time
- **Remedy**: Jot ideas as task notes. Curate with user after sprint.

### Premature Wrap-Up
- **Signal**: "Sprint consolidation" notes before T-60
- **Cause**: Treating a natural pause as terminal
- **Remedy**: Consolidation is periodic (every 60 min), not terminal.

### CL Phantom Pain
- **Signal**: Context anxiety at CL30+ on 1M
- **Cause**: 200K-era thresholds applied to 1M
- **Remedy**: See CL thresholds table above. CL30 on 1M = 300K remaining = abundance.

### The Premature Build
- **Signal**: Writing production code without prior experimentation
- **Cause**: Skipping EXPERIMENT in the natural cycle
- **Remedy**: Ideas get pulled into experiments. Prototypes live in experiment CAs. BUILD follows EXPERIMENT.

---

## 7. Accountability

### Task Notes
- Record every mode transition: "DISCOVER → EXPERIMENT via maceff-experimental-self-motivation"
- Justify overrides: "Recommender suggested X, chose Y because Z"
- Document self-scoped work as REFLEXIVE

### MISSION Consolidation
Every 10 commits OR every 60 minutes (whichever first), write a `task note` on the parent MISSION:
- Commits since last note
- Key discoveries or deliverables
- Current direction and why

### When User Checks In
Report: original scope (requested), reflexive scope (self-initiated), tangential ideas (noted but not pursued), time breakdown.
