# Configuration Guide

This document describes all configuration files and environment variables used by the macf package.

## Configuration Files

### `.maceff/config.json` - Unified Config Layer

Location: `{project_root}/.maceff/config.json` (resolved via `find_agent_home`).

The canonical per-project configuration file. Replaces ad-hoc `~/.zshenv` / `~/.bashrc` env-var workarounds for deployment-wide settings. Per-project config travels with the repo, doesn't pollute the shell environment, and is enumerable via `macf_tools config show`.

**Structure** (all blocks optional):
```json
{
  "agent_identity": {
    "calling_card": "ShortName",
    "moniker": "FullAgentName",
    "description": "Optional human-readable description",
    "created": "2024-11-01T12:00:00Z"
  },
  "context": {
    "window": 1000000,
    "low_context_cl": 5
  },
  "session": {
    "user_idle_timeout_mins": 10
  }
}
```

**Resolution chain** (highest priority first; per-setting):

1. **Inline env var** — `MACF_CONTEXT_WINDOW=200000 macf_tools ...` (explicit one-off override)
2. **`.maceff/config.json`** at the relevant dotted path (per-project default)
3. **Hard-coded default** (last-resort fallback)

Use **inline env vars** for ephemeral overrides (one invocation, one test). Use **`.maceff/config.json`** for persistent per-project defaults. **Anti-pattern**: baking persistent settings into `~/.zshenv` or `~/.bashrc` — these don't travel with the repo and silently break when running the same project on a different machine.

**Migrated settings**:

| Setting | Env Var | Config Path | Default | Description |
|---------|---------|-------------|---------|-------------|
| Context window | `MACF_CONTEXT_WINDOW` | `context.window` | `200000` | Total context window in tokens |
| Low-context CL | `MACF_LOW_CONTEXT_CL` | `context.low_context_cl` | `5` | CL below which LOW_CONTEXT engages |
| Idle timeout | `MACF_USER_IDLE_TIMEOUT_MINS` | `session.user_idle_timeout_mins` | `10` | Minutes before USER_IDLE engages |
| Calling card | `MACEFF_AGENT_NAME` | `agent_identity.calling_card` | (none) | Display name for the agent |

**Inspect resolution** at any time:
```bash
macf_tools config show
```
Output shows each setting's resolved value plus which layer supplied it (`env`, `config`, or `default`). Use `--json` for programmatic consumers.

**Adding new migrations**: extend `RESOLVED_SETTINGS` in `macf/src/macf/config.py` with the four-tuple (`name`, `env_var`, `config_path`, `default` + optional `coerce`). The consumer site then calls `resolve_setting(...)` instead of `os.environ.get(...)`.

**Fields** in the `agent_identity` block:
- `calling_card` - Short-form display name (preferred). Resolved by `get_agent_identity` for statusline / Telegram signatures.
- `moniker` - Full / formal agent name. Used as fallback when `calling_card` is absent.
- `description` - Optional human-readable description.
- `created` - Timestamp of config creation.

**Usage**: `ConsciousnessConfig.agent_id` (host context) reads `agent_identity.moniker`; `get_agent_identity` (utils/identity.py) prefers `agent_identity.calling_card` then falls back to `moniker`.

### `.maceff/agent_state.json` - **DEPRECATED**

> ⚠️ **Event-First Architecture (v0.3+)**: State is now derived from `.maceff/agent_events_log.jsonl`.
> These state files are no longer written or read. Kept in docs for legacy backup compatibility only.

~~Location:~~
- ~~**Container**: `/home/{agent}/.maceff/agent_state.json` (agent-scoped)~~
- ~~**Host**: `{project_root}/.maceff/agent_state.json` (project-scoped)~~

~~Persistent state that survives session boundaries.~~

**Structure**:
```json
{
  "last_session_id": "abc123...",
  "last_session_ended_at": 1700000000.0,
  "current_cycle_number": 42,
  "cycles_completed": 41
}
```

**Fields**:
- `last_session_id` - Last known session UUID (for migration detection)
- `last_session_ended_at` - Unix timestamp when last session ended
- `current_cycle_number` - Current cycle counter (increments on compaction)
- `cycles_completed` - Number of completed cycles

**Lifecycle**: Persists across all sessions for the project/agent.

### `.maceff/sessions/{session_id}/session_state.json` - Session State

Location:
- **Container**: `/home/{agent}/.maceff/sessions/{session_id}/session_state.json`
- **Host**: `{project_root}/.maceff/sessions/{session_id}/session_state.json`

Session-specific state that does NOT persist across session boundaries.

**Structure**:
```json
{
  "session_id": "abc123...",
  "auto_mode": true,
  "auto_mode_source": "env",
  "auto_mode_confidence": 0.9,
  "compaction_count": 2,
  "pending_todos": [
    {
      "content": "Task 1",
      "status": "pending",
      "activeForm": "Working on task 1"
    }
  ],
  "current_dev_drv_started_at": 1700000000.0,
  "current_dev_drv_prompt_uuid": "prompt_abc123...",
  "dev_drv_count": 3,
  "total_dev_drv_duration": 3600.0,
  "last_updated": 1700000000.0
}
```

**Fields**:
- `session_id` - Current session UUID
- `auto_mode` - Whether AUTO_MODE is enabled
- `auto_mode_source` - Source of auto_mode setting ("env", "config", "session", "default")
- `auto_mode_confidence` - Confidence score 0.0-1.0
- `compaction_count` - Number of compactions in this session
- `pending_todos` - TODO items for recovery
- `current_dev_drv_started_at` - Current development drive start time
- `current_dev_drv_prompt_uuid` - UUID of prompt that started drive
- `dev_drv_count` - Number of development drives completed
- `total_dev_drv_duration` - Total seconds spent in drives
- `last_updated` - Unix timestamp of last state update

**Lifecycle**: Created when session starts, orphaned when session ID changes.

### `.maceff/agent_events_log.jsonl` - Event Sourcing Log

Location: `{project_root}/.maceff/agent_events_log.jsonl`

JSONL append-only log for forensic event sourcing.

**Format**: One JSON object per line
```json
{"timestamp": 1700000000.0, "event": "session_started", "breadcrumb": "s_abc1234/c_42/g_abc1234/p_abc1234/t_1700000000", "data": {"session_id": "abc123...", "cycle": 42}, "hook_input": {}}
```

**Schema**:
- `timestamp` - Unix epoch timestamp
- `event` - Event type (see Event Types section in event-sourcing.md)
- `breadcrumb` - Forensic breadcrumb for querying
- `data` - Event-specific data fields
- `hook_input` - Original hook stdin data (optional)

**Querying**: Use `macf_tools events query` commands.

## Environment Variables

### `MACF_AUTO_MODE`

**Purpose**: Control AUTO_MODE behavior for post-compaction recovery.

**Values**:
- `true`, `1`, `yes` - Enable AUTO_MODE
- `false`, `0`, `no` - Disable AUTO_MODE (MANUAL mode)

**Priority**: Environment variable takes precedence over config file (confidence 0.9).

**Example**:
```bash
export MACF_AUTO_MODE=true
```

### `MACF_AGENT_ROOT`

**Purpose**: Override agent root path detection.

**Value**: Absolute path to agent root directory.

**Priority**: Highest priority in path resolution (overrides all detection).

**Example**:
```bash
export MACF_AGENT_ROOT=/Users/user/project/agent
```

### `MACF_PROJECT_ROOT`

**Purpose**: Override project root detection.

**Value**: Absolute path to project root directory.

**Validation**: Path must exist and contain "tools" marker directory.

**Example**:
```bash
export MACF_PROJECT_ROOT=/Users/user/project
```

### `MACEFF_USER`

**Purpose**: Agent username in container contexts.

**Value**: Username string (e.g., "pa_user001").

**Context**: Used in container environments for agent identification.

**Example**:
```bash
export MACEFF_USER=pa_user001
```

### `MACF_EVENTS_LOG_PATH`

**Purpose**: Override events log file path for testing.

**Value**: Absolute path to JSONL log file.

**Example**:
```bash
export MACF_EVENTS_LOG_PATH=/tmp/test_events.jsonl
```

### `MACF_SESSION_RETENTION_DAYS`

**Purpose**: Configure session retention policy.

**Value**: Integer number of days.

**Default**: 7 days.

**Example**:
```bash
export MACF_SESSION_RETENTION_DAYS=14
```

### `CLAUDE_PROJECT_DIR`

**Purpose**: Claude Code project directory (used for project root detection).

**Value**: Absolute path to project directory.

**Priority**: Second priority after `MACF_PROJECT_ROOT`.

**Example**:
```bash
export CLAUDE_PROJECT_DIR=/Users/user/project
```

## Path Resolution

The macf package uses a 4-tier detection system for finding agent root:

### 1. Environment Override (Highest Priority)

```bash
export MACF_AGENT_ROOT=/custom/path/agent
```

If `MACF_AGENT_ROOT` is set and valid, use it directly.

### 2. Container Detection

**Marker**: `/.dockerenv` file exists

**Resolution**: `/home/{USER}/agent`

**Example**: `/home/pa_user001/agent`

### 3. Host with Project Detection

**Marker**: `.claude/` directory found by walking up from cwd

**Resolution**: `{project_root}/agent`

**Example**: `/Users/user/project/agent`

### 4. Fallback

**Resolution**: `~/.macf/{agent_name}/agent`

**Example**: `/Users/user/.macf/ClaudeTheBuilder/agent`

## Configuration Examples

### Container Environment

```bash
# Container setup (automatic detection)
# /.dockerenv exists → uses /home/pa_user001/agent

macf_tools session info
# Shows:
# Agent Root: /home/pa_user001/agent
# Agent ID: pa_user001 (from MACEFF_USER)
```

### Host Development

```bash
# Host setup (project-scoped)
cd /Users/user/project
macf_tools config init  # Creates .maceff/config.json

# Project root detected → uses /Users/user/project/agent
macf_tools session info
# Shows:
# Agent Root: /Users/user/project/agent
# Agent ID: ClaudeTheBuilder (from .maceff/config.json moniker)
```

### Custom Override

```bash
# Override detection for special cases
export MACF_AGENT_ROOT=/custom/location/agent

macf_tools session info
# Shows:
# Agent Root: /custom/location/agent
# Agent ID: (detected from environment or config)
```

## See Also

- [CLI Reference](cli-reference.md) - Command usage
- [Hooks Guide](hooks.md) - Hook installation and usage
- [Architecture](../maintainer/architecture.md) - System design
- [Event Sourcing](../maintainer/event-sourcing.md) - Event log details
