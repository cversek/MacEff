# Mode System Policy

**Type**: Operations Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE
**Version**: 2.1
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
- What is the SPRINT work mode and how does it differ from the rotatable modes?
- When is SPRINT mode set and when does it clear?
- What does mode-locking mean for the Markov recommender?

**4 Mode Detection**
- How is each mode detected?
- What is event-based vs computed vs agent-declared detection?
- What env vars configure thresholds?
- What must a detector do when it cannot determine whether a mode applies?

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

**13 Nag Design**
- What distinguishes a nag from a dashboard report?
- What three properties must a nag have?
- Why is habituation the budget a nag spends?
- What should be done about a host's reminders for a capability the framework supersedes?

**14 Modes and Subagents**
- Which modes apply to a subagent, and which belong to the primary alone?
- Why is reading the primary's modes from inside a delegation misleading rather than merely useless?
- Does a subagent declare a work mode, and does the recommender run for it?
- What does a subagent consult in place of the mode set?

=== CEP_NAV_BOUNDARY ===

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

Five operational modes, independently triggered, simultaneously active:

| Mode | Emoji | Trigger Type | Description |
|------|-------|-------------|-------------|
| **AUTO_MODE** | 🤖 | Event-based | Agent operating autonomously with user authorization |
| **USER_IDLE** | 😴 | Computed | User hasn't sent a message within idle timeout |
| **USER_REMOTE** | 📡 | Event + computed clear | User reachable only via a remote channel; CLI unattended |
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

### USER_REMOTE 📡
- **Trigger**: Explicit `macf_tools mode set USER_REMOTE` — the operator declares they have stepped away from the CLI and are reachable **only** through a remote channel (Telegram).
- **Meaning**: The user is *present and responsive*, but the **CLI is unattended**. This is the opposite failure surface from USER_IDLE: the hazard is not that the agent stops, but that it **blocks on a tool needing CLI input nobody is there to give** — a permission prompt, or an `AskUserQuestion` that never renders on the remote channel — and hangs the whole session until the operator physically returns.
- **Deactivation**: **Automatic, the instant the operator sends a message from the CLI** — a `user_activity_detected` event with `source == "direct"`. A message from Telegram (`source == "channel"`) does **not** clear it: the operator is still remote. The Transcript Monitor already records this direct-vs-channel distinction (`detect_user_activity`), so the discriminator is a read, not a new signal.
- **Forbidden while active** (each blocks on the absent CLI):
  - `AskUserQuestion` — its prompt does not propagate to Telegram, so a remote operator can never answer it. Ask in a Telegram `reply`, or in the turn-final message (which the Stop hook forwards to the channel), instead.
  - Every **Ask-list** command (`git push`, `gh pr create`, `gh pr merge`, `gh issue create/close`, `git reset --hard`, `rm -r`, docker teardown, …) — each raises a CLI permission prompt. Accumulate commits locally and **hold pushes/PRs** until USER_REMOTE clears.
- **Enforcement (Ask → Deny)**: activation flips those Ask-list entries to **Deny** and adds `AskUserQuestion` to the deny list, so an attempt returns an *immediate denial the agent can route around* rather than a silent hang; deactivation restores them. Permission changes load at CC startup, so full enforcement takes effect on the **next restart** — until then, the switch message and this policy are the binding guidance. Denial-not-prompt is the safety property: a hung session with a remote operator can only be cleared by their physical return.
- **Allowed**: the Telegram `reply` tool (the operator's live channel — unlike QUIET_MODE, USER_REMOTE does **not** silence Telegram), plus all local work — reads, edits, tests, `git commit`, `macf_tools`.
- **Scope/mode housekeeping — the non-hanging path**: `scope clear` is an Ask-list command (it destroys all scope tracking with no completion reports), so it is **denied** while remote and must not be used. Housekeep with the *incremental, reversible* primitives instead — none are Ask-listed, so they run unattended: `scope remove <ids>` (drop specific entries — how a remote agent heals a stale gate), `scope pause <ids> --justification …` or **`scope pause --all --justification …`** (quiet the whole gate reversibly, with an audit trail), and `scope unpause` to restore. Defer any genuine full `scope clear` until the operator is back at the CLI.
- **vs USER_IDLE / QUIET_MODE**: USER_IDLE = user gone, whereabouts unknown, keep working and assume closeout responsibility. QUIET_MODE = do not disturb on *any* channel. USER_REMOTE = user *here, on Telegram* — talk to them there, but never touch a tool that waits on the empty CLI.

**Switch message** (printed on activation, and the contract an agent must honor):

> 📡 USER_REMOTE active. The operator is reachable ONLY via Telegram; the CLI is unattended. Do NOT use tools that block on CLI input — they will hang the session:
> • AskUserQuestion (does not reach Telegram) → ask via Telegram reply or your turn-final message.
> • Ask-list commands (git push, gh pr create/merge, gh issue create/close, git reset --hard, rm -r, docker teardown) → hold them; accumulate commits locally.
> Communicate via the Telegram reply tool. Clears the instant you send a message from the CLI.

### QUIET_MODE 🔕
- **Trigger**: Explicit event OR auto-triggered alongside USER_IDLE (configurable)
- **Auto-trigger**: When `MACF_QUIET_ON_IDLE=true` (default: false), activates with USER_IDLE. Off by default — idle doesn't mean the user wants silence (they may be monitoring via Telegram).
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

Six work modes representing the agent's current activity type. Agent-declared (set by motivation skills or task lifecycle events), displayed in the emoji dashboard.

| Mode | Emoji | Description | Activation |
|------|-------|-------------|-----------|
| **DISCOVER** | 🔍 | Source reading, empirical analysis, curiosity-driven exploration | Motivation skill |
| **BUILD** | 🔨 | Prototype building, experiments, code implementation | Motivation skill |
| **CURATE** | 📋 | Learnings, ideas, index maintenance, knowledge organization | Motivation skill |
| **CONSOLIDATE** | ✍️ | Observations, synthesis, cross-references, documentation | Motivation skill |
| **EXPERIMENT** | 🧪 | Structured hypothesis-driven investigation | Motivation skill |
| **SPRINT** | 🏃 | Workload-defined autonomous execution (mode-locked) | SPRINT task lifecycle |

### 3.1 Rotatable Modes (DISCOVER, BUILD, CURATE, CONSOLIDATE, EXPERIMENT)

These five modes participate in the Markov transition matrix and can be suggested by the gate point recommender. The agent declares them by invoking the corresponding motivation skill. They rotate freely during ⏲️ PLAY_TIME sessions.

**Activation**: Set by motivation skills when they activate. Only one work mode is active at a time (mutual exclusion within this layer).

### 3.2 SPRINT Mode (Mode-Locked)

**SPRINT 🏃** is a special work mode with different semantics from the five rotatable modes:

- **Derived from SCOPE, not from status**: the mode is in force while a SPRINT task is in **active scope** and `in_progress`. The agent does not invoke a motivation skill to enter SPRINT mode.
- **Set automatically**: creating a sprint scopes the sprint task alongside its workload, and any later `scope set` re-includes a running sprint that the caller omitted.
- **Clears automatically**: when no sprint task remains in active scope. Unscoping releases the lock; completing the sprint does too, by way of leaving scope.

**Why scope and not status.** An earlier version of this policy anchored on task
start and completion, and both failed in practice. A sprint *resumed* rather than
created never fires `task start` — the task is already `in_progress` — so the
mode was never set, which is the normal case after a compaction or an
operator-directed pause. And the mode was observed clearing on unscoping rather
than on completion. A sprint that is `in_progress` with no scope is stopped; one
that is scoped is running. **Status says what a record claims; scope says what is
being worked**, and completion already keys on the same fact.

**Derive, do not store.** The reader prefers the live invariant — a SPRINT task
in active scope forces the mode — and falls back to the last `work_mode_change`
event only when none is found. Scope operations therefore *reconcile* that event
rather than treating it as the source of truth: a second copy of a fact the scope
already holds is free to drift from it, and a stale copy is how a mode-lock
outlives its sprint or a running sprint loses its lock.
- **Markov-locked**: The gate point recommender is **disabled** while SPRINT mode is active. No mode-transition suggestions fire at Stop hook gates.
- **Activates scope nag**: Instead of mode suggestions, the Stop hook emits a scope-completion nag listing remaining scoped tasks.
- **Mode-set restriction**: `mode set-work <other>` while SPRINT is active warns or rejects — open question on strictness: hard-fail vs warn vs convert-to-PLAY_TIME (TODO: resolve in implementation, see roadmap §8 open question 3).

**Why SPRINT is a mode**: The Stop hook reads `current_work_mode` to decide behavior. SPRINT as a mode lets the hook react to a single signal: "is the agent in SPRINT mode? then nag, don't recommend." This is cleaner than threading task-type through every hook check.

**Display**: Dashboard shows `🏃` in the work mode position:
```
🏗️ MACF 🤖 🏃 | 10:45 AM | breadcrumb
```

**Display**: Rotatable work modes appear in the dashboard alongside operational modes:
```
🏗️ MACF 🤖😴 🔍 | 10:45 AM | breadcrumb
```

**No work mode active**: When no motivation skill has set a work mode (and no SPRINT task is active), the work mode field is empty. This is normal in MANUAL_MODE.

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
| `MACF_QUIET_ON_IDLE` | false | Auto-activate QUIET_MODE with USER_IDLE (off by default) |

---

### When a Detector Cannot Tell

A detector reads a record and decides whether a mode applies. Sometimes it can
do neither — the record is unreachable, a scan came back empty, a file is
missing. That is a third answer, and it must not be quietly collapsed into
"the mode does not apply".

It has happened here. `USER_IDLE` read a bounded scan's empty result as
*the user is present*, and the mode silently disengaged while the operator was
away — the more the agent worked, the sooner it cleared, because the agent's own
records buried the evidence. The general form is the compiled-false-absence trap
in `empiricism`; the language-level rule is in the Python coding standards. What
belongs here is the part neither of those can decide: **which way a given mode
should fail.**

**Choose the default by what the mode grants.**

A mode that grants *care* — closer checkpointing, more conservative choices,
preferring to ask — is cheap to enter wrongly and expensive to leave wrongly.
Default toward it when the answer is unknown. `USER_IDLE` is this kind: reading
an absent operator as present costs the whole feature, while reading a present
operator as absent costs a little redundant caution they can correct in one
message.

A mode that grants *authority* — permission to act without confirmation, to skip
a gate, to decide alone — is the reverse. Never enter it on an unknown. An
authority-granting mode must be **positively established**, not inferred from a
failure to find evidence against it.

**State the choice where it is made.** A detector that falls back must say so —
in a comment at minimum, and in a warning when the fallback changes behaviour an
operator would notice. A mode that changes because a lookup failed, with nothing
anywhere recording that it failed, is indistinguishable from a mode that changed
because the world changed. That is the property being protected: an operator
watching the dashboard should never have to wonder whether an emoji reflects
their situation or the reader's reach.

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

The recommender uses a **Markov transition matrix** over the five **rotatable** work modes (DISCOVER, BUILD, CURATE, CONSOLIDATE, EXPERIMENT). **SPRINT mode is excluded from the matrix** — the recommender is disabled when SPRINT is active (see §3.2).

The current work mode determines the probability distribution for the next work mode. This is intentionally simple but the architecture supports:

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
    "CONSOLIDATE": "consolidative-self-motivation",
    "EXPERIMENT": "experimental-self-motivation"
    // SPRINT: not in skill_map — set by task lifecycle, not skill invocation
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
- `autonomous_sprint.md` — SPRINT work mode; mode-locking behavior; scope-nag routing
- `play_time.md` — PLAY_TIME; chain-advance routing; Markov-after-exhaustion
- `reflexive_self_motivation.md` — references recommender for skill selection

---

## 13. Nag Design

A **nag** is any unsolicited message the framework injects into an agent's context to prompt a corrective action — the touch-discipline reminder, the scope gate, the idle-stop counter. It is the same channel as the dashboard: infrastructure telling the agent about its own state. The dashboard reports; a nag asks for something.

That difference is what makes nags expensive. A report costs a glance. A request costs a decision, every time it fires, and an agent that decides "not now" often enough stops deciding at all.

### 13.1 Three required properties

**Computed from observed state, never from a timer.** A nag that fires on elapsed time cannot know whether the thing it is asking for has already happened. It will therefore fire during exemplary behavior, and the agent learns that its own diligence has no effect on the signal.

**Names the specific remedy.** "Consider tracking your progress" costs a decision and supplies nothing to decide with. "Add a note or start the right task" names the two commands that resolve it. The remedy must be an action the agent can take immediately, not a category of virtue.

**Clears on the action.** The agent must be able to make the nag stop by doing the thing. A nag that cannot be satisfied — because nothing the agent is willing to do resets its trigger — is not a reminder, it is a permanent background condition, and the only available response is to tune it out.

Any nag failing one of these should be fixed or removed. Two of three is not a passing grade: a state-derived nag that names no remedy still costs a decision, and a remedy-naming nag on a timer still fires during good behavior.

### 13.2 Habituation is the real budget

The scarce resource is not context space — it is the agent's willingness to read injected messages carefully. Every nag spends from that budget, and the spending is shared: an agent trained by repetition to discount one category of injected message does not keep the discount neatly scoped to the nag that earned it.

So the count matters as much as the quality. Prefer one nag that fires rarely and correctly over three that fire often and approximately. When adding a nag, the question is not "is this useful?" but "is this more useful than the attention it will cost across every future session?"

### 13.3 Foreign nags

A framework that supersedes a host capability inherits the host's reminders about it, and those reminders keep running against a model of the world the framework replaced. They will be timer-driven, they will recommend the superseded surface, and they will be computed from a view of state the framework no longer writes to.

Such a nag cannot be satisfied by good behavior — only silenced. Where the host offers a suppression lever, use it: leaving a permanently-unsatisfiable request in the agent's context spends the habituation budget on nothing. Where it does not, say so plainly in the agent's instructions, because "ignore that one" is a rule an agent can hold, while an unexplained contradiction is one it must re-litigate every time.

Document the mechanism when you find it. A suppression lever discovered and not written down is discovered again by the next agent, at full cost.

---

## Anti-Patterns (Summary)

- **Mode anxiety**: Announcing mode states anxiously. The dashboard shows state — act on it calmly.
- **The unsatisfiable nag**: Shipping a reminder whose trigger no available action resets. It does not change behavior; it trains the agent to skim injected messages.
- **Premature closeout**: Starting closeout when only AUTO_MODE is active. Requires dual condition.
- **Notification spam in QUIET_MODE**: Sending messages when QUIET_MODE is active. Silence is respectful.
- **Ignoring LOW_CONTEXT**: Continuing normal work at CL5 without closeout. LOW_CONTEXT is urgency.
- **Fighting the recommender**: Always picking the highest-probability skill. The Monte Carlo "spice" exists to encourage exploration.

---

## 14. Modes and Subagents

A subagent is not a small primary. Most of the operational modes describe a
relationship between the primary and its operator, and a subagent stands outside
that relationship entirely.

**The mechanical fact that makes this more than a definitional point:** a
subagent runs inside the primary's session and resolves the same session id, so
`mode get` inside a delegation returns the **primary's** modes. Reading them is
therefore not merely uninformative — it is *misleading*, because the values are
real and belong to someone else.

| Mode | Applies to a subagent? |
|------|----------------------|
| **AUTO_MODE** 🤖 | **No — the primary's.** It records that the operator authorised *the primary* to act autonomously. A subagent that reads it sees a true value about a different agent and can mistake it for a licence it was never given. |
| **USER_IDLE** 😴 | **No.** It describes an operator the subagent has no channel to; user communication is not a subagent's to do. Nothing about its behaviour would change if it knew. |
| **USER_REMOTE** 📡 | **The hazard applies; the meaning does not.** "Talk to them on Telegram" is not available to a subagent. "Do not invoke a tool that blocks on CLI input" applies with *more* force: a subagent that hangs on a permission prompt hangs the primary's session too, and the primary cannot see the prompt to answer it. |
| **QUIET_MODE** 🔕 | **No,** with the same caveat: it suppresses notifications a subagent does not send, and defers questions a subagent should not be asking. |
| **LOW_CONTEXT** 🪫 | **Yes, directly.** A subagent has its own context window and its own edge. This is the one operational mode it computes about *itself*, and the one it must act on without consulting anyone. |

### Work modes inside a delegation

A delegation arrives with its purpose already fixed by the delegating agent. The
subagent does not declare a work mode, and **the recommender does not run for
it** — gate points fire in the Stop hook, and a subagent terminates through
SubagentStop, which has no recommender.

This is worth stating rather than leaving to inference, because the absence looks
like an oversight from inside a subagent that knows the recommender exists. It is
deliberate. Recommending a mode transition to an agent whose purpose is fixed and
which is about to terminate would be advice it cannot take.

### What a subagent should do instead

Read the delegation brief. It carries the authorisation, the scope, and the
purpose that the mode set carries for a primary. Where a brief is silent, the
answer is in policy or in the parent's instruction — not in a dashboard reading
that belongs to another agent.

**The reason this section exists in a policy rather than in a preamble's
phrasing:** an agent-facing block that listed five modes a subagent can neither
read nor act on would be worse than no block at all. An instrument that cannot be
acted on teaches its reader to discount instruments, and the dashboard is the one
thing the framework most needs an agent to keep trusting.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — the mode
     set, the Markov recommender, the dashboard, and nag design. -->

[[modes]] [[autonomy]] [[observability]] [[supervision]]
