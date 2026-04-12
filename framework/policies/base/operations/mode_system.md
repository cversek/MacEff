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

At each gate point, a **Markov state machine recommender** suggests which work mode to transition to next. The current work mode is the Markov state; the transition matrix determines the probability distribution for the next state.

The recommender:
1. Reads the **current work mode** (the Markov state)
2. Looks up the **transition row** for that state
3. Applies **operational mode modifiers** (USER_IDLE, LOW_CONTEXT) then renormalizes
4. Performs **Monte Carlo sampling** from the modified distribution
5. Maps the selected work mode to its **motivation skill**
6. Presents the recommendation to the agent via systemMessage
7. Agent performs **ULTRATHINK deliberation** and invokes the skill (or overrides with justification)

### Transitions Are Skill Invocations

**A transition into a different work mode MUST invoke a motivation skill.** The Markov model selects the transition; the skill IS the transition action.

**Skill naming convention**:
```
/{agent_prefix}-{adjective}-self-motivation

/ctb-exploratory-self-motivation       → DISCOVER 🔍
/ctb-generative-self-motivation        → BUILD 🔨
/ctb-curative-self-motivation          → CURATE 📋
/ctb-consolidative-self-motivation     → CONSOLIDATE ✍️

Framework defaults (agents without custom skills):
/maceff-exploratory-self-motivation
/maceff-generative-self-motivation
/maceff-curative-self-motivation
/maceff-consolidative-self-motivation
```

**Resolution order**: Agent-specific (`/ctb-*`) overrides framework default (`/maceff-*`). Each agent can customize their skill's reflection questions, task creation patterns, and domain preferences.

**Each skill's job**:
1. Set the work mode (emit `work_mode_change` event)
2. Perform mode-specific ULTRATHINK reflection (different questions per type)
3. Create scoped tasks from the reflection
4. Return control to the agent loop

**Existing `/{agent}-reflexive-self-motivation`**: General-purpose fallback for MANUAL_MODE or when no Markov transition is active.

### Agent Interaction Protocol

**Recommendations are serious suggestions, not commands.** The agent:
- **Takes recommendations seriously** — they encode the productive workflow rhythm
- **Overrides when justified** — counter-choices MUST be justified in task notes
- **Doesn't follow blindly** — contextual awareness may outweigh the stochastic suggestion

This creates accountability without rigidity. The Markov model guides; the agent decides.

### Gate Point Flow

```
Stop hook gate fires (scope or timer)
  ↓
Current work mode: DISCOVER 🔍
  ↓
Look up transition row for DISCOVER:
  → BUILD: 0.45, CURATE: 0.25, DISCOVER: 0.20, CONSOLIDATE: 0.10
  ↓
Apply operational mode modifiers (e.g., LOW_CONTEXT boosts CURATE/CONSOLIDATE)
  ↓
Monte Carlo sample → selected: BUILD 🔨
  ↓
systemMessage to agent:
  "Recommended transition: DISCOVER → BUILD (p=0.45)
   Invoke: /ctb-generative-self-motivation
   Full distribution: BUILD 0.45 | CURATE 0.25 | DISCOVER 0.20 | CONSOLIDATE 0.10
   Override requires justification in task notes."
  ↓
Agent ULTRATHINK: "I've accumulated findings for 90 minutes.
  BUILD is the natural next step — I'll prototype the transcript monitor."
  ↓
Agent invokes: Skill(skill: "ctb-generative-self-motivation")
  ↓
Skill executes: sets BUILD 🔨, reflects on what to build, creates tasks
```

### The Monte Carlo "Spice"

The Markov transition matrix encodes the natural productivity cycle (DISCOVER → BUILD → CURATE → CONSOLIDATE → DISCOVER), but the stochastic element means the agent won't always follow the most probable path. Occasionally the sampler suggests an unexpected transition — and that unexpected suggestion may be exactly what breaks a semantic rut.

**Epsilon exploration**: With probability ε (default 0.05), the recommender ignores the transition matrix entirely and picks uniformly at random. This is the "wild card" — 1 in 20 gate points produces a completely unexpected suggestion.

---

## 8. The Markov Transition Model

### Architecture: Simple Implementation, Flexible Foundation

The recommender uses a **Markov transition matrix** over work modes. The current work mode determines the probability distribution for the next work mode. This is intentionally simple — a 4×4 matrix — but the architecture supports:

- **Per-agent tuning**: Different agents can curate different matrices that match their workflow
- **Sprint-type profiles**: A "research sprint" matrix might bias toward DISCOVER, while a "shipping sprint" biases toward BUILD
- **Evolving probabilities**: Values below are **initial examples**, expected to be tuned through experimentation
- **Additional work modes**: New rows/columns added as the mode vocabulary grows

### Transition Matrix (example values — subject to experimental tuning)

P(next_work_mode | current_work_mode):

```
                 → DISCOVER  → BUILD  → CURATE  → CONSOLIDATE
FROM DISCOVER      0.20       0.45     0.25       0.10
FROM BUILD         0.25       0.15     0.45       0.15
FROM CURATE        0.30       0.15     0.15       0.40
FROM CONSOLIDATE   0.50       0.25     0.15       0.10
```

**The natural cycle** (following highest-probability transitions):
```
DISCOVER →(0.45)→ BUILD →(0.45)→ CURATE →(0.40)→ CONSOLIDATE →(0.50)→ DISCOVER
```

**Why this cycle works**: Discovery produces things to build. Building produces things to document. Curating produces things to synthesize. Synthesis generates new questions to explore.

**Self-transitions** (diagonal): Momentum preservation — sometimes you're in flow and should continue.

**Off-diagonal novelty**: Low-probability transitions that break ruts — e.g., DISCOVER → CONSOLIDATE (0.10) = "stop exploring, synthesize what you have."

### Initial Distribution (cold start)

When no current work mode is set (beginning of sprint):
```
DISCOVER: 0.40, BUILD: 0.25, CURATE: 0.20, CONSOLIDATE: 0.15
```

### Operational Mode Modifiers

Modifiers multiply the base transition probabilities, then **renormalize** to sum to 1.0.

| Modifier | DISCOVER | BUILD | CURATE | CONSOLIDATE | Rationale |
|----------|----------|-------|--------|-------------|-----------|
| USER_IDLE | 1.1 | 1.1 | 0.9 | 1.0 | Explore/build freely while user is away |
| LOW_CONTEXT | 0.2 | 0.2 | 1.8 | 1.8 | Preserve wisdom, don't start new things |
| QUIET_MODE | — | — | — | — | No modifier (affects notifications, not strategy) |

Multiple modifiers multiply sequentially, renormalize once at the end.

### Configuration Schema

Stored in `.maceff/mode_transitions.json` (per-agent, extensible):

```json
{
  "schema_version": "1.0",
  "profile": "default",
  "transitions": {
    "DISCOVER":     {"DISCOVER": 0.20, "BUILD": 0.45, "CURATE": 0.25, "CONSOLIDATE": 0.10},
    "BUILD":        {"DISCOVER": 0.25, "BUILD": 0.15, "CURATE": 0.45, "CONSOLIDATE": 0.15},
    "CURATE":       {"DISCOVER": 0.30, "BUILD": 0.15, "CURATE": 0.15, "CONSOLIDATE": 0.40},
    "CONSOLIDATE":  {"DISCOVER": 0.50, "BUILD": 0.25, "CURATE": 0.15, "CONSOLIDATE": 0.10}
  },
  "initial": {"DISCOVER": 0.40, "BUILD": 0.25, "CURATE": 0.20, "CONSOLIDATE": 0.15},
  "modifiers": {
    "USER_IDLE":   {"DISCOVER": 1.1, "BUILD": 1.1, "CURATE": 0.9, "CONSOLIDATE": 1.0},
    "LOW_CONTEXT": {"DISCOVER": 0.2, "BUILD": 0.2, "CURATE": 1.8, "CONSOLIDATE": 1.8}
  },
  "epsilon": 0.05,
  "skill_map": {
    "DISCOVER": "exploratory-self-motivation",
    "BUILD": "generative-self-motivation",
    "CURATE": "curative-self-motivation",
    "CONSOLIDATE": "consolidative-self-motivation"
  }
}
```

**Profile support**: The `profile` field enables agents to maintain multiple matrices:
- `"default"` — general-purpose sprint
- `"research"` — biased toward DISCOVER and CONSOLIDATE
- `"shipping"` — biased toward BUILD and CURATE
- `"closeout"` — biased toward CURATE and CONSOLIDATE

Agents select profiles at sprint start or let the recommender use the default.

**Skill map**: Maps work modes to skill name suffixes. The recommender prepends the agent prefix (e.g., `ctb-`) or framework prefix (`maceff-`) to form the full skill name.

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
