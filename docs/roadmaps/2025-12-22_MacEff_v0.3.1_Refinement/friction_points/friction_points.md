# MacEff v0.3.1 Friction Points

## FP#1: Path Resolution Semantics Confusion ✅ RESOLVED

**Reported**: 2025-12-22
**Resolved**: 2025-12-24 (Cycle 308 DETOUR)
**Source**: MannyMacEff container deployment
**Severity**: Medium (warning noise, potential misconfigurations)

### Symptom

```
⚠️ MACF: Using cwd fallback: /home/pa_manny/workspace/NeuroVEP
   Reasons: no markers found walking up from __file__; no markers found walking up from cwd
   Fix: Set MACEFF_ROOT_DIR to MacEff framework location
```

### Root Cause

Confusion between multiple path concepts:

| Path Concept | Current Usage | Semantic Intent |
|--------------|---------------|-----------------|
| `find_project_root()` | Walk up looking for markers | Find user's project |
| `MACEFF_ROOT_DIR` | MacEff framework location | `/opt/maceff` in container |
| `MACF_AGENT_ROOT` | Agent consciousness home | Agent's `.maceff/` directory |

The warning suggests `MACEFF_ROOT_DIR` but the function `find_project_root` is looking for the **user's project**, not the framework.

### Questions to Resolve

1. When does `macf_tools` need the framework root vs the project root?
2. Which env var controls which path?
3. How should container startup set these correctly?
4. Is `find_project_root` the right function for this context?

### Resolution (Cycle 308 DETOUR)

**Commits**: `b400eb2`, `1cdf3a4`

Three-way path semantics implemented:

| Function | Env Var | Purpose |
|----------|---------|---------|
| `find_maceff_root()` | `MACEFF_ROOT_DIR` | MacEff framework installation |
| `find_project_root()` | `CLAUDE_PROJECT_DIR` | User's project workspace |
| `find_agent_home()` | `MACEFF_AGENT_HOME_DIR` | Agent's sacred home (consciousness persists) |

**Changes Made**:
1. ✅ Created 3 distinct functions in `macf/src/macf/utils/paths.py`
2. ✅ Added 11 tests in `macf/tests/test_paths.py`
3. ✅ Migrated call sites: manifest.py, cycles.py, agent_events_log.py, recovery.py, cli.py
4. ✅ Container setup: Added `MACEFF_AGENT_HOME_DIR=$HOME` to start.py bash_init

**Archive**: `archived_todos/2025-12-24_012029_DETOUR_Path_Finding_Disambiguation_COMPLETED.md`

### Related

- MannyMacEff FP#1 (deployment-side - needs submodule sync)
- `macf/src/macf/utils/paths.py` (path resolution logic)
- `docker/scripts/start.py` (env var setup)
