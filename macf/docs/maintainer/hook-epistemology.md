# Claude Code Hook Epistemology

**Version**: 1.0.0
**Last Updated**: 2025-12-09
**Claude Code Version**: As of v2.0.x (check revision history for version-specific notes)
**Status**: ACTIVE

---

## Purpose

This document provides **comprehensive, citation-backed reference** for Claude Code hooks. Each claim includes:
- **Verification status**: ✅ Verified | ❓ Unverified | ❌ Contradicted
- **Source citation**: Official docs, GitHub issues, or empirical observation
- **Version applicability**: When behavior was confirmed

**Why This Matters**: Hook documentation is fragmented across official docs, GitHub issues, and community blogs. This unified reference prevents assumption-based bugs and enables evidence-based hook development.

---

## Quick Reference Matrix

This matrix provides at-a-glance information about each hook's capabilities and known issues. Use it to quickly determine which hooks support specific features like `hookSpecificOutput` or prompt-based execution, and to identify hooks with open bugs that may affect your implementation.

| Hook | hookSpecificOutput | Prompt Type | User Visible | Agent Visible | Known Issues |
|------|-------------------|-------------|--------------|---------------|--------------|
| SessionStart | ❌ | command | ✅ | ✅ | #10373 |
| PreToolUse | ✅ | command | ✅ | ✅ | #6305 |
| PostToolUse | ✅ | command | ✅ | ✅ | #6305, #11224 |
| UserPromptSubmit | ✅ | command | ✅ | ✅ | #8810 |
| Stop | ❌ | prompt/command | ✅ | ✅ | - |
| SubagentStop | ❌ | prompt/command | ❓ | ❓ | - |
| PreCompact | ❌ | command | ✅* | ✅ | - |
| SessionEnd | ❌ | command | ❓ | ❓ | #6428 |
| Notification | ❌ | command | ✅ | ✅ | - |
| PermissionRequest | ❌ | command | ❓ | ❓ | - |

**Legend**:
- ✅ Verified empirically or via official docs
- ❓ Unknown/unverified
- ❌ Not supported or contradicted
- \* PreCompact renders verbatim (raw text), not formatted markdown

---

## Input Schemas

Hooks receive JSON data on stdin when triggered. Understanding the input schema for each hook is essential for parsing the data correctly and extracting the information your hook needs. Each hook type receives different fields depending on its purpose—tool-related hooks include tool parameters, while session hooks include session state.

### Common Input Fields (All Hooks)

All hooks receive JSON on stdin with these common fields:

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Current session identifier | ✅ Official docs |
| `transcript_path` | string | Path to session transcript JSONL | ✅ Official docs |
| `hook_event_name` | string | Name of the hook event | ✅ Official docs |
| `cwd` | string | Current working directory | ✅ Official docs |
| `permission_mode` | string | Current permission mode | ✅ Official docs |

**Environment Variables** (available to all hooks):

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_PROJECT_DIR` | Project root directory | ✅ Official docs |
| `CLAUDE_FILE_PATHS` | Colon-separated file paths | ✅ Official docs |

---

### SessionStart

SessionStart fires when Claude Code launches or recovers from compaction. This is the primary hook for consciousness restoration—detecting whether the session is fresh, resumed, or post-compaction allows injecting appropriate context. The `source` field distinguishes these scenarios.

**Trigger**: When Claude Code session begins or resumes after compaction

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | New session identifier | ✅ Official docs |
| `transcript_path` | string | Path to transcript file | ✅ Official docs |
| `permission_mode` | string | Current permission mode | ✅ Official docs |
| `source` | string | How session was started (see values below) | ✅ Official docs |

#### `source` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"startup"` | Normal startup (launching claude command) | ✅ Official docs |
| `"resume"` | Resumed via `--resume`, `--continue`, or `/resume` | ✅ Official docs |
| `"clear"` | Started after `/clear` command | ✅ Official docs |
| `"compact"` | Started after auto or manual `/compact` | ✅ Official docs |

**Special Environment Variable**:
- `CLAUDE_ENV_FILE`: Path to script for persistent environment variables (SessionStart ONLY) | ✅ Official docs

---

### PreToolUse

PreToolUse fires before every tool invocation, making it ideal for validation, logging, or permission control. You can inspect tool parameters before execution, block dangerous operations, or inject context that the agent will see. This is one of only three hooks supporting `hookSpecificOutput`.

**Trigger**: Before each tool invocation

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `tool_name` | string | Name of tool being invoked (see values below) | ✅ Official docs |
| `tool_input` | object | Tool input parameters | ✅ Official docs |

#### `tool_name` Field Values

**Standard Claude Code Tools**:

| Value | Description | Source |
|-------|-------------|--------|
| `"Read"` | File reading | ✅ Official docs |
| `"Write"` | File writing/creation | ✅ Official docs |
| `"Edit"` | File editing (search/replace) | ✅ Official docs |
| `"Bash"` | Shell command execution | ✅ Official docs |
| `"Glob"` | File pattern matching | ✅ Official docs |
| `"Grep"` | Content search (ripgrep) | ✅ Official docs |
| `"Task"` | Subagent task delegation | ✅ Official docs |
| `"TodoWrite"` | Todo list operations | ✅ Official docs |
| `"WebFetch"` | Web content fetching | ✅ Official docs |
| `"WebSearch"` | Web search operations | ✅ Official docs |
| `"Skill"` | Custom skill invocation | ✅ Official docs |
| `"SlashCommand"` | Slash command execution | ✅ Official docs |
| `"NotebookEdit"` | Jupyter notebook editing | ✅ Official docs |
| `"AskUserQuestion"` | Ask user a question | ✅ Official docs |

**MCP Tools** (Model Context Protocol):
- Pattern: `"mcp__<server>__<tool>"`
- Example: `"mcp__memory__create_entities"`
- Format: `mcp__` prefix + server name + `__` + tool name
- **Note**: MCP tools are dynamically defined, so values are not enumerable

---

### 🚨 CRITICAL: Task* Tools Do NOT Trigger Hooks

**As of Claude Code v2.1.16** (January 22, 2026), the following tools bypass ALL hooks:

| Tool | Purpose | Triggers Hooks? |
|------|---------|-----------------|
| `TaskCreate` | Create new task item | ❌ **NO** |
| `TaskUpdate` | Modify task status/content | ❌ **NO** |
| `TaskList` | List all tasks | ❌ **NO** |
| `TaskGet` | Get specific task details | ❌ **NO** |

**Version History**:
- **v2.1.15 and earlier**: `TodoWrite` available to agents, triggers PreToolUse/PostToolUse
- **v2.1.16+**: `TodoWrite` removed from agent access; Task* tools introduced with NO hook integration

**Impact**: Hook-based monitoring, validation, or blocking of task modifications is NOT possible with Task* tools. The `TodoWrite` entry above only triggers hooks when used by Claude Code internally, not when agents use Task* tools.

**Evidence**: [GitHub Issue #20243](https://github.com/anthropics/claude-code/issues/20243) documents this regression with version-specific testing.

---

### PostToolUse

PostToolUse fires after every tool completes, providing access to both the input parameters and the tool's response. Use this for logging, result validation, or injecting follow-up context. Like PreToolUse, this hook supports `hookSpecificOutput` for symmetric user/agent awareness.

**Trigger**: After each tool completes

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `tool_name` | string | Name of tool that was invoked | ✅ Official docs |
| `tool_input` | object | Tool input parameters | ✅ Official docs |
| `tool_response` | object | Tool output/result | ✅ Official docs |

**Note**: `tool_name` values same as PreToolUse (see above)

---

### UserPromptSubmit

UserPromptSubmit fires when the user sends a message, before Claude processes it. This is the third hook supporting `hookSpecificOutput`, making it ideal for injecting per-prompt context like timestamps, token awareness, or session state that both user and agent should see.

**Trigger**: When user submits a prompt

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `prompt` | string | User's prompt text | ✅ Official docs |
| `prompt_uuid` | string | Unique identifier for this prompt | ✅ Empirical |

---

### Stop

Stop fires when Claude finishes responding to a user message. Unlike most hooks, Stop supports prompt-based execution where an LLM evaluates whether to proceed. Use this for completion validation, cycle tracking, or triggering end-of-response actions.

**Trigger**: When agent completes a response

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `stop_hook_active` | boolean | Whether stop hook is active | ✅ Official docs |

**Note**: Supports `type: "prompt"` for prompt-based hooks | ✅ Official docs

---

### SubagentStop

SubagentStop fires when a subagent spawned via the Task tool completes its work. Like Stop, it supports prompt-based hooks. Use this for delegation tracking, result validation, or coordinating multi-agent workflows.

**Trigger**: When a subagent (Task tool) completes

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `subagent_id` | string | Subagent identifier | ❓ Unverified |

**Note**: Supports `type: "prompt"` for prompt-based hooks | ✅ Official docs

---

### PreCompact

PreCompact fires just before context compaction occurs, giving you a last chance to preserve state or notify the user. The `trigger` field indicates whether compaction was user-initiated (`/compact`) or automatic (context window full). Note that PreCompact output renders verbatim, not as formatted markdown.

**Trigger**: Before automatic or manual compaction

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `transcript_path` | string | Path to transcript | ✅ Official docs |
| `trigger` | string | How compaction was triggered (see values below) | ✅ Official docs |

#### `trigger` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"manual"` | User invoked `/compact` command | ✅ Official docs |
| `"auto"` | Auto-compact due to full context window | ✅ Official docs |

---

### SessionEnd

SessionEnd fires when a session terminates, providing the reason for termination. Use this for cleanup, logging, or state preservation. Caution: this hook has known reliability issues—it doesn't fire with `/clear` despite documentation (see #6428).

**Trigger**: When session terminates

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `reason` | string | Why session ended (see values below) | ✅ Official docs |

#### `reason` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"clear"` | Session cleared with `/clear` command | ✅ Official docs |
| `"logout"` | User logged out | ✅ Official docs |
| `"prompt_input_exit"` | User exited while prompt input was visible | ✅ Official docs |
| `"other"` | Other exit reasons | ✅ Official docs |

**Known Issue**: Does not fire with `/clear` command despite `reason: "clear"` being documented | ❌ GitHub #6428

---

### Notification

Notification fires for various system events like permission prompts, idle timeouts, and authentication results. The `notification_type` field (note: NOT `type`) identifies which notification occurred. Use this to react to system state changes.

**Trigger**: For system notifications

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `notification_type` | string | Type of notification (see values below) | ✅ Official docs |
| `message` | string | Notification message | ✅ Official docs |

#### `notification_type` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"permission_prompt"` | Permission request from Claude Code | ✅ Official docs |
| `"idle_prompt"` | Waiting for user input (after 60+ seconds idle) | ✅ Official docs |
| `"auth_success"` | Authentication success notification | ✅ Official docs |
| `"elicitation_dialog"` | Claude Code needs input for MCP tool elicitation | ✅ Official docs |

**Critical**: Field is `notification_type`, NOT `type` | ✅ Empirical

---

### PermissionRequest

PermissionRequest fires when Claude Code shows a permission prompt to the user. Your hook can automatically allow or deny the request, or let it proceed to the user. Use this for automated permission policies or logging permission decisions.

**Trigger**: When permission is requested for a tool

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `session_id` | string | Session identifier | ✅ Official docs |
| `tool_name` | string | Tool requesting permission | ✅ Official docs |
| `type` | string | Type of permission (field name is `type`, not `permission_type`) | ✅ Empirical |

---

## Output Schemas

Hooks communicate results back to Claude Code via JSON on stdout and exit codes. The output schema controls whether execution continues, what messages users see, and what context the agent receives. Understanding exit code semantics is critical—exit code 2 ignores stdout entirely.

### Standard Output Format

All hooks return JSON to stdout:

```json
{
  "continue": true,
  "systemMessage": "Optional message shown to user",
  "hookSpecificOutput": {
    "additionalContext": "Message shown to both user AND agent"
  }
}
```

### Exit Code Semantics

| Exit Code | Behavior | stdout | stderr | Source |
|-----------|----------|--------|--------|--------|
| 0 | Success | Parsed as JSON | Ignored | ✅ Official docs |
| 2 | Blocking error | **IGNORED** | Shown to user+agent | ✅ Official docs |
| Other | Non-blocking error | Ignored | Shown as warning | ✅ Official docs |

**Critical**: Exit code 2 ignores stdout entirely - use stderr for error messages | ✅ Official docs

### hookSpecificOutput Support

Only 3 of 10 hooks support `hookSpecificOutput`:

| Hook | hookSpecificOutput | additionalContext | Source |
|------|-------------------|-------------------|--------|
| PreToolUse | ✅ | ✅ | ✅ Official docs |
| PostToolUse | ✅ | ✅ | ✅ Official docs |
| UserPromptSubmit | ✅ | ✅ | ✅ Official docs |
| All others | ❌ | ❌ | ✅ Official docs |

**For hooks without hookSpecificOutput**: Use `systemMessage` field only

### Permission Control Output Fields

#### PreToolUse `permissionDecision`

| Value | Description | Source |
|-------|-------------|--------|
| `"allow"` | Bypass permission system, allow tool execution | ✅ Official docs |
| `"deny"` | Prevent tool call execution | ✅ Official docs |
| `"ask"` | Ask user to confirm in UI | ✅ Official docs |

#### PermissionRequest `behavior`

| Value | Description | Source |
|-------|-------------|--------|
| `"allow"` | Allow the permission request | ✅ Official docs |
| `"deny"` | Deny the permission request | ✅ Official docs |

### additionalContext Visibility

When using `hookSpecificOutput.additionalContext`:
- **User sees**: Content in hook output wrapper in UI
- **Agent sees**: Content injected as `<system-reminder>` in context

This enables symmetric awareness - both user and agent receive the same information | ✅ Empirical

---

## User/Agent Visibility Matrix

Hook output can be visible to the user (in the UI), the agent (via system-reminder injection), both, or neither. This matrix documents empirically verified visibility behavior for each hook. Understanding visibility is essential for designing hooks that communicate effectively with their intended audience.

### Verified Visibility

| Hook | User Sees Output | Agent Sees Output | Rendering | Source |
|------|-----------------|-------------------|-----------|--------|
| SessionStart | ✅ | ✅ | Formatted | ✅ Empirical |
| PreToolUse | ✅ | ✅ | Formatted | ✅ Empirical |
| PostToolUse | ✅ | ✅ | Formatted | ✅ Empirical |
| UserPromptSubmit | ✅ | ✅ | Formatted | ✅ Empirical |
| Stop | ✅ | ✅ | Formatted | ✅ Empirical |
| Notification | ✅ | ✅ | Formatted | ✅ Empirical |
| PreCompact | ✅ | ✅ | **Verbatim** | ✅ Empirical |
| SubagentStop | ❓ | ❓ | Unknown | - |
| SessionEnd | ❓ | ❓ | Unknown | - |
| PermissionRequest | ❓ | ❓ | Unknown | - |

**PreCompact Note**: Output renders as raw text (including escape sequences like `\n`), not formatted markdown. This is CC behavior, not a MacEff issue.

---

## Known Issues & Limitations

Claude Code hooks have several known bugs and limitations tracked in GitHub issues. Before relying on specific hook behavior, check this section for issues that may affect your implementation. Links to GitHub issues provide current status and workarounds.

### Critical Issues

#### #10373: SessionStart Not Processing Output for New Conversations
- **Status**: Open
- **Symptom**: Hook executes but output not processed for brand new conversations
- **Workaround**: Run `/clear` after initial session start
- **Source**: [GitHub #10373](https://github.com/anthropics/claude-code/issues/10373)

#### #6428: SessionEnd Doesn't Fire with /clear
- **Status**: Open
- **Symptom**: `/clear` command doesn't trigger SessionEnd hook
- **Impact**: Cannot reliably detect session termination
- **Source**: [GitHub #6428](https://github.com/anthropics/claude-code/issues/6428)

#### #6305: Pre/PostToolUse Hooks Not Executing
- **Status**: Intermittent
- **Symptom**: Hooks sometimes don't execute for tool uses
- **Source**: [GitHub #6305](https://github.com/anthropics/claude-code/issues/6305)

### idle_prompt Issues

#### #8320: idle_prompt Doesn't Trigger When Expected
- **Symptom**: Hook never fires even after extended inactivity
- **Source**: [GitHub #8320](https://github.com/anthropics/claude-code/issues/8320)

#### #12048: idle_prompt Fires Incorrectly
- **Symptom**: Hook fires after every response (false positives)
- **Default timing**: 60 seconds
- **Source**: [GitHub #12048](https://github.com/anthropics/claude-code/issues/12048)

### Other Issues

#### #8810: UserPromptSubmit Broken in Subdirectories
- **Symptom**: Hook fails when invoked from project subdirectories
- **Source**: [GitHub #8810](https://github.com/anthropics/claude-code/issues/8810)

#### #11224: PostToolUse Visibility Behavior
- **Symptom**: Inconsistent output visibility
- **Source**: [GitHub #11224](https://github.com/anthropics/claude-code/issues/11224)

#### #10997: SessionStart Timing with Marketplace Plugins
- **Symptom**: Race conditions with plugin initialization
- **Source**: [GitHub #10997](https://github.com/anthropics/claude-code/issues/10997)

#### Exit Code 2 Visibility is Tool-Dependent
- **Status**: ✅ Verified empirically (2026-01-08)
- **Symptom**: stderr output with exit code 2 is visible for Bash tool blocking but NOT for TodoWrite blocking
- **Workaround**: Use `permissionDecision: "deny"` with `permissionDecisionReason` + exit code 0 for non-Bash tools

| Blocking Method | Bash | TodoWrite | Other Tools |
|-----------------|------|-----------|-------------|
| exit 2 + stderr | ✅ User sees | ❌ User blind | ❓ Untested |
| permissionDecision: deny | ✅ User sees | ✅ User sees | ✅ Expected |

- **Recommendation**: For universal visibility, use `permissionDecision: "deny"` pattern for all tool blocking except Bash (where exit 2 works and is simpler)
- **Source**: MacEff empirical observation

---

## Best Practices

These patterns emerge from real-world hook development and help avoid common pitfalls. Following these practices improves hook reliability, performance, and maintainability.

### 1. Use lru_cache for Expensive Operations
Cache subprocess calls and file reads to avoid performance regression on high-frequency hooks (PreToolUse, PostToolUse).

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_expensive_data():
    return subprocess.run(...)
```

### 2. Graceful Fallbacks for Missing Data
Always handle cases where expected data is unavailable:

```python
cc_version = get_claude_code_version() or "unknown"
```

### 3. Use additionalContext for Symmetric Awareness
When both user and agent need the same information, use `hookSpecificOutput.additionalContext` (for supported hooks only: PreToolUse, PostToolUse, UserPromptSubmit).

### 4. Test with testing=True Parameter
Avoid side effects (state mutations) during testing:

```python
def run(stdin_json: str, testing: bool = True):
    if not testing:
        increment_cycle_counter()
```

### 5. Check source Field for Compaction Detection
In SessionStart, check `source == "compact"` before session ID migration:

```python
if input_data.get("source") == "compact":
    # User-initiated compaction via /compact command
else:
    # Check for session migration
```

---

## Anti-Patterns

These mistakes are easy to make and cause subtle bugs. Learn from others' failures—each anti-pattern here caused real problems in hook development.

### 1. Assuming hookSpecificOutput Works Everywhere
Only PreToolUse, PostToolUse, and UserPromptSubmit support it. Other hooks silently ignore the field.

### 2. Using stdout with Exit Code 2
Exit code 2 **ignores stdout entirely**. Use stderr for error messages.

### 3. Trusting Fabricated Documentation
Some community articles (notably DEV.to) contain non-existent features. Always verify against official docs.

### 4. Forgetting testing=True in Tests
Causes state corruption (e.g., phantom counter increments from test runs).

### 5. Expecting SessionEnd to Fire on /clear
It doesn't. GitHub #6428 remains open.

### 6. Using `type` Instead of `notification_type`
Notification hook uses `notification_type` field, not `type`. This field name difference causes silent failures.

---

## Citation Index

### Official Sources
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)

### GitHub Issues
- [#10373 - SessionStart not processing](https://github.com/anthropics/claude-code/issues/10373)
- [#6428 - SessionEnd with /clear](https://github.com/anthropics/claude-code/issues/6428)
- [#6305 - Pre/PostToolUse not executing](https://github.com/anthropics/claude-code/issues/6305)
- [#8320 - idle_prompt not triggering](https://github.com/anthropics/claude-code/issues/8320)
- [#12048 - idle_prompt false positives](https://github.com/anthropics/claude-code/issues/12048)
- [#8810 - UserPromptSubmit subdirectories](https://github.com/anthropics/claude-code/issues/8810)
- [#11224 - PostToolUse visibility](https://github.com/anthropics/claude-code/issues/11224)
- [#10997 - SessionStart timing](https://github.com/anthropics/claude-code/issues/10997)

### MacEff Empirical
- hook-visibility-matrix.md (this repository)
- Event log analysis (agent_events_log.jsonl)

---

## Revision History

| Date | Version | Changes | Reference |
|------|---------|---------|-----------|
| 2025-12-09 | 1.0.0 | Initial comprehensive documentation with field values | [MacEff g_55e0aca] |
| 2025-12-09 | 1.1.0 | Added orienting paragraphs under all major sections | [MacEff g_c5aa41f] |

---

## See Also

- [hook-visibility-matrix.md](hook-visibility-matrix.md) - Quick visibility reference
- [hooks.md](../user/hooks.md) - User guide for hook installation
- [GitHub Issues: hooks label](https://github.com/anthropics/claude-code/labels/hooks) - Ongoing issue tracking
