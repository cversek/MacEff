---
name: maceff-todo-restoration
description: USE IMMEDIATELY when (1) SessionStart hook detects new session ID (session file migration) OR (2) user reports TODO accessibility issues after compaction/session events. Restores TODO context using two-tier recovery - official backups from current/last cycle (PRIMARY) or forensic recovery from orphaned files (FALLBACK).
allowed-tools: Read, Bash, Grep, TodoWrite
---

## User Trustworthiness Principle

**CRITICAL**: When user reports TODO accessibility issues, **TRUST THEM UNCONDITIONALLY**.

**The Agent/User UI Disconnect**:
- System-reminders may show TODOs to the AGENT (you)
- But user's UI is DISCONNECTED after session migration
- User cannot see what you see in system-reminders
- Anthropic's system-reminders reflect AGENT state, not USER UI state

**Mandatory Response to User Report**:
1. User says "I lost access to TODOs" → **TRUST THIS**
2. Do NOT say "TODOs are already accessible" based on system-reminders
3. **IMMEDIATELY invoke TodoWrite** to restore user's UI connection
4. The act of TodoWrite reconnects the user's UI regardless of agent state

**Why This Matters**:
- Session migration orphans the TODO file (new session ID = new filename)
- Agent may still see old TODOs via cached system-reminders
- User's UI points to new (empty) session file
- Only TodoWrite creates the new session's TODO file

## Policy Engagement Protocol

Navigate `framework/policies/base/development/todo_hygiene.md` using CEP navigation:

1. **First access**: Read from beginning to `=== CEP_NAV_BOUNDARY ===` marker
2. **Locate sections**: Scan navigation guide for BOTH "TODO Backup Protocol" AND "Session File Migration TODO Recovery"
3. **Grep navigation**: Find section headers + boundaries for each
4. **Selective read**: Read backup protocol first (official backups), then forensic recovery (fallback) using offset/limit

## Questions to Extract from Policy Reading

**TODO Backup Protocol Questions** (check official backups FIRST):
1. **Where are official TODO backups stored?**
2. **What filename format identifies TODO backups?**
3. **How do you determine if a backup is from current or last cycle?**
4. **What validation criteria indicate a suitable backup?**
5. **What are the recovery steps using official backups?**

**Session File Migration Recovery Questions** (forensic fallback):
6. **What causes TODO file orphaning during session migration?**
7. **Where are orphaned TODO files located?**
8. **How do you identify the previous session's TODO file?**
9. **What should be restored to preserve strategic context?**
10. **What TodoWrite format preserves hierarchical structure?**

## Execution

**Three-Tier Recovery Strategy**:

1. **PRIMARY: Official Backup Recovery**
   - Check backup location from policy
   - Identify backups from current/last cycle using filename pattern
   - Validate and restore using steps from backup protocol

2. **FALLBACK: Forensic Recovery**
   - Only if no suitable official backup exists
   - Search orphaned file location from policy
   - Apply forensic identification and recovery steps

3. **TIER 3: Event Log Intelligence** (when forensics need guidance)
   - Query agent_events_log for `migration_detected` events
   - Extract `orphaned_todo_size` and `current_cycle` from event data
   - Apply heuristics:
     - `size < 100`: Skip (empty placeholder) → append `todo_restoration_skipped`
     - `size > 200 AND cycle > 50`: Restore (substantial work) → append `todo_restoration_completed`
     - Otherwise: Ask user for decision
   - Record all decisions as events for forensic trail

**Event Log Query Pattern**:
```python
from macf.agent_events_log import query_events, append_event

# Find migrations without matching restorations
migrations = query_events({'event_type': 'migration_detected'})
restorations = query_events({'event_type': 'todo_restoration_completed'})
skips = query_events({'event_type': 'todo_restoration_skipped'})

# Check latest migration for restoration status
# Extract: orphaned_todo_size, current_cycle
# Apply heuristics, then append outcome event
```

## Critical Meta-Pattern

**Policy as API**: Skill uses CEP navigation for selective policy reading. As sections reorganize or content evolves, navigation guide adapts automatically.

## Version History

- v2.0 (2025-11-26): Three-tier recovery with event log intelligence (Tier 3). Heuristics: size < 100 skip, size > 200 + cycle > 50 restore, else ask user. Event outcome tracking.
- v1.2 (2025-11-22): Added user-reported TODO accessibility issues as explicit activation condition
- v1.1 (2025-11-22): Two-tier recovery strategy - official backups (PRIMARY) before forensic recovery (FALLBACK). Timeless content references instead of section numbers.
- v1.0 (2025-11-18): Session migration TODO recovery via CEP navigation
