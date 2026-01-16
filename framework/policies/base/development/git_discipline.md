# Git Discipline Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Development
**Status**: ACTIVE
**Updated**: 2026-01-15

---

## Policy Statement

Git operations require discipline to maintain repository integrity, enable collaboration, and preserve forensic traceability. This policy consolidates git-related guidance for multi-agent, multi-identity, and submodule-based workflows.

## Scope

Applies to Primary Agents (PA) and all Subagents (SA) performing version control operations.

---

## CEP Navigation Guide

**1 Commit Discipline**
- When should I commit?
- What commit message format should I use?
- How do I structure atomic commits?
- When to include breadcrumbs in commits?
- What types are valid for commit prefixes?

**2 Branch Management**
- When should I create a branch?
- How do I name branches?
- When to merge vs rebase?
- How do I handle merge conflicts?

**3 Push/Pull Protocol**
- When should I push?
- How often should I pull?
- What about force push?
- How do I handle diverged branches?

**4 Multi-Identity Management**
- How do I switch GitHub identities?
- How do I verify identity before operations?
- What causes "Repository not found" errors?
- How do I handle silent switch failures?

**5 Submodule Workflows**
- What is detached HEAD state?
- How do I commit to submodules?
- How do I update parent submodule references?
- How do I verify submodule alignment?

**6 Git-LFS & Large Files**
- When should I use git-lfs?
- What file types need LFS tracking?
- How do I configure .gitattributes?
- What files should never be committed?

**7 Git Safety**
- What operations are dangerous?
- When is --force acceptable?
- How do I recover from mistakes?
- What should I never do?

**8 Release Protocol**
- How do I version releases?
- What changelog format should I use?
- How do I document migrations?

**9 Repository Hygiene**
- How do I keep history clean?
- What belongs in .gitignore?
- When to squash commits?

**10 Collaboration Patterns**
- How do I create good PRs?
- What about code review?
- How do I coordinate with others?

---

## 1. Commit Discipline

### When to Commit

- **Atomic units**: Each commit represents one logical change
- **Compilable state**: Code should work after each commit
- **Before risky operations**: Checkpoint before refactoring, merging, rebasing
- **End of work session**: Never leave uncommitted changes overnight
- **After successful tests**: Commit working code, not broken code

### Commit Message Format

```
type(scope): concise description

[Optional body with more detail]

[Optional breadcrumb: s_xxx/c_xxx/g_xxx/p_xxx/t_xxx]

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Valid Types**:
| Type | Purpose |
|------|---------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `docs` | Documentation only |
| `test` | Test additions or modifications |
| `chore` | Maintenance, dependencies, submodule updates |
| `experiment` | Experimental code (may be reverted) |
| `archive` | Archiving completed work |
| `reflection` | Consciousness artifact commits |

**Scope**: Component or area affected (hooks, cli, policies, etc.)

### Breadcrumb Integration

Include breadcrumbs in commits for:
- Consciousness artifacts (CCPs, JOTEWRs, roadmaps)
- Major feature completions
- Policy updates reflecting cycle learnings
- Cross-repository references

**Identity-Blind Format** (for public repositories):
```
[CTB:s_xxx/c_xxx/g_xxx/p_xxx/t_xxx]
```

This preserves forensic traceability without identity pollution in framework code.

---

## 2. Branch Management

### When to Branch

- **Feature work**: New capabilities requiring multiple commits
- **Risky changes**: Experimental work that might fail
- **Collaboration**: When others need to review before merge
- **Release preparation**: Stabilization before tagging

### Branch Naming

```
feature/description    # New functionality
fix/issue-description  # Bug fixes
experiment/name        # Experimental work
release/vX.Y.Z         # Release preparation
```

### Merge vs Rebase

| Situation | Strategy | Rationale |
|-----------|----------|-----------|
| Local cleanup before pushing | Rebase | Clean linear history |
| Integrating shared branches | Merge | Preserve collaboration history |
| Published/shared branches | Never rebase | Prevents history rewriting |
| Feature branch to main | Squash merge | Clean single-commit integration |

---

## 3. Push/Pull Protocol

### Push Frequency

- After each logical milestone
- Before ending work session
- After successful test runs
- Before switching to different work

### Pull Before Push

Always `git pull --rebase` before pushing to avoid unnecessary merge commits.

### Force Push Rules

| Context | Allowed? | Rationale |
|---------|----------|-----------|
| main/master branches | **NEVER** | Breaks collaboration |
| Shared branches | Only with explicit user request | Coordinates team |
| Personal feature branches | Acceptable | Your responsibility |
| After interactive rebase | If not yet pushed | Local only |

---

## 4. Multi-Identity Management

### Identity Switching Protocol

When working with multiple GitHub identities (personal, team, organizational):

```bash
# 1. Check current identity FIRST
gh auth status 2>&1 | head -3

# 2. Switch if needed
gh auth switch --user <identity-name>

# 3. VERIFY switch succeeded (silent failures are common)
gh auth status 2>&1 | head -3
# Must show: "Active account: true"

# 4. If silent failure, use -u flag
gh auth switch -u <identity-name>
```

### Identity-to-Repository Mapping

Before ANY push operation:
1. Verify current identity matches repository owner
2. Switch if mismatched
3. Verify switch succeeded
4. Then push

### Common Failure Pattern

```
Error: "Repository not found. fatal: repository not found"
```

**Root cause (95% of cases)**: Wrong GitHub identity active

**Diagnostic protocol**:
```bash
# Step 1: Check identity FIRST (not credentials)
gh auth status 2>&1 | head -3

# Step 2: If wrong, switch IMMEDIATELY
gh auth switch --user <correct-identity>

# Step 3: Verify and retry
gh auth status
git push origin main
```

### Post-Compaction Identity Recovery

After context reset, verify identity before operations:
```bash
# Check which identity committed recently
git log --oneline -5  # Review commit messages

# Verify current identity
gh auth status

# Switch if needed
gh auth switch --user <correct-identity>
```

---

## 5. Submodule Workflows

### Understanding Detached HEAD

Submodules exist in **detached HEAD state** (not on a branch):
- Commits to submodule are valid but "orphaned" until referenced
- Parent must update submodule reference after commits
- Two-step commit process required

### Two-Step Commit Pattern

```bash
# 1. Make changes in submodule
git -C /path/to/submodule add .
git -C /path/to/submodule commit -m "fix(component): description"

# 2. Update parent reference
git -C /path/to/parent add submodule-path
git -C /path/to/parent commit -m "chore: update submodule - description"

# 3. Push both (submodule first if on branch)
git -C /path/to/parent push origin main
```

### Submodule Alignment Verification

Before deployment or major operations:
```bash
# Source and submodule should show same commit
git -C /path/to/source log --oneline -1
git -C /path/to/parent/submodule log --oneline -1

# If different → submodule not updated
```

### Pulling Upstream into Submodule

```bash
# 1. Fetch and merge in submodule
git -C /path/to/submodule fetch origin
git -C /path/to/submodule merge origin/main

# 2. Update parent reference
git -C /path/to/parent add submodule-path
git -C /path/to/parent commit -m "chore: update submodule"
git -C /path/to/parent push origin main
```

---

## 6. Git-LFS & Large Files

### When to Use Git-LFS

| File Category | Examples | LFS? |
|---------------|----------|------|
| ML/Data | `.pkl`, `.joblib`, training data | Yes |
| Compiled | `.so`, `.pyd`, binaries | Yes |
| Generated | `.db`, large `.log`, caches | Yes |
| Consciousness artifacts | `.md`, `.json` | No |
| Source code | `.py`, `.ts`, `.go` | No |
| Configuration | `.yaml`, `.toml` | No |

### .gitattributes Configuration

```gitattributes
# Machine Learning artifacts
examples/data/**/*.pkl filter=lfs diff=lfs merge=lfs -text
models/**/*.joblib filter=lfs diff=lfs merge=lfs -text

# Compiled extensions
src/**/*.so filter=lfs diff=lfs merge=lfs -text

# Large generated artifacts
cache/**/*.db filter=lfs diff=lfs merge=lfs -text
logs/**/*.log filter=lfs diff=lfs merge=lfs -text
```

### Container LFS Setup

```dockerfile
RUN apt-get install -y git git-lfs
RUN git lfs install --system
```

System-wide installation ensures all processes have transparent LFS support.

### Files That Should NEVER Be Committed

| Category | Examples | Solution |
|----------|----------|----------|
| Secrets | `.env`, credentials, API keys | `.gitignore` |
| Build artifacts | `__pycache__/`, `node_modules/` | `.gitignore` |
| IDE config | `.idea/`, `.vscode/` (usually) | `.gitignore` |
| OS artifacts | `.DS_Store`, `Thumbs.db` | `.gitignore` |
| Large binaries | videos, datasets | Git-LFS or external storage |

---

## 7. Git Safety

### Dangerous Operations

| Operation | Risk | When Acceptable |
|-----------|------|-----------------|
| `git push --force` | HIGH | Personal branch only, explicit request |
| `git reset --hard` | HIGH | Local only, after careful review |
| `git rebase -i` | MEDIUM | Local commits only |
| `git clean -fd` | MEDIUM | After checking `git status` |
| `git checkout -- .` | MEDIUM | Intentional discard of all changes |

### Never Do

- Force push to main/master
- Rebase published commits
- Commit secrets or credentials
- Skip hooks without explicit reason (`--no-verify`)
- Use interactive git commands (`-i` flag) in automation

### Recovery Commands

```bash
# Find lost commits
git reflog

# Undo last commit, keep changes staged
git reset --soft HEAD~1

# Discard changes in specific file
git checkout -- <file>

# Temporarily save changes
git stash
git stash pop  # Restore

# Recover from bad merge
git merge --abort

# Recover from bad rebase
git rebase --abort
```

---

## 8. Release Protocol

### Semantic Versioning

Format: `vMAJOR.MINOR.PATCH`

| Component | Increment When |
|-----------|----------------|
| MAJOR | Breaking changes, incompatible API |
| MINOR | New features, backward compatible |
| PATCH | Bug fixes, no new features |

### Changelog Format (Keep a Changelog)

```markdown
## [vX.Y.Z] - YYYY-MM-DD

### Summary
One-line overview of release scope.

### Added
- New feature A
- New capability B

### Changed
- Modified behavior X
- Updated component Y

### Fixed
- Bug fix for issue Z
- Resolved edge case W

### Infrastructure
- Technical implementation details
```

### Migration Documentation

Major versions require:
- Multi-phase migration guide
- Friction point catalog (what breaks, impact, workaround)
- Success criteria per phase (testable completion)
- Backup protocols before destructive operations
- Step-by-step validation commands

---

## 9. Repository Hygiene

### Standard .gitignore

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Environment
.env
.env.local

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
*.log

# Test/Coverage
.coverage
htmlcov/
.pytest_cache/
```

### Clean History Practices

- Squash WIP commits before merging to main
- Write meaningful commit messages (not "fix", "wip", "stuff")
- Keep commits focused and atomic
- Remove debug code before committing

### Workspace Discipline

**Forbidden in package source**:
- Ad hoc development scripts
- Temporary test files
- Generated cache files
- Debug scripts

**Ad hoc scripts go to**: `agent/public/dev_scripts/YYYY-MM-DD_HHMMSS_purpose.py`

---

## 10. Collaboration Patterns

### PR Description Format

```markdown
## Summary
- Brief description of changes (1-3 bullets)

## Test plan
- How to verify the changes
- Commands to run
- Expected output

## Related
- Links to issues, roadmaps, or discussions

---
Generated with Claude Code
```

### Code Review Protocol

1. **Before requesting review**: Run tests, lint, verify build
2. **Respond promptly**: Address feedback within session if possible
3. **Explain decisions**: Comment on non-obvious choices
4. **Iterate small**: Multiple small PRs > one large PR

### Coordination Patterns

- **Communicate intent**: Announce major refactoring before starting
- **Avoid conflicts**: Check who's working on what
- **Merge frequently**: Don't let branches diverge too far
- **Tag milestones**: Create tags for significant releases

---

## Cross-References

- [Roadmaps Following](../consciousness/roadmaps_following.md) - Commit requirements for roadmap phases
- [Checkpoints](../consciousness/checkpoints.md) - Git commit references in CCPs
- [Agent Backup](../operations/agent_backup.md) - Git discipline for backups
- [Scholarship](../consciousness/scholarship.md) - Breadcrumb format for citations
- [Workspace Discipline](workspace_discipline.md) - File organization standards

---

**Policy Complete**
