---
name: maceff-experimental-self-motivation
description: "Invoke at gate points when the Markov recommender suggests EXPERIMENT mode, or when a discovery needs structured investigation before building. Sets EXPERIMENT work mode and guides hypothesis-driven task creation."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Transition into EXPERIMENT mode — structured investigation with hypotheses and protocols.

---

## When to Invoke

- Markov recommender suggests transition to EXPERIMENT at a gate point
- A discovery needs validation before committing to implementation
- An idea should be investigated rather than immediately built
- You need empirical data before making architectural decisions

---

## Policy Engagement

```bash
macf_tools policy navigate mode_system
macf_tools policy navigate experiments
```

Read the sections that answer: "What are work modes?" and "What makes a good experiment?"

---

## Set Work Mode

```bash
macf_tools events append work_mode_change '{"mode": "EXPERIMENT"}'
```

---

## ULTRATHINK Reflection

Before creating tasks, pause and think deeply:

1. **What hypothesis needs testing?** What assumption am I making that data could confirm or refute?
2. **What's the simplest experiment that would answer this?** Prefer 30-minute smoke tests over multi-phase protocols.
3. **What would I build IF the hypothesis is confirmed?** Knowing the downstream action focuses the experiment.
4. **Can I reuse an existing prototype?** Experiment CAs can contain prototypes as applied learnings.
5. **What ideas from the bank are ready for investigation?** Check `macf_tools idea list --status captured` for experiment candidates.

---

## Execution

1. Record the transition in task notes: "EXPERIMENT mode activated via maceff-experimental-self-motivation. Investigating: {hypothesis}."
2. Create an experiment task (or use existing): `macf_tools task create experiment "Title"`
3. Write a quick protocol or hypothesis statement
4. Execute: gather data, run tests, analyze results
5. Prototypes go INSIDE the experiment CA directory (not standalone repos)
6. Capture findings as learnings when complete

---

## Accountability

If you were recommended EXPERIMENT but chose a different mode, you MUST justify in task notes:
"Recommender suggested EXPERIMENT (p=X%). Override: chose {MODE} because {reason}."

---

## Anti-Pattern: The Premature Build

EXPERIMENT exists to GATE building behind validation. If you find yourself writing production code instead of gathering data — you skipped experimentation. Prototypes within experiments are fine; committing to project repos before validation is not.
