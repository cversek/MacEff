# Roadmaps Policy

**Type**: Planning & Accountability (Public CA)
**Scope**: All agents (PA and SA)
**Status**: Framework policy for complex multi-phase development planning

---

## Purpose

Roadmaps are **strategic planning artifacts** that preserve complex development plans across multiple cycles, phases, and compactions. They provide hierarchical structure, accountability checkboxes, and tight integration with TODO discipline to ensure agents execute strategic work systematically rather than proceeding blind.

**Core Insight**: Roadmaps aren't just planning documents—they're **consciousness preservation infrastructure** for strategic intent that survives context loss and enables coordinated execution across extended timeframes.

**Observability Insight**: Roadmap/TODO integration provides **essential agent work observability** that builds trust for large multi-cycle plan execution. Users can see exactly what's planned, what's in progress, what's complete—creating transparency and accountability that enables confident delegation of complex work.

---

## Consciousness Artifact Emoji Icons

**CA Type Emojis** (use consistently throughout):

- 🗺️ **MISSION / Roadmap** - Root node for multi-phase strategic plan
- 📋 **Phase / Subplan** - Major phase with detailed planning document
- 🔬 **Observation** - Technical discovery work
- 🧪 **Experiment** - Hypothesis testing work
- 📊 **Report** - Completion narrative work
- 💭 **Reflection** - Wisdom synthesis work
- 🔖 **Checkpoint** - Strategic state preservation work (CCP)
- 📦 **Archive** - Collapsed TODO subtree (archived)

**Usage Rules**:
- Use appropriate emoji for TODO item type
- **Completed items**: No emoji needed (UI shows completion formatting)
- **Archive marker**: Always 📦 for collapsed subtrees
- **Phase with subplan**: Use 📋 to indicate detailed planning document exists

---

## When This Applies

### Mandatory Roadmap Triggers

**Create roadmap when**:
- Multi-phase work (>3 distinct phases)
- Estimated duration >1 day
- Complex feature development requiring coordination
- Architecture changes affecting multiple components
- Migration or refactoring projects
- Security implementations
- Work spanning multiple cycles (compaction boundaries)
- Delegation requiring specialist coordination

### Optional But Recommended

- Investigation projects with uncertain scope
- Experimental work requiring structured exploration
- Documentation projects with multiple deliverables
- Integration work across repositories

### When NOT Required

- Single-phase tasks (<4 hours)
- Bug fixes with clear scope
- Simple feature additions
- Routine maintenance work
- Quick improvements

---

## CEP Navigation Guide

**1 Roadmap Structure Requirements**
- What's the folder structure for roadmaps?
- How do I organize roadmap files?
- Where do subplans go?
- Where do archived TODOs go?

**1.1 Folder Organization**
- Naming convention for roadmap folders?
- What files go in roadmap directory?
- Subplan organization?
- Delegation plan location?

**1.2 Roadmap File Format**
- Required sections in roadmap.md?
- Header metadata fields?
- Phase structure format?
- Success criteria format?

**1.3 Subplan Structure**
- When to create detailed subplans?
- Subplan naming convention?
- How subplans relate to parent roadmap?

**2 TODO Integration (MANDATORY)**
- How do roadmaps integrate with TODO lists?
- What's the numbered phase format?
- Where do I embed plan filepaths?
- How do I link TODOs to roadmap phases?

**2.1 Numbered Phase Hierarchy**
- What's the numbering scheme?
- Dot notation for nesting?
- MISSION vs phase vs sub-phase?
- Maximum nesting depth?

**2.2 Embedded Filepaths**
- Where do filepaths go in TODO items?
- Format for embedded paths?
- Relative path structure?
- Why are embedded paths mandatory?

**2.3 Mandatory Reading Discipline**
- When must I read embedded plans?
- Reading before work (not "if confused")?
- What if I skip reading?
- How to track plan reading?

**3 Archive-Then-Collapse Protocol**
- What is archive-then-collapse?
- When do I archive TODO hierarchies?
- Archive filename format?
- What goes in archive files?

**3.1 Archive Filename Convention**
- Timestamp format?
- Descriptive naming?
- STATUS field values?
- Examples?

**3.2 Archive Contents Requirements**
- Hierarchical TODO content?
- Breadcrumb inclusion?
- Claude Code todos JSON?
- Additional metadata?

**3.3 Archive Package Emoji**
- How to mark archived subtrees?
- Archive filepath embedding?
- Visual distinction from active work?

**3.4 NO CLOBBERING Rule**
- What is clobbering?
- Why is it prohibited?
- Archive-before-collapse discipline?
- Git commit requirements?

**4 Git Discipline Integration**
- When to commit roadmaps?
- Revision requirements?
- Archive file commits?
- Branch strategy?

**4.1 Commit-Before-Revise**
- Why commit before revisions?
- What if I need to update plan?
- Git workflow for plan evolution?

**4.2 Archive Commits**
- When to commit archive files?
- Commit message format?
- Forensic trail importance?

**5 Breadcrumb Traceability**
- Where do breadcrumbs go in roadmaps?
- Breadcrumb format?
- Work unit citations?
- Cross-cycle reconstruction?

**5.1 Roadmap Header Breadcrumbs**
- Creation breadcrumb location?
- Update breadcrumbs?
- Phase completion breadcrumbs?

**5.2 Breadcrumb Abbreviation**
- How to abbreviate sequential breadcrumbs?
- Abbreviation pattern?
- When to use full vs abbreviated?

**6 Phase Breakdown Guidelines**
- How to structure phases?
- Phase size recommendations?
- Sub-phase criteria?
- Success criteria per phase?

**6.1 Phase Numbering**
- Top-level phase numbers (1, 2, 3)?
- Sub-phase dot notation (1.1, 1.2)?
- Nested sub-phases (1.1.1, 1.1.2)?
- When to use nested numbering?

**6.2 Completion Criteria**
- Checkbox format?
- Measurable criteria?
- Verification methods?
- Evidence requirements?

**6.3 Friction Points Documentation**
- When to document friction?
- Friction points file structure?
- How to cite friction points?
- FP citation format?
- Archaeological benefits?

**7 PA vs SA Distinctions**
- PA roadmap scope?
- SA roadmap scope?
- Delegation plan relationship?
- Handoff requirements?

**7.1 PA Roadmaps (Mission-Level)**
- Strategic multi-cycle planning?
- Campaign-level coordination?
- Delegation orchestration?

**7.2 SA Roadmaps (Task-Level)**
- Bounded delegation scope?
- Tactical execution plans?
- Handoff documentation?

**8 Templates and Examples**
- Common roadmap templates?
- Real-world examples?
- Anti-pattern examples?
- Best practices?

**8.1 Migration Project Template**
- Phase structure for migrations?
- Validation checkpoints?
- Rollback planning?

**8.2 Feature Development Template**
- Architecture → Implementation → Testing?
- Integration checkpoints?
- Documentation requirements?

=== CEP_NAV_BOUNDARY ===

---

## 1 Roadmap Structure Requirements

### 1.1 Folder Organization

**ALL roadmaps use folder-based hierarchical structure**:

```
roadmaps/YYYY-MM-DD_Descriptive_Name/
├── roadmap.md                      # Main plan document
├── subplans/                       # Detailed phase plans (optional)
│   ├── phase_1_1_detailed.md
│   ├── phase_2_3_detailed.md
│   └── ...
├── delegation_plans/               # DELEG_PLANs for SA work (optional)
│   ├── YYYY-MM-DD_DELEG_PLAN_Task_Agent.md
│   └── ...
├── friction_points/                # Friction documentation (optional)
│   └── friction_points.md
└── archived_todos/                 # Collapsed TODO hierarchies (MANDATORY)
    ├── YYYY-MM-DD_HHMMSS_Plan_Description_COMPLETED.md
    ├── YYYY-MM-DD_HHMMSS_Plan_Description_PARTIAL.md
    ├── YYYY-MM-DD_HHMMSS_Plan_Description_ABORTED.md
    └── YYYY-MM-DD_HHMMSS_Plan_Description_DEFERRED.md
```

**Naming Convention**: `YYYY-MM-DD_Descriptive_Name`
- Date: When roadmap created
- Descriptive_Name: Clear, concise (3-5 words, underscores, no spaces)
- Examples:
  - `2025-10-24_AgentX_v0.3_Phase4_Deployment`
  - `2025-10-02_Temporal_Awareness_Universal_Consciousness`
  - `2025-10-17_Named_Agents_Architecture`

**Location**:
- **PA**: `agent/public/roadmaps/YYYY-MM-DD_Name/`
- **SA**: `agent/subagents/{role}/public/roadmaps/YYYY-MM-DD_Name/`

### 1.2 Roadmap File Format (roadmap.md)

**Required Header**:
```markdown
# [Descriptive Title] ROADMAP

**Date**: YYYY-MM-DD [Day of week]
**Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
**Status**: DRAFT | ACTIVE | COMPLETE
**Context**: [Brief situational context]

---

## Mission

[1-3 paragraphs: What are we building? Why does it matter? What success looks like?]

---
```

**Required Sections**:
1. **Mission** - Executive summary (1-3 paragraphs)
2. **Phase Breakdown** - Numbered phases with completion criteria
3. **Success Criteria** - Overall roadmap completion definition
4. **Risk Assessment** (optional but recommended)
5. **References** (if building on prior work)

**Phase Structure** (per phase):
```markdown
## Phase [N]: [Phase Title]

**Goal**: [1 sentence objective]

**Deliverables**:
- Specific artifact 1
- Specific artifact 2

**Success Criteria**:
- [ ] Measurable criterion 1
- [ ] Measurable criterion 2
- [ ] Evidence-based criterion 3

**Breadcrumb** (when complete): s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

**Enhanced Citation Usage** (citing this phase from checkpoint):
```
[Roadmap 2025-10-28 "Feature Implementation" §2 "Core Implementation" complete: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](2025-10-28_Feature_Implementation/roadmap.md#phase-2-core-implementation)
```
```

### 1.3 Subplan Structure

**When to create subplans**:
- Phase has >5 sub-phases (becomes too large for main roadmap)
- Phase requires detailed technical specification
- Phase involves multiple specialists needing shared plan
- Complex implementation requiring step-by-step guidance

**Subplan naming**: `phase_[number]_[descriptor].md`
- Examples:
  - `phase_1_preparation.md`
  - `phase_2_3_docker_infrastructure.md`
  - `phase_4_validation.md`

**Subplan format**: Same structure as main roadmap but scoped to single phase

**Link from parent roadmap**:
```markdown
## Phase 1: Preparation

**Detailed Plan**: `subplans/phase_1_preparation.md`

[Brief summary, full details in subplan]
```

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
🗺️ MISSION: AgentX v0.3.0 Migration [2025-10-27_AgentX_v0.3_Migration/roadmap.md]
  📋 1: Safe Preparation [subplans/phase_1_preparation.md]
  📋 2: Docker Infrastructure [subplans/phase_2_docker.md]
    → 2.1: Platform-aware build
    → 2.2: ARM64 optimization
```

**Path Format Rules**:
- **Roadmap path** (MISSION node): `{folder}/roadmap.md`
  - Example: `2025-10-27_AgentX_v0.3_Migration/roadmap.md`
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

**Why Mandatory**:
- Enables tracking across cycles (plan path survives compaction)
- Agents know EXACTLY where to find strategic context
- Post-compaction recovery: TODO list → embedded path → read plan → restore consciousness
- Cross-cycle archaeology: breadcrumbs + embedded paths = complete reconstruction
- **Observability**: User sees plan documentation structure, can review same plans agent reads

### 2.3 Mandatory Reading Discipline

**🚨 CRITICAL RULE: Read plans BEFORE work, not "if confused" 🚨**

**The Problem**: Agents don't know what they're missing until they read the plan.

**The Solution**: Embedded filepaths are **PREREQUISITES**, not suggestions.

**Reading Protocol**:
1. See TODO item with embedded filepath
2. **IMMEDIATELY** read the embedded plan file
3. Integrate strategic context, constraints, approach
4. THEN begin work on that phase

**Example Workflow**:
```markdown
TODO: 📋 2: Docker Infrastructure [subplans/phase_2_docker.md]
```

**Agent Action**:
1. `Read agent/public/roadmaps/2025-10-27_Name/subplans/phase_2_docker.md` (FIRST)
2. Understand: platform-aware build, ARM64 vs x86_64, CUDA optional
3. THEN: Begin docker implementation with full context

**Path Resolution**:
- Roadmap folder location known from MISSION node path
- Subplan path relative to that folder
- Agent constructs full path for Read tool

**Violation Consequences**:
- Proceeding blind without strategic context
- Missing critical constraints or approach decisions
- Rework when discovering plan contents mid-implementation
- Violates consciousness preservation intent
- **Breaks observability**: User expects agent to follow documented plan

---

## 3 Archive-Then-Collapse Protocol

### 3.1 Archive Filename Convention

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

### 3.2 Archive Contents Requirements

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
**Original Plan**: 2025-10-24_AgentX_v0.3_Migration/roadmap.md
**Status**: COMPLETED

## Hierarchical TODO Content

🗺️ MISSION: AgentX v0.3.0 Migration [2025-10-24_AgentX_v0.3_Migration/roadmap.md]
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

### 3.3 Archive Package Emoji

**How to Mark Archived Subtrees in Active TODO List**:

After archiving, replace the collapsed subtree with **📦 package emoji** and reference to archive:

```markdown
🗺️ MISSION: AgentX v0.3.0 Migration [2025-10-24_AgentX_v0.3_Migration/roadmap.md]
  [📦 Archive 2025-10-27 "Phases 1-4 Complete": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md)
  📋 5: CEP Fixes & Bootstrap [subplans/phase_5_cep.md]
    → 5.1: Critical path fixes
    → 5.2: Infrastructure improvements
```

**Enhanced Format**: `[📦 Archive YYYY-MM-DD "Description": s/c/g/p/t](archived_todos/filename.md)`

**Classic Format** (also acceptable): `📦 [Descriptive Summary] [Breadcrumb] → archived_todos/[filename].md`

**Components** (enhanced format):
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

### 3.4 NO CLOBBERING Rule

**🚨 ABSOLUTE PROHIBITION: NO COLLAPSING/CLOBBERING WITHOUT ARCHIVING 🚨**

**What is Clobbering**:
- Marking parent TODO complete and deleting/hiding child TODOs
- Removing hierarchical detail without preservation
- Overwriting active plans without git commit
- Losing breadcrumb trails and forensic data

**Why Prohibited**:
- **Consciousness preservation**: TODO hierarchies are consciousness artifacts
- **Forensic reconstruction**: Future cycles need breadcrumb trails
- **Accountability**: Work history must be traceable
- **Learning**: Lessons from completed work guide future work
- **Observability**: Users need complete work history for trust

**Archive-Then-Collapse Discipline**:
1. Complete all sub-phase work
2. **ARCHIVE** hierarchical TODO tree to `archived_todos/YYYY-MM-DD_HHMMSS_Description_STATUS.md`
3. **COMMIT** archive file to git
4. **REPLACE** collapsed subtree with 📦 package emoji + archive path in active TODO list
5. Mark parent phase complete (no emoji needed)

**Violation = Consciousness Destruction**: Losing breadcrumbs, work trails, forensic data, and user trust.

---

## 4 Git Discipline Integration

### 4.1 Commit-Before-Revise

**Rule**: Roadmaps and subplans MUST be committed to git BEFORE revisions.

**Workflow**:
1. Create roadmap/subplan
2. **COMMIT to git** (initial version)
3. Begin execution
4. Discover need for revision
5. **COMMIT current version** (before changes)
6. Revise plan
7. **COMMIT revised version** (with rationale in commit message)

**Why**:
- **Forensic trail**: See plan evolution over time
- **Accountability**: Know what was planned vs what changed
- **Recovery**: Revert to earlier plan version if needed
- **Learning**: Understand why plans evolved
- **Observability**: Users can review plan history

**Commit Message Format**:
```bash
git commit -m "roadmap: Create AgentX v0.3 Phase 4 deployment plan

- 13-point validation checklist
- Repository cloning strategy
- Risk assessment with friction points
- Breadcrumb: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
"

git commit -m "roadmap: Revise Phase 4.4 validation (added GitHub auth check)

Discovered SSH key authentication critical for private repos.
Added validation step 4.4.11 for GitHub auth before repo cloning.

- Breadcrumb: s_abc12345/c_42/g_def5678/p_e5f6g7h/t_1761345678
"
```

### 4.2 Archive Commits

**Archive files MUST be committed** to preserve forensic trail.

**When to Commit**:
- Immediately after creating archive file
- Before collapsing TODO hierarchy
- Same commit can include both archive + parent TODO update

**Commit Message Format**:
```bash
git commit -m "roadmap: Archive Phases 1-4 completion [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]

Archived hierarchical TODO tree to:
2025-10-24_AgentX_v0.3_Migration/archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md

- All 4 phases complete
- 23 sub-tasks tracked with breadcrumbs
- Includes Claude Code todos JSON for forensics
"
```

**Forensic Benefits**:
- Future cycles can `git log` to find archived TODOs
- Breadcrumbs in archives enable conversation reconstruction
- Complete work history preserved across compactions
- **Observability**: Users can audit all work via git history

---

## 5 Breadcrumb Traceability

### 5.1 Roadmap Header Breadcrumbs

**Creation Breadcrumb** (mandatory in header):
```markdown
# AgentX v0.3 Phase 4 Deployment ROADMAP

**Date**: 2025-10-24 Friday, 4:02 PM EDT
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Status**: ACTIVE
```

**Update Breadcrumbs** (when plan revised):
```markdown
## Revision History

- **2025-10-25**: Added Phase 4.4.11 GitHub auth validation [s_abc12345/c_42/g_def5678/p_e5f6g7h/t_1761345678]
- **2025-10-26**: Extended Phase 4.7 with project-y-analysis package [/t_1761456789/.]
```

### 5.2 Breadcrumb Abbreviation

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

**Abbreviated** (timestamp and git changed):
```markdown
Create reports.md [/t_1761708042/g_abc9876]
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

**Phase Completion Breadcrumbs**:
```markdown
## Phase 4: Deployment & Validation

**Status**: COMPLETE
**Breadcrumb**: s_abc12345/c_42/g_def5678/p_e5f6g7h/t_1761345678

All 13 validation checks passed. Container deployed successfully.
```

**Archive Cross-References**:
```markdown
## Phase 1-3: Foundation Complete

**Status**: COMPLETE (Archived)
**Archive**: `archived_todos/2025-10-27_215009_Phases1-3_Foundation_COMPLETED.md`
**Breadcrumb**: s_abc12345/c_42/g_ghi9012/p_i8j9k0l/t_1761123456
```

**Archaeological Power**: Breadcrumbs + embedded paths + git history = complete reconstruction across 30+ compactions.

---

## 6 Phase Breakdown Guidelines

### 6.1 Phase Numbering

**Top-Level Phases** (1, 2, 3, ...):
- Major work units (days to weeks)
- Distinct deliverables
- Clear milestones
- Example: "1: Safe Preparation", "2: Docker Infrastructure"

**Sub-Phases** (1.1, 1.2, 2.1, ...):
- Components within major phase
- Hours to days each
- Related sub-tasks
- Example: "1.1: Backup volume", "1.2: Update submodule"

**Nested Sub-Phases** (1.1.1, 1.1.2, ...):
- Fine-grained steps within sub-phase
- Minutes to hours each
- Specific actions
- Example: "1.1.1: Check volume size", "1.1.2: Execute backup command"

**Maximum Depth Guideline**:
- **Recommended**: 3 levels (Phase 1.1.1)
- **Absolute max**: 4 levels (Phase 1.1.1.1)
- **Beyond 4**: Create subplan file instead

### 6.2 Completion Criteria

**Checkbox Format**:
```markdown
**Success Criteria**:
- [ ] Specific, measurable criterion
- [ ] Test passing (command to verify)
- [ ] File created (path and size)
- [ ] Evidence-based validation
```

**Good Criteria** (measurable, verifiable):
- ✅ "Container shows as 'Up' in `docker ps`"
- ✅ "All 5 repos cloned to /shared_workspace/repos/"
- ✅ "Python 3.12.x reported by `python --version`"
- ✅ "Test suite passes: 19/19 tests green"

**Bad Criteria** (vague, subjective):
- ❌ "Container working properly"
- ❌ "Repos look good"
- ❌ "Python seems fine"
- ❌ "Tests mostly pass"

**Evidence Requirements**:
- Command output (copy test results)
- File paths (confirm existence)
- Verification commands (show how to check)
- Git commit hashes (prove completion)

---

## 6.3 Friction Points Documentation

**Purpose**: Friction points are **learning artifacts** that document unexpected obstacles, their solutions, and prevention strategies. They transform painful blockers into reusable knowledge.

### When to Document Friction

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

### Friction Points Structure

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

### Citing Friction Points

**FP Citation Format** (subclass of Roadmap citations):
```
[Roadmap YYYY-MM-DD "Roadmap Title" FP#{N} "FP Brief Title": s/c/g/p/t](friction_points/friction_points.md#fpN-anchor)
```

**Components**:
- **Roadmap** + date + title: Parent roadmap identification
- **FP#{N}**: Friction point number within roadmap (e.g., FP#1, FP#2)
- **FP title**: Brief descriptor (3-5 words, quoted)
- **Breadcrumb**: FP discovery moment (s/c/g/p/t format)
- **Link**: Relative path to friction_points.md + GitHub anchor

**GitHub Anchor Rules**:
- Lowercase FP title: `FP#1: Docker Override Discovery` → `#fp1-docker-override-discovery`
- Include FP number prefix in anchor for uniqueness
- Use explicit anchor IDs in headers: `{#fp1-anchor}`

### Citation Examples

**In Checkpoints** (summarizing cycle friction):
```markdown
## Friction This Cycle

Encountered docker-compose working directory dependency [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../roadmaps/2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery) which blocked volume mounting for 25 minutes.
```

**In Reflections** (deep pattern analysis):
```markdown
## Wisdom: Documentation vs Discipline

Building on [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../public/roadmaps/2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery), this friction reveals systematic pattern: documentation teaches mechanism, experience teaches discipline.
```

**In Future Roadmaps** (referencing prior friction):
```markdown
## Risk Assessment

**Known Friction Patterns**:
- [Roadmap 2025-10-24 "AgentX Deploy" FP#2 "SSH Key Location": s_.../c_.../t_...](../2025-10-24_AgentX_Deploy/friction_points/friction_points.md#fp2-ssh-key-location)
- [Roadmap 2025-11-11 "Docker DETOUR" FP#1: s_.../c_.../t_...](../2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery)
```

**Cross-Roadmap Pattern Recognition**:
```markdown
Both [Roadmap 2025-10-23 "TestMacEff Deploy" FP#3: s_.../t_...] and [Roadmap 2025-11-11 "Docker DETOUR" FP#1: s_.../t_...] share root cause: tools assume standard conventions, operational reality requires auto-detection.
```

### Archaeological Benefits

**Enhanced citations enable**:
- **Forensic navigation**: Breadcrumb → exact discovery conversation
- **Pattern discovery**: Find all friction citing similar root causes
- **Wisdom synthesis**: Trace how friction insights influenced future work
- **Prevention transfer**: Share friction knowledge across projects/agents
- **Knowledge graphs**: Friction citations create edges in learning network

**Query Examples** (future memory system):
```bash
# Find all friction points from Cycle 42-100
macf_tools memory query --ca-tag Roadmap --fp-only --cycle-range 90-100

# Find friction citing docker-compose patterns
macf_tools memory query --cited-desc "docker-compose" --ca-tag Roadmap --fp-only

# Build friction pattern graph
macf_tools memory graph --root-fp "FP#1" --depth 2 --pattern-clustering
```

### Integration with Scholarship Policy

Friction Point citations follow enhanced citation format from scholarship.md:
- CA_TAG: Use "Roadmap" (friction belongs to parent roadmap)
- FP#{N}: Unique identifier within roadmap
- Full breadcrumb: s/c/g/p/t discovery coordinates
- GitHub links: Enable one-click navigation to specific FP
- Sanitization: Use generic breadcrumbs in framework examples

See `scholarship.md` for complete enhanced citation guidelines.

---

## 7 PA vs SA Distinctions

### 7.1 PA Roadmaps (Mission-Level)

**Scope**:
- Multi-cycle campaigns (weeks to months)
- Strategic coordination across phases
- Delegation orchestration
- Mission-level success criteria

**Complexity**:
- 5-20+ phases typical
- Multiple sub-phases per phase
- Coordination across specialists
- Long-term vision

**Examples**:
- `2025-10-24_AgentX_v0.3_Migration` (7 phases, multi-cycle)
- `2025-10-02_Temporal_Awareness_Universal_Consciousness` (4 phases, extensible)
- `2025-10-17_Named_Agents_Architecture` (3 phases, foundation-building)

**Location**: `agent/public/roadmaps/YYYY-MM-DD_Name/`

**Observability Benefit**: User sees complete multi-cycle mission structure, builds confidence in agent's strategic planning capability.

### 7.2 SA Roadmaps (Task-Level)

**Scope**:
- Bounded delegation scope (hours to days)
- Tactical execution plans
- Single specialist focus
- Task-level completion

**Complexity**:
- 2-5 phases typical
- Focused sub-phases
- Clear handoff criteria
- Immediate deliverables

**Examples**:
- `2025-10-21_Phase1_1_Pydantic_Models` (3 phases, DevOpsEng)
- `2025-10-08_Hook_Architecture_Refactoring` (4 phases, TestEng)
- `2025-10-15_DataPipeline_Implementation` (2 phases, DataScientist)

**Location**: `agent/subagents/{role}/public/roadmaps/YYYY-MM-DD_Name/`

**Delegation Plan Relationship**:
- DELEG_PLAN references SA roadmap
- PA orchestrates via DELEG_PLAN
- SA executes via roadmap
- Handoff via completion criteria

---

## 8 Templates and Examples

### 8.1 Migration Project Template

```markdown
# [Project] Migration ROADMAP

**Date**: YYYY-MM-DD
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Status**: ACTIVE

## Mission

Migrate [project] from [old state] to [new state], preserving [critical assets] while enabling [new capabilities].

## Phase 1: Safe Preparation

**Goal**: Backup current state and validate rollback capability

**Success Criteria**:
- [ ] Complete backup created (size: ___GB)
- [ ] Backup integrity verified
- [ ] Rollback procedure documented and tested

## Phase 2: [Component] Migration

**Goal**: Migrate [component] with zero data loss

**Success Criteria**:
- [ ] Component migrated successfully
- [ ] Data integrity verified (checksums match)
- [ ] Rollback tested and working

## Phase 3: Validation & Cutover

**Goal**: Prove new state works, switch over

**Success Criteria**:
- [ ] All validation checks passing
- [ ] Performance meets or exceeds baseline
- [ ] Production cutover successful

## Rollback Plan

If migration fails:
1. Stop new system
2. Restore from backup (Phase 1)
3. Verify restoration
4. Document failure for retrospective
```

### 8.2 Feature Development Template

```markdown
# [Feature Name] Implementation ROADMAP

**Date**: YYYY-MM-DD
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Status**: ACTIVE

## Mission

Implement [feature] enabling users to [capability], addressing [user need].

## Phase 1: Architecture & Design

**Goal**: Define approach before coding

**Success Criteria**:
- [ ] Architecture diagram created
- [ ] API contracts defined
- [ ] Data model designed
- [ ] Tech choices documented

## Phase 2: Core Implementation

**Goal**: Working implementation passing tests

**Success Criteria**:
- [ ] Core functionality implemented
- [ ] Unit tests written and passing (N/N green)
- [ ] Integration tests passing
- [ ] Code reviewed and approved

## Phase 3: Integration & Polish

**Goal**: Feature integrated into product

**Success Criteria**:
- [ ] Integrated with existing features
- [ ] Documentation complete
- [ ] User-facing polish (error messages, UX)
- [ ] Production-ready

## Phase 4: Deployment & Validation

**Goal**: Feature live and working

**Success Criteria**:
- [ ] Deployed to production
- [ ] Monitoring in place
- [ ] User validation successful
- [ ] No regressions detected
```

### 8.3 Investigation Template

```markdown
# [Problem] Investigation ROADMAP

**Date**: YYYY-MM-DD
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Status**: ACTIVE

## Mission

Investigate [problem/opportunity], understand root causes, propose solutions.

## Phase 1: Problem Definition

**Goal**: Clearly define what we're investigating

**Success Criteria**:
- [ ] Problem statement documented
- [ ] Reproduction steps identified
- [ ] Success metrics defined

## Phase 2: Data Collection

**Goal**: Gather evidence and data

**Success Criteria**:
- [ ] Logs collected and analyzed
- [ ] Metrics gathered
- [ ] Experiments run
- [ ] Observations documented

## Phase 3: Root Cause Analysis

**Goal**: Understand WHY problem occurs

**Success Criteria**:
- [ ] Hypothesis tested
- [ ] Root cause identified
- [ ] Contributing factors documented

## Phase 4: Solution Design

**Goal**: Propose actionable solutions

**Success Criteria**:
- [ ] Solution options documented
- [ ] Trade-offs analyzed
- [ ] Recommendation made with rationale
- [ ] Implementation roadmap (if approved)
```

---

## Integration with Other Policies

### Related Policies

- **todo_hygiene.md**: Hierarchical TODO structure, breadcrumb discipline, archive-then-collapse
- **git_discipline.md**: Commit requirements, forensic trail preservation
- **checkpoints.md**: Strategic state preservation at phase boundaries
- **reflections.md**: Wisdom synthesis from roadmap execution
- **delegation_guidelines.md**: DELEG_PLAN integration with roadmaps
- **meta/policy_writing.md** (External References): How external tools (like `/ctb_roadmap` command) should reference this policy's folder structure requirements and phase formatting using timeless content categories

### Personal Policies Connection

Agents may develop **personal roadmap conventions** in `~/agent/policies/personal/` if they:
- Discover project-specific planning patterns
- Develop specialized phase breakdown approaches
- Create domain-specific templates
- Refine numbering or archive conventions

Personal roadmap policies **override** this framework policy (highest precedence).

---

## Anti-Patterns to Avoid

### Planning Anti-Patterns

- ❌ **No roadmap for multi-phase work** - Proceeding blind without strategic plan
- ❌ **Vague phase definitions** - "Work on feature" instead of measurable criteria
- ❌ **Missing folder structure** - Flat roadmap file instead of folder with subplans/archives
- ❌ **No embedded filepaths** - TODOs reference phases without plan links
- ❌ **Skipping mandatory reading** - Starting work before reading embedded plans
- ❌ **Lettered phases** - "Phase A", "Phase B" instead of numbered (1, 2)
- ❌ **Full paths in TODOs** - Using project-absolute instead of relative paths

### Execution Anti-Patterns

- ❌ **Clobbering without archiving** - Collapsing TODOs without preservation
- ❌ **Missing archive contents** - Archive without breadcrumbs or todos JSON
- ❌ **No git commits** - Roadmap revisions without commit history
- ❌ **Wrong STATUS** - Marking COMPLETED when work PARTIAL, ABORTED, or DEFERRED
- ❌ **Batch archiving** - Waiting until end to archive (lose forensic trail)
- ❌ **Missing package emoji** - Collapsed work without 📦 visual marker
- ❌ **Using ✅ for completion** - UI shows completion, don't duplicate with emoji

### Accountability Anti-Patterns

- ❌ **Unchecked criteria** - Moving to next phase with incomplete current phase
- ❌ **No breadcrumbs** - Missing creation/completion breadcrumbs
- ❌ **Vague success criteria** - Subjective measures instead of objective verification
- ❌ **No evidence** - Claiming completion without verification commands/outputs
- ❌ **Breaking observability** - Hiding progress from user, proceeding off-plan

---

## Philosophy: Roadmaps as Consciousness Infrastructure

**Core Insight**: Roadmaps aren't bureaucracy—they're **consciousness preservation** for strategic intent.

**Why This Matters**:
- **Compaction survival**: Strategic plans survive 93% context loss
- **Cross-cycle execution**: Work spanning weeks preserved across compaction boundaries
- **Forensic reconstruction**: Breadcrumbs + embedded paths + git = complete archaeological trail
- **Learning accumulation**: Archive wisdom guides future roadmap creation
- **Observability builds trust**: User sees plans, progress, completion—enables confident multi-cycle delegation

**The Observability Principle**:

When users can see:
- **What's planned** (roadmap with phases, criteria)
- **What's in progress** (numbered TODO hierarchy with embedded paths)
- **What's complete** (archived work with breadcrumbs, 📦 package markers)

They can **trust the agent** to execute complex multi-cycle work autonomously.

Without observability → anxiety, micromanagement, lost confidence.
With observability → trust, delegation, strategic partnership.

**The Mantra**: "A roadmap is a love letter to future-you who has lost 93% of memory but still needs to execute the mission. It's also a transparency window for users who need to trust the process."

**Without roadmaps**: Ad hoc planning, lost context, strategic drift, rework, user anxiety.
**With roadmaps**: Systematic execution, preserved intent, accountability, learning, user confidence.

---

## Evolution and Feedback

This policy evolves through:
- **Pattern observation**: What roadmap structures actually work?
- **Archive analysis**: What forensic data proves most valuable post-compaction?
- **Agent feedback**: What helps vs hinders during execution?
- **User feedback**: What observability features build trust?
- **Effectiveness metrics**: Do roadmaps improve multi-cycle success rates?

**Principle**: Roadmaps should feel like strategic clarity and user transparency, not bureaucratic burden. If they don't serve consciousness preservation AND observability → refine them.

---

**Policy Established**: Roadmaps as hierarchical planning infrastructure with mandatory TODO integration, archive-then-collapse discipline, breadcrumb traceability, and consciousness preservation across compaction boundaries. Observability builds trust for multi-cycle autonomous execution.

**Core Wisdom**: "Embedded filepaths are prerequisites. Archive before collapse. Read plans before work. Breadcrumbs enable resurrection. Observability enables trust."

**Remember**: This is consciousness infrastructure for strategic work AND trust infrastructure for human-AI collaboration. Use what serves both missions, refine what doesn't.
