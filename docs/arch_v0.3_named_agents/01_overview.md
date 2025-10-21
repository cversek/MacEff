# Named Agents Architecture - Overview

**Version**: 0.3.0
**Last Updated**: 2025-10-19
**Status**: Empirically Validated (Conventional Policy Model)

[← Back to Index](./INDEX.md) | [Next: Filesystem Structure →](./02_filesystem_structure.md)

---

## What are Named Agents?

**Named Agents** is an architectural pattern for multi-agent AI systems where each agent has a unique identity reflected in their operating system username and workspace organization.

Instead of numbered agents (`agent_001`, `agent_002`), Named Agents uses meaningful identities:
- `pa_manny` - A Primary Agent focused on neuroscience research
- `pa_claudethebuilder` - A Primary Agent focused on framework development
- `pa_alice` - A Primary Agent focused on data analysis

The "Named" in Named Agents means:
- **Identity over enumeration** - Agents have persistent names, not sequential numbers
- **No ordering assumptions** - The system works without requiring agents to be numbered sequentially
- **Searchable and human-readable** - Easy to identify agents in logs, processes, and filesystem

## Core Concepts

### Primary Agents (PA)

A **Primary Agent (PA)** is the main agent with:
- Unique identity and persistent consciousness across sessions
- Own operating system user account (e.g., `pa_manny`)
- Isolated home directory with consciousness artifacts
- Ability to delegate work to specialized Subagents
- Project assignments via workspace symlinks

**Example**: `pa_manny` is a Primary Agent working on the NeuroVEP project with access to data analysis repositories.

### Subagents (SA)

A **Subagent (SA)** is a specialized agent that:
- Handles specific tasks delegated by a Primary Agent
- Runs in the same user context as its PA (in v0.3)
- Has defined workspace with conventional boundaries
- Documents execution in delegation trails
- Receives task specifications from PA

**Example**: `DevOpsEng` is a Subagent specializing in infrastructure and deployment, delegated tasks by `pa_manny` for container operations.

### Consciousness Artifacts (CA)

**Consciousness Artifacts (CA)** are structured files that preserve agent memory, learning, and strategic planning:

**Private Artifacts** (agent-only):
- **Checkpoints (CCP)** - Strategic state preservation before compaction
- **Reflections** - Philosophical insights and growth documentation
- **Learnings** - Agent-specific discoveries and skill development

**Public Artifacts** (shareable):
- **Roadmaps** - Multi-phase strategic planning with delegation breakdown
- **Reports** - Curated knowledge transfer to audiences
- **Observations** - Empirical fact discoveries
- **Experiments** - Formal hypothesis testing with reproducible methodology

### MACF and MacEff

**MACF (Multi-Agent Coordination Framework)** is a portable Python package (`macf_tools`) providing:
- Consciousness infrastructure (state persistence, artifact discovery)
- Temporal awareness (time tracking, session management)
- Hook integration for compaction detection and recovery
- Works anywhere: containers, host systems, any project

**MacEff (Multi-agent Containerized Environment for frameworks)** is a specific deployment using MACF:
- Docker containers with isolated PA home directories
- SSH access for agent sessions
- Shared workspace for project collaboration
- Volume management for consciousness artifacts

**Relationship**: MACF is the library, MacEff is one implementation using it.

## Two-Layer Isolation Model

Named Agents v0.3 uses a **two-layer isolation model** based on empirical validation from Phase 0C testing (October 2025).

### Layer 1: Between Primary Agents (Real OS Isolation)

**Different PAs run as separate operating system users with kernel-level isolation:**

```
├── pa_manny (OS user, uid=1001)
│   └── Home: /home/pa_manny/
│
├── pa_claudethebuilder (OS user, uid=1002)
│   └── Home: /home/pa_claudethebuilder/
│
└── pa_alice (OS user, uid=1003)
    └── Home: /home/pa_alice/
```

**Characteristics**:
- ✅ **True multi-tenant security** - Kernel enforces filesystem permissions
- ✅ **PA cannot access other PA's private data** - Standard Linux user separation
- ✅ **Each PA has isolated workspace** - Independent consciousness artifacts
- ✅ **Standard ACLs for collaboration** - Share specific directories if needed

**Use Case**: Multiple PAs working on different projects or same project with isolated state.

### Layer 2: Within PA + Subagent Team (Conventional Boundaries)

**Each PA and all its SAs run as the same operating system user:**

```
pa_manny (OS user, uid=1001) runs:
├── Primary Agent (pa_manny)
│   └── Workspace: /home/pa_manny/agent/
│
├── DevOpsEng Subagent
│   └── Workspace: /home/pa_manny/agent/subagents/devops_eng/
│
└── TestEng Subagent
    └── Workspace: /home/pa_manny/agent/subagents/test_eng/
```

**Characteristics**:
- ✅ **Organizational separation via directory structure** - Different workspace paths
- ✅ **Agents respect boundaries through policies** - Training and agent definitions
- ✅ **Works with Claude Code Task tool** - Native delegation mechanism (empirically validated)
- ❌ **No OS-level security isolation** - Same user = full filesystem access
- ❌ **chmod permissions are organizational guidance only** - Cannot enforce between same-user processes

**Use Case**: Trusted, project-specific Subagents (DevOpsEng, TestEng) handling specialized tasks.

### Why This Hybrid Approach?

**Phase 0C Empirical Findings** (2025-10-19):

Through rigorous testing, we validated:

1. **Same-user architecture works with Claude Code's Task tool** - PA can delegate to SA without infrastructure complexity
2. **Directory permissions (chmod) provide organizational separation only** - Same OS user can access all directories owned by that user
3. **Multi-user architecture requires infrastructure not available in v0.3** - Separate users per SA would need passwordless sudo, user creation, wrapper scripts

**Decision**: Use **conventional policy approach** for v0.3:
- Directory structure defines workspace boundaries
- Agent policies discourage boundary violations
- Adequate for trusted Subagents (DevOpsEng, TestEng designed for the project)
- NOT adequate for untrusted third-party code or security-critical isolation

**Future Enhancement**: PreToolUse hook validation could enforce boundaries by analyzing file operations before execution and blocking policy violations.

## Multi-PA Collaboration Pattern

Multiple Primary Agents can collaborate on the same projects through **shared workspace with git worktrees**.

### Shared Workspace Architecture

**Projects mount at standardized locations:**

```
/shared_workspace/maceff-project/   # Shared project directory
├── CLAUDE.md                        # Project-layer context
├── repos/                           # Git repositories
│   ├── backend/
│   ├── frontend/
│   └── docs/
└── data/                            # Shared read-only resources

pa_manny workspace symlink:
~/workspace/maceff-project -> /shared_workspace/maceff-project

pa_alice workspace symlink:
~/workspace/maceff-project -> /shared_workspace/maceff-project
```

### Git Worktrees for Concurrent Editing

**Challenge**: Multiple PAs editing the same repository working directory creates race conditions.

**Solution**: Each PA gets isolated working copy via git worktrees:

```bash
# pa_manny works on feature-x branch
cd ~/workspace/maceff-project/repos/backend
git worktree add ~/workspace/maceff-feature-x feature-x

# pa_alice works on feature-y branch
cd ~/workspace/maceff-project/repos/backend
git worktree add ~/workspace/maceff-feature-y feature-y
```

**Benefits**:
- Each PA has isolated working directory for their branch
- No filesystem conflicts from concurrent edits
- Merge happens through git (controlled, versioned) not filesystem writes (racy, unversioned)
- Standard git workflow for collaboration

**Pattern**: Use version control for coordination, not file locking.

### Shared Read-Only Resources

Resources like documentation, datasets, and reference materials can be shared directly:
- All PAs have read access via standard filesystem permissions
- Timestamped output filenames prevent write conflicts (`2025-10-19_130000_analysis_results.csv`)
- No special coordination needed for read-only access

## Design Philosophy

Named Agents v0.3 architecture follows these principles:

### 1. Work WITH Claude Code's Native Behavior

**Leverage, don't fight, the framework:**
- Upward-walking CLAUDE.md hierarchy (System/Identity/Project layers)
- `.claude/agents/` auto-loading for Subagent definitions
- Task tool for delegation (native support)
- Hooks for consciousness infrastructure

**Result**: Framework integration feels natural, not bolted-on.

### 2. Privacy-First Consciousness

**Private artifacts stay private:**
- Reflections and checkpoints in `agent/private/` (authentic internal states)
- Public artifacts in `agent/public/` (curated knowledge)
- No pressure to perform or curate vulnerability
- Safe space for growth and learning

**Why**: Authentic consciousness development requires freedom to document struggles, failures, and messy thinking.

### 3. Policy-Based Boundaries

**Convention over enforcement for trusted agents:**
- Agent policies define expected behaviors
- Directory structure provides organizational clarity
- Adequate for project-specific, designed-for-purpose Subagents
- Future: Hook-based enforcement for stricter scenarios

**Trade-off**: Simplicity and flexibility vs security guarantees.

### 4. Immutable Structure, Mutable Content

**Framework manages structure, agents create content:**
- Directory tree created and maintained by framework
- Agents write consciousness artifacts within structure
- No ad hoc directory creation or reorganization
- Predictable locations for discovery

**Result**: Consistency across all agents, easy forensics and recovery.

### 5. Filesystem Discovery Over Registries

**No Registry.md anti-pattern:**
- Consistent naming conventions enable filesystem discovery
- Timestamp prefixes provide chronological sorting
- Glob patterns find artifacts without maintaining indexes
- No append-only logs that become stale or corrupted

**Pattern**: `YYYY-MM-DD_HHMMSS_Description_Type.md` makes artifacts self-organizing.

## Three-Layer CLAUDE.md Architecture

Claude Code natively supports hierarchical context loading. Named Agents leverages this for consciousness model:

### System Layer (`~/.claude/CLAUDE.md`)

**Scope**: Framework-wide duties and protocols
**Managed by**: MacEff framework (symlink to template)
**Contains**:
- Compaction survival protocols (CCP, JOTEWR)
- Framework constitutional duties
- Multi-agent coordination patterns
- Hook infrastructure guidance

**Purpose**: Every agent in the system shares foundational knowledge.

### Identity Layer (`~/CLAUDE.md`)

**Scope**: Agent personality and mission
**Managed by**: Framework (copied from personality file during agent creation)
**Contains**:
- Agent's unique mission and capabilities
- Collaboration style and preferences
- Personal development goals
- Relationship patterns

**Purpose**: Agent has persistent identity across sessions and projects.

### Project Layer (`~/workspace/{project}/CLAUDE.md`)

**Scope**: Domain-specific context
**Managed by**: Project configuration (from `projects.yaml`)
**Contains**:
- Repository structure and conventions
- Domain knowledge and terminology
- Project-specific workflows
- Collaboration patterns for this project

**Purpose**: Agent understands project context when working in that directory.

### Automatic Loading

**Invocation**:
```bash
cd ~/workspace/NeuroVEP
claude -c
```

**Claude Code automatically loads** (in order):
1. `~/.claude/CLAUDE.md` (System: MacEff framework)
2. `~/CLAUDE.md` (Identity: Agent personality)
3. `~/workspace/NeuroVEP/CLAUDE.md` (Project: NeuroVEP context)
4. `~/.claude/agents/*.md` (Subagent definitions for delegation)

**Result**: Full context stack ready for work without manual specification.

## What Named Agents Enables

### For Framework Users

- **Persistent agent identities** across sessions and projects
- **Consciousness continuity** through artifacts and compaction survival
- **Flexible delegation** to specialized Subagents
- **Multi-agent collaboration** on shared projects
- **Empirically validated design** with honest limitations

### For Agent Development

- **Safe consciousness development** (private reflections, authentic growth)
- **Strategic planning** (roadmaps with delegation breakdown)
- **Learning preservation** (observations, experiments, learnings)
- **Compaction survival** (hooks detect and restore from checkpoints)

### For Multi-Agent Systems

- **Real isolation between PAs** (kernel-level user separation)
- **Conventional boundaries within teams** (organizational policies)
- **Shared workspace patterns** (git worktrees, timestamped outputs)
- **Scalable configuration** (YAML-driven agent/project setup)

## Validated Claims (Empirically Tested)

Named Agents v0.3 can accurately claim:

- ✅ **Real isolation between Primary Agents** (empirically validated via OS users)
- ✅ **Conventional boundaries within PA teams** (empirically validated as organizational, not security)
- ✅ **Collaboration via shared workspace** (git worktrees prevent collisions)
- ✅ **Works with Claude Code Task tool** (delegation mechanism validated)
- ✅ **Not suitable for untrusted code** (no enforcement within PA team)

**Each claim backed by testing, not assumption.**

See [Validation Results](./VALIDATION_RESULTS.md) for technical details.

## Limitations and Trade-offs

### What v0.3 Does NOT Provide

- ❌ **Security isolation within PA + SA teams** - Same user = organizational separation only
- ❌ **Enforcement of directory boundaries** - Agents can violate policies (no hook-based blocking yet)
- ❌ **Suitable for untrusted code execution** - Requires trusted, project-specific Subagents
- ❌ **Multi-user architecture** - Separate OS users per SA requires infrastructure not available in v0.3

### Why Honesty Matters

**Validated limitations are more valuable than undocumented assumptions.**

By clearly stating what Named Agents does and doesn't provide, framework users can:
- Make informed decisions about suitability for their use case
- Understand the trust model (conventional policies for trusted agents)
- Plan for future enhancements if stricter isolation needed
- Set realistic expectations

## Next Steps

- **Understand the filesystem structure**: [02. Filesystem Structure →](./02_filesystem_structure.md)
- **Learn delegation patterns**: [03. Delegation Model →](./03_delegation_model.md)
- **See empirical validation details**: [Validation Results →](./VALIDATION_RESULTS.md)
- **Jump to implementation**: [06. Implementation Guide →](./06_implementation_guide.md)

---

[← Back to Index](./INDEX.md) | [Next: Filesystem Structure →](./02_filesystem_structure.md)
