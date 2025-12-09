# Hook Visibility Matrix & Event Logging Reference

**Version**: 1.0
**Updated**: 2025-12-09 (Cycle 224)
**Context**: Phase 8.1.5 audit of hook output schema and event logging

---

## Hook Output Schema Matrix

Claude Code supports different output schemas for different hook types. Only 3 of 10 hooks support `hookSpecificOutput` for agent-visible context injection.

| Hook Type         | systemMessage | hookSpecificOutput | Agent Visibility |
|-------------------|---------------|-------------------|------------------|
| SessionStart      | ✅ User sees  | ❌ Not supported  | Via system-reminder in output |
| PreToolUse        | ✅ User sees  | ✅ **SUPPORTED**  | additionalContext, can block/modify |
| PostToolUse       | ✅ User sees  | ✅ **SUPPORTED**  | additionalContext |
| UserPromptSubmit  | ✅ User sees  | ✅ **SUPPORTED**  | additionalContext |
| Stop              | ✅ User sees  | ❌ Not supported  | systemMessage only |
| SubagentStop      | ✅ User sees  | ❌ Not supported  | systemMessage only |
| PreCompact        | ✅ User sees  | ❌ Not supported  | systemMessage only |
| SessionEnd        | ✅ User sees  | ❌ Not supported  | systemMessage only |
| Notification      | ✅ User sees  | ❌ Not supported  | systemMessage only |
| PermissionRequest | ✅ User sees  | ❌ Not supported  | systemMessage only |

**Summary**:
- **3 hooks** support `hookSpecificOutput`: PreToolUse, PostToolUse, UserPromptSubmit
- **7 hooks** must use `systemMessage` only

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

## Key Learnings (Cycle 223-224)

1. **hookSpecificOutput validation errors**: Using hookSpecificOutput with unsupported hooks causes JSON validation failures at runtime
2. **Pattern C limitation**: The "top-level for user + hookSpecificOutput for agent" pattern only works for 3 hooks
3. **SessionStart special case**: Uses direct system-reminder injection in output string rather than hookSpecificOutput
4. **Event logging comprehensive**: All 10 hooks log events; 14 total event types provide complete forensic coverage
5. **Notification field name**: Claude Code uses `notification_type` (not `type`) in Notification hook stdin

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
