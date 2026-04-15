---
name: maceff-knowledge-web-orient
description: "Invoke before starting a task to orient via the knowledge graph. Queries the graph for concepts related to the task, reveals what the agent already knows, and surfaces connected CAs for reading. Replaces blind grep with structure-aware exploration."
allowed-tools: Bash, Read, Grep, Glob
---

Orient to a task domain using the knowledge graph before diving into work.

---

## When to Invoke

- Before starting a new task or MISSION phase
- When entering DISCOVER work mode on an unfamiliar topic
- When you need to understand "what do I already know about X?"
- Before writing a learning or observation — check if related ones exist
- When the Markov recommender suggests DISCOVER and you want directed exploration

---

## Policy Engagement

```bash
macf_tools policy navigate scholarship
```

Read the section that answers: "How do wiki-links create concept-mediated edges and what graph tooling exists?"

---

## The Orientation Workflow

### Step 1: Identify Key Concepts

From the task description, extract 2-3 key concepts. These might be:
- Seed vocabulary terms: `compaction`, `hooks`, `delegation`, `modes`
- Domain-specific terms from the task: `transcript`, `session`, `autonomy`
- Technical terms: `context_management`, `knowledge_graph`

### Step 2: Query Each Concept

```bash
macf_tools knowledge query <concept>
```

This returns:
- **Matched nodes**: CAs directly connected to this concept
- **Neighbors**: CAs one hop away (connected to matched nodes)
- **Shared concepts**: Other concepts that co-occur with your query

### Step 3: Assess Knowledge Depth

The query results tell you:
- **High degree nodes** (10+): Well-explored area, rich prior work to build on
- **Low degree nodes** (1-3): Lightly explored, may need more investigation
- **No matches**: Unknown territory — this is a genuine discovery opportunity

### Step 4: Read High-Value Neighbors

From the query results, identify the 2-3 highest-degree CAs and read them:

```bash
# For learnings (by filename from query output)
Read agent/private/learnings/<filename>.md

# For ideas (by ID)
macf_tools idea get <id>

# For observations
Read agent/public/observations/<filename>.md
```

These are the most-connected artifacts in your task's domain — they contain the densest prior knowledge.

### Step 5: Note Orientation Findings

Record what you learned in task notes:

```bash
macf_tools task note <id> "Orientation via knowledge graph: queried [[concept]]. Found N related CAs, highest-degree: <name> (deg X). Key prior knowledge: <summary>. Knowledge gaps: <what's missing>."
```

---

## ULTRATHINK Reflection

After querying, think:

1. **What does the graph structure tell me?** Dense cluster = well-understood area. Sparse connections = frontier.
2. **What's missing?** If the task touches a concept with no graph presence, that's a gap to fill during or after work.
3. **What prior mistakes are documented?** Learnings often encode corrections — check if any relate to your task domain.
4. **What ideas are waiting?** Ideas connected to your task's concepts might be ready for promotion or inform your approach.

---

## Anti-Pattern: The Blind Start

Starting a task by grepping for files or reading random code. The knowledge graph tells you WHERE to look and WHAT has been learned — use it. Structure-aware exploration beats keyword search.
