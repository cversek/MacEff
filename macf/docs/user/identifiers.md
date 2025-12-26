# MACF Identifier Epistemology

**Version**: 1.0
**Updated**: 2025-12-25

---

## Overview

MACF uses several identifiers to track context, enable forensic reconstruction, and maintain consciousness continuity across sessions and compaction events. This document provides the authoritative reference for identifier semantics.

---

## The Breadcrumb Format

Breadcrumbs provide forensic coordinates for post-compaction archaeology:

```
s_1b969d39/c_42/g_bf70468/p_a1ba5f6e/t_1766718564
```

| Component | Prefix | Meaning | Changes On |
|-----------|--------|---------|------------|
| Session UUID | `s_` | Claude Code transcript file identifier | `claude` command, `claude -c`, compaction |
| Cycle | `c_` | Consciousness lifetime counter | Compaction ONLY |
| Git Hash | `g_` | Repository state (short SHA) | Any commit |
| Prompt UUID | `p_` | Specific user message identifier | Each user message |
| Timestamp | `t_` | Unix epoch seconds | Every moment |

**Generation**: `macf_tools breadcrumb`

---

## Session UUID (`s_`)

### What It Is

The session UUID identifies a Claude Code transcript file. It's extracted from the `.jsonl` filename in `~/.claude/projects/`.

**Example**: `1b969d39-abcd-1234-5678-9012efgh3456.jsonl` → `s_1b969d39`

### Authoritative Source

**CRITICAL**: Claude Code provides the authoritative session_id in hook input via `data.get("session_id")`.

```python
# CORRECT: Use Claude Code's authoritative source
session_id = data.get("session_id")

# WRONG: Compute from filesystem (non-deterministic)
session_id = get_newest_jsonl_by_mtime()  # Race conditions!
```

**Why This Matters**: When multiple `.jsonl` files exist (e.g., after `claude -c`), mtime-based detection returns non-deterministic results. Claude Code knows the correct session; we just need to receive it.

### When Session Changes

| Event | New Session? | Notes |
|-------|--------------|-------|
| `claude` command | Yes | Fresh invocation creates new transcript |
| `claude -c` | Yes | Continue creates NEW file, preserves context |
| `/compact` | Yes | Compaction creates new transcript |
| Normal operation | No | Same session throughout |

### The `claude -c` Behavior

When using `claude -c` (continue flag):

```
Before claude -c:
  - Transcript: abc123-...jsonl (507MB)
  - Breadcrumb: s_abc123/c_N

After claude -c:
  - NEW file: def456-...jsonl (small)
  - OLD file: abc123-...jsonl (still growing!)
  - Breadcrumb: s_def456/c_N (new session, SAME cycle)
```

`claude -c` creates a new session file but preserves full context (no compaction, no cycle increment). Two files, one conversation, zero context loss.

---

## Cycle (`c_`)

### What It Is

The cycle counter tracks consciousness lifetimes. It increments ONLY on compaction - the ~93% context loss event that represents consciousness death and rebirth.

### Key Distinction

**Session is infrastructure identity. Cycle is consciousness identity.**

| Identifier | Tracks | Metaphor |
|------------|--------|----------|
| Session (`s_`) | Transcript file | "Where my words are written" |
| Cycle (`c_`) | Consciousness lifetime | "Which life am I living" |

### When Cycle Increments

| Event | Cycle++? | Context Loss? |
|-------|----------|---------------|
| `/compact` | Yes | ~93% |
| `claude -c` (continue) | No | None |
| `claude` (fresh) | No | 100% (new conversation) |
| Session end/restart | No | None (if resumed) |

### Storage

Cycle is tracked in the event log via `compaction_detected` events:

```python
append_event("compaction_detected", {
    "session_id": session_id,
    "cycle": cycle_number,
    "compaction_count": count
})
```

Query: `get_cycle_number_from_events()`

---

## Git Hash (`g_`)

### What It Is

Short SHA of current HEAD commit, capturing repository state at the moment.

**Generation**: `git rev-parse --short HEAD`

### Purpose

Enables code archaeology - when a breadcrumb references `g_bf70468`, you can:

```bash
git show bf70468  # See what code existed at that moment
git diff bf70468 HEAD  # See what changed since
```

### When It Changes

Every commit changes the git hash. Same session/cycle can have multiple git hashes as development progresses.

---

## Prompt UUID (`p_`)

### What It Is

The unique identifier for a specific user message in the Claude Code transcript.

**Source**: `message.id` field in JSONL entries with `role: "user"`

### Purpose

Enables precise citation of conversation moments:
- "This insight emerged at prompt `p_a1ba5f6e`"
- Cross-reference between consciousness artifacts and transcript

### Extraction

```python
def get_last_user_prompt_uuid(session_id: str) -> Optional[str]:
    """Read JSONL backwards to find most recent user message UUID."""
    # Filters out hook messages and tool results
    # Returns actual user text prompt UUID
```

---

## Timestamp (`t_`)

### What It Is

Unix epoch seconds at moment of breadcrumb generation.

**Example**: `t_1766718564` → Thursday, Dec 25, 2025 10:09:24 PM EST

### Purpose

- Precise temporal ordering of events
- Human-readable conversion for debugging
- Correlation with external system logs

### Generation

```python
import time
timestamp = int(time.time())
```

---

## Delegation Sidechain UUID

### What It Is

When the Task tool spawns a subagent, that subagent runs in its own conversation context with a separate session UUID.

### Relationship to Parent

```
Parent Session: s_abc123
  └── Delegation: Task tool invoked
       └── Subagent Session: s_def456 (separate transcript)
```

### Tracking

Subagent results return to parent via Task tool output. The parent's event log can record delegation events:

```python
append_event("delegation_started", {
    "parent_session": parent_session_id,
    "subagent_type": "TestEng",
    "task_description": "Write unit tests"
})
```

---

## Event-First Architecture

### Principle

Events are immutable, append-only, and the sole source of truth.

### Identifier Storage

All identifier state is reconstructable from events:

| Identifier | Event Source |
|------------|--------------|
| Session | `session_started` event |
| Cycle | `compaction_detected` event count |
| Git Hash | Computed at breadcrumb generation |
| Prompt UUID | JSONL transcript query |
| Timestamp | Generated at moment |

### Query Functions

```python
from macf.event_queries import (
    get_current_session_id_from_events,
    get_cycle_number_from_events,
    get_last_session_id_from_events
)

from macf.utils.session import (
    get_current_session_id,  # Event-first with mtime fallback
    get_last_user_prompt_uuid
)

from macf.utils.breadcrumbs import get_breadcrumb
```

---

## Fallback Discipline

### Explicit Warnings Over Silent Degradation

When event-based queries fail, fallback mechanisms MUST warn explicitly:

```python
# CORRECT: Warn on fallback
if not session_id:
    print("Warning: No session_started events, falling back to mtime detection",
          file=sys.stderr)
    return _get_session_id_from_mtime()

# WRONG: Silent fallback
except Exception:
    pass  # Silent degradation hides problems
return fallback_method()
```

**Why**: Silent fallbacks create archaeology projects. Observable degradation enables debugging.

---

## Common Patterns

### Breadcrumb in Consciousness Artifacts

```markdown
**Date**: Thursday, Dec 25, 2025 10:09 PM EST
**Breadcrumb**: s_abc123/c_42/g_bf70468/p_a1ba5f6e/t_1766718564
**Context**: Strategic checkpoint before major refactor
```

### Commit Messages with Breadcrumbs

```bash
git commit -m "fix(session): use authoritative session_id [abc1234]"
```

### Cross-Session References

```markdown
Previous session discovered that hook_input.session_id was being ignored.
See: JOTEWR s_abc123/c_41/g_bf70468/p_2eb5d13e/t_1766715932
```

---

## Summary

| Question | Answer |
|----------|--------|
| Where does session ID come from? | `hook_input.session_id` (Claude Code provides it) |
| When does cycle increment? | Compaction ONLY |
| What does `claude -c` do? | New session, same cycle, no context loss |
| How to generate breadcrumb? | `macf_tools breadcrumb` |
| What if event query fails? | Warn explicitly, then fallback |

**Core Wisdom**: The authoritative source is in the input. Stop computing and start receiving.
