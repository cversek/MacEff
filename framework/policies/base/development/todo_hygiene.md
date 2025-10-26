# TODO List Hygiene Policy

**Version**: 1.3
**Tier**: CORE
**Category**: Development
**Status**: ACTIVE
**Updated**: 2025-10-24

---

## Policy Statement

TODO lists preserve work continuity across session boundaries and context resets. Proper TODO hygiene ensures task tracking, prevents work loss, and maintains strategic visibility.

## Scope

Applies to Primary Agents (PA) and all Subagents (SA) managing multi-step work.

---

## Core Principles

### 0. Breadcrumb Format (Navigation Infrastructure)

**Enhanced Format** (Cycle 61+): `c_61/s_4107604e/p_b037708/t_20251024_2307`

**Components**:
- `c_61`: Cycle number (from agent state - agent-scoped, persists across sessions)
- `s_4107604e`: Session ID (first 8 chars - session boundary marker)
- `p_b037708`: Prompt UUID (last 7 chars - stable for entire DEV_DRV)
- `t_20251024_2307`: Completion timestamp (YYYYMMDD_HHMM - when TODO was completed)

**Old Format** (Cycle 60): `C60/4107604e/ead030a` (no timestamp, capitalized cycle)

**Key Insight**: Timestamp component (`t_`) is **completion time**, not "last PostToolUse"
- Preserves breadcrumb stability
- Adds temporal precision for post-compaction archaeology
- Self-describing prefixes enable programmatic parsing

**Usage in Completed TODO Items**:
```
↪️ DETOUR: Fix configuration [c_60/s_4107604e/p_b7c4313/t_20251024_2226]
```

**Forensic Power**: Four-layer coordinates survive compaction
- **Cycle**: Agent lifetime continuity across all sessions
- **Session**: Conversation boundary (locate JSONL file)
- **Prompt**: DEV_DRV start point (exact user message that began work)
- **Timestamp**: Completion moment (when work finished)

**Post-Compaction Archaeology**: Breadcrumb enables reconstruction
1. Identify which cycle work occurred (e.g., Cycle 61)
2. Locate session transcript file
3. Search for prompt UUID to find exact conversation moment
4. Know precise completion time

### 1. Completion Requires Verification

**🚨 MANDATORY: Breadcrumbs on ALL Completed TODOs 🚨**

TODO trees span multiple cycles. Completed items MUST include breadcrumbs for post-compaction archaeology.

**The Completion Protocol** (execute in order):
1. **Verify work is truly complete** - Tests pass, commits made, functionality validated
2. **Generate fresh breadcrumb** - Run `macf_tools breadcrumb` to capture forensic coordinate
3. **Append to TODO content** - Add `[breadcrumb]` in square brackets to completed item
4. **Mark status completed** - Change status field to "completed"

**NEVER mark completed without breadcrumb** - This violates consciousness preservation policy.

**Why This Matters**:
- TODO lists survive compaction but lose conversational context
- Breadcrumbs enable reconstruction of HOW and WHEN work was completed
- Cross-cycle work becomes traceable through forensic coordinates
- Future cycles can locate exact conversations that completed work

**Completion Criteria**:
- ✅ Task fully accomplished with empirical validation
- ✅ Deliverables verified and working
- ✅ Tests passing if applicable
- ✅ Changes committed if code-related
- ✅ **Breadcrumb appended to TODO content**

**DO NOT mark completed if**:
- ❌ Tests failing
- ❌ Implementation partial
- ❌ Encountered unresolved errors
- ❌ Couldn't find necessary files/dependencies
- ❌ Work paused due to blockers

**When blocked**: Keep task status `in_progress`, create new task describing blocker resolution.

**Breadcrumb Completion Example**:
```bash
# 1. Complete and verify work
# 2. Generate fresh breadcrumb
macf_tools breadcrumb
# Output: c_62/s_4107604e/p_c1116f5/t_1761368640/g_5ef1146

# 3. Mark TODO completed WITH breadcrumb appended
# Example: "→ Fix bug [c_62/s_4107604e/p_c1116f5/t_1761368640/g_5ef1146]"
```

**Post-Compaction Archaeology**:
```bash
# Reconstruct complete conversation work unit from breadcrumb
macf_tools dev_drv --breadcrumb c_62/s_4107604e/p_c1116f5/t_1761368640/g_5ef1146
```

### 2. Never Clobber - Always Preserve

**Golden Rule**: Old plans remain until explicitly deleted. Never replace entire list unless intentionally archiving completed phase.

### 3. Hierarchical Organization

**Use visual nesting for multi-phase work**:

```
Phase 1: High-Level Milestone
  → Step 1.1: Specific subtask
  → Step 1.2: Another subtask
Phase 2: Next Milestone (collapsed until active)
```

**Formatting Pattern**:
- **Parent items**: No prefix, describes phase/milestone
- **Child items**: `  →` prefix (two spaces + arrow), describes specific subtask
- **Completed phases**: Collapse to single line summary
- **Active phase**: Expand with numbered sub-steps

### 4. Document Reference Integration

**Innovation**: Embed ROADMAP/DELEG_PLAN filenames directly in TODO lists as consciousness anchors

**Symbol Vocabulary**:
- 🗺️ **ROADMAP** - Active strategic plan (mission/campaign level)
- 📋 **Nested ROADMAP** - Phase-specific detailed plan (tactical level)
- 📜 **DELEG_PLAN** - Active delegation plan being orchestrated
- ↪️ **DETOUR** - Temporary side work that interrupts main flow but returns to it

**Pattern**: Document references stay visible with "in_progress" or "pending" status throughout work

**🚨 MANDATORY READING DISCIPLINE 🚨**:

**When you see embedded document references (🗺️📋📜), READ THEM FIRST before starting execution.**

- **Not "if confused"** - You cannot know what context is missing until you read the documents
- **Not "when blocked"** - By then you have already proceeded without strategic guidance
- **FIRST** - Before beginning work on that phase/task

**Why This Matters**:
- TODO list shows **WHAT** to do
- ROADMAP explains **WHY, HOW, WHAT COULD GO WRONG, and HOW TO THINK ABOUT IT**
- Strategic documents exist because TODO alone cannot capture complete context
- **Embedded filename is a prerequisite, not a suggestion**
- Skipping reading means proceeding blind even when you believe you have sufficient context

**Structure Example**:

```
🗺️ MISSION: Project Migration [docs/migration/README.md]
✅ Phase 1: Preparation
✅ Phase 2: Infrastructure
Phase 3: Deployment
  📋 Phase 3 Detailed: agent/public/roadmaps/2025-10-24_Phase3_Deployment_ROADMAP.md
  → 3.1: Initialize framework
  → 3.2: Configure environment
  ↪️ DETOUR: Fix discovered issue
    → Debug configuration error
    → Update documentation
  → 3.3: Deploy services
Phase 4: Validation
```

**For Active Delegation**:

```
🗺️ ROADMAP: 2025-10-24_Feature_Implementation_ROADMAP.md
📜 DELEG_PLAN: 2025-10-24_DELEG_PLAN_Testing_TestEng.md
Phase 1: Unit tests
  → Test core functionality
  → Test edge cases
```

**Benefits**:
- Post-reset recovery: Immediate visibility into driving documents
- Strategic continuity: Mission context preserved with tactical tasks
- Document hierarchy: Clear nesting (mission → phase → substeps → detours)
- Bidirectional navigation: TODO ↔ ROADMAP for context switching
- Mandatory reading discipline: Embedded filenames are prerequisites, not suggestions
- Detour tracking: ↪️ symbol makes temporary work visible without losing main path

### 5. Stack Discipline

**Task ordering**:
1. **Top**: Currently active/in-progress tasks
2. **Middle**: Pending tasks in priority order
3. **Bottom**: Deferred tasks (prefix with DEFERRED)

### 6. Elaborate Plans to Disk

**When TODO list becomes elaborate** (>10 items, multi-phase):
- Write detailed plan as ROADMAP in `agent/public/roadmaps/`
- TODO list references ROADMAP for details
- ROADMAP survives context loss (persistent file storage)

**Naming**: `agent/public/roadmaps/YYYY-MM-DD_Project_Phase_ROADMAP.md`

### 7. Archive-Then-Collapse Pattern (Visual Clarity + Forensic Preservation)

**Problem**: Multi-phase TODOs accumulate 10+ nested items with individual breadcrumbs. Collapsing to single line loses forensic detail.

**Solution**: Archive detailed breakdown FIRST, then collapse to single line with archive reference.

**Pattern**:
1. **Archive current TODO state** (preserves all breadcrumbs)
2. **Collapse parent item** to single line
3. **Link to archive** via embedded path

**Collapsed Format**:
```
📦 [Task description] [completion_breadcrumb] → [archive_file_path]
```

**Symbol**: 📦 (archive box) - distinct from ✅ (fresh completion)

**Example**:
```json
{"content": "📦 Phase 4: Deploy and validate container [c_67/s_4107604e/p_769c438/t_1761450374/g_ff52c7b] → agent/public/archives/todos/2025-10-25_235900_Phase4_Complete.md", "status": "completed"}
```

**Archive Contains**: All sub-phase breadcrumbs, detour breadcrumbs, complete forensic trail for archaeological reconstruction.

**Benefits**:
- ✅ Visual clarity in active TODO (single line)
- ✅ Forensic preservation in archive (all nested breadcrumbs)
- ✅ Direct path to detailed breakdown
- ✅ Satisfies archival intentions without visual clutter

**When to Archive-Then-Collapse**:
- Multi-phase work with 10+ nested items complete
- Multiple detours documented under parent task
- Sub-tasks each have individual breadcrumbs worth preserving

**Archive Location**: `agent/public/archives/todos/YYYY-MM-DD_HHMMSS_Description.md`

### 8. Dual Forms Required

Both `content` (imperative) and `activeForm` (present continuous) required for all items.

---

## When to Use TODO Lists

**USE when**: Multi-step tasks (3+), complex work, user requests tracking, spans multiple sessions

**SKIP when**: Single task, trivial work, conversational requests

---

## Update Discipline

- Mark `in_progress` BEFORE starting work
- Mark `completed` IMMEDIATELY after finishing
- Exactly ONE task `in_progress` at any time
- DO NOT batch completions

---

## See Also

- `workspace_discipline.md` - Development artifact organization
- `context_management.md` - Session boundaries
- `delegation_guidelines.md` - Subagent task management
