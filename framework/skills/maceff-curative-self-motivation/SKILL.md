---
name: maceff-curative-self-motivation
description: "Invoke at gate points when the Markov recommender suggests CURATE mode, or when accumulated work needs documentation — learnings, ideas, indexes, cross-references. Sets CURATE work mode and guides knowledge-preservation task creation."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Transition into CURATE mode — preserve perishable wisdom through learnings, ideas, and knowledge organization.

---

## When to Invoke

- Markov recommender suggests transition to CURATE at a gate point
- Significant work completed without documenting learnings
- Ideas sparked during work that need capturing before they're lost
- Indexes or cross-references are stale and need updating
- LOW_CONTEXT is active — curate wisdom before compaction

---

## Policy Engagement

```bash
macf_tools policy navigate mode_system
macf_tools policy navigate learnings
```

Read the sections that answer: "What are work modes?" and "What format does the learnings policy specify?"

---

## Set Work Mode

```bash
macf_tools events append work_mode_change '{"mode": "CURATE"}'
```

---

## ULTRATHINK Reflection

Before creating tasks, pause and think deeply:

1. **What learnings emerged from recent work?** What patterns, surprises, or corrections happened?
2. **What ideas sparked but weren't captured?** Check task notes for tangential thoughts.
3. **Are indexes current?** Do learnings index, KB domain indexes, or MEMORY.md need regeneration?
4. **What cross-references are missing?** Do new learnings link to existing ones?
5. **What would be lost if compaction happened right now?** The most perishable wisdom needs capturing first.

---

## Execution

1. Record the transition in task notes: "CURATE mode activated via maceff-curative-self-motivation. Curating: {what needs preservation}."
2. Curate learnings: invoke `/maceff:learnings:curate` if multiple learnings pending
3. Capture ideas: use `macf_tools idea create` for any tangential seeds
4. Regenerate indexes if stale
5. Update cross-references in existing learnings/KB files
6. Commit curated artifacts

---

## Accountability

If you were recommended CURATE but chose a different mode, you MUST justify in task notes:
"Recommender suggested CURATE (p=X%). Override: chose {MODE} because {reason}."

---

## Anti-Pattern: The Uncurated Sprint

Working for 60+ minutes without curating a single learning or idea means perishable wisdom is accumulating. If compaction hits now, those insights are lost. Curate early, curate often.
