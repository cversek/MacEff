# Hook Visibility Matrix & Event Logging Reference

**Version**: 1.1
**Updated**: 2026-01-08
**Context**: Phase 8.1.5 audit of hook output schema and event logging

---

## Hook Output Schema Matrix

Claude Code supports different output schemas for different hook types. Only 3 of 10 hooks support `hookSpecificOutput` for agent-visible context injection.

| Hook Type         | systemMessage | hookSpecificOutput | User Visibility | Agent Visibility |
|-------------------|---------------|-------------------|-----------------|------------------|
| SessionStart      | ✅ Yes        | ❌ Not supported  | ✅ Confirmed    | Via system-reminder in output |
| PreToolUse        | ✅ Yes        | ✅ **SUPPORTED**  | ✅ Confirmed    | additionalContext, can block/modify |
| PostToolUse       | ✅ Yes        | ✅ **SUPPORTED**  | ✅ Confirmed    | additionalContext |
| UserPromptSubmit  | ✅ Yes        | ✅ **SUPPORTED**  | ✅ Confirmed    | additionalContext |
| Stop              | ✅ Yes        | ❌ Not supported  | ✅ Confirmed    | systemMessage only |
| SubagentStop      | ✅ Yes        | ❌ Not supported  | ❓ Unknown      | systemMessage only |
| PreCompact        | ✅ Yes        | ❌ Not supported  | ✅ Confirmed*   | systemMessage only |
| SessionEnd        | ✅ Yes        | ❌ Not supported  | ❓ Unknown      | systemMessage only |
| Notification      | ✅ Yes        | ❌ Not supported  | ✅ Confirmed    | systemMessage only |
| PermissionRequest | ✅ Yes        | ❌ Not supported  | ❓ Unknown      | systemMessage only |

**Summary**:
- **3 hooks** support `hookSpecificOutput`: PreToolUse, PostToolUse, UserPromptSubmit
- **7 hooks** must use `systemMessage` only

**\* PreCompact Rendering Note**: Unlike other hooks that display as `{HookName} says:` with rendered markdown, PreCompact output appears verbatim with raw JSON (escaped unicode like `\ud83c\udfd7\ufe0f` and literal `\n` characters). The content is visible but not formatted.

---

## hookSpecificOutput Schema (for supported hooks)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse" | "PostToolUse" | "UserPromptSubmit",
    "additionalContext": "string (agent sees this)",
    "permissionDecision": "allow" | "deny" | "ask",  // PreToolUse only
    "permissionDecisionReason": "string",             // PreToolUse only
    "updatedInput": {}                                // PreToolUse only
  }
}
```

---

## Event Logging Coverage

All hooks log events to `.maceff/agent_events_log.jsonl` for forensic reconstruction.

| Hook               | Event Name            | Key Data Fields |
|--------------------|-----------------------|-----------------|
| SessionStart       | `session_started`     | session_id, cycle, environment |
| SessionStart       | `compaction_detected` | previous_session, compaction_count |
| SessionStart       | `migration_detected`  | previous_session, reason |
| SessionStart       | `auto_mode_detected`  | indicator |
| UserPromptSubmit   | `dev_drv_started`     | prompt_uuid, session_id |
| PreToolUse         | `tool_call_started`   | tool_name, tool_input |
| PreToolUse         | `delegation_started`  | agent_type (when Task tool) |
| PostToolUse        | `tool_call_completed` | tool_name, duration |
| Stop               | `dev_drv_ended`       | duration, tool_count, stats |
| SubagentStop       | `delegation_completed`| agent_id, duration, success |
| PreCompact         | `pre_compact`         | breadcrumb, cluac_level |
| SessionEnd         | `session_ended`       | reason, tokens_used |
| Notification       | `notification_received`| notification_type, message |
| PermissionRequest  | `permission_requested`| tool_name, permission_type |

**Total Events**: 14 distinct event types across 10 hooks

---

## Forensic Query Examples

```bash
# Find all compaction events
macf_tools events query --event compaction_detected

# Find all tool calls in a session
macf_tools events query --event tool_call_started --session abc12345

# Find DEV_DRV duration stats
macf_tools events query --event dev_drv_ended --fields duration,tool_count

# Find delegation results
macf_tools events query --event delegation_completed --fields success,duration
```

---

## PreToolUse Blocking Visibility (Tool-Dependent Behavior)

**CRITICAL FINDING**:

Exit code 2 + stderr messaging has **tool-dependent user visibility**:

| Tool Blocked | Exit Code 2 + stderr | User Sees Message? |
|--------------|---------------------|-------------------|
| Bash         | ✅ Works            | ✅ Yes            |
| TodoWrite    | ❌ Silent           | ❌ No (user blind)|
| Other tools  | ❓ Unknown          | Needs testing     |

**The Problem**: When PreToolUse hook blocks with `exit 2` and stderr message, user visibility depends on which tool triggered the hook. Bash users see the stderr message; TodoWrite users see nothing.

**The Solution**: Use `permissionDecision: "deny"` pattern for universal user visibility:

```json
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Your message here - user WILL see this"
  }
}
```

**Why This Works**: The `permissionDecision: "deny"` routes through JSON parsing (exit 0), not stderr capture. This provides consistent user-facing messaging regardless of which tool was blocked.

**Discovery Context**: Discovered empirically while implementing TODO collapse blocking. The same hook code that worked for Bash blocking failed silently for TodoWrite blocking. Cross-agent testing revealed the tool-dependent polymorphism.

---

## Key Learnings

1. **hookSpecificOutput validation errors**: Using hookSpecificOutput with unsupported hooks causes JSON validation failures at runtime
2. **Pattern C limitation**: The "top-level for user + hookSpecificOutput for agent" pattern only works for 3 hooks
3. **SessionStart special case**: Uses direct system-reminder injection in output string rather than hookSpecificOutput
4. **Event logging comprehensive**: All 10 hooks log events; 14 total event types provide complete forensic coverage
5. **Notification field name**: Claude Code uses `notification_type` (not `type`) in Notification hook stdin
6. **Exit code 2 is tool-polymorphic**: stderr visibility when blocking with exit 2 depends on which tool triggered PreToolUse. Use `permissionDecision: "deny"` for universal user visibility.

---

## Notification Types Reference

Known `notification_type` values from Claude Code:

| Type | Description | Timing |
|------|-------------|--------|
| `permission_prompt` | Tool permission request shown to user | Immediate when permission needed |
| `idle_prompt` | "Claude is waiting for your input" | 60 seconds after input idle (default) |

**idle_prompt Caveats** (from GitHub issues #8320, #12048):
- **False positives**: May fire after EVERY response, not just when genuinely idle
- **False negatives**: Some users report it never triggers even after 60+ seconds
- **Known reliability issues**: Feature may need fundamental redesign to distinguish genuine idle waiting vs normal operation completion

More types may exist (e.g., `auth_success`) but haven't been observed yet in this deployment

---

## Related Documentation

- `macf/docs/user/hooks.md` - User-facing hook installation guide
- `macf/docs/maintainer/architecture.md` - Internal design patterns
- `macf/docs/maintainer/event-sourcing.md` - Event log query patterns
