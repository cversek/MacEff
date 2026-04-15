---
name: maceff-knowledge-web-curate
description: "Invoke during CURATE mode or after wiki-link enrichment work to strengthen the knowledge web. Runs gap detection, evaluates suggestions, adds wiki-links to CAs, and re-verifies. Highest-ROI curation activity — 5 minutes for transformative graph enrichment."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Strengthen the knowledge web through gap-driven wiki-link curation.

---

## When to Invoke

- During CURATE work mode when the knowledge web needs enrichment
- After creating multiple new CAs (learnings, observations, ideas) without wiki-links
- When `macf_tools knowledge gaps` reports missing connections
- As part of cycle closeout to ensure new work is connected to existing web
- After batch idea creation (e.g., autonomous sprint)

---

## Policy Engagement

```bash
macf_tools policy navigate scholarship
```

Read the section that answers: "What wiki-link normalization rules and seed vocabulary does the scholarship policy specify?"

---

## The Curation Workflow

### Step 1: Baseline

```bash
macf_tools knowledge graph --json    # Current node/edge counts
macf_tools knowledge gaps            # What's missing?
```

Record baseline metrics in task notes: nodes, edges, cross-CA edges, gap count.

### Step 2: Evaluate Gaps

For each gap suggestion:
- **100% confidence**: Almost certainly genuine — add the wiki-link
- **50-67% confidence**: Evaluate whether the keyword overlap reflects real conceptual connection
- **Below 50%**: Skip unless you have domain knowledge confirming the link

### Step 3: Query Before Linking

Before adding a wiki-link, query the concept to understand what you're connecting to:

```bash
macf_tools knowledge query <concept>    # What's already connected?
```

This prevents spurious links — if the subgraph doesn't relate to your node, the keyword overlap was coincidental.

### Step 4: Add Wiki-Links

**For ideas** (JSON files): Update the `links.wiki_links` array
**For learnings/observations** (markdown): Add or update `## Wiki-Links` section

Wiki-link format: `[[concept_name]]` — lowercase, underscores, no `.md` suffix.
Aim for 2-5 concepts per artifact.

### Step 5: Re-Verify

```bash
macf_tools knowledge gaps             # Should decrease
macf_tools knowledge graph --json     # Edge count should increase
```

Record post-curation metrics. The delta is the evidence of value.

---

## ULTRATHINK Reflection

Before curating, think:

1. **Are there new concepts that should exist?** If 3+ CAs share a theme not in the seed vocabulary, create a new concept.
2. **Are existing concepts too broad?** If `[[hooks]]` connects 20+ nodes, consider splitting into `[[hooks_lifecycle]]` and `[[hooks_injection]]`.
3. **Are there orphan CAs?** Learnings or observations without `## Wiki-Links` sections are invisible to the graph.
4. **Is normalization consistent?** Check for `.md` suffixes, capitalization, or hyphen vs underscore variants of the same concept.

---

## Anti-Pattern: The Isolated Sprint

Creating 10 learnings and 5 ideas during a sprint without adding wiki-links produces isolated nodes. The graph grows in node count but not in edge count. Run gap detection after any productive sprint.
