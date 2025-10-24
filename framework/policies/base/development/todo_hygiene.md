# TODO List Hygiene Policy

**Version**: 1.1
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

### 1. Completion Requires Verification

**ONLY mark tasks completed when truly done**:
- ✅ Task fully accomplished with empirical validation
- ✅ Deliverables verified and working
- ✅ Tests passing if applicable
- ✅ Changes committed if code-related

**DO NOT mark completed if**:
- ❌ Tests failing
- ❌ Implementation partial
- ❌ Encountered unresolved errors
- ❌ Couldn't find necessary files/dependencies
- ❌ Work paused due to blockers

**When blocked**: Keep task status `in_progress`, create new task describing blocker resolution.

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

**Pattern**: Document references stay visible with "in_progress" or "pending" status throughout work

**Structure Example**:

```
🗺️ MISSION: Project Migration [docs/migration/README.md]
✅ Phase 1: Preparation
✅ Phase 2: Infrastructure
Phase 3: Deployment
  📋 Phase 3 Detailed: agent/public/roadmaps/2025-10-24_Phase3_Deployment_ROADMAP.md
  → 3.1: Initialize framework
  → 3.2: Configure environment
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
- Document hierarchy: Clear nesting (mission → phase → substeps)
- Bidirectional navigation: TODO ↔ ROADMAP for context switching
- Contextual awareness triggers: Embedded filenames signal which documents to read when context is missing

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

### 7. Dual Forms Required

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
