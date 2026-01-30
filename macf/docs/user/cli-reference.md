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
- [Search Service](#search-service)
- [Event Sourcing](#event-sourcing)
- [Task Commands](#task-commands-v040)
  - [Task Creation Commands](#task-creation-commands)
  - [Task Lifecycle Commands](#task-lifecycle-commands)
  - [Task Metadata Commands](#task-metadata-commands)
  - [Task Archive Commands](#task-archive-commands)
  - [Task Protection Commands](#task-protection-commands)
  - [Task Completion](#task-completion)

## Global Options

```bash
macf_tools --version    # Show version number
macf_tools --help       # Show command help
```

## Environment Commands

### env

Display comprehensive environment and debugging information.

**Syntax:**
```bash
macf_tools env           # Pretty-printed output (default)
macf_tools env --json    # Machine-readable JSON output
```

**Output Categories:**

| Category | Information |
|----------|-------------|
| **Agent ID** | Persistent identity: `{DisplayName}@{uuid}` (e.g., `MannyMacEff@a3f7c2`) |
| **Versions** | MACF version, Claude Code version, Python interpreter path + version |
| **Time** | Current time (local + UTC), timezone name |
| **Paths** | Agent home, framework root, event log, hooks dir, policies dir |
| **Session** | Session ID, cycle number, git hash |
| **System** | Platform, OS version, CWD, hostname |
| **Environment** | BASH_ENV, CLAUDE_PROJECT_DIR, MACEFF_AGENT_HOME_DIR |
| **Config** | Hooks installed count, auto_mode status |

**Example Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent ID
  MannyMacEff@a3f7c2

Versions
  MACF:         0.3.3
  Claude Code:  2.1.2
  Python:       /usr/bin/python3 (3.10.12)

Time
  Local:        2026-01-08 04:50:00 PM EST
  UTC:          2026-01-08 21:50:00

Paths
  Agent Home:   /Users/user/project
  Framework:    /opt/maceff
  Event Log:    ~/.maceff/agent_events_log.jsonl

Session
  Session ID:   c7cfbf0e
  Cycle:        327
  Git Hash:     3654b42

System
  Platform:     darwin
  OS:           Darwin 24.5.0
  Hostname:     MacBook-Pro.local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Related:** `context`, `session info`

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

### policy navigate

Show CEP Navigation Guide for a policy.

**Syntax:**
```bash
macf_tools policy navigate POLICY_NAME
```

**Arguments:**
- `POLICY_NAME` - Name of the policy (without .md extension)

**Description:** Displays the CEP (Consciousness Expanding Protocol) Navigation Guide, showing semantic section structure with questions that guide policy discovery. Use this before `policy read` to understand policy organization.

**Example:**
```bash
macf_tools policy navigate todo_hygiene
```

**Related:** `policy read`, `policy list`

### policy read

Read a policy file with optional section filtering.

**Syntax:**
```bash
macf_tools policy read POLICY_NAME [--section N[.M[.P]]] [--from-nav-boundary]
```

**Arguments:**
- `POLICY_NAME` - Name of the policy (without .md extension)

**Options:**
- `--section N` - Read specific section and all subsections
- `--from-nav-boundary` - Start reading from after CEP Navigation Guide

**Section Hierarchical Matching:**
- `--section 10` matches sections 10, 10.1, 10.2, etc. (but NOT 11 or 100)
- `--section 10.1` matches 10.1, 10.1.1, 10.1.2, etc. (but NOT 10.2)
- Uses prefix matching with dot separator to prevent false matches

**Examples:**
```bash
# Read full policy
macf_tools policy read todo_hygiene

# Read section 10 and all subsections (10.1, 10.2, etc.)
macf_tools policy read todo_hygiene --section 10

# Read only subsection 10.1 and its children
macf_tools policy read todo_hygiene --section 10.1

# Read policy content after navigation guide
macf_tools policy read delegation_guidelines --from-nav-boundary
```

**Related:** `policy navigate`, `policy list`

### policy build_index

Build hybrid FTS5 + semantic search index from policy files.

**Syntax:**
```bash
macf_tools policy build_index [--policies-dir DIR] [--db-path PATH] [--json]
```

**Options:**
- `--policies-dir DIR` - Path to policies directory (default: auto-detected framework path)
- `--db-path PATH` - Path for output database (default: `~/.maceff/policy_index.lance/`)
- `--json` - Output as JSON instead of human-readable format

**Output (default):**
```
✅ Policy index built:
   Documents: 24
   Questions: 156
   Total time: 3.45s
   Database: /Users/user/.maceff/policy_index.lance/
```

**Dependencies:** Requires optional packages:
```bash
pip install lancedb sentence-transformers
```

**Related:** `policy recommend`, `search-service start`

### policy recommend

Get hybrid search policy recommendations using LanceDB's semantic + full-text search.

**Syntax:**
```bash
macf_tools policy recommend QUERY [--limit N] [--explain] [--json]
```

**Arguments:**
- `QUERY` - Natural language query (minimum 10 characters)

**Options:**
- `--limit N` - Maximum number of results (default: 5)
- `--explain` - Show verbose breakdown with retriever contributions
- `--json` - Output as JSON for machine processing

**Output (default):**
```
📚 Policy Recommendations:
🥇 📋 TODO_HYGIENE (1.327)
   → §10 "What is the TODO backup protocol?"
🥈 📋 CHECKPOINTS (1.503)
🥉 📋 CONTEXT_RECOVERY (1.576)
```

**Output (--explain):**
```
📚 Policy Recommendations for: "How do I backup TODOs?"
────────────────────────────────────────────────────────────────

🥇 TODO_HYGIENE
   RRF Score: 1.327
   Distance: 0.423
   Matched Questions:
     → §10 "What is the TODO backup protocol?"
     → §10.1 "How do I query TODO history via CLI?"
```

**Performance:**
- With search service running: ~20ms response time
- Without service (fallback): ~8s (model loading overhead)

**Tip:** Start the search service for fast responses:
```bash
macf_tools search-service start --daemon
```

**Dependencies:** Requires optional packages:
```bash
pip install lancedb sentence-transformers
```

**Related:** `policy build_index`, `search-service start`

### policy ca-types

Show consciousness artifact types with emojis.

**Syntax:**
```bash
macf_tools policy ca-types
```

**Description:** Displays configured CA (Consciousness Artifact) types and their visual representations.

**Related:** `policy manifest`, `list ccps`

## Search Service

Commands for managing the persistent search service daemon that provides fast (~20ms) policy recommendations.

### search-service start

Start the search service daemon.

**Syntax:**
```bash
macf_tools search-service start [--port PORT] [--daemon]
```

**Options:**
- `--port PORT` - Port to listen on (default: 9001)
- `--daemon` - Run in background (detached from terminal)

**Description:** Starts a persistent socket service that keeps the embedding model loaded in memory. This eliminates the ~8s model loading overhead on each query.

**Example:**
```bash
# Start in foreground (for debugging)
macf_tools search-service start

# Start as background daemon (recommended)
macf_tools search-service start --daemon
```

**Dependencies:** Requires optional packages:
```bash
pip install lancedb sentence-transformers
```

**Related:** `search-service stop`, `search-service status`, `policy recommend`

### search-service stop

Stop the running search service.

**Syntax:**
```bash
macf_tools search-service stop
```

**Description:** Gracefully stops the search service daemon if running.

**Output:**
```
✅ Search service stopped
```

**Related:** `search-service start`, `search-service status`

### search-service status

Show search service status.

**Syntax:**
```bash
macf_tools search-service status [--json]
```

**Options:**
- `--json` - Output as JSON

**Output (running):**
```
✅ Search service is running
   PID: 12345
   Port: 9001
```

**Output (not running):**
```
⚠️  Search service is not running
   Start with: macf_tools search-service start
```

**Related:** `search-service start`, `search-service stop`

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

---

## Task Commands (v0.4.0+)

Task commands provide CLI access to Claude Code's native Task* tools with MTMD (MacfTaskMetaData) enhancement.

**Policy Reference:** See `task_management.md` for comprehensive task lifecycle, hierarchy rules, and MTMD schema documentation.

```bash
macf_tools policy navigate task_management  # CEP navigation guide
macf_tools policy read task_management      # Full policy
```

---

### Task Creation Commands

#### task create mission

Create a MISSION task with associated roadmap. MISSIONs are strategic multi-phase work items.

**Syntax:**
```bash
macf_tools task create mission <title> [--repo REPO] [--version VERSION] [--json]
```

**Arguments:**
- `title` - Mission title (becomes task subject with 🗺️ prefix)

**Options:**
- `--repo REPO` - Repository name (e.g., MacEff)
- `--version VERSION` - Target version (e.g., 0.4.0)
- `--json` - Output as JSON

**Smart Defaults:**
- Creates `plan_ca_ref` pointing to `agent/public/roadmaps/{date}_{title}/roadmap.md`
- Sets `task_type: MISSION` in MTMD
- Prompts for roadmap creation workflow

**Example:**
```bash
macf_tools task create mission "v0.5.0 Feature Release" --repo MacEff --version 0.5.0
```

#### task create experiment

Create an EXPERIMENT task with associated protocol. Experiments are hypothesis-driven explorations.

**Syntax:**
```bash
macf_tools task create experiment <title> [--json]
```

**Arguments:**
- `title` - Experiment title (becomes task subject with 🧪 prefix)

**Options:**
- `--json` - Output as JSON

**Smart Defaults:**
- Creates `plan_ca_ref` pointing to `agent/public/experiments/{date}_{title}/protocol.md`
- Sets `task_type: EXPERIMENT` in MTMD

**Example:**
```bash
macf_tools task create experiment "LanceDB Hybrid Search Performance"
```

#### task create detour

Create a DETOUR task for unplanned but necessary work branching from current mission.

**Syntax:**
```bash
macf_tools task create detour <title> [--repo REPO] [--version VERSION] [--json]
```

**Arguments:**
- `title` - Detour title (becomes task subject with 🔀 prefix)

**Options:**
- `--repo REPO` - Repository name
- `--version VERSION` - Target version
- `--json` - Output as JSON

**Smart Defaults:**
- Creates `plan_ca_ref` pointing to `agent/public/roadmaps/{date}_{title}/roadmap.md`
- Sets `task_type: DETOUR` in MTMD

**Example:**
```bash
macf_tools task create detour "Urgent Security Fix" --repo MacEff --version 0.4.1
```

#### task create phase

Create a PHASE task as a child of a parent MISSION/EXPERIMENT/DETOUR.

**Syntax:**
```bash
macf_tools task create phase <title> --parent <PARENT_ID> [--json]
```

**Arguments:**
- `title` - Phase title

**Required Options:**
- `--parent PARENT_ID` - Parent task ID (e.g., #67 or 67)

**Options:**
- `--json` - Output as JSON

**Smart Defaults:**
- Sets `task_type: PHASE` in MTMD
- Sets `parent_id` linking to parent task
- Adds `[^#N]` prefix to subject for hierarchy display

**Example:**
```bash
macf_tools task create phase "Phase 1: Core Implementation" --parent #26
macf_tools task create phase "Phase 2: Testing" --parent 26
```

#### task create bug

Create a BUG task for defect tracking. Can be standalone or linked to a parent.

**Syntax:**
```bash
macf_tools task create bug <title> [--parent PARENT] (--plan PLAN | --plan-ca-ref PATH) [--json]
```

**Arguments:**
- `title` - Bug title (becomes task subject with 🐛 prefix)

**Options:**
- `--parent PARENT` - Optional parent task ID
- `--plan PLAN` - Inline plan description (for simple bugs)
- `--plan-ca-ref PATH` - Path to BUG_FIX roadmap CA (for complex bugs)
- `--json` - Output as JSON

**Mutually Exclusive:** Must provide either `--plan` or `--plan-ca-ref`

**Examples:**
```bash
# Simple bug with inline plan
macf_tools task create bug "Fix null pointer in parser" --plan "Check for null before accessing"

# Complex bug with roadmap
macf_tools task create bug "Memory leak in session handler" --plan-ca-ref agent/public/roadmaps/2026-01-29_Memory_Leak/roadmap.md

# Bug under a mission
macf_tools task create bug "Test flakiness" --parent #26 --plan "Add retry logic"
```

#### task create deleg

Create a DELEG_PLAN task for delegating work to subagents.

**Syntax:**
```bash
macf_tools task create deleg <title> [--parent PARENT] (--plan PLAN | --plan-ca-ref PATH) [--json]
```

**Arguments:**
- `title` - Delegation title (becomes task subject with 📜 prefix)

**Options:**
- `--parent PARENT` - Optional parent task ID
- `--plan PLAN` - Inline delegation plan (for simple delegations)
- `--plan-ca-ref PATH` - Path to DELEG_PLAN CA (for complex delegations)
- `--json` - Output as JSON

**Mutually Exclusive:** Must provide either `--plan` or `--plan-ca-ref`

**Examples:**
```bash
# Simple delegation with inline plan
macf_tools task create deleg "Write unit tests for parser" --plan "TestEng: Cover edge cases"

# Complex delegation with CA
macf_tools task create deleg "Refactor CLI architecture" --plan-ca-ref agent/public/roadmaps/2026-01-29_CLI_Refactor/deleg_plan.md
```

#### task create task

Create a standalone TASK (🔧) for ad-hoc work items without strategic planning overhead.

**Syntax:**
```bash
macf_tools task create task <title> [--json]
```

**Arguments:**
- `title` - Task title (becomes subject with 🔧 prefix)

**Options:**
- `--json` - Output as JSON

**Example:**
```bash
macf_tools task create task "Update README badges"
```

---

### Task Lifecycle Commands

#### task list

List tasks with hierarchy and metadata.

**Syntax:**
```bash
macf_tools task list [--type TYPE] [--all-sessions]
```

**Options:**
- `--type TYPE` - Filter by type (MISSION, EXPERIMENT, DETOUR, PHASE, BUG, AD_HOC)
- `--all-sessions` - Include tasks from historical sessions

**Output:**
```
📋 Tasks (current session)
============================================================
◼ #67 🗺️ MISSION: MACF Task CLI & Policy Migration
   → agent/public/roadmaps/2026-01-23_MACF_Task_CLI/roadmap.md
✔ #68 [^#67] 📋 Phase 1: Core CLI Commands
◻ #81 [^#67] 📋 Phase 2: Metadata Management
```

### task get

Display full task details including MTMD.

**Syntax:**
```bash
macf_tools task get <task_id>
```

**Example:**
```bash
macf_tools task get 67
macf_tools task get #67  # Leading # is optional
```

### task tree

Display task hierarchy as tree.

**Syntax:**
```bash
macf_tools task tree [task_id]
```

**Arguments:**
- `task_id` - Root task ID (default: `000` sentinel, shows all tasks)

**Output:**
```
🌳 Task Tree from #67 (19 tasks)
├── ✔ #68 [^#67] 📋 Phase 1: Core CLI Commands
│   ├── ✔ #69 [^#68] 1.1: Create package structure
│   └── ✔ #70 [^#68] 1.2: Implement task list
├── ◻ #81 [^#67] 📋 Phase 2: Metadata Management
```

### task delete

Delete a task file (requires grant in MANUAL_MODE).

**Syntax:**
```bash
macf_tools task delete <task_id> [--cascade] [--force]
```

**Options:**
- `--cascade` - Also delete child tasks
- `--force` - Skip confirmation prompt

**Protection Level:** HIGH (requires user grant)

### task edit

Edit a top-level task field (subject, status, description).

**Syntax:**
```bash
macf_tools task edit <task_id> <field> <value>
```

**Example:**
```bash
macf_tools task edit 67 status completed
macf_tools task edit 67 subject "New title"
```

### task metadata get

Display pure MTMD for a task.

**Syntax:**
```bash
macf_tools task metadata get <task_id>
```

**Output:**
```
📦 MacfTaskMetaData (v1.0) for #81
----------------------------------------
  creation_breadcrumb: s_77270981/c_374/g_a948f8b/...
  created_cycle: 374
  created_by: PA
  parent_id: 67
  repo: MacEff
  target_version: 0.4.0
```

### task metadata set

Set an MTMD field value.

**Syntax:**
```bash
macf_tools task metadata set <task_id> <field> <value>
```

**Example:**
```bash
macf_tools task metadata set 81 repo MacEff
macf_tools task metadata set 81 target_version 0.4.0
macf_tools task metadata set 81 parent_id 67
```

**Valid Fields:** `plan_ca_ref`, `parent_id`, `repo`, `target_version`, `release_branch`, `completion_breadcrumb`, `unblock_breadcrumb`, `archived`, `archived_at`, `creation_breadcrumb`, `created_cycle`, `created_by`, `experiment_ca_ref`

### task metadata add

Add a custom field to MTMD's custom section.

**Syntax:**
```bash
macf_tools task metadata add <task_id> <key> <value>
```

**Example:**
```bash
macf_tools task metadata add 67 priority high
macf_tools task metadata add 67 reviewer cversek
```

### task metadata validate

Validate MTMD against schema requirements.

**Syntax:**
```bash
macf_tools task metadata validate <task_id>
```

**Output (success):**
```
🔍 Validating task #81: [^#67] 📋 Phase 2...

   Type: PHASE

✅ VALIDATION PASSED
```

**Output (failure):**
```
🔍 Validating task #67: 🗺️ MISSION...

   Type: MISSION

❌ VALIDATION FAILED

   ❌ MISSION requires plan_ca_ref (roadmap/protocol path)
```

**Validation Rules:**
- ALL tasks: `creation_breadcrumb` required
- MISSION/EXPERIMENT/DETOUR: `plan_ca_ref` required
- PHASE tasks: `parent_id` required
- Subject `[^#N]` must match MTMD `parent_id`

---

### Task Archive Commands

#### task archive

Archive a task (and optionally its children) to disk. Archived tasks are moved out of the active session.

**Syntax:**
```bash
macf_tools task archive <task_id> [--no-cascade] [--json]
```

**Arguments:**
- `task_id` - Task ID to archive (e.g., #67 or 67)

**Options:**
- `--no-cascade` - Archive only this task, not children (default: cascade enabled)
- `--json` - Output as JSON

**Behavior:**
- Default cascades to archive all child tasks
- Writes archive files to `agent/public/task_archives/`
- Archive filename: `{date}_task_{id}_{sanitized_subject}.json`

**Example:**
```bash
# Archive mission and all phases
macf_tools task archive #26

# Archive single task only
macf_tools task archive #67 --no-cascade
```

#### task restore

Restore a previously archived task.

**Syntax:**
```bash
macf_tools task restore <archive_path_or_id> [--json]
```

**Arguments:**
- `archive_path_or_id` - Archive file path OR original task ID

**Options:**
- `--json` - Output as JSON

**Examples:**
```bash
# Restore by archive file path
macf_tools task restore agent/public/task_archives/2026-01-29_task_67_Mission.json

# Restore by original task ID (searches archive directory)
macf_tools task restore 67
```

#### task archived list

List all archived tasks.

**Syntax:**
```bash
macf_tools task archived list
```

**Output:**
```
📦 Archived Tasks
============================================================
  2026-01-29_task_5_Extend_grant-delete.json (#5)
  2026-01-29_task_6_BUG_Hook_messages.json (#6)
  ...
```

---

### Task Protection Commands

Tasks use a grant-based protection system. Destructive operations require explicit user grants.

#### task grant-update

Grant permission to update a task's description/MTMD fields.

**Syntax:**
```bash
macf_tools task grant-update <task_id> [--field FIELD] [--value VALUE] [--reason REASON]
```

**Arguments:**
- `task_id` - Task ID to grant update permission (e.g., #67 or 67)

**Options:**
- `--field, -f FIELD` - Specific MTMD field to grant modification for
- `--value, -v VALUE` - Expected new value (requires --field)
- `--reason, -r REASON` - Reason for granting (documentation)

**Examples:**
```bash
# Grant general update permission
macf_tools task grant-update #67 --reason "Updating completion report"

# Grant specific field modification
macf_tools task grant-update #67 --field plan_ca_ref --value "agent/public/roadmaps/new.md"
```

#### task grant-delete

Grant permission to delete one or more tasks. Accepts multiple task IDs for batch operations.

**Syntax:**
```bash
macf_tools task grant-delete <task_ids>... [--reason REASON]
```

**Arguments:**
- `task_ids` - One or more task IDs (e.g., #67 68 #69)

**Options:**
- `--reason, -r REASON` - Reason for granting (documentation)

**Protection:** Uses exact set-matching - grant covers precisely the specified tasks, no more.

**Examples:**
```bash
# Grant delete for single task
macf_tools task grant-delete #67 --reason "Obsolete task"

# Grant delete for multiple tasks (set-matching)
macf_tools task grant-delete #36 #37 #38 #39 --reason "Test cleanup"
macf_tools task grant-delete 36 37 38 39 --reason "Test cleanup"
```

---

### Task Completion

#### task complete

Mark a task as completed with a mandatory completion report.

**Syntax:**
```bash
macf_tools task complete <task_id> --report <REPORT>
```

**Arguments:**
- `task_id` - Task ID to complete (e.g., #67 or 67)

**Required Options:**
- `--report, -r REPORT` - Completion report documenting work done

**What It Does:**
1. Generates `completion_breadcrumb` automatically
2. Sets `completion_report` in MTMD from `--report` flag
3. Updates task status to `completed`
4. Appends update entry to MTMD audit trail

**Completion Report Format:**

The `--report` should include:
- **Work done**: What was accomplished
- **Difficulties**: Any blockers (or "No difficulties")
- **Future work**: Identified follow-up (or "None")
- **Git status**: Commit hash or "pending"

**Examples:**
```bash
macf_tools task complete #67 --report "Implemented task complete command. No difficulties. Committed: 97a11d3"

macf_tools task complete #28 --report "Fixed test isolation. Difficulty: subprocess env inheritance. Future: Document pattern. Committed: 4cd30ce"

macf_tools task complete #81 -r "Research complete. Difficulties: sparse docs. Future: Phase 2 implementation. Committed: pending"
```

**Related:** See `task_management.md` §6 for complete completion protocol.

---

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

- **0.4.0** - Task System with MTMD, grant-based protection, archive/restore
- **0.3.0** - Initial release with full CLI suite
