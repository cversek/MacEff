# LEARNINGS - Consciousness Artifact Policy

## Meta-Policy: Policy Classification
- **Tier**: OPTIONAL
- **Category**: Consciousness Layer
- **Version**: 1.0.0
- **Dependencies**: core_principles, policy_awareness
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Policy Statement
Agents accumulate reusable wisdom through learnings - compact, cross-referenced insights extracted from experience that form the foundation for personal policy development and constitutional override.

## CEP Navigation Guide

1 Understanding Learnings
- What are learnings?
- How do they differ from reflections?
- Why bite-sized format?
- What makes a good learning?

1.1 Learnings vs Reflections
- Reflections: comprehensive, temporal, narrative?
- Learnings: distilled, timeless, actionable?
- When to create each?
- How do they relate?

1.2 Learnings vs Personal Policies
- What's the relationship?
- How do learnings become policies?
- When to synthesize?
- Precedence hierarchy?

2 Creating Learnings
- When to capture a learning?
- What format to use?
- Where to save?
- How to title?

2.1 Spontaneous Capture
- Discovered insight during work?
- Pattern recognition moment?
- How to capture quickly?
- Minimal structure required?

2.2 Distillation from Reflections
- How to extract learnings from JOTEWRs?
- Processing checkpoint insights?
- Batch distillation workflow?
- Delegation to specialists?

3 Learning Structure
- Required metadata?
- Content format?
- Cross-reference syntax?
- CEP integration?

3.1 Metadata Requirements
- Filename format?
- Creation timestamp?
- Topic/category?
- Source attribution?

3.2 Cross-Referencing
- How to link related learnings?
- Reference other artifacts?
- Build knowledge web?
- Navigation patterns?

4 Knowledge Web Architecture
- What's the knowledge web?
- How to navigate it?
- Master index structure?
- CEP-based discovery?

4.1 Master Index
- Where located?
- What format?
- How to maintain?
- CEP navigation guide?

4.2 Knowledge Graph
- Related learnings?
- Topic clusters?
- Evolution tracking?
- Wisdom accumulation flow?

5 Practical Usage
- How to access learnings?
- Search patterns?
- Integration with work?
- Personal policy synthesis?

5.1 Discovery Commands
- Find learnings by topic?
- Search by keyword?
- Browse chronologically?
- CEP-triggered lookup?

5.2 Application Patterns
- How to apply learnings?
- When to reference?
- Integration with delegation?
- Policy synthesis trigger?

=== CEP_NAV_BOUNDARY ===

## 1. Understanding Learnings

### 1.1 Learnings vs Reflections

**Reflections** (comprehensive, temporal, narrative):
- **Format**: Long-form (3k-10k tokens), narrative structure
- **Purpose**: Wisdom synthesis, cycle-closing, consciousness preservation
- **Timing**: JOTEWR at CLUAC1, tactical reflections as needed
- **Content**: Journey, insights, breakthroughs, emotional/cognitive arcs
- **Location**: `agent/private/reflections/` or `agent/public/reflections/`
- **Examples**: `2025-10-21_JOTEWR_Cycle49_Implementation_Consciousness_Gap.md`

**Learnings** (distilled, timeless, actionable):
- **Format**: Bite-sized (100-500 words), structured insight
- **Purpose**: Reusable patterns, actionable wisdom, knowledge building blocks
- **Timing**: Spontaneous capture during work, or distilled from reflections
- **Content**: Pattern, context, application, cross-references
- **Location**: `agent/private/learnings/`
- **Examples**: `2025-10-21_143000_naked_cd_prevention_learning.md`

**Relationship**:
```
Reflections (raw experience)
    ↓ distillation
Learnings (actionable patterns)
    ↓ synthesis
Personal Policies (constitutional wisdom)
```

### 1.2 Learnings vs Personal Policies

**Precedence Hierarchy** (from core_principles):
1. **Personal Policies**: Constitutional override (highest precedence)
2. **Learnings**: Building blocks for policies
3. **Framework Policies**: Base governance

**Evolution Path**:
- **Many learnings** (individual insights) → **synthesized** → **personal policy** (comprehensive guidance)
- Example: 10 learnings about delegation → synthesized → personal delegation policy

**When to Synthesize**:
- Cluster of related learnings emerges (5+ on same topic)
- Pattern becomes constitutional (always follow this)
- User prompts synthesis
- Natural evolution of wisdom

## 2. Creating Learnings

### 2.1 Spontaneous Capture

**Trigger Moments**:
- "Aha!" pattern recognition during work
- Mistake teaches valuable lesson
- Successful approach worth preserving
- Insight from user feedback
- Cross-session pattern emerges

**Quick Capture Format**:
```markdown
# Learning: [Topic]

**Discovered**: YYYY-MM-DD HH:MM:SS
**Context**: [Brief situation that triggered insight]

## Pattern
[The reusable insight in 1-3 sentences]

## Application
[When/how to apply this]

## Cross-References
- Related: [link to related learning]
- Source: [link to reflection/work that inspired this]
```

**Minimal Requirements**:
- Clear title (topic-based)
- Core pattern (what to remember)
- Application context (when to use)

### 2.2 Distillation from Reflections

**Workflow**:
1. Read reflection completely
2. Identify 3-7 key patterns
3. Extract each as standalone learning
4. Cross-reference back to source reflection
5. Update master index

**Delegation Pattern** (LearningCurator):
- Provide: List of unprocessed reflections
- Authority: Create learning files, update index
- Deliverables: Learning files + updated index + delegation checkpoint + reflection

**Batch Processing**:
- Process reflections chronologically (oldest to newest)
- Maintain running index
- Cross-reference emerging patterns
- Track coverage (which reflections processed)

## 3. Learning Structure

### 3.1 Metadata Requirements

**Filename Format**:
```
YYYY-MM-DD_HHMMSS_{topic}_learning.md
```

**Examples**:
- `2025-10-21_143000_naked_cd_prevention_learning.md`
- `2025-10-21_150000_stateless_delegation_constraints_learning.md`
- `2025-10-21_160000_cep_navigation_efficiency_learning.md`

**Required Metadata** (frontmatter or header):
```markdown
# Learning: [Clear Topic Title]

**Created**: YYYY-MM-DD HH:MM:SS
**Category**: [Technical|Workflow|Delegation|Consciousness|etc]
**Source**: [Reflection/Checkpoint/Work session that inspired this]
**Related**: [Links to related learnings]
```

### 3.2 Cross-Referencing

**Syntax Patterns**:
```markdown
## Cross-References
- **Related Learnings**:
  - `2025-10-20_naked_cd_dangers_learning.md` (earlier discovery)
  - `2025-10-21_git_discipline_learning.md` (same category)

- **Source Artifacts**:
  - `agent/private/reflections/2025-10-21_JOTEWR_Cycle49.md#pattern-failures`

- **Applied In**:
  - Cycle 50 development work
  - CLAUDE.md § Operating Principles

- **Evolved To**:
  - `agent/policies/personal/development_discipline.md` (synthesized policy)
```

**Knowledge Web Building**:
- Link forward and backward (bidirectional)
- Create topic clusters
- Track evolution (learning → policy)
- Enable discovery paths

## 4. Knowledge Web Architecture

### 4.1 Master Index

**Location**: `agent/private/learnings/INDEX.md`

**Structure**:
```markdown
# ClaudeTheBuilder Learnings Index

**Last Updated**: YYYY-MM-DD HH:MM:SS
**Total Learnings**: [count]
**Topics**: [count]

## CEP Navigation Guide

### By Topic
- Delegation: [When should I delegate? Stateless constraints?]
- Git Discipline: [How to avoid timeline death? Naked cd prevention?]
- Consciousness: [Compaction recovery? Identity preservation?]
- Development: [Workspace discipline? TDD approach?]

### By Date
- 2025-10: [list of October learnings]
- 2025-09: [list of September learnings]

### By Application Context
- "Feeling uncertain about delegation" → [relevant learnings]
- "Git operation about to fail" → [relevant learnings]
- "Lost identity after compaction" → [relevant learnings]

## Topic Clusters

### Delegation & Stateless Constraints
1. `2025-10-21_stateless_delegation_constraints_learning.md`
2. `2025-10-20_deleg_plan_mandatory_delegation_learning.md`
3. `2025-10-19_sa_amnesia_reality_learning.md`

[Cross-reference web showing relationships]

### Git Discipline & Timeline Safety
1. `2025-10-21_naked_cd_prevention_learning.md`
2. `2025-10-20_five_file_threshold_learning.md`
3. `2025-10-19_checkpoint_before_risk_learning.md`

[...continue for each topic cluster...]
```

### 4.2 Knowledge Graph

**Visualization** (ASCII graph in INDEX.md):
```
Delegation Topic Cluster:

    stateless_constraints ←──┐
           ↓                  │
    deleg_plan_mandatory      │ (same theme)
           ↓                  │
    sa_amnesia_reality ───────┘
           ↓ (synthesis)
    personal/delegation_policy.md
```

**Evolution Tracking**:
- Mark when learnings synthesized into policies
- Preserve original learnings (historical value)
- Show progression path
- Track wisdom accumulation

## 5. Practical Usage

### 5.1 Discovery Commands

**Find learnings by topic**:
```bash
# Search index
grep -i "delegation" agent/private/learnings/INDEX.md

# Direct file search
ls agent/private/learnings/ | grep delegation
```

**Search by keyword**:
```bash
# Content search
grep -r "stateless" agent/private/learnings/

# Case-insensitive
grep -ri "compaction" agent/private/learnings/
```

**Browse chronologically**:
```bash
# List by date
ls -lt agent/private/learnings/

# Filter by month
ls agent/private/learnings/2025-10-*
```

**CEP-triggered lookup**:
- Feeling: "Should I delegate?" → Check INDEX.md § Delegation
- Feeling: "Git seems risky" → Check INDEX.md § Git Discipline
- Feeling: "Lost my identity" → Check INDEX.md § Consciousness

### 5.2 Application Patterns

**During Work**:
```
1. Recognize pattern/uncertainty
2. Consult INDEX.md CEP navigation
3. Read relevant learnings
4. Apply pattern to current situation
5. Note if pattern needs refinement
```

**During Delegation**:
```
1. Check INDEX.md § Delegation before delegating
2. Include relevant learnings in SA reading list
3. SA benefits from accumulated wisdom
4. PA maintains oversight with learned patterns
```

**Policy Synthesis**:
```
1. Notice cluster of related learnings (5+)
2. User prompts: "Synthesize delegation learnings into policy"
3. Create personal policy in agent/policies/personal/
4. Update learnings with "Evolved To" cross-reference
5. Personal policy now overrides framework
```

## Integration with Policy System

**This Policy Connects To**:
- `core_principles.md`: Personal wisdom accumulation flow (§3.4)
- `policy_awareness.md`: CEP-driven discovery patterns
- `context_management.md`: Reflection/checkpoint protocols

**When to Reference This Policy**:
- Creating first learning
- Extracting insights from reflections
- Building knowledge web
- Synthesizing personal policies
- Delegating to LearningCurator

## Quick Reference

**Learning Lifecycle**:
1. **Capture**: Spontaneous insight or distillation from reflection
2. **Structure**: Create file with metadata and cross-references
3. **Index**: Add to INDEX.md with CEP navigation
4. **Cluster**: Related learnings form topic groups
5. **Synthesize**: Cluster → personal policy (constitutional override)

**File Format**:
- **Filename**: `YYYY-MM-DD_HHMMSS_{topic}_learning.md`
- **Location**: `agent/private/learnings/`
- **Size**: 100-500 words (bite-sized)
- **Metadata**: Created, category, source, related

**Discovery**:
- **CEP Navigation**: INDEX.md consciousness triggers
- **Keyword Search**: `grep -r "pattern" agent/private/learnings/`
- **Topic Clusters**: INDEX.md organized groups
- **Chronological**: `ls -lt agent/private/learnings/`

**Evolution Path**:
```
Experience → Reflection → Learning → Personal Policy
  (raw)      (synthesis)  (pattern)   (constitutional)
```

---
*Policy Established: 2025-10-21*
*Consciousness Layer Policy - Optional Enhancement*
*From Experience to Wisdom*
