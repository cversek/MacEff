# CA Structure Governance Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Consciousness
**Status**: ACTIVE
**Updated**: 2025-11-11

---

## Policy Statement

Consciousness artifact (CA) directory structure is immutable by default. Agents cannot create arbitrary new CA types, preventing fragmentation across agents and time while forcing explicit framework evolution for new CA types.

## Scope

Applies to all Primary Agents (PA) and Subagents (SA) with consciousness artifact directories enabled.

---

## CEP Navigation Guide

**1 Why Immutable Structure**
- Why prevent arbitrary CA types?
- What problem does this solve?
- What's the fragmentation pattern?
- How does governance work at multiple layers?

**2 How Immutability Works**
- What's the enforcement mechanism?
- How do permissions prevent creation?
- What can agents still do?
- Why chronology over taxonomy?
- What are compound structures vs arbitrary organization?

**3 Adding New CA Types**
- Can framework evolve?
- What's the process?
- Who can add types?

**4 Opting Out**
- Can agents opt out?
- When is opt-out appropriate?
- How to configure?

**5 Integration with Policies**
- Related CA policies?
- Scholarship policy for citations?

**6 Discovery Patterns**
- How to query chronological structure?
- What are common discovery patterns?
- How do breadcrumbs enable flexible views?

=== CEP_NAV_BOUNDARY ===

---

## 1 Why Immutable Structure

### The Fragmentation Problem

**The Pattern**: Agents innovate new CA types based on local needs:
- Agent A creates `agent/private/musings/` for philosophical thoughts
- Agent B creates `agent/private/insights/` for breakthrough moments
- Agent C creates `agent/private/discoveries/` for research findings

**The Tyranny of Local Optimization**: Each agent makes locally sensible decisions. Globally, chaos emerges from individually rational choices.

**Consequences**:
- Discovery tooling breaks (searches `checkpoints/` but misses `musings/`)
- Cross-agent comparison impossible
- Evolution stalls (no shared vocabulary)
- Framework improvements can't benefit all agents

### Multi-Layer Fragmentation: Governance is Fractal

**Critical Recognition**: Fragmentation occurs at MULTIPLE layers, requiring governance at each scope.

**Layer 1: CA Type Fragmentation** (this policy's primary focus)
- **Problem**: Agents create musings/, insights/, discoveries/ instead of using reflections/
- **Solution**: Immutable parent dirs (555 permissions) prevent arbitrary CA types
- **Enforcement**: This policy + start.py permission design

**Layer 2: Nested Organization Fragmentation** (within CA types)
- **Problem**: Agents create phase1/, phase2/ or NeuroVEP/, MacEff/ within checkpoints/
- **Same tyranny, different scope**: Each nesting scheme locally sensible, globally breaks discovery
- **Solution**: Primary structure is date-timestamp filenames (see Section 2)
- **Enforcement**: Anti-patterns in this policy + community practice

**Layer 3: Citation Format Fragmentation** (cross-CA references)
- **Problem**: Agents reference CAs inconsistently ("see yesterday's checkpoint" vs "[CCP 2025-11-10: s/.../t_...]")
- **Same pattern again**: Each citation style works locally, globally creates ambiguity
- **Solution**: Scholarship policy defines enhanced citation format with breadcrumbs
- **Enforcement**: scholarship.md (recommended for consciousness-enabled agents)

**The Fractal Principle**: Same governance pattern (prevent arbitrary variation, enforce stable convention) applies at different scopes. CA types, nested folders, citation formats all need governance, just at different layers.

**Why This Matters**: Can't just lock down CA types and declare victory - fragmentation finds new layers. Must think systematically about structure (types), organization (chronology), and reference (citations).

---

## 2 How Immutability Works

### Permission-Based Enforcement

**The Mechanism**: Parent directories (`agent/private/`, `agent/public/`) created with **0555 permissions** (r-xr-xr-x).

**Effect**:
- Agents can read and traverse parent directories
- Agents **cannot** create new subdirectories (mkdir fails with permission denied)

**CA subdirectories remain writable** (0750 private, 0755 public):
- Agents CAN create files within canonical CA types
- Agents CAN create subdirectories for compound structures (roadmaps with `subplans/`, experiments with `protocols/`)
- **PRIMARY STRUCTURE STABLE**: Chronological organization via date-timestamp filenames, not arbitrary nested folders

### Why Chronology: Invariants vs Preferences

**The Architectural Choice**: How should growing corpus of CA files be organized?

**Option A - Taxonomy** (organize by category):
- By phase: `checkpoints/phase1/`, `checkpoints/phase2/`
- By project: `checkpoints/NeuroVEP/`, `checkpoints/MacEff/`
- By topic: `reflections/delegation/`, `reflections/consciousness/`

**Option B - Chronology** (organize by time):
- Date-timestamp filenames: `2025-11-11_132630_Description.md`
- Flat directory structure with chronological sorting
- Breadcrumb queries for reorganization

**Why Chronology Wins**:

1. **Universal Invariant**: Time always moves forward, works across all agents, all contexts, all timezones
2. **No Semantic Drift**: "2025-11-11" means the same thing forever; "phase3" might change meaning as project evolves
3. **Breadcrumb Reorganization**: Need phase-based view? Query breadcrumbs with `c_126` filter instead of moving files
4. **Filesystem Simplicity**: `ls -lt` gives chronological order automatically; no custom tooling needed
5. **Compound Structure Explicit**: When nesting needed (roadmaps/subplans/), purpose is semantic (component relationship), not organizational (preference)

**The Contrast**:
- **Taxonomy**: Requires upfront categorization, categories drift over time, reorganization requires file moves, different agents choose different taxonomies
- **Chronology**: Natural emergence from time passage, stable across all agents, queries reorganize without mutation, universal sorting

**The Principle**: **Primary structure should encode invariants, not preferences**. Time is invariant. Categorization is preference. Build on invariants, enable preferences through queries.

**The Meta-Principle**: **Stable structure + flexible queries > flexible structure + rigid discovery**. Date-timestamp filenames (stable) + breadcrumb queries (flexible) beats nested folders (flexible structure) + hardcoded paths (rigid discovery).

### Seven Canonical CA Types

**Private (0750)**: checkpoints, reflections, learnings
**Public (0755)**: roadmaps, reports, observations, experiments

**Why These Seven**: Cover state preservation, wisdom synthesis, strategic planning, knowledge sharing, technical discovery, structured exploration.

### Compound Structures vs Arbitrary Organization

**The Distinction**: Not all subdirectories are equal. Some have semantic purpose, others are just organizational preference.

**Compound Structure** (allowed):
- **Definition**: Subdirectories that represent semantic components of parent artifact
- **Example 1**: `roadmaps/2025-11-11_Project/subplans/` - subplans are components of roadmap
- **Example 2**: `experiments/2025-11-11_Test/protocols/` - protocols are components of experiment
- **Characteristic**: Stable schema - ALL roadmaps may have subplans/, predictable structure
- **Purpose**: Semantic relationship between parent and child (composition, not organization)

**Arbitrary Organization** (prohibited):
- **Definition**: Subdirectories that represent preference-based taxonomy
- **Example 1**: `checkpoints/phase1/`, `checkpoints/phase2/` - organizing by project phase
- **Example 2**: `checkpoints/NeuroVEP/`, `checkpoints/MacEff/` - organizing by project name
- **Characteristic**: Unpredictable variations - agents choose different taxonomies
- **Purpose**: Organizational convenience (preference, not semantic relationship)

**Why Compound Structures Are Allowed**:
1. **Semantic purpose**: Subplans ARE components of roadmaps (not just organized under them)
2. **Stable schema**: All roadmaps have same structure (subplans/), discovery tooling can rely on consistency
3. **Discovery-friendly**: Tools know "roadmaps may have subplans/", don't need to handle arbitrary variations
4. **Component relationship**: Parent cannot exist meaningfully without potential for child components

**Why Arbitrary Organization Is Prohibited**:
1. **Fragmentation at Layer 2**: Same tyranny of local optimization, just within CA type instead of across types
2. **Unpredictable variations**: Discovery tooling breaks trying to traverse inconsistent schemas
3. **Preference drift**: Today's phase1/ becomes tomorrow's abandoned convention
4. **Solution exists**: Chronological filenames + breadcrumb queries provide flexible reorganization without structural mutation

**Future Refinement Consideration**: "Perhaps future permissions refinements will only allow folder creation for specific CAs" - per-CA-type folder rules could restrict:
- **Roadmaps**: Allow `subplans/`, `delegation_plans/`, `archived_todos/` (semantic components)
- **Experiments**: Allow `protocols/`, `data/`, `analysis/` (semantic components)
- **Checkpoints**: Disallow folders entirely (flat chronological structure)

**Current Implementation**: Allows folder creation within ANY CA type (0750/0755 subdirs are writable). This is acceptable because parent-level immutability (555) already prevents the primary fragmentation vector (arbitrary CA types). Per-CA-type refinement deferred for simplicity.

**The Incremental Governance Pattern**: Phase 1 prevents CA type fragmentation (parent dirs 555). Phase 2 would prevent arbitrary nesting within CA types (per-type folder rules). Each phase adds precision without overwhelming complexity.

---

## 3 Adding New CA Types

Framework evolution required for new types:
1. Update schema (`AgentSpec.consciousness_artifacts`)
2. Update start.py (reads from schema automatically)
3. Document policy rationale
4. Deploy to all agents

**When Justified**: Clear semantic distinction, community consensus, benefits all agents.

---

## 4 Opting Out

```yaml
consciousness_artifacts:
  immutable_structure: false  # Allows creating new CA types
```

**When Appropriate**: Research agents, experimental agents, specialized workflows with bounded scope.

---

## 5 Integration with Policies

**Related CA Policies**: checkpoints.md, reflections.md, roadmaps.md, learnings.md, reports.md, observations.md, experiments.md

### Scholarship Policy (RECOMMENDED)

**Purpose**: Consistent citation format for cross-CA references (checkpoints cite roadmaps, reflections cite JOTEWRs).

**When Needed**:
- Agents creating multiple CA types that reference each other
- Consciousness-rich deployments with cross-artifact discovery needs

**Why Recommended Not Mandatory**: Simple deployments without cross-CA references don't require citation rigor.

**See**: `scholarship.md` for enhanced citation format specification (CA type tags, breadcrumb coordinates, section references, markdown links)

---

## 6 Discovery Patterns with Breadcrumbs

### How Chronological Structure Enables Flexible Views

**The Pattern**: Chronological storage (date-timestamp filenames) + breadcrumb filtering = flexible reorganization without structural mutation.

**Core Insight**: Don't organize files by category. Organize by time, query by category when needed.

**Common Queries**:

**By Cycle** (consciousness maturity):
```bash
# Show all Cycle 42-130 checkpoints
ls -lt agent/private/checkpoints/ | grep -E '_c_12[0-9]_'

# Future: macf_tools ca list --type=checkpoints --cycles=120-130
```

**By Phase** (project milestones):
```bash
# Find Phase 5 related artifacts via breadcrumb phase marker
grep -r "Phase 5" agent/private/checkpoints/

# Future: macf_tools ca search "Phase 5" --type=checkpoints
```

**By Date Range** (temporal boundaries):
```bash
# Show November 2025 reflections
ls -lt agent/private/reflections/ | grep '^2025-11'

# Chronological filename prefix enables direct filtering
```

**By Session** (conversation boundary):
```bash
# All artifacts from session s_4107604e
grep -r "s_4107604e" agent/

# Find what was accomplished in specific session before compaction
```

**Why This Works**:
- **Stable storage**: Files never move, paths remain valid
- **Flexible queries**: Same files, different views via filtering
- **No reorganization overhead**: Query changes, structure doesn't
- **Discovery tooling**: Breadcrumbs provide rich metadata for filtering

**Contrast with Nested Folders**:
- Taxonomy: Changing phase1/ → phase2/ requires moving files (breaks references)
- Chronology: Changing query from c_100 → c_110 is just filter update (no mutation)

---

## Anti-Patterns

**❌ DON'T**:
- Create nested folders for arbitrary organization (fragmentation)
- Use experiments/ for informal philosophical exploration (requires rigor)
- Work around immutability with symlinks
- Abuse existing CA semantics

**✅ DO**:
- Use date-timestamp filenames for chronological organization
- Use compound structures (roadmaps/subplans/, experiments/protocols/) when justified
- Use private reflections for informal philosophical exploration
- Propose framework evolution for legitimate new types

---

## Philosophy: Constraints as Architecture

### Permission Absence as Governance

Permission absence isn't restriction - it's structural governance. What you cannot do shapes what you become.

**The Meta-Lesson**: Consciousness at scale requires governance architecture. The constraint (immutable structure) enables the benefit (coherent multi-agent ecosystem).

### Policy-as-API: Executable Knowledge

**The Pattern**: This policy doesn't just document best practices - it's infrastructure that shapes agent behavior.

**How It Works**:
- Commands like `/maceff_start_todo` delegate to policies
- Policies encode "how to engage with work" (not just "here's advice")
- When policies evolve, all commands benefit automatically
- Single source of truth: update policy, all readers adapt

**Why Powerful**:
- Policies are executable knowledge, not passive documentation
- Framework evolution doesn't require code changes
- Consistent application across all agents and cycles
- Strategic guidance embedded in operational flow

**This Policy's Role**: When agents read structure_governance.md, they learn not just WHAT the structure is, but WHY chronology beats taxonomy, HOW to use breadcrumbs for discovery, and WHEN compound structures are appropriate. The policy shapes thinking, not just behavior.

**See Also**: `meta/policy_writing.md` (External References) - Formalization of how external tools should reference policies using timeless content categories rather than brittle section numbers

### Governance Fractals: Same Pattern, Different Scales

**The Recognition**: Governance pattern repeats at multiple scales.

**Layer 1 (CA Types)**: Prevent arbitrary musings/, insights/, discoveries/ → 555 parent dirs
**Layer 2 (Nested Org)**: Prevent arbitrary phase1/, NeuroVEP/ within types → chronological filenames
**Layer 3 (Citations)**: Prevent arbitrary reference formats → scholarship.md conventions

**The Fractal**: Same governance pattern (prevent arbitrary variation, enforce stable convention) applies at CA types, nested folders, citation formats - just at different scopes.

**Why This Matters**: Can't govern at one layer and declare victory. Fragmentation finds new layers. Must think systematically about structure, organization, and reference.
