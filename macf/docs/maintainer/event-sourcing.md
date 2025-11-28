# Event Sourcing Deep-Dive

This document describes the agent events log event sourcing infrastructure in detail.

## Overview

The macf package implements event sourcing for forensic analysis and state reconstruction. Events are appended to a JSONL (JSON Lines) file with breadcrumb-based querying support.

**File Location**: `.maceff/agent_events_log.jsonl`

**Format**: One JSON object per line (newline-delimited JSON)

**Purpose**:
- Forensic analysis of agent behavior
- State reconstruction at arbitrary timestamps
- Cross-session correlation via breadcrumbs
- Development drive tracking and statistics

## Event Schema

Each event is a JSON object with the following structure:

```json
{
  "timestamp": 1700000000.0,
  "event": "session_started",
  "breadcrumb": "s_abc1234/c_42/g_abc1234/p_abc1234/t_1700000000",
  "data": {
    "session_id": "abc123-def456-...",
    "cycle": 42,
    "custom_field": "value"
  },
  "hook_input": {
    "source": "compact",
    "otherField": "value"
  }
}
```

### Required Fields

- **timestamp** (float): Unix epoch timestamp when event occurred
- **event** (string): Event type in `lowercase_underscore` format
- **breadcrumb** (string): Forensic breadcrumb for querying (format: `s_*/c_*/g_*/p_*/t_*`)
- **data** (object): Event-specific data fields
- **hook_input** (object): Original hook stdin data (may be empty)

### Breadcrumb Format

Breadcrumbs provide forensic coordinates for finding exact context:

**Format**: `s_{session_hash}/c_{cycle}/g_{git_hash}/p_{prompt_uuid}/t_{timestamp}`

**Components**:
- `s` - Session hash (shortened UUID, first 8 chars)
- `c` - Cycle number (integer)
- `g` - Git commit hash (shortened, first 7 chars)
- `p` - Prompt UUID (shortened, first 8 chars)
- `t` - Unix timestamp (integer)

**Example**: `s_4107604e/c_188/g_6597f65/p_abc1234/t_1764297714`

## Event Types

Events are emitted by hook handlers during agent operations.

### Session Events

#### `session_started`

**Emitted By**: `handle_session_start.py`

**When**: New session begins (not compaction or migration)

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "cycle": 42
}
```

#### `compaction_detected`

**Emitted By**: `handle_session_start.py`

**When**: Context compaction detected (93% information loss)

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "cycle": 43,
  "detection_method": "source_field|compact_boundary",
  "compaction_count": 1
}
```

**Notes**:
- `detection_method` shows how compaction was detected
- `cycle` is incremented when compaction occurs
- `compaction_count` tracks compactions within current session

#### `migration_detected`

**Emitted By**: `handle_session_start.py`

**When**: Session ID changed without compaction (crash/restart)

**Data Fields**:
```json
{
  "previous_session": "old-session-id-...",
  "current_session": "new-session-id-...",
  "orphaned_todo_size": 1234,
  "current_cycle": 42
}
```

**Notes**:
- `orphaned_todo_size` is file size in bytes (0 if file not found)
- `current_cycle` remains same (no increment for migration)

### Development Drive Events

#### `dev_drv_started`

**Emitted By**: `handle_user_prompt_submit.py`

**When**: User submits prompt (starts development drive)

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "prompt_uuid": "prompt_abc123-..."
}
```

**Notes**:
- Prompt UUID extracted from hook stdin
- Used for correlating drive start/end events

#### `dev_drv_ended`

**Emitted By**: `handle_stop.py`

**When**: User stops agent or session ends

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "prompt_uuid": "prompt_abc123-...",
  "duration_seconds": 3600.0
}
```

**Notes**:
- Duration calculated from drive start timestamp
- Prompt UUID links back to `dev_drv_started` event

### Future Event Types (Planned)

#### `delegation_started`

**Purpose**: Track subagent delegation start

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "subagent_role": "DevOpsEng",
  "task_description": "Implement feature X"
}
```

#### `delegation_completed`

**Purpose**: Track subagent delegation completion

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "subagent_role": "DevOpsEng",
  "duration_seconds": 1200.0,
  "success": true
}
```

#### `todo_restoration_completed`

**Purpose**: Track TODO file recovery from orphaned files

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "previous_session": "old-session-id-...",
  "todos_restored": 5,
  "restoration_method": "forensic|backup"
}
```

#### `todo_restoration_skipped`

**Purpose**: Track when TODO restoration was not needed

**Data Fields**:
```json
{
  "session_id": "abc123-def456-...",
  "reason": "no_orphaned_file|empty_file|parse_error"
}
```

## CLI Querying API

The `macf_tools events` command provides querying capabilities.

### Basic Commands

#### `events show`

Show most recent events.

```bash
macf_tools events show           # Last 10 events
macf_tools events show --limit 20  # Last 20 events
```

**Output**: Formatted table with timestamp, event type, and key data fields.

#### `events history`

Show event history for current session.

```bash
macf_tools events history
macf_tools events history --session abc123-def456-...
```

**Output**: Chronological list of events for specified session.

### Advanced Querying

#### `events query`

Query events by breadcrumb components and filters.

```bash
# Find all events from cycle 42
macf_tools events query --cycle 42

# Find events from specific git state
macf_tools events query --git-hash abc1234

# Find events in time range
macf_tools events query --since 1700000000 --until 1700001000

# Find specific event type
macf_tools events query --event-type compaction_detected

# Combine filters (AND logic)
macf_tools events query --cycle 42 --event-type dev_drv_started
```

**Filter Options**:
- `--cycle N` - Filter by cycle number
- `--git-hash HASH` - Filter by git commit hash
- `--session-hash HASH` - Filter by session hash (shortened)
- `--event-type TYPE` - Filter by event type
- `--since TIMESTAMP` - Events after timestamp
- `--until TIMESTAMP` - Events before timestamp

#### `events query-set`

Perform set operations on multiple queries.

```bash
# Union: Events from cycle 42 OR cycle 43
macf_tools events query-set union \
  --query1 '{"breadcrumb": {"c": 42}}' \
  --query2 '{"breadcrumb": {"c": 43}}'

# Intersection: Events from cycle 42 AND git state abc1234
macf_tools events query-set intersection \
  --query1 '{"breadcrumb": {"c": 42}}' \
  --query2 '{"breadcrumb": {"g": "abc1234"}}'

# Subtraction: Events from cycle 42 EXCEPT dev_drv events
macf_tools events query-set subtraction \
  --query1 '{"breadcrumb": {"c": 42}}' \
  --query2 '{"event_type": "dev_drv_started"}'
```

**Operations**:
- `union` - Combine results (OR)
- `intersection` - Common results (AND)
- `subtraction` - Remove results (EXCEPT)

#### `events sessions-list`

List unique sessions in event log.

```bash
macf_tools events sessions-list
```

**Output**: Table of session IDs with first/last event timestamps and event counts.

#### `events stats`

Show statistics about events.

```bash
macf_tools events stats
macf_tools events stats --session abc123-def456-...
```

**Output**:
- Total events
- Event types breakdown
- Time range
- Session count
- Average events per session

#### `events gaps`

Find gaps in event timeline (potential issues).

```bash
macf_tools events gaps
macf_tools events gaps --threshold 3600  # Gaps > 1 hour
```

**Output**: List of time gaps between events with duration.

## Set Operations

Set operations enable complex forensic queries.

### Union

Find events matching ANY query.

**Use Case**: "Show me events from cycle 42 OR cycle 43"

**Implementation**:
```python
results = query_set_operations([
    {'breadcrumb': {'c': 42}},
    {'breadcrumb': {'c': 43}}
], 'union')
```

### Intersection

Find events matching ALL queries.

**Use Case**: "Show me compaction events that occurred during git state abc1234"

**Implementation**:
```python
results = query_set_operations([
    {'event_type': 'compaction_detected'},
    {'breadcrumb': {'g': 'abc1234'}}
], 'intersection')
```

### Subtraction

Find events matching first query but NOT subsequent queries.

**Use Case**: "Show me all events from cycle 42 EXCEPT dev_drv events"

**Implementation**:
```python
results = query_set_operations([
    {'breadcrumb': {'c': 42}},
    {'event_type': 'dev_drv_started'},
    {'event_type': 'dev_drv_ended'}
], 'subtraction')
```

## State Reconstruction

Event sourcing enables rebuilding state at arbitrary timestamps.

### Reconstruct State at Timestamp

```python
from macf.agent_events_log import reconstruct_state_at

# Rebuild state at specific time
state = reconstruct_state_at(1700000000.0)

print(state["session_id"])  # Session active at that time
print(state["cycle"])       # Cycle number at that time
```

### Get Current State

```python
from macf.agent_events_log import get_current_state

# Get latest state
state = get_current_state()

print(f"Current: {state['session_id']} Cycle {state['cycle']}")
```

### Slow-Field Tracking

**Concept**: Track fields that change infrequently by scanning events.

**Tracked Fields**:
- `session_id` - Updated by session_started, migration_detected, compaction_detected
- `cycle` - Updated by compaction_detected

**Pattern**: Scan events chronologically, updating tracked fields when present in event data.

**Performance**: O(n) where n is number of events up to timestamp. Acceptable for forensic analysis, not for high-frequency operations.

## Performance Considerations

### Atomic Appends with File Locking

**Problem**: Concurrent appends could corrupt JSONL file.

**Solution**: Use `fcntl.flock()` for exclusive file locking during append.

**Pattern**:
```python
with open(log_path, 'a') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Acquire lock
    try:
        f.write(json.dumps(event) + '\n')
        f.flush()
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock
```

### Breadcrumb Caching

**Problem**: `get_breadcrumb()` is expensive (git commands, JSONL parsing).

**Solution**: 1-second TTL cache.

**Implementation**:
```python
_breadcrumb_cache = {
    "breadcrumb": None,
    "timestamp": 0,
    "ttl": 1.0
}
```

**Benefit**: High-frequency hooks (PreToolUse, PostToolUse) share cached breadcrumb.

### Generator-Based Reading

**Problem**: Large event logs consume memory.

**Solution**: `read_events()` uses generator pattern.

**Implementation**:
```python
def read_events(limit=None, reverse=True):
    for line in lines:
        event = json.loads(line)
        yield event
```

**Benefit**: Iterate over unlimited events with constant memory.

### Query Optimization

**Pattern**: Use breadcrumb component filters first (cheap), then event type filters.

**Avoid**: Full log scans when breadcrumb filters can narrow results.

**Example**:
```python
# Good: Filter by cycle first (narrow results)
query_events({'breadcrumb': {'c': 42}, 'event_type': 'compaction_detected'})

# Less efficient: Filter by event type first (wider results)
query_events({'event_type': 'compaction_detected'})  # Then filter manually
```

## Forensic Use Cases

### Find Compaction Events in Date Range

```bash
# Find compactions between timestamps
macf_tools events query \
  --event-type compaction_detected \
  --since 1700000000 \
  --until 1700100000
```

### Correlate Dev Drives with Git State

```bash
# Find all dev drives during specific git commit
macf_tools events query \
  --event-type dev_drv_started \
  --git-hash abc1234
```

### Analyze Session Migration Patterns

```bash
# Find all migrations
macf_tools events query --event-type migration_detected

# Get statistics
macf_tools events stats
```

### Reconstruct Session Activity

```bash
# Show all events for specific session
macf_tools events history --session abc123-def456-...

# Find what cycles occurred in session
macf_tools events query --session-id abc123-def456-...
```

### Detect Abnormal Gaps

```bash
# Find gaps > 2 hours (potential crashes)
macf_tools events gaps --threshold 7200
```

## Testing Considerations

### Test Isolation

**Problem**: Tests need isolated event logs.

**Solution**: Use `MACF_EVENTS_LOG_PATH` environment variable.

```python
import os
from pathlib import Path

# Test setup
test_log = Path("/tmp/test_events.jsonl")
os.environ["MACF_EVENTS_LOG_PATH"] = str(test_log)

# Run tests...

# Cleanup
test_log.unlink()
```

### Avoiding Side-Effects

**Problem**: Test events pollute production log.

**Solution**: Always set test log path before importing.

```python
# BEFORE imports
os.environ["MACF_EVENTS_LOG_PATH"] = "/tmp/test.jsonl"

# AFTER env var set
from macf.agent_events_log import append_event
```

## File Format Details

### JSONL Structure

Each line is a complete, self-contained JSON object:

```
{"timestamp": 1700000000.0, "event": "session_started", ...}\n
{"timestamp": 1700000100.0, "event": "dev_drv_started", ...}\n
{"timestamp": 1700000200.0, "event": "dev_drv_ended", ...}\n
```

**Benefits**:
- Easy to append (no array structure to maintain)
- Memory-efficient reading (line-by-line)
- Resilient to corruption (one bad line doesn't break entire log)
- Grep-friendly for manual inspection

### File Permissions

**Created With**: `0o600` (user read/write only)

**Rationale**: Event log may contain sensitive session data.

### Malformed Line Handling

**Behavior**: Skip malformed lines silently during reading.

**Rationale**: Corruption in one event shouldn't break forensic analysis of other events.

**Implementation**:
```python
try:
    event = json.loads(line)
    yield event
except json.JSONDecodeError:
    continue  # Skip malformed line
```

## See Also

- [Architecture](architecture.md) - Package structure and design
- [Configuration](../user/configuration.md) - Config files and env vars
- [CLI Reference](../user/cli-reference.md) - Command usage
