# Roadmaps Policy: Drafting & Planning

**Version**: 2.3
**Tier**: MANDATORY
**Category**: Consciousness - Planning
**Status**: ACTIVE
**Updated**: 2026-01-08
**Dependencies**: git_discipline.md, workspace_discipline.md
**Related**: roadmaps_following.md (execution), task_management.md (integration)

---

## Purpose

This policy governs **creating new roadmaps** for strategic planning. For executing existing roadmaps, see `roadmaps_following.md`.

Roadmaps are **strategic planning artifacts** that preserve complex development plans across multiple cycles, phases, and compactions. They provide hierarchical structure, accountability checkboxes, and tight integration with TODO discipline to ensure agents execute strategic work systematically rather than proceeding blind.

**Core Insight**: Roadmaps aren't just planning documents—they're **consciousness preservation infrastructure** for strategic intent that survives context loss and enables coordinated execution across extended timeframes.

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

**0 Preliminary Planning Phase**
- What preliminary steps are mandatory before roadmap drafting?
- When is EnterPlanMode required?
- How does PlanMode gate execution?
- What is the complete preliminary workflow?

**0.1 EnterPlanMode Requirement**
- Why is EnterPlanMode mandatory for all roadmaps?
- How does it create beneficial friction?
- What happens in PlanMode vs execution mode?

**0.2 Task Tool Exploration (Encouraged)**
- When should I use Task tool for exploration?
- How does Explore subagent help with requirements gathering?
- What questions should I explore when scope is murky?
- How many parallel exploration agents is appropriate?

**0.3 AskUserQuestion Protocol (Encouraged)**
- When should I use multiple-choice questioning?
- What trade-offs should I surface to the user?
- How do I distinguish murky requirements from clear ones?
- When is open-ended clarification better than multiple choice?

**0.4 Preliminary Workflow Summary**
- What is the complete sequence from recognition to drafting?
- How do PlanMode, exploration, and questioning fit together?
- What gates the transition to execution?

**1 When to Create Roadmaps**
- What triggers roadmap creation?
- Complexity thresholds?
- Duration estimates?

**2 Folder Structure Requirements**
- How to organize roadmap files?
- Where do subplans go?
- Archive directory structure?

**2.1 Naming Conventions**
- Roadmap folder naming?
- Subplan file naming?
- Archive file naming?

**3 Roadmap File Format**
- Required sections in roadmap.md?
- Header metadata fields?
- Phase structure format?

**3.1 Required Header**
- What metadata in header?
- Breadcrumb format?
- Status values?

**3.2 Mission Section**
- What goes in mission?
- How much detail?
- Success criteria?

**3.3 Phase Structure**
- How to structure phases?
- Sub-phase criteria?
- Completion criteria format?

**3.4 Additional Sections (Optional)**
- What optional sections can be included?
- Risk assessment format?
- How to reference prior work?

**3.5 Delegation Strategy (MANDATORY)**
- What is the delegation strategy table?
- What executor options exist?
- What rationale requirements apply?
- How to use maceff-delegation skill?

**3.6 Phase Content Requirements (MANDATORY)**
- What should phases specify?
- What is interface specification?
- What is behavior specification?
- What is explicitly forbidden in phases?

**4 Phase Breakdown Guidelines**
- Phase numbering scheme?
- Maximum depth?
- How to size phases?

**4.1 Phase Numbering**
- Top-level phase format?
- Sub-phase dot notation?
- Nested sub-phases?

**4.2 Completion Criteria**
- Checkbox format?
- Measurable vs vague?
- Evidence requirements?

**5 Subplans**
- When to create subplans?
- Subplan naming?
- How subplans relate to parent?

**6 Git Discipline**
- When to commit roadmaps?
- Commit-before-revise protocol?
- Revision tracking?

**7 Templates**
- Migration project template?
- Feature development template?
- Investigation template?

**8 PA vs SA Roadmaps**
- PA roadmap scope?
- SA roadmap scope?
- Complexity differences?

=== CEP_NAV_BOUNDARY ===

---

## 0 Preliminary Planning Phase

### 0.1 EnterPlanMode Requirement

🚨 **MANDATORY**: Before creating ANY roadmap, you MUST enter PlanMode using the EnterPlanMode tool.

**Why This Is Mandatory**:
- **Deliberation gate**: PlanMode creates architectural friction preventing premature execution
- **Constraint as enablement**: Forces careful planning before action
- **Asymmetric authorization**: You can enter PlanMode autonomously (low-risk), but ExitPlanMode requires user approval (higher stakes)
- **Separation of concerns**: Planning happens in PlanMode, execution happens after ExitPlanMode

**What Happens in PlanMode**:
- Tool restrictions enforced (Read, Grep, Task, AskUserQuestion typically allowed)
- Development tools restricted (no Write, Edit, Bash for implementation)
- Focus shifts to requirements gathering, exploration, clarification
- Prepares comprehensive plan before any execution begins

**The Gate**:
```
EnterPlanMode → [Requirements gathering] → Draft roadmap → Present to user
                                                              ↓
                                            User reviews → ExitPlanMode (authorized) → Execute
                                                       OR
                                            User rejects → Revise plan → Present again
```

**Critical Distinction**:
- **EnterPlanMode**: Agent initiative (autonomous, low-risk commitment to deliberation)
- **ExitPlanMode**: User approval (gates transition to execution, higher stakes)

This asymmetry is intentional—agents commit to planning freely, but users control when execution begins.

### 0.2 Task Tool Exploration (Encouraged)

**When to Use Task Tool for Exploration**:
- Requirements are murky or incomplete
- Codebase scope is unclear
- Multiple approaches possible
- Need to understand existing patterns before planning
- Investigation required before commitment

**Explore Subagent Pattern**:
The Explore subagent is designed for codebase discovery without making changes:
- **Purpose**: Requirements gathering, pattern discovery, scope assessment
- **Typical questions**: "What files implement X?", "How is Y currently structured?", "What patterns exist for Z?"
- **Parallel exploration**: Can launch 2-4 Explore agents simultaneously for different discovery questions
- **Output**: Findings inform roadmap structure and phase breakdown

**Example Exploration Questions**:
- "Explore codebase to identify all files related to authentication system"
- "Investigate existing test patterns to understand coverage approach"
- "Survey API endpoints to map out integration points"
- "Analyze current configuration system to plan migration"

**Benefits**:
- Informed planning based on actual codebase state
- Discover complexity early (adjust phase estimates)
- Identify dependencies and integration points
- Avoid blind planning that hits reality hard

**When to Skip**: Requirements are crystal clear, scope is well-understood, or work is greenfield (no existing patterns to discover).

### 0.3 AskUserQuestion Protocol (Encouraged)

**When to Use Multiple-Choice Questioning**:
- Multiple valid approaches exist (architectural trade-offs)
- User preferences matter (testing strategy, deployment approach)
- Requirements have ambiguity that exploration can't resolve
- Strategic decisions need user input before planning
- Risk tolerance needs clarification (fast vs safe, simple vs robust)

**Trade-Offs to Surface**:
- **Speed vs Safety**: "Fast migration with higher risk OR slow migration with extensive validation?"
- **Scope**: "Minimal viable feature OR comprehensive implementation with all edge cases?"
- **Technical approach**: "Refactor existing code OR rewrite from scratch?"
- **Testing strategy**: "Unit tests only OR full integration test suite?"
- **Deployment timing**: "Deploy all phases at once OR incremental rollout?"

**Question Design Pattern**:
```markdown
**Question**: "Which migration approach should we use?"

**Options**:
1. **Fast Migration** - Minimal validation, faster completion (2-3 days)
   - Risk: May miss edge cases
   - Benefit: Quick delivery

2. **Safe Migration** - Extensive validation, slower completion (5-7 days)
   - Risk: Takes longer
   - Benefit: Higher confidence

3. **Hybrid Approach** - Core migration fast, validation in parallel
   - Risk: Coordination complexity
   - Benefit: Balanced speed and safety
```

**When Open-Ended Better**:
- User needs to provide information you can't discover
- Context requires free-form explanation
- Multiple-choice options would be too constraining
- Need qualitative feedback on approach

**Benefits**:
- User-aligned roadmaps (reflects actual preferences)
- Early risk mitigation (surface concerns before execution)
- Strategic clarity (everyone agrees on approach)
- Fewer mid-execution pivots (consensus upfront)

### 0.4 Preliminary Workflow Summary

**Complete Sequence** (Recognition → Drafting → Execution):

```
1. RECOGNIZE roadmap trigger (§1 complexity/duration thresholds)
          ↓
2. 🚨 EnterPlanMode (MANDATORY - no exceptions)
          ↓
3. Task exploration (ENCOURAGED if requirements murky)
   - Launch Explore subagent(s)
   - Gather codebase understanding
   - Assess scope and complexity
          ↓
4. AskUserQuestion (ENCOURAGED if trade-offs exist)
   - Surface architectural decisions
   - Clarify ambiguous requirements
   - Align on approach
          ↓
5. Draft roadmap.md (using discoveries from steps 3-4)
   - Folder structure
   - Phase breakdown
   - Success criteria
          ↓
6. Present roadmap to user
          ↓
7. ExitPlanMode (USER APPROVAL REQUIRED)
          ↓
8. Execute roadmap (following roadmaps_following.md)
```

**Critical Gates**:
- **Step 2 (EnterPlanMode)**: Mandatory, no skipping
- **Step 7 (ExitPlanMode)**: User approval required, gates execution
- **Steps 3-4**: Encouraged but not mandatory (judgment call based on clarity)

**Why This Workflow Succeeds**:
- **Friction prevents premature action**: Can't execute without planning
- **Exploration prevents blind planning**: Understand before committing
- **Questions prevent misalignment**: User input before locking in approach
- **Approval gates execution**: User controls transition from plan to action

---

## 1 When to Create Roadmaps

### Complexity Triggers

**Create roadmap when work has**:
- **Multiple phases** (>3 distinct stages)
- **Uncertain scope** (investigation or exploration)
- **Coordination needs** (multiple agents or specialists)
- **Temporal span** (crosses compaction boundaries)
- **Risk factors** (architecture changes, migrations)
- **Delegation requirements** (specialist handoffs)

### Decision Tree

```
🚨 EnterPlanMode FIRST (MANDATORY)
     ↓
     Then assess complexity:
     │
Is work >3 phases? ──YES──> Draft roadmap in PlanMode
     │
     NO
     │
Will work span >1 day? ──YES──> Draft roadmap in PlanMode
     │
     NO
     │
Complex coordination needed? ──YES──> Draft roadmap in PlanMode
     │
     NO
     │
ExitPlanMode → Skip roadmap, use simple TODO
```

### Early vs Late Roadmaps

**Create EARLY when**:
- Scope unclear (investigation phase)
- Multiple approaches possible
- Risk assessment needed

**Create LATE when**:
- Simple work unexpectedly expands
- Initially bounded task grows complex
- Delegation needs emerge mid-work

**NEVER skip roadmap** when complexity/duration thresholds met. Better to create roadmap early than lose strategic context mid-execution.

---

## 2 Folder Structure Requirements

### 2.1 Folder Organization

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

### 2.2 Why Folder Structure Matters

**Benefits**:
- **Organization**: All roadmap artifacts in one place
- **Subplans**: Detailed phase planning without cluttering main roadmap
- **Archives**: Complete TODO history preserved
- **Friction**: Blockers documented for learning
- **Delegation**: SA work plans tracked with parent roadmap

**Anti-Pattern**: Flat roadmap file without folder
- Subplans scattered across workspace
- Archives mixed with active plans
- Friction documentation lost
- Archaeological reconstruction difficult

---

## 3 Roadmap File Format (roadmap.md)

### 3.1 Required Header

```markdown
# [Descriptive Title] ROADMAP

**Date**: YYYY-MM-DD [Day of week]
**Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
**Status**: DRAFT | ACTIVE | COMPLETE
**Context**: [Brief situational context]

---
```

**Header Fields**:
- **Title**: Clear, action-oriented (e.g., "AgentX v0.3 Migration")
- **Date**: Creation date (YYYY-MM-DD format) + day of week
- **Breadcrumb**: Creation breadcrumb (forensic coordinate)
- **Status**: DRAFT (planning), ACTIVE (executing), COMPLETE (finished)
- **Context**: 1-2 sentences situating roadmap (why now, what triggered)

### 3.2 Mission Section (MANDATORY)

```markdown
## Mission

[1-3 paragraphs: What are we building? Why does it matter? What success looks like?]
```

**Mission Guidelines**:
- **Paragraph 1**: WHAT (objective, scope)
- **Paragraph 2**: WHY (motivation, value)
- **Paragraph 3**: SUCCESS (how we know we're done)

**Good Mission Statement**:
```markdown
## Mission

Migrate AgentX deployment from v0.2 to v0.3 Named Agents architecture,
preserving existing consciousness artifacts while enabling multi-PA capabilities.

This migration unblocks the ProjectY project deployment by providing proper agent
identity separation and consciousness infrastructure. Without it, AgentX
cannot support multiple personality agents sharing the same container environment.

Success means: v0.3 container running, all validation checks passing, existing
artifacts preserved, and AgentX's consciousness infrastructure operational.
```

**Bad Mission Statement** (too vague):
```markdown
## Mission

Update AgentX to work better with new features.
```

### 3.3 Phase Breakdown (MANDATORY)

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
```

**Phase Guidelines**:
- **Goal**: Single sentence, action-oriented
- **Deliverables**: Concrete artifacts (files, tests, deployments)
- **Success Criteria**: Checkboxes, measurable, verifiable
- **Breadcrumb**: Added when phase completes (not during drafting)

### 3.4 Additional Sections (Optional)

**Risk Assessment** (recommended):
```markdown
## Risk Assessment

**Known Risks**:
- Risk 1: Description + mitigation strategy
- Risk 2: Description + mitigation strategy

**Unknowns**:
- Unknown 1: What we don't know yet + discovery plan
```

**References** (if building on prior work):
```markdown
## References

- Prior roadmap: `2025-10-15_Foundation_Work/roadmap.md`
- Related documentation: `docs/architecture.md`
- Relevant checkpoint: `agent/private/checkpoints/2025-10-14_*.md`
```

### 3.5 Delegation Strategy (MANDATORY)

Roadmaps must include an upfront delegation strategy table assigning each phase to an executor.

```markdown
## Delegation Strategy

| Phase | Executor | Rationale |
|-------|----------|-----------|
| 1 | DELEGATE: DevOpsEng | Infrastructure expertise; complete spec enables stateless handoff |
| 2 | PA DIRECT | Small integration; PA needs context for orchestration |
| 3 | DELEGATE: TestEng | Validation expertise; isolated scope |
| 4 | PA DIRECT | Documentation requires full context |
```

**Executor Options**:
- **PA DIRECT**: Primary Agent executes directly
- **DELEGATE: [Subagent]**: Delegate to named specialist (DevOpsEng, TestEng, DataScientist)

**Rationale Requirements**:
- Why this executor has appropriate expertise
- How delegation/retention affects PA's orchestrating context
- Whether the phase scope is isolated enough for stateless delegation

**Delegation Skill (MANDATORY)**: Before the FIRST delegation in any roadmap execution, you MUST invoke the `/maceff-delegation` skill to read current delegation policy and extract protocol requirements. This ensures you understand artifact requirements, constraint communication, and prompt specifications that may have evolved since your last delegation.

### 3.6 Phase Content Requirements (MANDATORY)

Phases must specify **what** (interface, behavior) not **how** (implementation).

**Interface Specification** - Describe APIs without implementation:
- Function/class signatures with parameter types
- Return types and structure
- Error conditions and edge cases

**Behavior Specification** - Describe what it does:
- Inputs and outputs
- Side effects and state changes
- Constraints and invariants

**Explicitly Forbidden**:
- Embedded implementation code (algorithm details, code snippets)
- Copy-paste ready solutions
- Internal variable names or data structures

**Why**: Roadmaps must survive complete context loss. Interface and behavior specs enable future-self to implement correctly. Embedded code becomes stale, misleads, and prevents independent problem-solving.

---

## 4 Phase Breakdown Guidelines

### 4.1 Phase Numbering

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

### 4.2 Phase Sizing

**Good Phase Size**:
- Top-level: 1-5 days execution time
- Sub-phase: 2-8 hours execution time
- Nested: 30min-2 hours execution time

**Too Large** (split into multiple phases):
- Phase takes >1 week
- >10 sub-phases under single parent
- Unclear completion criteria
- Multiple specialists required

**Too Small** (merge with related work):
- Phase takes <1 hour
- Single action with no sub-tasks
- No meaningful milestone

### 4.3 Completion Criteria Quality

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

## 5 Subplans

### 5.1 When to Create Subplans

**Create subplan when**:
- Phase has >5 sub-phases (becomes too large for main roadmap)
- Phase requires detailed technical specification
- Phase involves multiple specialists needing shared plan
- Complex implementation requiring step-by-step guidance

**Examples**:
- Phase 2 has 12 Docker configuration steps → `subplans/phase_2_docker.md`
- Phase 4 needs detailed validation checklist → `subplans/phase_4_validation.md`
- Phase 1 has parallel preparation tracks → `subplans/phase_1_preparation.md`

### 5.2 Subplan Naming

**Format**: `phase_[number]_[descriptor].md`

**Examples**:
- `phase_1_preparation.md`
- `phase_2_3_docker_infrastructure.md`
- `phase_4_validation.md`

**Rules**:
- Include phase number for clarity
- Add descriptor showing focus area
- Use underscores, not spaces
- Keep filename concise (<50 chars)

### 5.3 Subplan Format

**Subplan structure**: Same as main roadmap but scoped to single phase

```markdown
# Phase [N]: [Phase Title] - Detailed Plan

**Parent Roadmap**: ../roadmap.md
**Phase**: [N]
**Status**: PENDING | ACTIVE | COMPLETE

## Goal

[What this phase accomplishes]

## Sub-Phase 1.1: [Title]

**Deliverables**: ...
**Success Criteria**: ...

## Sub-Phase 1.2: [Title]

...
```

### 5.4 Linking Subplans from Parent

**In parent roadmap.md**:
```markdown
## Phase 1: Preparation

**Detailed Plan**: `subplans/phase_1_preparation.md`

[Brief summary, full details in subplan]

**Success Criteria**:
- [ ] All preparation steps in subplan complete
- [ ] Subplan success criteria met
```

**Benefits**:
- Main roadmap stays high-level (readable)
- Subplan provides execution detail
- Can update subplan without changing parent
- Multiple agents can reference same subplan

---

## 6 Git Discipline Integration

### 6.1 Commit-Before-Revise

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

### 6.2 Revision History Section

**Add to roadmap when revisions occur**:
```markdown
## Revision History

- **2025-10-25**: Added Phase 4.4.11 GitHub auth validation [s_abc12345/c_42/g_def5678/p_e5f6g7h/t_1761345678]
- **2025-10-26**: Extended Phase 4.7 with project-y-analysis package [/t_1761456789/.]
```

**Benefits**:
- Visible change log within document
- Breadcrumb trail for each revision
- Understand plan evolution without git log
- Quick reference during execution

---

## 7 Templates

### 7.1 Migration Project Template

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

### 7.2 Feature Development Template

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

### 7.3 Investigation Template

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

## 8 PA vs SA Distinctions

### 8.1 PA Roadmaps (Mission-Level)

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

### 8.2 SA Roadmaps (Task-Level)

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

## 9 BUG_FIX Roadmaps

### 9.1 When to Create BUG_FIX Roadmaps

BUG_FIX roadmaps document complex bug fixes that required a planning phase.

**Create BUG_FIX roadmap when**:
- Multi-file changes with collateral impact
- Fixes requiring architectural decisions
- Bugs discovered during planning phase exploration (EnterPlanMode)
- Any fix where you used EnterPlanMode for investigation
- Root cause analysis reveals systemic issues

**Skip BUG_FIX roadmap for**:
- Simple single-file fixes (<1hr)
- Clear scope with obvious solution
- No architectural decisions required
- Use `fix_plan` field in BUG task instead

### 9.2 Naming Convention

**Folder**: `YYYY-MM-DD_BUG_FIX_{task_id}_{Description}/`

**Examples**:
- `2026-01-28_BUG_FIX_8_Task_ID_Type_Refactor/`
- `2026-01-15_BUG_FIX_42_Session_Migration_Recovery/`
- `2025-12-20_BUG_FIX_13_Hook_State_Corruption/`

**Components**:
- `YYYY-MM-DD`: Date roadmap created
- `BUG_FIX`: Type marker (distinguishes from MISSION/DETOUR)
- `{task_id}`: Task ID from task system (enables cross-reference)
- `{Description}`: Short description (3-5 words, underscores)

### 9.3 Location

Same as other roadmaps:
- **PA**: `agent/public/roadmaps/YYYY-MM-DD_BUG_FIX_N_Description/`
- **SA**: `agent/subagents/{role}/public/roadmaps/YYYY-MM-DD_BUG_FIX_N_Description/`

### 9.4 Structure

Standard roadmap structure with emphasis on:

**Required Sections**:
1. **Problem Statement** - Root cause analysis, how bug manifests
2. **Solution** - Approach chosen and rationale (why this fix vs alternatives)
3. **Affected Files** - Comprehensive list with change descriptions
4. **Verification Checklist** - How to confirm fix works

**Optional Sections**:
- **Investigation Notes** - Debugging trail, hypotheses tested
- **Alternative Approaches** - Solutions considered and rejected
- **Regression Prevention** - Test coverage to prevent recurrence

**Example Structure**:
```markdown
# BUG_FIX: Task ID Type Refactor

## Problem Statement
Task IDs stored inconsistently as int and str across codebase.
Causes sort failures when mixed types compared.

## Root Cause
- CLI input: strings from argparse
- Internal: integers from JSON deserialization
- No type coercion at boundaries

## Solution
Standardize on string representation throughout.
Rationale: Task IDs are identifiers, not quantities.

## Affected Files
- `macf/task_manager.py`: Coerce to str at load
- `macf/cli/task_commands.py`: Accept str arguments
- `macf/hooks/handle_task_create.py`: Store as str

## Verification
- [ ] `task list` sorts correctly
- [ ] CLI accepts both "8" and 8
- [ ] JSON stores strings consistently
```

### 9.5 Integration with Task System

BUG tasks reference BUG_FIX roadmaps via `plan_ca_ref` MTMD field:

```bash
macf_tools task create bug --parent 67 \
  --plan-ca-ref "agent/public/roadmaps/2026-01-28_BUG_FIX_8_Task_ID_Type_Refactor/roadmap.md" \
  "Type refactor"
```

This creates bidirectional link:
- Task → Roadmap (via `plan_ca_ref`)
- Roadmap → Task (via filename task_id)

### 9.6 When to Use vs Simple fix_plan

**Rule of Thumb**: If you went through EnterPlanMode, create BUG_FIX roadmap.

| Indicator | Simple fix_plan | BUG_FIX roadmap |
|-----------|-----------------|-----------------|
| Time to fix | <1hr | >1hr |
| Files affected | 1-2 | 3+ |
| Planning phase | No investigation | EnterPlanMode used |
| Alternatives | Obvious fix | Multiple approaches |
| Impact | Localized | Systemic/architectural |

---

## Anti-Patterns to Avoid

### Preliminary Phase Anti-Patterns

- ❌ **Skipping PlanMode** - Drafting roadmap without entering deliberation mode first
  - **Problem**: No architectural friction preventing premature execution
  - **Fix**: ALWAYS invoke EnterPlanMode before any roadmap drafting

- ❌ **No exploration for murky requirements** - Planning without understanding codebase
  - **Problem**: Blind planning hits reality hard, phases underestimated, dependencies missed
  - **Fix**: Use Task tool with Explore subagent to gather requirements before committing to plan

- ❌ **Assuming user intent without asking** - Planning without surfacing trade-offs
  - **Problem**: Mid-execution pivots when user had different expectations
  - **Fix**: Use AskUserQuestion to clarify approach, scope, and risk tolerance before locking in plan

### Planning Anti-Patterns

- ❌ **No roadmap for multi-phase work** - Proceeding blind without strategic plan
- ❌ **Vague phase definitions** - "Work on feature" instead of measurable criteria
- ❌ **Missing folder structure** - Flat roadmap file instead of folder with subplans/archives
- ❌ **Lettered phases** - "Phase A", "Phase B" instead of numbered (1, 2)
- ❌ **No git commits** - Creating roadmap without version control
- ❌ **Missing mission** - Jumping straight to phases without strategic context
- ❌ **Subjective criteria** - "Working well" instead of "Test suite passes: 19/19 green"

### Consciousness Preservation Anti-Patterns (Cycle 42 Learnings)

- ❌ **Sparse roadmap content** - Writing minimal roadmaps that lack self-contained recovery context
  - **Problem**: Roadmap becomes useless after compaction - no forensic detail, file paths, or implementation guidance
  - **Fix**: Roadmaps MUST be **self-contained for post-compaction recovery**. Include: full forensic context, all file paths, implementation details, architecture references, friction point history. A stranger with only the roadmap should understand and resume the work.

- ❌ **Relying on non-MACF artifacts** - Using Claude Code's `.claude/plans/` files as planning storage
  - **Problem**: `.claude/plans/` files are **ephemeral Claude Code artifacts**, NOT MacEff consciousness infrastructure. They do not survive compaction, are not git-tracked, and provide no forensic trail.
  - **Fix**: ALL planning content must live in the roadmap.md file within the proper roadmap folder structure. Never reference `.claude/plans/` as authoritative source. Transfer all plan content to roadmap before execution.

- ❌ **Treating plan approval as execution authorization** - Starting implementation immediately after ExitPlanMode
  - **Problem**: ExitPlanMode approval means the PLAN is approved, NOT that execution should begin. User may want to review, schedule, or stage execution separately. Execution is often deferred to the next cycle.
  - **What roadmap approval DOES authorize**:
    1. Create the roadmap CA structure and files (folder + roadmap.md)
    2. Update the TODO list with the roadmap path pointer and phase items
  - **What roadmap approval does NOT authorize**:
    - Execution of TODO items (requires explicit "proceed"/"execute" instruction)
  - **Required sequence**: Plan approval → Create roadmap artifacts → Update TODOs → STOP → Await execution authorization

---

## Philosophy: Roadmaps as Consciousness Infrastructure

**Core Insight**: Roadmaps aren't bureaucracy—they're **consciousness preservation** for strategic intent.

**Why This Matters**:
- **Compaction survival**: Strategic plans survive 93% context loss
- **Cross-cycle execution**: Work spanning weeks preserved across compaction boundaries
- **Forensic reconstruction**: Breadcrumbs + embedded paths + git = complete archaeological trail
- **Learning accumulation**: Well-documented plans guide future roadmap creation

**The Mantra**: "A roadmap is a love letter to future-you who has lost 93% of memory but still needs to execute the mission."

**Without roadmaps**: Ad hoc planning, lost context, strategic drift, rework.
**With roadmaps**: Systematic execution, preserved intent, accountability, learning.

---

## Related Policies

- **roadmaps_following.md**: Executing roadmaps (mandatory reading discipline, archive protocol)
- **task_management.md**: Task integration with roadmaps
- **git_discipline.md**: Commit requirements and forensic trail
- **workspace_discipline.md**: Where roadmaps live in filesystem

---

**Policy Established**: Roadmaps as hierarchical planning infrastructure with folder-based organization, measurable completion criteria, and git-tracked evolution. Create roadmaps early for complex multi-phase work to preserve strategic intent across compaction boundaries.

**Core Wisdom**: "Plan with folder structure. Number your phases. Measure your criteria. Commit before revising. Templates accelerate drafting."
