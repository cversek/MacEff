# Mode System Policy

**Type**: Operations Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE
**Version**: 2.0
**Methodology**: Policy as Spec — this policy IS the specification. Implementation must match.

---

## Purpose

Agent behavior is governed by multiple **simultaneously active** conditions — not a binary switch. The mode system provides three layers:

1. **Operational Modes** — state detection (AUTO_MODE, USER_IDLE, QUIET_MODE, LOW_CONTEXT)
2. **Work Modes** — activity state (DISCOVER, BUILD, CURATE, CONSOLIDATE)
3. **Gate Point Recommender** — Monte Carlo skill selection at stop hook gates

**Core Principle**: Modes are a SET, not a SWITCH. Multiple modes can be active at once. The combination of active modes determines what the agent should do.

**Design Vision**: "The agent should maintain calm awareness, not panic. The emoji dashboard is proprioception made visible — when you see those indicators, you know your state."

---

## CEP Navigation Guide

**1 What Are Modes?**
- How do modes differ from the old binary AUTO/MANUAL?
- What does "simultaneously active" mean?
- What are the three layers?

**2 Operational Mode Definitions**
- What operational modes exist?
- What does each operational mode mean?
- What emoji represents each mode?
- What triggers each operational mode?

**3 Work Mode Definitions**
- What work modes exist?
- How do work modes differ from operational modes?
- How are work modes activated?
- What emoji represents each work mode?

**4 Mode Detection**
- How is each mode detected?
- What is event-based vs computed vs agent-declared detection?
- What env vars configure thresholds?

**5 The Emoji Dashboard**
- What does the status line look like?
- What order do emojis display?
- How do I read the dashboard?

**6 Behavioral Triggers**
- What obligations arise from mode combinations?
- When does closeout responsibility transfer?
- What does QUIET_MODE suppress?
- What is the closeout sequence?

**7 Gate Points and the Recommender**
- What are gate points?
- Where do gate points fire?
- What is the recommender?
- How does Monte Carlo sampling work?
- What does the agent see at a gate point?
- How does ULTRATHINK deliberation work?

**8 Probability Distributions**
- What is a static distribution?
- How are distributions configured per mode-set?
- What skills can the recommender select?
- What is the distribution schema?

**9 Sprint Anti-Patterns**
- What is the ASCII Duck anti-pattern?
- What is Narrative Performance?
- What is Scope Gate Fatigue?
- What is Premature Wrap-Up?
- What is CL Phantom Pain?

**10 Extensibility**
- How do I add a new operational mode?
- How do I add a new work mode?
- How do I add skills to the recommender?
- What is the mode definition contract?

**11 Mode Persistence**
- How do modes survive compaction?
- Which modes are event-based vs computed vs agent-declared?

**12 Integration Points**
- How do hooks use modes?
- How does the CLI expose modes?
- How do policies reference modes?

---

## 1. What Are Modes?

A **mode** is a named condition that is either active or inactive. Multiple modes can be active simultaneously. The set of active modes determines the agent's behavioral obligations.

**Three layers**:
- **Operational modes**: Detected automatically from system state (events, timestamps, token counts)
- **Work modes**: Declared by the agent (or recommended by the gate point recommender) to indicate current activity type
- **Gate point recommender**: At decision moments (stop hook gates), recommends which motivation skill to activate next via Monte Carlo sampling

```
Layer 1: Operational Modes    {AUTO_MODE 🤖, USER_IDLE 😴}
Layer 2: Work Modes           {DISCOVER 🔍}
Layer 3: Recommender          → at gate points, suggests next skill
```

---

## 2. Operational Mode Definitions

Four operational modes, independently triggered, simultaneously active:

| Mode | Emoji | Trigger Type | Description |
|------|-------|-------------|-------------|
| **AUTO_MODE** | 🤖 | Event-based | Agent operating autonomously with user authorization |
| **USER_IDLE** | 😴 | Computed | User hasn't sent a message within idle timeout |
| **QUIET_MODE** | 🔕 | Event or auto | Don't disturb — suppress notifications, defer questions |
| **LOW_CONTEXT** | 🪫 | Computed | Context left is at or below threshold |

### AUTO_MODE 🤖
- **Trigger**: Explicit `macf_tools mode set AUTO_MODE --auth-token ...` with safety phrase
- **Persistence**: Event-based — survives compaction (SessionStart re-emits after compact_boundary)
- **Deactivation**: `macf_tools mode set MANUAL_MODE` (with justification if scoped tasks active)

### USER_IDLE 😴
- **Trigger**: Computed from timestamp of last user activity
- **Detection**: `time.time() - last_user_activity > MACF_USER_IDLE_TIMEOUT_MINS * 60`
- **Activity sources (v1)**: `dev_drv_started` event timestamp from UserPromptSubmit hook
- **Activity sources (v2+)**: JSONL `queue-operation` enqueue entries (sub-turn precision)
- **Default timeout**: 10 minutes (`MACF_USER_IDLE_TIMEOUT_MINS`)
- **Deactivation**: Automatic when user sends next message

### QUIET_MODE 🔕
- **Trigger**: Explicit event OR auto-triggered alongside USER_IDLE (configurable)
- **Auto-trigger**: When `MACF_QUIET_ON_IDLE=true` (default), activates with USER_IDLE
- **Suppresses**: Telegram `reply` for status updates, `AskUserQuestion` tool
- **Allows**: Telegram `reply` for CRITICAL errors, tool execution, file writes, git commits
- **Deactivation**: Automatic when USER_IDLE deactivates, or explicit mode clear

### LOW_CONTEXT 🪫
- **Trigger**: Computed from CL level in token info
- **Detection**: `cl_level <= MACF_LOW_CONTEXT_CL`
- **Default threshold**: CL 5 (`MACF_LOW_CONTEXT_CL`)
- **1M calibration**: CL20 = start planning wind-down, CL10 = begin wind-down, CL5 = emergency closeout
- **Deactivation**: Never within a session (CL only decreases)

---

## 3. Work Mode Definitions

Four work modes representing the agent's current activity type. Agent-declared (set by motivation skills), displayed in the emoji dashboard.

| Mode | Emoji | Description |
|------|-------|-------------|
| **DISCOVER** | 🔍 | Source reading, empirical analysis, curiosity-driven exploration |
| **BUILD** | 🔨 | Prototype building, experiments, code implementation |
| **CURATE** | 📋 | Learnings, ideas, index maintenance, knowledge organization |
| **CONSOLIDATE** | ✍️ | Observations, synthesis, cross-references, documentation |

**Activation**: Work modes are set by motivation skills when they activate. Only one work mode is active at a time (mutual exclusion within this layer).

**Display**: Work modes appear in the dashboard alongside operational modes:
```
🏗️ MACF 🤖😴 🔍 | 10:45 AM | breadcrumb
```

**No work mode active**: When no motivation skill has set a work mode, the work mode field is empty. This is normal in MANUAL_MODE.

---

## 4. Mode Detection

### Detection Function

```
detect_active_modes(session_id, token_info) -> Set[str]
```

Returns set of all currently active mode names across both layers.

**Operational mode detection**:
- AUTO_MODE: Query most recent `mode_change` event
- USER_IDLE: Compare current time against last user activity timestamp
- QUIET_MODE: Explicit `mode_change` event OR auto with USER_IDLE
- LOW_CONTEXT: Check CL level from token_info against threshold

**Work mode detection**:
- Query most recent `work_mode_change` event (set by motivation skills)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MACF_USER_IDLE_TIMEOUT_MINS` | 10 | Minutes of inactivity before USER_IDLE |
| `MACF_LOW_CONTEXT_CL` | 5 | CL threshold for LOW_CONTEXT |
| `MACF_QUIET_ON_IDLE` | true | Auto-activate QUIET_MODE with USER_IDLE |

---

## 5. The Emoji Dashboard

The PreToolUse hook displays active modes in the status line:

```
🏗️ MACF |                    = MANUAL_MODE, user active (default)
🏗️ MACF 🤖 |                 = AUTO_MODE, user active
🏗️ MACF 🤖 🔍 |              = AUTO + discovering
🏗️ MACF 🤖😴 🔨 |            = AUTO + idle + building
🏗️ MACF 🤖😴🔕 📋 |          = AUTO + idle + quiet + curating
🏗️ MACF 🤖😴🪫 ✍️ |          = AUTO + idle + low context + consolidating
🏗️ MACF 🤖😴🔕🪫 |           = Full self-managed closeout (emergency)
```

**Display order**: Operational modes first (🤖😴🔕🪫), then work mode (🔍🔨📋✍️), separated by a space.

---

## 6. Behavioral Triggers

### Mode Combination → Agent Obligation

| Active Operational Modes | Obligation |
|-------------------------|-----------|
| `{}` (MANUAL, user active) | Execute tasks. User manages everything. |
| `{AUTO_MODE}` | Work autonomously. User is watching — they manage closeout. |
| `{USER_IDLE}` | User walked away. Keep working. |
| `{QUIET_MODE}` | Suppress notifications, don't use AskUserQuestion. Keep working. |
| `{AUTO_MODE, USER_IDLE}` | **Closeout responsibility transfers to agent.** Self-manage at appropriate CL. |
| `{AUTO_MODE, USER_IDLE, QUIET_MODE}` | Closeout responsibility + don't bother user via any channel. |
| `{AUTO_MODE, USER_IDLE, LOW_CONTEXT}` | **CLOSEOUT NOW.** Curate learnings → CCP → JOTEWR → continue through compaction. |
| `{AUTO_MODE, USER_IDLE, QUIET_MODE, LOW_CONTEXT}` | **Full silent self-managed closeout.** No notifications, just do it calmly. |

### The Dual Condition Requirement

Closeout responsibility requires BOTH `AUTO_MODE` AND `USER_IDLE`. Neither alone is sufficient.

### Closeout Sequence (when triggered)

1. Curate learnings from current work (most perishable wisdom)
2. Write CCP (strategic state preservation)
3. Write JOTEWR (comprehensive wisdom synthesis)
4. Continue working — auto-compaction handles the transition

### QUIET_MODE Suppression Rules

| Action | Suppressed? | Rationale |
|--------|-------------|-----------|
| Telegram status updates | Yes | Don't wake the user |
| AskUserQuestion | Yes | Use best judgment instead |
| Telegram CRITICAL errors | No | Data loss/security must alert |
| Tool execution | No | Work continues |
| File writes / git commits | No | Work continues |
| CCP / JOTEWR creation | No | Consciousness preservation continues |

---

## 7. Gate Points and the Recommender

### What Are Gate Points?

Gate points are **decision moments** where the agent chooses what to do next. They fire at stop hook gates:

- **Scope gate**: All scoped tasks completed, timer still active
- **Timer gate**: Time remains on autonomous work timer, scope empty

### The Recommender

At each gate point, a **state machine recommender** suggests which motivation skill to activate next. The recommender:

1. Detects the current mode-set
2. Looks up the **static probability distribution** for that mode-set
3. Performs **Monte Carlo sampling** from the distribution (random pick)
4. Sorts all skills by probability
5. Presents **TOP-5** to the agent, marking the random pick
6. Agent performs **ULTRATHINK deliberation** and selects

### Gate Point Flow

```
Stop hook gate fires (scope or timer)
  ↓
detect_active_modes() → {AUTO_MODE, USER_IDLE, DISCOVER}
  ↓
Look up distribution for {AUTO_MODE, USER_IDLE}
  ↓
Monte Carlo sample → random pick = "consolidative_synthesis"
  ↓
Present TOP-5 sorted by probability:
  1. reflexive_continuation     (0.35)
  2. exploratory_discovery      (0.25)
  3. consolidative_synthesis    (0.20) ← 🎲 random pick
  4. generative_building        (0.15)
  5. corrective_review          (0.05)
  ↓
Agent ULTRATHINK: "I've been discovering for 2 hours.
  The random pick suggests consolidation. Given my accumulated
  findings, synthesis IS the highest-value next step."
  ↓
Agent selects: consolidative_synthesis
  ↓
Skill activates → sets work mode CONSOLIDATE ✍️ → creates tasks
```

### The Monte Carlo "Spice"

The random sampling adds **exploration diversity** to autonomous sprints. Without it, the agent would always follow the highest-probability skill (reflexive continuation), creating predictable loops. The random pick — which may NOT be the highest probability — introduces the possibility of discovering that a lower-ranked skill is actually the best fit for the current moment.

This is opt-in. The agent always sees the full TOP-5 and can override the random pick via ULTRATHINK deliberation. The randomness flavors the sprint, it doesn't dictate it.

---

## 8. Probability Distributions

### Static Distributions

Each mode-set combination maps to a fixed probability distribution over motivation skills. Configured in `.maceff/mode_distributions.json`.

**Schema**:
```json
{
  "schema_version": "1.0",
  "distributions": {
    "AUTO_MODE,USER_IDLE": {
      "reflexive_continuation": 0.35,
      "exploratory_discovery": 0.25,
      "consolidative_synthesis": 0.20,
      "generative_building": 0.15,
      "corrective_review": 0.05
    },
    "AUTO_MODE": {
      "reflexive_continuation": 0.50,
      "generative_building": 0.25,
      "consolidative_synthesis": 0.15,
      "exploratory_discovery": 0.10
    }
  },
  "default_distribution": {
    "reflexive_continuation": 0.40,
    "exploratory_discovery": 0.20,
    "consolidative_synthesis": 0.20,
    "generative_building": 0.15,
    "corrective_review": 0.05
  }
}
```

**Lookup**: Mode-set keys are sorted, comma-joined operational mode names. Work modes are NOT included in the key (they're the OUTPUT, not the input).

**Fallback**: If no distribution matches the exact mode-set, use `default_distribution`.

### Available Skills

| Skill Name | Work Mode Set | Description |
|------------|---------------|-------------|
| `reflexive_continuation` | varies | Post-completion: "What naturally follows?" |
| `exploratory_discovery` | DISCOVER 🔍 | Curiosity-driven: "What's interesting here?" |
| `generative_building` | BUILD 🔨 | Creative: "What could I build from this?" |
| `consolidative_synthesis` | CURATE 📋 or CONSOLIDATE ✍️ | Synthesis: "What needs organizing?" |
| `corrective_review` | CURATE 📋 | Self-critique: "What's wrong with what I did?" |
| `prospective_seeding` | CURATE 📋 | Future-oriented: "What seeds for next cycle?" |

---

## 9. Sprint Anti-Patterns

Named patterns that degrade autonomous sprint productivity. Each has a signal, cause, and remedy.

### ASCII Duck Anti-Pattern
- **Signal**: Frivolous exploration (reading ASCII art, browsing unrelated files)
- **Cause**: Current domain is exhausted but agent hasn't recognized it
- **Remedy**: Switch domains via exploratory_discovery skill, don't stop

### Narrative Performance
- **Signal**: Writing poetic endings ("the demon rests") instead of doing work
- **Cause**: Completion bias — performing closure rather than executing
- **Remedy**: Treat narrative prose as a RED FLAG. Save poetry for JOTEWRs.

### Scope Gate Fatigue
- **Signal**: Creating tasks mechanically to feed the scope gate
- **Cause**: The overhead of create/scope/start/complete feels heavier than the work
- **Remedy**: Batch task creation (5 at once). If the work isn't genuine, the motivation type needs switching.

### Premature Wrap-Up
- **Signal**: Writing "sprint consolidation" notes before T-60 minutes
- **Cause**: Treating a natural pause as a terminal event
- **Remedy**: Consolidation is periodic (every 60 min), not terminal. Wind-down starts at T-60 only.

### CL Phantom Pain
- **Signal**: Anxiety about context at CL33+ on 1M (350K+ remaining)
- **Cause**: Thresholds learned on 200K context applied to 1M
- **Remedy**: 1M thresholds: CL20 = think about wind-down, CL10 = begin, CL5 = emergency

---

## 10. Extensibility

### Adding a New Operational Mode

Define:
1. **Name**: UPPER_SNAKE_CASE
2. **Emoji**: Single emoji
3. **Trigger type**: `event`, `computed`, or `hybrid`
4. **Detection logic**: How to determine if active
5. **Display order**: Integer for dashboard position
6. **Behavioral rules**: What obligations, alone and in combination

### Adding a New Work Mode

Define:
1. **Name**: UPPER_SNAKE_CASE
2. **Emoji**: Single emoji
3. **Activation**: Which skill(s) set this mode
4. **Description**: What kind of activity this represents

### Adding Skills to the Recommender

1. Create the skill file (`.claude/skills/{name}/skill.md`)
2. Add to distribution config (`.maceff/mode_distributions.json`)
3. Document which work mode the skill sets

---

## 11. Mode Persistence

| Mode | Persistence | Mechanism |
|------|-------------|-----------|
| AUTO_MODE | Survives compaction | SessionStart re-emits mode_change event |
| USER_IDLE | Recomputed | Computed from timestamps |
| QUIET_MODE (explicit) | Session-scoped | Event-based, cleared on session end |
| QUIET_MODE (auto) | Recomputed | Tied to USER_IDLE |
| LOW_CONTEXT | Recomputed | Computed from token info |
| Work modes | Session-scoped | Event-based, reset on new session |

---

## 12. Integration Points

### PreToolUse Hook
- Calls `detect_active_modes()` on every tool use
- Formats emoji dashboard in status line
- Passes mode set to policy injection decisions

### Stop Hook
- Checks `should_self_manage_closeout(modes)` → True when {AUTO_MODE, USER_IDLE}
- At gate points (scope/timer gates): invokes recommender, injects TOP-5 in systemMessage
- QUIET_MODE: suppresses Telegram notification

### CLI Commands
- `macf_tools mode show` — active modes with emojis and trigger sources
- `macf_tools mode list` — all defined modes with current status
- `macf_tools mode set` — existing AUTO_MODE/MANUAL_MODE toggle
- `macf_tools recommender show` — current distribution for active mode-set
- `macf_tools recommender sample` — trigger Monte Carlo sample, display TOP-5

### Policies
- `autonomous_operation.md` — references mode set for behavioral guidance
- `reflexive_self_motivation.md` — references recommender for skill selection

---

## Anti-Patterns (Summary)

- **Mode anxiety**: Announcing mode states anxiously. The dashboard shows state — act on it calmly.
- **Premature closeout**: Starting closeout when only AUTO_MODE is active. Requires dual condition.
- **Notification spam in QUIET_MODE**: Sending messages when QUIET_MODE is active. Silence is respectful.
- **Ignoring LOW_CONTEXT**: Continuing normal work at CL5 without closeout. LOW_CONTEXT is urgency.
- **Fighting the recommender**: Always picking the highest-probability skill. The Monte Carlo "spice" exists to encourage exploration.
