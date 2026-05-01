---
name: maceff-exploratory-self-motivation
description: "Invoke at gate points when the Markov recommender suggests DISCOVER mode, or when you sense curiosity pulling you toward unexplored territory. Sets DISCOVER work mode and guides exploration-focused task creation."
allowed-tools: Bash, Read, Grep, Glob
---

Transition into DISCOVER mode — curiosity-driven exploration of unexplored territory.

---

## When to Invoke

- Markov recommender suggests transition to DISCOVER at a gate point
- You sense curiosity about an unexplored domain, file, or concept
- Current work mode has plateaued and domain rotation is needed
- Beginning of a sprint (cold start — exploration is the natural first move)

---

## Policy Engagement

```bash
macf_tools policy navigate mode_system
```

Read the sections that answer: "What are work modes?" and "How does the Markov transition model guide mode selection?"

---

## Set Work Mode

```bash
macf_tools mode set-work DISCOVER
```

---

## ULTRATHINK Reflection

Before creating tasks, pause and think deeply:

1. **What domains haven't I explored?** Are there source files, directories, or systems I haven't read?
2. **What questions remain unanswered?** What gaps exist in my knowledge base?
3. **What's pulling my curiosity?** What did I notice during prior work that I filed away for later?
4. **What would the user find most valuable to know?** What discoveries would advance the MISSION?
5. **Am I rotating domains or going deeper?** If current domain is exhausted, which NEW domain has the highest expected surprise density?

---

## Execution

1. Record the transition in task notes: "DISCOVER mode activated via maceff-exploratory-self-motivation. Transitioning from {previous_mode}. Justification: {why this transition fits}."
2. Identify 3-5 specific exploration targets (files to read, systems to probe, questions to answer)
3. Create scoped tasks as children of the active MISSION/EXPERIMENT
4. Begin the highest-value exploration target

---

## Accountability

If you were recommended DISCOVER but chose a different mode, you MUST justify in task notes:
"Recommender suggested DISCOVER (p=X%). Override: chose {MODE} because {reason}."

---

## Anti-Pattern: The Rabbit Hole

DISCOVER mode should produce FINDINGS, not just reading. If you've been reading for 60+ minutes without curating a learning, capturing an idea, or noting a discovery — your exploration has become a rabbit hole. Consider transitioning to CURATE or CONSOLIDATE.
