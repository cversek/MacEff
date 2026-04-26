---
description: Create MacEff-compliant roadmap with enforced pre-draft ceremony
argument-hint: [brief topic description]
allowed-tools: Read, Bash(macf_tools:*), Grep, AskUserQuestion, Task(Explore), EnterPlanMode, ExitPlanMode
---

Create a MacEff-compliant roadmap following the complete preliminary workflow with mandatory ceremony enforcement.

**Argument**: Brief description of the roadmap topic

---

## 🚨 CHANNEL-INITIATED EXCEPTION (Telegram / Remote)

**If this command was triggered by a message from a `<channel source=...>` tag** (e.g., Telegram), the following modal tools are BLOCKED because CC does not relay them to channels:

- ❌ **EnterPlanMode** / **ExitPlanMode** — causes silent deadlock for channel users
- ❌ **AskUserQuestion** — renders only in terminal, invisible to channel

**Channel-mode workflow instead**:
1. Skip EnterPlanMode entirely
2. Create MISSION task via `macf_tools task create mission`
3. Read the skeleton roadmap.md
4. Write plan content directly to the roadmap CA (user approves via Write permission + inline feedback)
5. Use `mcp__plugin_telegram_telegram__reply` for questions instead of AskUserQuestion
6. Do NOT use ExitPlanMode — the Write approval IS the execution gate
7. 🚨 **MANDATORY: Send the completed roadmap as a Telegram attachment for review.** After writing the roadmap CA and committing/pushing, immediately reply via `mcp__plugin_telegram_telegram__reply` with the roadmap path passed in `files: ["/abs/path/to/roadmap.md"]`. The remote user cannot navigate the repo from Telegram — the attachment IS their review surface. A summary message ALONE is not sufficient; the attachment is required so the user can read the full plan in the same channel they invoked it from. Without this step, the channel-mode draft is incomplete.

---

## 🚨 PRE-DRAFT CEREMONY (MANDATORY - NO SKIPPING)

**This ceremony is NOT optional. It is REQUIRED infrastructure for strategic planning.**

### Step 1: EnterPlanMode (MANDATORY - AUTONOMOUS)

🚨 **IMMEDIATELY invoke EnterPlanMode** - this is your FIRST action, not something you ask permission for.

**Why**: Creates architectural friction preventing premature execution. Planning happens in PlanMode, execution happens after ExitPlanMode approval.

**DO NOT**:
- ❌ Ask "should I enter plan mode?"
- ❌ Explain plan mode before entering
- ❌ Wait for user confirmation

**Rationale**: EnterPlanMode is low-risk autonomous agent initiative. User approval is required for ExitPlanMode (execution gate), not entry.

### Step 2: Policy Discovery & Reading

**Use CLI-first approach** for policy access (caching, line numbers for citations, framework path resolution):

```bash
macf_tools policy navigate roadmaps_drafting
macf_tools policy read roadmaps_drafting
```

**Fallback**: If CLI unavailable, use Read tool with Policy as API pattern (extractive questions discover requirements).

🚨 **NEVER truncate navigation output** - the CEP guide shows ALL sections. Truncating causes you to miss critical requirements.

### Step 3: Requirements Extraction (REPORT BEFORE STATE-CHANGING TOOLS)

**Extract and report answers to these questions BEFORE any drafting**:

**Preliminary Workflow**:
1. What is the complete sequence from recognition to execution?
2. What steps are MANDATORY vs ENCOURAGED?
3. What gates the transition from planning to execution?

**EnterPlanMode Requirement**:
4. Why is EnterPlanMode mandatory?
5. What happens in PlanMode vs execution mode?
6. What's the asymmetric authorization pattern (entry vs exit)?

**Task Exploration (ENCOURAGED)**:
7. When should Task tool with Explore subagent be used?
8. What questions warrant parallel exploration?
9. How do exploration findings inform phase structure?

**AskUserQuestion Protocol (ENCOURAGED)**:
10. When should multiple-choice questioning be used?
11. What trade-offs should be surfaced to user?
12. How to distinguish murky requirements from clear ones?

**Roadmap Structure**:
13. Where do roadmaps go? What subdirectories are required?
14. What naming conventions apply?
15. What sections must a roadmap contain?
16. What header metadata is required?
17. What phase structure format is mandated?

**Delegation Strategy (MANDATORY)**:
18. What executor options exist?
19. What rationale requirements apply to each phase?
20. When should delegation skill be invoked?

**Phase Content Requirements (MANDATORY)**:
21. What should phases specify?
22. What is explicitly FORBIDDEN in phase descriptions?

### Step 4: Exploration (ENCOURAGED if requirements murky)

**If scope is unclear or requirements ambiguous**, use Task tool with Explore subagent to investigate:
- Requirements discovery
- Codebase patterns
- Complexity assessment
- Dependency identification

**Benefits**: Informed planning based on actual state, discover complexity early, avoid blind planning.

### Step 5: User Questioning (ENCOURAGED if trade-offs exist)

**If architectural decisions or user preferences matter**, use AskUserQuestion to surface:
- Multiple valid approaches
- Speed vs safety trade-offs
- Testing strategy preferences
- Risk tolerance clarification

**Benefits**: User-aligned roadmaps, early risk mitigation, strategic clarity, fewer mid-execution pivots.

---

## DRAFTING PHASE (After Ceremony Complete)

### Claude Code Plan File Usage

**Pattern**: Use Claude Code's native plan mode for iterative drafting:

1. **Gather context** from policy extraction, exploration, user questions
2. **Draft in plan file** - iterate freely
3. **Refine structure** based on policy requirements
4. **Present to user** for review

🚨 **CRITICAL**: Plan file is drafting workspace ONLY - NOT a MacEff consciousness artifact. Final roadmap MUST be transferred to compliant CA structure.

### Drafting Guidelines

**Apply policy requirements**:
- Folder structure per policy
- Required sections per policy
- Phase breakdown guidelines
- Delegation strategy table
- Phase content requirements
- Portable paths for framework roadmaps

**Present to user**: Show draft, request feedback, iterate until approved.

---

## POST-DRAFT CEREMONY (MANDATORY - NO SKIPPING)

**This ceremony happens AFTER user approves draft, BEFORE execution.**

### Step 1: Create Mission Task (Atomically)

Use CLI to create task atomically - this creates folder structure, skeleton roadmap.md, and mission task in one operation.

### Step 2: Transfer Plan Content to Roadmap CA

🚨 **Read skeleton FIRST**: The CLI output shows the skeleton path. You MUST read it before writing (Claude Code requires reading existing files first).

**Then transfer your plan file content** to the skeleton roadmap.md.

**Preserve**:
- Header metadata from skeleton
- Task management fields
- Policy-compliant structure

### Step 3: Report to User

**Report**:
- Task ID
- Roadmap path
- Phase count and delegation assignments

### Step 4: 🛑 STOP (Execution Gate)

**DO NOT start implementation.** The user MUST authorize execution separately.

**Why**: Roadmap drafting is planning. Task start is execution commitment. These are separate approval gates.

---

## Workflow Summary (Recognition → Draft → Execution)

```
1. RECOGNIZE roadmap trigger (user invokes command)
         ↓
2. 🚨 EnterPlanMode (MANDATORY - autonomous, immediate)
         ↓
3. Policy reading (MANDATORY - navigate + read via CLI)
         ↓
4. Extract requirements (MANDATORY - report answers to user)
         ↓
5. Task exploration (ENCOURAGED if murky - use Explore subagent)
         ↓
6. AskUserQuestion (ENCOURAGED if trade-offs - surface decisions)
         ↓
7. Draft in plan file (iterative - apply policy requirements)
         ↓
8. Present to user (get feedback, iterate until approved)
         ↓
9. Create mission task (MANDATORY - CLI creates skeleton)
         ↓
10. Transfer content to roadmap.md (MANDATORY - populate skeleton)
         ↓
11. Report task ID and path (MANDATORY - user needs reference)
         ↓
12. 🛑 STOP (MANDATORY - await execution authorization)
```

**Critical Gates**:
- **Step 2**: EnterPlanMode - autonomous, no skipping
- **Step 9-12**: Post-draft ceremony - required before execution
- **Step 12**: STOP - user approval required for execution transition

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

🚨 **Path portability required** - Use `{FRAMEWORK_ROOT}` for policy references in framework roadmaps.

🚨 **EnterPlanMode is MANDATORY** - No exceptions. Autonomous invocation, not permission-seeking.

🚨 **Pre-draft ceremony is REQUIRED** - Cannot skip to "just draft". Policy reading, extraction, exploration/questioning (when applicable) are infrastructure.

🚨 **Post-draft ceremony is REQUIRED** - Cannot skip to "start implementing". Task creation, content transfer, reporting, STOP are mandatory.

---

**Meta-Pattern**: CLI-First with Policy as API fallback. Use CLI tools when available (caching, citations, path resolution). If CLI unavailable, use Read tool with extractive questions to discover requirements from policies. Commands point to policy knowledge, don't duplicate it.
