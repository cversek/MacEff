# Event Sourcing Guide

This document explains how to use the event-first architecture in macf v0.3.0+.

## Overview

macf uses **event sourcing** as the primary mechanism for state management. Instead of reading/writing state files, all state is derived from an append-only event log.

**Key Principle**: Events are the sole source of truth. State files (`.maceff/agent_state.json`, `session_state.json`) are deprecated.

## Event Log Location

**File**: `.maceff/agent_events_log.jsonl`

**Format**: JSON Lines (one JSON object per line)

## Querying Events

### CLI Commands

```bash
# Show current agent state (derived from events)
macf_tools events show

# Show recent events
macf_tools events history --limit 20

# Query by event type
macf_tools events query --event session_started

# Query by cycle
macf_tools events query --cycle 42

# Query by session
macf_tools events query --session abc123

# Show event statistics
macf_tools events stats

# Detect gaps (potential crashes)
macf_tools events gaps --threshold 3600
```

### Common Event Types

| Event | Description |
|-------|-------------|
| `session_started` | New session began |
| `compaction_detected` | Context compaction occurred (cycle increment) |
| `dev_drv_started` | Development drive began |
| `dev_drv_completed` | Development drive ended |
| `deleg_drv_started` | Delegation drive began |
| `deleg_drv_completed` | Delegation drive ended |
| `migration_detected` | Session migration (restart without compaction) |
| `todos_updated` | TODO list state captured after successful TodoWrite |
| `todos_auth_collapse` | Authorization granted for TODO list collapse |
| `todos_auth_cleared` | TODO collapse authorization consumed or expired |

## Breadcrumbs

Every event includes a **breadcrumb** - forensic coordinates for finding exact context:

**Format**: `s_{session}/c_{cycle}/g_{git}/p_{prompt}/t_{timestamp}`

**Example**: `s_1b969d39/c_286/g_5dc6aa1/p_abc123/t_1766115000`

**Generate current breadcrumb**:
```bash
macf_tools breadcrumb
```

## State Reconstruction

State is reconstructed by scanning events backwards from the most recent:

```python
# Example: Get current cycle number
from macf.event_queries import get_current_cycle_from_events
cycle = get_current_cycle_from_events()

# Example: Get development drive stats
from macf.event_queries import get_dev_drv_stats_from_events
stats = get_dev_drv_stats_from_events(session_id)
```

## Migration from State Files

**Before (v0.2.x)**:
```python
# Reading state file directly
with open('.maceff/agent_state.json') as f:
    state = json.load(f)
    cycle = state['current_cycle_number']
```

**After (v0.3.0+)**:
```python
# Query events for state
from macf.event_queries import get_current_cycle_from_events
cycle = get_current_cycle_from_events()
```

## Benefits

1. **Forensic Trail**: Complete history of all state changes
2. **Corruption Resistance**: Append-only prevents partial writes
3. **Reproducibility**: Reconstruct state at any point in time
4. **Cross-Session Correlation**: Breadcrumbs link across compaction boundaries

## See Also

- [CLI Reference](cli-reference.md) - Full command documentation
- [Configuration](configuration.md) - Event log environment variables
- [Architecture](../maintainer/architecture.md) - Implementation details
