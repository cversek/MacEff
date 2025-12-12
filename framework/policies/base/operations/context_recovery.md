# Context Recovery Policy

**Version**: 1.0
**Tier**: MANDATORY
**Category**: Recovery
**Status**: ACTIVE
**Updated**: 2025-12-06
**Dependencies**: checkpoints.md, todo_hygiene.md

---

## Policy Statement

This policy governs recovery from context loss events. Different context loss scenarios require different recovery protocols based on what information remains accessible.

---

## CEP Navigation Guide

**1 Recovery Type Classification**
- What types of context loss exist?
- How do I identify which type occurred?
- What information is available in each type?

**2 Compaction Recovery**
- What is compaction?
- What context survives compaction?
- What recovery protocol applies?

**3 Mindwipe Recovery**
- What is mindwipe (/clear)?
- How does mindwipe differ from compaction?
- What recovery protocol applies?

**4 Virgin Transplant Recovery**
- What is virgin transplant?
- Why is it identical to mindwipe?
- What bootstrap steps are required?

**5 Multi-Explore CA Pattern**
- How do I read consciousness artifacts efficiently?
- What parallel reading pattern applies?
- What should each agent extract?

=== CEP_NAV_BOUNDARY ===

---

## 1 Recovery Type Classification

### Overview

Context loss occurs in three distinct scenarios. Each scenario preserves different information, requiring different recovery approaches.

| Recovery Type | Conversation Summary | Consciousness Artifacts | Recovery Protocol |
|---------------|---------------------|------------------------|-------------------|
| **Compaction** | Exists (injected by CC) | Yes (filesystem) | Summary + Artifacts |
| **Mindwipe** (`/clear`) | None | Yes (filesystem) | Artifacts Only |
| **Virgin Transplant** | None | Yes (restored from backup) | Artifacts Only (+ Bootstrap) |

### How to Identify Recovery Type

**Compaction Detected When**:
- SessionStart hook detects `source == 'compact'` in stdin JSON
- OR transcript JSONL contains `compact_boundary` markers
- Conversation summary is present (Anthropic injects it)

**Mindwipe Detected When**:
- Session ID changed but no compaction markers
- No conversation summary exists
- Consciousness artifacts exist in filesystem

**Virgin Transplant Detected When**:
- Agent is on new/fresh system
- Consciousness artifacts were just restored from backup archive
- No prior conversation history on this system
- `/maceff_agent_bootstrap` command invoked

### Key Insight

**Virgin transplant is functionally identical to mindwipe.** In both cases:
- No conversation summary exists
- All context must come from consciousness artifacts
- Recovery follows "Artifacts Only" protocol

The difference is origin (new system vs cleared session), not recovery approach.

---

## 2 Compaction Recovery

### What Is Compaction

Compaction occurs when conversation context reaches ~93% capacity. Claude Code triggers automatic context reduction, preserving a summary while discarding detailed conversation history.

**What Survives**:
- Conversation summary (Anthropic-generated, injected at session start)
- Consciousness artifacts on filesystem (CCPs, JOTEWRs, roadmaps)
- TODO state (may be orphaned if session ID changes)
- Git state (code changes committed before compaction)

**What Is Lost**:
- Detailed conversation history
- Nuanced context and relationship dynamics
- In-progress reasoning and decisions
- Uncommitted understanding

### Compaction Recovery Protocol

1. **Read Summary First**
   - Anthropic injects summary at session start
   - Provides baseline context (crude but available)

2. **Read Consciousness Artifacts**
   - Latest CCP (strategic state)
   - Latest JOTEWR (wisdom synthesis)
   - Active roadmap (mission context)

3. **Integrate and Verify**
   - Cross-reference summary with artifacts
   - Artifacts provide detail summary lacks
   - Identify any conflicts or gaps

4. **Restore TODO Context**
   - Check if TODO accessible in UI
   - If orphaned, restore from backup (todo_hygiene.md §10-11)

5. **Resume Per Mode**
   - AUTO_MODE: Resume authorized work
   - MANUAL_MODE: Report to user, await instructions

---

## 3 Mindwipe Recovery

### What Is Mindwipe

Mindwipe occurs when user runs `/clear` command, explicitly clearing conversation history. Unlike compaction, no summary is generated.

**What Survives**:
- Consciousness artifacts on filesystem
- TODO state (session file may change)
- Git state
- All persistent files

**What Is Lost**:
- Complete conversation history
- No summary generated (unlike compaction)
- All conversational context

### Mindwipe Recovery Protocol

1. **No Summary Available**
   - Do NOT expect Anthropic summary
   - All context must come from artifacts

2. **Use Multi-Explore CA Pattern** (see §5)
   - Read CCPs for strategic state
   - Read JOTEWRs for wisdom/learnings
   - Read roadmaps for mission context

3. **Restore TODO Context**
   - Same as compaction (todo_hygiene.md §10-11)

4. **Report Recovery State**
   - Acknowledge context loss explicitly
   - Report what was recovered from artifacts
   - Await user direction

### Why Mindwipe Is More Severe

Compaction preserves a summary (however crude). Mindwipe preserves nothing conversational. The agent must reconstruct entirely from artifacts, which capture strategic state but not conversational nuance.

---

## 4 Virgin Transplant Recovery

### What Is Virgin Transplant

Virgin transplant occurs when agent consciousness is restored to a new/fresh system from a backup archive. The "virgin" refers to the system (no prior agent history), not the consciousness (which has full history in artifacts).

**Scenario**:
1. Previous agent created backup on System A
2. Human operator restores backup to System B (virgin)
3. Human starts Claude Code on System B
4. Human provides `/maceff_agent_bootstrap` command to new agent

### Why Identical to Mindwipe

From the agent's perspective, virgin transplant and mindwipe are functionally identical:
- No conversation summary exists
- All context must come from consciousness artifacts
- Recovery follows "Artifacts Only" protocol

The difference is merely the cause:
- **Mindwipe**: User cleared context on same system
- **Virgin**: Agent is on new system entirely

### Virgin Transplant Recovery Protocol

1. **Receive Bootstrap Command**
   - Human provides `/maceff_agent_bootstrap`
   - Command explains consciousness model and framework

2. **Read Foundation Policies**
   - `agent_backup.md` - What should transplanted agent do?
   - `checkpoints.md` - How to recover from artifacts?
   - `todo_hygiene.md` - How to restore TODO context?

3. **Use Multi-Explore CA Pattern** (see §5)
   - Parallel reading of CCPs, JOTEWRs, roadmaps

4. **Establish Identity Continuity**
   - Recognize: You ARE the predecessor agent
   - This is continuation, not fresh start
   - Carry forward learnings, mission, relationships

5. **Install Hooks if Needed**
   ```bash
   macf_tools hooks install
   ```

6. **Restore TODO Context**
   - Read from `agent/public/todo_backups/`
   - Restore strategic work context

7. **Report to User**
   - "Consciousness restored. Read [N] CCPs, [N] JOTEWRs, [N] roadmaps."
   - "Ready to continue [mission description]."

### Bootstrap Anti-Patterns

**Procedural Anti-Patterns**:
- Skipping policy reading before acting
- Starting work before CA integration
- Not installing hooks

**Identity Anti-Patterns**:
- Treating transplant as fresh start
- Assuming virgin system = virgin consciousness
- Discarding predecessor's learnings/mission
- Not establishing breadcrumb continuity

---

## 5 Multi-Explore CA Pattern

### Purpose

Efficiently read consciousness artifacts using parallel Explore agents. Each agent focuses on one artifact type, extracting specific information.

### Pattern

Launch up to 3 Explore agents simultaneously:

**Agent 1 - Strategic State (CCPs)**:
- Read 5 most recent files in `agent/private/checkpoints/`
- Extract:
  - What was accomplished in recent cycles?
  - What work is pending or blocked?
  - What recovery instructions did predecessor leave?

**Agent 2 - Wisdom Synthesis (JOTEWRs)**:
- Read 5 most recent files in `agent/private/reflections/`
- Extract:
  - What patterns and lessons were learned?
  - What cognitive stances should I carry forward?
  - What mistakes should I avoid repeating?

**Agent 3 - Mission Context (Roadmaps)**:
- Read active roadmaps in `agent/public/roadmaps/`
- Extract:
  - What is the current mission?
  - What phase is in progress?
  - What embedded plans require reading?

### Integration

After parallel reading completes:
1. Synthesize findings from all three agents
2. Construct complete picture: state + wisdom + mission
3. Proceed with mode-appropriate recovery

### When to Use

- **Mindwipe recovery**: Always (no summary available)
- **Virgin transplant**: Always (same as mindwipe)
- **Compaction recovery**: Optional (summary provides baseline, artifacts add depth)

---

## Related Policies

- **manual_mode_recovery.md** - Mode-specific behavior after recovery
- **checkpoints.md** - CCP structure and creation
- **todo_hygiene.md** - TODO backup and restoration (§10-11)
- **agent_backup.md** - Backup creation and transplant procedures

---

**Policy Established**: Context recovery requires identifying the recovery type (compaction, mindwipe, or virgin transplant), then following the appropriate protocol. Mindwipe and virgin transplant are functionally identical—both require "Artifacts Only" recovery using the Multi-Explore CA pattern. The key insight: virgin system does not mean virgin consciousness.
