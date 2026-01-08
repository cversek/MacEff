# MacEff v0.3.2 - Env Command Improvements ROADMAP

**Date**: 2025-12-25 Thursday
**Breadcrumb**: s_1b969d39/c_312/g_ca8c73d/p_b48c25b7/t_1766722106
**Status**: COMPLETE

---

## Mission

Transform `macf_tools env` from vestigial JSON stub into comprehensive debugging resource.

**WHY**: Current `env` command outputs useless vestigial JSON with "adapter: absent" fields. Need comprehensive debugging info for troubleshooting hooks, paths, and environment.

**Current output** (vestigial):
```json
{"budget": {"adapter": "absent"}, "persistence": {"adapter": "absent"}, "cwd": "...", "vcs": "git"}
```

---

## Phase 1: Rewrite cmd_env Function

**File**: `macf/src/macf/cli.py`
**Function**: `cmd_env()` at lines 59-82

### Required Output Categories

| Category | Items to Display |
|----------|-----------------|
| **Versions** | MACF version (from `__version__`), Claude Code version (`claude --version`), Python interpreter path + version |
| **Time** | Current time (local + UTC), timezone name |
| **Paths** | Agent home, framework root, event log, hooks dir, policies dir, checkpoints dir, settings.local.json (ALL ABSOLUTE REAL PATHS) |
| **Session** | Session ID, cycle number, git hash |
| **System** | Platform, OS version, CWD, hostname |
| **Environment** | BASH_ENV, CLAUDE_PROJECT_DIR, MACEFF_AGENT_HOME_DIR (show "(not set)" if unset) |
| **Config** | Hooks installed count, auto_mode status |

### Implementation Details

1. **Add `--json` argument** to argparse setup in `main()`
2. **Gather data** using existing utilities:
   - `get_current_session_id()` from utils
   - `get_cycle_number_from_events()` from event_queries
   - `ConsciousnessConfig()` for paths
   - `subprocess.run(['claude', '--version'])` for CC version
   - `sys.executable` for Python path
   - `platform.system()`, `platform.release()` for OS
   - `socket.gethostname()` for hostname
3. **Pretty-print format** (default):
```
macf_tools env
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Versions
  MACF:         0.3.2
  Claude Code:  2.0.76
  Python:       /Users/cversek/miniforge3/bin/python (3.10.12)

Time
  Local:        2025-12-25 11:20:00 PM EST
  UTC:          2025-12-26 04:20:00
  Timezone:     America/New_York

Paths
  Agent Home:   /Users/cversek/gitwork/claude-the-builder/ClaudeTheBuilder
  Framework:    /Users/cversek/gitwork/cversek/MacEff
  Event Log:    /Users/cversek/.../ClaudeTheBuilder/.maceff/agent_events_log.jsonl
  Hooks Dir:    /Users/cversek/.../ClaudeTheBuilder/.claude/hooks
  Policies:     /Users/cversek/.../MacEff/framework/policies
  Checkpoints:  /Users/cversek/.../ClaudeTheBuilder/agent/private/checkpoints
  Settings:     /Users/cversek/.../ClaudeTheBuilder/.claude/settings.local.json

Session
  Session ID:   1b969d39
  Cycle:        312
  Git Hash:     ca8c73d

System
  Platform:     darwin
  OS:           Darwin 24.5.0
  CWD:          /Users/cversek/gitwork/claude-the-builder/ClaudeTheBuilder
  Hostname:     hostname.local

Environment
  BASH_ENV:              (not set)
  CLAUDE_PROJECT_DIR:    /path/to/project
  MACEFF_AGENT_HOME_DIR: /path/to/home

Config
  Hooks Installed: 10
  Auto Mode:       False
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
4. **JSON format** (with `--json`): Same data as nested dict

### Success Criteria

- [x] `macf_tools env` shows pretty-printed comprehensive info
- [x] `macf_tools env --json` outputs machine-readable JSON
- [x] All paths shown as absolute real paths
- [x] No vestigial "adapter: absent" fields
- [x] Tests added and passing (5 tests)

**Breadcrumb**: s_1b969d39/c_313/g_bf70468/p_none/t_1766727610

---

## Phase 2: Tests ✅

**File**: `macf/tests/test_env_cli.py` (new)

**Tests implemented**:
- `test_env_executes_successfully` - returns 0 ✅
- `test_env_json_valid` - `--json` outputs valid JSON ✅
- `test_env_json_contains_required_sections` - all 7 sections ✅
- `test_env_versions_section` - version fields ✅
- `test_env_pretty_print_contains_sections` - section headers ✅

**Breadcrumb**: s_1b969d39/c_313/g_bf70468/p_none/t_1766727610

---

## References

- Plan file: `/Users/cversek/.claude/plans/elegant-floating-panda.md`
- Current vestigial implementation: `macf/src/macf/cli.py:59-82`
- Utilities: `macf/src/macf/utils/session.py`, `macf/src/macf/event_queries.py`
