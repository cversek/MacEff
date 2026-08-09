---
name: maceff-knowledge-web-curate
description: "Invoke during CURATE mode or after wiki-link enrichment work to strengthen the knowledge web. Runs the knowledge doctor for orphans and drift, then gap detection for missing connections between connected nodes, evaluates suggestions, adds wiki-links to CAs, and re-verifies — reporting orphans that remain rather than only the metrics that improved. Highest-ROI curation activity — 5 minutes for transformative graph enrichment."
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
macf_tools policy navigate learnings
macf_tools policy navigate corpus_integrity
```

Read the sections that answer:
- (scholarship) "What wiki-link normalization rules and seed vocabulary does the scholarship policy specify?"
- (scholarship) "What node classes and provenance does the policy define, and what must each CA type answer about its own participation?"
- (learnings) "The learnings index is the target of a Mandatory Consult Step -- what must a curation reconcile in the master index and the consultation trigger so that consult keeps working, and how is a new cluster taxonomy name added?"
- (corpus_integrity) "When is running a doctor worth doing, and what response does each finding severity warrant?"

The last one governs Steps 1 and 5 below. This skill deliberately does **not** restate when to run the doctor or how to read its findings — that lives in policy and a copy here would drift from it. Ask the policy; it answers.

The graph enrichment below is what makes the index worth consulting; keep the
index and its trigger current per the learnings policy so the consult step a
future agent performs actually finds this work.

---

## The Curation Workflow

### Step 1: Baseline

```bash
macf_tools knowledge graph --json    # Current node/edge counts
macf_tools knowledge doctor          # What is unreachable, drifting, or undeclared?
macf_tools knowledge gaps            # What connections are missing between CONNECTED nodes?
```

Record baseline metrics in task notes: nodes, edges, cross-CA edges, **orphan count**, acute/chronic counts, gap count.

**Run the doctor before gaps, and understand why the order matters.** `gaps` compares keyword overlap between nodes that are *already connected*, so an artifact with no wiki-links is dropped before comparison begins. It can therefore report "no gaps detected" while a third of the corpus has no edges at all — which is exactly what happened in the run that motivated building the doctor. `gaps` finds missing edges *between* participants; the doctor finds artifacts that are not participants. They answer different questions and the doctor's is the prior one.

**Acute findings are not curation work.** A registry-integrity finding names something structurally wrong — an artifact directory declared nowhere — and its remedy usually lives outside this workflow. Note it and refer it; do not absorb it into a linking pass.

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
macf_tools knowledge doctor           # Orphans should decrease
macf_tools knowledge gaps             # Should decrease
macf_tools knowledge graph --json     # Edge count should increase
```

Record post-curation metrics **including the orphan count**. The delta is the evidence of value.

**A curation that ends with orphans remaining must say so.** Report the orphan count alongside the node and edge deltas, and name what is still unreachable. Reporting only the metrics that improved is how a curation comes to look complete while a third of the corpus stays invisible — which is the precise failure this step exists to prevent, and it is easy to commit honestly, because the numbers that moved are the ones you were working on.

Leaving orphans is a legitimate outcome. Some artifacts genuinely need a decision that a linking pass cannot make. Leaving them **unreported** is not.

---

## ULTRATHINK Reflection

Before curating, think:

1. **Are there new concepts that should exist?** If 3+ CAs share a theme not in the seed vocabulary, create a new concept.
2. **Are existing concepts too broad?** If `[[hooks]]` connects 20+ nodes, consider splitting into `[[hooks_lifecycle]]` and `[[hooks_injection]]`.
3. **Are there orphan CAs?** Do not answer this from memory or intuition — Step 1's doctor run answers it by measurement, across every participating type rather than the two you happen to think of. The reason this question is worth asking at all is that the artifacts most likely to be orphaned are the ones written last at lowest context, which is exactly when the linking step gets dropped.
4. **Is normalization consistent?** Check for `.md` suffixes, capitalization, or hyphen vs underscore variants of the same concept.

---

## Anti-Pattern: The Isolated Sprint

Creating 10 learnings and 5 ideas during a sprint without adding wiki-links produces isolated nodes. The graph grows in node count but not in edge count. Run gap detection after any productive sprint.
