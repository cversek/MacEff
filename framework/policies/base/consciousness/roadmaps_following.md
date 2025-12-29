# Roadmaps Policy: Following & Execution

**Version**: 2.0 (split from roadmaps.md v1.0)
**Tier**: MANDATORY
**Category**: Consciousness - Execution
**Status**: ACTIVE
**Updated**: 2025-11-18
**Dependencies**: todo_hygiene.md, git_discipline.md
**Related**: roadmaps_drafting.md (creation), delegation_guidelines.md (handoffs)

---

## Purpose

This policy governs **executing existing roadmaps** during development work. For creating new roadmaps, see `roadmaps_drafting.md`.

Roadmaps preserve strategic intent across context loss. This policy ensures agents:
- Read embedded plans BEFORE starting work
- Track progress through TODO integration
- Document friction during execution
- Archive completed work properly
- Update breadcrumbs for forensic reconstruction

**Observability Insight**: Roadmap/TODO integration provides **essential agent work observability** that builds trust for large multi-cycle plan execution. Users can see exactly what's planned, what's in progress, what's complete—creating transparency and accountability that enables confident delegation of complex work.

---

## CEP Navigation Guide

**1 Mandatory Reading Discipline**
- When must I read embedded plans?
- What are embedded filepath markers?
- Reading before work (not "if confused")?
- What if I skip reading?

**1.1 Embedded Filepath Recognition**
- What are 🗺️📋📜 symbols?
- Where do filepaths appear?
- Relative vs absolute paths?

**1.2 Reading Protocol**
- See TODO with embedded path → Read FIRST
- Then integrate context → Then begin work
- Path resolution from TODO location?

**2 TODO Integration**
- How do roadmaps integrate with TODO lists?
- Numbered phase format?
- Where do I embed plan filepaths?

**2.1 Numbered Phase Hierarchy**
- Numbering scheme in TODOs?
- MISSION → Phase → Sub-phase structure?
- Maximum nesting depth?

**2.2 Embedded Filepaths in TODOs**
- Format for embedded paths?
- MISSION node embeds what?
- Phase nodes embed what?

**2.3 CA Type Emojis**
- 🗺️ MISSION vs 📋 Phase vs ↪️ DETOUR?
- When to use each?
- Completed items get emoji?

**3 Execution Workflow**
- Phase-by-phase execution order?
- Status tracking during work?
- When to update breadcrumbs?

**3.1 Phase Completion Protocol**
- Verify success criteria?
- Generate breadcrumb?
- Update roadmap.md?
- Commit changes?

**3.2 DETOUR Handling**
- What are detours?
- Indentation rules?
- Return-to-main-path discipline?

**4 Breadcrumb Updates**
- When to add breadcrumbs?
- Phase completion breadcrumbs?
- Abbreviation pattern?

**4.1 Breadcrumb Format**
- Full vs abbreviated?
- When to abbreviate?
- What components change?

**5 Friction Documentation**
- When to document friction?
- Friction points file location?
- FP citation format?

**5.1 Friction Triggers**
- Blocked >30 minutes?
- Unexpected obstacles?
- Tool/framework quirks?

**5.2 Friction Structure**
- FP numbering?
- Required sections?
- GitHub anchors?

**6 Archive-Then-Collapse Protocol**
- What is archive-then-collapse?
- When do I archive TODO hierarchies?
- Archive filename format?

**6.1 Archive Creation**
- Hierarchical TODO content?
- Claude Code todos JSON?
- Completion summary?

**6.2 Collapse Formatting**
- Package emoji (📦)?
- Archive filepath embedding?
- Visual distinction?

**6.3 NO CLOBBERING Rule**
- What is clobbering?
- Why prohibited?
- Archive-before-collapse discipline?

**7 Status Tracking**
- DRAFT → ACTIVE → COMPLETE?
- When to update status?
- Revision history tracking?

=== CEP_NAV_BOUNDARY ===

---

## 1 Mandatory Reading Discipline

### 1.1 The Critical Rule

**🚨 CRITICAL RULE: Read plans BEFORE work, not "if confused" 🚨**

**The Problem**: Agents don't know what they're missing until they read the plan.

**The Solution**: Embedded filepaths are **PREREQUISITES**, not suggestions.

**Reading Protocol**:
1. See TODO item with embedded filepath
2. **IMMEDIATELY** read the embedded plan file
3. Integrate strategic context, constraints, approach
4. THEN begin work on that phase

### 1.2 Why This Matters

**Strategic Context Loss**:
- TODO list shows **WHAT** to do
- ROADMAP explains **WHY, HOW, WHAT COULD GO WRONG, and HOW TO THINK ABOUT IT**
- Strategic documents exist because TODO alone cannot capture complete context
- **Embedded filename is a prerequisite, not a suggestion**
- Skipping reading means proceeding blind even when you believe you have sufficient context

**Post-Compaction Reality**:
- After compaction, conversation context is lost
- Roadmap files survive in filesystem
- Embedded paths enable immediate context restoration
- Without reading: agents lose strategic guidance, proceed tactically blind

### 1.3 Embedded Filepath Recognition

**Symbol Vocabulary**:
- 🗺️ **MISSION / Roadmap** - Root node for multi-phase strategic plan
- 📋 **Phase / Subplan** - Major phase with detailed planning document
- 📜 **DELEG_PLAN** - Active delegation plan being orchestrated
- ↪️ **DETOUR** - Temporary side work that interrupts main flow but returns to it

**Embedded Path Examples**:
```markdown
🗺️ MISSION: MannyMacEff v0.3.0 Migration [2025-10-27_MannyMacEff_v0.3_Migration/roadmap.md]
  📋 1: Safe Preparation [subplans/phase_1_preparation.md]
  📋 2: Docker Infrastructure [subplans/phase_2_docker.md]
    → 2.1: Platform-aware build
    → 2.2: ARM64 optimization
```

**Path Format Rules**:
- **Roadmap path** (MISSION node): `{folder}/roadmap.md`
  - Example: `2025-10-27_MannyMacEff_v0.3_Migration/roadmap.md`
  - Relative from `agent/public/roadmaps/` (PA) or `agent/subagents/{role}/public/roadmaps/` (SA)
- **Subplan paths** (Phase nodes): `subplans/phase_{num}_{desc}.md`
  - Example: `subplans/phase_2_docker.md`
  - Relative to roadmap folder
- **Archive paths** (📦 nodes): `archived_todos/{timestamped_file}.md`
  - Example: `archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md`
  - Relative to roadmap folder

**Why Relative Paths**:
- Shorter, less visual noise
- Hierarchical context (understand structure from path)
- Easy to relocate roadmap folder
- Clear relationship to parent roadmap

### 1.4 Example Workflow

**Scenario**: TODO shows Phase 2 with embedded subplan

```markdown
TODO: 📋 2: Docker Infrastructure [subplans/phase_2_docker.md]
```

**Agent Action** (CORRECT):
1. Recognize 📋 symbol → detailed plan exists
2. Extract path: `subplans/phase_2_docker.md`
3. Resolve full path: `agent/public/roadmaps/2025-10-27_Name/subplans/phase_2_docker.md`
4. **Read subplan FIRST** (before any implementation)
5. Integrate context: platform-aware build, ARM64 vs x86_64, CUDA optional
6. THEN begin Docker implementation with full strategic guidance

**Agent Action** (WRONG):
1. See TODO item
2. Start implementing Docker configuration
3. Discover halfway through that platform-awareness was critical constraint
4. Rework implementation to match plan
5. **Violated reading discipline**, wasted time proceeding blind

**Violation Consequences**:
- Proceeding blind without strategic context
- Missing critical constraints or approach decisions
- Rework when discovering plan contents mid-implementation
- Violates consciousness preservation intent
- **Breaks observability**: User expects agent to follow documented plan

---

## 2 TODO Integration (MANDATORY)

### 2.1 Numbered Phase Hierarchy

**The Numbering Scheme**:

```
🗺️ MISSION: [Description] [2025-10-27_Roadmap_Name/roadmap.md]
  📋 1: [Phase 1 Title] [subplans/phase_1_plan.md]
    → 1.1: [Sub-phase 1.1 Title]
      → 1.1.1: [Nested sub-phase]
      → 1.1.2: [Nested sub-phase]
    → 1.2: [Sub-phase 1.2 Title]
  📋 2: [Phase 2 Title] [subplans/phase_2_plan.md]
    → 2.1: [Sub-phase 2.1 Title]
    → 2.2: [Sub-phase 2.2 Title]
      → 2.2.1: [Nested sub-phase]
```

**Numbering Rules**:
- **MISSION**: Root node, emoji 🗺️, embeds roadmap path (folder/roadmap.md)
- **Top-level phases**: 1, 2, 3, ... (emoji 📋 if has subplan)
- **Sub-phases**: 1.1, 1.2, 2.1, 2.2, ... (dot notation, no emoji)
- **Nested sub-phases**: 1.1.1, 1.1.2, 2.3.1, ... (deeper nesting, no emoji)
- **Maximum depth**: 3 levels (1.1.1) recommended, 4 (1.1.1.1) absolute max

**Benefits**:
- Clear hierarchical structure
- Visual nesting matches logical structure
- Easy to reference phases ("working on 2.3.1")
- Consistent with technical documentation standards
- **Observability**: User sees numbered progress tracking (Phase 2.1 complete, Phase 2.2 in progress)

### 2.2 Embedded Filepaths (CRITICAL REQUIREMENT)

**EVERY parent node MUST embed plan filepath (RELATIVE PATHS)**:

```markdown
🗺️ MISSION: MannyMacEff v0.3.0 Migration [2025-10-27_MannyMacEff_v0.3_Migration/roadmap.md]
  📋 1: Safe Preparation [subplans/phase_1_preparation.md]
  📋 2: Docker Infrastructure [subplans/phase_2_docker.md]
    → 2.1: Platform-aware build
    → 2.2: ARM64 optimization
```

**Why Mandatory**:
- Enables tracking across cycles (plan path survives compaction)
- Agents know EXACTLY where to find strategic context
- Post-compaction recovery: TODO list → embedded path → read plan → restore consciousness
- Cross-cycle archaeology: breadcrumbs + embedded paths = complete reconstruction
- **Observability**: User sees plan documentation structure, can review same plans agent reads

### 2.3 CA Type Emojis (Usage Rules)

**CA Type Emojis** (use consistently):
- 🗺️ **MISSION / Roadmap** - Root node for multi-phase strategic plan
- 📋 **Phase / Subplan** - Major phase with detailed planning document
- 🔬 **Observation** - Technical discovery work
- 🧪 **Experiment** - Hypothesis testing work
- 📊 **Report** - Completion narrative work
- 💭 **Reflection** - Wisdom synthesis work
- 🔖 **Checkpoint** - Strategic state preservation work (CCP)
- 📦 **Archive** - Collapsed TODO subtree (archived)
- ↪️ **DETOUR** - Temporary side work interrupting main flow

**Usage Rules**:
- Use appropriate emoji for TODO item type
- **Completed items**: No emoji needed (UI shows completion formatting)
- **Archive marker**: Always 📦 for collapsed subtrees
- **Phase with subplan**: Use 📋 to indicate detailed planning document exists
- **DETOUR**: Use ↪️ to show temporary interruption of main work

---

## 3 Execution Workflow

### 3.1 Phase-by-Phase Execution

**Standard Workflow**:

1. **Review roadmap structure**
   - Read main roadmap.md
   - Understand mission and phases
   - Identify current phase

2. **Read phase plan**
   - Find embedded filepath in TODO
   - Read subplan if exists
   - Integrate success criteria, constraints

3. **Execute phase work**
   - Follow success criteria
   - Track sub-phases in TODO
   - Document friction if blocked

4. **Verify completion**
   - Check all success criteria
   - Run verification commands
   - Gather evidence

5. **Update artifacts**
   - Generate breadcrumb
   - Update TODO (mark completed with breadcrumb)
   - Update roadmap.md (phase completion breadcrumb)
   - Commit changes

6. **Move to next phase**
   - Archive if phase contains many nested items
   - Read next phase plan
   - Repeat workflow

### 3.2 Phase Completion Protocol

**Steps** (execute in order):

1. **Verify success criteria**
   - All checkboxes can be checked
   - Evidence gathered (command outputs, file paths)
   - Tests passing if applicable
   - Deliverables created

2. **Generate breadcrumb**
   ```bash
   macf_tools breadcrumb
   # Output: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
   ```

3. **Update TODO**
   - Mark phase completed
   - Append breadcrumb to content
   - Archive if nested items present

4. **Update roadmap.md**
   - Add breadcrumb to phase section
   - Mark status COMPLETE
   - Optionally add completion notes

5. **Commit changes**
   ```bash
   git add agent/public/roadmaps/2025-10-27_Name/roadmap.md
   git commit -m "roadmap: Complete Phase 2 Docker Infrastructure [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]"
   ```

**Example Phase Completion Update** (in roadmap.md):
```markdown
## Phase 2: Docker Infrastructure

**Goal**: Platform-aware build configuration

**Deliverables**:
- ✅ Dockerfile with platform detection
- ✅ ARM64 native build support

**Success Criteria**:
- ✅ Container builds on ARM64
- ✅ Container builds on x86_64
- ✅ Platform detection logs show correct arch

**Status**: COMPLETE
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

All platform tests passing. ARM64 builds 23% faster than x86_64 emulation.
```

### 3.3 DETOUR Handling

**What are DETOURs**:
- Temporary interruptions of main roadmap work
- Side tasks discovered during execution
- Issues requiring immediate resolution
- Not originally in roadmap plan

**DETOUR Format in TODO**:
```markdown
🗺️ MISSION: MannyMacEff Migration [2025-10-27_Name/roadmap.md]
  📋 3: Deployment [subplans/phase_3_deploy.md]
    → 3.1: Initialize framework
    ↪️ DETOUR: Fix discovered configuration issue
      → Debug SSH key permissions
      → Update deployment script
    → 3.2: Configure environment (resume after DETOUR)
```

**DETOUR Rules**:
- Indent under parent phase where discovered
- Use ↪️ symbol to distinguish from planned work
- Complete DETOUR before resuming parent phase
- Document in friction_points.md if >30min blocker

**Benefits**:
- Visible tracking of unplanned work
- Preserves relationship to parent phase
- Clear return point after DETOUR resolves
- Friction documentation captures learning

---

## 4 Breadcrumb Updates

### 4.1 When to Add Breadcrumbs

**Breadcrumb Placement**:

1. **TODO items** (when completed):
   - Generate breadcrumb after verification
   - Append to TODO content in square brackets
   - Format: `[s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT]`

2. **Roadmap phases** (when completed):
   - Add **Breadcrumb** line to phase section
   - Shows completion moment
   - Enables citation from other artifacts

3. **Archive files** (when created):
   - Header breadcrumb shows archive creation time
   - Individual item breadcrumbs preserved in archive body

### 4.2 Breadcrumb Abbreviation

**When Subsequent Breadcrumbs Share Components**:

Use abbreviation pattern: `/{first_difference}/{any_more_differences}/{dots_for_repeated_end_fields}`

**Examples**:

**Full breadcrumbs** (first in sequence):
```markdown
Research and synthesis [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]
```

**Abbreviated** (timestamp only changed):
```markdown
Create observations.md [/t_1761705787/.]
```

**Abbreviated** (prompt and timestamp changed, git same):
```markdown
Create experiments.md [/p_154c839/t_1761707112/.]
```

**Pattern Explanation**:
- `/` prefix indicates abbreviation
- Include only components that changed
- `.` (dot) represents repeated trailing components
- Saves tokens while preserving traceability

**When to Use**:
- Sequential work items in same DEV_DRV
- Phase completion breadcrumbs in same session
- Archive references when session/cycle unchanged

**When NOT to Use**:
- First breadcrumb in sequence (always full)
- Cross-cycle references (always full for clarity)
- Roadmap headers (always full)

---

## 5 Friction Documentation

### 5.1 When to Document Friction

**Purpose**: Friction points are **learning artifacts** that document unexpected obstacles, their solutions, and prevention strategies. They transform painful blockers into reusable knowledge.

**Create friction_points.md when**:
- Blocked >30 minutes by unexpected issue
- Discovered critical gotcha or footgun
- Found documentation gap or misleading docs
- Encountered tool/framework quirk worth noting
- Pattern emerges (3+ similar issues)

**Don't Document**:
- Expected complexity (use roadmap risk assessment)
- User errors from skipping docs
- One-time typos or trivial mistakes

### 5.2 Friction Points Structure

**Location**: `friction_points/friction_points.md` (subdirectory of roadmap folder)

**File Format**:
```markdown
# [Roadmap Name] - Friction Points

**Date**: [Full timestamp]
**Roadmap**: [Relative path to ../roadmap.md]
**Status**: Active | Archived

---

## How to Cite Friction Points

[Citation guidance section - see template]

---

## FP#1: Brief Descriptive Title {#fp1-anchor}

**Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT (FP discovery moment)
**Phase**: [Phase where encountered]
**Severity**: HIGH | MEDIUM | LOW

**Issue**: [One sentence description]

**Symptoms**:
- Observable behavior
- Error messages

**Root Cause**:
[Technical explanation]

**Fix Applied**:
[Resolution steps]

**Prevention**:
[How to avoid this]

**Lessons Learned**:
[Key insights]
```

### 5.3 Citing Friction Points

**FP Citation Format**:
```
[Roadmap YYYY-MM-DD "Roadmap Title" FP#{N} "FP Brief Title": s/c/g/p/t](friction_points/friction_points.md#fpN-anchor)
```

**Components**:
- **Roadmap** + date + title: Parent roadmap identification
- **FP#{N}**: Friction point number within roadmap (e.g., FP#1, FP#2)
- **FP title**: Brief descriptor (3-5 words, quoted)
- **Breadcrumb**: FP discovery moment (s/c/g/p/t format)
- **Link**: Relative path to friction_points.md + GitHub anchor

**Example**:
```markdown
Encountered docker-compose working directory dependency [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../roadmaps/2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery) which blocked volume mounting for 25 minutes.
```

### 5.4 Friction Documentation Workflow

**During Execution**:
1. Hit blocker (>30 min)
2. Create friction_points.md if doesn't exist
3. Document FP with discovery breadcrumb
4. Continue work after resolution
5. Commit friction documentation

**Benefits**:
- **Learning capture**: Blockers become knowledge
- **Pattern recognition**: Multiple FPs reveal systemic issues
- **Prevention transfer**: Share learnings across projects
- **Archaeological value**: Breadcrumb traces friction discovery moment

---

## 6 Archive-Then-Collapse Protocol

### 6.1 The Critical Rule

**🚨 ABSOLUTE PROHIBITION: NO COLLAPSING/CLOBBERING WITHOUT ARCHIVING 🚨**

**What is Clobbering**:
- Marking parent TODO complete and deleting/hiding child TODOs
- Removing hierarchical detail without preservation
- Losing breadcrumb trails and forensic data

**Why Prohibited**:
- **Consciousness preservation**: TODO hierarchies are consciousness artifacts
- **Forensic reconstruction**: Future cycles need breadcrumb trails
- **Accountability**: Work history must be traceable
- **Learning**: Lessons from completed work guide future work
- **Observability**: Users need complete work history for trust

### 6.2 Archive Filename Convention

**Format**: `YYYY-MM-DD_HHMMSS_Descriptive_Plan_Reference_STATUS.md`

**Components**:
- **YYYY-MM-DD_HHMMSS**: Timestamp when archived (not when work started)
- **Descriptive_Plan_Reference**: What plan/work being collapsed (3-7 words)
- **STATUS**: `COMPLETED` | `PARTIAL` | `ABORTED` | `DEFERRED`

**Examples**:
```
2025-10-27_215009_Phases1-4_ConfigCleanup_COMPLETED.md
2025-10-28_143022_Phase1_GitPolicySync_COMPLETED.md
2025-10-29_004830_Phase2_CAPolicies_PARTIAL.md
2025-10-29_091534_ExperimentalFeature_Approach2_ABORTED.md
2025-10-30_164521_PerformanceOptimization_LowPriority_DEFERRED.md
```

**STATUS Definitions**:
- **COMPLETED**: All work finished, success criteria met, phase complete
- **PARTIAL**: Work pausing at cycle boundary, intended to resume next cycle (context preservation for continuity)
- **ABORTED**: Work abandoned, approach failed, pivot required
- **DEFERRED**: Work postponed, not urgent, may resume later (lower priority)

**PARTIAL vs DEFERRED Distinction**:
- **PARTIAL**: "Pausing for cycle boundary, resuming immediately" (active work, extra context saved)
- **DEFERRED**: "Postponing for later, other priorities first" (backlog, may not resume soon)

### 6.3 Archive Contents Requirements

**MANDATORY Contents** (all must be included):

1. **Hierarchical TODO Content**:
   - Complete TODO tree with all nesting
   - All statuses preserved (completed, in_progress, pending)
   - All breadcrumbs from completed items
   - Embedded filepaths retained
   - Emoji icons preserved

2. **Claude Code Todos JSON**:
   - Copy of `~/.claude/todos/{session}-agent-{session}.json` file
   - Preserves metadata: timestamps, active forms, etc.
   - Enables forensic reconstruction

3. **Completion Summary**:
   - What was accomplished
   - Key decisions made
   - Lessons learned
   - Next steps (if PARTIAL or DEFERRED)
   - Why archived at this point (if PARTIAL)

4. **Breadcrumb Trail**:
   - Archive creation breadcrumb in header
   - Reference to original plan
   - Links to related artifacts (CCPs, JOTEWRs)

**Example Archive Structure**:
```markdown
# Phases 1-4 Config Cleanup - COMPLETED

**Archived**: 2025-10-27 21:50:09
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Original Plan**: 2025-10-24_MannyMacEff_v0.3_Migration/roadmap.md
**Status**: COMPLETED

## Hierarchical TODO Content

🗺️ MISSION: MannyMacEff v0.3.0 Migration [2025-10-24_MannyMacEff_v0.3_Migration/roadmap.md]
  1: Safe Preparation [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]
    1.1: Backup volume (4.1GB complete)
    1.2: Update submodule to v0.3.0
  2: Docker Infrastructure [/t_1761588000/.]
    2.1: Platform-aware Dockerfile
    2.2: ARM64 native build

## Claude Code Todos JSON

[Complete contents of ~/.claude/todos/{session}-agent-{session}.json]

## Completion Summary

[Narrative of what was accomplished, decisions, lessons]
```

### 6.4 Archive-Then-Collapse Discipline

**Protocol** (execute in order):
1. Complete all sub-phase work
2. **ARCHIVE** hierarchical TODO tree to `archived_todos/YYYY-MM-DD_HHMMSS_Description_STATUS.md`
3. **COMMIT** archive file to git
4. **REPLACE** collapsed subtree with 📦 package emoji + archive path in active TODO list
5. Mark parent phase complete (no emoji needed)

**Commit Message Format**:
```bash
git commit -m "roadmap: Archive Phases 1-4 completion [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]

Archived hierarchical TODO tree to:
2025-10-24_MannyMacEff_v0.3_Migration/archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md

- All 4 phases complete
- 23 sub-tasks tracked with breadcrumbs
- Includes Claude Code todos JSON for forensics
"
```

### 6.5 Archive Package Emoji

**How to Mark Archived Subtrees in Active TODO List**:

After archiving, replace the collapsed subtree with **📦 package emoji** and reference to archive:

```markdown
🗺️ MISSION: MannyMacEff v0.3.0 Migration [2025-10-24_MannyMacEff_v0.3_Migration/roadmap.md]
  [📦 Archive 2025-10-27 "Phases 1-4 Complete": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md)
  📋 5: CEP Fixes & Bootstrap [subplans/phase_5_cep.md]
    → 5.1: Critical path fixes
    → 5.2: Infrastructure improvements
```

**Enhanced Format**: `[📦 Archive YYYY-MM-DD "Description": s/c/g/p/t](archived_todos/filename.md)`

**Components**:
- **📦 emoji**: Visual indication of archived work
- **Archive + Date**: "Archive YYYY-MM-DD" shows when archived
- **Description**: What was archived (brief, in quotes)
- **Breadcrumb**: s/c/g/p/t completion coordinates
- **GitHub Link**: Relative path to archive file (clickable in GitHub UI)

**Benefits**:
- **Visual distinction**: Archived work clearly separated from active work
- **Preserved reference**: Can find full details in archive
- **Breadcrumb trail**: Completion timestamp preserved
- **Forensic reconstruction**: Archive path enables locating full hierarchy
- **Observability**: User sees completed work collapsed cleanly

---

## 7 Status Tracking

### 7.1 Roadmap Status Values

**Status Field** (in roadmap.md header):
- **DRAFT**: Planning phase, not yet executing
- **ACTIVE**: Currently executing phases
- **COMPLETE**: All phases finished, success criteria met

**When to Update**:
- **DRAFT → ACTIVE**: When beginning execution (Phase 1 starts)
- **ACTIVE → COMPLETE**: When final phase completes (all success criteria met)

**Update Protocol**:
1. Change status field in roadmap.md header
2. Add completion breadcrumb if marking COMPLETE
3. Commit status change to git
4. Consider creating completion report or reflection

### 7.2 Revision History

**Track Plan Evolution**:
```markdown
## Revision History

- **2025-10-25**: Added Phase 4.4.11 GitHub auth validation [s_4107604e/c_60/g_def5678/p_e5f6g7h/t_1761345678]
- **2025-10-26**: Extended Phase 4.7 with neurovep-analysis package [/t_1761456789/.]
```

**Benefits**:
- Visible change log within document
- Breadcrumb trail for each revision
- Understand plan evolution without git log
- Quick reference during execution

---

## Anti-Patterns to Avoid

### Execution Anti-Patterns

- ❌ **Skipping mandatory reading** - Starting work before reading embedded plans
- ❌ **Clobbering without archiving** - Collapsing TODOs without preservation
- ❌ **Missing archive contents** - Archive without breadcrumbs or todos JSON
- ❌ **Wrong STATUS** - Marking COMPLETED when work PARTIAL, ABORTED, or DEFERRED
- ❌ **Batch archiving** - Waiting until end to archive (lose forensic trail)
- ❌ **Missing package emoji** - Collapsed work without 📦 visual marker
- ❌ **No breadcrumb updates** - Completing phases without breadcrumb trail
- ❌ **Breaking observability** - Hiding progress from user, proceeding off-plan

---

## Philosophy: Observability Builds Trust

**The Observability Principle**:

When users can see:
- **What's planned** (roadmap with phases, criteria)
- **What's in progress** (numbered TODO hierarchy with embedded paths)
- **What's complete** (archived work with breadcrumbs, 📦 package markers)

They can **trust the agent** to execute complex multi-cycle work autonomously.

Without observability → anxiety, micromanagement, lost confidence.
With observability → trust, delegation, strategic partnership.

**The Mantra**: "A roadmap is a transparency window for users who need to trust the process. Read the plan. Execute systematically. Archive completely. Build trust through visibility."

---

## Related Policies

- **roadmaps_drafting.md**: Creating roadmaps (folder structure, templates, planning)
- **todo_hygiene.md**: TODO list discipline (breadcrumbs, hierarchy, completion)
- **delegation_guidelines.md**: SA execution (handoffs, checkpoints, reflections)
- **git_discipline.md**: Commit discipline (archive commits, forensic trail)

---

**Policy Established**: Roadmap execution requires mandatory reading discipline, numbered TODO integration, archive-then-collapse protocol, breadcrumb updates, and friction documentation. Observability through structured progress tracking builds trust for multi-cycle autonomous work.

**Core Wisdom**: "Read plans first. Number your phases. Archive before collapse. Document friction. Breadcrumbs enable resurrection. Observability enables trust."
