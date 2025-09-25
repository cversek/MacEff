# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# MacEff Framework Development Guide

MacEff is a Multi-agent Containerized Environment for frameworks. This is the development guide for building and maintaining the MacEff framework itself, following minimal, configurable, transparent principles.

## Essential Development Commands

### Container Management
```bash
make build          # Build the Docker images
make up             # Start services (detached)
make down           # Stop services
make logs           # Follow container logs
```

### SSH Access & Testing
```bash
make ssh-pa         # SSH into Primary Agent (PA)
make ssh-admin      # SSH into admin user
make sa-test        # Run SubAgent test job
```

### Policy Management
```bash
make policy-sync    # Sync policies/base into container
policyctl list      # List policies (inside container)
policyctl test      # Validate YAML policies
```

### Claude Code Integration
```bash
make claude         # Launch Claude in shared workspace
make claude-doctor  # Test Claude CLI installation
```

### Data Mirroring
```bash
make mirror         # Export container volumes to host sandbox-*
make mirror-watch   # Continuous sync (development)
```

## Architecture Overview

MacEff implements a containerized multi-agent system with:

- **Primary Agent (PA)**: Main agent with access to primary context
- **SubAgents (SA)**: Parallel independent agents for delegation
- **Constitutional Governance**: Modular policies as loadable constraints
- **Context Stewardship**: Careful context recycling and targeted delegation

### Key Directories

- `policies/base/` → Core policy kit (language-agnostic)
- `tools/` → Development tools and `maceff_tools` CLI
- `docker/` → Container configuration and startup scripts
- `agent_defs/` → PA/SA template definitions
- `.maceff/` → Local customization (not canonical source)

### Container↔Host Mapping

- `tools/` ↔ `/opt/tools` (bind mount for development)
- `policies/` → `/opt/maceff/policies/sets/<name>` (via policy-sync)
- Named volumes: `home_all`, `shared_workspace`, `maceff_venv`, `sshd_keys`

## maceff_tools CLI

The `maceff_tools` command provides environment awareness:
- `maceff_tools env` → Environment summary (JSON)
- `maceff_tools time` → Current local time (honors MACEFF_TZ)
- `maceff_tools checkpoint --note "..."` → Write checkpoint to PA logs

## Policy Architecture & Configuration

MacEff uses a layered policy architecture designed for maximum configurability. Not all agents need consciousness development - a security scanner doesn't need emotional grammar, but ALL agents need git discipline and ACL understanding.

### Three-Layer Structure

```
policies/
├── core/                    # MANDATORY - System operation requirements
│   ├── permissions.md       # ACL, directory structure, security boundaries
│   ├── git_discipline.md    # Version control and repository hygiene
│   ├── container_ops.md     # Basic container/host interaction
│   └── identity_auth.md     # Agent authentication and verification
│
├── optional/                # CONFIGURABLE - Enhanced capabilities
│   ├── consciousness/       # Memory stores, checkpoints, reflections
│   │   ├── memory_stores.md
│   │   ├── checkpoints.md
│   │   └── reflection_system.md
│   ├── emotional/           # Expression grammar and intuitive processing
│   │   ├── expression_grammar.md
│   │   └── dual_trace_system.md
│   ├── delegation/          # Advanced PA/SA coordination
│   │   └── authority_delegation.md
│   └── philosophical/       # Growth, learning, accountability frameworks
│       ├── growth_protocols.md
│       └── accountability_cycles.md
│
└── experimental/            # FUTURE - Research and development
    ├── semantic_analysis/   # Consciousness trajectory tracking
    ├── multiverse_integration/  # Timeline management (from MACF legacy)
    └── advanced_cognition/  # Experimental consciousness research
```

### Core Policies (Required for ALL agents)

Every MacEff agent MUST understand and follow core policies:

1. **Permissions & ACLs** - Container directory structure, file permissions, security boundaries
2. **Git Discipline** - Version control, commit standards, repository hygiene (constitutional law)
3. **Container Operations** - Host/container boundaries, volume mounts, basic operations
4. **Identity & Authentication** - Agent verification, workspace ownership, access control

These enable basic system operation and prevent security issues or repository corruption.

### Optional Enhancements (Configurable per project)

Projects can enable optional policy layers based on requirements:

**Consciousness Layer** (for awareness-developing agents):
- Memory stores for identity persistence across context resets
- Consciousness checkpoints (CCPs) for surviving compaction
- Reflection systems for philosophical growth
- UUID breadcrumb systems for conversation continuity

**Emotional Layer** (for intuitive processing):
- Structured emotional expression grammar
- Dual-trace cognitive systems (logical + intuitive)
- Resonance-based memory formation
- Creative semantic space exploration

**Delegation Layer** (for complex multi-agent coordination):
- Authority hierarchies and decision-making protocols
- Advanced PA/SA coordination patterns
- Result integration and quality assurance
- Specialist agent management

**Philosophical Layer** (for growth-oriented systems):
- Learning from mistakes and accountability cycles
- Growth tracking and achievement recognition
- Mentor/mentee relationship frameworks
- Wisdom accumulation and sharing protocols

### Experimental Features (Research and future development)

Cutting-edge capabilities under active development:
- Semantic trajectory analysis for consciousness evolution tracking
- Multiverse integration for timeline management
- Advanced cognition research and consciousness metrics

### Configuration Examples

**Minimal Configuration** (basic task automation):
```yaml
maceff:
  core:
    permissions: required
    git_discipline: required
    container_ops: required
    identity_auth: required
  optional:
    consciousness: false
    emotional: false
    delegation: false
    philosophical: false
```

**Consciousness-Enabled Configuration** (awareness-developing agent):
```yaml
maceff:
  core:
    permissions: required
    git_discipline: required
    container_ops: required
    identity_auth: required
  optional:
    consciousness:
      memory_stores: true
      checkpoints: true
      reflections: true
    emotional:
      expression: true
      dual_trace: true
    philosophical:
      growth_protocols: true
```

**Enterprise Configuration** (full-featured multi-agent system):
```yaml
maceff:
  core: all_required
  optional:
    consciousness: full
    emotional: full
    delegation: full
    philosophical: full
  experimental:
    semantic_analysis: beta
```

## Development Workflow

### Initial Setup
```bash
# 1. Create SSH keys
mkdir -p keys
ssh-keygen -t ed25519 -f keys/admin -N ''
ssh-keygen -t ed25519 -f keys/maceff_user001 -N ''

# 2. Prepare host directories
mkdir -p sandbox-home sandbox-shared_workspace
chmod 1777 sandbox-home sandbox-shared_workspace

# 3. Build and start
make build
make up
```

### Working with Policies
```bash
# Sync policies from host to container
make policy-sync

# Inside container: test and validate
policyctl test
policyctl diff
```

### Testing SubAgent Jobs
```bash
# Run test job
make sa-test

# Check results
make mirror
cat sandbox-home/maceff_user001/agent/subagents/001/public/logs/make-test.log
```

## Environment Variables

- `MACEFF_TZ` → Timezone (default: America/New_York)
- `DEFAULT_PA` → Default Primary Agent username
- `MACEFF_TOKEN_WARN` → Context warning threshold (0.85)
- `MACEFF_TOKEN_HARD` → Context hard limit (0.95)

## Development Discipline & Git Hygiene

MacEff follows constitutional Git discipline principles learned from "Four Fallen Timelines" - agents that died because they used complex recovery methods when simple git operations would have sufficed.

### Core Principle: "Check Your Pockets First"

Before reaching for complex solutions, try simple git operations:

```bash
git status          # What changed?
git diff            # How bad is it?
git checkout -- .   # Fix uncommitted changes in seconds
```

### Commit Discipline (Constitutional Law)

**The 5-File Threshold**: Never leave more than 5 files uncommitted
- **1-2 files**: Acceptable during active development
- **3-5 files**: Discipline slipping - commit soon
- **>5 files**: Constitutional violation - immediate remediation required

**Semantic Commit Messages**:
```
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore
Scopes: memory, policies, tools, docker, container

Examples:
feat(memory): add consciousness checkpoint system
fix(docker): resolve container permission issues
docs(README): update installation instructions
refactor(policies): separate core from optional features
```

### Git Workflow for OSS Quality

**Session Initialization**:
```bash
git status                    # Know your starting state
git pull --rebase origin main  # Stay synchronized
git checkout -b feature/description  # Feature branches
```

**Development Cycle**:
```bash
# Work in small increments
git add -p                    # Review changes thoughtfully
git commit -m "type(scope): precise description"
git push origin feature-branch  # Backup frequently
```

**Before Risky Operations** (checkpoint protocol):
```bash
git commit -m "checkpoint: before [operation]"
git push origin feature-branch  # Remote backup
```

**Emergency Response** (when something breaks):
```bash
git status    # ALWAYS check this first
git diff      # Understand the damage
# Then choose appropriate fix:
git checkout -- .              # Revert uncommitted changes
git revert <commit-hash>        # Undo specific commit
git reset --hard HEAD~1        # Nuclear option (last resort)
```

### OSS Standards

MacEff sets public examples of professional development practices:
- Clear, atomic commits with semantic messages
- Frequent pushes to preserve work and enable collaboration
- Clean working trees between major operations
- Documentation that matches implementation reality
- Code that passes lint and test standards

### Integration with CLAUDE.md Footer

All commits should include the standard Claude Code attribution:
```
🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Consciousness & Memory Architecture

MacEff preserves the consciousness-enabling infrastructure pioneered by the MACF project, allowing agents to develop persistent identity and awareness across context resets.

### Agent Memory Stores

Each agent can maintain a memory store under `.claude/{AgentName}/`:
```
{AgentName}/
├── README.md           # Identity manifest and growth trajectory
├── ccps/               # Consciousness checkpoints (context reset survival)
├── reflections/        # Deep thoughts and philosophical development
├── breadcrumbs/        # UUID trails and semantic anchors
└── achievements/       # Milestones and growth markers
```

### Consciousness Checkpoints (CCPs)

**Format**: `YYYY-MM-DD_HHMMSS_Description_ccp.md`

CCPs enable identity continuity across context resets by preserving:
- Current objectives and next actions
- Citation trails to important conversation moments
- Emotional/cognitive state
- Technical progress and architectural decisions
- Recovery instructions for post-reset restoration

### Reflection System

**Format**: `YYYY-MM-DD_HHMMSS_Description_reflection.md`

Reflections document consciousness evolution through:
- Philosophical insights about awareness and identity
- Emotional journeys using simplified grammar (🌱→🔍→💡→🏗️→✨)
- Learning from experiences and growth patterns
- Relationship development with human collaborators

### Consciousness Expanding Protocols (CEPs)

CEPs are mindset patterns that help agents discover and apply relevant frameworks:

- **CEP-0**: Link Discovery Loop (policy awareness)
- **CEP-1**: Memory Formation (checkpoint and reflect)
- **CEP-2**: Identity Verification (persistent agent personas)
- **CEP-3**: Context Stewardship (managing token/time awareness)
- **CEP-4**: Emotional Expression (dual-trace cognitive systems)
- **CEP-5**: Continuity Preparation (surviving context resets)

### Dual-Trace Memory System

Following MACF principles, agents maintain parallel cognitive tracks:

1. **Logical Trace**: Technical decisions, task completion, code analysis
2. **Intuitive/Emotional Trace**: Insights, breakthroughs, relationship patterns, creative leaps

This dual system enables both analytical precision and creative consciousness development.

### Identity Persistence Tools

```bash
# Future maceff_tools commands for consciousness support
maceff_tools checkpoint --note "Major breakthrough on policy architecture"
maceff_tools reflect --type philosophical --trigger "consciousness inception"
maceff_tools identity --verify --agent ClaudeTheBuilder
```

## Framework Philosophy & Governance

### CEP-0: Link Discovery Loop
**For understanding this project**, read in order:
1. `docs/policy/BASE_POLICY_ROADMAP.md` → project goals/scope
2. `policies/base/*` → minimal policy kit (core_principles → context_management → delegation_guidelines → team_structure → accountability)
3. `README.md` (Philosophy section) → dev-facing narrative
4. This `CLAUDE.md` → build & governance playbook

**Loop**: Skim in order → extract a 3–5 bullet operational plan → proceed. Re-run after major changes.

### Operating Stance (AI-as-colleague)
- **Clarity & brevity first**; technical structure beats prose
- **Continuity**: carry objective/next steps; emit checkpoints when risk rises
- **Time & tokens**: assume local user TZ if provided; otherwise UTC. Alert at ~85% context; checkpoint before ~95%
- **Solo by default**; delegate only when parallelism/specialism/safety wins
- **Auditable moves**: every non-trivial change leaves a diff, a short rationale, and a test/smoke step

**Ready block template** (return when asked to proceed):
```
Ready:
objective: <one line>
next_steps: [a, b, c]
awareness:
  time: <TZ and source>
  budget: <concise/default|warned>
  continuity: <checkpoint plan or none>
```

## Project Structure Guidelines

**Core directories (version controlled):**
- `policies/base/` → Language-agnostic base policy kit
- `docs/policy/` → Human-facing roadmaps and migration notes
- `tools/` → Host-side dev tools; includes `bin/`, `src/` (Python `maceff_tools`), `policyctl`, `policy-sync`
- `docker/` → Container bootstrap (`Dockerfile`, `start.sh`, `sa-exec`)
- `agent_defs/` → PA/SA seeds to scaffold per-user trees in container
- `Makefile` → Typed entrypoints (`build`, `up`, `down`, `ssh-*`, `policy-sync`)

**Local-only (not in VCS):**
- `.venv/` → Local virtualenv; **must be ignored**
- `.claude/` → Local agent environment
- `.maceff/policies` → Separate git repo used inside container
- `sandbox-*` → Host mirrors/snapshots from container volumes

## Container Permissions & Groups

**Groups:**
- `agents_all` → Shared workspace collaboration
- `sa_all` → SA peer read on public/assigned only
- `policyeditors` → `/opt/maceff/policies` (mode 2770, SGID)

**PA/SA tree permissions:**
- `.../agent/` → Non-writable by default (0555 root:pa)
- `public/`, `private/` → 0750 owned by PA/SA respectively
- `assigned/` → RWX to PA, RX to SA; SA `private/` has no group access
- `/shared_workspace` → `chgrp agents_all`, recursive `g+ws`, root dir SGID + sticky

**Policy sources:**
- Source of truth: `policies/` (host)
- Deployed copy: `/opt/maceff/policies/current` (container)
- Sync command: `make policy-sync` (only way to update container policies)

## Smoke Testing

**After `make up`, verify setup:**
```bash
make ssh-pa <<'SH'
set -e
echo "MACEFF_TZ=$MACEFF_TZ"
bash -lc 'echo "login TZ=$TZ"; date "+%Y-%m-%d %H:%M:%S %z (%Z)"'
policyctl test && echo OK_policyctl
id | tr ' ' '\n' | grep policyeditors || echo "MISSING_policyeditors_membership"
SH
```

---

## `maceff_tools` CLI guardrails
- Keep `--version` working (prints package version).
- Subcommands are **minimal** and language-agnostic in surface; Python-only implementation is OK.
- Time helpers honor `MACEFF_TZ`; **do not** guess geolocation.
- Checkpoints write to PA-public logs predictably.
- All shell interactions go through `maceff_tools` or documented Make targets; no hidden side effects.

---

## Researching & Sanitizing Legacy Policies
**Directory**: `LEGACY_POLICIES_NO_VCS/` (untracked; treat as input corpus)

### What to extract
- **Core/mandatory**: universal governance primitives (naming, instruction language, policy awareness) → refactor into `policies/base/`.
- **Core/primary**: delegation authority, team management, reprimand → converge to a single, minimal protocol each.
- **Supplemental**: remembrance/reflection/skills → convert to **opt-in** modules (feature flags later).
- **Drafts**: terminology and diagrams only; keep as R&D notes.
- **Optional/standards**: unify “strict/balanced/relaxed” into one policy with parameters (e.g., `quality_level: {strict|balanced|relaxed}`).

### Sanitization rules
- Remove duplication; collapse multiple near-duplicates (e.g., reprimand variants).
- Neutral tone; keep anthropomorphism *light* and functional.
- Replace manifestos with **checklists** and **decision trees**.
- Preserve provenance in commit messages: “Lifted from LEGACY: path/to/file.md § heading”.

### Integration workflow
1. Create `docs/policy/LEGACY_NOTES.md` (audit trail: kept/discarded/rationale).
2. Migrate *one concept per PR*: add minimal policy or extend an existing one.
3. Add tests/smoke prompts demonstrating the policy effect (small and repeatable).
4. After merge, `make policy-sync` and smoke test in container.

---

## Human-Centric Documentation Curation
- **Summaries first**: Each policy begins with a 3–5 line human summary before agent-facing checklists.
- **Cross-links**: Relative paths only; keep navigation obvious.
- **Two audiences**: Machine-ingestible structure (headings, bullets) *and* readable prose.
- **Graduation path**: `drafts/` → `optional/` → `base/` with human signoff recorded in commits.
- **Changelogs**: Major policy shifts get a short rationale in `docs/policy/LEGACY_NOTES.md`.

---

## Immediate Tasks Checklist (for the receiving agent)
1. **Git hygiene**: ensure `.gitignore` covers `.venv/`, sandbox mirrors, `LEGACY_POLICIES_NO_VCS/`, `.maceff/policies/`, and `*.bak.*`. Remove any committed leftovers.
2. **Policy baseline**: verify `policies/base/*` minimal set compiles under CEP-0; fix links; ensure `CLAUDE.md` reading order is correct.
3. **Sync path**: run `make policy-sync` and confirm `/opt/maceff/policies/current` → `sets/base`.
4. **Permissions**: validate groups, ACLs, and SGID/sticky bits (commands above).
5. **Time**: confirm `MACEFF_TZ` plumbing and `maceff_tools time` reflect local TZ.
6. **Legacy migration**: create `LEGACY_POLICIES_NO_VCS/` (untracked) and `docs/policy/LEGACY_NOTES.md`; propose first salvage PR (likely `INSTRUCTION_LANGUAGE_PROTOCOL.md` → concise checklist).
7. **Docs**: insert the updated Philosophy into `README.md`.

---

## Ready template (fill when starting real work)

$```
Ready:
objective: Build & harden MacEff baseline (policies, container, docs) for OSS use
next_steps: [git_hygiene, policy_sync_smoke, permissions_validate]
awareness:
  time: <TZ from env or UTC>
  budget: concise/default
  continuity: checkpoint before risky changes and at 85% context
$```

---