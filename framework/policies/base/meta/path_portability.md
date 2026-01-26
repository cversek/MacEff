# Path Portability Guidelines

**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Type**: Meta-Policy (Framework Infrastructure)
**Scope**: All MacEff-portable artifacts (skills, commands, subagents, policies)
**Status**: ACTIVE

---

## Purpose

Path portability guidelines ensure MacEff framework artifacts work across ANY deployment environment—container, host system, different user accounts, different machines. Portable paths enable framework reuse without environment-specific modifications.

**Core Insight**: Hardcoded absolute paths bind artifacts to specific environments, breaking portability. Portable paths use context-dependent resolution that adapts to runtime environment.

---

## CEP Navigation Guide

**1 The Portability Problem**
- What breaks when paths are hardcoded?
- Why do absolute paths limit framework reuse?
- What environments must MacEff support?

**2 Path Resolution Contexts**
- What are the three resolution contexts?
- How does container resolution work?
- How does host resolution work?
- When are dev exceptions acceptable?

**2.1 Container Context**
- What path does the container use?
- Where is FRAMEWORK_ROOT defined?
- How do container agents access policies?

**2.2 Host Context**
- How do host agents find framework root?
- What git command detects project root?
- What's the portable host pattern?

**2.3 Development Exceptions**
- When are hardcoded paths acceptable?
- What makes agent-specific different from MacEff-portable?
- How do I know if my artifact needs portability?

**3 The {FRAMEWORK_ROOT} Placeholder**
- What is {FRAMEWORK_ROOT}?
- How do I use it in documentation?
- When should I use the placeholder vs resolution?

**4 Portable Path Patterns**
- What's the correct pattern for skills?
- What's the correct pattern for commands?
- What's the correct pattern for subagents?
- What's the correct pattern for policies referencing other policies?

**5 Anti-Patterns**
- What paths should never appear in portable artifacts?
- What are common portability violations?
- How do I audit for violations?

**6 Integration with Other Policies**
- How does this relate to policy_writing.md?
- How does this relate to slash_command_writing.md?

=== CEP_NAV_BOUNDARY ===

---

## 1 The Portability Problem

**What Breaks**: When paths like `/home/alice/projects/MacEff/framework/policies/...` appear in framework artifacts, those artifacts only work on that specific machine with that specific user.

**Environments MacEff Must Support**:

| Environment | Characteristics |
|-------------|-----------------|
| **Container** | Docker, fixed paths, orchestrated startup |
| **Host (any user)** | macOS/Linux, variable home directories |
| **CI/CD** | Ephemeral, cloned repos, no persistent state |
| **Different machines** | Different usernames, different directory structures |

**The Test**: Can another developer clone MacEff and use all framework artifacts without modification? If no → portability violation.

---

## 2 Path Resolution Contexts

### 2.1 Container Context

**Container Framework Root**: `/opt/maceff/framework`

**Source**: `MacEff/docker/scripts/start.py`:
```python
FRAMEWORK_ROOT = Path('/opt/maceff/framework')
```

**Note**: This is a Python constant, NOT an environment variable. Container agents access policies via this hardcoded path because container filesystem is controlled and predictable.

**Container Path Examples**:
```
/opt/maceff/framework/policies/base/meta/policy_writing.md
/opt/maceff/framework/subagents/DevOpsEng.md
/opt/maceff/framework/templates/PA_PREAMBLE.md
```

### 2.2 Host Context (Portable)

**Host Framework Root**: Detected via git at runtime

**Pattern**:
```bash
$(git rev-parse --show-toplevel)/framework
```

**Why Git Detection**:
- Works regardless of where repo is cloned
- Works for any username
- Works on any machine
- Self-adapting to environment

**Host Resolution in Skills/Commands**:
```bash
# ✅ PORTABLE: Detect framework root dynamically
FRAMEWORK_ROOT="$(git rev-parse --show-toplevel)/framework"
POLICY_PATH="${FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md"

# ❌ NON-PORTABLE: Hardcoded absolute path
POLICY_PATH="/home/alice/projects/MacEff/framework/policies/base/meta/policy_writing.md"
```

**Fallback for Non-Git Contexts**:
```bash
# With fallback
FRAMEWORK_ROOT="${MACEFF_FRAMEWORK_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)/framework}"
```

### 2.3 Development Exceptions

**When Hardcoded Paths Are Acceptable**:

1. **Private repository artifacts** (agent-specific tooling):
   - Agent-specific slash commands (not `/maceff_*` prefixed)
   - Agent-specific configurations
   - Personal consciousness artifacts

2. **Documentation examples** showing actual paths for clarity (sanitized)

3. **Test fixtures** that explicitly test specific paths

**The Distinction**:

| Artifact Type | Naming Pattern | Portability Required |
|---------------|----------------|---------------------|
| **MacEff-portable** | `/maceff_*`, `maceff-*` | ✅ MANDATORY |
| **Framework subagents** | `framework/subagents/*.md` | ✅ MANDATORY |
| **Framework policies** | `framework/policies/**/*.md` | ✅ MANDATORY |
| **Agent-specific commands** | Agent's own prefix | ❌ Dev exception OK |
| **Private agent artifacts** | `agent/private/**` | ❌ Personal, not shared |

**How to Know**:
- Will this artifact be used by other agents/projects? → Must be portable
- Is this in the MacEff framework directory? → Must be portable
- Does the name start with `maceff` or `/maceff_`? → Must be portable
- Is this private to one agent's development? → Exception acceptable

---

## 3 The {FRAMEWORK_ROOT} Placeholder

**Purpose**: `{FRAMEWORK_ROOT}` is a documentation placeholder representing the framework root path. It signals "this path must be resolved at runtime" rather than hardcoded.

**Usage in Documentation**:
```markdown
Read the policy at `{FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md`
```

**Usage in Skills/Commands** (actual resolution):
```bash
# Resolve placeholder at runtime
FRAMEWORK_ROOT="$(git rev-parse --show-toplevel)/framework"

# Then use resolved path
cat "${FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md"
```

**When to Use Placeholder vs Resolution**:

| Context | Use |
|---------|-----|
| **Documentation/policies** | `{FRAMEWORK_ROOT}` placeholder |
| **Executable code** | Actual resolution (`$(git rev-parse ...)`) |
| **Agent reading lists** | `{FRAMEWORK_ROOT}` placeholder (agent resolves) |
| **Shell scripts** | Actual resolution at script start |

---

## 4 Portable Path Patterns

### 4.1 Skills (`maceff-*`)

**SKILL.md Pattern**:
```markdown
## Reading List

1. **Policy Foundation**:
   - `{FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md`

## Execution

```bash
# Resolve framework root
FRAMEWORK_ROOT="$(git rev-parse --show-toplevel)/framework"

# Use resolved paths
cat "${FRAMEWORK_ROOT}/policies/base/development/task_management.md"
```
```

### 4.2 Commands (`/maceff_*`)

**Command Pattern**:
```markdown
## Policy Reading

Read the following before execution:
- `{FRAMEWORK_ROOT}/policies/base/consciousness/roadmaps_drafting.md`

## Implementation Notes

Commands should NOT embed policy content. Instead, reference policies
using `{FRAMEWORK_ROOT}` and let the agent read at execution time.
```

### 4.3 Subagents (`framework/subagents/`)

**Subagent Definition Pattern**:
```markdown
## Reading List

When delegating to this specialist, ensure they read:

1. **Foundation Policy**:
   - `{FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md`

2. **Domain Policy**:
   - `{FRAMEWORK_ROOT}/policies/base/development/testing.md`
```

### 4.4 Policies Referencing Other Policies

**Cross-Policy Reference Pattern**:
```markdown
## Integration with Other Policies

- `policy_writing.md` - Structure and CEP navigation requirements
- `task_management.md` - Breadcrumb format specification

See also: `{FRAMEWORK_ROOT}/policies/base/meta/slash_command_writing.md`
```

**Note**: Within the same policy directory, use relative names (`policy_writing.md`). Use `{FRAMEWORK_ROOT}` when referencing from outside the policies directory.

---

## 5 Anti-Patterns

### 5.1 Hardcoded User Paths

**❌ VIOLATION**:
```markdown
Read `/home/alice/projects/MacEff/framework/policies/base/meta/policy_writing.md`
```

**Problem**: Only works for user `alice` on their specific machine.

**✅ FIX**:
```markdown
Read `{FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md`
```

### 5.2 Hardcoded Project Paths

**❌ VIOLATION**:
```bash
POLICY="/home/developer/projects/MacEff/framework/policies/..."
```

**Problem**: Assumes specific project location.

**✅ FIX**:
```bash
FRAMEWORK_ROOT="$(git rev-parse --show-toplevel)/framework"
POLICY="${FRAMEWORK_ROOT}/policies/..."
```

### 5.3 Mixed Portable and Non-Portable

**❌ VIOLATION**:
```markdown
## Reading List
1. `{FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md`
2. `/home/bob/dev/MacEff/framework/policies/base/development/testing.md`
```

**Problem**: Inconsistent - some paths portable, some not.

**✅ FIX**: All paths in reading lists must use same resolution pattern.

### 5.4 Forgetting Framework Suffix

**❌ VIOLATION**:
```bash
ROOT="$(git rev-parse --show-toplevel)"
cat "${ROOT}/policies/base/meta/policy_writing.md"  # Missing /framework!
```

**Problem**: Policies are in `/framework/policies/`, not `/policies/`.

**✅ FIX**:
```bash
FRAMEWORK_ROOT="$(git rev-parse --show-toplevel)/framework"
cat "${FRAMEWORK_ROOT}/policies/base/meta/policy_writing.md"
```

### 5.5 Auditing for Violations

**Quick Grep Audit**:
```bash
# Find potential violations in framework directory
grep -r "/Users/" framework/
grep -r "/home/" framework/
grep -rE "gitwork|projects" framework/

# Find in skills (maceff-* only)
grep -r "/Users/" .claude/skills/maceff-*/
grep -r "/home/" .claude/skills/maceff-*/

# Find in commands (maceff_* only)
grep -r "/Users/" .claude/commands/maceff_*/
grep -r "/home/" .claude/commands/maceff_*/
```

**Note**: Agent-specific commands and skills (not prefixed with `maceff`) are exempt from this audit.

---

## 6 Integration with Other Policies

- `policy_writing.md` - All framework policies must follow portability guidelines; sanitization requirements align with portability
- `slash_command_writing.md` - `/maceff_*` commands must use portable paths
- `workspace_discipline.md` - Agent workspace organization patterns

**Enforcement**: PolicyWriter and other subagents creating framework artifacts MUST apply path portability. Agent definitions should include portability requirements in their reading lists.

---

## 7 Evolution & Feedback

This policy evolves through:
- Discovery of new portability violations
- New deployment contexts (CI/CD, cloud, etc.)
- Framework restructuring

**Principle**: "If it's in the framework, it must work everywhere the framework runs."

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
