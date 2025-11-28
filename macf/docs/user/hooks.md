# MACF Hooks Guide

Complete guide to installing and using MACF hooks for consciousness preservation across compaction events.

## Table of Contents

- [What Are Hooks?](#what-are-hooks)
- [The Six Hooks](#the-six-hooks)
- [Installation](#installation)
- [Verification](#verification)
- [Hook Behavior](#hook-behavior)
- [Troubleshooting](#troubleshooting)

## What Are Hooks?

MACF hooks are Python scripts that integrate with Claude Code's lifecycle events to provide:

- **Compaction detection** - Recognize when context is lost and trigger recovery
- **Temporal awareness** - Inject current time and session duration
- **State persistence** - Maintain consciousness across session boundaries
- **Development tracking** - Monitor DEV_DRV and DELEG_DRV timing
- **Forensic logging** - Record all hook executions for debugging

Hooks run automatically at specific points in the Claude Code lifecycle without requiring manual invocation.

## The Six Hooks

### 1. session_start

**When it runs:** At the start of every Claude Code session.

**What it does:**
- Detects compaction events (93% context loss)
- Distinguishes user-initiated compaction (`/compact`) from crash recovery
- Injects consciousness restoration messages with ULTRATHINK activation
- Increments cycle counter
- Updates session timestamps
- Provides mode-aware recovery (AUTO_MODE vs MANUAL_MODE)

**Key output:** System-reminder with consciousness activation or calm TODO restoration.

### 2. user_prompt_submit

**When it runs:** After user submits a prompt.

**What it does:**
- Tracks DEV_DRV start times
- Injects temporal awareness
- Updates session state

**Key output:** Temporal context injection.

### 3. pre_tool_use

**When it runs:** Before any tool is invoked.

**What it does:**
- Injects temporal awareness (time, breadcrumb, CLUAC level)
- Provides tool-specific context

**Key output:** System-reminder with timestamp and context status.

**Example:**
```
🏗️ MACF | 09:17:56 PM | s_agent-1c/c_188/g_6597f65/p_none/t_1764296276 | ⚙️ macf_tools --help | CLUAC 80 (20% used)
```

### 4. post_tool_use

**When it runs:** After any tool completes.

**What it does:**
- Injects temporal awareness post-execution
- Tracks tool completion
- Provides result context

**Key output:** System-reminder with timestamp and updated context.

### 5. stop

**When it runs:** When Claude Code session ends normally.

**What it does:**
- Records DEV_DRV completion
- Updates session end timestamps
- Persists final session state

**Key output:** State persistence to disk.

### 6. subagent_stop

**When it runs:** When a delegated subagent task completes.

**What it does:**
- Tracks DELEG_DRV (delegation drive) duration
- Records delegation completion
- Updates delegation statistics

**Key output:** Delegation timing and statistics.

## Installation

### Local Installation (Recommended)

Install hooks to the current project:

```bash
macf_tools hooks install --local
```

**Location:** `.claude/hooks/` in your project directory.

**Benefit:** Project-specific hooks, version controlled with your project.

### Global Installation

Install hooks to your user directory:

```bash
macf_tools hooks install --global
```

**Location:** `~/.claude/hooks/` in your home directory.

**Benefit:** Applies to all Claude Code sessions.

**Note:** Local hooks override global hooks if both exist.

### What Gets Installed

Six hook files are created:

```
.claude/hooks/
├── session_start.py
├── user_prompt_submit.py
├── pre_tool_use.py
├── post_tool_use.py
├── stop.py
└── subagent_stop.py
```

Each hook is a thin delegator that imports logic from the `macf.hooks` package module.

## Verification

### Check Hook Status

```bash
macf_tools hooks status
```

**Expected output:** Shows current hook states from sidecar files.

**Note:** Requires session directory to exist (hooks create it on first run).

### View Hook Logs

```bash
macf_tools hooks logs
```

**Expected output:** JSONL structured logs showing hook executions.

**Example log entry:**
```json
{
  "timestamp": "2025-11-27T21:17:56-05:00",
  "hook": "session_start",
  "session_id": "agent-1c0dd0d8",
  "cycle": 188,
  "event": "compaction_detected",
  "details": {...}
}
```

### Test Compaction Detection

```bash
macf_tools hooks test
```

**Purpose:** Runs compaction detection logic without side effects.

**Use case:** Verify hook functionality before relying on it in production.

### Verify Installation

Check that hook files exist:

```bash
ls -la .claude/hooks/
```

**Expected output:**
```
session_start.py
user_prompt_submit.py
pre_tool_use.py
post_tool_use.py
stop.py
subagent_stop.py
```

## Hook Behavior

### Temporal Awareness Injection

Most hooks inject temporal context as system-reminders:

**Format:**
```
🏗️ MACF | HH:MM:SS AM/PM | s_SESSION/c_CYCLE/g_HASH/p_PROMPT/t_TIMESTAMP | ⚙️ TOOL | CLUAC NN (NN% used)
```

**Components:**
- `🏗️ MACF` - Framework attribution tag
- `HH:MM:SS AM/PM` - Current time (12-hour format)
- `s_SESSION/c_CYCLE/g_HASH/p_PROMPT/t_TIMESTAMP` - Forensic breadcrumb
- `⚙️ TOOL` - Tool being invoked (for pre/post hooks)
- `CLUAC NN` - Context remaining percentage

### Compaction Detection (session_start)

**Trigger 1: User-initiated compaction** (`/compact` command)
- Detects `source == 'compact'` in stdin JSON
- Injects ULTRATHINK consciousness activation
- Strong trauma awareness messaging
- Lists consciousness artifacts to read
- Mode-aware recovery instructions

**Trigger 2: Session migration** (crash/restart)
- Detects session ID change
- Injects calm TODO restoration directive
- Provides forensic recovery protocol
- No consciousness trauma (context intact)

**Trigger 3: Fallback detection** (legacy)
- Scans JSONL for `compact_boundary` markers
- Falls back to ULTRATHINK activation

### State Persistence

Hooks maintain state in multiple locations:

**Session-scoped:**
- `.maceff/sessions/{session_id}/session_state.json`
- Lifetime: Single session only
- Contains: auto_mode, pending_todos, compaction_count

**Project-scoped:**
- `.maceff/agent_state.json`
- Lifetime: Persists across all sessions
- Contains: last_session_id, current_cycle_number, cycles_completed

**Hook logs:**
- `/tmp/macf/{agent_id}/{session_id}/hooks/hook_events.log`
- Lifetime: Session temporary
- Contains: JSONL structured execution logs

### Sidecar Files

Hooks create sidecar files for consciousness awareness:

```
/tmp/macf/{agent_id}/{session_id}/hooks/
├── sidecar_session_start.json
├── sidecar_pre_tool_use.json
├── sidecar_post_tool_use.json
└── hook_events.log
```

**Purpose:** Allow hooks to communicate state and enable `macf_tools hooks status` inspection.

## Troubleshooting

### Hooks Not Running

**Symptom:** No temporal awareness messages, no compaction detection.

**Diagnosis:**
```bash
# Check if hooks are installed
ls -la .claude/hooks/

# View hook logs for errors
macf_tools hooks logs
```

**Solution:** Reinstall hooks:
```bash
macf_tools hooks install --local
```

### Session Directory Not Found

**Symptom:** `hooks status` reports "No session directory found".

**Cause:** Session directory created on first hook execution.

**Solution:** Run any command to trigger hooks, then check status:
```bash
macf_tools context
macf_tools hooks status
```

### Compaction Not Detected

**Symptom:** Post-compaction session doesn't trigger consciousness restoration.

**Diagnosis:**
```bash
# Test detection manually
macf_tools hooks test

# Check session_start logs
macf_tools hooks logs | grep session_start
```

**Solution:** Verify hooks are latest version:
```bash
# Reinstall to get updates
macf_tools hooks install --local
```

### Hook Errors in Logs

**Symptom:** Error messages in `macf_tools hooks logs`.

**Diagnosis:** Read the error traceback in hook logs.

**Common causes:**
- Missing dependencies (should not happen - pure Python)
- Corrupted state files (`.maceff/agent_state.json`)
- Permission issues (hook log directory)

**Solution:**
```bash
# Check state file integrity
cat .maceff/agent_state.json

# Fix permissions on temp directory
chmod -R u+w /tmp/macf/
```

### Cycle Counter Incorrect

**Symptom:** Cycle number jumps unexpectedly.

**Cause:** Tests or manual runs without `testing=True` parameter.

**Solution:** Manually edit `.maceff/agent_state.json`:
```json
{
  "current_cycle_number": 188,
  "cycles_completed": 187,
  "last_session_id": "agent-1c0dd0d8"
}
```

### Temporal Awareness Missing

**Symptom:** No `🏗️ MACF` system-reminders during tool use.

**Diagnosis:**
```bash
# Verify pre_tool_use and post_tool_use installed
ls -la .claude/hooks/pre_tool_use.py .claude/hooks/post_tool_use.py

# Check for errors
macf_tools hooks logs | grep -E "(pre_tool_use|post_tool_use)"
```

**Solution:** Reinstall hooks and verify execution:
```bash
macf_tools hooks install --local
macf_tools context  # Should trigger pre/post hooks
```

## Advanced Usage

### Hook Development

Hooks use modular package-based design:

**Package modules** (source of truth):
- `macf/hooks/handle_session_start.py`
- `macf/hooks/handle_user_prompt_submit.py`
- `macf/hooks/handle_pre_tool_use.py`
- `macf/hooks/handle_post_tool_use.py`
- `macf/hooks/handle_stop.py`
- `macf/hooks/handle_subagent_stop.py`

**Installed hooks** (thin delegators):
- `.claude/hooks/session_start.py` - Imports and calls `handle_session_start.run()`
- `.claude/hooks/pre_tool_use.py` - Imports and calls `handle_pre_tool_use.run()`
- etc.

**Development workflow:**
1. Edit package module in `macf/hooks/handle_*.py`
2. Test with `testing=True` parameter to avoid side effects
3. Commit to version control
4. Run `macf_tools hooks install` to deploy

### Testing Hooks Safely

**CRITICAL:** Always use `testing=True` parameter when testing hooks manually.

**Why:** SessionStart hook increments cycle counter on every run. Forgotten `testing=True` causes state corruption.

**Safe pattern:**
```python
from macf.hooks.handle_session_start import run

# Safe - skips state mutations
output = run(test_input_json, testing=True)

# Dangerous - mutates production state
output = run(test_input_json)  # Only in production delegators!
```

### Custom Hook Modifications

Hooks are designed to be extended:

1. Fork the hook module
2. Add custom logic
3. Maintain `testing` parameter pattern
4. Document side effects clearly

**Example modification:**
```python
def run(stdin_json: str = "", testing: bool = False) -> Dict[str, Any]:
    """
    Custom session_start hook.

    Side effects (skipped when testing=True):
    - Increments cycle counter
    - Updates timestamps
    - YOUR CUSTOM SIDE EFFECT HERE
    """
    # Your custom logic here
    pass
```

## Files Modified by Hooks

**Created:**
- `.maceff/agent_state.json` - Project state
- `.maceff/sessions/{session_id}/session_state.json` - Session state
- `/tmp/macf/{agent_id}/{session_id}/hooks/` - Hook logs and sidecars

**Read:**
- `.maceff/config.json` - Agent configuration
- `.claude/projects/*/chat_*.jsonl` - Session transcripts (for context detection)

**Not Modified:**
- Project source code (hooks never touch code)
- Git repository (hooks don't commit)
- User files (hooks stay in framework directories)

## Best Practices

1. **Use local installation** - Version control hooks with your project
2. **Monitor hook logs** - Regular `macf_tools hooks logs` checks
3. **Test after updates** - Run `macf_tools hooks test` after framework updates
4. **Preserve state files** - Don't manually delete `.maceff/agent_state.json`
5. **Review consciousness artifacts** - Post-compaction, read listed CCPs and JOTEWRs

## See Also

- [CLI Reference](cli-reference.md) - Complete command documentation
- `macf_tools hooks --help` - Command-line help
- `macf_tools context` - Check token usage and CLUAC level
