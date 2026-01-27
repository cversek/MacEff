# Claude Code Task System Internals

**Type**: Maintainer Documentation
**Status**: Current as of Claude Code 2.1.20
**Scope**: Task file format, visibility requirements, extension patterns

---

## Overview

Claude Code's Task List is a file-based persistence system. This document describes its architecture, requirements for task visibility, and extension patterns for MACF tooling.

## File System Architecture

### Location
```
~/.claude/tasks/{session_uuid}/{task_id}.json
```

| Component | Description |
|-----------|-------------|
| Root directory | `~/.claude/tasks/` |
| Session folders | Full UUID (e.g., `77270981-bd9d-4d0f-ad09-3702f5b0d1cb`) |
| Task files | `{id}.json` - one file per task |

### JSON Schema

```json
{
  "id": "string",           // Task ID - MUST BE STRING
  "subject": "string",      // Display text (supports emoji)
  "description": "string",  // Detailed description (NOT shown in UI)
  "activeForm": "string",   // REQUIRED - Present tense (e.g., "Running tests")
  "status": "string",       // "pending" | "in_progress" | "completed"
  "blocks": [],             // Array of task IDs this task blocks
  "blockedBy": []           // Array of task IDs blocking this task
}
```

## CC Visibility Requirements

**CRITICAL**: For tasks to appear in CC's UI and native tools, the JSON must meet these requirements:

| Field | Requirement | Effect if Wrong |
|-------|-------------|-----------------|
| `id` | **Must be STRING** (`"88"` not `88`) | Task invisible to CC |
| `activeForm` | **Must be present** | Task invisible to CC |

### Discovery Context

CLI-created tasks with integer `id` and missing `activeForm`:
- Exist on disk ✅
- Readable by external tools ✅
- **Invisible to CC UI** ❌
- **Invisible to native TaskList** ❌
- Session restarts do NOT fix visibility

### Examples

**WRONG** (invisible to CC):
```json
{
  "id": 88,
  "subject": "My Task",
  "description": "...",
  "status": "pending"
}
```

**CORRECT** (visible to CC):
```json
{
  "id": "88",
  "subject": "My Task",
  "description": "...",
  "activeForm": "Working on My Task",
  "status": "pending"
}
```

## Native Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `TaskCreate` | Create new task | Sets id/activeForm correctly |
| `TaskUpdate` | Update task fields | Full file rewrite |
| `TaskList` | List all tasks | Only shows visible tasks |
| `TaskGet` | Get single task | Returns task by ID |
| `TaskDelete` | **DOES NOT EXIST** | Use file deletion |

**Key Limitation**: No native tool for task deletion.

## CC Version-Specific Behaviors

### CC 2.1.20: Task ID Column Removed

**Change**: In CC 2.1.20, the task ID column was removed from the UI display.

**Before** (CC 2.1.19):
```
#67. [in_progress] 🗺️ MISSION: Task CLI
#68. [pending] [^#67] 📋 Phase 1
```

**After** (CC 2.1.20):
```
  ◼ 🗺️ MISSION: Task CLI
  ◻ [^#67] 📋 Phase 1
```

**MACF Workaround**: Embed task ID with ANSI dim codes in subject:
- CLI `task create` commands prepend dim `#N` to subjects
- CC UI **DOES render ANSI escape codes** (discovered via testing!)
- Example stored: `\033[2m#89\033[0m \033[2m[^#67]\033[0m 📋 Phase 4`
- Example rendered: dim `#89` dim `[^#67]` normal `📋 Phase 4`

**Subject Format**:
```
#{task_id} [^#{parent_id}] {emoji} {title}
```

## File System Behaviors

### Modification
- Direct JSON edits are **immediately reflected** in CC tools and UI
- No caching layer - CC reads files on each access

### Deletion
- Removing `{id}.json` file removes task from CC immediately
- TaskGet returns "Task not found"
- UI updates instantly

### TaskUpdate Behavior
- **Full file rewrite** - overwrites entire JSON
- Standard schema fields preserved
- **Custom JSON fields are CLOBBERED**

## ID Assignment

ID assignment uses `max(existing_file_IDs) + 1`:

| Scenario | Behavior |
|----------|----------|
| Delete non-max ID | Gap persists, ID not reused |
| Delete max ID (same session) | In-memory counter continues |
| Delete max ID (after restart) | Counter recalculates, ID reused |

**Implication**: IDs are reliable within session, but max-ID reuse can occur across restarts.

## UI Ordering

Tasks displayed in order:
1. **Status grouping**: `in_progress` → `pending` → `completed`
2. **Within status**: Ordered by numeric task ID (ascending)
3. **Truncation**: Completed tasks show as "+N completed" after threshold

## MACF Extension Patterns

### Task Deletion (via file system)
```bash
rm ~/.claude/tasks/{session_uuid}/{task_id}.json
```
Safe and immediate. Recommended for programmatic task cleanup.

### Metadata Storage

**❌ Custom JSON fields** - Clobbered by TaskUpdate
```json
{
  "id": "1",
  "custom_field": "...",  // WILL BE DELETED on TaskUpdate
}
```

**✅ Description field** - Survives TaskUpdate
```
Task description text.

<macf_task_metadata version="1.0">
creation_breadcrumb: s_.../c_.../g_.../p_.../t_...
created_cycle: 42
created_by: PA
</macf_task_metadata>
```

### Description Field Properties
- NOT shown in user UI (only `subject` displayed)
- Survives TaskUpdate operations
- No apparent size limit (tested to 100KB+)
- Supports any text including XML-like tags

## Multi-Agent Coordination

### Subagent Task Storage
- Subagents CAN use Task* tools
- Tasks stored in **parent session folder** (shared visibility)
- PA and all SAs share the same task list

### SA Naming Convention
```
[SA:{agent_type}] {subject}
```

Examples:
- `[SA:DevOpsEng] Implement CLI command`
- `[SA:TestEng] Write unit tests`

## CLI Integration

The `macf_tools task create` suite handles visibility requirements automatically:

```bash
# All commands create CC-visible tasks with correct id/activeForm
macf_tools task create mission "Title" [--repo] [--version]
macf_tools task create experiment "Title"
macf_tools task create phase --parent N "Title"
macf_tools task create bug --parent N "Title"
```

## Cross-References

- [CLI Reference: Task Commands](../user/cli-reference.md)
- [Task Management Policy](../../../framework/policies/base/development/task_management.md)
