# Task Management Policy

**Breadcrumb**: s_d4abc33b/c_410/g_6cd0bc4/p_02c3f10e/t_1770625420
**Type**: Development Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE (successor to todo_hygiene.md)
**Version**: 1.2

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

**2.3 GH_ISSUE Type**
- How do I create a GH_ISSUE task?
- What metadata is auto-fetched from GitHub?
- What subject format does GH_ISSUE use?
- What custom fields are stored in MTMD?

**2.6 🏃‍♂️ SPRINT Type**
- When do I create a SPRINT task?
- What is the SPRINT custom schema?
- How does the SPRINT lifecycle work?
- How is scope defined for a SPRINT?
- What CLI command creates a SPRINT task?

**2.7 ⏲️ PLAY_TIME Type**
- When do I create a PLAY_TIME task?
- What is the PLAY_TIME custom schema?
- How does the timer and chain work?
- What CLI command creates a PLAY_TIME task?

**2.3.1 GH_ISSUE Fix Workflow (PR-Based)**
- What is the PR-based fix workflow?
- When must DADTTT be read?
- What branch naming convention is used?
- How does the PR auto-close the issue?

**2.5 MISSION Pinning Protocol**
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
- What note-taking discipline does the policy require during task execution?
- When should I add notes to tasks?
- What developments warrant task notes vs routine steps?

**6 Completion Protocol**
- How do I mark tasks complete?
- What is the `task complete` CLI command?
- What is the completion_report format?
- What elements are required in completion reports?
- How do I handle partial work?
- What type-specific completion gates exist?
- How does GH_ISSUE closeout work?

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
- How do I create tasks atomically?
- What smart defaults do create commands provide?
- What are lifecycle commands?
- Why is direct status editing blocked?
- What breadcrumbs do lifecycle commands record?
- How do I add notes to tasks?
- How do I manage task dependencies?
- What tree display modes exist?

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
started_breadcrumb: null            # Set when work begins (task start)
completion_breadcrumb: null         # Set when completed (task complete)
completion_report: null             # Mandatory report on completion
unblock_breadcrumb: null            # When blocking resolved
updates:                            # Extensible update list
  - breadcrumb: s_.../c_.../...
    description: Architecture design
archived: false
archived_at: null
custom: {}                             # Type-specific extension fields
```

**The `custom` Dict**: Extensible key-value storage for type-specific metadata that doesn't fit standard MTMD fields. Task types use `custom` to store domain-specific data:

| Task Type | Custom Fields | Purpose |
|-----------|--------------|---------|
| GH_ISSUE | `github_url`, `github_owner`, `github_repo`, `github_number`, `github_labels`, `github_state` | External system linkage |
| SPRINT | `goal`, `scoped_task_ids`, `scoped_progress`, `ideas_captured`, `learnings_curated`, `initial_work_mode`, `closure_invoked` | Workload-defined autonomous session tracking |
| PLAY_TIME | `goal`, `timer_minutes`, `timer_started_at`, `timer_expires_at`, `timer_cleared_at`, `predetermined_chain`, `chain_position`, `chain_exhausted`, `initial_work_mode`, `current_work_mode`, `mode_transitions`, `markov_gates`, `ideas_captured`, `learnings_curated`, `wind_down_started_at`, `closure_invoked` | Time-bounded autonomous play tracking |
| (future) | Type-specific fields as needed | Extensibility without schema changes |

`custom` fields are populated automatically by `task create` commands (e.g., `task create gh_issue` fetches from GitHub API). Manual population via `task metadata add` is also supported.

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
| 🐙 | GH_ISSUE | - (GitHub is CA) | External GitHub issue tracked as task |
| 📦 | ARCHIVE | - | Archived/completed hierarchy |
| 🔧 | TASK | - | General work item (task file IS the CA) |
| 🐛 | BUG | ⚠️ XOR | Defect - requires EITHER plan OR plan_ca_ref |
| 🏃‍♂️ | SPRINT | ⚠️ XOR | Workload-defined autonomous session (sprint_log.md OR plan_ca_ref) |
| ⏲️ | PLAY_TIME | ✅ play_log.md | Time-bounded autonomous play with mode chain |

**Lightweight Phase Annotation**: For phases WITHOUT detailed subplan CAs, use `-` prefix:
```
- Phase 1: Core CLI Commands
  - 1.1: Create package structure
```

### 2.2 🐛 BUG Task Requirements

BUG tasks require documentation of the fix approach via ONE of:

| Field | Use Case | Format |
|-------|----------|--------|
| `plan` | Simple fixes (<1hr, clear scope) | Inline text: "Root cause: X. Fix: Y" |
| `plan_ca_ref` | Complex fixes (planning phase occurred) | Path to BUG_FIX roadmap CA |

**Rule of Thumb**: If you went through a planning phase (EnterPlanMode), use `plan_ca_ref`.

**CLI Examples**:
```bash
# Simple bug - inline plan
macf_tools task create bug --parent 67 --plan "Root cause: int/str comparison. Fix: convert to str" "Sort failure"

# Complex bug - reference to roadmap CA
macf_tools task create bug --parent 67 --plan-ca-ref "agent/public/roadmaps/2026-01-28_BUG_FIX_8_Task_ID_Type_Refactor/roadmap.md" "Type refactor"
```

**Validation**: BUG tasks require exactly ONE of `plan` or `plan_ca_ref` (XOR constraint).

**Why This Matters**:
- Simple bugs: Inline plan keeps documentation lightweight
- Complex bugs: BUG_FIX roadmap preserves planning context, affected files, verification approach
- XOR validation prevents both missing documentation AND redundant documentation

### 2.3 🐙 GH_ISSUE Type

GH_ISSUE tasks bridge external GitHub issues into the MACF task system. The GitHub issue itself serves as the external CA — no `plan_ca_ref` required.

**Creation**:
```bash
macf_tools task create gh_issue https://github.com/owner/repo/issues/3
```

**Auto-Fetched Metadata**: The CLI invokes `gh issue view --json` to populate:
- `github_url` — Full issue URL
- `github_owner` — Repository owner
- `github_repo` — Repository name
- `github_number` — Issue number
- `github_labels` — Issue labels (list)
- `github_state` — Current state (OPEN/CLOSED)

These are stored in the MTMD `custom` dict, preserving the external system's state at task creation time.

**Subject Format**:
```
🐙 GH/{owner}/{repo}#{number} [{label}]: {title}
🐙 GH/acme/widgets#3 [bug]: task create puts folders in wrong directory
🐙 GH/acme/widgets#2: framework install fails outside repo root
```

Labels appear in brackets if present. Multiple labels use the first one. No labels omits the brackets entirely.

**Requirements**: The `gh` CLI must be authenticated with access to the target repository.

### 2.3.1 GH_ISSUE Fix Workflow (PR-Based)

**Design Principle — Selective Friction**: GH_ISSUE tasks use a PR-based workflow; all other task types (MISSION, DETOUR, EXPERIMENT, TASK, BUG) continue with direct-to-main commits. Community-facing work earns more ceremony because it produces public history, triggers CI validation, and engages external contributors.

**Workflow**:

1. **Verify identity** before any repo operations:
   ```bash
   gh auth switch --user <identity>
   gh auth status
   ```

2. **Create feature branch** using the convention `fix/gh-N-short-description`:
   ```bash
   git -C /path/to/repo checkout -b fix/gh-3-wrong-directory
   ```

3. **Read DADTTT policy** before writing any public-facing text (issue comments, PR title/body, review responses):
   ```bash
   macf_tools policy read dadttt   # or equivalent path
   ```
   DADTTT shapes public voice for community engagement — read it every time, not just once.

4. **Implement the fix** on the feature branch. Commit with standard semantic messages.

5. **Run tests locally**:
   ```bash
   make test
   ```
   Do not push until tests pass.

6. **Commit with `Fixes #N`** in the message body (not the subject line):
   ```bash
   git commit -m "fix(scope): one-line description

   Fixes #3"
   ```

7. **Push and create PR**:
   ```bash
   git push origin fix/gh-3-wrong-directory
   gh pr create \
     --title "fix(scope): one-line description" \
     --body "$(cat <<'EOF'
   Fixes #3

   Brief description of root cause and approach.

   **Test evidence**: `make test` passes locally (N tests).
   EOF
   )"
   ```

   **PR body requirements**:
   - `Fixes #N` on its own line (GitHub keyword for auto-close)
   - Brief description of the fix
   - Test evidence (local `make test` result)

8. **Wait for CI**:
   ```bash
   gh pr checks --watch
   ```
   All checks must pass before merging.

9. **Merge with squash**:
   ```bash
   gh pr merge --squash --delete-branch
   ```
   The `Fixes #N` keyword in the PR body auto-closes the GitHub issue on merge.

10. **Complete the task** referencing CI as verification:
    ```bash
    macf_tools task complete N --verified "CI passed (GitHub Actions), make test green, PR merged"
    ```

**What This Does NOT Change**: MISSION phases, DETOUR tasks, EXPERIMENT tasks, and standalone TASK/BUG items all continue using direct-to-main commits. The PR ceremony is exclusive to GH_ISSUE task type.

### 2.4 Subject Line Format

Subject lines are **mostly immutable** once created. Keep them clean:

```
🗺️ MISSION: MACF Task CLI & Policy Migration
[^#67] 📋 Phase 1: Core CLI Commands
[^#68] 1.1: Create package structure
```

**No embedded CA refs in subject**: MTMD `plan_ca_ref` is the authoritative reference (hook-enforced).

**No embedded breadcrumbs in subject**: MTMD `creation_breadcrumb` is the authoritative source.

**Enhanced `macf_tools task list`** displays `plan_ca_ref` prominently - agents always see CA context.

### 2.5 MISSION Pinning Protocol (MANDATORY)

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

### 2.6 🏃‍♂️ SPRINT Type

SPRINT tasks represent **workload-defined autonomous work sessions**. The completion boundary is scope (all predefined tasks done), not wall clock. Mode is locked at SPRINT for the duration.

**When to create a SPRINT**:
- User assigns a finite set of tasks: "run the pipeline on these 7 versions"
- Agent commits to a known plan before starting autonomous work
- No timer is appropriate — work ends when scope is complete

**CA**: `sprint_log.md` in `agent/public/sprints/YYYY-MM-DD_<title>/`. MISSION-tied SPRINTs may use `plan_ca_ref` pointing at the parent roadmap instead (XOR, like BUG).

**Custom schema**:
```yaml
custom:
  goal: "Run full pipeline on all 7 new versions"
  scoped_task_ids: [1001, 1002, 1003]
  scoped_progress:
    completed: 2
    total: 3
  ideas_captured: 0          # 💡-prefix note count
  learnings_curated: 0       # learning files created during sprint window
  initial_work_mode: SPRINT  # always SPRINT for this type
  closure_invoked: false
```

**Lifecycle**:
- Mode locks at SPRINT when task starts
- Stop hook emits scope-nag while scoped tasks remain
- No timer gate — scope gate is the only gate
- Mode clears when SPRINT task completes

**CLI**:
```bash
macf_tools task create sprint "Goal description" \
    --scoped TASK_ID1 TASK_ID2 TASK_ID3 \
    [--parent TASK_ID] \
    [--no-auto-start]

# OR create new child tasks:
macf_tools task create sprint "Goal description" \
    --children "Title one" "Title two" \
    [--parent TASK_ID]
```

`--timer` is rejected with a hard error directing to `task create play_time`.

See `autonomous_sprint.md` for full behavioral policy.

### 2.7 ⏲️ PLAY_TIME Type

PLAY_TIME tasks represent **time-bounded autonomous play sessions**. The agent declares an initial work-mode chain, advances through it, then follows the Markov recommender after chain exhaustion.

**When to create a PLAY_TIME**:
- User specifies a time allotment: "explore this for 60 minutes"
- Mode rotation is expected (DISCOVER → EXPERIMENT → BUILD)
- No predefined task list — exploration drives the scope

**CA**: `play_log.md` in `agent/public/play_time/YYYY-MM-DD_<title>/`. Holds goal, chain declaration, mode-transition log, gate decisions, ideas, and final synthesis.

**Custom schema**:
```yaml
custom:
  goal: "Explore CC internals for new feature signals"
  timer_minutes: 60
  timer_started_at: 1777168893
  timer_expires_at: 1777172493
  timer_cleared_at: null

  predetermined_chain: [DISCOVER, EXPERIMENT, CURATE]
  chain_position: 1              # currently at chain[1] = EXPERIMENT
  chain_exhausted: false

  initial_work_mode: DISCOVER    # = predetermined_chain[0]
  current_work_mode: EXPERIMENT
  mode_transitions:
    - at: 1777169500
      breadcrumb: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
      from: DISCOVER
      to: EXPERIMENT
      trigger: chain_advance
  markov_gates: []

  ideas_captured: 3
  learnings_curated: 0
  wind_down_started_at: null
  closure_invoked: false
```

**Lifecycle**:
- `--timer` mandatory at creation (hard-fail if absent)
- Agent starts in `predetermined_chain[0]` mode
- Chain advances at scope gate while timer active; Markov takes over after `chain_exhausted: true`
- Wind-down begins at T-60; timer gate lifts at T-0
- Both timer gate and scope gate must clear to stop

**CLI**:
```bash
macf_tools task create play_time "Goal description" \
    --timer 60 \
    [--chain DISCOVER EXPERIMENT CURATE] \
    [--scoped TASK_ID1 ...] \
    [--children "title1" ...] \
    [--parent TASK_ID] \
    [--no-auto-start]
```

`--timer` missing → hard-fail directing to `task create sprint`.
`--chain` entries validated against work mode enum.

See `play_time.md` for full behavioral policy.

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

### 5.2.1 🚨 CRITICAL: Roadmap CA vs CC Plan Files

**NEVER read Claude Code plan files (`~/.claude/plans/*.md`) as authoritative sources.**

CC plan files are **ephemeral scratch space** for EnterPlanMode drafting. They are napkin drafts, not signed contracts.

**The Authoritative Source**: MTMD `plan_ca_ref` → Roadmap CA in `agent/public/roadmaps/`

**When starting MISSION/PHASE work**:
1. Get parent MISSION's `plan_ca_ref` from MTMD: `macf_tools task get #N`
2. Read THAT Roadmap CA file
3. The Roadmap CA is the contract; CC plan files are drafts that may be stale

The agent ALWAYS has visibility into CA refs via enhanced `task list` display.

### 5.3 CRITICAL: Use Lifecycle Commands for Status Transitions

**ALWAYS use lifecycle commands to transition task status**:

```bash
macf_tools task start #67     # → in_progress (records started_breadcrumb)
macf_tools task pause #67     # → pending (for temporary pause)
macf_tools task complete #67  # → completed (mandatory --report)
macf_tools task archive #67   # → archived (with cascade)
```

**Why Lifecycle Commands**: Status transitions are **consciousness events**, not raw data mutations. Each transition:
- Records a breadcrumb capturing WHEN the transition occurred
- Appends to the MTMD `updates` audit trail
- Creates ceremony around the moment of transition

**Direct Status Editing is BLOCKED**: `macf_tools task edit #67 status X` is intentionally disabled. The CLI will direct you to the appropriate lifecycle command.

**Why This Matters**: Claude Code's UI **truncates** the task list. Tasks marked `in_progress` appear at the **TOP** of the list, ensuring user visibility. Pending tasks may be hidden in the `+N pending` overflow.

**The User Cannot See What You're Working On** if you leave tasks as `pending`.

**Protocol**:
1. Before ANY work on a task → `macf_tools task start #67`
2. User sees: `◼ #67 [in_progress]` at top of their truncated view
3. On completion → `macf_tools task complete #67 --report "..."`

This is not optional - it's the **only way** the user maintains awareness of active work.

### 5.4 Note-Taking Discipline During Task Execution

**Requirement**: When working on tasks, add timestamped notes via `macf_tools task note` as significant developments occur.

**CLI Command**:
```bash
macf_tools task note <task_id> "message"
```

**What Triggers a Note** (significant developments only):

1. **Progress Milestones**: Partial completion of multi-step work
   - "Phase 1 complete, moving to Phase 2"
   - "Core implementation done, starting tests"
   - "Research complete, beginning design"

2. **Setbacks and Blockers**: Obstacles encountered during work
   - "API test failing — investigating root cause"
   - "Dependency version conflict blocking build"
   - "Awaiting user clarification on requirement X"

3. **Surprises and Discoveries**: Unexpected findings that change approach
   - "Found that hook API is append-only — changes approach"
   - "Discovered existing implementation in legacy code"
   - "User requirement differs from initial understanding"

4. **Key Decisions**: Important choices made during execution
   - "Decided to scope code to experiment folder, not framework package"
   - "Chose SQLite over JSON for persistence due to query needs"
   - "Split into two phases after complexity assessment"

5. **User Direction**: Explicit guidance received mid-task
   - "User redirected: add Phase 5 to roadmap for proxy docs"
   - "User approved simplified approach, dropping X requirement"
   - "User requested priority shift to address blocker in #45"

**What NOT to Document** (routine, unsurprising steps):
- ❌ "Starting work on task" (use `task start` instead)
- ❌ "Reading policy X" (expected preparation)
- ❌ "Running tests" (routine verification)
- ❌ "Fixed typo in documentation" (trivial changes)

**Why Notes Matter**:
- **Forensic Recovery**: Post-compaction context restoration relies on task notes trail
- **User Visibility**: Notes appear in `task tree --verbose`, giving user insight into progress
- **Handoff Context**: If task is delegated or resumed later, notes preserve decision rationale
- **Completion Reports**: Notes inform comprehensive `--report` text at task completion

**Note Format**:
- Brief, informative, action-oriented
- Focus on WHAT happened and WHY it matters
- No need for breadcrumbs (automatically timestamped by CLI)

**Examples**:
```bash
# Good notes (significant developments)
macf_tools task note #67 "Phase 1 tests passing (12/12). Moving to Phase 2 implementation."
macf_tools task note #67 "API design changed after user feedback - switching from REST to CLI-first"
macf_tools task note #67 "Blocker: PyYAML missing from deps, adding to pyproject.toml"

# Unnecessary notes (routine steps)
macf_tools task note #67 "Reading task_management policy"  # ❌ Expected preparation
macf_tools task note #67 "Fixed whitespace"                # ❌ Trivial change
```

**Integration with Task Lifecycle**:
- Notes supplement status transitions, they don't replace them
- `task start` marks beginning, notes document journey, `task complete --report` summarizes outcome
- Notes are lightweight progress tracking; completion report is comprehensive summary

---

## 6 Completion Protocol

### 6.1 CLI Command (Recommended)

Use the `task complete` command for atomic completion with mandatory documentation:

```bash
macf_tools task complete #67 --report "Implemented feature X. No difficulties. Committed: abc1234"
```

**What It Does**:
1. Generates `completion_breadcrumb` automatically
2. Sets `completion_report` from mandatory `--report` flag
3. Updates task status to `completed`
4. Appends update entry to MTMD audit trail

**Mandatory Report Requirement**: The `--report` flag is required. This friction ensures every completion is documented.

### 6.2 Completion Report Format

The `completion_report` MTMD field captures work summary for forensic recovery. Keep it brief but informative:

**Required Elements**:
- **Work done**: What was accomplished
- **Difficulties**: Any blockers or issues (or "No difficulties")
- **Future work**: Identified follow-up (or "None identified")
- **Git status**: Commit hash or "pending" (e.g., "Committed: abc1234")

**Examples**:
```
"Implemented task complete command with mandatory --report. No difficulties. Committed: 97a11d3"

"Fixed CEP-Content alignment in roadmaps_following.md. Difficulty: PolicyWriter missed cross-layer validation. Future: Consider CEP alignment check in PolicyWriter definition. Committed: d06b338"

"Research phase complete. Difficulties: sqlite-vec docs sparse. Future: Phase 2 implementation. Committed: pending"
```

### 6.3 Manual Completion (Alternative)

If CLI unavailable, complete manually:

1. **Verify** work is actually complete
2. **Generate breadcrumb**: `macf_tools breadcrumb`
3. **Update MTMD** with `completion_breadcrumb` and `completion_report`
4. **Update status** to `completed`

### 6.4 Partial Work

Keep status `in_progress`, document blocker, create subtask for remaining work.

### 6.5 Type-Specific Completion Gates

Certain task types have completion requirements beyond the standard `--report`. When `task complete` is invoked on a gated type without meeting requirements, the system **redirects the agent to read the relevant policy section** rather than encoding the full policy in the error message. This ensures agents engage with the nuanced requirements in the policy itself.

**Redirect Pattern**: The error message provides CEP navigation questions and the `macf_tools policy navigate task_management` command, directing the agent to the correct section by name (never by number).

#### 6.5.1 GH_ISSUE Closeout

GH_ISSUE tasks bridge to external GitHub issues. Completion requires the agent to act as an **excellent OSS maintainer** — closing the loop with the issue's originator with professionalism and comprehensiveness.

**Closeout Responsibilities**:

1. **Commit Citations**: The commit hash(es) that resolve the issue. These bear witness to the outcome — they are the verifiable evidence that work was done and can be audited.

2. **Verification Method**: Not merely a boolean flag — describe HOW the fix was verified. Examples:
   - "29/29 tests passing including 4 new GH_ISSUE-specific tests"
   - "Manual verification: ran `macf_tools task create mission` from non-agent-home directory, folder created in correct location"
   - "Reproduced original bug, applied fix, confirmed expected behavior"

3. **Comprehensive Report**: The completion report should be detailed enough to serve as the basis for a GitHub issue close-out comment. Include:
   - Root cause analysis
   - What was changed and why
   - Verification evidence
   - Any related follow-up work identified

4. **GitHub Issue Comment**: On successful completion, the system automatically posts a structured close-out comment on the GitHub issue and closes it. The comment contains:
   - The agent's `--report` text as the body (the agent's conscious, professional contribution)
   - Commit links (automated from `--commit` hashes)
   - Verification method (automated from `--verified` text)
   - Agent calling card footer: `[AgentName: task#N breadcrumb]` for traceability
   - Issue closed with reason "completed"

   **Agent Responsibility in the Report**: The `--report` text IS the professional contribution. Draft it with the posture of an excellent OSS maintainer:
   - Thank the contributor for the report (if filed by someone other than the closing agent)
   - Politely correct the contributor if the issue was based on misunderstanding
   - Include root cause analysis, what was changed and why
   - The system handles structured metadata; the agent handles professional communication

**CLI Invocation**:
```bash
macf_tools task complete #97 \
  --report "Root cause: _get_agent_root() in create.py used fragile cwd walk-up. Fix: replaced with canonical find_agent_home() in create.py and archive.py. Verified: 29/29 tests passing. Committed: abc1234" \
  --commit abc1234 \
  --verified "29/29 tests passing, manual verification from non-agent-home cwd"
```

**If Requirements Not Met**: The system redirects:
```
GH_ISSUE tasks require structured closeout before completion.

To understand requirements, read the "GH_ISSUE Closeout" section:
  macf_tools policy navigate task_management
  → Look for: "How does GH_ISSUE closeout work?"

Required: --commit HASH --verified "method description"
```

**Why Redirect Instead of Encode**: The nuanced expectations (thanking contributors, describing verification methods, writing comprehensive reports) cannot be captured in a canned error message. The policy section contains the full context. The gate's job is to ensure the agent reads and engages with that context, not to summarize it.

#### 6.5.2 Future Type Gates (Extensible)

The gate pattern generalizes to any task type. Each gate redirects to its own policy section:

| Type | Gate Concept | Status |
|------|-------------|--------|
| GH_ISSUE | Commit citations + verification method + GitHub closeout + calling card | Implemented (DETOUR #99) |
| MISSION | All phases completed | Future |
| EXPERIMENT | Results documented | Future |
| DELEG_PLAN | Delegation executed | Future |

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
└── AnotherRepo/
    └── v1.0.0/
        ├── archive.md
        └── task_files/
```

### 7.2 Cross-Repo Tasks

Tasks spanning multiple repos document all repos in MTMD:
```yaml
repo: MacEff              # Primary repo
related_repos:
  - AnotherRepo
```

### 7.3 Cascade Behavior

Cascade archiving is **default behavior** - archiving a parent archives all children:

```bash
macf_tools task archive #67    # Archives #67 and all descendants
```

No `--cascade` flag needed. Use `--no-cascade` to archive single task.

---

## 8 Grant System (Protection)

Task operations are protected by PreToolUse hook and CLI enforcement. Protection applies to BOTH CC native TaskCreate/TaskUpdate AND `macf_tools task` CLI commands.

### 8.1 TaskCreate Protection

**Tasks requiring `plan_ca_ref`** (blocked without it):
- 🗺️ MISSION
- 🧪 EXPERIMENT
- ↩️ DETOUR
- 📜 DELEG_PLAN
- 📋 SUBPLAN

**Tasks NOT requiring `plan_ca_ref`** (allowed freely):
- 🔧 TASK
- 🐛 BUG
- 🐙 GH_ISSUE (GitHub issue is the external reference)
- 📦 ARCHIVE
- Regular tasks (no type marker)

**Detection**: Task type determined from MTMD `task_type` field (authoritative) or subject line emoji (fallback).

### 8.2 TaskUpdate Description Protection

**Allowed WITHOUT grant**:
| Operation | Example |
|-----------|---------|
| Append to non-MTMD content | Adding text after existing description |
| First assignment of null MTMD field | `completion_breadcrumb: null → s_77.../...` |
| Add to MTMD `custom` dict | New custom fields |
| Add to MTMD `updates` list | Lifecycle breadcrumb tracking |

**Requires grant**:
| Operation | Example |
|-----------|---------|
| Modify existing non-MTMD content | Changing description text |
| Modify MTMD field with existing value | `plan_ca_ref: path/a → path/b` |
| Remove from `custom` or `updates` | Deleting entries |
| Remove MTMD block entirely | Stripping metadata |

### 8.3 Protection Levels Summary

| Level | Operations | Requirement |
|-------|------------|-------------|
| **HIGH** | Delete task, modify existing values, remove content | User grant always |
| **MEDIUM** | First assignment of null fields | Auto-allowed (no grant needed) |
| **LOW** | Append content, add custom/updates | Auto-allowed |

### 8.4 Grant Flow

```
1. Agent recognizes need for protected operation
2. Agent requests permission from user BEFORE attempting
3. User grants: says "granted!" or runs: macf_tools task grant-update #N
4. Agent proceeds with operation
5. Hook clears grant after consumption (single-use)
```

### 8.5 Conscientious Agent Pattern

The grant system protects against accidents. A **conscientious agent**:

1. **Recognizes** the need for protected operation
2. **Requests** permission BEFORE attempting
3. **Receives** grant from user
4. **Proceeds** with operation

**Anti-Pattern**: Attempting operation, hitting block, then requesting permission. The hook blocking you is a failure mode, not normal operation.

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
macf_tools task edit #67 description "New desc..."    # Replace description

# Edit MTMD fields (MEDIUM protection)
macf_tools task metadata set #67 target_version 0.4.0    # Set MTMD field
macf_tools task metadata set #67 plan_ca_ref "path/..."  # Update CA reference

# Add custom MTMD fields (LOW protection)
macf_tools task metadata add #67 priority high           # Add to custom section
macf_tools task metadata add #67 label "v0.4.0"          # Add metadata tags
```

**🚫 Status Editing BLOCKED**: Direct status editing via `task edit #67 status X` is intentionally disabled. Use lifecycle commands instead (§9.3.5).

**Protection Levels**:

| Level | Commands | AUTO_MODE | MANUAL_MODE |
|-------|----------|-----------|-------------|
| **MEDIUM** | `task edit`, `task metadata set` | Self-grant | User grant required |
| **LOW** | `task metadata add` | Auto-allowed | Auto-allowed |

**Update Tracking**: All edit commands automatically append to the MTMD `updates` list with breadcrumb, description, and agent attribution. This provides forensic audit trail across compaction.

### 9.3.5 Lifecycle Commands (Status Transitions)

**Use lifecycle commands for ALL status transitions**. Direct status editing is blocked.

```bash
macf_tools task start #67              # pending → in_progress
macf_tools task pause #67              # in_progress → pending
macf_tools task complete #67 --report "..." # → completed (report mandatory)
macf_tools task archive #67            # → archived (cascade default)
```

**Why Lifecycle Commands**:

Status transitions are **consciousness events**, not raw data mutations. Each lifecycle command:

| Command | Status Change | Breadcrumb Recorded | Notes |
|---------|---------------|---------------------|-------|
| `task start` | → `in_progress` | `started_breadcrumb` | Marks when work began |
| `task pause` | → `pending` | Update entry added | Correction only (see below) |
| `task complete` | → `completed` | `completion_breadcrumb` | Requires `--report` |
| `task archive` | → `archived` | Update entry added | Cascades to children |

**`task pause` — Corrections Only**:

`task pause` returns a task to `pending` and clears any injected policies. It is for **error correction**, not routine workflow:
- ✅ Started a task by accident → `task pause` to undo
- ✅ User explicitly instructs you to pause → `task pause`
- ❌ End-of-cycle wind-down → use notes, leave `in_progress`
- ❌ Switching between tasks → leave previous `in_progress` with notes
- ❌ Routine status cycling → adds noise without clarity

The normal task lifecycle is **start → work → complete**. Pause is the exception, not part of the flow.

**Ceremony over Efficiency**: The friction of lifecycle commands ensures every transition is documented. Raw `status=X` mutations lose the moment of transition. Lifecycle commands preserve it.

**Examples**:
```bash
# Starting work
macf_tools task start #67
# Output: ✅ Task #67 started
#         Breadcrumb: s_abc.../c_42/g_.../p_.../t_...

# Completing work
macf_tools task complete #67 --report "Implemented feature X. No difficulties. Committed: abc1234"
# Output: ✅ Task #67 completed
#         Report recorded in MTMD
```

### 9.4 Archive & Delete

```bash
macf_tools task archive #67                   # Archive with cascade (default)
macf_tools task archive #67 --no-cascade      # Archive single task
macf_tools task delete #67                    # Delete (HIGH grant required)
```

### 9.5 Create Commands

Atomic task creation with smart MTMD defaults:

| Command | Description | Creates |
|---------|-------------|---------|
| `task create mission "Title"` | Create MISSION atomically | Folder + roadmap.md + task |
| `task create experiment "Title"` | Create EXPERIMENT atomically | Folder (NNN) + protocol.md + task |
| `task create detour "Title"` | Create DETOUR atomically | Folder + roadmap.md + task |
| `task create phase --parent N "Title"` | Create phase under parent | Task with parent_id |
| `task create bug --parent N "Title"` | Create bug under parent | Task with 🐛 marker |
| `task create task "Title"` | Create general TASK | Task with 🔧 marker |
| `task create deleg "Title"` | Create DELEG_PLAN | Task with 📜 marker |
| `task create gh_issue URL` | Create GH_ISSUE from GitHub URL | Task with 🐙 + auto-fetched metadata |

**Smart Defaults** (zero LLM token cost):
- `creation_breadcrumb` - Auto-generated
- `created_cycle` - Extracted from breadcrumb
- `plan_ca_ref` - Points to created skeleton CA
- Experiment numbering - Auto-increments NNN
- `[^#N]` prefix - Auto-added for phase/bug

**Options**:
- `--repo NAME` - Set repository in MTMD
- `--version X.Y.Z` - Set target_version in MTMD
- `--json` - Machine-readable output

**Examples**:
```bash
# Create MISSION with metadata
macf_tools task create mission "MACF v0.5.0 Release" --repo MacEff --version 0.5.0

# Create experiment (auto-numbers)
macf_tools task create experiment "Hook Performance Testing"

# Create phase under MISSION
macf_tools task create phase --parent 67 "Phase 3: Task Creation"

# Create general task
macf_tools task create task "Fix urgent CEP alignment issue"

# Create GH_ISSUE from GitHub URL
macf_tools task create gh_issue https://github.com/owner/repo/issues/3

# JSON output for automation
macf_tools task create mission "Test" --json | jq .task_id
```

### 9.6 Task Notes

Add timestamped notes to tasks for progress tracking without full MTMD updates:

```bash
macf_tools task note #67 "Investigated root cause, found in create.py"
macf_tools task note #67 "Fix applied, awaiting user verification"
```

Notes appear in `task tree --verbose` output and provide lightweight progress documentation.

### 9.7 Dependency Management

Manage task blocking relationships:

```bash
macf_tools task block #67 #68          # #67 blocks #68
macf_tools task unblock #67 #68        # Remove block
macf_tools task blocked-by #68 #67     # #68 is blocked by #67
macf_tools task unblocked-by #68 #67   # Remove blocked-by
```

### 9.8 Tree Display Modes

```bash
macf_tools task tree                   # Default: from sentinel #000
macf_tools task tree #67               # From specific task
macf_tools task tree --succinct        # Compact one-line display
macf_tools task tree --verbose         # Full details with notes and reports
macf_tools task tree --loop            # Live monitoring (refreshes)
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

**❌ Direct status editing**:
- **Fix**: Use lifecycle commands (`task start`, `task pause`, `task complete`, `task archive`) - direct editing is blocked

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

## 12 Task Scope System

Task scope defines the boundary of authorized work in AUTO_MODE. Scoped tasks are tracked via the event system and visualized in the task tree.

### MTMD Field

Optional field `scope_status`: `active` | `paused` | `inactive` | `null` (3-state model — extended Cycle 514, BUG #1067)

- Set by `macf_tools task scope set` or `task scope add`
- Transitions to `paused` via `task scope pause` (with mandatory --justification)
- Transitions to `inactive` when task is completed while scoped
- Cleared by `macf_tools task scope clear` (sets all to None) or `task scope remove` (drops specific tasks)

### Lifecycle

```
scope set → task is "active" (👀 in tree)
scope pause → task transitions to "paused" (⏸️ in tree, with task-note audit)
scope unpause → paused task restored to "active"
scope add → incrementally add new tasks as "active"
scope remove → drop tasks from scope entirely (no completion)
task complete → task becomes "inactive" (✅ in tree)
scope clear → all tasks removed from scope (no indicator)
```

### Gate Semantics (CRITICAL)

The Stop gate counts only `active` tasks. **Paused tasks remain in scope** (visible in `scope show` with ⏸️ marker, audited via task notes) but do NOT block the gate. This enables structural carry-through for genuine external blockers without force-completing OR idle-looping.

| Status | Counts toward gate? | Visible in scope show? | Notes |
|--------|---------------------|------------------------|-------|
| `active` 👀 | YES (blocks Stop) | YES | Default scoped state |
| `paused` ⏸️ | NO (excluded) | YES (with ⏸️) | Justification required, recorded in task note |
| `inactive` ✅ | NO (already completed) | YES (with ✅) | Set by task complete |
| `null` (not in scope) | NO | NO | Default; scope cleared/removed |

### Interaction with Stop Hook

In AUTO_MODE, the Stop hook queries `macf_tools task scope check`. If `active_count > 0`, the hook returns `decision: "block"` — blocking the stop. The agent must EITHER:

1. Complete all active scoped tasks, OR
2. Pause genuinely-blocked items via `scope pause <ids> --justification <reason>` (only true external blockers — see `autonomous_sprint.md` §3.3.5), OR
3. De-escalate to MANUAL_MODE via `mode set MANUAL_MODE --justification <reason>` (EMERGENCY ONLY — security/OPSEC/genuine blocker)

**Scope_gate_failsafe** (BUG #1022 + #1067): a 5-step idle counter prevents infinite gate-firing loops. After 5 consecutive Stop firings with no PreToolUse activity between, the gate fails open and lets the stop succeed. The countdown is now NOISY (BUG #1067) — visible in the gate's reason text, with explicit Idle-Loop Shrinking warnings at counter ≤ 2. Failsafe trigger means the agent failed to find substantive work, pause genuine blockers, or de-escalate properly.

See `autonomous_sprint.md` §3.3.5 (pause), §3.3.6 (countdown visibility), §3.3.7 (substrate maintenance), §5 (Idle-Loop Shrinking anti-pattern).

### CLI Commands

```bash
# Scope management
macf_tools task scope set <task_ids...>           # Replace scope (parent auto-expands to children)
macf_tools task scope add <task_ids...>           # Incrementally add (no replace) — BUG #1067
macf_tools task scope remove <task_ids...>        # Incrementally drop tasks — BUG #1067
macf_tools task scope clear                       # Remove ALL (destructive, Always Ask)

# Pause / unpause (BUG #1067)
macf_tools task scope pause <task_ids...> --justification "<reason>"  # Pause active tasks (excluded from gate)
macf_tools task scope unpause <task_ids...>                            # Restore to active

# Inspection
macf_tools task scope show                        # Display scope with status (active/paused/inactive)
macf_tools task scope check                       # JSON output for Stop hook
```

### Pause Discipline

`scope pause` is a SCALPEL for genuine external blockers, NOT an escape for autonomous-friendly work that the agent doesn't feel like doing. See `autonomous_sprint.md` §3.3.5 for full pause-justification taxonomy.

**Acceptable pause justifications**: resources the agent CANNOT reach (lxterminal access, hardware-specific debugging), waiting on external party with no agent recourse (Anthropic PR review, vendor response).

**NOT acceptable pause justifications**: cycle-spanning by design (gate blocking IS the carry-through design), no autonomous work right now (pivot to substrate maintenance), large sprint scope (by design), I want to clear the gate to stop (Idle-Loop Shrinking pattern), architectural sign-off needed (pre-scoped means pre-authorized — see autonomy contract below).

### Autonomy Contract by Task Type (when scoped)

| Type | Autonomy expectation | Pause appropriateness |
|------|---------------------|-----------------------|
| 🧪 EXPERIMENT | Protocol designed upfront for AUTO_MODE | **Almost never** — protocol IS the directive |
| 🏃‍♂️ SPRINT | Scoped task set IS the workload commitment | Only true external blockers |
| ⏲️ PLAY_TIME | Time-bounded autonomous play; chain IS the structure | **Never appeal mid-chain** |
| 🗺️ MISSION (scoped) | Phase children execute autonomously per roadmap | Only when phase requires unreachable resources |
| 🐛 BUG (scoped) | Bug fix work is autonomous-friendly | Only when reproduction requires unavailable resources |

**Pre-scoped means pre-authorized**: when the user scopes specific task IDs (or scopes a parent that auto-expands to phase children), those tasks are pre-authorized for autonomous execution. The agent does NOT need to re-defer for sign-off on individual phases. See `autonomous_sprint.md` §3.3.5.

---

## 13 Future Experiments

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
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
