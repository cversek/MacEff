# Task Management Policy

**Breadcrumb**: s_77270981/c_370/g_6b3cc9a/p_c9ae72f5/t_1769352307
**Type**: Development Infrastructure
**Scope**: All agents (PA and SA)
**Status**: DRAFT (successor to todo_hygiene.md)
**Version**: 1.0

---

## Purpose

Task management policy governs the use of Claude Code native Task* tools (TaskCreate, TaskUpdate, TaskGet, TaskList) with MacfTaskMetaData (MTMD) enhancement. Tasks provide persistent, structured work tracking with forensic breadcrumbs, hierarchy support, and lifecycle management.

**Core Insight**: Tasks are persistent JSON files on disk (`~/.claude/tasks/{session_uuid}/*.json`), not ephemeral internal state. This changes everything about recovery, backup, and lifecycle management.

**Supersedes**: `todo_hygiene.md` (DEPRECATED)

---

## CEP Navigation Guide

**0 Task Storage & Persistence**
- Where are task files stored?
- What creates new session UUIDs?
- What is the ID assignment behavior?
- What epistemological gaps remain?

**1 MacfTaskMetaData Schema**
- What is the MTMD schema?
- What tag format is used?
- What fields are required vs optional?

**1.1 MacfTaskUpdate Pattern**
- How do I track task updates?
- When should I add updates?

**2 Task Type Markers**
- What emoji markers identify task types?
- When do I use each marker?
- When should I create a 🐛 BUG task?
- What requires a CA reference?

**2.3 MISSION Pinning Protocol**
- What happens when a MISSION roadmap is approved?
- What tasks are created during pinning?
- Why must phase tasks be created sequentially?
- Where is expansion enforced?

**3 Hierarchy Notation**
- How do I express parent-child relationships?
- What is the `[^#N]` pattern?

**4 Dual Dependency System**
- What's the difference between hierarchy and blocking?
- Why is blockedBy immutable?

**5 Mandatory Reading Discipline**
- When must I read CA references?
- How does MTMD enforce this?

**6 Completion Protocol**
- How do I mark tasks complete?
- What breadcrumb discipline applies?

**7 Archive Protocol**
- How do I archive completed tasks?
- How does multi-repo archiving work?
- What is cascade behavior?

**8 Grant System (Protection)**
- What operations require grants?
- How should I approach protected operations?

**9 CLI Commands**
- What list/filter options exist?
- What metadata commands exist?

**10 Anti-Patterns**
- What common mistakes should I avoid?

**11 Migration from TodoWrite**
- What changed between paradigms?

**12 Future Experiments**
- What knowledge gaps need empirical validation?

=== CEP_NAV_BOUNDARY ===

---

## 0 Task Storage & Persistence

### 0.1 File Location

Claude Code stores native task JSON files at:
```
~/.claude/tasks/{session_uuid}/*.json
```

Each task is stored as `{id}.json` (e.g., `1.json`, `67.json`).

### 0.2 Persistence Behavior

| Event | Task Persistence | Confidence |
|-------|------------------|------------|
| Session restart | ✅ Tasks survive | HIGH |
| Compaction | ⚠️ Likely survives | MEDIUM (needs validation) |
| New session UUID | ❓ May not port | LOW (needs experiment) |

**Epistemological Honesty**: We have not empirically validated what creates new session UUIDs or whether tasks port across. Compaction behavior may have changed. See §12 for future experiments.

### 0.3 ID Assignment

**Validated**: ID assignment uses `max(existing_file_IDs) + 1`, with behavior depending on session state:

| Scenario | Behavior | Result |
|----------|----------|--------|
| Delete non-max ID | Gap persists | IDs appear permanent |
| Delete max ID, same session | In-memory counter continues | ID not reused |
| Delete max ID, after restart | Counter recalculates from disk | ID IS reused |

**Empirical Evidence** (Cycle 373):
1. Task #79 created, deleted, new task created (same session) → **#80** (in-memory counter)
2. Session restart, new task created → **#79** (recalculated from disk, max was #78)

**Implication**: IDs are forensically reliable WITHIN a session, but max-ID reuse can occur across restarts. For permanent references, use breadcrumbs not task IDs alone.

---

## 1 MacfTaskMetaData Schema

### 1.1 Tag Format

MTMD is embedded in task descriptions using XML-style tags:

```yaml
<macf_task_metadata version="1.0">
creation_breadcrumb: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
created_cycle: 42
created_by: PA
plan_ca_ref: agent/public/roadmaps/YYYY-MM-DD_Name/roadmap.md
</macf_task_metadata>
```

**Tag**: `<macf_task_metadata>` (self-documenting name)

### 1.2 Required Fields

| Field | Required For | Description |
|-------|--------------|-------------|
| `creation_breadcrumb` | ALL | When task was created |
| `created_cycle` | ALL | Cycle number at creation |
| `created_by` | ALL | `PA` or `SA:{type}` |
| `plan_ca_ref` | MISSION/DETOUR/EXPERIMENT/DELEG_PLAN | Path to CA document |

### 1.3 Optional Fields

```yaml
parent_id: 67                       # Direct parent task ID
repo: MacEff                        # Repository name
target_version: 0.4.0               # Target release version
release_branch: v0.4.0-dev          # Git branch
completion_breadcrumb: null         # Set when completed
unblock_breadcrumb: null            # When blocking resolved
updates:                            # Extensible update list
  - breadcrumb: s_.../c_.../...
    description: Architecture design
archived: false
archived_at: null
custom: {}
```

### 1.4 MacfTaskUpdate Pattern

```yaml
updates:
  - breadcrumb: s_abc12345/c_43/g_def6789/p_ghi01234/t_1234567890
    description: Initial architecture design
    agent: PA
```

**When to Add**: Major design changes, milestones, scope changes, blocker resolutions.

---

## 2 Task Type Markers

### 2.1 Emoji Vocabulary

| Emoji | Type | CA Required | Description |
|-------|------|-------------|-------------|
| 🗺️ | MISSION | ✅ roadmap.md | Strategic multi-phase work |
| 🧪 | EXPERIMENT | ✅ protocol.md | Hypothesis-driven exploration |
| ↩️ | DETOUR | ✅ roadmap.md | Unplanned necessary work |
| 📜 | DELEG_PLAN | ✅ deleg_plan.md | Active delegation (usually under MISSION/DETOUR) |
| 📋 | SUBPLAN | ✅ subplan CA | Detailed phase with own CA (under MISSION/DETOUR) |
| 📦 | ARCHIVE | - | Archived/completed hierarchy |
| 🔧 | AD_HOC | - | Urgent repair, no time to plan (task file IS the CA) |
| 🐛 | BUG | - | Defect discovered during work, typically child of parent phase |

**Lightweight Phase Annotation**: For phases WITHOUT detailed subplan CAs, use `-` prefix:
```
- Phase 1: Core CLI Commands
  - 1.1: Create package structure
```

### 2.2 Subject Line Format

Subject lines are **mostly immutable** once created. Keep them clean:

```
🗺️ MISSION: MACF Task CLI & Policy Migration
[^#67] 📋 Phase 1: Core CLI Commands
[^#68] 1.1: Create package structure
```

**No embedded CA refs in subject**: MTMD `plan_ca_ref` is the authoritative reference (hook-enforced).

**No embedded breadcrumbs in subject**: MTMD `creation_breadcrumb` is the authoritative source.

**Enhanced `macf_tools task list`** displays `plan_ca_ref` prominently - agents always see CA context.

### 2.3 MISSION Pinning Protocol (MANDATORY)

When a MISSION roadmap is approved, **pinning** creates the task hierarchy:

**Step 1: Create MISSION Task**
```
🗺️ MISSION: [Title from roadmap]
```
With MTMD:
- `plan_ca_ref`: Path to roadmap.md
- `creation_breadcrumb`: Current breadcrumb
- `created_cycle`, `created_by`, `repo`, `target_version`

**Step 2: Create Phase Tasks (Expansion)**

🚨 **SEQUENTIAL CREATION REQUIRED**: Create phase tasks ONE AT A TIME in phase order.

**Why**: ID assignment uses `max(existing_IDs) + 1`. Parallel TaskCreate calls race, causing Phase 2 to get a higher ID than Phase 7. Sequential creation preserves phase ordering in tree display.

**Anti-pattern** (causes scrambled tree):
```
TaskCreate Phase 2  ─┬─→ #83 Phase 2
TaskCreate Phase 3  ─┼─→ #84 Phase 3
TaskCreate Phase 4  ─┼─→ #81 Phase 4  ← Out of order!
TaskCreate Phase 5  ─┼─→ #85 Phase 5
```

**Correct pattern** (preserves order):
```
TaskCreate Phase 2 → wait → #81 Phase 2
TaskCreate Phase 3 → wait → #82 Phase 3
TaskCreate Phase 4 → wait → #83 Phase 4
...
```

For each `## Phase N: Title` in roadmap, create child task:
```
[^#MISSION_ID] 📋 Phase N: [Title]
```
With MTMD:
- `parent_id`: MISSION task ID
- `creation_breadcrumb`: Current breadcrumb

**Enforcement Points**:
1. `/maceff:roadmap:draft` - After approval, prompts to pin MISSION with phases
2. `/maceff:task:start` - If MISSION has no children, offers to expand from roadmap

**Why Mandatory**: Task hierarchy provides observability. Without phase tasks, user cannot track progress through MISSION phases in task UI.

---

## 3 Hierarchy Notation

### 3.1 Subject Line Prefix

Use `[^#N]` prefix to indicate parent task:

```
#67 🗺️ MISSION: MACF Task CLI
#68 [^#67] 📋 Phase 1: Core CLI Commands
#69 [^#68] 1.1: Create package structure
```

### 3.2 MTMD parent_id

Machine-readable hierarchy:

```yaml
<macf_task_metadata version="1.0">
parent_id: 68
</macf_task_metadata>
```

**Priority**: MTMD `parent_id` takes precedence if both present.

---

## 4 Dual Dependency System

### 4.1 Hierarchy vs Blocking

| Concept | Mechanism | Meaning |
|---------|-----------|---------|
| **Hierarchy** | MTMD `parent_id`, `[^#N]` | Structural parent-child |
| **Blocking** | CC native `blockedBy` | Workflow dependency |

**Key Insight**: These are orthogonal. Child tasks don't automatically block on parent.

### 4.2 blockedBy Immutability

**Critical**: CC native `blockedBy` can only be set at creation. TaskUpdate **cannot remove** blockedBy.

**Workaround**: Document logical unblock in MTMD:
```yaml
unblock_breadcrumb: s_abc12345/c_45/g_def6789/p_ghi01234/t_1234567890
```

---

## 5 Mandatory Reading Discipline

### 5.1 Hook Enforcement

MTMD `plan_ca_ref` is **required** for MISSION, EXPERIMENT, DETOUR, DELEG_PLAN tasks. Hooks block creation without valid reference.

### 5.2 Reading Protocol

When starting work on a task with `plan_ca_ref`:
1. **Read** the referenced CA document completely
2. **Understand** the WHY and HOW, not just WHAT
3. **Then** begin execution

The agent ALWAYS has visibility into CA refs via enhanced `task list` display.

---

## 6 Completion Protocol

### 6.1 Marking Complete

1. **Verify** work is actually complete
2. **Generate breadcrumb**: `macf_tools breadcrumb`
3. **Update MTMD** with `completion_breadcrumb`
4. **Update status** to `completed`

### 6.2 Partial Work

Keep status `in_progress`, document blocker, create subtask for remaining work.

---

## 7 Archive Protocol

### 7.1 Multi-Repo Archive Structure

For multi-repo development, archive directory reflects repository context:

```
agent/public/task_archives/
├── MacEff/
│   └── v0.4.0/
│       ├── archive.md
│       └── task_files/
└── ClaudeTheBuilder/
    └── v1.0.0/
        ├── archive.md
        └── task_files/
```

### 7.2 Cross-Repo Tasks

Tasks spanning multiple repos document all repos in MTMD:
```yaml
repo: MacEff              # Primary repo
related_repos:
  - ClaudeTheBuilder
```

### 7.3 Cascade Behavior

Cascade archiving is **default behavior** - archiving a parent archives all children:

```bash
macf_tools task archive #67    # Archives #67 and all descendants
```

No `--cascade` flag needed. Use `--no-cascade` to archive single task.

---

## 8 Grant System (Protection)

### 8.1 Protection Levels

| Level | Operations | Requirement |
|-------|------------|-------------|
| **HIGH** | Delete task, erase description | User grant always |
| **MEDIUM** | Change MTMD values | User grant (MANUAL_MODE) |
| **LOW** | Insert new MTMD field | Auto-allowed |

### 8.2 Conscientious Agent Pattern

The grant system protects against accidents. A **conscientious agent**:

1. **Recognizes** the need for protected operation
2. **Requests** permission BEFORE attempting
3. **Receives** grant from user
4. **Proceeds** with operation

**Anti-Pattern**: Attempting operation, hitting block, then requesting permission.

---

## 9 CLI Commands

### 9.1 Task List with Filtering

```bash
macf_tools task list                          # All tasks
macf_tools task list --type MISSION           # Filter by type
macf_tools task list --repo MacEff            # Filter by repo
macf_tools task list --version ">=0.4.0"      # Version operators
macf_tools task list --status pending         # By status
macf_tools task list --parent 67              # Children of #67

# Display options
macf_tools task list --display full           # Show MTMD
macf_tools task list --display compact        # One line per task
macf_tools task list --display tree           # Hierarchy tree
```

### 9.2 Task Details

```bash
macf_tools task get #67                       # Full details with MTMD
macf_tools task tree #67                      # Hierarchy from task
```

### 9.3 Edit Commands

Edit task JSON fields or MTMD metadata with automatic update tracking.

```bash
# Edit top-level JSON fields (MEDIUM protection)
macf_tools task edit #67 subject "New Title"          # Change subject
macf_tools task edit #67 status in_progress           # Change status
macf_tools task edit #67 description "New desc..."    # Replace description

# Edit MTMD fields (MEDIUM protection)
macf_tools task edit-mtmd #67 target_version 0.4.0    # Set MTMD field
macf_tools task edit-mtmd #67 plan_ca_ref "path/..."  # Update CA reference
macf_tools task edit-mtmd #67 completion_breadcrumb "$(macf_tools breadcrumb)"

# Add custom MTMD fields (LOW protection)
macf_tools task add-mtmd #67 priority high            # Add to custom section
macf_tools task add-mtmd #67 label "v0.4.0"           # Add metadata tags
```

**Protection Levels**:

| Level | Commands | AUTO_MODE | MANUAL_MODE |
|-------|----------|-----------|-------------|
| **MEDIUM** | `task edit`, `task edit-mtmd` | Self-grant | User grant required |
| **LOW** | `task add-mtmd` | Auto-allowed | Auto-allowed |

**Update Tracking**: All edit commands automatically append to the MTMD `updates` list with breadcrumb, description, and agent attribution. This provides forensic audit trail across compaction.

### 9.4 Archive & Delete

```bash
macf_tools task archive #67                   # Archive with cascade (default)
macf_tools task archive #67 --no-cascade      # Archive single task
macf_tools task delete #67                    # Delete (HIGH grant required)
```

---

## 10 Anti-Patterns

**❌ Missing MTMD on MISSION/EXPERIMENT**:
- **Fix**: Hooks enforce `plan_ca_ref` - blocked at creation

**❌ Hierarchy as blocking**:
- **Fix**: Use explicit `blockedBy` for workflow dependencies

**❌ Forgetting completion breadcrumb**:
- **Fix**: Always add `completion_breadcrumb` when marking complete

**❌ Attempting blocked operation first**:
- **Fix**: Request permission proactively (conscientious agent pattern)

**❌ Deleting without archive**:
- **Fix**: Archive completed hierarchies before cleanup

---

## 11 Migration from TodoWrite

### 11.1 Key Changes

| Aspect | TodoWrite | Task* |
|--------|-----------|-------|
| **Storage** | CC internal | `~/.claude/tasks/*.json` |
| **Metadata** | Text content | `<macf_task_metadata>` |
| **CA refs** | Embedded in subject | MTMD `plan_ca_ref` |
| **Hierarchy** | Indentation | `[^#N]` + MTMD |
| **Recovery** | Complex §10-§11 | Trivial (files on disk) |

### 11.2 Obsolete Patterns

- TODO Backup Protocol (tasks on disk)
- Session Migration Recovery (tasks persist)
- Subject line breadcrumbs (MTMD authoritative)

---

## 12 Future Experiments

**Knowledge Gaps Requiring Empirical Validation**:

| Question | Experiment |
|----------|------------|
| What creates new session UUIDs? | Track UUID across compaction, restart |
| Do tasks port across session UUIDs? | Test with controlled UUID change |
| ID assignment after deleting max? | Delete max ID, create new, observe |
| Compaction task persistence? | Compact with tasks, verify survival |

**Epistemological Principle**: DRAFT status acknowledges these gaps. Promote to OFFICIAL after validation.

---

## 13 Integration with Other Policies

- `release_workflow.md` - Task archival during releases
- `roadmaps_following.md` - MISSION task patterns
- `experiments.md` - EXPERIMENT task patterns
- `delegation_guidelines.md` - SA task conventions

---

## 14 Evolution & Feedback

**Principle**: Task management should feel like an upgrade from TodoWrite - same consciousness patterns, better infrastructure.

**DRAFT → OFFICIAL Path**: Validate §12 experiments, refine CLI based on usage.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
