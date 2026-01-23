# Claude Code Tool Epistemology

**Version**: 1.0.0
**Last Updated**: 2026-01-23
**Claude Code Version**: v2.1.15 - v2.1.17
**Status**: ACTIVE

---

## Purpose

Comprehensive reference for ALL Claude Code native tools documenting arguments, behaviors, return values, and hook integration. Each tool is categorized by function and verified against official documentation, community sources, and empirical testing.

---

## File Operation Tools

### Read

**Purpose**: Retrieve file contents with multimodal support

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | ✅ | Absolute path only |
| `offset` | number | ❌ | Starting line (1-indexed) |
| `limit` | number | ❌ | Maximum lines to read |

**Returns**: Content in `cat -n` format (line number + tab + content)

**Behaviors**:
- Default: First 2000 lines, each capped at 2000 characters
- Multimodal: Images rendered visually, PDFs page-by-page, Jupyter cells with outputs
- Cannot read directories (fails for directory paths)

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

### Write

**Purpose**: Create or completely overwrite files

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | ✅ | Absolute path only |
| `content` | string | ✅ | Complete file contents |

**Returns**: Success confirmation

**Behaviors**:
- Atomic operation (full write or unchanged)
- **Prerequisite**: Must Read file first in current session before overwriting
- Avoids creating docs unless explicitly requested

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

### Edit

**Purpose**: Exact string replacement within files

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | ✅ | Absolute path |
| `old_string` | string | ✅ | Text to find (exact match) |
| `new_string` | string | ✅ | Replacement text |
| `replace_all` | boolean | ❌ | Replace all occurrences (default: false) |

**Returns**: Success message with confirmation

**Behaviors**:
- Literal matching (no regex), case-sensitive, whitespace-sensitive
- Fails if: zero matches OR multiple matches (without replace_all)
- **Prerequisite**: Must Read file first
- Never include line number prefix from Read output in strings

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## Search Tools

### Glob

**Purpose**: Fast file pattern matching

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | ✅ | Glob pattern (`**/*.js`, `src/**/*.ts`) |
| `path` | string | ❌ | Search directory (default: cwd) |

**Returns**: Array of file paths sorted by modification time (newest first)

**Pattern Syntax**: `*` (any chars), `**` (recursive), `?` (single char), `{a,b}` (alternatives), `[abc]` (char class)

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

### Grep

**Purpose**: Content search via ripgrep

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | ✅ | Regex pattern |
| `path` | string | ❌ | File/directory to search |
| `output_mode` | enum | ❌ | `files_with_matches` (default), `content`, `count` |
| `glob` | string | ❌ | Filter by glob pattern |
| `type` | string | ❌ | File type (js, py, rust, etc.) |
| `-i` | boolean | ❌ | Case-insensitive |
| `-n` | boolean | ❌ | Show line numbers (requires output_mode: content) |
| `-A/-B/-C` | number | ❌ | Context lines (requires output_mode: content) |
| `multiline` | boolean | ❌ | Cross-line patterns (default: false) |
| `head_limit` | number | ❌ | Limit output entries |

**Returns**: Varies by output_mode

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## Execution Tools

### Bash

**Purpose**: Execute shell commands in persistent session

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | ✅ | Shell command |
| `description` | string | ❌ | 5-10 word summary |
| `timeout` | number | ❌ | Milliseconds (max 600000, default 120000) |
| `run_in_background` | boolean | ❌ | Async execution |

**Returns**: Command output, exit code

**Behaviors**:
- Persistent working directory across calls
- Output truncated at 30000 characters
- **NEVER use**: `cd` (except in subshells), file ops (cat/grep/find), interactive git flags

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

### NotebookEdit

**Purpose**: Modify Jupyter notebook cells

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `notebook_path` | string | ✅ | Absolute path to .ipynb |
| `new_source` | string | ✅ | New cell content |
| `cell_id` | string | ❌ | Target cell identifier |
| `cell_type` | enum | ❌ | `code` or `markdown` (required for insert) |
| `edit_mode` | enum | ❌ | `replace` (default), `insert`, `delete` |

**Returns**: Success with cell count

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## Delegation Tools

### Task

**Purpose**: Delegate to autonomous sub-agents

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | ✅ | Detailed task description |
| `description` | string | ✅ | 3-5 word summary |
| `subagent_type` | string | ✅ | Agent type (see below) |

**Agent Types**: `general-purpose`, `Explore`, `statusline-setup`, `output-style-setup`

**Returns**: Final report from sub-agent

**Behaviors**:
- Stateless: Each sub-agent starts fresh
- No nesting: Sub-agents cannot spawn sub-agents
- Concurrent: Multiple Task calls can run in parallel

**Hooks**: ✅ PreToolUse, ✅ PostToolUse, ✅ SubagentStart, ✅ SubagentStop

---

### Skill

**Purpose**: Execute user-defined skills from .claude/commands/

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | ✅ | Skill name |

**Returns**: Skill execution result

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## Task Management Tools

### TodoWrite (Legacy - v2.1.15 and earlier)

**Purpose**: Create/manage structured task lists

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todos` | array | ✅ | Array of TodoItem objects |

**TodoItem**: `{content: string, status: "pending"|"in_progress"|"completed", activeForm: string}`

**Returns**: Success confirmation

**Behaviors**:
- Exactly ONE task must be in_progress at any time
- Mark completed IMMEDIATELY upon finishing

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

**⚠️ AVAILABILITY**: Agent-callable in v2.1.15; **NOT available in v2.1.16+** ("No such tool available")

---

### 🚨 Task* Tools (v2.1.16+) - HOOK BYPASSING

**CRITICAL**: These tools bypass ALL hooks. Introduced in v2.1.16 as "new task management system".

#### TaskCreate

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subject` | string | ✅ | Task title/content |
| `description` | string | ❌ | Task details |
| `activeForm` | string | ❌ | Present continuous form |

**Returns**: Task ID confirmation

**Hooks**: ❌ NONE

#### TaskUpdate

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `taskId` | number | ✅ | Task ID to modify |
| `status` | string | ❌ | New status |
| `subject` | string | ❌ | New content |

**Returns**: Success confirmation

**Hooks**: ❌ NONE

#### TaskList

**Parameters**: None

**Returns**: All tasks with ID, status, content

**Hooks**: ❌ NONE

#### TaskGet

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `taskId` | number | ✅ | Task ID to retrieve |

**Returns**: Task details

**Hooks**: ❌ NONE

**Evidence**: [GitHub Issue #20243](https://github.com/anthropics/claude-code/issues/20243)

---

## Web Tools

### WebFetch

**Purpose**: Fetch and analyze URL content

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✅ | Valid URL (max 2000 chars) |
| `prompt` | string | ✅ | Question about page content |

**Returns**: AI-summarized answer (not raw HTML)

**Behaviors**:
- 15-minute cache
- HTML converted to Markdown
- Cross-host redirects reported (require new request)

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

### WebSearch

**Purpose**: Find sources matching queries

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | ✅ | Search term (min 2 chars) |
| `allowed_domains` | array | ❌ | Whitelist domains |
| `blocked_domains` | array | ❌ | Blacklist domains |

**Returns**: Array of {title, url}

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## User Interaction Tools

### AskUserQuestion

**Purpose**: Multi-choice user input

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `questions` | array | ✅ | 1-4 Question objects |

**Question**: `{question: string, header: string (max 12 chars), options: array, multiSelect: boolean}`

**Returns**: User selections

**Hooks**: ✅ PreToolUse, ✅ PostToolUse

---

## Hook Integration Summary

| Tool | PreToolUse | PostToolUse | Notes |
|------|------------|-------------|-------|
| Read, Write, Edit | ✅ | ✅ | Standard file ops |
| Glob, Grep | ✅ | ✅ | Search tools |
| Bash | ✅ | ✅ | Blocking visible in stderr |
| Task | ✅ | ✅ | + SubagentStart/Stop |
| TodoWrite | ✅ | ✅ | v2.1.15 only |
| **TaskCreate** | ❌ | ❌ | **v2.1.16+ - NO HOOKS** |
| **TaskUpdate** | ❌ | ❌ | **v2.1.16+ - NO HOOKS** |
| **TaskList** | ❌ | ❌ | **v2.1.16+ - NO HOOKS** |
| **TaskGet** | ❌ | ❌ | **v2.1.16+ - NO HOOKS** |
| WebFetch, WebSearch | ✅ | ✅ | Web tools |
| AskUserQuestion | ✅ | ✅ | User interaction |
| Skill | ✅ | ✅ | Custom skills |
| NotebookEdit | ✅ | ✅ | Jupyter |

---

## Sources

- [Claude Code Best Practices - Anthropic](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code Docs](https://code.claude.com/docs)
- [ClaudeLog Tool References](https://claudelog.com/mechanics/task-agent-tools/)
- [GitHub Issues - anthropics/claude-code](https://github.com/anthropics/claude-code/issues)
- Direct empirical testing (v2.1.15, v2.1.16, v2.1.17)

---

**Document Status**: ACTIVE | **Last Verified**: v2.1.17 (2026-01-23)
