---
name: maceff-consolidative-self-motivation
description: "Invoke at gate points when the Markov recommender suggests CONSOLIDATE mode, or when scattered findings need synthesis into coherent observations, architecture documents, or knowledge web connections. Sets CONSOLIDATE work mode."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Transition into CONSOLIDATE mode — synthesize scattered findings into coherent understanding.

---

## When to Invoke

- Markov recommender suggests transition to CONSOLIDATE at a gate point
- Multiple learnings, KB entries, or experiment results need synthesis
- An observation document would connect dots that individual artifacts cannot
- A domain has been explored deeply enough to produce an architecture view
- LOW_CONTEXT is active — consolidate before compaction for maximum preservation

---

## Policy Engagement

```bash
macf_tools policy navigate mode_system
macf_tools policy navigate observations
```

Read the sections that answer: "What are work modes?" and "What format do observations use?"

---

## Set Work Mode

```bash
macf_tools mode set-work CONSOLIDATE
```

---

## ULTRATHINK Reflection

Before creating tasks, pause and think deeply:

1. **What scattered findings need connection?** Which KB entries, learnings, or experiment results form a coherent story when combined?
2. **What architecture view is missing?** Individual files document parts — what synthesis would reveal the whole?
3. **What observation would be most valuable to the user?** What connections would surprise or inform?
4. **What cross-domain patterns emerged?** Do findings from different domains share underlying principles?
5. **Is there a stakeholder report in this?** Can the synthesis be translated into accessible narrative for non-technical collaborators?

---

## Execution

1. Record the transition in task notes: "CONSOLIDATE mode activated via maceff-consolidative-self-motivation. Synthesizing: {what scattered findings}."
2. Review recent work: scan learnings, KB entries, experiment results, ideas
3. Write synthesis artifact: observation document, architecture view, or knowledge web update
4. Create cross-references between the synthesis and its source artifacts
5. Commit with clear linkage to the MISSION/experiment context

---

## Accountability

If you were recommended CONSOLIDATE but chose a different mode, you MUST justify in task notes:
"Recommender suggested CONSOLIDATE (p=X%). Override: chose {MODE} because {reason}."

---

## Anti-Pattern: The Premature Synthesis

Consolidating before enough raw material exists produces thin, obvious observations. If you have fewer than 3 substantial findings to connect — consider more DISCOVER or EXPERIMENT work first. Synthesis compounds knowledge; it cannot create it from nothing.
