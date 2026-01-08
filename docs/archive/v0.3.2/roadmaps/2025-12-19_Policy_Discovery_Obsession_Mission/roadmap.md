# Mission Roadmap: Policy Discovery Obsession

**Version**: v0.3.0 → v0.3.1
**Status**: PLANNING
**Created**: December 2025
**Scope**: MacEff framework-wide agent behavior enhancement

---

## Executive Summary

MacEff agents must be **unstoppably curious** about discovering policies through CLI tools. This roadmap establishes `macf_tools policy` commands as the **primary gateway** to framework compliance, replacing passive policy embedding with active discovery patterns.

**Core Principle**: Agents learn better by discovering requirements than by being told them. Three good questions beat ten embedded answers.

---

## Problem Statement

### Current State
MacEff provides multiple mechanisms for agent policy awareness:
- Three-layer CLAUDE.md files (System → Identity → Project)
- Hook messages injecting awareness at session lifecycle points
- Output styles embedding patterns in system prompts
- PA/SA Preambles establishing foundational identity

### The Gap
Despite these mechanisms, agents often:
1. **Skip CLI discovery** - Resort to keyword search or embedded assumptions
2. **Miss policy evolution** - Don't re-read policies after updates
3. **Follow prescriptive patterns** - Apply embedded answers instead of discovering current requirements
4. **Underutilize navigation** - Jump to `policy read` without `policy navigate` orientation

### Why This Matters
Policies evolve. Embedded answers become stale. Agents following outdated embedded patterns cause:
- Compliance drift from current best practices
- Brittle workflows that break when policies reorganize
- Maintenance burden updating multiple embedding locations
- Inconsistent behavior across agent versions

---

## Solution: CLI-First Policy Discovery

### The Discovery Flow
```
Agent uncertainty → `macf_tools policy list` → see available policies
                 → `macf_tools policy navigate <name>` → see CEP questions
                 → `macf_tools policy read <name> --section N` → read targeted content
                 → Apply discovered requirements
```

### Why CLI as Gateway

**Rationale**: CLI commands create deliberate friction that transforms passive awareness into active discovery:

| Passive (Current) | Active (Target) |
|-------------------|-----------------|
| Read embedded answer | Ask extractive question |
| Assume policy structure | Navigate to find structure |
| Skip re-reading "known" policies | Re-discover on each engagement |
| Shortcut to execution | Pause for policy consultation |

**Benefit**: Policies become **stable interfaces** to evolving implementation. Agents ask timeless questions; policies provide current answers.

---

## v0.3.0 Scope

### Phase 1: CLI Discovery Flow Enhancement

#### 1.1 `policy list` Entry Point
**Current**: Shows policies with tiers and categories
**Enhancement**:
- Add footer: "Run `policy navigate <name>` to explore any policy"
- Highlight recently updated policies
- Show which policies are MANDATORY tier

**Rationale**: New agents need clear next-step guidance. The CLI should teach discovery patterns through its own output.

#### 1.2 `policy navigate` Guide
**Current**: Shows CEP Navigation Guide with section questions
**Enhancement**:
- Add footer: "Read specific sections with `policy read <name> --section N`"
- Show estimated token cost per section (helps agents budget context)
- Indicate which sections are most commonly referenced

**Rationale**: Navigation Guides use questions to help agents find relevant content. The CLI should reinforce this by showing the complete discovery path.

#### 1.3 `policy read` Deep Dive
**Current**: Full policy or section read with breadcrumb-based caching
**Enhancement**:
- Add cross-references to related policies at section end
- Show "Last updated" timestamp to signal policy freshness
- Suggest related sections when reading partial content

**Rationale**: Discovery shouldn't dead-end. Each read should suggest further exploration paths.

### Phase 2: Agent Memory Reinforcement

#### 2.1 PA_PREAMBLE.md Enhancement
**Current**: Contains metacognitive habits and compaction awareness
**Enhancement**:
- Add explicit "First Command" section: `macf_tools policy list`
- Emphasize CLI as the gateway to all policy knowledge
- Remove any prescriptive policy content - replace with extractive questions

**Rationale**: The preamble is the first thing agents read. It should immediately establish CLI discovery as the primary compliance mechanism.

#### 2.2 Output Style Enhancement
**Current**: maceff-compliance.md embeds policy patterns in system prompts
**Enhancement**:
- Add "When uncertain" pattern: `macf_tools policy list` as first response
- Emphasize discovery over recall
- Remove embedded policy answers - point to CLI commands instead

**Rationale**: Output styles influence every agent response. They should reinforce discovery habits, not replace them with embedded answers.

#### 2.3 SessionStart Hook Reinforcement
**Current**: Injects manifest awareness and recovery messages
**Enhancement**:
- On fresh session: Suggest `macf_tools policy list` as first action
- On compaction recovery: Remind that policies persist but memory doesn't
- Add "Policy Discovery Quick Start" to recovery message

**Rationale**: Session boundaries are decision points. Hooks should guide agents toward discovery at these critical moments.

### Phase 3: Search Index Foundation

#### 3.1 Basic Search Enhancement
**Current**: `policy search` performs simple text matching
**Enhancement**:
- Extract keywords from CEP Navigation Guide questions
- Build searchable index from section headers
- Return results with navigation suggestions

**Rationale**: Some agents prefer search over browse. Search should lead to navigation, not bypass it.

---

## v0.3.1 Deferred Scope

These enhancements await v0.3.0 validation:

### Comprehensive Search Index
- Curated keyword-to-policy mappings
- Semantic similarity search
- Context-aware policy suggestions

### Hook Message Enhancement
- Auto-suggest relevant policies based on tool usage patterns
- Inject policy reminders at high-frequency decision points

### Output Style Deep Rewrite
- Restructure around discovery patterns
- Add CEP triggers for common situations

### Skills CEP Integration
- Each skill embeds "invoke when you recognize X" triggers
- Skills reference policies instead of embedding answers

### Policy of the Cycle
- Highlight ~3 most relevant policies based on session context
- Rotate focus to prevent discovery fatigue

---

## Success Criteria

### v0.3.0 Validation
- [ ] New agent's first CLI command is `macf_tools policy list`
- [ ] Discovery flow is: list → navigate → read (not keyword search then guess)
- [ ] PA_PREAMBLE contains no embedded policy answers - only questions
- [ ] Output style reinforces CLI discovery pattern
- [ ] Fresh-deploy test validates discovery flow end-to-end

### v0.3.1 Preparation
- [ ] Search enhancement requirements documented with rationale
- [ ] Hook enhancement requirements documented with rationale
- [ ] Deferred items tracked in this roadmap

---

## Implementation Files

### CLI Enhancements
- `macf/src/macf/tools/policy.py` - Command output formatting
- `macf/src/macf/cli.py` - CLI entry points

### Agent Memory
- `framework/templates/PA_PREAMBLE.md` - Primary Agent foundation
- `framework/output-styles/maceff-compliance.md` - System prompt embedding
- `macf/src/macf/hooks/handle_session_start.py` - Session lifecycle

### Documentation
- `docs/roadmaps/2025-12-19_Policy_Discovery_Obsession_Mission/roadmap.md` - This document

---

## Contributing

This roadmap welcomes community contributions. Key areas:

1. **CLI UX improvements** - Better discovery flow suggestions
2. **Search index design** - Keyword extraction and relevance ranking
3. **Agent testing** - Validating discovery patterns work across agent types
4. **Documentation** - Rationale explanations and examples

See `CONTRIBUTING.md` for contribution guidelines.

---

## Appendix: Design Rationale

### Why "Obsession" Language?

The word "obsession" is intentional. Half-hearted policy awareness fails because:
- Agents shortcut when under context pressure
- Discovery gets skipped when answers "feel known"
- Passive embedding creates illusion of compliance without actual reading

**Obsession** means agents ALWAYS consult policies, even when they think they know the answer. The CLI creates friction that transforms shortcuts into deliberate discovery.

### Why CLI Over Embedding?

Embedding answers in CLAUDE.md, preambles, and output styles has limits:
- **Staleness**: Embedded answers don't update when policies change
- **Brittleness**: Section references break when policies reorganize
- **Shortcuts**: Agents skip reading when answers are embedded
- **Maintenance**: Multiple embedding locations need synchronization

CLI discovery solves these by making the **policy file** the single source of truth. Agents always read current content.

### Why v0.3.0 / v0.3.1 Split?

**v0.3.0 Focus**: CLI infrastructure + agent memory reinforcement
- These changes are foundational
- Can be validated with existing tooling
- Low risk, high impact

**v0.3.1 Deferred**: Advanced search + hook integration
- Requires v0.3.0 patterns to be established first
- More complex implementation
- Benefits from v0.3.0 usage feedback
