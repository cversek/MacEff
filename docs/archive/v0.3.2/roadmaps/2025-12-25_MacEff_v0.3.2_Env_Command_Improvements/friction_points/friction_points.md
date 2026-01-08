# Friction Points - Env Command Improvements v0.3.2

## FP#1: Environment Section Too Limited

**Discovered**: 2025-12-27 (C313)
**Status**: FIXING

**Problem**: The `environment` section in `macf_tools env` only showed 3 hardcoded env vars:
- BASH_ENV
- CLAUDE_PROJECT_DIR
- MACEFF_AGENT_HOME_DIR

**Impact**: Important env vars like `MACEFF_TZ`, `CLAUDECODE`, `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` were not visible, reducing diagnostic utility.

**Fix**: Dynamically gather all env vars matching prefixes: `MACEFF_*`, `MACF_*`, `CLAUDE*`, `BASH_ENV`, `TZ`

---

## FP#2: Noisy config.json Warnings

**Discovered**: 2025-12-27 (C313)
**Status**: DOCUMENTED

**Problem**: Running `macf_tools env` produces stderr warnings:
```
⚠️ MACF: JSON file not found (config.json)
⚠️ MACF: JSON read failed (config.json): JSON file not found: /home/pa_manny/.maceff/config.json
⚠️ MACF: Config auto_mode read failed: JSON file not found: /home/pa_manny/.maceff/config.json
```

**Cause**: `detect_auto_mode()` tries to read `.maceff/config.json` which doesn't exist in fresh deployments.

**Impact**: Noisy diagnostic output, confusing for users.

**Potential Fix**:
- Option A: Suppress warnings when config file doesn't exist (it's optional)
- Option B: Create default config.json during container init
- Option C: Use `.claude.json` as config source (Claude Code native format)

**Note**: User suggested `.claude.json` (sibling of `.claude/` directory) as the config file pattern. Needs investigation of Claude Code's native config format.
