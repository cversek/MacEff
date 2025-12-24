# MacEff v0.3.1 Friction Points

## FP#1: Path Resolution Semantics Confusion

**Reported**: 2025-12-22
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

### Proposed Fix

1. **Clarify semantics**: Document each path concept in maintainer docs
2. **Env var audit**: Review all MACEFF_* and MACF_* env vars
3. **Container setup**: Ensure start.py sets correct vars in agent environment
4. **Warning improvement**: Make warning specify which path is missing

### Related

- MannyMacEff FP#1 (deployment-side of same issue)
- `macf/src/macf/utils/paths.py` (path resolution logic)
- `docker/scripts/start.py` (env var setup)
