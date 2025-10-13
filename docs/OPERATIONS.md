# MacEff Operations Guide

## Framework Upgrade Workflows

This guide covers operational procedures for upgrading MacEff framework components in running containers without rebuilds.

---

## Quick Reference

```bash
# Full framework upgrade (all components)
tools/bin/framework-upgrade

# Individual component upgrades
tools/bin/policy-sync [set_name]     # Sync policies
tools/bin/template-sync              # Sync templates
tools/bin/tools-sync                 # Deploy macf_tools package
tools/bin/preamble-upgrade [pa_user] # Upgrade PA preambles
```

---

## Upgrading Policies

**Command**: `tools/bin/policy-sync [set_name]`

**Purpose**: Sync policy files from host to running container

**Usage**:
```bash
# Sync base policy set (default)
tools/bin/policy-sync

# Sync specific policy set
tools/bin/policy-sync experimental
```

**What it does**:
- Copies `policies/base/` (or specified set) to container `/opt/maceff/policies/sets/[set_name]/`
- Fixes permissions (chmod 644 for policy files)
- Updates `current` symlink if needed

**Validation**:
```bash
docker exec maceff-sandbox ls -la /opt/maceff/policies/current/
docker exec maceff-sandbox cat /opt/maceff/policies/current/manifest.json | jq .
```

---

## Upgrading Templates

**Command**: `tools/bin/template-sync`

**Purpose**: Deploy latest preamble and template files to container

**Usage**:
```bash
tools/bin/template-sync
```

**What it does**:
- Copies `templates/` directory to container `/opt/maceff/templates/`
- Fixes permissions (chmod 644 for template files)
- Lists synced templates

**Validation**:
```bash
docker exec maceff-sandbox ls -la /opt/maceff/templates/
docker exec maceff-sandbox cat /opt/maceff/templates/PA_PREAMBLE.md | head -20
```

**When to use**: After updating PA_PREAMBLE.md or other template files

---

## Upgrading macf_tools Package

**Command**: `tools/bin/tools-sync`

**Purpose**: Deploy latest macf_tools Python package code to container

**Usage**:
```bash
tools/bin/tools-sync
```

**What it does**:
- Copies `tools/src/` directory to container `/opt/tools/src/`
- Reinstalls package in container: `pip install -e /opt/tools`
- Displays updated version

**Validation**:
```bash
docker exec maceff-sandbox bash -lc "macf_tools --version"
docker exec maceff-sandbox bash -lc "python -c 'import macf; print(macf.__version__)'"
```

**When to use**: After making changes to macf_tools CLI or hook code

---

## Upgrading PA Preambles

**Command**: `tools/bin/preamble-upgrade [pa_user]`

**Purpose**: Update PA CLAUDE.md files with latest framework preamble while preserving user content

**Usage**:
```bash
# Upgrade default PA (from common.sh)
tools/bin/preamble-upgrade

# Upgrade specific PA
tools/bin/preamble-upgrade alice
tools/bin/preamble-upgrade maceff_user001
```

**What it does**:
1. Syncs latest templates (ensures PA_PREAMBLE.md is current)
2. Runs `macf_tools agent init` inside container as PA user
3. Replaces framework content below upgrade boundary
4. **Preserves user content above boundary marker**

**Upgrade Boundary**:
```markdown
---

<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->
<!-- Framework preamble managed by macf_tools - edits below will be lost on upgrade -->
<!-- Add custom policies and agent-specific content ABOVE this boundary -->
```

**User content above this line survives upgrades.**

**Validation**:
```bash
# Check user content preserved
docker exec -u maceff_user001 maceff-sandbox head -20 ~/.claude/CLAUDE.md

# Verify boundary marker exists
docker exec -u maceff_user001 maceff-sandbox grep "DO NOT WRITE BELOW" ~/.claude/CLAUDE.md
```

**When to use**: After updating framework policies or preamble templates

---

## Full Framework Upgrade

**Command**: `tools/bin/framework-upgrade`

**Purpose**: One-command upgrade of all framework components

**Usage**:
```bash
tools/bin/framework-upgrade
```

**What it does** (in order):
1. **[1/4]** Sync policies (`policy-sync`)
2. **[2/4]** Sync templates (`template-sync`)
3. **[3/4]** Sync macf_tools package (`tools-sync`)
4. **[4/4]** Upgrade PA preambles (`preamble-upgrade`)

**When to use**:
- After pulling framework updates from git
- Regular maintenance upgrades
- Before starting new development work

**Validation**:
```bash
# Verify all components updated
docker exec maceff-sandbox ls -la /opt/maceff/policies/current/
docker exec maceff-sandbox ls -la /opt/maceff/templates/
docker exec maceff-sandbox bash -lc "macf_tools --version"
docker exec -u maceff_user001 maceff-sandbox head -20 ~/.claude/CLAUDE.md
```

---

## Rollback Procedures

### Rollback Strategy

All upgrade scripts are **idempotent** (safe to re-run). To rollback:

1. **Git checkout previous version** on host
2. **Re-run upgrade scripts** to sync old version to container

### Step-by-Step Rollback

```bash
# 1. Find commit before problematic upgrade
cd /Users/cversek/gitwork/cversek/MacEff
git log --oneline -10

# 2. Checkout previous version
git checkout <previous-commit-hash>

# 3. Re-sync to container (overwrites with old version)
tools/bin/framework-upgrade

# 4. Validate rollback worked
docker exec maceff-sandbox cat /opt/maceff/policies/current/manifest.json | jq .version
docker exec maceff-sandbox bash -lc "macf_tools --version"

# 5. Return to main branch (or stay on old version)
git checkout main
```

### Emergency Recovery

If container is broken:

```bash
# 1. Stop container
make down

# 2. Checkout known-good version
git checkout <known-good-commit>

# 3. Rebuild container (bakes framework assets)
make build

# 4. Start container
make up

# 5. Verify
make ssh-pa
# Test inside container
```

---

## Troubleshooting

### Container Not Running

**Symptom**: Scripts fail with "container not running"

**Fix**:
```bash
# Start container
make up

# Verify running
docker ps | grep maceff
```

### Permission Errors

**Symptom**: "Permission denied" when accessing files in container

**Fix**:
```bash
# Fix template permissions
tools/bin/template-sync

# Fix policy permissions
tools/bin/policy-sync

# Manual permission fix (if needed)
docker exec -u 0 maceff-sandbox chmod 644 /opt/maceff/policies/current/*.md
```

### Preamble Upgrade Overwrites User Content

**Symptom**: Custom policies lost after `preamble-upgrade`

**Cause**: User content was below upgrade boundary

**Prevention**:
- Always add custom content **above** the boundary marker
- Check boundary exists: `grep "DO NOT WRITE BELOW" ~/.claude/CLAUDE.md`

**Recovery**:
```bash
# Check git history in container
docker exec -u maceff_user001 maceff-sandbox bash -lc "cd ~/.claude && git log --oneline"

# Restore from git if needed
docker exec -u maceff_user001 maceff-sandbox bash -lc "cd ~/.claude && git checkout HEAD~1 CLAUDE.md"
```

### macf_tools Version Not Updating

**Symptom**: `macf_tools --version` shows old version after `tools-sync`

**Fix**:
```bash
# Force reinstall in container
docker exec maceff-sandbox bash -lc "pip install --force-reinstall -e /opt/tools"

# Verify
docker exec maceff-sandbox bash -lc "macf_tools --version"
```

---

## Container Lifecycle

### Initial Setup

```bash
# 1. Build container (includes framework assets)
make build

# 2. Start container
make up

# 3. Verify PA initialized automatically
docker exec -u maceff_user001 maceff-sandbox cat ~/.claude/CLAUDE.md | head -20
```

### Regular Maintenance

```bash
# Weekly or after framework updates
tools/bin/framework-upgrade
```

### Development Workflow

```bash
# 1. Make changes to policies/templates/tools
git add -p
git commit -m "feat: description"

# 2. Sync to running container (no rebuild)
tools/bin/framework-upgrade

# 3. Test in container
make ssh-pa
# Test changes inside container

# 4. Iterate without rebuild
```

---

## Best Practices

1. **Always use upgrade scripts** - Don't manually copy files
2. **Test before deploying** - Run upgrades on dev container first
3. **Commit before upgrading** - Clean git state enables rollback
4. **Validate after upgrades** - Run validation commands
5. **Document deviations** - Note any manual interventions

---

## Related Documentation

- **Agent Bootstrap**: See `AGENT_BOOTSTRAP.md` for PA onboarding
- **Policy Architecture**: See `policies/base/manifest.json` for discovery index
- **Tool Development**: See `tools/README.md` for macf_tools development

---

**Last Updated**: 2025-10-13 (Cycle 32, Sprint 4)
