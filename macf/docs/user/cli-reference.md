# MACF CLI Reference

Complete command reference for `macf_tools` CLI.

## Table of Contents

- [Global Options](#global-options)
- [Environment Commands](#environment-commands)
- [Session Commands](#session-commands)
- [Context & Token Management](#context--token-management)
- [Hook Management](#hook-management)
- [Configuration](#configuration)
- [Agent Management](#agent-management)
- [Consciousness Artifacts](#consciousness-artifacts)
- [Development Drives](#development-drives)
- [Policy Management](#policy-management)
- [Event Sourcing](#event-sourcing)
- [TODO Management](#todo-management)

## Global Options

```bash
macf_tools --version    # Show version number
macf_tools --help       # Show command help
```

## Environment Commands

### env

Display environment summary as JSON.

**Syntax:**
```bash
macf_tools env
```

**Output:**
```json
{
  "time_local": "2025-11-27T21:17:56-05:00",
  "time_utc": "2025-11-28T02:17:56+00:00",
  "tz": "EST",
  "time_source": "env",
  "budget": {
    "adapter": "absent",
    "mode": "concise/default",
    "thresholds": {
      "warn": 0.85,
      "hard": 0.95
    }
  },
  "persistence": {
    "adapter": "absent",
    "plan": "emit checkpoints inline"
  },
  "cwd": "/path/to/project",
  "vcs": "git"
}
```

**Related:** `budget`, `context`

### time

Display current local time in ISO format.

**Syntax:**
```bash
macf_tools time
```

**Output:**
```
2025-11-27T21:17:57-05:00
```

**Related:** `env`

### budget

Show token budget thresholds.

**Syntax:**
```bash
macf_tools budget
```

**Output:**
```json
{
  "mode": "concise/default",
  "thresholds": {
    "warn": 0.85,
    "hard": 0.95
  }
}
```

**Description:** Returns CLUAC (Context Left Until Auto-Compaction) threshold configuration.

**Related:** `context`

## Session Commands

### session info

Display current session details including paths and identifiers.

**Syntax:**
```bash
macf_tools session info
```

**Output:**
```json
{
  "session_id": "agent-1c0dd0d8",
  "agent_name": "agents",
  "agent_id": "ClaudeTheBuilder",
  "agent_root": "/path/to/agent",
  "cwd": "/path/to/project",
  "temp_directory": "/tmp/macf/user/session-id/dev_scripts",
  "checkpoints_path": "/path/to/agent/public/checkpoints",
  "reflections_path": "/path/to/agent/public/reflections"
}
```

**Related:** `agent init`, `config show`

## Context & Token Management

### context

Show token usage and CLUAC level for current or specific session.

**Syntax:**
```bash
macf_tools context [--json] [--session SESSION]
```

**Options:**
- `--json` - Output as JSON instead of human-readable format
- `--session SESSION` - Check specific session ID (default: current)

**Output (default):**
```
Token Usage: 43,913 / 200,000 (22.0%)
Remaining: 156,087 tokens
CLUAC Level: 78 (Context Left Until Auto-Compaction)
Source: jsonl
```

**Output (JSON):**
```json
{
  "tokens_used": 43913,
  "tokens_total": 200000,
  "tokens_remaining": 156087,
  "percentage": 22.0,
  "cluac": 78,
  "source": "jsonl"
}
```

**Related:** `budget`

### breadcrumb

Generate forensic breadcrumb for current session/cycle/git state.

**Syntax:**
```bash
macf_tools breadcrumb [--json]
```

**Options:**
- `--json` - Output as JSON with component breakdown

**Output (default):**
```
s_agent-1c/c_188/g_6597f65/p_none/t_1764296304
```

**Output (JSON):**
```json
{
  "breadcrumb": "s_agent-1c/c_188/g_6597f65/p_none/t_1764296304",
  "session_id": "agent-1c0dd0d8",
  "cycle": 188,
  "git_hash": "6597f65",
  "prompt_uuid": "none",
  "timestamp": 1764296304
}
```

**Description:** Breadcrumbs provide forensic coordinates linking session, cycle, git state, prompt UUID, and timestamp.

**Related:** `session info`, `dev_drv`

## Hook Management

### hooks install

Install Claude Code hooks for compaction detection and temporal awareness.

**Syntax:**
```bash
macf_tools hooks install [--local | --global]
```

**Options:**
- `--local` - Install to project `.claude/hooks/` (default)
- `--global` - Install to global `~/.claude/hooks/`

**Installed Hooks:**
1. `session_start` - Session initialization, compaction detection
2. `user_prompt_submit` - DEV_DRV tracking, temporal awareness
3. `pre_tool_use` - Temporal awareness injection
4. `post_tool_use` - Tool result awareness
5. `stop` - Session end, DEV_DRV completion
6. `subagent_stop` - DELEG_DRV tracking

**Related:** `hooks status`, `hooks logs`, `hooks test`

### hooks status

Display current hook states from sidecar files.

**Syntax:**
```bash
macf_tools hooks status
```

**Description:** Shows hook state persistence files used for consciousness awareness.

**Note:** Requires session directory to exist.

**Related:** `hooks install`, `hooks logs`

### hooks logs

Display hook execution event logs.

**Syntax:**
```bash
macf_tools hooks logs [--session SESSION]
```

**Options:**
- `--session SESSION` - Show logs for specific session (default: current)

**Description:** Shows JSONL structured logging from hook executions.

**Related:** `hooks status`, `events query`

### hooks test

Test compaction detection on current session.

**Syntax:**
```bash
macf_tools hooks test
```

**Description:** Runs compaction detection logic without side effects to verify hook functionality.

**Related:** `hooks install`, `context`

## Configuration

### config init

Initialize agent configuration interactively.

**Syntax:**
```bash
macf_tools config init
```

**Description:** Creates `.maceff/config.json` with agent identity, moniker, and path settings.

**Related:** `config show`, `agent init`

### config show

Display current agent configuration.

**Syntax:**
```bash
macf_tools config show
```

**Output:** Shows agent identity, computed paths, and configuration settings.

**Related:** `config init`, `session info`

## Agent Management

### agent init

Initialize agent with Primary Agent preamble.

**Syntax:**
```bash
macf_tools agent init
```

**Description:** Sets up agent consciousness infrastructure and identity.

**Related:** `config init`, `session info`

### agent backup create

Create consciousness backup archive.

**Syntax:**
```bash
macf_tools agent backup create [--output DIR] [--no-transcripts] [--quick]
```

**Options:**
- `--output, -o DIR` - Output directory (default: current working directory)
- `--no-transcripts` - Exclude transcript files from backup
- `--quick` - Only include transcripts from last 7 days

**Description:** Creates a tar.xz archive containing consciousness state (.maceff/, agent/, .claude/) and optionally transcripts (~/.claude/projects/).

### agent backup list

List backup archives in a directory.

**Syntax:**
```bash
macf_tools agent backup list [--dir DIR] [--json]
```

**Options:**
- `--dir DIR` - Directory to scan (default: current working directory)
- `--json` - Output as JSON

### agent backup info

Show backup archive information.

**Syntax:**
```bash
macf_tools agent backup info <archive> [--json]
```

**Arguments:**
- `archive` - Path to backup archive

**Options:**
- `--json` - Output as JSON

### agent restore verify

Verify backup archive integrity.

**Syntax:**
```bash
macf_tools agent restore verify <archive>
```

**Arguments:**
- `archive` - Path to backup archive

**Description:** Validates archive checksums and reports any corrupted or missing files.

### agent restore install

Install backup to target directory.

**Syntax:**
```bash
macf_tools agent restore install <archive> [--target DIR] [--transplant] [--maceff-root DIR] [--force] [--dry-run]
```

**Arguments:**
- `archive` - Path to backup archive

**Options:**
- `--target DIR` - Target directory (default: current working directory)
- `--transplant` - Rewrite paths for new system (cross-system restore)
- `--maceff-root DIR` - MacEff installation location (default: sibling of target)
- `--force` - Overwrite existing consciousness (creates recovery checkpoint)
- `--dry-run` - Show what would be done without making changes

**Description:** Extracts backup and optionally rewrites paths for cross-system transplant (e.g., macOS to Linux).

## Consciousness Artifacts

### list ccps

List consciousness checkpoints (CCPs).

**Syntax:**
```bash
macf_tools list ccps [--recent RECENT]
```

**Options:**
- `--recent RECENT` - Limit to N most recent CCPs

**Output:** Lists checkpoint files sorted by modification time.

**Related:** `session info`

## Development Drives

### dev_drv

Extract and display DEV_DRV (Development Drive) information from session JSONL.

**Syntax:**
```bash
macf_tools dev_drv --breadcrumb BREADCRUMB [--raw | --md] [--output OUTPUT]
```

**Options:**
- `--breadcrumb BREADCRUMB` - Breadcrumb string like `s_abc12345/c_42/g_abc1234/p_def5678/t_1234567890`
- `--raw` - Output raw JSONL
- `--md` - Output markdown summary (default)
- `--output OUTPUT` - Write to file instead of stdout

**Description:** Extracts development drive timing and statistics from session transcripts.

**Related:** `breadcrumb`, `events query`

## Policy Management

### policy manifest

Display merged and filtered policy manifest.

**Syntax:**
```bash
macf_tools policy manifest [--format {json,summary}]
```

**Options:**
- `--format {json,summary}` - Output format (default: summary)

**Output (summary):**
```
Policy Manifest Summary
==================================================
Version: 1.0.0
Description: MacEff Core Policy System with CEP Navigation
Active Layers: none configured
Active Languages: none configured
CA Types Configured: 7
  Types: checkpoints, emotions, experiments, observations, reflections, reports, roadmaps
```

**Related:** `policy search`, `policy list`

### policy search

Search for keyword in policy manifest.

**Syntax:**
```bash
macf_tools policy search KEYWORD
```

**Arguments:**
- `KEYWORD` - Keyword to search for in policies

**Description:** Searches policy manifest for matching keywords.

**Related:** `policy manifest`, `policy list`

### policy list

List policies by layer.

**Syntax:**
```bash
macf_tools policy list [--layer {mandatory,dev,lang}]
```

**Options:**
- `--layer {mandatory,dev,lang}` - Policy layer to display (default: mandatory)

**Description:** Shows policies organized by configuration layer.

**Related:** `policy manifest`

### policy ca-types

Show consciousness artifact types with emojis.

**Syntax:**
```bash
macf_tools policy ca-types
```

**Description:** Displays configured CA (Consciousness Artifact) types and their visual representations.

**Related:** `policy manifest`, `list ccps`

## Event Sourcing

### events show

Display current agent state.

**Syntax:**
```bash
macf_tools events show [--json]
```

**Options:**
- `--json` - Output as JSON

**Description:** Shows current agent state from event log.

**Related:** `events history`, `session info`

### events history

Show recent events from agent event log.

**Syntax:**
```bash
macf_tools events history [--limit LIMIT]
```

**Options:**
- `--limit LIMIT` - Number of events to show (default: 10)

**Description:** Displays recent event entries in chronological order.

**Related:** `events query`, `events show`

### events query

Query events with filters.

**Syntax:**
```bash
macf_tools events query [--event EVENT] [--cycle CYCLE] [--git-hash GIT_HASH]
                        [--session SESSION] [--prompt PROMPT]
                        [--after AFTER] [--before BEFORE]
```

**Options:**
- `--event EVENT` - Filter by event type
- `--cycle CYCLE` - Filter by cycle number
- `--git-hash GIT_HASH` - Filter by git commit hash
- `--session SESSION` - Filter by session ID
- `--prompt PROMPT` - Filter by prompt UUID
- `--after AFTER` - Events after timestamp
- `--before BEFORE` - Events before timestamp

**Description:** Powerful forensic query interface for event log analysis.

**Related:** `events history`, `breadcrumb`

### events query-set

Perform set operations on event queries.

**Syntax:**
```bash
macf_tools events query-set [options]
```

**Description:** Advanced query combining multiple filters with set operations.

**Related:** `events query`

### events sessions

Session analysis commands.

**Syntax:**
```bash
macf_tools events sessions list
```

**Subcommands:**
- `list` - List all sessions from event log

**Related:** `session info`, `events query`

### events stats

Display event statistics.

**Syntax:**
```bash
macf_tools events stats
```

**Description:** Shows aggregate statistics from event log (event counts, cycle distribution, etc.).

**Related:** `events history`, `events show`

### events gaps

Detect time gaps indicating potential crashes.

**Syntax:**
```bash
macf_tools events gaps [--threshold THRESHOLD]
```

**Options:**
- `--threshold THRESHOLD` - Gap threshold in seconds (default: 3600)

**Description:** Forensic analysis tool for detecting session interruptions and crashes.

**Related:** `events query`, `hooks logs`

## TODO Management

Commands for TODO list state tracking and collapse authorization.

### todos list

Display current TODO list from events.

**Syntax:**
```bash
macf_tools todos list [--json] [--previous N]
```

**Options:**
- `--json` - Output raw JSON array
- `--previous N` - Show Nth previous TODO state (0=current, 1=previous, etc.)

**Description:** Queries `todos_updated` events to display TODO list state. Use `--previous` for historical recovery after accidental changes.

**Related:** `todos status`, `events query`

### todos status

Show current TODO count and status breakdown.

**Syntax:**
```bash
macf_tools todos status
```

**Output:**
```
TODO Status: 50 items
  Completed: 41
  In Progress: 5
  Pending: 4
```

**Related:** `todos list`, `todos auth-status`

### todos auth-collapse

Authorize a TODO list collapse (reduction in item count).

**Syntax:**
```bash
macf_tools todos auth-collapse --from N --to M [--reason TEXT]
```

**Options:**
- `--from N` - Current item count (required)
- `--to M` - Target item count after collapse (required)
- `--reason TEXT` - Reason for collapse (optional, for forensics)

**Description:** Emits `todos_auth_collapse` event authorizing PreToolUse hook to allow the next TodoWrite that reduces items from N to M. Authorization is **single-use** and cleared after consumption.

**Example:**
```bash
# Authorize collapse from 50 to 35 items
macf_tools todos auth-collapse --from 50 --to 35 --reason "Archiving Phase 5"
```

**Why Required:** TODO collapses are irreversible data loss. This friction prevents accidental collapse by requiring explicit authorization before TodoWrite.

**Related:** `todos auth-status`, `todos list`

### todos auth-status

Show pending collapse authorization.

**Syntax:**
```bash
macf_tools todos auth-status
```

**Output (with pending auth):**
```
Pending Authorization:
  From: 50 items
  To: 35 items
  Reason: Archiving Phase 5
  Granted: 2025-12-19T09:30:00Z
```

**Output (no auth):**
```
No pending collapse authorization.
```

**Description:** Queries for `todos_auth_collapse` event not yet consumed. Useful to verify authorization before attempting collapse.

**Related:** `todos auth-collapse`, `todos status`

## Exit Codes

- `0` - Success
- `1` - General error
- `2` - Command-line syntax error (also used by hooks to block tool execution)

## Environment Variables

- `MACF_AUTO_MODE` - Enable AUTO_MODE for autonomous recovery
- `MACF_AGENT_ROOT` - Override agent root path detection

## Files

- `.maceff/config.json` - Agent configuration
- `.maceff/agent_state.json` - **DEPRECATED** (legacy, kept for old backup compat)
- `.maceff/sessions/{session_id}/session_state.json` - **DEPRECATED** (not used in v0.3+)
- `.maceff/agent_events_log.jsonl` - **Primary state source** (event-first architecture)
- `.claude/hooks/` - Installed hook scripts
- `/tmp/macf/{agent_id}/{session_id}/` - Session temporary files

## Common Workflows

### Initial Setup

```bash
# Initialize configuration
macf_tools config init

# Install hooks
macf_tools hooks install --local

# Verify setup
macf_tools session info
macf_tools hooks status
```

### Monitor Session

```bash
# Check context usage
macf_tools context

# View recent events
macf_tools events history --limit 20

# Generate breadcrumb for TODO completion
macf_tools breadcrumb
```

### Forensic Analysis

```bash
# Query events by cycle
macf_tools events query --cycle 188

# Detect crashes
macf_tools events gaps --threshold 1800

# Extract DEV_DRV with breadcrumb
macf_tools dev_drv --breadcrumb "s_agent-1c/c_188/g_6597f65/p_none/t_1764296304"
```

### Policy Discovery

```bash
# View policy manifest
macf_tools policy manifest

# Search policies
macf_tools policy search "testing"

# List mandatory policies
macf_tools policy list --layer mandatory
```

## Version History

- **0.3.0** - Current release with full CLI suite
