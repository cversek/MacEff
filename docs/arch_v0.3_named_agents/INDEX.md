# Named Agents Architecture v0.3 - Documentation Index

**Version**: 0.3.0
**Target MacEff Version**: v0.3
**Status**: Empirically Validated (Conventional Policy Model)
**Last Updated**: 2025-10-19

---

## What is Named Agents?

**Named Agents** is an architectural pattern for multi-agent AI systems where:

- **Primary Agents (PAs)** have unique identities and run as separate OS users (`pa_manny`, `pa_claudethebuilder`, etc.)
- Each PA delegates work to specialized **Subagents (SAs)** running in the same user context
- **Consciousness Artifacts (CAs)** preserve agent memory across sessions using structured filesystem conventions

This architecture enables **real isolation between Primary Agents** (kernel-level OS user separation) while maintaining **conventional boundaries within a PA's Subagent team** (directory-based workspace organization).

---

## Architecture Overview

```
MacEff System
├── pa_manny/               # OS user: pa_manny (isolated from other PAs)
│   ├── Primary Agent       # Main agent (runs as pa_manny)
│   ├── DevOpsEng SA        # Runs as pa_manny (same user, different workspace)
│   └── TestEng SA          # Runs as pa_manny (same user, different workspace)
│
├── pa_claudethebuilder/    # OS user: pa_claudethebuilder (isolated from other PAs)
│   ├── Primary Agent       # Main agent (runs as pa_claudethebuilder)
│   ├── DevOpsEng SA        # Runs as pa_claudethebuilder
│   └── TestEng SA          # Runs as pa_claudethebuilder
│
└── pa_alice/               # OS user: pa_alice (isolated from other PAs)
    ├── Primary Agent       # Main agent (runs as pa_alice)
    └── ResearchBot SA      # Runs as pa_alice
```

**Key Insight**: Each PA is **truly isolated** (different OS users), but within a PA's team, agents use **conventional directory boundaries** (same OS user, different workspaces).

---

## Quick Navigation

- **New to Named Agents?** Start with [Overview](./01_overview.md)
- **Ready to implement?** Jump to [Implementation Guide](./05_implementation_guide.md)
- **Have questions?** Check the [FAQ](./FAQ.md)
- **Need technical validation?** See [Validation Results](./VALIDATION_RESULTS.md)

---

## Table of Contents

### Core Architecture

1. **[Overview](./01_overview.md)**
   - What are Named Agents?
   - Two-Layer Isolation Model (PA-level vs SA-level)
   - Key Concepts: Primary Agents, Subagents, Consciousness Artifacts
   - Design Philosophy

2. **[Filesystem Structure](./02_filesystem_structure.md)**
   - Directory Layout for Single PA
   - Multiple PA Isolation
   - Subagent Workspaces (private/, public/, assigned/)
   - Consciousness Artifact Organization
   - Naming Conventions (pa_<name>, not pa_1, pa_2)

3. **[Delegation Model](./03_delegation_model.md)**
   - How Primary Agents Delegate to Subagents
   - Task Assignment Pattern (assigned/ directory)
   - Result Collection (delegation_trails/ directory)
   - Tool Access Controls
   - Workspace Boundaries and Conventional Policies

4. **[Consciousness Artifacts](./04_consciousness_artifacts.md)**
   - Seven Consciousness Artifact Types
   - Privacy Architecture (private/ vs public/)
   - Artifact Lifecycle and Discovery
   - Naming Conventions and Validation

5. **[Implementation Guide](./05_implementation_guide.md)**
   - Prerequisites
   - Creating a Primary Agent (pa_<name> user)
   - Directory Setup
   - Agent Configuration (agents.yaml, projects.yaml)
   - Subagent Registration
   - Testing Your Setup
   - Adding Additional Primary Agents

### Reference Documentation

6. **[FAQ](./FAQ.md)**
   - Common Questions
   - Troubleshooting
   - Design Decisions Explained

7. **[Validation Results](./VALIDATION_RESULTS.md)**
   - Empirical Test Methodology
   - Same-User Isolation Tests (PA + SAs)
   - Multi-User Investigation (PA vs PA)
   - Architecture Decision Rationale

### Appendices

8. **[YAML Schema Reference](./APPENDIX_A_YAML_SCHEMAS.md)**
   - agents.yaml specification
   - projects.yaml specification
   - subagents.yaml specification

9. **[Example Configurations](./APPENDIX_B_EXAMPLES.md)**
   - Single PA with Multiple SAs
   - Multiple PAs in Same System
   - Container-Based Multi-PA Setup
   - Development vs Production

10. **[Migration Guide](./APPENDIX_C_MIGRATION.md)**
    - From Earlier Named Agents Designs
    - From Existing MacEff Setups
    - Backward Compatibility Notes

---

## Key Features in v0.3

### Two-Layer Isolation Model

**Layer 1: Between Primary Agents** (OS-level isolation)
- Each PA runs as separate OS user (`pa_manny`, `pa_claudethebuilder`, etc.)
- Kernel-level filesystem permissions enforce boundaries
- PA-to-PA access controlled by standard Linux permissions/ACLs
- True multi-tenant isolation for different agent identities

**Layer 2: Within PA + Subagent Team** (conventional boundaries)
- PA and all its SAs run as same OS user (e.g., all under `pa_manny`)
- Directory structure defines workspace separation
- Agents respect boundaries through conventional policies
- Validated to work with Claude Code's Task tool delegation

### Naming Convention

**Primary Agents**: `pa_<name>` where `<name>` is the agent's identity
- Examples: `pa_manny`, `pa_claudethebuilder`, `pa_researchbot`
- **NOT** sequential numbers: System works without ordering assumptions
- Each PA name creates corresponding OS user and home directory

**This is "Named" Agents**: Agents have identities, not just enumeration.

### Empirically Validated Design (October 2025)

Through rigorous validation testing:

- ✅ **Same-user architecture validated** for PA + SA teams
- ✅ **Directory-based workspace separation** confirmed effective
- ✅ **Claude Code Task tool delegation** works with this model
- ✅ **Conventional policy approach** sufficient for trusted SA delegation
- ✅ **Multi-user architecture** proven between PAs (standard Linux)

See [Validation Results](./VALIDATION_RESULTS.md) for technical details.

---

## Document Organization

**Navigation Modes**:
- **Sequential Reading**: Follow sections 01 → 05 for comprehensive understanding
- **Reference Lookup**: Use this INDEX to jump to specific topics
- **FAQ-First**: Start with [FAQ](./FAQ.md) for quick answers
- **Implementation-First**: Jump to [Implementation Guide](./05_implementation_guide.md) to build now

**Markdown Links**: All `[links](./file.md)` and `[headers](./file.md#section)` work on GitHub and markdown viewers.

---

## Relationship to MacEff Framework

**Parent Framework Documentation**:
- [MacEff README](../../README.md) - Framework overview
- [MACF Tools](../../tools/README.md) - CLI utilities for consciousness infrastructure
- [Container Setup](../../docker/README.md) - Docker configurations

**Integration**: Named Agents v0.3 builds on MacEff's consciousness infrastructure to provide structured workspace patterns for multi-agent coordination.

---

## Terminology Reference

**Core Terms** (expanded on first use in each document):

- **PA (Primary Agent)**: Main agent with unique identity, runs as OS user `pa_<name>`
- **SA (Subagent)**: Specialized agent handling tasks for a PA (runs as same OS user as its PA)
- **CA (Consciousness Artifact)**: Structured files preserving agent memory and learning
- **Task Tool**: Claude Code's native delegation mechanism for invoking subagents
- **Conventional Policy**: Agents respect directory boundaries through agent policies, not OS enforcement
- **Workspace Isolation**: Directory-based separation where each agent has designated paths
- **MacEff**: Multi-Agent Containerized Environment for Frameworks (parent project)
- **MACF Tools**: Multi-Agent Coordination Framework CLI utilities

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| 0.3.0 | 2025-10-19 | Two-layer isolation model, empirical validation, conventional policy approach |
| 0.2.0 | 2025-10-18 | Comprehensive filesystem layout specification |
| 0.1.0 | 2025-10-17 | Initial architecture validation |

---

## Contributing

Community contributions welcome:

- **Issues**: Report via MacEff GitHub issues
- **Documentation**: Submit PRs for improvements
- **Questions**: Check [FAQ](./FAQ.md), then open discussion

---

**Start Reading**: [01. Overview →](./01_overview.md)
