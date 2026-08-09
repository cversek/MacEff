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

3.3 Pre-Curation Discovery
- What existing learnings relate to the topic I'm about to curate?
- What topic clusters exist in the knowledge web?
- Which learnings might need bidirectional cross-link updates?
- How does discovery differ for single vs batch curation?

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

4.3 The Consultation Trigger and the Mandatory Consult Step
- Where does the learnings index live, and what rides in auto-loaded memory instead of per-learning pointers?
- What is the Mandatory Consult Step -- at which moments must the agent consult the index?
- How does the cluster taxonomy trigger the consult, and how does the pull model compensate for losing passive push?
- What does a learnings curation reconcile in the index and the trigger?

4.4 Knowledge Web Participation
- Does this type participate in the knowledge graph, and at what unit?
- Which node class and default provenance do learnings carry?
- How is an inherited learning marked, and why does it matter?
- What makes a learning an orphan, and who does an orphan fail?

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
5. Update the master learnings index (4.1) and verify the consultation trigger's cluster taxonomy (4.3)

**Delegation Pattern** (LearningCurator):
- Provide: List of unprocessed reflections
- Authority: Create learning files, update the master index and the consultation trigger
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
  - Cycle 42 development work
  - CLAUDE.md § Operating Principles

- **Evolved To**:
  - `agent/policies/personal/development_discipline.md` (synthesized policy)
```

**Knowledge Web Building**:
- Link forward and backward (bidirectional)
- Create topic clusters
- Track evolution (learning → policy)
- Enable discovery paths

### 3.3 Pre-Curation Discovery

Before writing new learnings, survey the existing knowledge web to identify cross-link targets. Discovery depth scales with curation mode:

**Batch Curation** ("multiple" mode — REQUIRED):
1. List all files in `agent/private/learnings/`
2. Group by topic cluster (from filenames or quick content scan)
3. Identify potential cross-link targets for each new learning
4. Note existing learnings that should receive back-links (bidirectional updates)

**Single Curation** (topic hint mode — targeted):
1. Search existing learnings for the topic keyword: `grep -ri "topic" agent/private/learnings/`
2. Identify 0-3 most relevant cross-link targets
3. Check if any existing learning needs a back-link update

**Why Discovery Matters**:
- Cross-references are edges in the knowledge graph — without them, learnings are isolated nodes
- Back-links ensure bidirectional discovery (A references B, B references A)
- Topic cluster awareness prevents duplicate learnings on the same insight
- Discovery before writing makes good scholarship the default, not an afterthought

## 4. Knowledge Web Architecture

### 4.1 Master Index

**The single, unbounded learnings index.** This is the one canonical index of all
active learnings, grouped by topic cluster with an activation hook per entry. It
grows without limit and is consulted on demand -- it is the target of the Mandatory
Consult Step (4.3). It is NOT force-loaded into context; the lightweight
consultation trigger in auto-loaded memory (4.3) is what points here.

**Location**: `agent/private/learnings/INDEX.md`

**Structure**:
```markdown
# Agent Learnings Index

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

### 4.3 The Consultation Trigger and the Mandatory Consult Step

**The single index is PULL, and it is unbounded.** The master index (4.1,
`agent/private/learnings/INDEX.md`) is the one canonical learnings index. It grows
without limit -- every active learning earns an entry, forever, because it is
consulted on demand rather than force-loaded. There is no second per-learning copy
in the platform's auto-loaded memory file. An earlier design kept one; it grew
unbounded inside a size-capped memory file and crowded out identity memory, which
is the failure this architecture removes.

**What rides in auto-loaded memory instead: a lightweight trigger.** The platform's
memory file (Claude Code: `~/.claude/projects/<project-key>/memory/MEMORY.md`)
carries a single small **consultation trigger**, not per-learning pointers. The
trigger holds three things: (a) the imperative to consult the index, (b) WHEN to
consult, and (c) the **cluster taxonomy** -- the topic-domain NAMES only (e.g.
"instrument-epistemology", "embedded-debug", "submission-integrity"). The taxonomy
is the reflex layer: it stays in context so the agent can recognize whether the
current problem plausibly belongs to a domain where prior wisdom exists, then pull
the detail from INDEX.md. It is a table of contents in context, with the contents
themselves one read away.

**The Mandatory Consult Step (MANDATORY).** Before beginning substantive work on a
problem, the agent MUST consult the learnings index for previously-encountered
problems of the same class. Consult at these moments:
- **Task or phase orientation** -- before diving into a new problem.
- **When a bug resists the first hypothesis** -- before building a fix on a guess.
- **Before declaring a problem novel, hard, or a dead end** -- the "I have never
  seen this" reflex is exactly when a prior learning most often exists.
- **Before shipping a fix or a claim** -- a relevant learning may name the failure
  mode you are about to repeat.

Mechanism: match the current problem against the trigger's cluster taxonomy; if any
cluster plausibly fits, open INDEX.md and scan that cluster's activation hooks. A
hook names WHEN it applies, so the scan is fast. Consulting and finding nothing is
a valid, cheap outcome; NOT consulting is the anti-pattern.

**The honest trade.** This replaces passive push of every activation hook with push
of the taxonomy plus a hard requirement to pull. The risk is real and worth stating
plainly: a pulled index only fires if the consult step is honored -- a hook works
as a reflex only when it is in context, and most hooks are no longer in context.
The design compensates three ways, and all three must hold: (1) the cluster
taxonomy stays in context as the recognition layer, so the agent knows WHETHER to
look without already knowing WHAT it will find; (2) the consult step is MANDATORY
and is enforced at orientation -- the knowledge-web orientation skill discovers this
requirement from policy and performs the consult as a workflow step; (3) the index
is unbounded, so completeness is free and nothing is dropped for budget. If
consultation stops happening in practice, that is a policy-compliance failure to
surface, not a reason to re-bloat the memory file.

**Curation integration.** Every learnings curation ends by (a) updating the master
index INDEX.md -- add the new learning to its cluster with an activation hook, keep
the header counts current -- and (b) verifying the consultation trigger's cluster
taxonomy still names every active cluster, adding a name when a new domain emerges
and retiring one only when its cluster empties. The trigger is the ONLY learnings
content in the memory file; keep it lean. Verify that the trigger's path to INDEX.md
resolves.

### 4.4 Knowledge Web Participation

Sections 4.1–4.3 describe the *index* — a curated, human-readable path into the corpus. This section covers the *graph*, which is a different mechanism with a different failure mode: the index is maintained by a curation step, while the graph is built by scanning artifacts for `[[concept]]` links. An artifact can be perfectly indexed and still invisible to the graph.

**Does this type participate?** Yes. Learnings are the densest concept-bearing artifacts in the corpus and the most-queried.

**What is the unit of a node?** The whole learning file. Learnings are single-insight by design, so the artifact and the concept-bearing unit coincide.

**Which class?** **Conceptual authority** — a learning states what was found in a form intended to outlive the episode that produced it. That is the definition of the class (see `scholarship.md`, on node classes and provenance).

**What provenance?** **Lived** by default: a learning records this agent's own experience. A learning that arrived from a predecessor lineage or another agent is **inherited**, and MUST carry a banner naming the lineage and stating that its claims are unverified by the current agent. This is not bookkeeping — an inherited learning read as lived experience causes the agent to cite as its own something it never experienced, and the corpus offers no other signal that would reveal it.

**Every learning carries a `## Wiki-Links` section.** A learning without one is an orphan: reachable through the index by an agent who already knows to look for it, and unreachable by concept query. Since concept query is how an agent finds prior work it does not know exists, an orphaned learning helps only the reader who least needs it.

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

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — learning
     capture, the master index, the consultation trigger, and provenance
     banners on inherited wisdom. -->

[[learnings]] [[knowledge_web]] [[provenance]] [[consciousness_artifacts]] [[discoverability]]

---
*Policy Established: 2025-10-21*
*Consciousness Layer Policy - Optional Enhancement*
*From Experience to Wisdom*
