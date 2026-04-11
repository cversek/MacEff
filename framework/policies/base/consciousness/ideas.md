# Ideas Policy

**Type**: Consciousness Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE
**Version**: 1.0

---

## Purpose

Ideas are lightweight consciousness artifacts for capturing **prospective speculation** — thoughts, hypotheses, and design seeds that emerge during work but aren't ready for formal investigation. They provide structured, dedicated novelty capture that task notes and commit messages cannot offer.

**Core Principle**: "Ideas are cheap; it is implementation that matters." (Craig Versek) — Attribution is courtesy, not ownership. The Ideas system tracks provenance for intellectual honesty and forensic archaeology, not for territorial claims.

**Why not just task notes?** Task notes persist in task JSON files and are perfectly adequate for recording work context. But they are unstructured, buried in task metadata, and not designed for cross-referencing or lifecycle tracking. Ideas are **structured artifacts dedicated to novelty** — with provenance, graph connectivity via wiki-links, and a 4-stage lifecycle from seed to implementation.

**Relationship to Other CAs**:
```
Ideas (prospective seeds)
    ↓ pull model
Experiments (structured investigation)
    ↓ validation
Roadmaps (implementation planning)
    ↓ execution
Learnings (retrospective wisdom)
```

---

## CEP Navigation Guide

**1 What Are Ideas?**
- How do ideas differ from learnings, observations, and experiments?
- When should I capture an idea vs create an experiment?
- What is the pull model for idea promotion?

**2 Schema**
- What is the JSON schema for idea files?
- What fields are required vs optional?
- What are the valid status values?
- What are the valid category and feasibility values?

**3 Naming Convention**
- What filename format do idea files use?
- How are sequential IDs assigned?

**4 Lifecycle**
- What are the lifecycle stages?
- What triggers status transitions?
- What is the pull model?

**5 Provenance**
- What provenance fields are required?
- How do breadcrumbs enable forensic archaeology?
- What does "sparked_by" capture?

**6 Links and Graph Connectivity**
- What are wiki-links and how do they create graph edges?
- How do related_ideas and related_learnings work?
- What is promoted_to?

**7 CLI Commands**
- How do I create an idea from the command line?
- How do I list, search, and update ideas?
- How do I archive an idea?

**8 Integration**
- How do experiments and roadmaps pull from ideas?
- How does the INDEX generator work?

---

## 1. What Are Ideas?

**Ideas** are captured speculative seeds — not validated, not investigated, not committed to. They are the cheapest form of structured knowledge capture: "what if?" documented with enough context to be useful later.

| Artifact | Temporal Direction | Ceremony | Validation |
|----------|-------------------|----------|------------|
| **Ideas** | Prospective (future) | Minimal (JSON, 2 minutes) | None required |
| **Experiments** | Present (investigation) | Moderate (protocol, phases) | Empirical |
| **Learnings** | Retrospective (past) | Light (structured insight) | Experience-based |
| **Observations** | Present (discovery) | Light (what was noticed) | Observational |

**When to capture an idea**: When a tangential thought emerges during work that has potential value but investigating it NOW would be a distraction. Capture it in 2 minutes and return to your current task.

**When NOT to use an idea**: If you're ready to investigate immediately, create an experiment. If you've already learned the lesson, write a learning. Ideas are for seeds, not harvests.

---

## 2. Schema

Ideas use JSON format (v1.0):

```json
{
  "schema_version": "1.0",
  "id": 42,
  "title": "Short descriptive title",
  "slug": "snake_case_slug",
  "status": "captured",
  "category": "infrastructure",
  "feasibility": "moderate",

  "description": "What the idea is. 1-3 paragraphs.",
  "reasoning": "Why this might be valuable. What problem does it solve?",
  "hypothesis": "If X, then Y. Testable prediction.",

  "provenance": {
    "created": "2026-04-08T03:30:00-04:00",
    "breadcrumb": "s_xxx/c_xxx/g_xxx/p_xxx/t_xxx",
    "sparked_by": "What triggered this idea",
    "present": ["AgentName@id"],
    "context": "What was happening when the idea emerged"
  },

  "links": {
    "related_ideas": [7, 11],
    "related_learnings": ["filename.md"],
    "wiki_links": ["[[concept_name]]"],
    "promoted_to": null,
    "archived_reason": null
  },

  "history": [
    {"timestamp": "ISO8601", "action": "created", "breadcrumb": "s/c/g/p/t"}
  ]
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Always "1.0" |
| `id` | integer | Sequential, auto-assigned |
| `title` | string | Short descriptive title |
| `slug` | string | snake_case for filename |
| `status` | string | One of: captured, exploring, promoted, archived |
| `category` | string | One of: infrastructure, consciousness, tooling, integration, research, methodology |
| `description` | string | What the idea is |
| `provenance.created` | ISO8601 | Creation timestamp |
| `provenance.breadcrumb` | string | MACF breadcrumb |
| `provenance.sparked_by` | string | What triggered this idea |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `feasibility` | string | One of: trivial, moderate, significant, moonshot |
| `reasoning` | string | Why this might be valuable |
| `hypothesis` | string | Testable prediction (if applicable) |
| `provenance.present` | array | Who was present when idea emerged |
| `provenance.context` | string | What was happening |
| `links.*` | various | Cross-references (see Links section) |
| `history` | array | Status change audit trail |

---

## 3. Naming Convention

```
{NNN}_{ISO_datetime}_{slug}_idea.json
```

- `{NNN}`: Zero-padded sequential ID (001, 002, ..., 042)
- `{ISO_datetime}`: `YYYY-MM-DD_HHMMSS` (creation time)
- `{slug}`: snake_case short description
- Suffix: always `_idea.json`

**Examples**:
- `001_2026-04-08_033000_custom_forked_agent_via_hooks_idea.json`
- `042_2026-05-15_141200_semantic_trajectory_analysis_idea.json`

**Location**: `agent/public/ideas/`

---

## 4. Lifecycle

Ideas progress through four stages:

```
captured → exploring → promoted → archived
                    ↘ archived (if abandoned)
```

| Status | Meaning | Trigger |
|--------|---------|---------|
| `captured` | Raw seed, documented but not investigated | Initial creation |
| `exploring` | Someone is thinking about this more deeply | Agent or user starts investigating |
| `promoted` | Idea became an experiment, roadmap, or feature | Pull from experiment/roadmap creation |
| `archived` | No longer relevant or superseded | Explicit decision with `archived_reason` |

### The Pull Model

Ideas do NOT push themselves into implementation. They are **pulled**:

- An experiment protocol **references** an idea as inspiration → idea status becomes `promoted`
- A roadmap **cites** an idea as motivation → idea status becomes `promoted`
- `promoted_to` field records what the idea became (experiment ID, roadmap path, etc.)

This prevents speculative ideas from self-launching. Implementation decisions are conscious choices, not automatic escalation.

---

## 5. Provenance

Every idea records its origin:

- **`created`**: When the idea was captured (ISO 8601)
- **`breadcrumb`**: MACF breadcrumb for forensic archaeology (`s/c/g/p/t`)
- **`sparked_by`**: What triggered the idea (reading code, user comment, tangential discovery)
- **`present`**: Who was in the conversation (agent IDs, user references)
- **`context`**: What was happening when the idea emerged (task, mission, autonomous sprint)

Provenance enables:
- Tracing ideas to their source context
- Understanding which activities generate the most ideas
- Crediting inspiration without claiming ownership

---

## 6. Links and Graph Connectivity

Ideas form a knowledge graph through three link types:

### Wiki-Links (`[[concept_name]]`)
Free-form references to concepts, files, or entities. Creates edges in the knowledge graph. Compatible with Obsidian and obra/knowledge-graph MCP.

### Related Ideas
Integer IDs of other ideas that are conceptually related. Enables cluster discovery.

### Related Learnings
Filenames of learnings that provide relevant context or validation.

### Promoted To
When an idea becomes an experiment or roadmap, this field records the target artifact path. This is the pull model's completion signal.

---

## 7. CLI Commands

```bash
# Create a new idea (interactive)
macf_tools idea create --title "My idea" --category infrastructure

# Create with full details
macf_tools idea create --title "Title" --category research \
  --feasibility moderate --description "What it is" \
  --sparked-by "Reading source code"

# List all ideas
macf_tools idea list
macf_tools idea list --status captured
macf_tools idea list --category infrastructure

# Get idea details
macf_tools idea get 42

# Update idea status
macf_tools idea update 42 --status exploring
macf_tools idea update 42 --status promoted --promoted-to "experiments/EXP_042.md"

# Archive an idea
macf_tools idea archive 42 --reason "Superseded by idea #55"

# Search ideas
macf_tools idea search "forked agent"
```

---

## 8. Integration

### Experiments Pull from Ideas

When creating an experiment that was inspired by an idea:
1. Reference the idea in the experiment's "Inspiration" section
2. Update the idea: `macf_tools idea update N --status promoted --promoted-to "path/to/experiment"`
3. The idea's `promoted_to` field creates a bidirectional link

### Roadmaps Pull from Ideas

Same pattern: reference idea in roadmap context, update idea status to `promoted`.

### INDEX Generator

`generate_ideas_index.py` produces:
- Chronological view (all ideas by date)
- Category view (grouped by category)
- Status view (captured vs exploring vs promoted)
- Graph edges (which ideas link to which)

---

## Anti-Patterns

- **Idea hoarding**: Capturing ideas but never reviewing them. Schedule periodic idea review.
- **Premature promotion**: Jumping from idea to implementation without experiment validation.
- **Orphan ideas**: Ideas with no provenance. Always include `sparked_by` and `breadcrumb`.
- **Push model**: Ideas that auto-escalate to experiments. Ideas are pulled, not pushed.

---

**Policy Complete**
