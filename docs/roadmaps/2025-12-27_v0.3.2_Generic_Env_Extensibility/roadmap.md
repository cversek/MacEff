# MISSION: Generic Environment Extensibility

**Date**: Saturday, Dec 27, 2025
**Version**: v0.3.2
**Status**: ACTIVE

---

## Mission

Make MacEff's `bash_init.sh` a simple dispatcher that sources `/opt/maceff/framework/env.d/*.sh` in alphanumeric order. Deployments provide their own conda/venv/whatever scripts via overlay. **No schemas. No templates. Just files.**

**Success**: `create_bash_init()` generates a minimal dispatcher. Environment-specific activation (conda, venv, etc.) lives in deployment overlays, not MacEff base.

---

## The Mechanism

```
MannyMacEff/framework/env.d/10-conda.sh     (parent creates)
    ↓ (maceff-init --force-overwrite)
MacEff/.maceff/framework/env.d/10-conda.sh  (overlay populated)
    ↓ (docker-compose mounts .maceff/framework/ → /opt/maceff/framework/)
/opt/maceff/framework/env.d/10-conda.sh     (container path)
    ↓ (bash_init.sh sources in alphanumeric order)
Conda activated
```

**Script Ordering Convention**:
- `00-*.sh` - Core setup (first)
- `10-*.sh` - Language managers (conda, pyenv, nvm)
- `20-*.sh` - PATH modifications
- `50-*.sh` - Custom deployment scripts
- `90-*.sh` - Finalization (last)

---

## Phase 1: Simplify create_bash_init()

**File**: `docker/scripts/start.py`

**Changes**:
1. Remove all conda-specific code from `create_bash_init()`
2. Remove `conda_env` parameter
3. Source from `/opt/maceff/framework/env.d/*.sh` (glob expands alphanumerically)

**New bash_init.sh content**:
```bash
#!/bin/bash
# MacEff: Shell initialization
export BASH_ENV="$HOME/.bash_init.sh"
export MACEFF_AGENT_HOME_DIR="$HOME"
export MACEFF_AGENT_NAME="{agent_name}"

# Source deployment-provided environment scripts (alphanumeric order)
if [ -d /opt/maceff/framework/env.d ]; then
    for script in /opt/maceff/framework/env.d/*.sh; do
        [ -r "$script" ] && . "$script"
    done
fi
```

**Success Criteria**:
- [ ] No conda code in start.py
- [ ] bash_init.sh sources from /opt/maceff/framework/env.d/
- [ ] Scripts execute in alphanumeric order
- [ ] Tests pass

---

## Phase 2: Remove conda_env from AgentSpec

**File**: `macf/src/macf/models/agent_spec.py`

Delete the `conda_env` field entirely.

**Success Criteria**:
- [ ] Field removed
- [ ] Tests pass

---

## Phase 3: Update maceff-init for env.d overlay

**File**: `maceff_tools/maceff-init`

Add to parent overlay section (~line 131):
```bash
if [[ -d "$REPO_ROOT/framework/env.d" ]]; then
    mkdir -p "$MACEFF_DIR/framework/env.d"
    cp -r "$REPO_ROOT/framework/env.d/"* "$MACEFF_DIR/framework/env.d/" 2>/dev/null || true
    warn "  ⚠ OVERLAY: env.d/* (parent environment scripts)"
fi
```

**Success Criteria**:
- [ ] maceff-init copies env.d from parent
- [ ] Scripts appear in .maceff/framework/env.d/

---

## Phase 4: Create MannyMacEff env.d scripts

**Location**: `MannyMacEff/framework/env.d/`

**10-conda.sh**:
```bash
#!/bin/bash
# MannyMacEff: Conda activation
if [ -f /opt/miniforge3/etc/profile.d/conda.sh ]; then
    . /opt/miniforge3/etc/profile.d/conda.sh
    conda activate "neurovep_data" 2>/dev/null || true
fi
```

**20-path.sh**:
```bash
#!/bin/bash
# MannyMacEff: PATH setup
if [ -d "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi
```

**Success Criteria**:
- [ ] Scripts created in MannyMacEff/framework/env.d/
- [ ] Scripts are executable (chmod +x)

---

## Phase 5: Documentation Updates

**File**: `docs/OPERATORS.md`

Add section: "Environment Extensibility"
- Explain env.d mechanism
- Document script ordering convention (00-90)
- Provide examples for conda, venv, nvm
- Explain overlay flow: parent → maceff-init → container

**File**: `docs/DEPLOYMENT.md` (or similar)

Document for deployment operators:
- How to create custom env.d scripts
- Where to place them (framework/env.d/)
- How maceff-init populates the overlay
- Verification steps

**Success Criteria**:
- [ ] OPERATORS.md updated with env.d section
- [ ] Deployment documentation covers env.d usage

---

## Phase 6: Verification

1. Run maceff-init in MannyMacEff
2. Rebuild container
3. SSH in, verify `which python` = conda python
4. Verify scripts sourced in order (add echo debug if needed)
5. Verify `macf_tools env` works

**Success Criteria**:
- [ ] Conda activation works
- [ ] MACEFF_* vars set
- [ ] No regression
- [ ] Scripts execute in correct order

---

## Critical Files

| File | Change |
|------|--------|
| `docker/scripts/start.py` | Simplify create_bash_init() |
| `macf/src/macf/models/agent_spec.py` | Remove conda_env field |
| `maceff_tools/maceff-init` | Add env.d overlay copying |
| `docs/OPERATORS.md` | Document env.d mechanism |
| `MannyMacEff/framework/env.d/*.sh` | NEW deployment scripts |
