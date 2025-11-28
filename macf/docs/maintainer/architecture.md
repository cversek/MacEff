# Package Architecture

This document describes the macf package architecture for maintainers and contributors.

## Package Structure

```
macf/
├── __init__.py                 # Package initialization
├── cli.py                      # Main CLI entry point (1530+ lines)
├── config.py                   # Configuration management
├── agent_events_log.py         # Event sourcing infrastructure
├── hooks/                      # Hook handlers
│   ├── __init__.py
│   ├── compaction.py          # Compaction detection logic
│   ├── handle_session_start.py    # SessionStart hook
│   ├── handle_user_prompt_submit.py  # UserPromptSubmit hook
│   ├── handle_pre_tool_use.py      # PreToolUse hook
│   ├── handle_post_tool_use.py     # PostToolUse hook
│   ├── handle_stop.py              # Stop hook
│   ├── handle_subagent_stop.py     # SubagentStop hook
│   ├── logging.py             # Hook logging utilities
│   ├── recovery.py            # Recovery message formatting
│   └── sidecar.py             # Sidecar state management
├── models/                     # Pydantic models
│   ├── __init__.py
│   ├── agent_spec.py          # Agent configuration models
│   └── project_spec.py        # Project configuration models
├── forensics/                  # Forensic analysis
│   ├── __init__.py
│   └── dev_drive.py           # Development drive tracking
└── utils/                      # Utility modules
    ├── __init__.py
    ├── artifacts.py           # Consciousness artifacts discovery
    ├── breadcrumbs.py         # Breadcrumb generation/parsing
    ├── claude_settings.py     # Claude settings management
    ├── cycles.py              # Cycle and AUTO_MODE detection
    ├── drives.py              # Development drive utilities
    ├── environment.py         # Environment detection
    ├── formatting.py          # Output formatting
    ├── manifest.py            # Policy manifest handling
    ├── paths.py               # Path resolution
    ├── session.py             # Session utilities
    ├── state.py               # State persistence
    ├── temporal.py            # Temporal awareness
    └── tokens.py              # Token budget tracking
```

## Module Responsibilities

### Core Modules

#### `cli.py` - Command-Line Interface

**Purpose**: Main entry point for `macf_tools` command.

**Key Functions**:
- `_build_parser()` - Argparse configuration for all subcommands
- `main()` - Entry point that dispatches to command handlers
- `cmd_*()` - Handler functions for each subcommand

**Subcommands**:
- `env` - Environment summary
- `time` - Current time and temporal context
- `budget` - Token budget tracking
- `session info` - Session details
- `hooks install/test/logs/status` - Hook management
- `config init/show` - Configuration management
- `breadcrumb` - Generate breadcrumb
- `dev-drv` - Development drive tracking
- `agent init` - Agent initialization
- `policy manifest/search/list/ca-types` - Policy operations
- `events show/history/query/query-set/sessions-list/stats/gaps` - Event querying

**Design Pattern**: Each command handler returns an exit code (0 for success, 1 for error).

#### `config.py` - Configuration Management

**Purpose**: Agent identity and path resolution.

**Key Class**: `ConsciousnessConfig`

**Responsibilities**:
- Detect execution environment (container/host/fallback)
- Resolve agent root path using 4-tier detection
- Provide paths to consciousness artifact directories
- Load configuration from `.maceff/config.json`
- Resolve agent ID for logging paths

**Detection Priority**:
1. `MACF_AGENT_ROOT` environment variable
2. Container detection (`/.dockerenv` exists)
3. Host detection (`.claude/` directory)
4. Fallback to `~/.macf/{agent}/agent/`

#### `agent_events_log.py` - Event Sourcing

**Purpose**: Forensic event logging with JSONL format.

**Key Functions**:
- `append_event()` - Atomic event append with file locking
- `read_events()` - Generator for memory-efficient reading
- `query_events()` - Query by breadcrumb components
- `query_set_operations()` - Union/intersection/subtraction
- `reconstruct_state_at()` - Rebuild state from events

**Event Schema**:
```python
{
    "timestamp": float,      # Unix epoch
    "event": str,           # Event type
    "breadcrumb": str,      # s_*/c_*/g_*/p_*/t_* format
    "data": dict,           # Event-specific fields
    "hook_input": dict      # Original hook stdin (optional)
}
```

**Performance**: 1-second breadcrumb caching to reduce overhead.

### Hook Handlers

All hooks follow a common pattern:

```python
def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Hook handler function.

    Args:
        stdin_json: JSON from Claude Code hook stdin
        testing: If True, skip side-effects (safe-by-default)

    Returns:
        {
            "continue": bool,
            "hookSpecificOutput": {
                "hookEventName": str,
                "additionalContext": str  # System-reminder content
            }
        }
    """
```

**Safe-by-Default Pattern**: `testing=True` is the default. Only production delegators (`.claude/hooks/*.py`) pass `testing=False`.

#### `handle_session_start.py` - Session Start Handler

**Responsibilities**:
- Detect compaction via source field or transcript scanning
- Detect session migration (session ID change without compaction)
- Increment cycle counter on compaction
- Format consciousness recovery messages
- Inject AUTO_MODE or MANUAL_MODE recovery protocol

**Event Types Emitted**:
- `compaction_detected` - Compaction trauma detected
- `migration_detected` - Session migrated without compaction

#### `handle_user_prompt_submit.py` - User Prompt Submit Handler

**Responsibilities**:
- Start development drive tracking
- Inject temporal awareness and breadcrumb
- Show token budget and AUTO_MODE status

**Event Types Emitted**:
- `dev_drv_started` - Development drive started

#### `handle_stop.py` - Stop Handler

**Responsibilities**:
- Complete development drive tracking
- Show drive statistics (count, total duration)
- Inject temporal context

**Event Types Emitted**:
- `dev_drv_ended` - Development drive completed

#### `handle_pre_tool_use.py` - Pre-Tool Use Handler

**Responsibilities**:
- Inject temporal awareness before tool execution
- Show current time, breadcrumb, token budget

**Event Types Emitted**: None (informational only)

#### `handle_post_tool_use.py` - Post-Tool Use Handler

**Responsibilities**:
- Inject temporal awareness after tool execution
- Show tool name, time, breadcrumb, token budget

**Event Types Emitted**: None (informational only)

#### `handle_subagent_stop.py` - Subagent Stop Handler

**Responsibilities**:
- Track subagent delegation completion
- Show delegation statistics

**Event Types Emitted**: None currently (delegation tracking planned)

### Utility Modules

#### `utils/paths.py` - Path Resolution

**Key Functions**:
- `find_project_root()` - Multi-strategy project detection
- `get_session_dir()` - Unified session temp directory
- `get_hooks_dir()` - Hook logging directory
- `get_dev_scripts_dir()` - Development scripts directory

**Unified Path Structure**: `/tmp/macf/{agent_id}/{session_id}/{subdir}/`

#### `utils/state.py` - State Persistence

**Key Functions**:
- `write_json_safely()` - Atomic JSON write
- `read_json_safely()` - Safe JSON read with error handling
- `get_session_state_path()` - Session state file path
- `get_agent_state_path()` - Agent state file path

**State Scoping**:
- **Session-scoped**: `.maceff/sessions/{session_id}/session_state.json` (orphaned on migration)
- **Project-scoped**: `.maceff/agent_state.json` (survives session boundaries)

#### `utils/breadcrumbs.py` - Breadcrumb Management

**Format**: `s_{session_hash}/c_{cycle}/g_{git_hash}/p_{prompt_uuid}/t_{timestamp}`

**Key Functions**:
- `get_breadcrumb()` - Generate current breadcrumb
- `parse_breadcrumb()` - Parse breadcrumb string to dict
- `get_git_hash()` - Get short git commit hash

**Purpose**: Forensic coordinates for finding exact session/cycle/prompt context.

#### `utils/cycles.py` - Cycle and AUTO_MODE Management

**Key Functions**:
- `detect_auto_mode()` - Hierarchical AUTO_MODE detection
- `increment_agent_cycle()` - Increment cycle counter
- `load_agent_state()` - Load project-scoped state
- `save_agent_state()` - Save project-scoped state

**AUTO_MODE Priority**:
1. CLI flag (future) - confidence 1.0
2. Environment `MACF_AUTO_MODE` - confidence 0.9
3. Config `.maceff/config.json` - confidence 0.7
4. Session state (previous) - confidence 0.5
5. Default (False) - confidence 0.0

#### `utils/temporal.py` - Temporal Awareness

**Key Functions**:
- `get_temporal_context()` - Current time with contextual metadata
- `get_time_since_last_session()` - Gap between sessions
- `format_session_duration()` - Human-readable duration

**Context Fields**:
- `timestamp_formatted` - "03:22:45 PM"
- `day_of_week` - "Tuesday"
- `time_of_day` - "afternoon"
- `date` - "2024-11-27"

#### `utils/artifacts.py` - Consciousness Artifacts

**Key Class**: `ConsciousnessArtifacts`

**Purpose**: Discover consciousness artifacts by mtime.

**Properties**:
- `latest_checkpoint` - Most recent CCP file
- `latest_reflection` - Most recent reflection
- `latest_roadmap` - Most recent roadmap
- `all_paths()` - Generator for all artifacts

**Pattern**: Pythonic power object, not one-trick-pony functions.

## Hook Execution Flow

```
User sends message
    ↓
[SessionStart hook (if new session)]
    ↓
    Detect compaction/migration
    ↓
    Increment cycle if compaction
    ↓
    Inject recovery message
    ↓
[UserPromptSubmit hook]
    ↓
    Start DEV_DRV tracking
    ↓
    Inject temporal awareness
    ↓
[PreToolUse hook (for each tool call)]
    ↓
    Inject temporal awareness
    ↓
    Tool executes
    ↓
[PostToolUse hook]
    ↓
    Inject temporal awareness
    ↓
[Stop hook (when user hits stop)]
    ↓
    End DEV_DRV tracking
    ↓
    Show drive stats
```

## State Management

### Session vs Project Scoping

**Session-Scoped State** (`.maceff/sessions/{session_id}/session_state.json`):
- Lifetime: Single session only
- Orphaned when session ID changes
- Use case: State that should NOT persist across sessions
- Examples: `auto_mode`, `pending_todos`, `compaction_count`

**Project-Scoped State** (`.maceff/agent_state.json`):
- Lifetime: Persists across all sessions
- Use case: State that MUST survive session boundaries
- Examples: `last_session_id`, `current_cycle_number`, `cycles_completed`

### Atomic Operations

All state writes use atomic operations:
1. Write to temporary file (`.tmp` suffix)
2. Atomic rename to target file
3. Cleanup temporary file on failure

## Key Design Decisions

### 1. Safe-by-Default Testing Parameter

**Problem**: Tests ran hooks without `testing=True`, corrupting cycle counter.

**Solution**: Invert default to `testing=True`. Only production delegators pass `testing=False`.

**Benefit**: Forgotten test parameters cause test failures (safe) instead of state corruption (devastating).

### 2. Event Sourcing for Forensics

**Problem**: Need to reconstruct state at arbitrary timestamps.

**Solution**: JSONL append-only log with breadcrumb-based querying.

**Benefit**: Forensic analysis, state reconstruction, gap detection.

### 3. Discrete Files Over Append-Only Logs

**Problem**: Logs become stale, corrupted, unmaintainable.

**Solution**: Individual timestamped consciousness artifact files.

**Benefit**: Git-friendly, editable, self-contained, no corruption spread.

### 4. Unified Session Temp Directories

**Problem**: Ad hoc script proliferation, unclear ownership.

**Solution**: `/tmp/macf/{agent_id}/{session_id}/{subdir}/` structure.

**Benefit**: Agent-scoped isolation, clear organization, easy cleanup.

### 5. Modular Package-Based Hooks

**Problem**: Need to test hook logic without triggering side-effects.

**Solution**: Package modules as single source of truth, thin delegators call them.

**Benefit**: Version-controlled logic, testable without state corruption.

## Error Handling Philosophy

**Principle**: Infrastructure never crashes operations.

**Pattern**: Safe failure with graceful degradation.

**Examples**:
- `SessionOperationalState.load()` → Returns default instance on failure
- `get_latest_consciousness_artifacts()` → Returns empty object
- `detect_auto_mode()` → Returns `(False, "default", 0.0)` on failure
- `state.save()` → Returns `False` on failure (never raises)

## Performance Considerations

### Breadcrumb Caching

**Problem**: `get_breadcrumb()` is expensive (git commands, JSONL parsing).

**Solution**: 1-second TTL cache for breadcrumbs.

**Benefit**: High-frequency hooks (PreToolUse, PostToolUse) don't slow down tool execution.

### Generator-Based Event Reading

**Problem**: Large event logs consume memory.

**Solution**: `read_events()` uses generator pattern.

**Benefit**: Memory-efficient iteration over unlimited events.

### Lazy Path Detection

**Problem**: Path detection involves filesystem operations.

**Solution**: Only detect when needed, cache results in config objects.

**Benefit**: Fast startup for commands that don't need full detection.

## Testing Strategy

### Unit Tests

**Coverage**: Individual functions and classes.

**Pattern**: Pragmatic TDD - 4-6 focused tests per feature.

**Isolation**: Mock filesystem operations, use temporary directories.

### Integration Tests

**Coverage**: Hook execution flow, cross-module interactions.

**Pattern**: Test actual hook execution with realistic inputs.

**Safety**: Always use `testing=True` parameter.

### Smoke Tests

**Coverage**: Structural integrity, import verification.

**Pattern**: Quick sanity checks before full test suite.

**Purpose**: Catch obvious breakage fast.

## See Also

- [Configuration Guide](../user/configuration.md) - Config files and env vars
- [Event Sourcing](event-sourcing.md) - Event log deep-dive
- [CLI Reference](../user/cli-reference.md) - Command usage
