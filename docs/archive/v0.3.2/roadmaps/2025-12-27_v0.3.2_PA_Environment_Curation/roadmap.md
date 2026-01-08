# MacEff v0.3.2 PA Environment Curation ROADMAP

**Date**: Saturday, Dec 27, 2025
**Breadcrumb**: s_abc12345/c_42/g_bf70468/p_none/t_1766874196
**Status**: ACTIVE
**Context**: Fix env var propagation gap - SSH sessions don't inherit docker-compose vars

---

## Mission

Implement unified PA environment configuration that works for SSH sessions, Claude Code Bash tool (non-interactive shells), and any other shell contexts. Fix the documentation gap where OPERATORS.md describes `.bash_init.sh` but start.py doesn't create it.

**The Problem**:
1. docker-compose.yml sets `BASH_ENV=/home/pa_manny/.bash_init.sh`
2. SSH sessions don't inherit docker-compose env vars (they read `/etc/environment`)
3. start.py doesn't create `.bash_init.sh` (documentation gap)
4. Claude Code shows `BASH_ENV: (not set)` in `macf_tools env`

**The Solution** (DRY pattern):
- `~/.bash_init.sh` - Single source of truth for PA shell initialization
- `~/.bashrc` sources it (interactive shells)
- `BASH_ENV=~/.bash_init.sh` in `/etc/environment` (non-interactive shells via SSH)
- `~/.claude/settings.json` `env` field (belt-and-suspenders for Claude Code)

---

## Phase 1: Create `create_bash_init()` Function

**File**: `docker/scripts/start.py`
**Location**: Insert after `install_ssh_key()` (~line 128)

Creates `~/.bash_init.sh` with:
- `BASH_ENV` (self-referential for nested shells)
- `MACEFF_AGENT_HOME_DIR=$HOME` (PA-specific)
- `MACEFF_AGENT_NAME=<agent_name>` (PA-specific)
- Conda activation block
- PATH for maceff-venv

Note: `MACEFF_ROOT_DIR` is in `/etc/environment` (container-wide)

**Success Criteria**:
- [ ] Function created with proper docstring
- [ ] File created with 755 permissions
- [ ] Owned by PA user

---

## Phase 2: Modify `configure_bashrc()` to DRY

**File**: `docker/scripts/start.py`
**Location**: Lines 146-162

Replace inline exports with sourcing bash_init.sh. Keep active_project cd logic (interactive-only).

**Success Criteria**:
- [ ] .bashrc sources .bash_init.sh
- [ ] No duplicate exports
- [ ] Idempotency check updated

---

## Phase 3: Modify `propagate_container_env()` for Container-Wide Vars

**File**: `docker/scripts/start.py`
**Location**: Lines 750-770

Add to `/etc/environment`:
- `MACEFF_ROOT_DIR=/opt/maceff` (constant for all PAs)
- `BASH_ENV=~/.bash_init.sh` (tilde expands per-user)

**Success Criteria**:
- [ ] /etc/environment contains MACEFF_ROOT_DIR=/opt/maceff
- [ ] /etc/environment contains BASH_ENV=~/.bash_init.sh
- [ ] Existing MACEFF_TZ logic preserved

---

## Phase 4: Inject PA Vars into Claude Settings

**File**: `docker/scripts/start.py`
**Location**: After line 225 in `configure_claude_settings()`

Inject into `merged_settings.env`:
- `MACEFF_AGENT_HOME_DIR` (PA-specific)
- `MACEFF_AGENT_NAME` (PA-specific)

**Success Criteria**:
- [ ] settings.json contains PA env vars
- [ ] Explicit config not overwritten

---

## Phase 5: Update Call Order in `create_pa_user()`

**File**: `docker/scripts/start.py`
**Location**: Lines 88-109

Add call to `create_bash_init()` BEFORE `configure_bashrc()`.

**Success Criteria**:
- [ ] create_bash_init() called before configure_bashrc()

---

## Phase 6: Update KEY_ENV_VARS

**File**: `macf/src/macf/utils/environment.py`
**Location**: Lines 18-26

- Replace `MACF_AGENT` with `MACEFF_AGENT_NAME` for consistency
- Ensure all new vars included for `macf_tools env` reporting

**Success Criteria**:
- [ ] KEY_ENV_VARS contains MACEFF_AGENT_NAME
- [ ] `macf_tools env` displays all new vars

---

## Phase 7: Verification

**Rebuild and Test**:
```bash
make build && make down && make up
make ssh
```

**Verification Commands**:
```bash
cat ~/.bash_init.sh
grep 'bash_init' ~/.bashrc
cat /etc/environment | grep -E 'BASH_ENV|MACEFF_ROOT'
cat ~/.claude/settings.json | jq '.env'
macf_tools env
```

**Success Criteria**:
- [ ] All env vars show correctly in `macf_tools env`
- [ ] Non-interactive shells have MACEFF_ROOT_DIR
- [ ] Conda activates in non-interactive context

---

## Variable Scoping

| Variable | Scope | Location |
|----------|-------|----------|
| `MACEFF_TZ` | Container-wide | `/etc/environment` |
| `BASH_ENV` | Container-wide | `/etc/environment` (tilde expands per-user) |
| `MACEFF_ROOT_DIR` | Container-wide | `/etc/environment` |
| `MACEFF_AGENT_HOME_DIR` | PA-specific | `~/.bash_init.sh` + `settings.json` |
| `MACEFF_AGENT_NAME` | PA-specific | `~/.bash_init.sh` + `settings.json` |

---

## Critical Files

| File | Purpose |
|------|---------|
| `docker/scripts/start.py` | Primary implementation target |
| `macf/src/macf/utils/environment.py` | KEY_ENV_VARS update |
