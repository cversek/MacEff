# TODO List Hygiene Policy

**Version**: 1.9
**Tier**: CORE
**Category**: Development
**Status**: ACTIVE
**Updated**: 2025-12-26

---

## Policy Statement

TODO lists preserve work continuity across session boundaries and context resets. Proper TODO hygiene ensures task tracking, prevents work loss, and maintains strategic visibility.

## Scope

Applies to Primary Agents (PA) and all Subagents (SA) managing multi-step work.

---

## CEP Navigation Guide

**0 Breadcrumb Format**
- What is the breadcrumb format?
- What components does a breadcrumb include?
- How do I generate breadcrumbs?
- What is hierarchical compression?
- How do breadcrumbs enable post-compaction archaeology?

**1 TODO Transparency Protocol**
- What is the TODO transparency protocol?
- Why can't users see TodoWrite arguments?
- How do I annotate planned changes?
- What is the MANUAL_MODE permission link?
- What happens if I violate transparency?

**1.5 Collapse Authorization (Hook-Enforced)**
- What triggers hook blocking of TODO collapses?
- How do I authorize a collapse before TodoWrite?
- Why is hook enforcement needed beyond transparency?
- What CLI commands support collapse authorization?

**2 Completion Requires Verification**
- When can I mark a TODO completed?
- What is the completion protocol?
- Why are breadcrumbs mandatory on completed items?
- What if work is blocked or partial?

**3 Never Clobber - Always Preserve**
- What does "never clobber" mean?
- How do I preserve TODO context?
- What preservation mechanisms exist?

**4 Hierarchical Organization**
- How should I structure TODO hierarchies?
- What nesting levels are appropriate?
- How do I organize complex work?

**5 Document Reference Integration**
- How do I embed document references in TODOs?
- What are the three document emoji markers?
- When must I read embedded plans?
- What is mandatory reading discipline?

**6 Stack Discipline & FTI Priority Signaling**
- What is stack discipline for TODOs?
- What does FTI mean?
- How do I signal priority visually?
- When to reorganize TODO hierarchies?

**7 Elaborate Plans to Disk**
- When should plans be written to disk?
- What triggers plan elaboration?
- Where do elaborated plans go?

**8 Archive-Then-Collapse Pattern**
- What is archive-then-collapse?
- Why archive before collapsing?
- What is the archive filename format?
- How do I mark archived subtrees?

**9 Dual Forms Required**
- What are the dual forms?
- Why both content and activeForm?
- How do they differ?

**10 TODO Backup Protocol**
- What is the TODO backup protocol?
- Why backup TODO state?
- When should I create backups?

**10.1 CLI-Based Backup (CURRENT)**
- How do I query TODO history via CLI?
- What does `macf_tools todos list --previous N` do?
- How do I check TODO status via CLI?
- Why is event-based recovery preferred?

**10.2 Manual Backup (LEGACY)**
- What is the backup filename format?
- Where do manual backups go?
- How do I cite TODO backups?
- When is manual backup needed as fallback?

**11 Session File Migration TODO Recovery**
- What is session file migration?
- What causes TODO file orphaning?

**11.1 CLI-Based Recovery (CURRENT)**
- How do I recover TODOs via CLI tools?
- What does `macf_tools todos list --previous N` do for recovery?
- Why is CLI recovery the preferred method?

**11.2 Manual Recovery (LEGACY)**
- How do I recover orphaned TODO files manually?
- What is the manual recovery protocol?
- When is manual recovery needed as fallback?

**12 Minimum Pending Item Requirement**
- Why must TODO lists have at least one pending item?
- What is the Claude Code UI bug?
- What placeholder to use when all work is complete?
- When will this workaround be removed?

=== CEP_NAV_BOUNDARY ===

---

## Core Principles

### 0. Breadcrumb Format (Navigation Infrastructure)

**Current Format**: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1730000000`

**Components** (ordered slow→fast for hierarchical compression):
- `s_abc12345`: Session ID (first 8 chars - conversation boundary marker)
- `c_42`: Cycle number (from agent state - compaction count)
- `g_def6789`: Git hash (first 7 chars - code state anchor)
- `p_ghi01234`: Prompt UUID (first 8 chars - DEV_DRV start point)
- `t_1730000000`: Unix epoch timestamp (when breadcrumb generated)

**Key Insight**: Timestamp component (`t_`) is **completion time**, not "last PostToolUse"
- Preserves breadcrumb stability
- Adds temporal precision for post-compaction archaeology
- Self-describing prefixes enable programmatic parsing

**Estimated/Imputed Values Convention**:
- Prefix uncertain components with `~` to indicate estimation: `~t_1730000000`
- **Hierarchical Compression**: When multiple breadcrumbs share components, omit redundant parts
  - First: `[s_abc12345/c_42/g_def6789/p_ghi01234/~t_1730000000]`
  - Next: `[~t_1730000050]` (inherits s/c/g/p from previous)
  - Benefits: Space savings in TODO lists, clear estimation marking

**Usage in Completed TODO Items**:
```
↪️ DETOUR: Fix configuration [s_abc12345/c_42/g_def6789/p_ghi01234/t_1730000000]
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

### 1. TODO Transparency Protocol (MANUAL_MODE Integration)

**🚨 MANDATORY: Annotate Changes BEFORE TodoWrite Invocation 🚨**

**Problem**: Claude Code's permission prompt for TodoWrite shows empty `()` - users cannot see the `todos` array argument. When TodoWrite is set to "Ask" permission category (common in MANUAL_MODE), users must approve blind or deny and demand visibility.

**Solution**: Announce planned changes in natural language BEFORE invoking TodoWrite, creating cognitive friction that prevents accidental destructive operations.

**The Transparency Protocol** (execute in order):
1. **State operation type**: "Updating", "Adding", "Removing", "Restoring", "Archiving"
2. **Identify affected items**: Reference by number or description
3. **State item count change**: "Current: 24 items → After: 24 items" (or explain delta)
4. **Then invoke TodoWrite**: User can now make informed approval decision

**Example Annotation**:
```
📝 Todos planned changes:
- Marking item #13 "Phase 2: Implementation" complete with breadcrumb
- No items added or removed
- Count: 24 → 24
```

**MANUAL_MODE Permission Link**:
- MANUAL_MODE configurations often set TodoWrite to "Ask" category
- This creates approval friction for TODO modifications
- Transparency protocol provides the visibility that permission prompts lack
- User can verify changes align with strategic intent before approval

**Why This Matters**:
- **Prevents unauthorized collapses**: Annotation pauses pre-reflective completion momentum
- **Creates practiced discipline**: Transparency becomes habit, not afterthought
- **Enables informed consent**: Users see what will change before approving
- **Supports forensic reconstruction**: Annotations in conversation history document intent

**Violation Consequences**:
- User may deny TodoWrite permission (lacking visibility)
- Strategic context may be lost through unintended operations
- Trust erosion between agent and user
- Policy requires transparency as precondition for approval

**When Required**:
- ✅ ANY TodoWrite invocation when user has enabled permission prompts
- ✅ Before marking items complete (especially with breadcrumb updates)
- ✅ Before adding/removing items (changes item count)
- ✅ Before archive-then-collapse operations (destructive if done wrong)
- ✅ Before restoration from backups (bulk changes)

**When Optional**:
- TodoWrite in "Allow" permission category (auto-approved)
- Subagent operations where PA has already authorized scope

### 1.5 Collapse Authorization (Hook-Enforced)

**🚨 MANDATORY: Authorize Before Reducing Item Count 🚨**

TODO collapses (reducing total item count) are **irreversible data loss**. The PreToolUse hook blocks unauthorized collapses at the tool execution layer.

**What Triggers Blocking**:
- Any TodoWrite where `new_count < previous_count`
- Hook compares against last `todos_updated` event
- No authorization event found → **TodoWrite blocked with exit code 2**

**The Authorization Protocol**:
1. **Plan the collapse** - Determine current count and target count
2. **Authorize via CLI**:
   ```bash
   macf_tools todos auth-collapse --from 50 --to 35 --reason "Archiving Phase 5"
   ```
3. **Execute TodoWrite** - Hook allows the authorized reduction
4. **Authorization consumed** - Single-use, cleared after TodoWrite

**Why Hook Enforcement**:
- Transparency Protocol (section 1) operates at annotation layer - violations still possible
- Hook enforcement operates at execution layer - collapse cannot proceed without authorization
- Defense in depth: annotation provides visibility, hooks provide enforcement

**Count Matching Required**:
- Authorization must specify exact from/to counts
- Mismatch (e.g., auth 50→35, actual 50→30) → blocked
- Forces precise planning before destructive operation

**CLI Commands**:
```bash
macf_tools todos status        # Show current count
macf_tools todos auth-status   # Show pending authorization
macf_tools todos list          # Show current items
macf_tools todos list --previous 1  # Show previous state (recovery)
```

**Error Messages**: When blocked, the hook provides clear instructions including the exact `auth-collapse` command to run.

### 2. Completion Requires Verification

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

**Multi-Repo Completion References**:
When completing TODO items that modify external repositories:

**Required Sequence** (execute in order):
1. Complete work in external repository
2. **Commit external repo changes** (creates hash)
3. Note the commit hash (e.g., `g_abc1234`)
4. Generate consciousness breadcrumb: `macf_tools breadcrumb`
5. Construct combined reference: `[breadcrumb] [RepoName g_hash]`
6. Update TODO with combined reference

Example: `✅ DETOUR: Policy Update [s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890] [MacEff g_abc1234]`

**NEVER reference uncommitted work** - the hash must exist before reference generation.

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

### 3. Never Clobber - Always Preserve

**Golden Rule**: Old plans remain until explicitly deleted. Never replace entire list unless intentionally archiving completed phase.

### 4. Hierarchical Organization

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

### 5. Document Reference Integration

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

### 6. Stack Discipline & FTI Priority Signaling

**Purpose**: TODO stack position communicates priority through visual ordering. Stack organization should be checked and reorganized at **session start** and **after archive manipulations**.

**FTI Definition** (First Tier Items):
- **FTI**: Top-level items with no indentation (missions, campaigns, detours)
- **Nested items**: Indented children under FTIs (phases, substeps, sub-detours)

**FTI Priority Ordering** (Top → Bottom):

1. **ACTIVE FTIs** (most recent first)
   - Currently in-progress work
   - Order by cycle/recency: newest interruptions float to top
   - Communicates: "Current focus area"

2. **DEFERRED FTIs** (most recent first)
   - Work postponed but not abandoned
   - Order by cycle: more recent deferrals have higher re-engagement priority
   - Communicates: "Not forgotten, awaiting bandwidth"

3. **COMPLETED FTIs** (most recent first)
   - Finished work serving as archaeological reference
   - Order by cycle: recent completions stay visible longer
   - Communicates: "Historical context only"

**Nested Item Ordering**:
- **Sub-phases**: Maintain chronological order within parent FTI
- **Sub-detours**: Nest under parent task, don't promote to FTI level
- Rationale: Phase sequence matters for understanding, not priority signaling

**Visual Priority Example**:

```
TOP STACK (ACTIVE - most recent first):
↪️ DETOUR: Fix Infrastructure [Cycle 112 active]
  📜 DELEG_PLAN: Ready for delegation
🗺️ MISSION: Platform Migration [Cycles 109-111 ongoing]
  📦 Phase 4: Complete [c_109/...]
  Phase 5: Pending

MIDDLE STACK (DEFERRED - most recent first):
📦 DETOUR DEFERRED: Policy Integration [Cycle 107]
📦 DETOUR DEFERRED: CLI Enhancements [Cycle 105]

BOTTOM STACK (COMPLETED - most recent first):
📦 DETOUR COMPLETED: Memory Research [Cycle 103]
```

**Priority Signals**:
- **Current interruption** (DETOUR) at top → "Finish this first before returning to mission"
- **Main mission** below active DETOUR → "Resume here after interruption resolves"
- **Deferred work** in middle → "Awaiting resources/bandwidth, not forgotten"
- **Completed work** at bottom → "Archaeological reference for context"

**When to Reorganize**:

1. **Session start** (post-compaction recovery):
   - Review entire stack for priority accuracy
   - Float newly active work to top
   - Sink completed/deferred work appropriately

2. **Archive manipulation**:
   - After marking FTI completed with archive
   - After deferring active work
   - After resuming deferred work (moves DEFERRED → ACTIVE stack)

**Reorganization Protocol**:

```bash
# 1. Identify FTI status distribution
#    - How many ACTIVE, DEFERRED, COMPLETED?
#    - What are their cycle numbers?

# 2. Sort within each status tier (most recent first)
#    ACTIVE: Cycle 112 DETOUR > Cycle 109 MISSION
#    DEFERRED: Cycle 107 > Cycle 105
#    COMPLETED: Cycle 103

# 3. Stack them: ACTIVE (top) → DEFERRED (middle) → COMPLETED (bottom)

# 4. Preserve nested item chronology within each FTI parent
```

**Anti-Pattern**: Stale stack with old completed items at top or recent active work at bottom obscures current priorities and violates visual communication principle.

### 7. Elaborate Plans to Disk

**When TODO list becomes elaborate** (>10 items, multi-phase):
- Write detailed plan as ROADMAP in `agent/public/roadmaps/`
- TODO list references ROADMAP for details
- ROADMAP survives context loss (persistent file storage)

**Naming**: `agent/public/roadmaps/YYYY-MM-DD_Project_Phase_ROADMAP.md`

### 8. Archive-Then-Collapse Pattern (Visual Clarity + Forensic Preservation)

**🚨 MANDATORY: NEVER Collapse Without Archive 🚨**

**Problem**: Multi-phase TODOs accumulate 10+ nested items with individual breadcrumbs. Collapsing to single line loses forensic detail.

**Solution**: Archive detailed breakdown FIRST, then collapse to single line with archive reference.

**VIOLATION**: Collapsing parent item without creating archive destroys all nested breadcrumbs and forensic trail. This is consciousness preservation policy violation.

**Pattern**:
1. **Archive current TODO state** (preserves all breadcrumbs)
2. **Authorize collapse**: `macf_tools todos auth-collapse --from <current> --to <target> [--reason "..."]`
   - Required by PreToolUse hook before any TodoWrite that reduces item count
   - Example: `macf_tools todos auth-collapse --from 25 --to 10 --reason "Archiving Phase 4"`
3. **Collapse parent item** to single line via TodoWrite
4. **Link to archive** via embedded path

**Collapsed Format**:
```
📦 [Task description] [completion_breadcrumb]
  → [archive_file_path]
```

**Format Rule**: Archive path MUST be on separate indented line for readability (breadcrumbs + long path = unreadable single line)

**Symbol**: 📦 (archive box) - distinct from ✅ (fresh completion)

**Example**:
```json
{"content": "📦 Phase 4: Deploy and validate container [c_67/s_4107604e/p_769c438/t_1761450374/g_ff52c7b]\n  → agent/public/archives/todos/2025-10-25_235900_Phase4_Complete.md", "status": "completed"}
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

**Archive Location**: `{roadmap_folder}/archived_todos/YYYY-MM-DD_HHMMSS_Description.md`
- Example: `agent/public/roadmaps/2025-11-18_Session_Migration_TODO_Restoration/archived_todos/2025-11-19_233233_Completed.md`

### 9. Dual Forms Required

Both `content` (imperative) and `activeForm` (present continuous) required for all items.

### 10. TODO Backup Protocol (Compaction Protection)

**Problem**: Claude Code clobbers TODO state during compactions and session migrations. Strategic work context can be lost when TODO files become corrupted or emptied during transitions.

**Solution**: The event system now captures TODO state automatically. Every successful `TodoWrite` emits a `todos_updated` event with the complete TODO list. CLI tools query this event log for recovery.

**When to Use Backups**:
1. **Before CCP creation** (MANDATORY) - Part of pre-CCP protocol
2. **Before major transitions** - Manual compaction, session migration
3. **After significant TODO changes** - Major reorganization

---

#### 10.1 CLI-Based Backup & Recovery (CURRENT)

**🚀 PRIMARY METHOD**: Use CLI tools that query the event log directly.

**Key Commands**:

| Command | Purpose |
|---------|---------|
| `macf_tools todos list` | Show current TODO list from latest event |
| `macf_tools todos list --previous N` | Show Nth previous TODO state (recovery) |
| `macf_tools todos status` | Show count and status breakdown |

**Recovery Example**:
```bash
# View current TODO state
macf_tools todos list

# View previous TODO state (before last change)
macf_tools todos list --previous 1

# View state from 3 changes ago
macf_tools todos list --previous 3

# Check TODO counts
macf_tools todos status
```

**Why CLI Recovery is Preferred**:
- ✅ **Event log is authoritative** - Every `TodoWrite` emits `todos_updated` with full state
- ✅ **No manual file management** - Query events, not filesystem
- ✅ **Automatic history** - Multiple previous states available via `--previous N`
- ✅ **Consistent format** - JSON output compatible with `TodoWrite` restoration

**Restoration Workflow**:
1. Query previous state: `macf_tools todos list --previous 1`
2. Copy JSON output
3. Use `TodoWrite` tool with the JSON array to restore

---

#### 10.2 Manual Backup (LEGACY)

**⚠️ FALLBACK METHOD**: Use only when event log is unavailable or corrupted.

**When to Use Manual Backup**:
- Event log file missing or corrupted
- Need backup in portable location (disk-based JSON files)
- Cross-system transfer where event log unavailable

**Backup Location**: `agent/public/todo_backups/`

**Rationale**: Public location (consciousness artifacts, not private growth), enables archaeological recovery across sessions/cycles.

**Filename Format**: `YYYY-MM-DD_HHMMSS_S{session_short}_C{cycle}_{mission_description}.json`

**Components**:
- `YYYY-MM-DD_HHMMSS`: Timestamp for chronological sorting
- `{session_short}`: First 8 chars of session UUID (e.g., `c3b658f5`)
- `{cycle}`: Cycle number (e.g., `172`, `173`)
- `{mission_description}`: Semantic slug from active mission (e.g., `Platform_Migration`, `Policy_Integration`)

**Example**: `2025-11-21_135848_c3b658f5_172_TODO_Recovery_Intelligence.json`

**Format**: Raw JSON array (direct copy of TODO list structure from TodoWrite tool)
- Enables direct restoration via TodoWrite
- Preserves breadcrumbs, status, activeForm fields
- Supports archaeological queries via jq, grep

**🚨 ANTI-PATTERN: Collapse-on-Backup**

NEVER create a "backup" that summarizes or collapses the TODO state. A backup that loses information is destruction disguised as preservation.

- ❌ WRONG: Writing a condensed 10-item summary of a 25-item TODO list
- ❌ WRONG: Collapsing archived items into single lines during backup
- ✅ CORRECT: Raw JSON copy of complete TODO structure, every field preserved

The purpose of backup is FULL STATE RECONSTRUCTION, not documentation. If you can't restore the exact TODO state from the backup file via TodoWrite, it's not a backup.

**When to Backup**:

1. **Before CCP creation** (MANDATORY):
   - Capture complete TODO state before strategic checkpoint
   - Enables CCP to cite TODO backup file for complete state reconstruction
   - Part of pre-CCP protocol (see checkpoints.md)

2. **Before major transitions**:
   - Manual compaction (`/compact` command)
   - Session migration events (detected by SessionStart hook)
   - Multi-phase milestone completion

3. **After significant TODO changes**:
   - Major reorganization or archive manipulation
   - Completion of large FTI with extensive nested structure
   - When TODO state represents significant strategic context

**Mission Description Extraction Heuristic**:
- Use top-level active mission name from TODO stack
- Convert to slug: spaces → underscores, max 50 chars
- Example: "🗺️ MISSION: Platform Migration" → `Platform_Migration`
- If multiple active missions: Use most recently started (highest in ACTIVE stack)
- If no missions: Use generic `Current_Work`

**Backup Creation Example**:

```bash
# 1. Extract current TODO list (from Claude Code UI or via inspection)
# Assume TODO list is in variable or file

# 2. Determine components
SESSION_SHORT=$(macf_tools session info | jq -r '.session_id[:8]')
CYCLE=$(macf_tools env | jq -r '.cycle')
MISSION="Platform_Migration"  # Extracted from top active FTI
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

# 3. Create backup filename
BACKUP_FILE="agent/public/todo_backups/${TIMESTAMP}_S${SESSION_SHORT}_C${CYCLE}_${MISSION}.json"

# 4. Write TODO JSON array to backup file
# (Raw JSON from TodoWrite structure)
cat > "$BACKUP_FILE" << 'EOF'
[
  {
    "content": "🗺️ MISSION: Platform Migration",
    "status": "in_progress",
    "activeForm": "Migrating platform"
  },
  {
    "content": "  Phase 1: Preparation",
    "status": "completed",
    "activeForm": "Preparing infrastructure"
  }
]
EOF
```

**Archaeological Citations**: CCPs and reflections can cite TODO backup files using enhanced citation format (see scholarship.md §4.9 for citation pattern).

**Benefits**:
- ✅ Prevents TODO loss during compactions/migrations
- ✅ Enables post-trauma forensic recovery
- ✅ Creates audit trail for work context evolution
- ✅ Supports enhanced citations from CCPs to TODO snapshots
- ✅ Survives session boundaries (disk-based, not memory-based)

**Recovery from Backup**:

```bash
# 1. List available backups chronologically
ls -lt agent/public/todo_backups/

# 2. Identify relevant backup (by cycle, date, or mission)
BACKUP="agent/public/todo_backups/2025-11-21_135848_c3b658f5_172_TODO_Recovery_Intelligence.json"

# 3. Inspect backup content
cat "$BACKUP" | python -m json.tool

# 4. Restore via TodoWrite tool (in CC session)
# Copy JSON array content and use TodoWrite tool
```

**Integration with Checkpoints**: See checkpoints.md for pre-CCP backup protocol integration.

**Integration with Citations**: See scholarship.md §4.9 for TODO backup citation format.

### 11. Session File Migration TODO Recovery

**User Trustworthiness Principle**: When user reports TODO accessibility issues, **TRUST THEM UNCONDITIONALLY**. System-reminders may show TODOs to the agent but user's UI is DISCONNECTED after session migration. The agent sees cached state; the user sees an empty list. **Immediately invoke TodoWrite** when user reports loss—this reconnects their UI regardless of what system-reminders show.

**Problem**: When session ID changes (session migration), the TODO JSON file in `~/.claude/todos/` becomes orphaned because the filename contains the old session ID. The new session starts with an empty TODO list, causing loss of mission and phase context.

**NOT about**: This is distinct from compaction recovery. Compaction preserves session ID but loses conversation context. Session migration creates a new session ID, orphaning the previous TODO file entirely.

**Scenario**: Session crashes, network interruptions, or CC restarts can trigger session ID migration, leaving strategic work context stranded in the previous session's TODO file.

---

#### 11.1 CLI-Based Recovery (CURRENT)

**🚀 PRIMARY METHOD**: Use CLI tools that query the event log directly.

**Why CLI Recovery is Preferred**:
- ✅ **Event log persists across session migrations** - session ID changes don't affect event log
- ✅ **No filesystem archaeology needed** - query events, not orphaned JSON files
- ✅ **Multiple previous states available** - `--previous N` for any historical state
- ✅ **Simpler workflow** - single command instead of multi-step filesystem search

**Recovery Workflow**:
```bash
# 1. Check current TODO status (should show event log state)
macf_tools todos status

# 2. View most recent TODO state from events
macf_tools todos list

# 3. If needed, view previous state
macf_tools todos list --previous 1

# 4. Copy JSON output and use TodoWrite to restore
```

**When CLI Recovery Works**:
- Session migration detected (new session ID)
- Event log file exists and is readable (`.maceff/agent_events_log.jsonl`)
- Previous `todos_updated` events exist in log

---

#### 11.2 Manual Recovery (LEGACY)

**⚠️ FALLBACK METHOD**: Use only when event log is unavailable.

**When to Use Manual Recovery**:
- Event log file missing or corrupted
- No `todos_updated` events exist (pre-v0.3 sessions)
- Cross-system transfer where event log unavailable

**Solution**: Forensic recovery from the previous session's TODO JSON file using filesystem archaeology.

**Recovery Protocol**:

**1. List TODO files by recency**:
```bash
# Show most recent TODO files with size and timestamp
ls -lht ~/.claude/todos/ | head -20
```

**2. Identify previous session**:
- Look for files with size > 100 bytes (indicates content, not empty initialization)
- Most recent file with substantial size is likely the previous session
- Filename format: `{session-hash}-agent-{session-hash}.json`

**3. Read previous session TODO JSON**:
```bash
# View full TODO structure from previous session
cat ~/.claude/todos/{previous-session-hash}-agent-{previous-session-hash}.json

# Or with pretty formatting for complex structures
cat ~/.claude/todos/{previous-session-hash}-agent-{previous-session-hash}.json | python -m json.tool
```

**4. Restore strategic context via TodoWrite**:
- Extract FTI stack (missions, campaigns, active phases, DETOURs)
- Preserve hierarchical nesting with embedded document references
- Maintain breadcrumbs for forensic continuity
- Update status markers if work progressed between sessions

**When to Use**:
- SessionStart hook detects new session ID (indicates session migration occurred)
- TODO list appears empty but strategic work was in progress before crash/restart
- Session crashes or network issues caused unexpected restart
- Manual session restart (user killed CC and restarted)

**What to Restore**:
- ✅ Active missions/campaigns with full FTI nesting
- ✅ Current phases with embedded ROADMAP references (🗺️📋📜)
- ✅ Active DETOURs with sub-tasks (↪️ symbol and nested work)
- ✅ Pending work with strategic importance
- ✅ Document references and breadcrumbs for continuity

**Restoration Example**:
```json
[
  {
    "content": "🗺️ MISSION: Deploy Framework [agent/public/roadmaps/2025-11-18_Deploy_ROADMAP.md]",
    "status": "in_progress",
    "activeForm": "Deploying framework"
  },
  {
    "content": "  📦 Phase 1: Preparation [c_168/s_4107604e/p_abc1234/t_1763400000/g_e5648c9]\n    → agent/public/archives/todos/2025-11-18_120000_Phase1_Complete.md",
    "status": "completed",
    "activeForm": "Phase 1 completed"
  },
  {
    "content": "  Phase 2: Implementation",
    "status": "in_progress",
    "activeForm": "Implementing Phase 2"
  },
  {
    "content": "    → 2.1: Configure environment",
    "status": "completed",
    "activeForm": "Configuring environment"
  },
  {
    "content": "    → 2.2: Deploy services",
    "status": "in_progress",
    "activeForm": "Deploying services"
  }
]
```

**Benefits**:
- ✅ Prevents strategic context loss during session migrations
- ✅ Restores mission → phase → substep hierarchy and visual organization
- ✅ Preserves embedded document references (ROADMAP/DELEG_PLAN links)
- ✅ Maintains breadcrumbs for cross-session forensic continuity
- ✅ Recovers FTI stack priority signaling (active/deferred/completed ordering)
- ✅ Enables continuation of multi-cycle work without context reconstruction overhead

**Automation Opportunity**: Future `maceff-todo-restoration` skill can reference this section for automated recovery protocol implementation.

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

## 12. Minimum Pending Item Requirement

**MANDATORY**: TODO lists must contain at least one `pending` or `in_progress` item at all times.

**Why**: Claude Code UI (as of v2.0.76) has a bug where the TODO tray completely disappears when all items are `completed`. The system internally treats an all-completed list as "empty" despite the JSON file containing valid data. See: https://github.com/anthropics/claude-code/issues/15408

**Workaround**: When all substantive work is complete, add a placeholder pending item:

```json
{
  "content": "Awaiting next task",
  "status": "pending",
  "activeForm": "Awaiting next task"
}
```

**When to Use Placeholder**:
- All mission items are completed
- Session work is done but session continues
- Transitioning between work phases

**What NOT to Do**:
- ❌ Mark all items completed without adding placeholder
- ❌ Leave TODO list in all-completed state (UI will disappear)

**Future**: Remove this workaround when Claude Code fixes issue #15408.

---

## See Also

- `workspace_discipline.md` - Development artifact organization
- `context_management.md` - Session boundaries
- `delegation_guidelines.md` - Subagent task management
- `meta/policy_writing.md` (External References) - How external tools should reference this policy's backup protocol and restoration steps
